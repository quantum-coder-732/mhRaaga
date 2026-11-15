"""Admin dashboard logic against an in-memory DynamoDB stand-in (no AWS needed)."""
import json, os, sys, unittest
from decimal import Decimal
ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, "..", "..", "..", "music_engine_framework_layer")); sys.path.insert(0, os.path.join(ROOT, "..", "api"))
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1"); os.environ["ADMIN_EMAILS"] = "boss@example.com"
import handler as h, admin, studio  # noqa: E402
h._cache["jwt_secret"] = "test-signing-key"


class Fake:
    def __init__(self, keys): self.keys, self.rows = keys, {}
    def _k(self, i): return tuple(i.get(k) for k in self.keys)
    def put_item(self, Item, ConditionExpression=None):
        if ConditionExpression and self._k(Item) in self.rows: raise h._db.meta.client.exceptions.ConditionalCheckFailedException({"Error": {}}, "put")
        self.rows[self._k(Item)] = json.loads(json.dumps(Item, default=lambda o: float(o) if isinstance(o, Decimal) else str(o)), parse_float=Decimal)
    def get_item(self, Key):
        r = self.rows.get(self._k(Key)); return {"Item": dict(r)} if r else {}
    def delete_item(self, Key): self.rows.pop(self._k(Key), None)
    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues=None, ExpressionAttributeNames=None, **_):
        it = self.rows.setdefault(self._k(Key), dict(Key)); names, vals = ExpressionAttributeNames or {}, ExpressionAttributeValues or {}
        ue = (" " + UpdateExpression) if UpdateExpression.startswith("REMOVE") else UpdateExpression
        sets, _, rem = ue.partition(" REMOVE ")
        if sets.startswith("SET "):
            for part in sets[4:].split(", "):
                a, v = [x.strip() for x in part.split("=")]; it[names.get(a, a)] = vals[v]
        elif sets.startswith("ADD "):
            a, v = sets[4:].split(" "); it[a] = it.get(a, 0) + vals[v]
        for a in [x.strip() for x in rem.split(",") if x.strip()]: it.pop(names.get(a, a), None)
    def query(self, KeyConditionExpression=None, Select=None, ScanIndexForward=True, Limit=None, **_):
        owner = KeyConditionExpression._values[1]; rows = sorted((v for k, v in self.rows.items() if k[0] == owner), key=lambda r: r["id"], reverse=not ScanIndexForward)
        rows = rows[:Limit] if Limit else rows
        return {"Count": len(rows)} if Select == "COUNT" else {"Items": [dict(r) for r in rows]}
    def scan(self, **_): return {"Items": [dict(r) for r in self.rows.values()]}
    def batch_writer(self):
        t = self
        class B:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def delete_item(s, Key): t.delete_item(Key)
        return B()


def mk(email, name="N", role=None, **kw):
    it = {"email": email, "name": name, "pw": h.hash_pw("password-1"), "created": "2026-11-01T00:00:00+00:00", "qday": h.today(), "qn": 0, **kw}
    if role: it["role"] = role
    h._users.put_item(Item=it); return h._users.get_item(Key={"email": email})["Item"]


class Admin(unittest.TestCase):
    def setUp(self):
        h._users, h._songs = Fake(("email",)), Fake(("owner", "id"))
        self.boss, self.adm, self.bob = mk("boss@example.com", "Boss"), mk("adm@example.com", "Adm", "admin"), mk("bob@example.com", "Bob")
        h._songs.put_item(Item={"owner": "bob@example.com", "id": "1", "title": "x"})

    def test_only_admins_get_in(self):
        for fn in (lambda: admin.users_list(self.bob), lambda: admin.stats(self.bob), lambda: admin.schema_get(self.bob)):
            with self.assertRaises(h.ApiError) as c: fn()
            self.assertEqual(c.exception.status, 403)
        self.assertEqual(admin.users_list(self.adm)[0], 200)

    def test_list_shows_roles_and_songs(self):
        users = {u["email"]: u for u in admin.users_list(self.boss)[1]["users"]}
        self.assertEqual((users["boss@example.com"]["role"], users["boss@example.com"]["owner"]), ("admin", True))
        self.assertEqual((users["adm@example.com"]["role"], users["bob@example.com"]["role"], users["bob@example.com"]["songs"]), ("admin", "user", 1))

    def test_change_name_and_role(self):
        _, r = admin.users_update(self.boss, "bob@example.com", {"name": "Robert", "role": "admin"})
        self.assertEqual((r["user"]["name"], r["user"]["role"]), ("Robert", "admin")); self.assertTrue(admin.is_admin(h._users.get_item(Key={"email": "bob@example.com"})["Item"]))
        with self.assertRaises(h.ApiError): admin.users_update(self.adm, "bob@example.com", {"role": "user"})       # only an owner changes roles
        with self.assertRaises(h.ApiError): admin.users_update(self.boss, "boss@example.com", {"role": "user"})    # an owner stays admin
        with self.assertRaises(h.ApiError): admin.users_update(self.boss, "bob@example.com", {"role": "superuser"})
        with self.assertRaises(h.ApiError): admin.users_update(self.boss, "bob@example.com", {"name": "  "})

    def test_disable_blocks_everything_and_owner_is_protected(self):
        admin.users_update(self.boss, "bob@example.com", {"disabled": True})
        ev = {"headers": {"authorization": "Bearer " + h.make_token("bob@example.com")}}
        with self.assertRaises(h.ApiError) as c: h.user_from(ev)
        self.assertEqual(c.exception.status, 403)
        with self.assertRaises(h.ApiError) as c: h.login({"body": json.dumps({"email": "bob@example.com", "password": "password-1"})})
        self.assertEqual(c.exception.status, 403)
        for who in ("boss@example.com",):
            with self.assertRaises(h.ApiError): admin.users_update(self.adm, who, {"disabled": True})
        with self.assertRaises(h.ApiError): admin.users_update(self.boss, "boss@example.com", {"disabled": True})
        admin.users_update(self.boss, "bob@example.com", {"disabled": False}); self.assertFalse(h._users.get_item(Key={"email": "bob@example.com"})["Item"]["disabled"])

    def test_limit_quota_and_reset(self):
        admin.users_update(self.boss, "bob@example.com", {"daily_limit": 2}); bob = h._users.get_item(Key={"email": "bob@example.com"})["Item"]
        h.take_quota(bob); bob = h._users.get_item(Key={"email": "bob@example.com"})["Item"]; h.take_quota(bob); bob = h._users.get_item(Key={"email": "bob@example.com"})["Item"]
        with self.assertRaises(h.ApiError) as c: h.take_quota(bob)
        self.assertEqual(c.exception.status, 429)
        admin.users_update(self.boss, "bob@example.com", {"reset_quota": True}); h.take_quota(h._users.get_item(Key={"email": "bob@example.com"})["Item"])
        with self.assertRaises(h.ApiError): admin.users_update(self.boss, "bob@example.com", {"daily_limit": 5000})
        admin.users_update(self.boss, "bob@example.com", {"daily_limit": None}); self.assertNotIn("limit", h._users.get_item(Key={"email": "bob@example.com"})["Item"])

    def test_set_password(self):
        admin.users_update(self.boss, "bob@example.com", {"password": "brand-new-pass"}); it = h._users.get_item(Key={"email": "bob@example.com"})["Item"]
        self.assertTrue(h.check_pw("brand-new-pass", it["pw"])); self.assertFalse(h.check_pw("password-1", it["pw"]))
        with self.assertRaises(h.ApiError): admin.users_update(self.boss, "bob@example.com", {"password": "short"})
        with self.assertRaises(h.ApiError): admin.users_update(self.adm, "boss@example.com", {"password": "another-password"})  # not someone else's owner account

    def test_custom_columns_and_values(self):
        admin.schema_put(self.boss, {"columns": [{"key": "plan", "label": "Plan", "type": "select", "options": ["free", "pro"]}, {"key": "city", "label": "City", "type": "text"}, {"key": "seats", "label": "Seats", "type": "number"}, {"key": "paid", "label": "Paid", "type": "yesno"}, {"key": "until", "label": "Until", "type": "date"}]})
        _, r = admin.users_update(self.boss, "bob@example.com", {"extra": {"plan": "pro", "city": "Pune", "seats": "3", "paid": "yes", "until": "2026-12-31"}})
        self.assertEqual(r["user"]["extra"], {"plan": "pro", "city": "Pune", "seats": 3, "paid": True, "until": "2026-12-31"})
        for bad in ({"plan": "gold"}, {"seats": "many"}, {"paid": "maybe"}, {"until": "tomorrow"}, {"nothere": "x"}):
            with self.assertRaises(h.ApiError): admin.users_update(self.boss, "bob@example.com", {"extra": bad})
        _, r = admin.users_update(self.boss, "bob@example.com", {"extra": {"city": ""}}); self.assertIsNone(r["user"]["extra"]["city"])
        for bad in ([{"key": "Bad Key", "label": "x", "type": "text"}], [{"key": "a", "label": "x", "type": "select", "options": ["one"]}], [{"key": "a", "type": "text"}, {"key": "a", "type": "text"}]):
            with self.assertRaises(h.ApiError): admin.schema_put(self.boss, {"columns": bad})
        with self.assertRaises(h.ApiError): admin.schema_put(self.bob, {"columns": []})

    def test_add_and_delete_user(self):
        self.assertEqual(admin.users_create(self.boss, {"name": "Cy", "email": "cy@example.com", "password": "long-enough-1", "role": "admin"})[0], 201)
        with self.assertRaises(h.ApiError) as c: admin.users_create(self.boss, {"name": "Cy", "email": "cy@example.com", "password": "long-enough-1"})
        self.assertEqual(c.exception.status, 409)
        with self.assertRaises(h.ApiError): admin.users_create(self.adm, {"name": "Z", "email": "z@example.com", "password": "long-enough-1", "role": "admin"})   # only an owner adds admins
        with self.assertRaises(h.ApiError): admin.users_create(self.boss, {"name": "Z", "email": "nope", "password": "long-enough-1"})
        with self.assertRaises(h.ApiError): admin.users_delete(self.boss, "bob@example.com", {"confirm": "wrong"})
        _, r = admin.users_delete(self.boss, "bob@example.com", {"confirm": "BOB@example.com"}); self.assertEqual(r["songs_removed"], 1)
        self.assertNotIn(("bob@example.com",), h._users.rows)
        with self.assertRaises(h.ApiError): admin.users_delete(self.boss, "boss@example.com", {"confirm": "boss@example.com"})

    def test_audit_and_stats(self):
        admin.users_update(self.boss, "bob@example.com", {"name": "Bobby"}); st = admin.stats(self.boss)[1]
        self.assertEqual(st["users"], 3); self.assertEqual(st["admins"], 2); self.assertEqual(st["recent"][0]["what"], "user.update"); self.assertEqual(len(st["signups"]), 14)
        self.assertNotIn("password", json.dumps(st["recent"]))

    def test_me_reports_role(self):
        for u, want in ((self.boss, "admin"), (self.adm, "admin"), (self.bob, "user")):
            self.assertEqual(admin.is_admin(u), want == "admin")
        self.assertEqual(studio.need_admin(self.adm), None)
        with self.assertRaises(h.ApiError): studio.need_admin(self.bob)


class SignupRequests(unittest.TestCase):
    """Sign-up is a request; an administrator approves it and passes on a temporary password; the user then picks their own."""
    def setUp(self):
        h._users, h._songs = Fake(("email",)), Fake(("owner", "id"))
        self.boss, self.bob = mk("boss@example.com", "Boss"), mk("bob@example.com", "Bob")

    def ev(self, body, token=None):
        return {"headers": {"authorization": "Bearer " + token} if token else {}, "body": json.dumps(body)}

    def test_whole_flow(self):
        with self.assertRaises(h.ApiError) as c: h.signup(self.ev({"name": "A", "email": "nope"}))
        self.assertEqual(c.exception.status, 400)
        st, r = h.signup(self.ev({"name": "Neha", "email": "Neha@Y.in", "note": "bhajans"})); self.assertEqual((st, r["status"]), (202, "pending")); self.assertNotIn("token", r)
        self.assertEqual(h.signup(self.ev({"name": "Neha", "email": "neha@y.in"}))[0], 202)                      # twice is harmless
        with self.assertRaises(h.ApiError) as c: h.login(self.ev({"email": "neha@y.in", "password": "anything1"}))   # no account before approval
        self.assertEqual(c.exception.status, 401)
        self.assertEqual(h.request_status(self.ev({"email": "neha@y.in"}))[1]["status"], "pending")
        with self.assertRaises(h.ApiError): admin.requests_list(self.bob)                                          # plain users cannot see requests
        _, lst = admin.requests_list(self.boss); self.assertEqual((lst["pending"], lst["requests"][0]["email"]), (1, "neha@y.in"))
        _, ap = admin.request_approve(self.boss, "neha@y.in"); temp = ap["temp_password"]; self.assertGreaterEqual(len(temp), 8)
        self.assertEqual(h.request_status(self.ev({"email": "neha@y.in"}))[1]["status"], "account")
        _, lg = h.login(self.ev({"email": "neha@y.in", "password": temp})); self.assertTrue(lg["must_change"])
        user = h._users.get_item(Key={"email": "neha@y.in"})["Item"]; self.assertEqual(user["name"], "Neha")
        tok = lg["token"]
        for bad, code in (({"current": "wrong-wrong", "new": "my-own-pass1"}, 401), ({"current": temp, "new": "short"}, 400), ({"current": temp, "new": temp}, 400)):
            with self.assertRaises(h.ApiError) as c: h.change_password(self.ev(bad, tok))
            self.assertEqual(c.exception.status, code)
        self.assertEqual(h.change_password(self.ev({"current": temp, "new": "my-own-pass1"}, tok))[0], 200)
        with self.assertRaises(h.ApiError): h.login(self.ev({"email": "neha@y.in", "password": temp}))             # temporary password is dead
        self.assertFalse(h.login(self.ev({"email": "neha@y.in", "password": "my-own-pass1"}))[1]["must_change"])
        with self.assertRaises(h.ApiError) as c: admin.request_approve(self.boss, "neha@y.in")                     # they already set their own
        self.assertEqual(c.exception.status, 409)
        with self.assertRaises(h.ApiError) as c: h.signup(self.ev({"name": "Neha", "email": "neha@y.in"}))
        self.assertEqual(c.exception.status, 409)

    def test_reissue_and_reject(self):
        h.signup(self.ev({"name": "Ravi", "email": "ravi@y.in"})); _, a1 = admin.request_approve(self.boss, "ravi@y.in"); _, a2 = admin.request_approve(self.boss, "ravi@y.in")
        self.assertNotEqual(a1["temp_password"], a2["temp_password"])                                              # lost the first one: approve again
        with self.assertRaises(h.ApiError): h.login(self.ev({"email": "ravi@y.in", "password": a1["temp_password"]}))
        self.assertTrue(h.login(self.ev({"email": "ravi@y.in", "password": a2["temp_password"]}))[1]["must_change"])
        h.signup(self.ev({"name": "Spam", "email": "spam@y.in"})); admin.request_reject(self.boss, "spam@y.in")
        self.assertEqual(h.request_status(self.ev({"email": "spam@y.in"}))[1]["status"], "rejected")
        with self.assertRaises(h.ApiError): h.login(self.ev({"email": "spam@y.in", "password": "whatever12"}))
        with self.assertRaises(h.ApiError) as c: admin.request_approve(self.boss, "ghost@y.in")
        self.assertEqual(c.exception.status, 404)


if __name__ == "__main__":
    unittest.main(verbosity=0)
