"""Studio routes: AI rules (ethics) in S3, People profiles with voice samples, Stories / Pravachan / Explainer scripts.
Imported by handler.py; helpers are fetched lazily from it to avoid a circular import."""
from __future__ import annotations

import base64
import json
import math
import os
import re
import time
import uuid
from datetime import datetime, timezone

import boto3

from mhraaga_engine.brief import chat

BUCKET = os.environ.get("SITE_BUCKET", "")
ADMINS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
_s3 = boto3.client("s3") if BUCKET else None
_rules_cache: tuple[float, dict] = (0.0, {})
MAX_SAMPLES, MAX_SAMPLE_BYTES = 20, 2_500_000
STORY_DAILY_CALLS = 80

DEFAULT_RULES = {
    "version": 1,
    "principles": [
        "Create music, poems and talks that respect people. No hate, harassment, or content that sexualises minors.",
        "Never imitate a real person's voice or words without their written consent. People profiles are for you, or people who agreed.",
        "Do not present generated talks as the words of a real teacher, politician or public figure.",
        "Religious and spiritual content is offered with respect and without claiming medical, legal or miracle outcomes.",
        "Generated text is a draft written by a model; check facts before sharing.",
    ],
    "blocked_terms": ["child porn", "csam", "how to make a bomb", "suicide method", "nazi propaganda", "kill all"],
    "blocked_impersonation": ["in the voice of", "sounds exactly like", "clone the voice of", "fake speech by"],
    "max_prompt_chars": 800,
    "learned": {},
}


def H():
    import handler as h  # noqa: PLC0415
    return h


# ------------------------------------------------------------------ rules
def get_rules(force: bool = False) -> dict:
    global _rules_cache
    if not force and time.time() - _rules_cache[0] < 60 and _rules_cache[1]:
        return _rules_cache[1]
    rules = dict(DEFAULT_RULES)
    if _s3:
        for key, field in (("rules/ethics.json", None), ("rules/learned.json", "learned")):
            try:
                d = json.loads(_s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
                if field:
                    rules[field] = d
                else:
                    rules.update(d)
            except Exception:
                pass
    _rules_cache = (time.time(), rules)
    return rules


def check(*texts: str) -> None:
    """Raise 422 when any text breaks the live rules. Called on every prompt, lyric, story topic, translation and profile text."""
    r = get_rules()
    low = " ".join(t.lower() for t in texts if t)
    for term in r.get("blocked_terms", []) + r.get("blocked_impersonation", []):
        if term and term.lower() in low:
            raise H().ApiError(422, "This request goes against the AI rules for mhRaaga. See Studio > Rules.")


def rules_public() -> dict:
    r = get_rules()
    return {"version": r.get("version"), "updated": r.get("updated"), "principles": r.get("principles", []), "blocked_count": len(r.get("blocked_terms", [])),
            "learned": {k: v for k, v in r.get("learned", {}).items() if k in ("updated", "runs", "curve", "leaders")}}


def need_admin(u: dict) -> None:
    if u["email"].lower() not in ADMINS:
        raise H().ApiError(403, "Only an administrator can change the rules.")


def put_rules(u: dict, b: dict) -> dict:
    need_admin(u)
    cur = get_rules(force=True)
    new = {"principles": [str(x)[:300] for x in b.get("principles", cur["principles"])][:20],
           "blocked_terms": [str(x).lower()[:80] for x in b.get("blocked_terms", cur["blocked_terms"])][:300],
           "blocked_impersonation": [str(x).lower()[:80] for x in b.get("blocked_impersonation", cur["blocked_impersonation"])][:60],
           "max_prompt_chars": int(b.get("max_prompt_chars", cur["max_prompt_chars"]))}
    new["version"] = int(cur.get("version", 1)) + 1
    new["updated"] = datetime.now(timezone.utc).isoformat()
    new["updated_by"] = u["email"]
    if _s3:
        _s3.put_object(Bucket=BUCKET, Key=f"rules/history/{cur.get('version', 1):05d}.json", Body=json.dumps(cur).encode(), ContentType="application/json")
        _s3.put_object(Bucket=BUCKET, Key="rules/ethics.json", Body=json.dumps(new, ensure_ascii=False).encode(), ContentType="application/json")
    get_rules(force=True)
    return {"ok": True, "version": new["version"]}


def learned_defaults(language: str) -> dict:
    """What the self-learning loop found works best for this language (tala, lead, tempo). Empty when nothing is learned yet."""
    lead = get_rules().get("learned", {}).get("leaders", {}).get(language, {})
    out = {}
    if lead.get("tala", {}).get("arm"):
        out["tala"] = lead["tala"]["arm"]
    if lead.get("lead", {}).get("arm"):
        out["lead"] = lead["lead"]["arm"]
    if lead.get("tempo", {}).get("arm"):
        out["tempo"] = int(lead["tempo"]["arm"])
    return out


# ------------------------------------------------------------------ people
def _pkey(u): return f"people#{u['email']}"


def _person(u, pid):
    h = H()
    if not re.fullmatch(r"p-[0-9a-f]{8,16}", pid):
        raise h.ApiError(400, "Bad person id.")
    it = h._songs.get_item(Key={"owner": _pkey(u), "id": pid}).get("Item")
    if not it:
        raise h.ApiError(404, "Person not found.")
    return it


def _view(p, full=False):
    out = {"id": p["id"], "name": p["name"], "role": p.get("role", ""), "consent": bool(p.get("consent")), "style_notes": p.get("style_notes", ""),
           "samples": int(p.get("sample_count", 0)), "sources": p.get("sources", [])}
    if full:
        out["excerpts"] = len(p.get("excerpts", []))
    return out


def people_list(u):
    h = H()
    from boto3.dynamodb.conditions import Key  # noqa: PLC0415
    r = h._songs.query(KeyConditionExpression=Key("owner").eq(_pkey(u)), Limit=50)
    return 200, {"people": [_view(p, True) for p in r["Items"]]}


def people_create(u, b):
    h = H()
    name = h.text(b.get("name"), 60)
    if len(name) < 2:
        raise h.ApiError(400, "Give the person a name.")
    check(name, h.text(b.get("role"), 80))
    n = len(people_list(u)[1]["people"])
    if n >= 20:
        raise h.ApiError(400, "You can keep up to 20 people.")
    pid = "p-" + uuid.uuid4().hex[:10]
    item = {"owner": _pkey(u), "id": pid, "name": name, "role": h.text(b.get("role"), 80), "consent": bool(b.get("consent")), "style_notes": "",
            "excerpts": [], "sources": [], "sample_count": 0, "created": datetime.now(timezone.utc).isoformat()}
    h._songs.put_item(Item=item)
    return 200, _view(item, True)


def people_update(u, pid, b):
    h = H()
    p = _person(u, pid)
    sets, vals, names = [], {}, {}
    if "style_notes" in b:
        check(b["style_notes"]) if isinstance(b["style_notes"], str) else None
        sets.append("style_notes=:s"); vals[":s"] = h.text(b["style_notes"], 1500)
    if "role" in b:
        sets.append("#r=:r"); vals[":r"] = h.text(b["role"], 80); names["#r"] = "role"
    if "consent" in b:
        sets.append("consent=:c"); vals[":c"] = bool(b["consent"])
    if "sources" in b and isinstance(b["sources"], list):
        sets.append("sources=:u"); vals[":u"] = [h.text(x, 200) for x in b["sources"]][:30]  # links are stored as references only, never fetched
    if not sets:
        return 200, _view(p, True)
    h._songs.update_item(Key={"owner": _pkey(u), "id": pid}, UpdateExpression="SET " + ", ".join(sets), ExpressionAttributeValues=vals, **({"ExpressionAttributeNames": names} if names else {}))
    return 200, _view(_person(u, pid), True)


def people_delete(u, pid):
    h = H()
    p = _person(u, pid)
    for n in range(int(p.get("sample_count", 0))):
        try:
            _s3.delete_object(Bucket=BUCKET, Key=f"samples/{_hash(u)}/{pid}/{n}")
        except Exception:
            pass
    h._songs.delete_item(Key={"owner": _pkey(u), "id": pid})
    return 200, {"deleted": pid}


def _hash(u):
    import hashlib  # noqa: PLC0415
    return hashlib.sha256(u["email"].encode()).hexdigest()[:20]


def sample_add(u, pid, b):
    h = H()
    p = _person(u, pid)
    if not p.get("consent"):
        raise h.ApiError(403, "Tick the consent box first: this is your own voice, or the person gave written permission.")
    n = int(p.get("sample_count", 0))
    if n >= MAX_SAMPLES:
        raise h.ApiError(400, f"Up to {MAX_SAMPLES} samples per person.")
    mime = h.text(b.get("mime"), 40)
    if not re.fullmatch(r"audio/(webm|ogg|mpeg|mp4|wav|x-wav)(;.*)?", mime):
        raise h.ApiError(400, "Upload an audio file (webm, ogg, mp3, mp4 or wav).")
    try:
        raw = base64.b64decode(b.get("audio_b64", ""), validate=True)
    except Exception:
        raise h.ApiError(400, "Bad audio data.")
    if not 2000 < len(raw) <= MAX_SAMPLE_BYTES:
        raise h.ApiError(400, "Each sample must be under 2.5 MB and at least a second long.")
    _s3.put_object(Bucket=BUCKET, Key=f"samples/{_hash(u)}/{pid}/{n}", Body=raw, ContentType=mime.split(";")[0], Metadata={"mime": mime.split(";")[0]})
    h._songs.update_item(Key={"owner": _pkey(u), "id": pid}, UpdateExpression="SET sample_count=:n", ExpressionAttributeValues={":n": n + 1})
    return 200, {"samples": n + 1}


def sample_get(u, pid, n):
    h = H()
    p = _person(u, pid)
    if not 0 <= n < int(p.get("sample_count", 0)):
        raise h.ApiError(404, "Sample not found.")
    o = _s3.get_object(Bucket=BUCKET, Key=f"samples/{_hash(u)}/{pid}/{n}")
    return 200, {"mime": o.get("ContentType", "audio/webm"), "audio_b64": base64.b64encode(o["Body"].read()).decode()}


def people_learn(u, pid, b):
    """Learn a speaker's manner from a transcript the user pasted (e.g. from a video's 'Show transcript'). Nothing is downloaded."""
    h = H()
    p = _person(u, pid)
    t = h.text(b.get("text"), 12000)
    if len(t) < 300:
        raise h.ApiError(400, "Paste at least a few paragraphs of the transcript.")
    check(t)
    take_story_calls(u, 1)
    notes = chat("You study a speaker's manner from a transcript. Write 6 to 10 short bullet points on diction, pace, sentence length, favourite images and stories, how they open and close, "
                 "and the values they return to. Describe the style only; do not quote long passages and do not claim to be the person. Plain text, under 170 words.",
                 f"Existing notes:\n{p.get('style_notes', '')}\n\nNew transcript:\n{t[:9000]}", h.secret("openrouter_key"), max_tokens=500)
    ex = (p.get("excerpts") or [])[-4:] + [t[:1800]]
    h._songs.update_item(Key={"owner": _pkey(u), "id": pid}, UpdateExpression="SET style_notes=:s, excerpts=:e",
                         ExpressionAttributeValues={":s": notes[:1500], ":e": ex})
    return 200, _view(_person(u, pid), True)


# ------------------------------------------------------------------ stories / pravachan / explainer
def take_story_calls(u, n):
    h = H()
    day = h.today()
    used = int(u.get("sn", 0)) if u.get("sday") == day else 0
    if used + n > STORY_DAILY_CALLS:
        raise h.ApiError(429, "Daily limit for long scripts reached. Come back tomorrow.")
    h._users.update_item(Key={"email": u["email"]}, UpdateExpression="SET sday=:d, sn=:n", ExpressionAttributeValues={":d": day, ":n": used + n})
    u["sday"], u["sn"] = day, used + n


KINDS = {"story": "a warm, vivid story told by a narrator", "pravachan": "a spiritual discourse (pravachan) with teaching, illustration and reflection",
         "explainer": "a clear explainer video script that teaches one idea step by step"}


def _style(u, person_id):
    if not person_id:
        return ""
    p = _person(u, person_id)
    ex = "\n---\n".join((p.get("excerpts") or [])[-2:])[:3000]
    return (f"\nSpeak in the manner described below (style only; never say you are {p['name']}, never invent quotes for them):\nStyle notes: {p.get('style_notes', '')}\n"
            f"Sample of how this speaker talks:\n{ex}")


def story_outline(u, b):
    h = H()
    topic, lang = h.text(b.get("topic"), 400), h.text(b.get("language"), 12).lower() or "english"
    kind = b.get("kind") if b.get("kind") in KINDS else "story"
    mins = max(1, min(30, int(b.get("minutes", 5) or 5)))
    if len(topic) < 3:
        raise h.ApiError(400, "Say what the piece is about.")
    check(topic)
    take_story_calls(u, 1)
    n = max(1, min(14, math.ceil(mins / 2.5)))
    out = chat(f"You plan {KINDS[kind]} of about {mins} minutes in {lang}. Reply with ONE JSON object: "
               f'{{"title": str, "sections": [{{"heading": str, "brief": str (one sentence on what this section covers)}}] }} with exactly {n} sections that build to a satisfying end. '
               "Respect the AI rules: kind, truthful, no hate, no real-person impersonation." + _style(u, b.get("person_id")),
               f"Topic: {topic}", h.secret("openrouter_key"), max_tokens=1400, as_json=True, timeout=13.0)
    d = json.loads(out[out.index("{"): out.rindex("}") + 1])
    secs = [{"heading": str(s.get("heading", ""))[:100], "brief": str(s.get("brief", ""))[:300]} for s in d.get("sections", [])][:n]
    if not secs:
        raise h.ApiError(503, "Could not plan that. Try again.")
    return 200, {"title": str(d.get("title", topic))[:100], "kind": kind, "language": lang, "minutes": mins, "sections": secs, "calls_left": STORY_DAILY_CALLS - int(u.get("sn", 0))}


def story_section(u, b):
    h = H()
    kind = b.get("kind") if b.get("kind") in KINDS else "story"
    lang, title, heading, brief = h.text(b.get("language"), 12).lower() or "english", h.text(b.get("title"), 100), h.text(b.get("heading"), 100), h.text(b.get("brief"), 300)
    idx, total = int(b.get("idx", 0)), max(1, int(b.get("total", 1)))
    tail = h.text(b.get("previous_tail"), 400)
    check(title, heading, brief)
    take_story_calls(u, 1)
    words = 300 if kind != "pravachan" else 340
    out = chat(f"You write section {idx + 1} of {total} of {KINDS[kind]} titled '{title}', in {lang}, in native script. About {words} words, written to be spoken aloud: short sentences, no markdown, no stage directions. "
               'Reply with ONE JSON object: {"text": narration string, "points": [3 short on-screen key phrases]}. '
               + ("This is the last section: close with a gentle conclusion. " if idx + 1 == total else "") + _style(u, b.get("person_id")),
               f"Section: {heading}. Covers: {brief}. The previous section ended: {tail}", h.secret("openrouter_key"), max_tokens=1500, as_json=True, timeout=13.0)
    d = json.loads(out[out.index("{"): out.rindex("}") + 1])
    text_ = str(d.get("text", "")).strip()
    check(text_)
    if len(text_) < 40:
        raise h.ApiError(503, "That section came out empty. Try again.")
    return 200, {"text": text_[:4000], "points": [str(x)[:80] for x in d.get("points", [])][:4], "calls_left": STORY_DAILY_CALLS - int(u.get("sn", 0))}
