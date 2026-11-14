"""Run mhRaaga locally with the exact Lambda handler: static site + /api, DynamoDB replaced by a JSON file.
    python3 api/local_server.py            -> http://localhost:8787
Reads OPENROUTER_API_KEY from ../../../.env if present; without it the keyword fallback plans the song."""
from __future__ import annotations

import json
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "music_engine_framework_layer"))
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
import handler as h  # noqa: E402

DB = HERE.parent / "build" / "local-db.json"
for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


class FileTable:
    def __init__(self, name: str, keys: tuple[str, ...]):
        self.name, self.keys = name, keys

    def _all(self) -> dict:
        return json.loads(DB.read_text()) if DB.exists() else {}

    def _tbl(self, d: dict) -> dict:
        return d.setdefault(self.name, {})

    def _k(self, item: dict) -> str:
        return "|".join(str(item.get(k, "")) for k in self.keys)

    def put_item(self, Item, ConditionExpression=None):
        d = self._all(); t = self._tbl(d)
        if ConditionExpression and self._k(Item) in t:
            raise h._db.meta.client.exceptions.ConditionalCheckFailedException({"Error": {}}, "put")
        t[self._k(Item)] = Item; DB.parent.mkdir(exist_ok=True); DB.write_text(json.dumps(d, default=float))

    def get_item(self, Key):
        it = self._tbl(self._all()).get(self._k(Key)); return {"Item": dict(it)} if it else {}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, **_):
        d = self._all(); it = self._tbl(d)[self._k(Key)]
        for part in UpdateExpression[4:].split(","):
            f, v = [x.strip() for x in part.split("=")]; it[f] = ExpressionAttributeValues[v]
        DB.write_text(json.dumps(d, default=float))

    def delete_item(self, Key):
        d = self._all(); self._tbl(d).pop(self._k(Key), None); DB.write_text(json.dumps(d, default=float))

    def query(self, KeyConditionExpression=None, **kw):
        owner = KeyConditionExpression._values[1]
        rows = [v for v in self._tbl(self._all()).values() if v.get("owner") == owner]
        rows.sort(key=lambda r: r["id"], reverse=True)
        return {"Items": [{k: v for k, v in r.items() if k not in ("score", "brief", "owner")} for r in rows]}


h._users, h._songs = FileTable("users", ("email",)), FileTable("songs", ("owner", "id"))
sk = DB.parent / "local-jwt.key"; sk.parent.mkdir(exist_ok=True)
if not sk.exists(): sk.write_text(secrets.token_hex(32))
h._cache.update({"jwt_secret": sk.read_text(), "openrouter_key": os.environ.get("OPENROUTER_API_KEY", "")})
WEB = HERE.parent / "web"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}


class H(BaseHTTPRequestHandler):
    def _api(self):
        n = int(self.headers.get("content-length") or 0)
        ev = {"requestContext": {"http": {"method": self.command}}, "rawPath": self.path.split("?")[0],
              "headers": {k.lower(): v for k, v in self.headers.items()}, "body": self.rfile.read(n).decode() if n else None}
        r = h.handler(ev); b = r["body"].encode()
        self.send_response(r["statusCode"]); [self.send_header(k, v) for k, v in r["headers"].items()]
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/"): return self._api()
        p = WEB / (self.path.split("?")[0].lstrip("/") or "index.html")
        if not p.is_file() or WEB not in p.resolve().parents: p = WEB / "index.html"
        b = p.read_bytes(); self.send_response(200); self.send_header("Content-Type", TYPES.get(p.suffix, "application/octet-stream"))
        self.send_header("Permissions-Policy", "microphone=(self)"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    do_POST = do_PUT = do_DELETE = do_OPTIONS = _api
    def log_message(self, *a): pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    print(f"mhRaaga local: http://localhost:{port}  (LLM: {'OpenRouter' if h._cache['openrouter_key'] else 'keyword fallback'})")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
