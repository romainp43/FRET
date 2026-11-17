import json, os, sys, threading, unittest, urllib.request, urllib.error
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")
from fretrau import pricing  # noqa: E402


class Options(unittest.TestCase):
    def quote(self, **opts):
        return pricing.build_quote("Lyon", "Paris", "LTL", 4, 1800, opts, date.today() + timedelta(days=2), None)

    def test_new_options_add_fixed_fee(self):
        base = self.quote()
        rdv = self.quote(appointment=True)
        part = self.quote(residential=True)
        self.assertGreater(rdv.price_ht, base.price_ht)
        self.assertGreater(part.price_ht, base.price_ht)
        self.assertIn("rendez_vous", rdv.breakdown)
        self.assertIn("particulier", part.breakdown)


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        for rl in (self.server.RL_QUOTE, self.server.RL_GLOBAL, self.server.RL_TRACK):
            rl.hits.clear()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, method="POST", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_alternative_formula_is_retrievable(self):
        body = {"origin": "Lyon", "destination": "Paris", "mode": "LTL", "pallets": 4, "weight_kg": 1800,
                "pickup_date": (date.today() + timedelta(days=2)).isoformat(), "options": {}}
        q = self.post("/api/quote", body)
        self.assertTrue(q["alternatives"])
        alt = q["alternatives"][0]
        self.assertEqual(alt["label"], "Express")
        self.assertGreater(alt["price_ht"], q["price_ht"])
        with urllib.request.urlopen(self.base + "/api/quote/" + alt["quote_id"]) as r:
            self.assertEqual(json.loads(r.read())["price_ht"], alt["price_ht"])

    def test_friendly_404_for_browsers_and_json_for_api(self):
        req = urllib.request.Request(self.base + "/n-existe-pas", headers={"Accept": "text/html"})
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(req)
        self.assertEqual(c.exception.code, 404)
        self.assertIn(b"n'existe pas", c.exception.read())

    def test_robots_and_assets(self):
        for p, ct in (("/robots.txt", "text/plain"), ("/logo-mark.svg", "image/svg+xml"), ("/camion.svg", "image/svg+xml")):
            with urllib.request.urlopen(self.base + p) as r:
                self.assertEqual(r.status, 200)
                self.assertIn(ct, r.headers["Content-Type"])


if __name__ == "__main__":
    unittest.main()
