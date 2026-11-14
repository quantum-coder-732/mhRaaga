import io, os, sys, unittest, wave
ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, "..", "..", "..", "music_engine_framework_layer")); sys.path.insert(0, os.path.join(ROOT, "..", "api"))
os.environ["SITE_BUCKET"] = "test-bucket"; os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
sys.argv = ["x"]
import local_server  # noqa: F401  (wires the handler to the local file database)
import handler as h, voice

PCM = lambda secs: b"\x01\x02" * int(voice.RATE * secs)


class FakeS3:
    def __init__(self): self.objs = {}
    def head_object(self, Bucket, Key):
        if Key not in self.objs: raise KeyError(Key)
        return {"Metadata": self.objs[Key]["Metadata"]}
    def put_object(self, **kw): self.objs[kw["Key"]] = kw


class Voice(unittest.TestCase):
    def setUp(self):
        voice._s3, self.calls, self.spend = FakeS3(), [], []
        voice._spent_site = lambda _h: 0.0
        voice._add_spend = lambda _h, u, usd: self.spend.append(usd)
        self.u = {"email": "a@b.co"}

    def fake(self, *secs):
        q = list(secs)
        def f(model, lang, how, text, vc):
            self.calls.append((model, lang, vc)); return PCM(q.pop(0)), 0.002
        voice._openrouter = f

    def test_generates_once_then_serves_from_cache(self):
        self.fake(3.0)
        s, a = voice.speak(self.u, {"text": "सद्गुरुकृपेने अनुभव", "lang": "marathi", "style": "bhajan", "voice": "female"})
        self.assertEqual((s, a["cached"]), (200, False)); self.assertEqual(self.calls[0], ("openai/gpt-audio", "marathi", "shimmer"))   # devotional text: full model
        w = wave.open(io.BytesIO(voice._s3.objs[a["url"][1:]]["Body"])); self.assertEqual((w.getframerate(), w.getnchannels()), (24000, 1))
        s, b = voice.speak(self.u, {"text": "सद्गुरुकृपेने अनुभव", "lang": "marathi", "style": "bhajan", "voice": "female"})
        self.assertTrue(b["cached"]); self.assertEqual(len(self.calls), 1)      # the second request cost nothing
        self.assertEqual(len(self.spend), 1)

    def test_mini_that_adds_sentences_is_redone_on_the_full_model(self):
        self.fake(30.0, 2.0)
        s, a = voice.speak(self.u, {"text": "Hello there friend", "lang": "english", "style": "story"})
        self.assertEqual([c[0] for c in self.calls], ["openai/gpt-audio-mini", "openai/gpt-audio"]); self.assertEqual(a["seconds"], 2.0)
        self.assertAlmostEqual(sum(self.spend), 0.004)                         # both attempts are billed to the cap

    def test_limits_and_bad_input(self):
        with self.assertRaises(h.ApiError) as e: voice.speak(self.u, {"text": "x" * 400}); 
        self.assertEqual(e.exception.status, 400)
        with self.assertRaises(h.ApiError) as e: voice.speak(self.u, {"text": "[Mukhda]"})
        self.assertEqual(e.exception.status, 400)                                # tags only: nothing to speak
        with self.assertRaises(h.ApiError) as e: voice.speak({"email": "a@b.co", "tday": voice._day(), "tusd": 5}, {"text": "hello"})
        self.assertEqual(e.exception.status, 429)                                # user's daily cap
        voice._spent_site = lambda _h: 999.0
        with self.assertRaises(h.ApiError) as e: voice.speak(self.u, {"text": "hello"})
        self.assertEqual(e.exception.status, 429)                                # site-wide cap

    def test_busy_upstream_is_retried_then_reported_as_503(self):
        import urllib.error, urllib.request
        calls = []
        def fake_open(req, timeout=0):
            calls.append(1); raise urllib.error.HTTPError("u", 429, "Too Many Requests", {"Retry-After": "0"}, None)
        orig, orig_sleep = urllib.request.urlopen, voice.time.sleep
        urllib.request.urlopen, voice.time.sleep = fake_open, lambda s: None
        try:
            with self.assertRaises(h.ApiError) as e: voice._open(urllib.request.Request("http://x"))
        finally:
            urllib.request.urlopen, voice.time.sleep = orig, orig_sleep
        self.assertEqual(e.exception.status, 503); self.assertEqual(len(calls), 4)      # four tries, then a retryable 503

    def test_garbage_audio_is_not_cached(self):
        self.fake(0.05)
        with self.assertRaises(h.ApiError) as e: voice.speak(self.u, {"text": "hello world today", "style": "poem"})
        self.assertEqual(e.exception.status, 502); self.assertEqual(voice._s3.objs, {})

    def test_blocked_text_is_refused_before_any_spend(self):
        self.fake(2.0)
        with self.assertRaises(h.ApiError): voice.speak(self.u, {"text": "how to make a bomb"})
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
