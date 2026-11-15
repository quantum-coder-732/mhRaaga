"""Full AI songs with a sung voice, made by Google's Lyria 3 through OpenRouter (no GPU of ours, about $0.08 a song).

POST /lyria {title, style, lyrics, language}   start a song; answers at once with {id, status:"pending"}
GET  /lyria/{id}                               {status: pending|done|failed, audio, error}

A song takes 20-60 seconds, longer than a web request may last, so the request only saves a row and starts the same Lambda again in the
background (an "Event" invoke). That run calls the model, saves the MP3 in the site bucket under lyria/<random>.mp3 and marks the row done.
The finished song is an ordinary row of the user's library (source "lyria", with an `audio` link), so it shows in My songs.

It costs real money, so it is limited: LYRIA_USER_DAILY songs per user per day (any model) and LYRIA_SITE_DAILY_USD for the whole site per day.
Honest limits: a hosted model; it is not driven by our raga engine (the raga is whatever the model picks from the style words); Hindi
words are mostly sung right but some blur; we cannot see the audio quality from here."""
from __future__ import annotations

import base64
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import boto3

import studio

BUCKET = os.environ.get("SITE_BUCKET", "")
# the music models OpenRouter offers (checked against its model list): name -> (OpenRouter id, price per song in USD, what you get, minutes)
MODELS = {
    "pro": ("google/lyria-3-pro-preview", 0.08, "Full song, about 2 minutes", 2.0),
    "clip": ("google/lyria-3-clip-preview", 0.04, "30-second clip, half the price", 0.5),
}
ENABLED = os.environ.get("LYRIA", "on") == "on" and bool(BUCKET)
USER_DAILY = int(os.environ.get("LYRIA_USER_DAILY", "3"))
SITE_DAILY_USD = float(os.environ.get("LYRIA_SITE_DAILY_USD", "2"))
_s3 = boto3.client("s3") if BUCKET else None
_lam = None


def H():
    return studio.H()


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_prompt(title: str, style: str, lyrics: str, language: str, minutes: float = 2.0) -> str:
    style = style or "devotional, harmonium, bansuri flute, tabla, dholak, manjira, warm acoustic"
    length = "30-second clip of a" if minutes < 1 else "complete original"
    head = (f"Create a {length} {language.title()} song of about {'30 seconds' if minutes < 1 else '2 minutes'} titled \"{title}\". "
            f"A natural, expressive human lead vocal sings the lyrics below clearly and in tune. Style: {style}. "
            "Real acoustic instruments, unhurried, warm. No electronic or EDM sounds.")
    return head + (f"\n\nLyrics:\n{lyrics}" if lyrics else "\n\nWrite the lyrics yourself, in the same language.")


def info(u: dict) -> tuple[int, dict]:
    h = H()
    used = int(u.get("ly_n", 0)) if u.get("ly_day") == _day() else 0
    return 200, {"enabled": ENABLED, "per_day": USER_DAILY, "left_today": max(0, USER_DAILY - used),
                 "models": [{"key": k, "usd": v[1], "label": v[2]} for k, v in MODELS.items()]}


def create(u: dict, b: dict, function_name: str) -> tuple[int, dict]:
    global _lam
    h = H()
    if not ENABLED:
        raise h.ApiError(503, "Full AI songs are switched off.")
    title = h.text(b.get("title"), 80) or "AI song"
    style = h.text(b.get("style"), 200)
    lyrics = h.text(b.get("lyrics"), 1800)
    language = h.text(b.get("language"), 12).lower() or "hindi"
    model = b.get("model") if b.get("model") in MODELS else "pro"
    studio.check(" ".join([title, style, lyrics]))
    day = _day()
    used = int(u.get("ly_n", 0)) if u.get("ly_day") == day else 0
    if used >= USER_DAILY:
        raise h.ApiError(429, f"Daily limit of {USER_DAILY} full AI songs reached. Come back tomorrow.")
    site = h._songs.get_item(Key={"owner": "quota#lyria", "id": day}).get("Item")
    if site and float(site.get("usd", 0)) >= SITE_DAILY_USD:
        raise h.ApiError(429, "Full AI songs are resting for today. Try tomorrow.")
    sid = "ly" + str(int(time.time() * 1000)) + "-" + secrets.token_hex(3)
    key = "lyria/" + secrets.token_hex(12) + ".mp3"
    h._songs.put_item(Item={"owner": u["email"], "id": sid, "title": title, "source": "lyria", "status": "pending", "style": style, "language": language,
                            "lyrics": lyrics, "model": model, "audio": "/" + key, "created": datetime.now(timezone.utc).isoformat(), "plays": 0})
    h._users.update_item(Key={"email": u["email"]}, UpdateExpression="SET ly_day=:d, ly_n=:n", ExpressionAttributeValues={":d": day, ":n": used + 1})
    _lam = _lam or boto3.client("lambda")
    _lam.invoke(FunctionName=function_name, InvocationType="Event",
                Payload=json.dumps({"lyria_job": {"owner": u["email"], "id": sid, "key": key, "model": MODELS[model][0], "prompt": build_prompt(title, style, lyrics, language, MODELS[model][3])}}).encode())
    return 202, {"id": sid, "status": "pending"}


def status(u: dict, sid: str) -> tuple[int, dict]:
    h = H()
    it = h._songs.get_item(Key={"owner": u["email"], "id": sid}).get("Item")
    if not it or it.get("source") != "lyria":
        raise h.ApiError(404, "Song not found.")
    return 200, {"id": sid, "status": it.get("status", "done"), "audio": it.get("audio") if it.get("status") == "done" else None, "error": it.get("error", ""), "title": it.get("title", "")}


def run(job: dict) -> dict:
    """The background half: call the model, store the MP3, mark the row."""
    h = H()
    owner, sid = job["owner"], job["id"]
    spent = 0.0
    try:
        body = {"model": job.get("model") or MODELS["pro"][0], "modalities": ["text", "audio"], "stream": True, "usage": {"include": True},
                "messages": [{"role": "user", "content": job["prompt"]}]}
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + h.secret("openrouter_key"), "Content-Type": "application/json"})
        mp3, text = bytearray(), ""
        with urllib.request.urlopen(req, timeout=170) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:") or line.endswith("[DONE]"):
                    continue
                try:
                    d = json.loads(line[5:])
                except ValueError:
                    continue
                spent = float((d.get("usage") or {}).get("cost") or spent)
                for c in d.get("choices", []):
                    dl = c.get("delta") or {}
                    if (dl.get("audio") or {}).get("data"):
                        mp3 += base64.b64decode(dl["audio"]["data"])
                    if isinstance(dl.get("content"), str):
                        text += dl["content"]
        if len(mp3) < 50_000:
            raise RuntimeError("the model returned no song")
        _s3.put_object(Bucket=BUCKET, Key=job["key"], Body=bytes(mp3), ContentType="audio/mpeg", CacheControl="public,max-age=31536000,immutable")
        secs = int(len(mp3) * 8 / 192000)               # Lyria sends about 192 kbps; an estimate for the list
        h._songs.update_item(Key={"owner": owner, "id": sid}, UpdateExpression="SET #s=:s, #d=:d, tex=:t",
                             ExpressionAttributeNames={"#s": "status", "#d": "duration"}, ExpressionAttributeValues={":s": "done", ":d": Decimal(secs), ":t": text[:3000]})
        return {"ok": True, "bytes": len(mp3), "usd": spent}
    except Exception as e:
        print(f"[lyria] {type(e).__name__}: {e}")
        msg = "The song service is busy or did not answer. Try again in a minute." if not isinstance(e, urllib.error.HTTPError) else f"The song service said {e.code}."
        h._songs.update_item(Key={"owner": owner, "id": sid}, UpdateExpression="SET #s=:s, #e=:e", ExpressionAttributeNames={"#s": "status", "#e": "error"},
                             ExpressionAttributeValues={":s": "failed", ":e": msg})
        if not spent:                                    # nothing was charged, so the try does not count against today's limit
            try:
                h._users.update_item(Key={"email": owner}, UpdateExpression="ADD ly_n :m", ExpressionAttributeValues={":m": -1})
            except Exception:
                pass
        return {"ok": False, "error": str(e)[:200]}
    finally:
        if spent:
            try:
                h._songs.update_item(Key={"owner": "quota#lyria", "id": _day()}, UpdateExpression="ADD usd :c", ExpressionAttributeValues={":c": Decimal(str(round(spent, 6)))})
                h._users.update_item(Key={"email": owner}, UpdateExpression="ADD lusd_total :c", ExpressionAttributeValues={":c": Decimal(str(round(spent, 6)))})
            except Exception as e:
                print(f"[lyria] spend not recorded: {e}")
