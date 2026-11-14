"""Persistence for tracks and generation jobs.

DynamoDB when DYNAMO_ENDPOINT is set and reachable, otherwise a JSON file, so
the app runs with zero infrastructure. Each item is {id, created_at, doc} where
doc is the record as JSON: DynamoDB rejects floats, and discovery here is a
small scan-and-filter, which is fine at local scale (swap in GSIs later).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config


class Store:
    def __init__(self):
        self._lock = threading.RLock()
        self._tables = None
        self.backend = "file"
        self._file = config.DATA_DIR / "store.json"
        self._mem: dict[str, dict[str, dict]] = {"tracks": {}, "jobs": {}, "users": {}, "usage": {}}
        if config.DYNAMO_ENDPOINT and self._connect():
            self.backend = "dynamodb"
        else:
            self._load()

    def _connect(self) -> bool:
        try:
            import boto3
            ddb = boto3.resource("dynamodb", endpoint_url=config.DYNAMO_ENDPOINT, region_name=config.DYNAMO_REGION,
                                 aws_access_key_id="local", aws_secret_access_key="local")
            self._tables = {}
            for name in ("tracks", "jobs", "users", "usage"):
                full = config.TABLE_PREFIX + name
                try:
                    t = ddb.Table(full)
                    t.load()
                except Exception:
                    t = ddb.create_table(TableName=full, BillingMode="PAY_PER_REQUEST",
                                         KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                                         AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}])
                    t.wait_until_exists()
                self._tables[name] = t
            return True
        except Exception as e:  # unreachable endpoint, bad creds, ...
            print(f"[store] DynamoDB unavailable ({e}); using JSON file store")
            self._tables = None
            return False

    def _load(self):
        if self._file.exists():
            self._mem = json.loads(self._file.read_text())
        self._mem.setdefault("users", {})
        self._mem.setdefault("usage", {})

    def _flush(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self._file) + ".tmp")
        tmp.write_text(json.dumps(self._mem))
        tmp.replace(self._file)

    def put(self, kind: str, doc: dict) -> None:
        with self._lock:
            if self._tables:
                self._tables[kind].put_item(Item={"id": doc["id"], "created_at": doc.get("created_at", ""),
                                                   "doc": json.dumps(doc)})
            else:
                self._mem[kind][doc["id"]] = doc
                self._flush()

    def get(self, kind: str, id_: str) -> dict | None:
        with self._lock:
            if self._tables:
                item = self._tables[kind].get_item(Key={"id": id_}).get("Item")
                return json.loads(item["doc"]) if item else None
            return self._mem[kind].get(id_)

    def delete(self, kind: str, id_: str) -> None:
        with self._lock:
            if self._tables:
                self._tables[kind].delete_item(Key={"id": id_})
            else:
                self._mem[kind].pop(id_, None)
                self._flush()

    def update(self, kind: str, id_: str, **fields) -> dict | None:
        with self._lock:
            doc = self.get(kind, id_)
            if doc is None:
                return None
            doc.update(fields)
            self.put(kind, doc)
            return doc

    def all(self, kind: str) -> list[dict]:
        with self._lock:
            if self._tables:
                items, kw = [], {}
                while True:
                    page = self._tables[kind].scan(**kw)
                    items += [json.loads(i["doc"]) for i in page["Items"]]
                    if "LastEvaluatedKey" not in page:
                        return items
                    kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]
            return list(self._mem[kind].values())
