"""The Pecova music agent's webhook. Registered into Akanade with POST /api/v1/agents/register (see
scripts/register_agent.py): Akanade routes music tasks here and we answer {text, ok, confidence} where text is the
JSON brief. The brief is written by the cheapest capable OpenRouter model; every call's real usage/cost is recorded so
the admin cost page can show what *this app* used of the shared OpenRouter credits."""
from __future__ import annotations

import json
import re

import httpx
from fastapi import APIRouter, HTTPException, Request

from . import brain, config
from .store import Store  # noqa: F401  (type only)

router = APIRouter()
LANGS = ["hindi", "marathi", "sanskrit", "english"]
GENRES = ["bhajan", "raga", "devotional", "ghazal", "classical", "folk", "lofi", "pop", "ambient", "cinematic"]
TAALS = ["teental", "dadra", "keherwa", "rupak", "ektaal"]
INSTR = ["tanpura", "tabla", "harmonium", "flute", "sitar", "pad", "piano"]
SYSTEM = (
    "You are a music composer's assistant for Indian devotional, classical and contemporary music. Reply with ONE JSON "
    f"object only, keys: title, language (one of {LANGS}), genre (one of {GENRES}), raga (one of {list(brain.RAGAS)} or \"\"), "
    f"taal (one of {TAALS}), tempo_bpm (50-160), mood (short), instruments (array from {INSTR}), duration_seconds (30-180), "
    "lyrics (original words in the requested language - Devanagari for Hindi/Marathi/Sanskrit - 8-16 short lines in "
    "[Mukhda]/[Antara] sections; never reproduce a copyrighted song; \"\" for an instrumental). "
    "Never name or invoke any deity, god or religious figure unless the request itself does; write about music, the raga, the hour, nature and feeling. If the request says \"write and sing in X\", use language X. "
    "Pick a raga that suits the time of day and mood if none is named.")


def clamp(data: dict, prompt: str) -> dict:
    out = brain.fallback_brief(prompt, "", 60, False)
    for k in ("title", "mood"):
        if isinstance(data.get(k), str) and data[k].strip():
            out[k] = data[k].strip()[:80]
    if isinstance(data.get("lyrics"), str):
        out["lyrics"] = data["lyrics"].strip()
    for k, opts in (("language", LANGS), ("genre", GENRES), ("taal", TAALS)):
        v = str(data.get(k, "")).lower().strip()
        if v in opts:
            out[k] = v
    r = str(data.get("raga") or "").lower().strip()
    if r in brain.RAGAS or (r == "" and "raga" in data):
        out["raga"] = r
    try:
        out["tempo_bpm"] = max(50, min(160, int(data["tempo_bpm"])))
        out["duration_seconds"] = max(30, min(180, int(data["duration_seconds"])))
    except (KeyError, TypeError, ValueError):
        pass
    inst = [i.lower() for i in data.get("instruments") or [] if isinstance(i, str) and i.lower() in INSTR]
    if inst:
        out["instruments"] = inst
    return out


def ask_openrouter(prompt: str) -> tuple[dict, dict]:
    """Try the cheap models in order. Returns (brief_json, usage{model,in,out,cost})."""
    last = None
    for model in config.AGENT_MODELS:
        try:
            r = httpx.post("https://openrouter.ai/api/v1/chat/completions", timeout=60,
                           headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
                           json={"model": model, "temperature": 0.8, "usage": {"include": True},
                                 "response_format": {"type": "json_object"},
                                 "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
            r.raise_for_status()
            body = r.json()
            text = body["choices"][0]["message"]["content"]
            data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            u = body.get("usage") or {}
            return data, {"model": model, "in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0),
                          "cost": u.get("cost")}
        except Exception as e:  # try the next model
            last = e
    raise RuntimeError(f"all models failed: {last}")


@router.post("/agent/compose")
async def compose(request: Request):
    from .main import store, now
    if not config.AGENT_WEBHOOK_KEY or request.query_params.get("key") != config.AGENT_WEBHOOK_KEY:
        raise HTTPException(403, "bad agent key")
    body = await request.json()
    prompt = str(body.get("text") or "").strip()
    usage = {"model": "rule-based", "in": 0, "out": 0, "cost": 0.0}
    try:
        if not config.OPENROUTER_API_KEY:
            raise RuntimeError("no OPENROUTER_API_KEY")
        data, usage = ask_openrouter(prompt)
        ok, conf = True, 0.8
    except Exception as e:
        print(f"[agent] {e}; rule-based brief")
        data, ok, conf = {}, True, 0.4
    brief = clamp(data, prompt)
    tid = str(body.get("task_id") or now())
    store.put("usage", {"id": tid, "created_at": now(), "agent": "pecova-music-agent", **usage})
    return {"text": json.dumps(brief), "ok": ok, "confidence": conf}
