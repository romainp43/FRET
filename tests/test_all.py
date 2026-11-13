import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["FRETRAU_DB"] = ":memory:"
os.environ["FRETRAU_ADMIN_PASSWORD"] = "mot-de-passe-de-test-long"

from fretrau import pricing, security, booking  # noqa: E402
from fretrau.agents import compliance, sourcing, negotiation  # noqa: E402
from fretrau.carriers import CARRIERS  # noqa: E402

PICKUP = date.today() + timedelta(days=3)


class TestPricing(unittest.TestCase):
    def test_ftl_basic(self):
        q = pricing.build_quote("Lyon", "Paris", "FTL", 33, 18000)
        self.assertGreater(q.price_ht, q.carrier_cost_estimate)
        self.assertAlmostEqual(q.price_ttc, q.price_ht * 1.2, places=1)   # TVA 20 % en national

    def test_international_no_vat(self):
        q = pricing.build_quote("Lyon", "Milan", "FTL", 33, 18000)
        self.assertEqual(q.vat, 0.0)

    def test_options_increase_price(self):
        base = pricing.build_quote("Lyon", "Paris", "LTL", 4, 1200)
        adr = pricing.build_quote("Lyon", "Paris", "LTL", 4, 1200, {"adr": True, "urgent": True})
        self.assertGreater(adr.price_ht, base.price_ht)

    def test_rejects_bad_input(self):
        for args in [("Lyon", "Lyon", "FTL", 10, 1000), ("Lyon", "Atlantis", "FTL", 10, 1000),
                     ("Lyon", "Paris", "XXX", 10, 1000), ("Lyon", "Paris", "FTL", 10, 99999),
                     ("Lyon", "Paris", "LTL", 0, 100), ("Lyon", "Paris", "LTL", 2, 5000)]:
            with self.assertRaises(pricing.QuoteError):
                pricing.build_quote(*args)


class TestAgents(unittest.TestCase):
    def test_compliance_excludes_bad_carriers(self):
        q = pricing.build_quote("Paris", "Lyon", "FTL", 33, 18000)
        ranked, rejected = sourcing.rank(q, PICKUP)
        names = {r["carrier"] for r in ranked}
        self.assertFalse(any("Expirée" in n or "Sans Licence" in n or "Liste Noire" in n for n in names))
        self.assertGreaterEqual(len(rejected), 3)

    def test_international_needs_europe_flag(self):
        q = pricing.build_quote("Lyon", "Milan", "FTL", 33, 18000)
        ranked, _ = sourcing.rank(q, PICKUP, top_n=20)
        europe_ids = {c.id for c in CARRIERS if c.europe}
        self.assertTrue(all(r["carrier_id"] in europe_ids for r in ranked))

    def test_negotiation_never_exceeds_ceiling(self):
        for o, d, mode in [("Lyon", "Paris", "FTL"), ("Lille", "Marseille", "FTL"), ("Nantes", "Bordeaux", "LTL")]:
            q = pricing.build_quote(o, d, mode, 10, 3000)
            ranked, _ = sourcing.rank(q, PICKUP)
            by_id = {c.id: c for c in CARRIERS}
            for cand in ranked:
                r = negotiation.negotiate(q, cand, by_id[cand["carrier_id"]])
                if r["accepted"]:
                    self.assertLessEqual(r["price"], r["ceiling"] + 0.01)
                    self.assertGreaterEqual(r["margin_pct"], pricing.MIN_MARGIN * 100 - 0.5)
                else:
                    self.assertTrue(r["escalate_to_human"])

    def test_booking_confirms(self):
        from dataclasses import asdict
        q = pricing.build_quote("Lyon", "Paris", "FTL", 33, 18000)
        res = booking.run(asdict(q), PICKUP)
        self.assertEqual(res["status"], "confirmed")
        self.assertIsNotNone(res["carrier"])

    def test_llm_cannot_change_price(self):
        from fretrau.agents import llm
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertEqual(llm.draft("x", {"price_text": "10 €"}, "repli"), "repli")


class TestSecurity(unittest.TestCase):
    def test_password(self):
        h = security.hash_password("abc12345678")
        self.assertTrue(security.verify_password("abc12345678", h))
        self.assertFalse(security.verify_password("autre", h))

    def test_session_tamper(self):
        s = security.Sessions(b"secret")
        t = s.issue("admin")
        self.assertEqual(s.verify(t), "admin")
        self.assertIsNone(s.verify(t[:-1] + ("0" if t[-1] != "0" else "1")))
        self.assertIsNone(security.Sessions(b"autre").verify(t))

    def test_rate_limiter(self):
        rl = security.RateLimiter(3, 60)
        self.assertEqual([rl.allow("ip") for _ in range(5)], [True, True, True, False, False])

    def test_login_guard(self):
        g = security.LoginGuard(max_fail=2, lock_s=60)
        g.fail("ip"); g.fail("ip")
        self.assertTrue(g.locked("ip"))


class TestServer(unittest.TestCase):
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

    def call(self, method, path, body=None, headers=None, raw=False):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, method=method, headers=h,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                data = r.read()
                return r.status, (data if raw else json.loads(data)), r.headers
        except urllib.error.HTTPError as e:
            data = e.read()
            return e.code, (data if raw else json.loads(data)), e.headers

    def quote_body(self, **kw):
        b = {"origin": "Lyon", "destination": "Paris", "mode": "FTL", "pallets": 33, "weight_kg": 15000,
             "pickup_date": PICKUP.isoformat(), "options": {}}
        b.update(kw)
        return b

    def booking_body(self, quote_id, **kw):
        b = {"quote_id": quote_id, "accept_cgv": True, "pickup_address": "1 rue Test, Lyon",
             "delivery_address": "2 avenue Demo, Paris", "goods": "Palettes <b>de test</b>",
             "contact": {"name": "Jean Test", "company": "Test SAS", "email": "jean@test.fr", "phone": "0612345678"}}
        b.update(kw)
        return b

    def test_security_headers(self):
        status, _, headers = self.call("GET", "/api/cities")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertNotIn("Python", headers.get("Server", ""))

    def test_path_traversal_blocked(self):
        for p in ["/../server.py", "/..%2fserver.py", "/%2e%2e/server.py", "/fretrau.db"]:
            status, _, _ = self.call("GET", p)
            self.assertEqual(status, 404, p)

    def test_end_to_end(self):
        s, q, _ = self.call("POST", "/api/quote", self.quote_body())
        self.assertEqual(s, 200)
        self.assertNotIn("carrier_cost_estimate", q)
        s, b, _ = self.call("POST", "/api/book", self.booking_body(q["quote_id"]))
        self.assertEqual(s, 201, b)
        self.assertEqual(b["status"], "confirmed")
        s, t, _ = self.call("GET", "/api/track/" + b["tracking_code"])
        self.assertEqual(s, 200)
        self.assertTrue(t["events"][0]["done"])
        s, doc, _ = self.call("GET", "/api/doc/" + b["tracking_code"], raw=True)
        self.assertEqual(s, 200)
        self.assertNotIn(b"<b>de test</b>", doc)            # XSS échappé
        self.assertIn(b"&lt;b&gt;", doc)
        s, _, _ = self.call("POST", "/api/book", self.booking_body(q["quote_id"]))
        self.assertEqual(s, 409)                            # double réservation refusée

    def test_validation(self):
        s, _, _ = self.call("POST", "/api/quote", self.quote_body(origin="Atlantis"))
        self.assertEqual(s, 422)
        s, _, _ = self.call("POST", "/api/quote", self.quote_body(pickup_date="2001-01-01"))
        self.assertEqual(s, 422)
        s, _, _ = self.call("POST", "/api/quote", self.quote_body(weight_kg=True))
        self.assertEqual(s, 422)
        s, _, _ = self.call("POST", "/api/quote", self.quote_body(), headers={"Content-Type": "text/plain"})
        self.assertEqual(s, 415)

    def test_honeypot_and_cgv(self):
        _, q, _ = self.call("POST", "/api/quote", self.quote_body())
        s, r, _ = self.call("POST", "/api/book", self.booking_body(q["quote_id"], website="http://spam"))
        self.assertEqual(s, 200)
        self.assertNotIn("tracking_code", r)
        s, _, _ = self.call("POST", "/api/book", self.booking_body(q["quote_id"], accept_cgv=False))
        self.assertEqual(s, 422)

    def test_unknown_tracking(self):
        s, _, _ = self.call("GET", "/api/track/FR-000000000000")
        self.assertEqual(s, 404)
        s, _, _ = self.call("GET", "/api/track/1%27%20OR%20%271%27%3D%271")
        self.assertEqual(s, 404)

    def test_admin_requires_auth(self):
        s, _, _ = self.call("GET", "/api/admin/bookings", headers={"X-Requested-With": "fretrau"})
        self.assertEqual(s, 401)
        s, _, _ = self.call("POST", "/api/admin/login", {"user": "admin", "password": "mauvais"})
        self.assertEqual(s, 401)

    def test_admin_login_and_view(self):
        s, _, headers = self.call("POST", "/api/admin/login",
                                  {"user": "admin", "password": "mot-de-passe-de-test-long"})
        self.assertEqual(s, 200)
        cookie = headers["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        h = {"Cookie": cookie, "X-Requested-With": "fretrau"}
        s, data, _ = self.call("GET", "/api/admin/bookings", headers=h)
        self.assertEqual(s, 200)
        s, st, _ = self.call("GET", "/api/admin/stats", headers=h)
        self.assertEqual(s, 200)
        # cookie seul sans l'en-tête anti-CSRF : refusé
        s, _, _ = self.call("GET", "/api/admin/bookings", headers={"Cookie": cookie})
        self.assertEqual(s, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
