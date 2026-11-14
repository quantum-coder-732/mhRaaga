import os, sys, unittest
from pathlib import Path

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "music_engine_framework_layer"), str(ROOT / "tool_layer_mhraga/mhraaga-cloud/api")]
import handler, studio  # noqa: E402


class Studio(unittest.TestCase):
    def test_rules_block_and_allow(self):
        studio._rules_cache = (0.0, {})
        studio.check("a gentle poem about the river")
        for bad in ("how to make a bomb", "a talk in the voice of someone famous", "CLONE THE VOICE OF my teacher"):
            with self.assertRaises(handler.ApiError) as c:
                studio.check(bad)
            self.assertEqual(c.exception.status, 422)

    def test_learned_defaults_shape(self):
        studio._rules_cache = (9e18, {**studio.DEFAULT_RULES, "learned": {"leaders": {"tamil": {"tala": {"arm": "ektal"}, "lead": {"arm": "veena"}, "tempo": {"arm": "70"}}}}})
        self.assertEqual(studio.learned_defaults("tamil"), {"tala": "ektal", "lead": "veena", "tempo": 70})
        self.assertEqual(studio.learned_defaults("hindi"), {})

    def test_admin_only_rule_edits(self):
        with self.assertRaises(handler.ApiError) as c:
            studio.need_admin({"email": "someone@example.com"})
        self.assertEqual(c.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
