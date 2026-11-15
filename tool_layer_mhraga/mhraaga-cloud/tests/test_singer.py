"""The singer layer: raga melody -> ABC score for YuE2, request building, and the queue path that uses it (no GPU)."""
import json, os, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(__file__)
REPO = os.path.abspath(os.path.join(ROOT, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "music_engine_framework_layer")); sys.path.insert(0, os.path.join(REPO, "tool_layer_mhraga")); sys.path.insert(0, os.path.join(ROOT, "..", "api")); sys.path.insert(0, ROOT)
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1"); os.environ["ADMIN_EMAILS"] = "boss@example.com"
from mhraaga_engine import compose, get_raga  # noqa: E402
from singer import build_request, score_to_abc  # noqa: E402
from singer.abc import _abc_pitch  # noqa: E402
import handler as h, jobs  # noqa: E402
from test_admin import Fake, mk  # noqa: E402

LYR = "[Mukhda]\nline one here\nline two here\nline three here\nline four here\n[Chorus]\nsing it again\nsing it twice"
YUE_TOOLS = os.path.join(REPO, "third_party", "YuE", "skills", "yue2-music", "scripts", "abc_tools.py")


def song(spec="bhairavi", tala="dadra"):
    s = compose(get_raga(spec), tala, 96, 120, LYR, seed=5, lead="harmonium")
    return {"id": "s1", "title": "T", "score": s}


class Abc(unittest.TestCase):
    def test_pitch_spelling(self):
        seen = {}
        self.assertEqual(_abc_pitch(55, seen), "G,")                 # Sa = G3
        self.assertEqual(_abc_pitch(56, seen), "_A,")                # komal Re
        self.assertEqual(_abc_pitch(67, {}), "G")                    # an octave up
        self.assertEqual(_abc_pitch(79, {}), "g")
        s = {}; self.assertEqual((_abc_pitch(66, s), _abc_pitch(65, s)), ("^F", "=F"))   # a natural after a sharp in the same bar

    def test_structure_and_validator(self):
        r = build_request(song(), style_words="sufi qawwali, dholak", rid="x")
        self.assertEqual((r["lines"], r["bars"], r["cot"]), (6, 12, "melody"))
        self.assertIn("[Verse]", r["lyrics"]); self.assertIn("[Chorus]", r["lyrics"]); self.assertIn("96 BPM", r["style"]); self.assertTrue(r["abc"].startswith("X:1\nT:\n"))
        groups = r["abc"].count("V: Vocal\n"); self.assertEqual(groups, 3)                 # 12 bars in groups of at most 4
        if os.path.exists(YUE_TOOLS):                                                        # the model's own structural check
            with tempfile.NamedTemporaryFile("w", suffix=".abc", delete=False) as f: f.write(r["abc"])
            out = subprocess.run([sys.executable, YUE_TOOLS, "inspect", f.name], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertEqual(json.loads(out.stdout)["voices"]["Vocal"]["measures"], 12)

    def test_melody_stays_in_the_raga(self):
        """Every sung note, read back from the ABC, is a note of the raga: Sa is G, so Bhairavi (0 1 3 5 7 8 10 from Sa) is G A-flat B-flat C D E-flat F."""
        import re
        base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        for spec, scale in (("bhairavi", {0, 1, 3, 5, 7, 8, 10}), ("yaman", {0, 2, 4, 6, 7, 9, 11})):
            r = build_request(song(spec), rid="x"); used = set()
            for line in r["abc"].splitlines():
                if line.startswith(("X:", "T:", "M:", "L:", "Q:", "V:", "K:", "%", "Z")): continue
                for m in re.finditer(r"([_^=]?)([A-Ga-g])[,']*\d*-?", line):
                    pc = (base[m.group(2).upper()] + {"_": -1, "^": 1}.get(m.group(1), 0)) % 12
                    used.add((pc - 7) % 12)                                                   # semitones above Sa
            self.assertTrue(used and used <= scale, (spec, sorted(used)))

    def test_romanised_lyrics_keep_the_structure(self):
        r = build_request(song(), lyrics_override="a b\nc d\ne f\ng h\ni j\nk l")
        self.assertEqual(r["lyrics"].splitlines()[1], "a b"); self.assertEqual(r["lines"], 6)


class Queue(unittest.TestCase):
    def setUp(self):
        h._users, h._songs = Fake(("email",)), Fake(("owner", "id")); jobs.ENABLED = True
        self.boss = mk("boss@example.com", "Boss"); s = song()
        h._songs.put_item(Item={"owner": "boss@example.com", "id": "s1", "title": "T", "brief": "{}", "score": json.dumps(s["score"])})

    def test_sing_my_song(self):
        st, r = jobs.create(self.boss, {"song_id": "s1", "style": "sufi qawwali"}); self.assertEqual(st, 201)
        row = h._songs.get_item(Key={"owner": jobs.OWNER, "id": r["job"]["id"]})["Item"]
        self.assertEqual((row["cot"], row["song_id"]), ("melody", "s1")); self.assertTrue(row["abc"].startswith("X:1")); self.assertIn("[Verse]", row["lyrics"])
        with self.assertRaises(h.ApiError) as c: jobs.create(self.boss, {"song_id": "nope", "style": "sufi"})
        self.assertEqual(c.exception.status, 404)


if __name__ == "__main__":
    unittest.main(verbosity=0)
