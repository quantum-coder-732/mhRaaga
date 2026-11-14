"""Neural voice: text to speech as real audio the browser can mix with the music (Suno-style), not device speech.

POST /tts {text, lang, style, voice}  ->  {url, seconds, cached}
  - The audio is made once by an OpenRouter audio model and cached in S3 under tts/<hash>.wav, shared by every user, so a
    replay costs nothing and is instant. CloudFront serves it; the browser decodes it and mixes it with the raga.
  - A strict system prompt makes the model read the text verbatim. Measured on seven languages with a transcribe-back check:
    gpt-audio matched 7/7 (Hindi, Marathi, Telugu, Tamil, Gujarati, Kannada, English). The cheap mini model matched 6/7 and
    once added extra sentences, so mini output that is far longer than the text should be is thrown away and redone on the
    full model.
  - Cost is capped: per user per day and for the whole site per day (actual cost from the API's usage field).
Honest limits: a hosted model, so it costs money per new line and needs the OpenRouter key; pronunciation of Indic text is
good but not perfect; it speaks, it does not sing to the melody."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone

import boto3
from decimal import Decimal

import studio

BUCKET = os.environ.get("SITE_BUCKET", "")
MODEL_FULL = os.environ.get("TTS_MODEL", "openai/gpt-audio")
MODEL_MINI = os.environ.get("TTS_MODEL_MINI", "openai/gpt-audio-mini")
USER_DAILY_USD = float(os.environ.get("TTS_USER_DAILY_USD", "0.60"))
SITE_DAILY_USD = float(os.environ.get("TTS_SITE_DAILY_USD", "12"))
MAX_CHARS = 320
RATE = 24000
VOICES = {"male": "onyx", "female": "shimmer"}
LANGS = {"hindi", "marathi", "telugu", "tamil", "gujarati", "kannada", "english", "sanskrit", "bengali", "punjabi"}
# style -> (model tier, how to deliver). Devotional and poem text always gets the full model; stories and explainers the mini one.
STYLES = {
    "bhajan": ("full", "in a calm, warm, sincere devotional voice, unhurried, with a soft breath between phrases"),
    "song": ("full", "in a gentle, warm, expressive voice, flowing and unhurried"),
    "poem": ("full", "in a tender, slow, soft voice with gentle pauses at line ends"),
    "pravachan": ("full", "in a measured, clear, warm voice with natural pauses"),
    "story": ("mini", "as a warm storyteller: expressive but calm"),
    "explainer": ("mini", "as a clear, friendly teacher"),
    "speech": ("mini", "naturally and clearly"),
    "narration": ("mini", "as a calm film narrator"),
}
_s3 = boto3.client("s3") if BUCKET else None


def H():
    return studio.H()


def _system(lang: str, how: str) -> str:
    return (f"You are a text-to-speech engine for {lang.title()}. Read the user's text aloud exactly, word for word, {how}. "
            "Never add an introduction, a greeting, a comment, a translation, humming, a sung syllable, or any word that is not in the text. Output only the spoken text.")


def _openrouter(model: str, lang: str, how: str, text: str, voice: str) -> tuple[bytes, float]:
    h = H()
    body = {"model": model, "modalities": ["text", "audio"], "audio": {"voice": voice, "format": "pcm16"}, "stream": True, "usage": {"include": True},
            "messages": [{"role": "system", "content": _system(lang, how)}, {"role": "user", "content": text}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + h.secret("openrouter_key"), "Content-Type": "application/json"})
    pcm, cost = bytearray(), 0.0
    r = _open(req)
    with r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            try:
                d = json.loads(line[5:])
            except ValueError:
                continue
            cost = float((d.get("usage") or {}).get("cost") or cost)
            for c in d.get("choices", []):
                a = (c.get("delta") or {}).get("audio") or {}
                if a.get("data"):
                    pcm += base64.b64decode(a["data"])
    return bytes(pcm), cost


def _open(req):
    """Open the streaming request. When the upstream is rate-limited or briefly down, wait and try again (within the Lambda's time),
    then report it as a retryable 503 so the browser can try again instead of dropping to the device voice."""
    h, start = H(), time.time()
    for attempt in range(4):
        try:
            return urllib.request.urlopen(req, timeout=22)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                print(f"[tts] upstream {e.code}")
                raise
            wait = min(4.0, float(e.headers.get("Retry-After") or 1.2 * (attempt + 1)))
            if attempt == 3 or time.time() - start + wait > 17:
                raise h.ApiError(503, "The voice service is busy. Trying again in a moment.")
            time.sleep(wait)


def _wav(pcm: bytes) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm)
    return b.getvalue()


def _expected_seconds(text: str) -> float:
    indic = bool(re.search(r"[ऀ-ൿ]", text))
    return len(text) / (9.0 if indic else 12.0)    # unhurried devotional reading


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _spent_site(h) -> float:
    it = h._songs.get_item(Key={"owner": "quota#tts", "id": _day()}).get("Item")
    return float(it.get("usd", 0)) if it else 0.0


def _add_spend(h, u: dict, usd: float) -> None:
    day = _day()
    h._songs.update_item(Key={"owner": "quota#tts", "id": day}, UpdateExpression="ADD usd :c", ExpressionAttributeValues={":c": Decimal(str(round(usd, 6)))})
    if u.get("tday") == day:
        h._users.update_item(Key={"email": u["email"]}, UpdateExpression="ADD tusd :c", ExpressionAttributeValues={":c": Decimal(str(round(usd, 6)))})
    else:
        h._users.update_item(Key={"email": u["email"]}, UpdateExpression="SET tday=:d, tusd=:c", ExpressionAttributeValues={":d": day, ":c": Decimal(str(round(usd, 6)))})


def info() -> tuple[int, dict]:
    return 200, {"enabled": bool(BUCKET), "voices": list(VOICES), "styles": list(STYLES), "max_chars": MAX_CHARS}


def speak(u: dict, b: dict) -> tuple[int, dict]:
    h = H()
    if not BUCKET:
        raise h.ApiError(503, "Neural voice is not available here.")
    text = re.sub(r"\[[^\]]*\]", "", h.text(b.get("text"), 2000)).strip()
    if not text:
        raise h.ApiError(400, "Nothing to speak.")
    if len(text) > MAX_CHARS:
        raise h.ApiError(400, f"Send at most {MAX_CHARS} characters at a time.")
    lang = h.text(b.get("lang"), 12).lower()
    lang = lang if lang in LANGS else "english"
    style = b.get("style") if b.get("style") in STYLES else "speech"
    voice = VOICES.get(b.get("voice"), VOICES["male"])
    studio.check(text)
    tier, how = STYLES[style]
    model = MODEL_FULL if tier == "full" else MODEL_MINI
    key = hashlib.sha256(f"v2|{model}|{voice}|{style}|{lang}|{text}".encode()).hexdigest()[:40]
    obj = f"tts/{key}.wav"
    try:                                                    # a hit is free and shared by everyone
        head = _s3.head_object(Bucket=BUCKET, Key=obj)
        return 200, {"url": "/" + obj, "seconds": float(head.get("Metadata", {}).get("secs", 0)), "cached": True}
    except Exception:
        pass
    day = _day()
    if (float(u.get("tusd", 0)) if u.get("tday") == day else 0.0) >= USER_DAILY_USD:
        raise h.ApiError(429, "Daily neural-voice limit reached. The device voice still works; come back tomorrow.")
    if _spent_site(h) >= SITE_DAILY_USD:
        raise h.ApiError(429, "The neural voice is resting for today. The device voice still works.")
    spent = 0.0
    try:
        pcm, cost = _openrouter(model, lang, how, text, voice)
        spent += cost
        secs = len(pcm) / 2 / RATE
        if tier == "mini" and secs > 2.2 * _expected_seconds(text) + 1.5:     # the mini model sometimes adds sentences: redo on the full model
            pcm, cost = _openrouter(MODEL_FULL, lang, how, text, voice)
            spent += cost
            secs = len(pcm) / 2 / RATE
    except h.ApiError:
        raise
    except Exception as e:
        print(f"[tts] {type(e).__name__}: {e}")
        raise h.ApiError(502, "The voice service did not answer. The device voice still works.")
    finally:
        if spent:
            try:
                _add_spend(h, u, spent)
            except Exception as e:
                print(f"[tts] spend not recorded: {e}")
    if secs < 0.3 or secs > 2.6 * _expected_seconds(text) + 4:
        raise h.ApiError(502, "The voice came back wrong. Try again.")
    _s3.put_object(Bucket=BUCKET, Key=obj, Body=_wav(pcm), ContentType="audio/wav", CacheControl="public,max-age=31536000,immutable", Metadata={"secs": f"{secs:.2f}"})
    return 200, {"url": "/" + obj, "seconds": round(secs, 2), "cached": False}
