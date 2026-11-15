"""Admin dashboard API: users, roles, custom columns, usage and cloud cost. Every route needs an administrator.

Who is an administrator
  - the emails in ADMIN_EMAILS (the owners; they can never be demoted, disabled or deleted from the dashboard), and
  - any user whose record has role = "admin" (made by an owner on the Users tab).

Routes (all under /api/admin):
  GET    /admin/users                 list users with usage, role, status and custom column values
  POST   /admin/users                 add a user {name, email, password, role}
  PATCH  /admin/users/{email}         change name, role, disabled, daily_limit, password, reset_quota, extra{}
  POST   /admin/users/{email}/delete  delete a user and their songs {confirm: email}
  GET    /admin/schema                the custom columns (extra fields on a user record)
  PUT    /admin/schema                replace the custom columns
  GET    /admin/stats                 counts, sign-ups per day, voice spend per day, recent admin actions
  GET    /admin/costs[?refresh=1]     AWS cost (Cost Explorer), OpenRouter usage, voice spend; cached for an hour
Honest limits: AWS cost is for the whole AWS account (it includes anything else in it) and arrives a few hours late; OpenRouter
usage comes from the key's own counters."""
from __future__ import annotations

import calendar
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

import studio

BUCKET = os.environ.get("SITE_BUCKET", "")
ROLES = ("user", "admin")
COLUMN_TYPES = ("text", "number", "yesno", "date", "select")
MAX_COLUMNS = 20
CACHE_SECONDS = 3600
# AWS services that this project uses (to point out its share of an account-wide bill)
OURS = ("AWS Lambda", "Amazon DynamoDB", "Amazon Simple Storage Service", "Amazon CloudFront", "Amazon API Gateway", "Amazon Route 53",
        "AWS Systems Manager", "AmazonCloudWatch", "AWS Certificate Manager", "AWS Key Management Service")
_s3 = boto3.client("s3") if BUCKET else None


def H():
    return studio.H()


def is_admin(u: dict) -> bool:
    return u.get("email", "").lower() in studio.ADMINS or u.get("role") == "admin"


def is_owner(email: str) -> bool:
    return email.lower() in studio.ADMINS


def need(u: dict) -> None:
    if not is_admin(u):
        raise H().ApiError(403, "Administrators only.")


def _f(x):
    return float(x) if isinstance(x, Decimal) else x


def _clean(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- audit log
def audit(u: dict, what: str, target: str = "", detail: str = "") -> None:
    h = H()
    try:
        h._songs.put_item(Item={"owner": "admin#audit", "id": f"{int(time.time() * 1000):013d}", "who": u["email"], "what": what, "target": target[:120],
                                "detail": detail[:300], "at": datetime.now(timezone.utc).isoformat(),
                                "ttl": int(time.time()) + 180 * 86400})
    except Exception as e:
        print(f"[admin] audit not written: {e}")


def _recent_audit(n: int = 40) -> list:
    h = H()
    r = h._songs.query(KeyConditionExpression=Key("owner").eq("admin#audit"), ScanIndexForward=False, Limit=n)
    return [{k: v for k, v in _clean(i).items() if k in ("who", "what", "target", "detail", "at")} for i in r.get("Items", [])]


# ---------------------------------------------------------------- custom columns
def get_schema() -> list:
    h = H()
    it = h._songs.get_item(Key={"owner": "admin#config", "id": "schema"}).get("Item")
    return json.loads(it["columns"]) if it and it.get("columns") else []


def schema_get(u: dict):
    need(u)
    return 200, {"columns": get_schema(), "types": list(COLUMN_TYPES), "max": MAX_COLUMNS}


def schema_put(u: dict, b: dict):
    need(u)
    h = H()
    cols, seen = [], set()
    for c in (b.get("columns") or [])[:MAX_COLUMNS]:
        key = str(c.get("key", "")).strip().lower()
        label = h.text(c.get("label"), 40) or key
        typ = c.get("type") if c.get("type") in COLUMN_TYPES else "text"
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", key):
            raise h.ApiError(400, f"Column key '{key}' must be lowercase letters, digits or _ (start with a letter, up to 24).")
        if key in seen:
            raise h.ApiError(400, f"Column '{key}' is listed twice.")
        seen.add(key)
        col = {"key": key, "label": label, "type": typ}
        if typ == "select":
            opts = [h.text(o, 40) for o in (c.get("options") or []) if h.text(o, 40)][:12]
            if len(opts) < 2:
                raise h.ApiError(400, f"Column '{key}' is a select: give at least two options.")
            col["options"] = opts
        cols.append(col)
    h._songs.put_item(Item={"owner": "admin#config", "id": "schema", "columns": json.dumps(cols), "updated": datetime.now(timezone.utc).isoformat(), "by": u["email"]})
    audit(u, "columns", detail=", ".join(c["key"] for c in cols))
    return 200, {"columns": cols}


def _coerce(col: dict, v):
    """Check one custom value against its column. None or '' clears it."""
    h = H()
    if v is None or v == "":
        return None
    t = col["type"]
    if t == "number":
        try:
            return Decimal(str(float(v)))
        except (TypeError, ValueError):
            raise h.ApiError(400, f"'{col['label']}' must be a number.")
    if t == "yesno":
        if isinstance(v, bool):
            return v
        if str(v).lower() in ("yes", "true", "1"):
            return True
        if str(v).lower() in ("no", "false", "0"):
            return False
        raise h.ApiError(400, f"'{col['label']}' must be yes or no.")
    if t == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)):
            raise h.ApiError(400, f"'{col['label']}' must be a date like 2026-11-30.")
        return str(v)
    if t == "select":
        if str(v) not in col.get("options", []):
            raise h.ApiError(400, f"'{col['label']}' must be one of: {', '.join(col.get('options', []))}.")
        return str(v)
    return h.text(v, 200)


# ---------------------------------------------------------------- users
def _public(item: dict, cols: list, songs: int | None = None) -> dict:
    day = _today()
    extra = _clean(item.get("extra") or {})
    return {"email": item["email"], "name": item.get("name", ""), "role": "admin" if is_admin(item) else "user", "owner": is_owner(item["email"]),
            "disabled": bool(item.get("disabled")), "created": item.get("created", ""), "composed_today": int(item["qn"]) if item.get("qday") == day else 0,
            "limit": int(item.get("limit", H().DAILY_LIMIT)), "voice_usd_today": round(float(item["tusd"]), 4) if item.get("tday") == day and item.get("tusd") is not None else 0.0,
            "last_login": item.get("last_login", ""), "songs": songs, "extra": {c["key"]: extra.get(c["key"]) for c in cols}}


def _count_songs(email: str) -> int:
    h = H()
    r = h._songs.query(KeyConditionExpression=Key("owner").eq(email), Select="COUNT")
    return int(r.get("Count", 0))


def _all_users(limit: int = 500) -> list:
    h = H()
    items, kw = [], {}
    while len(items) < limit:
        r = h._users.scan(**kw)
        items += r.get("Items", [])
        if "LastEvaluatedKey" not in r:
            break
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    return items[:limit]


def users_list(u: dict):
    need(u)
    cols = get_schema()
    items = sorted(_all_users(), key=lambda i: i.get("created", ""), reverse=True)
    return 200, {"users": [_public(i, cols, _count_songs(i["email"])) for i in items], "columns": cols, "default_limit": H().DAILY_LIMIT, "roles": list(ROLES)}


def users_create(u: dict, b: dict):
    need(u)
    h = H()
    name, email, pw = h.text(b.get("name"), 60), h.text(b.get("email"), 254).lower(), b.get("password") or ""
    role = b.get("role") if b.get("role") in ROLES else "user"
    if not name or not h.EMAIL.match(email) or not isinstance(pw, str) or not 8 <= len(pw) <= 128:
        raise h.ApiError(400, "Enter a name, a valid email and a password of 8-128 characters.")
    if role == "admin" and not is_owner(u["email"]):
        raise h.ApiError(403, "Only an owner can add an administrator.")
    try:
        h._users.put_item(Item={"email": email, "name": name, "pw": h.hash_pw(pw), "created": datetime.now(timezone.utc).isoformat(), "fails": 0, "locked_until": 0,
                                "qday": h.today(), "qn": 0, "role": role}, ConditionExpression="attribute_not_exists(email)")
    except h._db.meta.client.exceptions.ConditionalCheckFailedException:
        raise h.ApiError(409, "That email is already registered.")
    audit(u, "user.create", email, f"role={role}")
    return 201, {"user": _public(h._users.get_item(Key={"email": email})["Item"], get_schema(), 0)}


def users_update(u: dict, email: str, b: dict):
    need(u)
    h = H()
    email = email.lower()
    item = h._users.get_item(Key={"email": email}).get("Item")
    if not item:
        raise h.ApiError(404, "No such user.")
    cols = {c["key"]: c for c in get_schema()}
    sets, rem, vals, names, did = [], [], {}, {}, []
    if "name" in b:
        nm = h.text(b.get("name"), 60)
        if not nm:
            raise h.ApiError(400, "The name cannot be empty.")
        sets.append("#n = :n"); names["#n"] = "name"; vals[":n"] = nm; did.append("name")
    if "role" in b:
        if b["role"] not in ROLES:
            raise h.ApiError(400, "Role must be user or admin.")
        if not is_owner(u["email"]):
            raise h.ApiError(403, "Only an owner can change roles.")
        if is_owner(email) and b["role"] != "admin":
            raise h.ApiError(400, "An owner is always an administrator.")
        sets.append("#r = :r"); names["#r"] = "role"; vals[":r"] = b["role"]; did.append(f"role={b['role']}")
    if "disabled" in b:
        if bool(b["disabled"]) and (is_owner(email) or email == u["email"].lower()):
            raise h.ApiError(400, "You cannot disable an owner or yourself.")
        if bool(b["disabled"]) and is_admin(item) and not is_owner(u["email"]):
            raise h.ApiError(403, "Only an owner can disable an administrator.")
        sets.append("disabled = :d"); vals[":d"] = bool(b["disabled"]); did.append("disabled" if b["disabled"] else "enabled")
    if "daily_limit" in b:
        if b["daily_limit"] in (None, ""):
            rem.append("#l"); names["#l"] = "limit"; did.append("limit=default")
        else:
            try:
                lim = int(b["daily_limit"])
            except (TypeError, ValueError):
                raise h.ApiError(400, "The daily limit must be a whole number.")
            if not 0 <= lim <= 1000:
                raise h.ApiError(400, "The daily limit must be 0 to 1000.")
            sets.append("#l = :l"); names["#l"] = "limit"; vals[":l"] = lim; did.append(f"limit={lim}")
    if b.get("reset_quota"):
        sets.append("qn = :z"); vals[":z"] = 0; sets.append("qday = :qd"); vals[":qd"] = h.today(); did.append("quota reset")
    if b.get("password"):
        pw = b["password"]
        if not isinstance(pw, str) or not 8 <= len(pw) <= 128:
            raise h.ApiError(400, "The password must be 8-128 characters.")
        if is_owner(email) and email != u["email"].lower():
            raise h.ApiError(403, "An owner's password can only be changed by that owner.")
        sets.append("pw = :pw"); vals[":pw"] = h.hash_pw(pw); sets.append("fails = :f0"); vals[":f0"] = 0; sets.append("locked_until = :l0"); vals[":l0"] = 0; did.append("password set")
    if isinstance(b.get("extra"), dict):
        extra = dict(_clean(item.get("extra") or {}))
        for k, v in b["extra"].items():
            if k not in cols:
                raise h.ApiError(400, f"There is no column '{k}'. Add it on the Columns tab first.")
            cv = _coerce(cols[k], v)
            if cv is None:
                extra.pop(k, None)
            else:
                extra[k] = cv
            did.append(f"{k}")
        sets.append("extra = :x"); vals[":x"] = json.loads(json.dumps(extra, default=lambda o: float(o) if isinstance(o, Decimal) else str(o)), parse_float=Decimal)
    if not (sets or rem):
        raise h.ApiError(400, "Nothing to change.")
    expr = ("SET " + ", ".join(sets) if sets else "") + (" REMOVE " + ", ".join(rem) if rem else "")
    kw = {"Key": {"email": email}, "UpdateExpression": expr.strip()}
    if names:
        kw["ExpressionAttributeNames"] = names
    if vals:
        kw["ExpressionAttributeValues"] = vals
    h._users.update_item(**kw)
    audit(u, "user.update", email, ", ".join(did))
    return 200, {"user": _public(h._users.get_item(Key={"email": email})["Item"], get_schema(), _count_songs(email))}


def users_delete(u: dict, email: str, b: dict):
    need(u)
    h = H()
    email = email.lower()
    if email == u["email"].lower() or is_owner(email):
        raise h.ApiError(400, "You cannot delete an owner or yourself.")
    if str(b.get("confirm", "")).lower() != email:
        raise h.ApiError(400, "Type the user's email to confirm.")
    item = h._users.get_item(Key={"email": email}).get("Item")
    if not item:
        raise h.ApiError(404, "No such user.")
    if is_admin(item) and not is_owner(u["email"]):
        raise h.ApiError(403, "Only an owner can delete an administrator.")
    n = 0
    while True:
        r = h._songs.query(KeyConditionExpression=Key("owner").eq(email), ProjectionExpression="#o, id", ExpressionAttributeNames={"#o": "owner"}, Limit=100)
        if not r["Items"]:
            break
        with h._songs.batch_writer() as bw:
            for it in r["Items"]:
                bw.delete_item(Key={"owner": it["owner"], "id": it["id"]})
                n += 1
    h._users.delete_item(Key={"email": email})
    audit(u, "user.delete", email, f"{n} songs removed")
    return 200, {"deleted": email, "songs_removed": n}


# ---------------------------------------------------------------- stats
def stats(u: dict):
    need(u)
    h = H()
    items = _all_users()
    day = _today()
    signups = {}
    for i in items:
        d = (i.get("created") or "")[:10]
        if d:
            signups[d] = signups.get(d, 0) + 1
    days = [(datetime.now(timezone.utc) - timedelta(days=k)).strftime("%Y-%m-%d") for k in range(13, -1, -1)]
    voice_days = []
    r = h._songs.query(KeyConditionExpression=Key("owner").eq("quota#tts"), ScanIndexForward=False, Limit=30)
    spend = {i["id"]: round(float(i.get("usd", 0)), 4) for i in r.get("Items", [])}
    songs_total = sum(_count_songs(i["email"]) for i in items)
    tts_objects = tts_bytes = None
    if _s3:
        try:
            tts_objects = tts_bytes = 0
            for page in _s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="tts/", PaginationConfig={"MaxItems": 20000}):
                for o in page.get("Contents", []):
                    tts_objects += 1
                    tts_bytes += o["Size"]
        except Exception as e:
            print(f"[admin] tts listing failed: {e}")
            tts_objects = tts_bytes = None
    return 200, {"users": len(items), "admins": sum(1 for i in items if is_admin(i)), "disabled": sum(1 for i in items if i.get("disabled")),
                 "songs": songs_total, "composed_today": sum(int(i["qn"]) for i in items if i.get("qday") == day),
                 "signups": [{"day": d, "n": signups.get(d, 0)} for d in days], "voice_usd": [{"day": d, "usd": spend.get(d, 0.0)} for d in days],
                 "voice_usd_today": spend.get(day, 0.0), "voice_site_cap": h.voice.SITE_DAILY_USD, "voice_user_cap": h.voice.USER_DAILY_USD,
                 "tts_files": tts_objects, "tts_mb": round(tts_bytes / 1e6, 1) if tts_bytes is not None else None,
                 "recent": _recent_audit(), "default_limit": h.DAILY_LIMIT}


# ---------------------------------------------------------------- costs
def _aws_costs() -> dict:
    ce = boto3.client("ce", region_name="us-east-1")
    now = datetime.now(timezone.utc)
    first = now.replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    end = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    by_service = ce.get_cost_and_usage(TimePeriod={"Start": prev.strftime("%Y-%m-%d"), "End": end}, Granularity="MONTHLY", Metrics=["UnblendedCost"], GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}])
    daily = ce.get_cost_and_usage(TimePeriod={"Start": (now - timedelta(days=30)).strftime("%Y-%m-%d"), "End": end}, Granularity="DAILY", Metrics=["UnblendedCost"])
    months = {}
    for r in by_service["ResultsByTime"]:
        m = r["TimePeriod"]["Start"][:7]
        rows = [{"service": g["Keys"][0], "usd": round(float(g["Metrics"]["UnblendedCost"]["Amount"]), 4), "ours": g["Keys"][0] in OURS} for g in r["Groups"]]
        rows = [x for x in rows if x["usd"] >= 0.005]
        rows.sort(key=lambda x: -x["usd"])
        months[m] = {"total": round(sum(x["usd"] for x in rows), 2), "ours": round(sum(x["usd"] for x in rows if x["ours"]), 2), "services": rows[:15]}
    cur = now.strftime("%Y-%m")
    days_in = calendar.monthrange(now.year, now.month)[1]
    mtd = months.get(cur, {}).get("total", 0.0)
    return {"months": months, "current": cur, "projected": round(mtd / max(1, now.day) * days_in, 2),
            "daily": [{"day": r["TimePeriod"]["Start"], "usd": round(float(r["Total"]["UnblendedCost"]["Amount"]), 2)} for r in daily["ResultsByTime"]],
            "note": "Whole AWS account, not only mhRaaga. AWS posts costs several hours late. 'ours' marks the services this project uses."}


def _openrouter() -> dict:
    h = H()
    req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + h.secret("openrouter_key")})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.load(r).get("data", {})
    pick = {k: d.get(k) for k in ("label", "usage", "usage_daily", "usage_weekly", "usage_monthly", "limit", "limit_remaining", "is_free_tier") if k in d}
    return pick


def costs(u: dict, refresh: bool = False):
    need(u)
    h = H()
    it = h._songs.get_item(Key={"owner": "admin#cache", "id": "costs"}).get("Item")
    if it and not refresh and time.time() - float(it.get("at", 0)) < CACHE_SECONDS:
        return 200, {**json.loads(it["data"]), "cached": True, "age_s": int(time.time() - float(it["at"]))}
    if it and refresh and time.time() - float(it.get("at", 0)) < 300:
        raise h.ApiError(429, "Costs were refreshed a moment ago. Each refresh is a paid AWS query, so please wait five minutes.")
    out, errors = {}, {}
    for name, fn in (("aws", _aws_costs), ("openrouter", _openrouter)):
        try:
            out[name] = fn()
        except Exception as e:
            print(f"[admin] {name} cost failed: {type(e).__name__}: {e}")
            errors[name] = f"{type(e).__name__}: {str(e)[:160]}"
    r = h._songs.query(KeyConditionExpression=Key("owner").eq("quota#tts"), ScanIndexForward=False, Limit=40)
    spend = {i["id"]: round(float(i.get("usd", 0)), 4) for i in r.get("Items", [])}
    month = _today()[:7]
    out["voice"] = {"today": spend.get(_today(), 0.0), "month": round(sum(v for k, v in spend.items() if k.startswith(month)), 4), "days": [{"day": k, "usd": v} for k, v in sorted(spend.items())][-30:]}
    out["errors"] = errors
    if out.get("aws") or out.get("openrouter"):
        h._songs.put_item(Item={"owner": "admin#cache", "id": "costs", "at": Decimal(str(time.time())), "data": json.dumps(out, default=_f)})
    return 200, {**out, "cached": False, "age_s": 0}


# ---------------------------------------------------------------- router
def route(method: str, path: str, event: dict, user_from, body_of, query: dict):
    """path is the part after /admin. Returns (status, body)."""
    h = H()
    u = user_from(event)
    parts = [p for p in path.strip("/").split("/") if p]
    if parts == ["users"] and method == "GET":
        return users_list(u)
    if parts == ["users"] and method == "POST":
        return users_create(u, body_of(event))
    if len(parts) == 2 and parts[0] == "users" and method == "PATCH":
        return users_update(u, parts[1], body_of(event))
    if len(parts) == 3 and parts[0] == "users" and parts[2] == "delete" and method == "POST":
        return users_delete(u, parts[1], body_of(event))
    if parts == ["schema"] and method == "GET":
        return schema_get(u)
    if parts == ["schema"] and method == "PUT":
        return schema_put(u, body_of(event))
    if parts == ["stats"] and method == "GET":
        return stats(u)
    if parts == ["costs"] and method == "GET":
        return costs(u, query.get("refresh") == "1")
    raise h.ApiError(404, "Not found.")
