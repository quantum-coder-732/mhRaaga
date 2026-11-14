"""Shared studio: many artists work in one project (film or song) at once.

Model (all in the songs table):
  owner=team#<pid>   id=0meta        project: title, kind (film|song), members {email: role}, rev
  owner=team#<pid>   id=L#<lid>      one layer per contribution (a film shot, or a song section). Owned by one artist.
  owner=team#<pid>   id=C#<ts>-<r>   comment
  owner=member#<email> id=<pid>      index so a member can list their projects

Roles: director (everything), artist (creates and edits only their own layers), viewer (read and comment).
Up to 150 members and 300 layers per project. Edits use optimistic locking: a layer save must carry the rev it was
based on, and loses with 409 if someone changed it first, so two people never silently overwrite each other.
Clients poll GET /teams/{pid}?since=<updated>; only layers changed since then come back."""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone

import studio

MAX_MEMBERS, MAX_LAYERS, MAX_PER_ARTIST, MAX_COMMENTS = 150, 300, 8, 200
ROLES = ("director", "artist", "viewer")
STATUSES = ("wip", "review", "approved")
KINDS = ("film", "song")
SECTIONS = ("mukhda", "antara", "sanchari", "bridge", "alap note", "outro")
PID = re.compile(r"t-[0-9a-f]{10}")
LID = re.compile(r"[0-9a-f]{10}")
LAYER_BYTES = 330_000


def H():
    return studio.H()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pk(pid: str) -> str:
    return f"team#{pid}"


def _email(v) -> str:
    v = (v or "").strip().lower() if isinstance(v, str) else ""
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,120}\.[^@\s]{2,}", v):
        raise H().ApiError(400, "Enter a valid email.")
    return v


def _query_all(pk: str, **kw) -> list[dict]:
    from boto3.dynamodb.conditions import Key
    h, out, start = H(), [], None
    while True:
        r = h._songs.query(KeyConditionExpression=Key("owner").eq(pk), **({"ExclusiveStartKey": start} if start else {}), **kw)
        out += r["Items"]
        start = r.get("LastEvaluatedKey")
        if not start or len(out) > 700:
            return out


def _meta(pid: str) -> dict:
    h = H()
    if not PID.fullmatch(pid or ""):
        raise h.ApiError(400, "Bad project id.")
    it = h._songs.get_item(Key={"owner": _pk(pid), "id": "0meta"}).get("Item")
    if not it:
        raise h.ApiError(404, "Project not found.")
    it["members"] = json.loads(it["members"])
    return it


def _role(m: dict, u: dict) -> str:
    r = m["members"].get(u["email"].lower())
    if not r:
        raise H().ApiError(403, "You are not in this project.")
    return r


def _save_meta(m: dict) -> None:
    H()._songs.put_item(Item={**m, "members": json.dumps(m["members"]), "updated": _now()})


def _index(email: str, m: dict, role: str | None) -> None:
    h = H()
    if role is None:
        h._songs.delete_item(Key={"owner": f"member#{email}", "id": m["pid"]})
    else:
        h._songs.put_item(Item={"owner": f"member#{email}", "id": m["pid"], "title": m["title"], "kind": m["kind"], "role": role, "director": m["director"]})


# ---------------------------------------------------------------- projects
def create(u: dict, b: dict):
    h = H()
    kind = b.get("kind") if b.get("kind") in KINDS else "film"
    title = h.text(b.get("title"), 80) or ("Untitled film" if kind == "film" else "Untitled song")
    studio.check(title)
    from boto3.dynamodb.conditions import Key
    directing = [i for i in h._songs.query(KeyConditionExpression=Key("owner").eq(f"member#{u['email']}"))["Items"] if i.get("director") == u["email"]]
    if len(directing) >= 20:
        raise h.ApiError(400, "You can direct up to 20 shared projects.")
    pid = "t-" + uuid.uuid4().hex[:10]
    m = {"owner": _pk(pid), "id": "0meta", "pid": pid, "title": title, "kind": kind, "director": u["email"], "members": {u["email"]: "director"},
         "created": _now(), "rev": 1, "raga": h.text(b.get("raga"), 40), "language": h.text(b.get("language"), 12)}
    _save_meta(m)
    _index(u["email"], m, "director")
    return 200, {"id": pid}


def mine(u: dict):
    from boto3.dynamodb.conditions import Key
    r = H()._songs.query(KeyConditionExpression=Key("owner").eq(f"member#{u['email']}"), Limit=100)
    return 200, {"projects": [{"id": i["id"], "title": i["title"], "kind": i["kind"], "role": i["role"], "director": i.get("director", "")} for i in r["Items"]]}


def get(u: dict, pid: str, since: str = ""):
    m = _meta(pid)
    role = _role(m, u)
    items = _query_all(_pk(pid), ProjectionExpression="id,#n,#b,slot,rev,updated,#s,title,nbytes,comment_at,#t,#x",
                       ExpressionAttributeNames={"#n": "name", "#b": "by", "#s": "status", "#t": "text", "#x": "layer"})
    layers = [i for i in items if i["id"].startswith("L#")]
    comments = [i for i in items if i["id"].startswith("C#")][-60:]
    changed = [l for l in layers if not since or l.get("updated", "") > since]
    return 200, {"id": pid, "title": m["title"], "kind": m["kind"], "director": m["director"], "role": role, "rev": int(m.get("rev", 1)),
                 "raga": m.get("raga", ""), "language": m.get("language", ""), "members": m["members"], "now": _now(),
                 "layers": sorted([{"id": l["id"][2:], "name": l.get("name", ""), "by": l.get("by", ""), "slot": int(l.get("slot", 0)), "rev": int(l.get("rev", 1)),
                                    "status": l.get("status", "wip"), "title": l.get("title", ""), "updated": l.get("updated", "")} for l in changed], key=lambda x: (x["slot"], x["id"])),
                 "layer_ids": [l["id"][2:] for l in layers],   # lets a client drop layers deleted since its last poll
                 "comments": [{"id": c["id"], "by": c.get("by", ""), "text": c.get("text", ""), "layer": c.get("layer", ""), "at": c["id"][2:15]} for c in comments]}


def delete(u: dict, pid: str):
    m = _meta(pid)
    if m["director"] != u["email"]:
        raise H().ApiError(403, "Only the director can delete the project.")
    h = H()
    for i in _query_all(_pk(pid), ProjectionExpression="id"):
        h._songs.delete_item(Key={"owner": _pk(pid), "id": i["id"]})
    for e in m["members"]:
        _index(e, m, None)
    return 200, {"deleted": pid}


# ---------------------------------------------------------------- members
def invite(u: dict, pid: str, b: dict):
    h = H()
    m = _meta(pid)
    if _role(m, u) != "director":
        raise h.ApiError(403, "Only the director can add people.")
    emails = b.get("emails") if isinstance(b.get("emails"), list) else [b.get("email")]
    role = b.get("role") if b.get("role") in ROLES else "artist"
    added = []
    for raw in emails[:150]:
        e = _email(raw)
        if e not in m["members"] and len(m["members"]) >= MAX_MEMBERS:
            raise h.ApiError(400, f"A project holds up to {MAX_MEMBERS} people.")
        if e == m["director"]:
            continue
        m["members"][e] = role
        added.append(e)
    m["rev"] = int(m.get("rev", 1)) + 1
    _save_meta(m)
    for e in added:
        _index(e, m, m["members"][e])
    return 200, {"added": added, "members": m["members"]}


def remove_member(u: dict, pid: str, email: str):
    h = H()
    m = _meta(pid)
    email = email.lower()
    if _role(m, u) != "director" and email != u["email"]:
        raise h.ApiError(403, "Only the director can remove people.")
    if email == m["director"]:
        raise h.ApiError(400, "The director cannot leave. Delete the project instead.")
    m["members"].pop(email, None)
    m["rev"] = int(m.get("rev", 1)) + 1
    _save_meta(m)
    _index(email, m, None)
    return 200, {"members": m["members"]}


# ---------------------------------------------------------------- layers
def _clean_layer(kind: str, b: dict) -> dict:
    h = H()
    d = b.get("data") if isinstance(b.get("data"), dict) else {}
    if kind == "film":
        data = studio._clean_scene(d)
        studio.check(data["title"], data["text"], data["narration"])
    else:
        sec = h.text(d.get("section"), 20).lower()
        data = {"section": sec if sec in SECTIONS else "mukhda", "lyrics": h.text(d.get("lyrics"), 1500), "note": h.text(d.get("note"), 300)}
        studio.check(data["lyrics"], data["note"])
    return data


def layer_get(u: dict, pid: str, lid: str):
    h = H()
    m = _meta(pid)
    _role(m, u)
    if not LID.fullmatch(lid or ""):
        raise h.ApiError(400, "Bad layer id.")
    it = h._songs.get_item(Key={"owner": _pk(pid), "id": "L#" + lid}).get("Item")
    if not it:
        raise h.ApiError(404, "Layer not found.")
    return 200, {"id": lid, "name": it.get("name", ""), "by": it.get("by", ""), "slot": int(it.get("slot", 0)), "rev": int(it.get("rev", 1)),
                 "status": it.get("status", "wip"), "data": json.loads(it["data"]), "updated": it.get("updated", "")}


def layer_save(u: dict, pid: str, lid: str | None, b: dict):
    h = H()
    m = _meta(pid)
    role = _role(m, u)
    if role == "viewer":
        raise h.ApiError(403, "Viewers can comment but not edit.")
    existing = None
    if lid is None:
        layers = [i for i in _query_all(_pk(pid), ProjectionExpression="id,#b", ExpressionAttributeNames={"#b": "by"}) if i["id"].startswith("L#")]
        if len(layers) >= MAX_LAYERS:
            raise h.ApiError(400, f"A project holds up to {MAX_LAYERS} layers.")
        if role != "director" and sum(1 for l in layers if l.get("by") == u["email"]) >= MAX_PER_ARTIST:
            raise h.ApiError(400, f"Each artist can hold up to {MAX_PER_ARTIST} layers.")
        lid = uuid.uuid4().hex[:10]
        rev, slot, status, by = 1, int(b.get("slot", len(layers) + 1)) if role == "director" else len(layers) + 1, "wip", u["email"]
    else:
        if not LID.fullmatch(lid):
            raise h.ApiError(400, "Bad layer id.")
        existing = h._songs.get_item(Key={"owner": _pk(pid), "id": "L#" + lid}).get("Item")
        if not existing:
            raise h.ApiError(404, "Layer not found.")
        if role != "director" and existing.get("by") != u["email"]:
            raise h.ApiError(403, "That layer belongs to another artist. Ask the director, or comment on it.")
        if int(b.get("base_rev", 0)) != int(existing.get("rev", 1)):
            raise h.ApiError(409, "Someone changed this layer after you opened it. Reload it to see their version.")
        rev, slot, status, by = int(existing["rev"]) + 1, int(existing.get("slot", 0)), existing.get("status", "wip"), existing["by"]
        if role == "director" and isinstance(b.get("slot"), int):
            slot = max(0, min(999, b["slot"]))
    if b.get("status") in STATUSES and (role == "director" or b["status"] != "approved"):
        status = b["status"]
    data = _clean_layer(m["kind"], b) if "data" in b or existing is None else json.loads(existing["data"])
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(raw) > LAYER_BYTES:
        raise h.ApiError(413, "This layer is too big. Use a smaller image.")
    name = h.text(b.get("name"), 60) or (existing or {}).get("name") or ("Shot" if m["kind"] == "film" else "Section")
    studio.check(name)
    title = data.get("title") or data.get("section") or ""
    h._songs.put_item(Item={"owner": _pk(pid), "id": "L#" + lid, "name": name, "by": by, "slot": slot, "rev": rev, "status": status, "title": title,
                            "nbytes": len(raw), "data": raw, "updated": _now()})
    return 200, {"id": lid, "rev": rev, "slot": slot, "status": status}


def layer_delete(u: dict, pid: str, lid: str):
    h = H()
    m = _meta(pid)
    role = _role(m, u)
    if not LID.fullmatch(lid or ""):
        raise h.ApiError(400, "Bad layer id.")
    it = h._songs.get_item(Key={"owner": _pk(pid), "id": "L#" + lid}).get("Item")
    if not it:
        raise h.ApiError(404, "Layer not found.")
    if role != "director" and it.get("by") != u["email"]:
        raise h.ApiError(403, "That layer belongs to another artist.")
    h._songs.delete_item(Key={"owner": _pk(pid), "id": "L#" + lid})
    return 200, {"deleted": lid}


# ---------------------------------------------------------------- comments
def comment(u: dict, pid: str, b: dict):
    h = H()
    m = _meta(pid)
    _role(m, u)
    t = h.text(b.get("text"), 500)
    if not t:
        raise h.ApiError(400, "Write a comment first.")
    studio.check(t)
    cid = f"C#{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:4]}"
    h._songs.put_item(Item={"owner": _pk(pid), "id": cid, "by": u["email"], "text": t, "layer": h.text(b.get("layer"), 10)})
    return 200, {"id": cid}


# ---------------------------------------------------------------- assemble
def assemble(u: dict, pid: str):
    """Film: ordered scenes from every layer (approved first if any are approved only when asked). Song: merged lyrics."""
    m = _meta(pid)
    _role(m, u)
    layers = sorted([i for i in _query_all(_pk(pid)) if i["id"].startswith("L#")], key=lambda i: (int(i.get("slot", 0)), i["id"]))
    only = [l for l in layers if l.get("status") == "approved"]
    use = only or layers
    datas = [(l, json.loads(l["data"])) for l in use]
    if m["kind"] == "film":
        budget, scenes = 4_200_000, []
        for l, d in datas:
            if len(d["bg"].get("image", "")) > budget:
                d["bg"]["image"] = ""
            budget -= len(d["bg"].get("image", ""))
            d["credit"] = l.get("by", "")
            scenes.append(d)
        return 200, {"title": m["title"], "language": m.get("language") or "english", "scenes": scenes, "used": "approved layers" if only else "all layers"}
    lyr = "\n".join(f"[{d['section'].title()}]\n{d['lyrics']}" for _, d in datas if d.get("lyrics"))
    return 200, {"title": m["title"], "lyrics": lyr, "raga": m.get("raga", ""), "language": m.get("language", ""), "used": "approved layers" if only else "all layers"}


def render_song(u: dict, pid: str, event: dict, make_song):
    """Director turns the merged lyrics into a song in their own library, using the normal compose pipeline."""
    m = _meta(pid)
    if _role(m, u) != "director":
        raise H().ApiError(403, "Only the director can render the song.")
    if m["kind"] != "song":
        raise H().ApiError(400, "This is a film project.")
    out = assemble(u, pid)[1]
    if len(out["lyrics"]) < 10:
        raise H().ApiError(400, "Add some lyrics to the layers first.")
    prompt = f"{m['title']}. A song written together by {len(m['members'])} people."
    ev = {**event, "isBase64Encoded": False, "body": json.dumps({"prompt": prompt, "raga": out["raga"], "language": out["language"], "lyrics": out["lyrics"], "title": m["title"]})}
    return make_song(ev)
