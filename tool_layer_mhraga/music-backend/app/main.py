"""aRaaga API: generation jobs, tracks, discovery, playback.

Run:  .venv/bin/uvicorn app.main:app --port 9100
"""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import agent, auth, brain, config, cost, engine, s3
from .store import Store

app = FastAPI(title="aRaaga")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
store = Store()
jobs_q: "queue.Queue[str]" = queue.Queue()
MAX_PROMPT = 1000


def who(request: Request, x_user_id: str = Header(default="guest")) -> str:
    """The signed-in user's email (from the bearer token); X-User-Id only when MUSIC_ALLOW_GUEST=1."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        sub = auth.read_token(header[7:])
        if sub and store.get("users", sub):
            return sub
        raise HTTPException(401, "Your session has expired. Sign in again.")
    if config.ALLOW_GUEST:
        return x_user_id
    raise HTTPException(401, "Sign in to continue.")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class GenerateIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=MAX_PROMPT)
    lyrics: str = Field(default="", max_length=3000)
    instrumental: bool = False
    duration_seconds: int = Field(default=60, ge=20, le=180)
    title: str = Field(default="", max_length=80)
    public: bool = True
    language: str = Field(default="", max_length=12)  # "" = let the AI decide from the prompt


def _public(t: dict, user: str) -> dict:
    out = {k: v for k, v in t.items() if k != "liked_by"}
    out["likes"] = len(t.get("liked_by", []))
    out["liked"] = user in t.get("liked_by", [])
    out["audio_url"] = f"/api/music/audio/{t['file']}"
    out["can_delete"] = t.get("creator") == user or _is_admin(user, store.get("users", user))
    return out


def run_job(job_id: str) -> None:
    job = store.get("jobs", job_id)
    if not job:
        return
    store.update("jobs", job_id, status="PROCESSING")
    try:
        req = job["request"]
        brief = brain.compose(req["prompt"], req["lyrics"], req["duration_seconds"], req["instrumental"], AK_TOKENS.get(job["user"], ""), (req.get("language") or "").lower())
        if req["title"]:
            brief["title"] = req["title"]
        track_id = uuid.uuid4().hex[:12]
        # rendering is CPU-bound numpy; keep it off the event loop (this runs in the worker thread)
        t0 = time.time()
        audio = engine.render(brief, config.AUDIO_DIR, track_id, AK_TOKENS.get(job["user"], ""))
        render_s = time.time() - t0
        f = config.AUDIO_DIR / audio["file"]
        s3.upload(f, f"tracks/{audio['file']}")  # idempotent; also covers the synth-only genres
        lu = brief.pop("_usage", {"in": 0, "out": 0, "estimated": False})
        spend = cost.song_cost(polly_chars=audio.get("polly_chars", 0), llm_in=lu["in"], llm_out=lu["out"],
                               llm_estimated=lu["estimated"], llm_cost=lu.get("cost"), render_seconds=render_s,
                               size_bytes=f.stat().st_size, duration_seconds=audio["duration_seconds"])
        track = {
            "id": track_id, "creator": job["user"], "title": brief["title"], "prompt": req["prompt"],
            "genre": brief["genre"], "language": brief["language"], "raga": brief["raga"], "taal": brief["taal"],
            "mood": brief["mood"], "tempo_bpm": brief["tempo_bpm"], "instruments": brief["instruments"],
            "lyrics": brief["lyrics"], "brief_source": brief["source"], "file": audio["file"],
            "duration_seconds": audio["duration_seconds"], "peaks": audio["peaks"],
            "visibility": "public" if req["public"] else "private", "plays": 0, "liked_by": [], "cost": spend,
            "created_at": now(),
        }
        store.put("tracks", track)
        store.update("jobs", job_id, status="COMPLETED", track_id=track_id)
    except Exception as e:  # surface any failure on the job instead of killing the worker
        store.update("jobs", job_id, status="FAILED", error=str(e)[:300])


def worker() -> None:
    while True:
        run_job(jobs_q.get())


SAMPLES = [
    ("Evening Yaman Alaap", "a calm Yaman raga, flute and tabla"),
    ("Dawn Bhairav Alaap", "Bhairav raga at dawn, meditative, sitar and tanpura"),
    ("Malkauns Midnight", "deep meditative Malkauns raga at midnight with tabla"),
    ("Bhupali Joy", "joyful Bhupali raga, energetic, harmonium and tabla"),
    ("Lofi Rain Study", "calm lofi beat for studying, soft piano"),
    ("Cinematic Sunrise", "cinematic ambient pad, uplifting sunrise"),
]


def seed_samples() -> None:
    if store.all("tracks"):
        return
    for title, prompt in SAMPLES:
        jid = uuid.uuid4().hex[:12]
        store.put("jobs", {"id": jid, "status": "QUEUED", "user": "raaga", "created_at": now(),
                           "request": {"prompt": prompt, "lyrics": "", "instrumental": False,
                                       "duration_seconds": 45, "title": title, "public": True}})
        jobs_q.put(jid)


@app.on_event("startup")
def startup():
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    for j in store.all("jobs"):  # resume work interrupted by a restart
        if j["status"] in ("QUEUED", "PROCESSING"):
            jobs_q.put(j["id"])
    if config.SEED_SAMPLES:
        seed_samples()


AK_TOKENS: dict[str, str] = {}


def _is_admin(email: str, u: dict | None) -> bool:
    u = u or {}
    return (email in config.ADMINS or (u.get("role") or "").lower() in config.ADMIN_ROLES
            or (u.get("name") or "").strip().casefold() in config.ADMIN_NAMES)


def _session(user: dict) -> dict:
    return {"token": auth.make_token(user["id"]), "user": {"email": user["id"], "name": user["name"]}}


app.include_router(agent.router)


@app.post("/api/auth/signup", status_code=201)
def signup(body: SignupIn):
    email = body.email.strip().lower()
    if not auth.valid_email(email):
        raise HTTPException(422, "Enter a valid email address.")
    if store.get("users", email):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = {"id": email, "name": body.name.strip(), "pw": auth.hash_password(body.password), "created_at": now()}
    store.put("users", user)
    return _session(user)


@app.post("/api/auth/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    auth.throttle(email)
    user = store.get("users", email)
    sso = auth.akanade_login(email, body.password)  # same credentials as Akanade
    if sso:
        if not user:
            user = {"id": email, "name": sso["name"], "pw": "", "created_at": now(), "sso": True}
        user["role"] = sso["role"]  # Akanade's role and name decide who may see costs
        user["name"] = sso["name"]
        store.put("users", user)
        AK_TOKENS[email] = sso["token"]  # the user's own Akanade token, kept in memory only (never stored)
        return _session(user)
    if not user or not user.get("pw") or not auth.verify_password(body.password, user["pw"]):
        auth.record_failure(email)
        raise HTTPException(401, "Invalid email or password.")
    return _session(user)


def admin(user: str = Depends(who)) -> str:
    u = store.get("users", user) or {}
    if _is_admin(user, u):
        return user
    raise HTTPException(403, "Admins only.")


@app.get("/api/admin/costs")
def admin_costs(_: str = Depends(admin)):
    """Per-song cost, totals, by creator and by day (admins / senior managers only)."""
    rows = [t for t in store.all("tracks") if t.get("cost")]
    songs = [{"id": t["id"], "title": t["title"], "creator": t["creator"], "language": t["language"], "genre": t["genre"],
              "created_at": t["created_at"], "duration_seconds": t["duration_seconds"], "plays": t.get("plays", 0),
              **t["cost"],
              "delivery_usd_to_date": round(t["cost"]["delivery_usd_per_play"] * t.get("plays", 0), 5)} for t in rows]
    songs.sort(key=lambda r: r["created_at"], reverse=True)

    def agg(key):
        out: dict = {}
        for r in songs:
            k = key(r)
            a = out.setdefault(k, {"songs": 0, "create_usd": 0.0, "polly_chars": 0, "llm_tokens": 0, "plays": 0})
            a["songs"] += 1; a["create_usd"] = round(a["create_usd"] + r["create_usd"], 5)
            a["polly_chars"] += r["polly_chars"]; a["llm_tokens"] += r["llm_tokens_in"] + r["llm_tokens_out"]; a["plays"] += r["plays"]
        return out
    n = len(songs) or 1
    raaga_llm = round(sum(r["llm_usd"] for r in songs), 5)
    models: dict = {}
    for u in store.all("usage"):
        m = models.setdefault(u.get("model", "?"), {"calls": 0, "tokens": 0, "usd": 0.0})
        m["calls"] += 1; m["tokens"] += int(u.get("in", 0)) + int(u.get("out", 0)); m["usd"] = round(m["usd"] + float(u.get("cost") or 0), 6)
    credits = None
    if config.OPENROUTER_MANAGEMENT_KEY:
        try:
            import httpx
            d = httpx.get("https://openrouter.ai/api/v1/credits", timeout=8,
                          headers={"Authorization": f"Bearer {config.OPENROUTER_MANAGEMENT_KEY}"}).json()["data"]
            credits = {"total_credits": d["total_credits"], "total_usage": d["total_usage"],
                       "remaining": round(d["total_credits"] - d["total_usage"], 4)}
        except Exception:
            credits = {"error": "could not read OpenRouter credits"}
    openrouter = {"akanade_connected": bool(config.AKANADE_TOKEN) or any(m != "rule-based" for m in models),
                  "raaga_tokens": sum(r["llm_tokens_in"] + r["llm_tokens_out"] for r in songs),
                  "raaga_usd": raaga_llm, "by_model": models, "account": credits,
                  "raaga_share_of_usage": (round(raaga_llm / credits["total_usage"], 4)
                                           if credits and credits.get("total_usage") else None)}
    return {"openrouter": openrouter, "currency": "USD", "estimate": True, "songs": songs,
            "totals": {"songs": len(songs), "create_usd": round(sum(r["create_usd"] for r in songs), 4),
                       "avg_create_usd": round(sum(r["create_usd"] for r in songs) / n, 5),
                       "polly_chars": sum(r["polly_chars"] for r in songs),
                       "llm_tokens": sum(r["llm_tokens_in"] + r["llm_tokens_out"] for r in songs),
                       "storage_usd_month": round(sum(r["storage_usd_month"] for r in songs), 5),
                       "delivery_usd_to_date": round(sum(r["delivery_usd_to_date"] for r in songs), 5)},
            "by_creator": agg(lambda r: r["creator"]), "by_day": agg(lambda r: r["created_at"][:10]),
            "prices": {"polly_per_m_chars": config.PRICE_POLLY_NEURAL_PER_M_CHARS,
                       "llm_per_m_tokens_in_out": [config.PRICE_LLM_IN_PER_M_TOKENS, config.PRICE_LLM_OUT_PER_M_TOKENS],
                       "ec2_per_hour": config.PRICE_EC2_PER_HOUR, "s3_per_gb_month": config.PRICE_S3_PER_GB_MONTH,
                       "cdn_per_gb": config.PRICE_CDN_PER_GB}}


@app.get("/api/auth/me")
def me(user: str = Depends(who)):
    u = store.get("users", user)
    return {"email": user, "name": u["name"] if u else user, "admin": _is_admin(user, u)}


@app.get("/api/health")
def health():
    return {"ok": True, "store": store.backend, "akanade": bool(config.AKANADE_TOKEN), "queued": jobs_q.qsize()}


@app.post("/api/music/generate", status_code=202)
def generate(body: GenerateIn, x_user_id: str = Depends(who)):
    pending = [j for j in store.all("jobs") if j["user"] == x_user_id and j["status"] in ("QUEUED", "PROCESSING")]
    if len(pending) >= 3:
        raise HTTPException(429, "You already have 3 songs being created; wait for one to finish.")
    job = {"id": uuid.uuid4().hex[:12], "status": "QUEUED", "user": x_user_id, "created_at": now(),
           "request": body.model_dump()}
    store.put("jobs", job)
    jobs_q.put(job["id"])
    return {"job_id": job["id"], "status": "QUEUED"}


@app.get("/api/music/jobs/{job_id}")
def get_job(job_id: str, x_user_id: str = Depends(who)):
    job = store.get("jobs", job_id)
    if not job:
        raise HTTPException(404, "job not found")
    out = {"job_id": job_id, "status": job["status"], "error": job.get("error")}
    if job.get("track_id"):
        out["track"] = _public(store.get("tracks", job["track_id"]), x_user_id)
    return out


@app.get("/api/music/tracks")
def list_tracks(sort: str = Query("trending", pattern="^(trending|new|top)$"), genre: str = "", q: str = "",
                mine: bool = False, liked: bool = False, limit: int = Query(40, ge=1, le=100),
                x_user_id: str = Depends(who)):
    tracks = store.all("tracks")
    tracks = [t for t in tracks if t["visibility"] == "public" or (t["visibility"] == "private" and t["creator"] == x_user_id)]
    if mine:
        tracks = [t for t in tracks if t["creator"] == x_user_id]
    if liked:
        tracks = [t for t in tracks if x_user_id in t.get("liked_by", [])]
    if genre:
        tracks = [t for t in tracks if genre.lower() in (t["genre"], t["raga"], t["language"], t["mood"])]
    if q:
        ql = q.lower()
        tracks = [t for t in tracks if ql in " ".join((t["title"], t["prompt"], t["genre"], t["raga"], t["mood"])).lower()]
    hours = lambda t: (time.time() - datetime.fromisoformat(t["created_at"]).timestamp()) / 3600
    if sort == "new":
        tracks.sort(key=lambda t: t["created_at"], reverse=True)
    elif sort == "top":
        tracks.sort(key=lambda t: (len(t.get("liked_by", [])), t["plays"]), reverse=True)
    else:  # trending: engagement decayed by age, so new tracks can surface
        tracks.sort(key=lambda t: (t["plays"] + 5 * len(t.get("liked_by", [])) + 1) / (hours(t) + 2) ** 0.8, reverse=True)
    return {"tracks": [_public(t, x_user_id) for t in tracks[:limit]]}


@app.get("/api/music/tracks/{track_id}")
def get_track(track_id: str, x_user_id: str = Depends(who)):
    t = store.get("tracks", track_id)
    if not t or (t["visibility"] != "public" and t["creator"] != x_user_id):
        raise HTTPException(404, "track not found")
    return _public(t, x_user_id)


@app.delete("/api/music/tracks/{track_id}")
def delete_track(track_id: str, x_user_id: str = Depends(who)):
    """The creator can delete their own song; admins and senior managers can delete any (incl. from Discover)."""
    t = store.get("tracks", track_id)
    if not t:
        raise HTTPException(404, "track not found")
    if t.get("creator") != x_user_id and not _is_admin(x_user_id, store.get("users", x_user_id)):
        raise HTTPException(403, "You can only delete your own songs.")
    store.delete("tracks", track_id)
    try:
        (config.AUDIO_DIR / t["file"]).unlink(missing_ok=True)
    except Exception:
        pass
    return {"deleted": track_id}


@app.post("/api/music/tracks/{track_id}/like")
def like(track_id: str, x_user_id: str = Depends(who)):
    t = store.get("tracks", track_id)
    if not t:
        raise HTTPException(404, "track not found")
    liked = set(t.get("liked_by", []))
    liked.symmetric_difference_update({x_user_id})
    t = store.update("tracks", track_id, liked_by=sorted(liked))
    return _public(t, x_user_id)


@app.post("/api/music/tracks/{track_id}/play")
def play(track_id: str, x_user_id: str = Depends(who)):
    t = store.get("tracks", track_id)
    if not t:
        raise HTTPException(404, "track not found")
    return _public(store.update("tracks", track_id, plays=t["plays"] + 1), x_user_id)


@app.delete("/api/music/tracks/{track_id}")
def delete_track(track_id: str, x_user_id: str = Depends(who)):
    t = store.get("tracks", track_id)
    if not t or t["creator"] != x_user_id:
        raise HTTPException(404, "track not found")
    store.update("tracks", track_id, visibility="deleted")
    return {"ok": True}


@app.get("/api/music/genres")
def genres():
    return {"genres": ["bhajan", "raga", "devotional", "ghazal", "classical", "folk", "lofi", "pop", "ambient", "cinematic"],
            "ragas": list(brain.RAGAS), "languages": ["hindi", "marathi", "sanskrit", "english"]}


@app.get("/api/music/audio/{name}")
def audio(name: str):
    path = (config.AUDIO_DIR / name).resolve()
    if path.parent != config.AUDIO_DIR.resolve():
        raise HTTPException(404, "audio not found")
    if not path.is_file():
        s3.fetch(f"tracks/{name}", path)  # cache miss: pull from S3
    if not path.is_file():
        raise HTTPException(404, "audio not found")
    return FileResponse(path, media_type="audio/mpeg" if name.endswith(".mp3") else "audio/wav")


# Production: the built web app (music-web/dist copied to ./web) is served from the same origin as the API.
_WEB = Path(__file__).resolve().parent.parent / "web"
if _WEB.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_WEB, html=True), name="web")
