"""AI singer jobs: lyrics + style -> a finished song with a real sung vocal, made by the open YuE2 model on a GPU machine.

Why a queue: YuE2 needs an NVIDIA GPU with 24 GB of memory and takes minutes per song, so it cannot run in this Lambda. The Lambda only
records the request (a row in DynamoDB); a separate worker on a GPU machine (tool_layer_mhraga/gpu-worker/worker.py) claims queued rows,
runs YuE2, uploads an MP3 to S3 under yue/, and marks the row done. With no worker running, jobs wait in the queue and the dashboard says so.

Routes (all under /api, administrators only, because a GPU machine costs money and the model's weights are free for personal and
non-commercial use but need a licence for company use):
  GET  /jobs/info        is the engine switched on, is a worker alive, the daily limit
  POST /jobs             {style, lyrics, title} or {song_id, style} (sing one of your songs on its own raga melody) -> queued job
  GET  /jobs             the latest jobs
  GET  /jobs/{id}        one job
Rows: songs table, owner "job#yue", id = millisecond timestamp; the worker's heartbeat is owner "job#yue", id "0worker"."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal

from boto3.dynamodb.conditions import Key

import admin
import studio

try:
    from singer import build_request   # the singer layer: raga melody as a score for YuE2
except ImportError:                       # not packaged (for example in a bare test run)
    build_request = None

ENABLED = os.environ.get("GPU_ENGINE", "off").lower() == "on"
DAILY = int(os.environ.get("GPU_DAILY_JOBS", "5"))
OWNER = "job#yue"
ALIVE_SECONDS = 300


def H():
    return studio.H()


def _view(i: dict) -> dict:
    d = admin._clean(i)
    return {k: d.get(k) for k in ("id", "status", "title", "style", "who", "created", "started", "finished", "seconds", "audio", "error", "lines") if d.get(k) is not None}


def _alive(h) -> tuple[bool, str]:
    w = h._songs.get_item(Key={"owner": OWNER, "id": "0worker"}).get("Item")
    if not w:
        return False, ""
    seen = float(w.get("seen", 0))
    return time.time() - seen < ALIVE_SECONDS, str(w.get("name", ""))


def info(u: dict):
    admin.need(u)
    h = H()
    alive, name = _alive(h)
    return 200, {"enabled": ENABLED, "worker_alive": alive, "worker": name, "daily_limit": DAILY,
                 "note": "Needs a GPU machine running tool_layer_mhraga/gpu-worker/worker.py. YuE2 weights: free for personal and non-commercial use; companies need a licence."}


def create(u: dict, b: dict):
    admin.need(u)
    h = H()
    if not ENABLED:
        raise h.ApiError(503, "The AI singer is switched off. Set GPU_ENGINE=on on the stack and start a GPU worker.")
    style, lyrics, title = h.text(b.get("style"), 200), h.text(b.get("lyrics"), 3000), h.text(b.get("title"), 60)
    abc, sid = "", h.text(b.get("song_id"), 40)
    if sid:                                                  # sing one of your own songs: the layer writes its raga melody as the score
        it = h._songs.get_item(Key={"owner": u["email"], "id": sid}).get("Item")
        if not it:
            raise h.ApiError(404, "No such song in your library.")
        if build_request is None:
            raise h.ApiError(503, "The singer layer is not installed here.")
        song = {**it, "score": json.loads(it["score"])}
        req = build_request(song, style_words=style, language=h.text(b.get("language"), 20) or "Hindi", lyrics_override=lyrics or None, rid=sid)
        style, lyrics, abc, title = req["style"][:200], req["lyrics"], req["abc"], title or it.get("title", "")
    if len(style) < 3 or len(lyrics) < 8:
        raise h.ApiError(400, "Give a style (genre, mood, instruments) and some lyrics, or pick a song.")
    studio.check(style, lyrics, title)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = int(u["jn"]) if u.get("jday") == day else 0
    if n >= DAILY:
        raise h.ApiError(429, f"Daily limit of {DAILY} AI-singer jobs reached.")
    h._users.update_item(Key={"email": u["email"]}, UpdateExpression="SET jday=:d, jn=:n", ExpressionAttributeValues={":d": day, ":n": n + 1})
    jid = f"{int(time.time() * 1000):013d}"
    item = {"owner": OWNER, "id": jid, "status": "queued", "title": title or "Untitled", "style": style, "lyrics": lyrics, "who": u["email"],
            "created": datetime.now(timezone.utc).isoformat(), "lines": len([x for x in lyrics.splitlines() if x.strip()]), "ttl": int(time.time()) + 90 * 86400}
    if abc:
        item["abc"], item["cot"], item["song_id"] = abc, "melody", sid
    h._songs.put_item(Item=item)
    admin.audit(u, "job.create", jid, style[:80])
    return 201, {"job": _view(item)}


def list_jobs(u: dict):
    admin.need(u)
    h = H()
    r = h._songs.query(KeyConditionExpression=Key("owner").eq(OWNER), ScanIndexForward=False, Limit=25)
    return 200, {"jobs": [_view(i) for i in r.get("Items", []) if i["id"] != "0worker"]}


def get_job(u: dict, jid: str):
    admin.need(u)
    h = H()
    if not re.fullmatch(r"\d{13}", jid):
        raise h.ApiError(400, "Bad job id.")
    it = h._songs.get_item(Key={"owner": OWNER, "id": jid}).get("Item")
    if not it:
        raise h.ApiError(404, "No such job.")
    return 200, {"job": _view(it)}


def route(method: str, path: str, event: dict, user_from, body_of):
    h = H()
    u = user_from(event)
    parts = [p for p in path.strip("/").split("/") if p]
    if parts == ["info"] and method == "GET":
        return info(u)
    if parts == [] and method == "GET":
        return list_jobs(u)
    if parts == [] and method == "POST":
        return create(u, body_of(event))
    if len(parts) == 1 and method == "GET":
        return get_job(u, parts[0])
    raise h.ApiError(404, "Not found.")
