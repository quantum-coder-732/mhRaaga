"""AI-singer job queue and the Styles parser (no GPU, no AWS)."""
import json, os, sys, time, unittest
ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, "..", "..", "..", "music_engine_framework_layer")); sys.path.insert(0, os.path.join(ROOT, "..", "api")); sys.path.insert(0, ROOT)
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1"); os.environ["ADMIN_EMAILS"] = "boss@example.com"
import handler as h, jobs  # noqa: E402
from test_admin import Fake, mk  # noqa: E402
from mhraaga_engine import styles, compose, get_raga  # noqa: E402


class Jobs(unittest.TestCase):
    def setUp(self):
        h._users, h._songs = Fake(("email",)), Fake(("owner", "id")); jobs.ENABLED = True
        self.boss, self.bob = mk("boss@example.com", "Boss"), mk("bob@example.com", "Bob")

    def test_admin_only_and_switch(self):
        with self.assertRaises(h.ApiError) as c: jobs.create(self.bob, {"style": "sufi", "lyrics": "kun faya kun"})
        self.assertEqual(c.exception.status, 403)
        jobs.ENABLED = False
        with self.assertRaises(h.ApiError) as c: jobs.create(self.boss, {"style": "sufi qawwali", "lyrics": "one two three four"})
        self.assertEqual(c.exception.status, 503)

    def test_create_list_get_limit(self):
        st, r = jobs.create(self.boss, {"style": "sufi qawwali, harmonium", "lyrics": "line one\nline two", "title": "T"}); self.assertEqual((st, r["job"]["status"]), (201, "queued"))
        self.assertEqual(r["job"]["lines"], 2); self.assertNotIn("lyrics", r["job"])
        jid = r["job"]["id"]; self.assertEqual(jobs.get_job(self.boss, jid)[1]["job"]["style"], "sufi qawwali, harmonium")
        self.assertEqual(len(jobs.list_jobs(self.boss)[1]["jobs"]), 1)
        for bad in ("abc", "1"):
            with self.assertRaises(h.ApiError): jobs.get_job(self.boss, bad)
        with self.assertRaises(h.ApiError): jobs.create(self.boss, {"style": "x", "lyrics": "short"})
        boss = h._users.get_item(Key={"email": "boss@example.com"})["Item"]
        for i in range(jobs.DAILY - 1):
            jobs.create(boss, {"style": "sufi", "lyrics": f"line {i} here"}); boss = h._users.get_item(Key={"email": "boss@example.com"})["Item"]
            time.sleep(0.002)
        with self.assertRaises(h.ApiError) as c: jobs.create(boss, {"style": "sufi", "lyrics": "one more song please"})
        self.assertEqual(c.exception.status, 429)

    def test_worker_alive(self):
        self.assertFalse(jobs.info(self.boss)[1]["worker_alive"])
        h._songs.put_item(Item={"owner": jobs.OWNER, "id": "0worker", "seen": int(time.time()), "name": "gpu-1"})
        self.assertEqual((jobs.info(self.boss)[1]["worker_alive"], jobs.info(self.boss)[1]["worker"]), (True, "gpu-1"))
        h._songs.put_item(Item={"owner": jobs.OWNER, "id": "0worker", "seen": int(time.time()) - 999, "name": "gpu-1"}); self.assertFalse(jobs.info(self.boss)[1]["worker_alive"])


class Styles(unittest.TestCase):
    def test_priority_and_ensemble(self):
        s = styles.parse("sufi qawwali, harmonium, dholak, handclaps, building crescendo")
        self.assertEqual((s["lead"], s["tala"], s["tempo"]), ("harmonium", "dadra", 96)); self.assertEqual(set(s["ensemble"]), {"dholak", "clap"})
        self.assertEqual(styles.parse("slow bhajan")["tempo"], 64); self.assertEqual(styles.parse("jazz fusion")["lead"], "")
        self.assertEqual(styles.parse("bhajan, veena")["lead"], "veena")

    def test_score_carries_style_and_ensemble(self):
        sc = compose(get_raga("bhairavi"), "dadra", 100, 90, "", seed=1, style="sufi qawwali", ensemble=["dholak", "clap", "tabla"])
        self.assertEqual((sc["meta"]["style"], sc["meta"]["ensemble"]), ("sufi qawwali", ["dholak", "clap"]))


class Projection(unittest.TestCase):
    """Regression: `style` is a DynamoDB reserved word, so naming it bare in a ProjectionExpression made /songs and /playlist fail with a 500."""
    RESERVED = {"style", "language", "source", "duration", "status", "name", "role", "limit", "type", "time", "date", "user", "key", "value", "data", "comment", "count", "order"}

    def test_list_songs_projection_has_no_bare_reserved_words(self):
        seen = {}
        class Rec(Fake):
            def query(self, **kw):
                seen.update(kw); return super().query(**kw)
        h._songs = Rec(("owner", "id")); h._users = Fake(("email",)); boss = mk("boss@example.com", "Boss")
        h.list_songs({"headers": {}}, "boss@example.com")
        names = seen["ProjectionExpression"].replace(" ", "").split(",")
        bare = [n for n in names if not n.startswith("#") and n.lower() in self.RESERVED]
        self.assertEqual(bare, [], f"bare reserved words in the projection: {bare}")
        self.assertEqual(seen["ExpressionAttributeNames"]["#y"], "style")


if __name__ == "__main__":
    unittest.main(verbosity=0)
