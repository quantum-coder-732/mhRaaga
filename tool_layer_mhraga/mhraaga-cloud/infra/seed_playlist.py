#!/usr/bin/env python3
"""Compose the starter songs through the live API and publish them to the shared playlist.
usage: SEED_EMAIL=.. SEED_PASSWORD=.. AWS_PROFILE=default python3 seed_playlist.py https://<cloudfront>"""
import json, os, sys, urllib.request
import boto3

BASE = sys.argv[1].rstrip("/")
OWNER = "playlist#common"
SONGS = [
    dict(prompt="A Krishna bansuri bhajan at dawn, gentle and flowing, like the flute calling the gopis", raga="Bhairav", lead="bansuri", language="hindi", tonic=233, duration=100),
    dict(prompt="An evening aarti for Krishna, serene and devotional, with a soft tabla", raga="Yaman", lead="bansuri", language="hindi", tonic=183, duration=100),
    dict(prompt="A Marathi abhang in praise of Vitthal, joyful and steady", raga="gopi:108", lead="veena", language="marathi", tonic=233, duration=100),
    dict(prompt="Midnight meditation, deep and still, nothing but the raga and the drone", raga="Malkauns", lead="harmonium", tonic=234, instrumental=True, duration=100),
    dict(prompt="A Sanskrit lullaby for the sunrise, peaceful and bright", raga="Bhoopali", lead="bansuri", language="sanskrit", tonic=233, duration=100),
    dict(prompt="The rasa dance under the autumn moon, sixteen thousand hearts and one flute", raga="gopi:16000", lead="bansuri", tala="keherwa", language="hindi", tonic=234, duration=110),
]

def call(path, body=None, token=None, method=None):
    req = urllib.request.Request(BASE + "/api" + path, data=json.dumps(body).encode() if body is not None else None, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

tok = call("/auth/login", {"email": os.environ["SEED_EMAIL"], "password": os.environ["SEED_PASSWORD"]})["token"]
table = boto3.resource("dynamodb", region_name="ap-south-1").Table("mhraaga-songs")
have = {s["title"] for s in call("/playlist")["songs"]}
for spec in SONGS:
    s = call("/compose", spec, tok)
    if s["title"] in have:
        call("/songs/" + s["id"], token=tok, method="DELETE"); continue
    item = table.get_item(Key={"owner": os.environ["SEED_EMAIL"].lower(), "id": s["id"]})["Item"]
    item["owner"] = OWNER
    table.put_item(Item=item)
    call("/songs/" + s["id"], token=tok, method="DELETE")
    print("added:", s["title"], "|", s["raga"], s["tala"], s["source"])
print("playlist now:", [x["title"] for x in call("/playlist")["songs"]])
