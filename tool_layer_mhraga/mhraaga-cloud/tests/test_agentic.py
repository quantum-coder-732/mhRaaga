import json, random, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "music_engine_framework_layer"))
from mhraaga_engine.agentic import critics, evolve
from mhraaga_engine.lyrics_bank import BANK, make_lyrics
from mhraaga_engine.brief import make_brief


class Agentic(unittest.TestCase):
    def test_seven_languages_have_native_script_lyrics(self):
        self.assertEqual(set(BANK), {"hindi", "marathi", "english", "telugu", "gujarati", "kannada", "tamil"})
        for lang in BANK:
            ly, _ = make_lyrics(lang, "", random.Random(1))
            self.assertIn("[", ly)
            self.assertEqual(make_brief("a song", {"language": lang})["language"], lang)

    def test_critic_scores_in_range_and_script_checked(self):
        g = {a: evolve.ARMS[a][0] for a in evolve.ARMS}
        s = evolve.make_song("tamil", g, 5)
        self.assertTrue(all(0 <= v <= 1 for v in s["review"]["scores"].values()))
        self.assertGreater(s["review"]["scores"]["lyrics_fit"], 0.8)
        wrong = dict(s["brief"], language="telugu")  # Tamil text judged as Telugu must score worse
        self.assertLess(critics.lyrics_fit(s["score"], wrong)[0], critics.lyrics_fit(s["score"], s["brief"])[0])

    def test_shapley_credit_is_efficient(self):
        q = {"a": 0.9, "b": 0.5, "c": 0.7}
        out = evolve.attribute_reward(q, 0.8)
        self.assertAlmostEqual(sum(out.values()), 0.8, places=6)
        self.assertGreater(out["a"], out["b"])

    def test_loop_improves_and_respects_cap(self):
        with tempfile.TemporaryDirectory() as d:
            evolve.STATE = Path(d) / "policy.json"
            evolve.Policy.__init__.__defaults__ = (evolve.STATE,)
            st = evolve.run(Path(d) / "cat", rounds=6, explore=6, improve=2, seed=7, log=lambda m: None)
            self.assertGreater(st["curve"][-1], st["curve"][0])
            self.assertLessEqual(st["size"], evolve.CAP)
            self.assertTrue(all(len(evolve.Catalog(Path(d) / "cat").of(l)) <= evolve.QUOTA[l] for l in evolve.LANGS))


if __name__ == "__main__":
    unittest.main()
