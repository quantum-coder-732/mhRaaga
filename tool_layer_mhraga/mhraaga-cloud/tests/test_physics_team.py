import json, os, random, sys, unittest
ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, "..", "..", "..", "music_engine_framework_layer"))
from mhraaga_engine import compose, get_raga
from mhraaga_engine import physics, autotune, gan


class Physics(unittest.TestCase):
    def test_rubato_is_small_and_bounded(self):
        ev = [[i * 0.5, 233.0, 0.4 if i % 4 else 2.0, 0] for i in range(60)]
        off = physics.rubato(ev, 0.5, 7)
        self.assertTrue(all(abs(o) <= 0.028 + 1e-9 for o in off)); self.assertGreater(max(off) - min(off), 0.002)

    def test_bigger_interval_longer_glide_and_bounded(self):
        a, b = physics.glide_time(2, 2.0), physics.glide_time(9, 2.0)
        self.assertGreater(b, a); self.assertLessEqual(b, 0.30); self.assertEqual(physics.glide_time(0.4, 2.0), 0.0)

    def test_leaps_land_harder_than_steps(self):
        w = physics.weights([0, 1, 0, 12, 0], [False] * 5)
        self.assertGreater(w[3], w[1]); self.assertTrue(all(0.6 <= x <= 1.0 for x in w))

    def test_floor_contact_bounces_with_restitution(self):
        w = physics.World1D(gravity=-9.8, floor=0.0, restitution=0.5); b = physics.Body(x=1.0); peaks = 0; up = False
        for _ in range(2000):
            v0 = b.v; w.step(b)
            if v0 > 0 and b.v <= 0: peaks += 1
        self.assertGreaterEqual(peaks, 1)


class Backend(unittest.TestCase):
    def test_backend_is_reported_and_matches_import(self):
        try:
            import Box2D  # noqa: F401
            want = "box2d "
        except ImportError:
            want = "box2d-style"
        self.assertTrue(physics.BACKEND.startswith(want), physics.BACKEND)
        self.assertEqual(compose(get_raga("yaman"), seed=2, duration=50)["meta"]["physics"]["engine"], physics.BACKEND)


class Tune(unittest.TestCase):
    def test_snap_pulls_to_shruti(self):
        sa, scale = 233.0, {0, 2, 4, 7, 9}
        f = sa * 9 / 8 * 2 ** (30 / 1200)                      # 30 cents sharp of Re
        self.assertAlmostEqual(autotune.snap(f, sa, scale, 1.0), sa * 9 / 8, places=3)
        half = autotune.snap(f, sa, scale, 0.5); self.assertTrue(sa * 9 / 8 < half < f)

    def test_deadband_keeps_vibrato(self):
        sa = 233.0; f = sa * 2 ** (6 / 1200)
        self.assertEqual(autotune.track([f], sa, {0, 2}, 1.0, 12.0)[0], f)


class Gan(unittest.TestCase):
    def test_phrases_stay_in_raga_and_vary(self):
        self.assertTrue(gan.available())
        r = get_raga("yaman"); sc = sorted({n % 12 for n in r["aroha"] + r["avaroha"]}); rng = random.Random(1); seen = set()
        for _ in range(15):
            g = gan.generate(rng, sc)
            if g: self.assertTrue(all(n % 12 in sc or n == 12 for n in g[0])); seen.add(tuple(g[0]))
        self.assertGreater(len(seen), 5)


class ComposePhysics(unittest.TestCase):
    def test_every_raga_kind_ends_on_sam_and_is_deterministic(self):
        for spec in ("yaman", "bhairav", "mela:29", "gopi:777"):
            a = compose(get_raga(spec), seed=11, duration=70, lyrics="a"); b = compose(get_raga(spec), seed=11, duration=70, lyrics="a")
            self.assertEqual(a, b); self.assertTrue(a["meta"]["physics"]["enabled"])
            self.assertEqual(a["lead"][-1][1], a["sa"]); ts = [e[0] for e in a["lead"]]; self.assertEqual(ts, sorted(ts))
            self.assertTrue(all(len(e) == 6 and 0.55 <= e[4] <= 1.0 for e in a["lead"]))

    def test_can_switch_physics_off(self):
        s = compose(get_raga("yaman"), seed=3, duration=60, human=False)
        self.assertFalse(s["meta"]["physics"]["enabled"]); self.assertEqual(len(s["lead"][0]), 4)


class Team(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "..", "api")); sys.argv = ["x"]
        import local_server as ls
        cls.h = ls.h; ls.DB.unlink(missing_ok=True); cls.tok = {}
        for n in ("dir", "a1", "a2", "vw", "out"):
            cls.h._users.put_item(Item={"email": f"{n}@t.com", "name": n, "pw": cls.h.hash_pw("Test-pass-123!"), "created": "2026-01-01T00:00:00+00:00", "fails": 0, "locked_until": 0, "qday": cls.h.today(), "qn": 0})
            c, o = cls.call("POST", "/auth/login", body={"email": f"{n}@t.com", "password": "Test-pass-123!"}); cls.tok[n] = o["token"]

    @classmethod
    def call(cls, m, p, t=None, body=None):
        ev = {"requestContext": {"http": {"method": m}}, "rawPath": "/api" + p, "headers": {"authorization": "Bearer " + t} if t else {}, "body": json.dumps(body) if body is not None else None}
        r = cls.h.handler(ev); return r["statusCode"], json.loads(r["body"] or "{}")

    def test_roles_locking_and_assemble(self):
        T, c = self.tok, self.call
        s, o = c("POST", "/teams", T["dir"], {"kind": "film", "title": "Test"}); pid = o["id"]
        self.assertEqual(c("POST", f"/teams/{pid}/invite", T["dir"], {"emails": ["a1@t.com", "a2@t.com"]})[0], 200)
        self.assertEqual(c("POST", f"/teams/{pid}/invite", T["dir"], {"email": "vw@t.com", "role": "viewer"})[0], 200)
        self.assertEqual(c("POST", f"/teams/{pid}/invite", T["a1"], {"email": "x@t.com"})[0], 403)       # artists cannot add people
        self.assertEqual(c("GET", f"/teams/{pid}", T["out"])[0], 403)                                    # outsiders see nothing
        s, l1 = c("POST", f"/teams/{pid}/layers", T["a1"], {"name": "A", "data": {"title": "One", "effects": ["glow", "bogus"]}})
        self.assertEqual(c("PUT", f"/teams/{pid}/layers/{l1['id']}", T["a2"], {"data": {"title": "x"}, "base_rev": 1})[0], 403)   # not their layer
        self.assertEqual(c("PUT", f"/teams/{pid}/layers/{l1['id']}", T["a1"], {"data": {"title": "Two", "effects": ["glow", "bogus"]}, "base_rev": 1})[0], 200)
        self.assertEqual(c("PUT", f"/teams/{pid}/layers/{l1['id']}", T["a1"], {"data": {"title": "Stale"}, "base_rev": 1})[0], 409)  # optimistic lock
        self.assertEqual(c("POST", f"/teams/{pid}/layers", T["vw"], {"data": {}})[0], 403)               # viewers cannot edit
        self.assertEqual(c("POST", f"/teams/{pid}/comments", T["vw"], {"text": "nice"})[0], 200)         # but can comment
        s, o = c("PUT", f"/teams/{pid}/layers/{l1['id']}", T["a1"], {"status": "approved", "base_rev": 2}); self.assertEqual(o["status"], "wip")   # cannot self-approve
        self.assertEqual(c("PUT", f"/teams/{pid}/layers/{l1['id']}", T["dir"], {"status": "approved", "base_rev": 3})[1]["status"], "approved")
        s, a = c("GET", f"/teams/{pid}/assemble", T["dir"]); self.assertEqual([x["title"] for x in a["scenes"]], ["Two"]); self.assertEqual(a["scenes"][0]["effects"], ["glow"])
        self.assertEqual(c("DELETE", f"/teams/{pid}", T["a1"])[0], 403); self.assertEqual(c("DELETE", f"/teams/{pid}", T["dir"])[0], 200)
        self.assertEqual(c("GET", f"/teams/{pid}", T["dir"])[0], 404)

    def test_member_cap_and_song_render(self):
        T, c = self.tok, self.call
        s, o = c("POST", "/teams", T["dir"], {"kind": "song", "title": "Song", "raga": "yaman"}); pid = o["id"]
        s, o = c("POST", f"/teams/{pid}/invite", T["dir"], {"emails": [f"u{i}@t.com" for i in range(150)]}); self.assertEqual(s, 400)   # director + 150 > cap
        c("POST", f"/teams/{pid}/layers", T["dir"], {"name": "M", "data": {"section": "mukhda", "lyrics": "sanjh dhale yaman ke sur\nman mein base"}})
        s, song = c("POST", f"/teams/{pid}/render", T["dir"]); self.assertEqual(s, 200); self.assertEqual(song["raga"], "Yaman"); self.assertTrue(song["score"]["meta"]["physics"]["enabled"])


if __name__ == "__main__":
    unittest.main()
