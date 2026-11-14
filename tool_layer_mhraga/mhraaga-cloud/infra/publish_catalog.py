#!/usr/bin/env python3
"""Run the agentic loop, then publish: songs -> S3 (catalog/) and the shared playlist table, reference tunes -> S3 (library/).
usage: AWS_PROFILE=default python3 publish_catalog.py [--rounds 8] [--explore 8] [--improve 3] [--library ~/library] [--no-evolve] [--dry]"""
import argparse, json, sys, time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "music_engine_framework_layer"))
from mhraaga_engine.agentic import evolve, library  # noqa: E402

CATALOG = ROOT / "music_engine_framework_layer/mhraaga_engine/agentic/data/catalog"
OWNER = "playlist#common"
ap = argparse.ArgumentParser()
ap.add_argument("--rounds", type=int, default=8); ap.add_argument("--explore", type=int, default=8); ap.add_argument("--improve", type=int, default=3)
ap.add_argument("--library", default="~/library"); ap.add_argument("--no-evolve", action="store_true"); ap.add_argument("--dry", action="store_true")
a = ap.parse_args()

library.profiles(a.library)
stats = None if a.no_evolve else evolve.run(CATALOG, a.rounds, a.explore, a.improve)
if stats:
    print(f"made {stats['made']} candidates, {stats['improved']} improvements, mean reward curve {stats['curve']}  (credit: {stats['attribution']})")
cat = evolve.Catalog(CATALOG)
rows = cat.index()
print(f"catalog: {len(rows)} songs (cap {evolve.CAP}); per language:", {l: len(cat.of(l)) for l in evolve.LANGS})
prev = json.loads((CATALOG / "report.json").read_text()) if (CATALOG / "report.json").exists() else {}
stats = stats or prev.get("stats")
report = {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stats": stats, "policy_runs": evolve.Policy().s["runs"],
          "library": [{k: p[k] for k in ("file", "duration", "tonic_pc", "tempo", "raga_like")} for p in library.cached()]}
(CATALOG / "report.json").write_text(json.dumps(report, ensure_ascii=False))
if a.dry:
    sys.exit(0)

import boto3  # noqa: E402
s3 = boto3.client("s3", region_name="ap-south-1")
bucket = next(b["Name"] for b in s3.list_buckets()["Buckets"] if b["Name"].startswith("mhraaga-site-"))
put = lambda key, body, ct, cc="public,max-age=300": s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=ct, CacheControl=cc)

want = {f"catalog/songs/{s['id']}.json" for s in cat.songs.values()}
have = {o["Key"] for p in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="catalog/songs/") for o in p.get("Contents", [])}
for sid, s in cat.songs.items():
    key = f"catalog/songs/{sid}.json"
    if key not in have:
        put(key, json.dumps(s, ensure_ascii=False, separators=(",", ":")).encode(), "application/json")
for key in have - want:  # replaced songs leave S3, so at most CAP generated songs stay
    s3.delete_object(Bucket=bucket, Key=key)
put("catalog/index.json", (CATALOG / "index.json").read_bytes(), "application/json", "no-cache")
put("catalog/report.json", (CATALOG / "report.json").read_bytes(), "application/json", "no-cache")
put("catalog/policy.json", evolve.STATE.read_bytes(), "application/json", "no-cache")
print(f"s3: {len(want)} songs live, {len(have - want)} replaced songs removed")

lib = []
for p in library.cached():
    f = Path(a.library).expanduser() / p["file"]
    if f.suffix.lower() == ".mp3" and f.exists():
        key = "library/" + p["file"].replace(" ", "_")
        try:
            s3.head_object(Bucket=bucket, Key=key)
        except Exception:
            s3.upload_file(str(f), bucket, key, ExtraArgs={"ContentType": "audio/mpeg", "CacheControl": "public,max-age=86400"})
        lib.append({"title": f.stem.replace("-", " ").replace("_", " ")[:80], "file": key, "duration": p["duration"], "tempo": p["tempo"]})
put("library/index.json", json.dumps({"tunes": lib}, ensure_ascii=False).encode(), "application/json", "no-cache")
print(f"s3: {len(lib)} library tunes")

table = boto3.resource("dynamodb", region_name="ap-south-1").Table("mhraaga-songs")
old = {i["id"] for p in table.meta.client.get_paginator("query").paginate(TableName="mhraaga-songs", KeyConditionExpression="#o = :o", ExpressionAttributeNames={"#o": "owner"},
       ExpressionAttributeValues={":o": OWNER}, ProjectionExpression="id") for i in p["Items"]}
with table.batch_writer() as bw:
    for sid, s in cat.songs.items():
        if sid in old:
            continue
        item = {k: s[k] for k in ("id", "title", "raga", "tala", "tempo", "mood", "language", "duration", "created", "source", "prompt")}
        item["owner"] = OWNER
        item["brief"] = json.dumps(s["brief"], ensure_ascii=False)
        item["score"] = json.dumps(s["score"], ensure_ascii=False, separators=(",", ":"))
        bw.put_item(Item=json.loads(json.dumps(item, ensure_ascii=False), parse_float=Decimal))
    for sid in old - set(cat.songs):
        bw.delete_item(Key={"owner": OWNER, "id": sid})
print(f"dynamodb playlist: +{len(set(cat.songs) - old)} -{len(old - set(cat.songs))}")
