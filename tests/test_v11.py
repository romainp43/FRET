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

    def test_temperature_range_stored_in_shipment(self):
        body = {"origin": "Lyon", "destination": "Paris", "mode": "FTL", "pallets": 20, "weight_kg": 12000,
                "pickup_date": (date.today() + timedelta(days=2)).isoformat(), "options": {"temperature": True},
                "temperature_range": "-18 °C"}
        q = self.post("/api/quote", body)
        stored = self.server.DB_.get_quote(q["quote_id"])
        self.assertEqual(stored["shipment"]["temperature_range"], "-18 °C")
        body["temperature_range"] = "n'importe quoi"
        q2 = self.post("/api/quote", body)
        self.assertNotIn("temperature_range", self.server.DB_.get_quote(q2["quote_id"])["shipment"])

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


class Temperature(unittest.TestCase):
    def test_range_saved_with_quote_option(self):
        import server
        self.assertIn("-18 °C", server.TEMPERATURE_RANGES)


class Questions(unittest.TestCase):
    def q(self, **kw):
        return pricing.build_quote("Lyon", "Paris", "LTL", 4, 1200, {}, date.today() + timedelta(days=2), None, **kw)

    def test_stackable_low_pallets_cost_less(self):
        self.assertLess(self.q(pallet_height_cm=100, stackable=True).price_ht, self.q(pallet_height_cm=100, stackable=False).price_ht)

    def test_tall_pallets_get_no_discount_and_oversize_refused(self):
        self.assertEqual(self.q(pallet_height_cm=150, stackable=True).price_ht, self.q(pallet_height_cm=150).price_ht)
        with self.assertRaises(pricing.QuoteError):
            self.q(pallet_height_cm=250)
        with self.assertRaises(pricing.QuoteError):
            self.q(pallet_height_cm=5)

    def test_adr_requires_class_and_un_through_api(self):
        import server
        httpd = server.make_server("127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        server.RL_QUOTE.hits.clear(); server.RL_GLOBAL.hits.clear()
        body = {"origin": "Lyon", "destination": "Paris", "mode": "LTL", "pallets": 2, "weight_kg": 800,
                "pickup_date": (date.today() + timedelta(days=2)).isoformat(), "options": {"adr": True}}

        def post(b):
            req = urllib.request.Request(base + "/api/quote", method="POST", data=json.dumps(b).encode(), headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            self.assertEqual(post(body)[0], 422)
            self.assertEqual(post(dict(body, adr_class="3", adr_un="12"))[0], 422)
            st, q = post(dict(body, adr_class="3", adr_un="1263"))
            self.assertEqual(st, 200)
            self.assertEqual(server.DB_.get_quote(q["quote_id"])["shipment"]["adr_un"], "1263")
        finally:
            httpd.shutdown()


class SendQuote(unittest.TestCase):
    def test_send_quote_by_email(self):
        import server
        server.RL_FORM.hits.clear(); server.RL_QUOTE.hits.clear(); server.RL_GLOBAL.hits.clear(); server.RL_SENDQUOTE_ADDR.hits.clear()
        httpd = server.make_server("127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        def post(path, b):
            req = urllib.request.Request(base + path, method="POST", data=json.dumps(b).encode(), headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            st, q = post("/api/quote", {"origin": "Lyon", "destination": "Paris", "mode": "FTL", "pallets": 20, "weight_kg": 9000,
                                        "pickup_date": (date.today() + timedelta(days=2)).isoformat(), "options": {}})
            self.assertEqual(st, 200)
            self.assertEqual(post("/api/quote/send", {"quote_id": q["quote_id"], "email": "pas-un-mail"})[0], 422)
            self.assertEqual(post("/api/quote/send", {"quote_id": "inconnu123456", "email": "a@b.fr"})[0], 404)
            self.assertEqual(post("/api/quote/send", {"quote_id": q["quote_id"], "email": "client@exemple.fr"})[0], 200)
            queued = [m for m in server.DB_.queued_mails() if m["to_addr"] == "client@exemple.fr"]
            self.assertTrue(queued)
            self.assertIn("#devis=" + q["quote_id"], queued[-1]["body"])
            for _ in range(3):
                last = post("/api/quote/send", {"quote_id": q["quote_id"], "email": "client@exemple.fr"})[0]
            self.assertEqual(last, 429)
        finally:
            httpd.shutdown()


class Outcomes(unittest.TestCase):
    def test_report_small_sample_is_indicative(self):
        from fretrau import outcomes
        rows = [{"customer_price_ht": 1000, "actual_cost_ht": 850, "carrier_price": 800, "on_time": 1, "carrier_id": 1, "carrier_name": "A"},
                {"customer_price_ht": 900, "actual_cost_ht": 880, "carrier_price": 800, "on_time": 0, "carrier_id": 1, "carrier_name": "A"}]
        r = outcomes.report(rows)
        self.assertTrue(r["indicative_only"])
        self.assertEqual(r["realized_margin_ht"], 170.0)
        self.assertEqual(r["on_time_rate"], 0.5)
        self.assertEqual(r["cost_vs_negotiated_pct"], 8.1)
        self.assertEqual(outcomes.report([])["count"], 0)

    def test_route_disk_cache_roundtrip(self):
        import tempfile
        from fretrau import routing
        with tempfile.TemporaryDirectory() as d:
            routing.CACHE_FILE = os.path.join(d, "r.json")
            routing._cache.clear()
            routing._cache[("A", "B")] = (123.4, "osrm")
            routing._cache[("C", "D")] = (50.0, "estimation")
            routing._save_disk()
            routing._cache.clear()
            routing._load_disk()
            self.assertEqual(routing._cache, {("A", "B"): (123.4, "osrm")})
            routing._cache.clear()

    def test_db_outcome_roundtrip(self):
        os.environ.setdefault("FRETRAU_DB", ":memory:")
        from fretrau.db import DB
        from fretrau import outcomes
        db = DB(":memory:")
        db.save_booking(tracking_code="FR-AAAAAAAAAAAA", quote_id="q", status="confirmed",
                        customer={"name": "T", "company": "T", "email": "t@t.fr", "phone": "0600000000"},
                        shipment={"origin": "Lyon", "destination": "Paris", "mode": "FTL"},
                        customer_price_ht=1000.0, agent_log={}, carrier_id=1, carrier_name="Rhône Fret", carrier_price=800.0)
        b = db.booking_by_code("FR-AAAAAAAAAAAA")
        db.record_outcome(b["id"], 820.0, True, "RAS", "admin")
        db.record_outcome(b["id"], 830.0, False, "retard 2 h", "admin")       # correction : remplace, pas de doublon
        rows = db.list_outcomes()
        self.assertEqual(len(rows), 1)
        r = outcomes.report(rows)
        self.assertEqual(r["realized_margin_ht"], 170.0)
        self.assertEqual(r["on_time_rate"], 0.0)
