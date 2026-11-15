"""mhRaaga API: one Lambda behind API Gateway (HTTP API). Stdlib + boto3 only (boto3 ships with the Lambda runtime).

Routes (all under /api):
  POST /translate (auth)  text -> another language
  POST /playlist/{id}/play|download  public counters
  GET  /health, /ragas, /ragas/{name|gopi:N|mela:N}, /playlist, /playlist/{id}   public
  POST /auth/signup, /auth/login            public, returns a 7-day signed token
  GET  /me, /songs, /songs/{id}             signed in
  POST /compose                             signed in: prompt -> LLM brief -> raga score, saved to the library
  DELETE /songs/{id}                        signed in
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote

import boto3
from boto3.dynamodb.conditions import Key

from mhraaga_engine import catalog, compose, get_raga, make_brief
from mhraaga_engine.brief import TARGETS, detect_language, translate
from mhraaga_engine.tala import TALAS

import admin
import jobs
import studio
from mhraaga_engine import styles
import team
import voice

USERS = os.environ.get("USERS_TABLE", "mhraaga-users")
SONGS = os.environ.get("SONGS_TABLE", "mhraaga-songs")
PARAM_PREFIX = os.environ.get("PARAM_PREFIX", "/mhraaga")
DAILY_LIMIT = int(os.environ.get("DAILY_COMPOSE_LIMIT", "30"))
SIGNUP_OPEN = os.environ.get("SIGNUP_OPEN", "true") == "true"
ORIGIN_SECRET = os.environ.get("ORIGIN_SECRET", "")  # set by CloudFront; blocks direct hits on the API Gateway URL
TOKEN_SECONDS = 7 * 24 * 3600
MAX_FAILS, LOCK_SECONDS = 8, 600

_db = boto3.resource("dynamodb")
_users, _songs = _db.Table(USERS), _db.Table(SONGS)
_ssm = boto3.client("ssm")
_cache: dict[str, str] = {}
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def secret(name: str) -> str:
    if name not in _cache:
        try:
            _cache[name] = _ssm.get_parameter(Name=f"{PARAM_PREFIX}/{name}", WithDecryption=True)["Parameter"]["Value"]
        except Exception as e:
            print(f"[ssm] {name}: {type(e).__name__}")
            _cache[name] = ""
    return _cache[name]


# ---------------------------------------------------------------- tokens + passwords
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(email: str, key: str | None = None) -> str:
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps({"sub": email, "exp": int(time.time()) + TOKEN_SECONDS}).encode())
    sig = hmac.new((key or secret("jwt_secret")).encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(sig)}"


def read_token(token: str, key: str | None = None) -> str | None:
    try:
        head, body, sig = token.split(".")
        want = hmac.new((key or secret("jwt_secret")).encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(want, _unb64(sig)):
            return None
        data = json.loads(_unb64(body))
        return data["sub"] if data["exp"] > time.time() else None
    except Exception:
        return None


def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"{_b64(salt)}${_b64(h)}"


def check_pw(pw: str, stored: str) -> bool:
    salt, h = stored.split("$")
    return hmac.compare_digest(_unb64(h), hashlib.scrypt(pw.encode(), salt=_unb64(salt), n=2 ** 14, r=8, p=1, dklen=32))


# ---------------------------------------------------------------- helpers
def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def user_from(event: dict) -> dict:
    auth = (event.get("headers") or {}).get("authorization", "")
    sub = read_token(auth[7:]) if auth.lower().startswith("bearer ") else None
    if not sub:
        raise ApiError(401, "Sign in to continue.")
    item = _users.get_item(Key={"email": sub}).get("Item")
    if not item:
        raise ApiError(401, "Your session has expired. Sign in again.")
    if item.get("disabled"):
        raise ApiError(403, "This account is disabled. Ask an administrator.")
    return item


def body_of(event: dict, limit: int = 20000) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    if len(raw) > limit:
        raise ApiError(413, "Request too large.")
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except ValueError:
        raise ApiError(400, "Body must be a JSON object.")


def text(v, limit: int) -> str:
    return v.strip()[:limit] if isinstance(v, str) else ""


# ---------------------------------------------------------------- routes
def signup(event):
    if not SIGNUP_OPEN:
        raise ApiError(403, "Sign-ups are closed.")
    b = body_of(event)
    name, email, pw = text(b.get("name"), 60), text(b.get("email"), 254).lower(), b.get("password") or ""
    if not name or not EMAIL.match(email) or not isinstance(pw, str) or not 8 <= len(pw) <= 128:
        raise ApiError(400, "Enter a name, a valid email and a password of 8-128 characters.")
    try:
        _users.put_item(Item={"email": email, "name": name, "pw": hash_pw(pw), "created": datetime.now(timezone.utc).isoformat(),
                              "fails": 0, "locked_until": 0, "qday": today(), "qn": 0},
                        ConditionExpression="attribute_not_exists(email)")
    except _db.meta.client.exceptions.ConditionalCheckFailedException:
        raise ApiError(409, "That email is already registered. Sign in instead.")
    return 201, {"token": make_token(email), "user": {"name": name, "email": email}}


def login(event):
    b = body_of(event)
    email, pw = text(b.get("email"), 254).lower(), b.get("password") or ""
    item = _users.get_item(Key={"email": email}).get("Item") if EMAIL.match(email) else None
    now = int(time.time())
    if item and int(item.get("locked_until", 0)) > now:
        raise ApiError(429, "Too many wrong passwords. Try again in a few minutes.")
    if not item or not isinstance(pw, str) or not check_pw(pw, item["pw"]):
        if item:
            fails = int(item.get("fails", 0)) + 1
            _users.update_item(Key={"email": email}, UpdateExpression="SET fails=:f, locked_until=:l",
                               ExpressionAttributeValues={":f": 0 if fails >= MAX_FAILS else fails,
                                                          ":l": now + LOCK_SECONDS if fails >= MAX_FAILS else 0})
        raise ApiError(401, "Wrong email or password.")
    if item.get("disabled"):
        raise ApiError(403, "This account is disabled. Ask an administrator.")
    _users.update_item(Key={"email": email}, UpdateExpression="SET fails=:z, last_login=:t", ExpressionAttributeValues={":z": 0, ":t": datetime.now(timezone.utc).isoformat()})
    return 200, {"token": make_token(email), "user": {"name": item["name"], "email": email}}


def me(event):
    u = user_from(event)
    used = int(u["qn"]) if u.get("qday") == today() else 0
    return 200, {"name": u["name"], "email": u["email"], "composed_today": used, "daily_limit": int(u.get("limit", DAILY_LIMIT)), "admin": admin.is_admin(u),
                 "role": "admin" if admin.is_admin(u) else "user"}


def rename_me(event):
    u = user_from(event)
    name = text(body_of(event).get("name"), 60)
    if not name:
        raise ApiError(400, "Enter a name.")
    _users.update_item(Key={"email": u["email"]}, UpdateExpression="SET #n=:n", ExpressionAttributeNames={"#n": "name"}, ExpressionAttributeValues={":n": name})
    return 200, {"name": name, "email": u["email"]}


def take_quota(u: dict) -> None:
    day, used = today(), int(u["qn"]) if u.get("qday") == today() else 0
    limit = int(u.get("limit", DAILY_LIMIT))
    if used >= limit:
        raise ApiError(429, f"Daily limit of {limit} songs reached. Come back tomorrow.")
    _users.update_item(Key={"email": u["email"]}, UpdateExpression="SET qday=:d, qn=:n",
                       ExpressionAttributeValues={":d": day, ":n": used + 1})


def make_song(event):
    u = user_from(event)
    b = body_of(event)
    prompt = text(b.get("prompt"), 800)
    if len(prompt) < 3:
        raise ApiError(400, "Describe the song in a few words.")
    style = text(b.get("style"), 200)
    studio.check(prompt, text(b.get("lyrics"), 3000), text(b.get("title"), 60), style)
    take_quota(u)
    raga_in = text(b.get("raga"), 40)
    if raga_in:
        try:
            get_raga(raga_in)
        except Exception:
            raise ApiError(400, f"Unknown raga '{raga_in}'.")
    tala_in = text(b.get("tala"), 20)
    opts = {"raga": raga_in, "tala": tala_in if tala_in in TALAS else "", "language": text(b.get("language"), 12).lower(),
            "lead": text(b.get("lead"), 12), "lyrics": text(b.get("lyrics"), 3000), "instrumental": bool(b.get("instrumental")), "poem": bool(b.get("poem")),
            "tempo": int(b["tempo"]) if isinstance(b.get("tempo"), (int, float)) and 40 <= b["tempo"] <= 180 else 0}
    hint = styles.parse(style)                        # style words -> lead, tala, tempo, extra players (what you choose by hand still wins)
    opts["style"] = style
    for k in ("lead", "tala"):
        if not opts[k] and hint[k]:
            opts[k] = hint[k]
    if not opts["tempo"] and hint["tempo"] and not opts["poem"]:
        opts["tempo"] = hint["tempo"]
    for k, v in studio.learned_defaults(opts["language"] or detect_language(prompt)).items():  # what the self-learning loop found works best
        if k == "tala" and not opts["tala"]:
            opts["tala"] = v
        elif k == "lead" and not opts["lead"]:
            opts["lead"] = v
        elif k == "tempo" and not opts["tempo"] and not opts["poem"]:
            opts["tempo"] = v
    brief = make_brief(prompt, opts, secret("openrouter_key"))
    if text(b.get("title"), 60):
        brief["title"] = text(b.get("title"), 60)
    if not raga_in and hint["ragas"] and brief.get("source") == "fallback":
        brief["raga"] = hint["ragas"][0]
    try:
        tonic = float(b["tonic"]) if b.get("tonic") in (183, 233, 234, 183.0, 233.0, 234.0) else None
        raga = get_raga(brief["raga"], tonic)
    except Exception:
        raga, brief["raga"] = get_raga("yaman"), "Yaman"
    dur = b.get("duration") if isinstance(b.get("duration"), (int, float)) else (150 if opts["poem"] else 90)
    score = compose(raga, brief.get("tala", ""), brief.get("tempo_bpm", 72), int(dur), brief.get("lyrics", ""),
                    sa=tonic, lead=brief.get("lead", "bansuri"), instrumental=bool(opts["instrumental"]), poem=bool(opts["poem"]), style=style, ensemble=hint["ensemble"])
    sid = f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:6]}"
    summary = {"id": sid, "title": text(brief.get("title"), 60) or "Untitled", "raga": raga["name"], "tala": score["meta"]["tala"],
               "tempo": score["meta"]["tempo"], "mood": brief.get("mood", ""), "language": brief.get("language", ""),
               "duration": score["duration"], "created": datetime.now(timezone.utc).isoformat(), "source": brief["source"],
               "prompt": prompt, "style": style}
    _songs.put_item(Item=_dec({"owner": u["email"], **summary, "brief": json.dumps({k: v for k, v in brief.items() if k != "usage"}),
                          "score": json.dumps(score, separators=(",", ":"))}))
    return 200, {**summary, "brief": {k: v for k, v in brief.items() if k != "usage"}, "score": score}


PLAYLIST_OWNER = "playlist#common"   # the shared, read-only playlist everybody can hear


def list_songs(event, owner=None):
    owner = owner or user_from(event)["email"]
    r = _songs.query(KeyConditionExpression=Key("owner").eq(owner), ScanIndexForward=False, Limit=100,
                     ProjectionExpression="id,title,raga,tala,tempo,mood,#l,#d,created,#s,prompt,plays,downloads,#y",      # "style" is a DynamoDB reserved word
                     ExpressionAttributeNames={"#l": "language", "#s": "source", "#d": "duration", "#y": "style"})
    return 200, {"songs": r["Items"]}


def get_song(event, sid, owner=None):
    owner = owner or user_from(event)["email"]
    it = _songs.get_item(Key={"owner": owner, "id": sid}).get("Item")
    if not it:
        raise ApiError(404, "Song not found.")
    it.pop("owner", None)
    it["score"], it["brief"] = json.loads(it["score"]), json.loads(it["brief"])
    return 200, it


def delete_song(event, sid):
    u = user_from(event)
    _songs.delete_item(Key={"owner": u["email"], "id": sid})
    return 200, {"deleted": sid}


# ---------------------------------------------------------------- entry
def _dec(o):
    """DynamoDB rejects floats: round-trip through JSON with Decimal."""
    from decimal import Decimal
    return json.loads(json.dumps(o), parse_float=Decimal)



def _num(o):
    from decimal import Decimal
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError


def team_route(method: str, path: str, event: dict):
    """Shared studio: /teams, /teams/{pid}, .../invite, .../members/{email}, .../layers[/{lid}], .../comments, .../assemble, .../render."""
    u, parts = user_from(event), path.strip("/").split("/")
    q = event.get("queryStringParameters") or {}
    if len(parts) == 1:
        return team.mine(u) if method == "GET" else team.create(u, body_of(event)) if method == "POST" else (_ for _ in ()).throw(ApiError(405, "Not allowed."))
    pid, rest = parts[1], parts[2:]
    if not rest:
        return team.get(u, pid, str(q.get("since", ""))[:40]) if method == "GET" else team.delete(u, pid) if method == "DELETE" else (_ for _ in ()).throw(ApiError(405, "Not allowed."))
    if rest == ["invite"] and method == "POST":
        return team.invite(u, pid, body_of(event))
    if len(rest) == 2 and rest[0] == "members" and method == "DELETE":
        from urllib.parse import unquote
        return team.remove_member(u, pid, unquote(rest[1]))
    if rest == ["layers"] and method == "POST":
        return team.layer_save(u, pid, None, body_of(event, 400000))
    if len(rest) == 2 and rest[0] == "layers":
        return (team.layer_get(u, pid, rest[1]) if method == "GET" else team.layer_save(u, pid, rest[1], body_of(event, 400000)) if method == "PUT"
                else team.layer_delete(u, pid, rest[1]) if method == "DELETE" else (_ for _ in ()).throw(ApiError(405, "Not allowed.")))
    if rest == ["comments"] and method == "POST":
        return team.comment(u, pid, body_of(event))
    if rest == ["assemble"] and method == "GET":
        return team.assemble(u, pid)
    if rest == ["render"] and method == "POST":
        return team.render_song(u, pid, event, make_song)
    raise ApiError(404, "Not found.")


def handler(event, context=None):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = (event.get("rawPath") or "/").rstrip("/") or "/"
    if path.startswith("/api"):
        path = path[4:] or "/"
    try:
        if ORIGIN_SECRET and not hmac.compare_digest((event.get("headers") or {}).get("x-origin-verify", ""), ORIGIN_SECRET):
            raise ApiError(403, "Use the official site.")
        if method == "OPTIONS":
            status, out = 204, {}
        elif (method, path) == ("GET", "/health"):
            status, out = 200, {"ok": True, "time": datetime.now(timezone.utc).isoformat(), "talas": list(TALAS)}
        elif (method, path) == ("GET", "/ragas"):
            status, out = 200, catalog()
        elif (method, path) == ("GET", "/playlist"):
            status, out = list_songs(event, PLAYLIST_OWNER)
        elif method == "POST" and re.fullmatch(r"/playlist/[0-9a-f-]{10,40}/(play|download)", path):
            _, _, sid, what = path.split("/")
            field = "plays" if what == "play" else "downloads"
            try:
                r = _songs.update_item(Key={"owner": PLAYLIST_OWNER, "id": sid}, UpdateExpression=f"ADD {field} :one",
                                       ConditionExpression="attribute_exists(id)", ExpressionAttributeValues={":one": 1}, ReturnValues="UPDATED_NEW")
            except Exception:
                raise ApiError(404, "Song not found.")
            status, out = 200, {field: int(r["Attributes"][field])}
        elif method == "GET" and path.startswith("/playlist/"):
            sid = path[10:]
            if not re.fullmatch(r"[0-9a-f-]{10,40}", sid):
                raise ApiError(400, "Bad song id.")
            status, out = get_song(event, sid, PLAYLIST_OWNER)
        elif method == "GET" and path.startswith("/ragas/"):
            spec = unquote(path[7:])
            if not re.fullmatch(r"[A-Za-z0-9 _:.\-]{1,40}", spec):
                raise ApiError(400, "Bad raga.")
            try:
                status, out = 200, get_raga(spec)
            except Exception:
                raise ApiError(404, "Unknown raga.")
        elif (method, path) == ("POST", "/auth/signup"):
            status, out = signup(event)
        elif (method, path) == ("POST", "/auth/login"):
            status, out = login(event)
        elif (method, path) == ("GET", "/me"):
            status, out = me(event)
        elif (method, path) == ("PATCH", "/me"):
            status, out = rename_me(event)
        elif path == "/jobs" or path.startswith("/jobs/"):
            status, out = jobs.route(method, path[5:], event, user_from, body_of)
        elif path == "/admin" or path.startswith("/admin/"):
            status, out = admin.route(method, path[6:], event, user_from, body_of, event.get("queryStringParameters") or {})
        elif (method, path) == ("POST", "/translate"):
            u = user_from(event)
            b = body_of(event)
            src, to = text(b.get("text"), 2500), text(b.get("to"), 12).lower()
            if len(src) < 1 or to not in TARGETS:
                raise ApiError(400, "Give some text and a target language.")
            studio.check(src)
            try:
                status, out = 200, {"text": translate(src, to, secret("openrouter_key")), "to": to}
            except RuntimeError as e:
                raise ApiError(503, str(e))
        elif (method, path) == ("GET", "/rules"):
            status, out = 200, studio.rules_public()
        elif (method, path) == ("GET", "/rules/full"):
            u = user_from(event)
            studio.need_admin(u)
            status, out = 200, {k: v for k, v in studio.get_rules(force=True).items() if k != "learned"}
        elif (method, path) == ("PUT", "/rules"):
            status, out = 200, studio.put_rules(user_from(event), body_of(event, 30000))
        elif (method, path) == ("GET", "/people"):
            status, out = studio.people_list(user_from(event))
        elif (method, path) == ("POST", "/people"):
            status, out = studio.people_create(user_from(event), body_of(event))
        elif path.startswith("/people/"):
            parts = path.split("/")[2:]
            u = user_from(event)
            if len(parts) == 1 and method == "PUT":
                status, out = studio.people_update(u, parts[0], body_of(event, 12000))
            elif len(parts) == 1 and method == "DELETE":
                status, out = studio.people_delete(u, parts[0])
            elif len(parts) == 2 and parts[1] == "learn" and method == "POST":
                status, out = studio.people_learn(u, parts[0], body_of(event, 14000))
            elif len(parts) == 2 and parts[1] == "samples" and method == "POST":
                status, out = studio.sample_add(u, parts[0], body_of(event, 3_800_000))
            elif len(parts) == 3 and parts[1] == "samples" and method == "GET" and parts[2].isdigit():
                status, out = studio.sample_get(u, parts[0], int(parts[2]))
            else:
                raise ApiError(404, "Not found.")
        elif (method, path) == ("POST", "/story/outline"):
            status, out = studio.story_outline(user_from(event), body_of(event))
        elif (method, path) == ("POST", "/story/section"):
            status, out = studio.story_section(user_from(event), body_of(event))
        elif (method, path) == ("GET", "/films"):
            status, out = studio.films_list(user_from(event))
        elif (method, path) == ("POST", "/films"):
            status, out = studio.film_save(user_from(event), None, body_of(event, 400000))
        elif (method, path) == ("POST", "/film/plan"):
            status, out = studio.film_plan(user_from(event), body_of(event))
        elif path.startswith("/films/") and method in ("GET", "PUT", "DELETE"):
            fid, u = path[7:], user_from(event)
            status, out = (studio.film_get(u, fid) if method == "GET" else studio.film_save(u, fid, body_of(event, 400000)) if method == "PUT" else studio.film_delete(u, fid))
        elif (method, path) == ("GET", "/tts/info"):
            status, out = voice.info()
        elif (method, path) == ("POST", "/tts"):
            status, out = voice.speak(user_from(event), body_of(event, 4000))
        elif path == "/teams" or path.startswith("/teams/"):
            status, out = team_route(method, path, event)
        elif (method, path) == ("POST", "/compose"):
            status, out = make_song(event)
        elif (method, path) == ("GET", "/songs"):
            status, out = list_songs(event)
        elif path.startswith("/songs/") and method in ("GET", "DELETE"):
            sid = path[7:]
            if not re.fullmatch(r"[0-9a-f-]{10,40}", sid):
                raise ApiError(400, "Bad song id.")
            status, out = (get_song if method == "GET" else delete_song)(event, sid)
        else:
            raise ApiError(404, "Not found.")
    except ApiError as e:
        status, out = e.status, {"error": e.message}
    except Exception as e:  # never leak internals
        print(f"[error] {type(e).__name__}: {e}")
        status, out = 500, {"error": "Something went wrong. Try again."}
    return {"statusCode": status, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store",
                                              "X-Content-Type-Options": "nosniff"},
            "body": json.dumps(out, default=_num) if status != 204 else ""}
