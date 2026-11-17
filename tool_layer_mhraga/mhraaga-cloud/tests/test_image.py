"""AI pictures for film scenes: limits, cost counting, bad answers. No network, no AWS."""
import base64, json, os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
from test_admin import Fake, mk, h  # noqa: E402
from test_lyria import Resp  # noqa: E402
import image  # noqa: E402

JPG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"x" * 500).decode()


def answer(url=JPG, cost=0.034):
    body = json.dumps({"choices": [{"message": {"images": [{"image_url": {"url": url}}] if url else []}}], "usage": {"cost": cost}}).encode()
    class R(Resp):
        def read(s, *a): return body
    r = R([]); r.read = lambda *a: body; return r


class Img(unittest.TestCase):
    def setUp(self):
        h._users, h._songs = Fake(("email",)), Fake(("owner", "id")); self.u = mk("bob@example.com", "Bob"); h._cache["openrouter_key"] = "k"; image.ENABLED = True
        self.orig = image.urllib.request.urlopen

    def tearDown(self): image.urllib.request.urlopen = self.orig

    def run_with(self, resp):
        image.urllib.request.urlopen = lambda req, timeout=0: resp
        return image.make(h._users.get_item(Key={"email": "bob@example.com"})["Item"], {"prompt": "a river at dawn"})

    def test_picture_cost_and_limit(self):
        st, r = self.run_with(answer()); self.assertEqual(st, 200); self.assertTrue(r["image"].startswith("data:image/jpeg")); self.assertEqual((r["usd"], r["left_today"]), (0.034, image.USER_DAILY - 1))
        self.assertAlmostEqual(float(h._songs.get_item(Key={"owner": "quota#image", "id": image._day()})["Item"]["usd"]), 0.034)
        for _ in range(image.USER_DAILY - 1): self.run_with(answer())
        with self.assertRaises(h.ApiError) as c: self.run_with(answer())
        self.assertEqual(c.exception.status, 429)

    def test_no_picture_is_an_error_but_the_charge_is_counted_and_the_try_is_given_back(self):
        with self.assertRaises(h.ApiError) as c: self.run_with(answer(url=""))
        self.assertEqual(c.exception.status, 502); self.assertAlmostEqual(float(h._songs.get_item(Key={"owner": "quota#image", "id": image._day()})["Item"]["usd"]), 0.034)
        self.assertEqual(int(h._users.get_item(Key={"email": "bob@example.com"})["Item"].get("img_n", 0)), 0)

    def test_site_cap_off_switch_and_short_prompt(self):
        from decimal import Decimal
        h._songs.put_item(Item={"owner": "quota#image", "id": image._day(), "usd": Decimal(str(image.SITE_DAILY_USD))})
        with self.assertRaises(h.ApiError) as c: self.run_with(answer())
        self.assertEqual(c.exception.status, 429)
        image.ENABLED = False
        with self.assertRaises(h.ApiError) as c: self.run_with(answer())
        self.assertEqual(c.exception.status, 503); image.ENABLED = True
        with self.assertRaises(h.ApiError) as c: image.make(self.u, {"prompt": "a"})
        self.assertEqual(c.exception.status, 400)
        self.assertEqual(image.info(self.u)[1]["left_today"], image.USER_DAILY)


if __name__ == "__main__":
    unittest.main(verbosity=0)
