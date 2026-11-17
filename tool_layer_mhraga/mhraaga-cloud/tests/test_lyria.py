"""Full AI songs (Lyria 3): limits, background hand-off, storing the result, failure handling. No network, no AWS."""
import base64, io, json, os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
from test_admin import Fake, mk, h  # noqa: E402  (sets the env and the signing key)
import lyria  # noqa: E402


class Lam:
    def __init__(s): s.calls = []
    def invoke(s, **kw): s.calls.append(kw)


class S3:
    def __init__(s): s.put = {}
    def put_object(s, Bucket, Key, Body, **kw): s.put[Key] = Body


class Resp:
    def __init__(s, lines): s.lines = lines
    def __enter__(s): return s
    def __exit__(s, *a): return False
    def __iter__(s): return iter(s.lines)


def stream(mp3: bytes, cost=0.08):
    ev = lambda d: ("data: " + json.dumps(d) + "\n").encode()
    return Resp([ev({"choices": [{"delta": {"content": "[[A0]]"}}]}), ev({"choices": [{"delta": {"audio": {"data": base64.b64encode(mp3).decode()}}}]}),
                 ev({"choices": [], "usage": {"cost": cost}}), b"data: [DONE]\n"])


class Ly(unittest.TestCase):
    def setUp(self):
        h._users, h._songs = Fake(("email",)), Fake(("owner", "id"))
        self.u = mk("bob@example.com", "Bob"); lyria.BUCKET, lyria.ENABLED = "b", True; lyria._s3, lyria._lam = S3(), Lam()
        h._cache["openrouter_key"] = "k"

    def test_create_hands_off_and_limits(self):
        st, r = lyria.create(self.u, {"title": "T", "style": "bhajan", "lyrics": "[Verse]\nhe mohan"}, "mhraaga-api")
        self.assertEqual((st, r["status"]), (202, "pending")); call = lyria._lam.calls[0]
        self.assertEqual((call["FunctionName"], call["InvocationType"]), ("mhraaga-api", "Event")); job = json.loads(call["Payload"])["lyria_job"]
        self.assertIn("he mohan", job["prompt"]); self.assertTrue(job["key"].startswith("lyria/") and job["key"].endswith(".mp3"))
        row = h._songs.get_item(Key={"owner": "bob@example.com", "id": r["id"]})["Item"]; self.assertEqual((row["source"], row["status"]), ("lyria", "pending"))
        self.assertEqual(lyria.status(self.u, r["id"])[1]["status"], "pending")
        for _ in range(lyria.USER_DAILY - 1):
            lyria.create(h._users.get_item(Key={"email": "bob@example.com"})["Item"], {"title": "x"}, "f")
        with self.assertRaises(h.ApiError) as c: lyria.create(h._users.get_item(Key={"email": "bob@example.com"})["Item"], {"title": "x"}, "f")
        self.assertEqual(c.exception.status, 429)

    def test_site_cap_and_off_switch(self):
        h._songs.put_item(Item={"owner": "quota#lyria", "id": lyria._day(), "usd": Decimal_(lyria.SITE_DAILY_USD)})
        with self.assertRaises(h.ApiError) as c: lyria.create(self.u, {"title": "x"}, "f")
        self.assertEqual(c.exception.status, 429)
        lyria.ENABLED = False
        with self.assertRaises(h.ApiError) as c: lyria.create(self.u, {"title": "x"}, "f")
        self.assertEqual(c.exception.status, 503)

    def test_run_stores_song_and_spend(self):
        _, r = lyria.create(self.u, {"title": "T"}, "f"); job = json.loads(lyria._lam.calls[0]["Payload"])["lyria_job"]
        orig = lyria.urllib.request.urlopen; lyria.urllib.request.urlopen = lambda req, timeout=0: stream(b"x" * 90_000)
        try: out = lyria.run(job)
        finally: lyria.urllib.request.urlopen = orig
        self.assertTrue(out["ok"]); self.assertEqual(len(lyria._s3.put[job["key"]]), 90_000)
        st = lyria.status(self.u, r["id"])[1]; self.assertEqual((st["status"], st["audio"]), ("done", "/" + job["key"]))
        self.assertAlmostEqual(float(h._songs.get_item(Key={"owner": "quota#lyria", "id": lyria._day()})["Item"]["usd"]), 0.08)
        self.assertEqual(st["title"], "T"); full = h.get_song({"headers": {"authorization": "Bearer " + h.make_token("bob@example.com")}}, r["id"])[1]
        self.assertEqual(full["audio"], "/" + job["key"])                                          # opens without a score

    def test_failure_is_reported_and_not_counted(self):
        _, r = lyria.create(self.u, {"title": "T"}, "f"); job = json.loads(lyria._lam.calls[0]["Payload"])["lyria_job"]
        orig = lyria.urllib.request.urlopen; lyria.urllib.request.urlopen = lambda req, timeout=0: stream(b"tiny", cost=0)
        try: out = lyria.run(job)
        finally: lyria.urllib.request.urlopen = orig
        self.assertFalse(out["ok"]); st = lyria.status(self.u, r["id"])[1]; self.assertEqual(st["status"], "failed"); self.assertTrue(st["error"])
        self.assertEqual(int(h._users.get_item(Key={"email": "bob@example.com"})["Item"]["ly_n"]), 0)   # nothing charged, so the try is given back

    def test_plan_cost_names_the_model_and_prices_the_call(self):
        n, c = h.plan_cost({"usage": {"model": "deepseek/deepseek-v4-flash", "prompt_tokens": 1000, "completion_tokens": 500}}); self.assertEqual(n, "DeepSeek V4 Flash"); self.assertAlmostEqual(c, 0.00018, places=6)
        self.assertEqual(h.plan_cost({"source": "fallback"}), ("Built-in engine", 0.0))
        self.assertEqual(h.plan_cost({"usage": {"model": "z-ai/glm-5.3-flash", "cost": 0.0004}}), ("GLM 5.3 Flash", 0.0004))

    def test_handler_runs_the_background_job(self):
        self.assertIn("lyria_job", __import__("inspect").getsource(h.handler))


def Decimal_(x):
    from decimal import Decimal
    return Decimal(str(x))


if __name__ == "__main__":
    unittest.main(verbosity=0)
