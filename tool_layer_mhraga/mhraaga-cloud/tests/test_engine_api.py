import json, os, sys, unittest
ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, "..", "..", "..", "music_engine_framework_layer"))
from mhraaga_engine import compose, get_raga, melakarta, catalog
from mhraaga_engine.ragas import N_GOPI
from mhraaga_engine.tala import TALAS
from mhraaga_engine.brief import fallback, make_brief


class Engine(unittest.TestCase):
    def test_melakartas(self):
        self.assertEqual(melakarta(29)["notes"], [0, 2, 4, 5, 7, 9, 11])   # Dheerasankarabharanam = major
        self.assertEqual(melakarta(22)["notes"], [0, 2, 3, 5, 7, 9, 10])   # Kharaharapriya = Kafi
        self.assertEqual(melakarta(65)["notes"], [0, 2, 4, 6, 7, 9, 11])   # Mechakalyani = Yaman
        self.assertEqual(melakarta(8)["notes"], [0, 1, 3, 5, 7, 8, 10])    # Hanumatodi = Bhairavi
        self.assertEqual(len({tuple(melakarta(i)["notes"]) for i in range(1, 73)}), 72)

    def test_gopi_deterministic_and_bounded(self):
        self.assertEqual(get_raga("gopi:123"), get_raga(123))
        for bad in (0, 16001):
            with self.assertRaises(ValueError): get_raga(bad)
        distinct = {(tuple(r["aroha"]), tuple(r["avaroha"]), r["tonic"], r["vadi"]) for r in (get_raga(n) for n in range(1, N_GOPI + 1))}
        self.assertGreater(len(distinct), 15000)

    def test_samvadi_is_fourth_or_fifth_for_gopi(self):
        for n in range(1, 2000, 13):
            r = get_raga(n)
            if r["samvadi"] != 0:
                self.assertIn((r["samvadi"] - r["vadi"]) % 12, (5, 7))

    def test_score_lands_on_sam(self):
        for spec in ("yaman", "gopi:777", "marwa", "todi"):
            for tala in TALAS:
                s = compose(get_raga(spec), tala, 70, 90, "[Mukhda]\nx\ny", seed=2)
                ts = [e[0] for e in s["lead"]]
                self.assertEqual(ts, sorted(ts))
                end_gat = s["sections"][2]["t1"] - 4 * 60 / 70
                self.assertAlmostEqual(s["lead"][-1][0], end_gat, places=2)       # final Sa exactly on sam
                self.assertAlmostEqual(s["tabla"][-1][0], end_gat, places=2)
                self.assertEqual(s["lead"][-1][1], s["sa"])

    def test_short_talas_do_not_repeat_one_motif(self):
        """Regression: in keherwa, dadra, adi and rupak the pakad used to fill every cycle, so the gat repeated and the GAN never ran."""
        for tala in ("keherwa", "dadra", "adi", "rupak"):
            for spec in ("yaman", "bhairavi"):
                s = compose(get_raga(spec), tala, 76, 150, "", seed=3)
                beat, cyc = 60 / s["meta"]["tempo"], TALAS[tala]["beats"] * 60 / s["meta"]["tempo"]
                g = [x for x in s["sections"] if x["name"] == "gat"][0]
                av = {}
                for t, f, *_ in s["lead"]:
                    if g["t0"] <= t < g["t1"]:
                        av.setdefault(int((t - g["t0"]) // cyc), []).append(round(f))
                self.assertGreaterEqual(len({tuple(v) for v in av.values()}) / len(av), 0.7, (tala, spec))
                self.assertGreater(s["meta"]["physics"]["gan_phrases"], 0, (tala, spec))

    def test_lyrics_and_instrumental(self):
        s = compose(get_raga("yaman"), "teental", 70, 90, "[A]\nl1\nl2", seed=1)
        self.assertEqual([x["text"] for x in s["lyrics"] if not x["tag"]], ["l1", "l2"])
        self.assertEqual(compose(get_raga("yaman"), "teental", 70, 90, "x", seed=1, instrumental=True)["lyrics"], [])

    def test_brief_fallback_and_overrides(self):
        b = make_brief("krishna flute at dawn", {"tala": "dadra", "tempo": 90}, api_key="")
        self.assertEqual((b["source"], b["tala"], b["tempo_bpm"]), ("fallback", "dadra", 90))
        self.assertTrue(b["raga"].startswith("gopi:"))
        self.assertEqual(make_brief("evening", {"instrumental": True})["lyrics"], "")
        self.assertEqual(fallback("hello", {})["language"], "english")


class Api(unittest.TestCase):
    """Handler logic with the DynamoDB tables stubbed in memory."""
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
        sys.path.insert(0, os.path.join(ROOT, "..", "api"))
        import handler
        cls.h = handler

    def setUp(self):
        h = self.h
        class T:
            def __init__(s): s.d = {}
            def put_item(s, Item, ConditionExpression=None):
                k = (Item.get("email") or Item["owner"], Item.get("id", ""))
                if ConditionExpression and k in s.d: raise h._db.meta.client.exceptions.ConditionalCheckFailedException({"Error": {}}, "put")
                s.d[k] = dict(Item)
            def get_item(s, Key): return {"Item": dict(s.d[(Key.get("email") or Key["owner"], Key.get("id", ""))])} if (Key.get("email") or Key["owner"], Key.get("id", "")) in s.d else {}
            def update_item(s, Key, UpdateExpression, ExpressionAttributeValues):
                it = s.d[(Key["email"], "")]
                for part in UpdateExpression[4:].split(","):
                    f, v = [x.strip() for x in part.split("=")]; it[f] = ExpressionAttributeValues[v]
            def delete_item(s, Key): s.d.pop((Key["owner"], Key["id"]), None)
            def query(s, **kw): return {"Items": [v for k, v in s.d.items() if k[0] == "x@y.in" and k[1]]}
        h._users, h._songs = T(), T()
        h._cache.update({"jwt_secret": "test-secret", "openrouter_key": ""})

    def call(self, method, path, body=None, token=None):
        ev = {"requestContext": {"http": {"method": method}}, "rawPath": path, "headers": {"authorization": f"Bearer {token}"} if token else {},
              "body": json.dumps(body) if body is not None else None}
        r = self.h.handler(ev); return r["statusCode"], json.loads(r["body"] or "{}")

    def test_flow_and_protection(self):
        self.assertEqual(self.call("GET", "/api/health")[0], 200)
        self.assertEqual(self.call("POST", "/api/compose", {"prompt": "yaman"})[0], 401)
        self.assertEqual(self.call("GET", "/api/songs", token="forged.token.here")[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/signup", {"name": "A", "email": "x@y.in", "password": "short"})[0], 400)
        st, r = self.call("POST", "/api/auth/signup", {"name": "A", "email": "X@y.in", "password": "longenough1"}); self.assertEqual(st, 201)
        tok = r["token"]
        self.assertEqual(self.call("POST", "/api/auth/signup", {"name": "A", "email": "x@y.in", "password": "longenough1"})[0], 409)
        self.assertEqual(self.call("POST", "/api/auth/login", {"email": "x@y.in", "password": "wrongwrong"})[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/login", {"email": "x@y.in", "password": "longenough1"})[0], 200)
        st, song = self.call("POST", "/api/compose", {"prompt": "krishna flute dawn bhajan", "duration": 60}, tok)
        self.assertEqual(st, 200); self.assertTrue(song["score"]["lead"]); self.assertEqual(song["source"], "fallback")
        st, got = self.call("GET", f"/api/songs/{song['id']}", token=tok); self.assertEqual(st, 200); self.assertEqual(got["score"]["lead"], song["score"]["lead"])
        self.assertEqual(self.call("POST", "/api/compose", {"prompt": "x", "raga": "nonsense"}, tok)[0], 400)
        self.assertEqual(self.call("DELETE", f"/api/songs/{song['id']}", token=tok)[0], 200)
        self.assertEqual(self.call("GET", f"/api/songs/{song['id']}", token=tok)[0], 404)

    def test_quota(self):
        self.h.DAILY_LIMIT = 2
        _, r = self.call("POST", "/api/auth/signup", {"name": "A", "email": "x@y.in", "password": "longenough1"})
        for _ in range(2): self.assertEqual(self.call("POST", "/api/compose", {"prompt": "yaman evening"}, r["token"])[0], 200)
        self.assertEqual(self.call("POST", "/api/compose", {"prompt": "yaman evening"}, r["token"])[0], 429)

    def test_token_expiry_and_tamper(self):
        t = self.h.make_token("a@b.in", "k")
        self.assertEqual(self.h.read_token(t, "k"), "a@b.in"); self.assertIsNone(self.h.read_token(t, "other"))
        self.assertIsNone(self.h.read_token(t[:-3] + "xxx", "k"))


if __name__ == "__main__":
    unittest.main()
