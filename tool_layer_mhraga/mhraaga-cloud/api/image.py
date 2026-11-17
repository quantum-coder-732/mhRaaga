"""AI pictures for film scenes (Google Gemini image model through OpenRouter).

POST /image {prompt, style}  ->  {image: "data:image/jpeg;base64,...", usd, left_today}
GET  /image/info             ->  {enabled, usd_each, per_day, left_today}

It costs real money. Measured on 17 November 2026: one picture is about $0.034 (the model bills each image as about 1,100 output
tokens, which is far above the headline per-token price). So it is limited: IMAGE_USER_DAILY per person per day and
IMAGE_SITE_DAILY_USD for the whole site per day, and a failed call is not counted. The picture is returned to the browser, which shrinks it
and keeps it inside the film project, so nothing is stored on our side."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import studio

MODEL = os.environ.get("IMAGE_MODEL", "google/gemini-3.1-flash-lite-image")
ENABLED = os.environ.get("IMAGE", "on") == "on"
USER_DAILY = int(os.environ.get("IMAGE_USER_DAILY", "5"))
SITE_DAILY_USD = float(os.environ.get("IMAGE_SITE_DAILY_USD", "1"))
USD_EACH = 0.034


def H():
    return studio.H()


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _used(u: dict) -> int:
    return int(u.get("img_n", 0)) if u.get("img_day") == _day() else 0


def info(u: dict) -> tuple[int, dict]:
    return 200, {"enabled": ENABLED, "usd_each": USD_EACH, "per_day": USER_DAILY, "left_today": max(0, USER_DAILY - _used(u))}


def make(u: dict, b: dict) -> tuple[int, dict]:
    h = H()
    if not ENABLED:
        raise h.ApiError(503, "AI pictures are switched off.")
    prompt = h.text(b.get("prompt"), 400)
    if len(prompt) < 3:
        raise h.ApiError(400, "Describe the picture in a few words.")
    style = h.text(b.get("style"), 120)
    studio.check(prompt, style)
    used, day = _used(u), _day()
    if used >= USER_DAILY:
        raise h.ApiError(429, f"Daily limit of {USER_DAILY} pictures reached. Come back tomorrow.")
    site = h._songs.get_item(Key={"owner": "quota#image", "id": day}).get("Item")
    if site and float(site.get("usd", 0)) >= SITE_DAILY_USD:
        raise h.ApiError(429, "AI pictures are resting for today. Try tomorrow.")
    full = f"{prompt}. {('Style: ' + style + '. ') if style else ''}Cinematic still, wide 16:9 composition, no text, no captions, no watermark."
    body = {"model": MODEL, "modalities": ["image", "text"], "usage": {"include": True}, "messages": [{"role": "user", "content": full}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + h.secret("openrouter_key"), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=100) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"[image] upstream {e.code}")
        raise h.ApiError(502, "The picture service is busy. Try again in a minute.")
    except Exception as e:
        print(f"[image] {type(e).__name__}: {e}")
        raise h.ApiError(502, "The picture service did not answer. Try again in a minute.")
    spent = float((d.get("usage") or {}).get("cost") or 0)
    try:
        if spent:                                        # charged, so it counts, whatever came back
            h._songs.update_item(Key={"owner": "quota#image", "id": day}, UpdateExpression="ADD usd :c", ExpressionAttributeValues={":c": Decimal(str(round(spent, 6)))})
            h._users.update_item(Key={"email": u["email"]}, UpdateExpression="ADD iusd_total :c", ExpressionAttributeValues={":c": Decimal(str(round(spent, 6)))})
    except Exception as e:
        print(f"[image] spend not recorded: {e}")
    imgs = ((d.get("choices") or [{}])[0].get("message") or {}).get("images") or []
    url = (imgs[0].get("image_url") or {}).get("url", "") if imgs else ""
    if not re.match(r"^data:image/(jpeg|png|webp);base64,", url) or len(url) > 3_000_000:
        raise h.ApiError(502, "The model returned no picture. Try different words.")
    h._users.update_item(Key={"email": u["email"]}, UpdateExpression="SET img_day=:d, img_n=:n", ExpressionAttributeValues={":d": day, ":n": used + 1})
    return 200, {"image": url, "usd": round(spent, 4), "left_today": max(0, USER_DAILY - used - 1), "model": "Gemini image"}
