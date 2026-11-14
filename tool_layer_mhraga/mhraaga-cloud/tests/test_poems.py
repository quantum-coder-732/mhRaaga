"""Spoken poems must look like the reference poem videos: short rhymed lines, 2-4 minutes, soft music with no tabla, ending on Sa."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "music_engine_framework_layer"))
from mhraaga_engine import compose, get_raga
from mhraaga_engine.agentic import critics
from mhraaga_engine.brief import make_brief

LANGS = ("english", "hindi", "marathi", "telugu", "gujarati", "kannada", "tamil")


def poem_song(lang, prompt="a poem about love as friendship"):
    b = make_brief(prompt, {"language": lang, "poem": True})
    sc = compose(get_raga(b["raga"]), b["tala"], b["tempo_bpm"], 150, b["lyrics"], seed=4, lead=b["lead"], poem=True)
    return b, sc


class Poems(unittest.TestCase):
    def test_every_language_makes_a_proper_poem(self):
        for lang in LANGS:
            b, sc = poem_song(lang)
            lines = [l for l in sc["lyrics"] if not l["tag"]]
            self.assertTrue(b["poem"], lang)
            self.assertTrue(10 <= len(lines) <= 24, f"{lang}: {len(lines)} lines")
            self.assertTrue(120 <= sc["duration"] <= 240, lang)
            self.assertEqual(sc["tabla"], [], lang)
            self.assertGreaterEqual(lines[0]["t"], 3, lang)
            self.assertLessEqual(lines[-1]["t"], sc["duration"] - 8, lang)
            r = critics.review(sc, b)
            self.assertGreater(r["scores"]["poem_form"], 0.7, f"{lang}: {r['detail']['poem_form']}")
            self.assertGreater(r["scores"]["lyrics_fit"], 0.8, lang)

    def test_poem_is_judged_on_form_not_tabla(self):
        b, sc = poem_song("english")
        self.assertEqual(critics.review(sc, b)["scores"]["cadence"] >= 0.4, True)


if __name__ == "__main__":
    unittest.main()
