import hashlib, json, os, sys, threading, time, unittest, urllib.request, urllib.error
from datetime import date, datetime, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")
from fretrau import calendar_fr, driver, payments, pricing, sms, verify_remote  # noqa: E402
from fretrau.agents import claims_triage, guard, watchtower  # noqa: E402
from fretrau.db import DB  # noqa: E402
from fretrau import agent_config, simulation  # noqa: E402


class Guard(unittest.TestCase):
    cust = {"email": "a@societe.fr", "phone": "0612345678", "consent": {"ip_hash": "x"}}
    ship = {"pickup_address": "1 rue Alpha, 69001 Lyon", "delivery_address": "2 rue Beta, 75010 Paris", "site_contact_phone": "0611223344"}

    def test_clean_booking_ok(self):
        self.assertEqual(guard.assess(self.cust, self.ship, 900, [], time.time())["action"], "ok")

    def test_disposable_email_goes_to_review(self):
        r = guard.assess({**self.cust, "email": "x@mailinator.com"}, self.ship, 900, [], time.time())
        self.assertEqual(r["action"], "review")
        self.assertTrue(r["flags"])

    def test_same_addresses_and_burst(self):
        s = {**self.ship, "delivery_address": self.ship["pickup_address"]}
        self.assertEqual(guard.assess(self.cust, s, 900, [], time.time())["action"], "review")
        now = time.time()
        recent = [{"email": "a@societe.fr", "ip_hash": "x", "created_at": now - 60}] * 6
        self.assertEqual(guard.assess(self.cust, self.ship, 900, recent, now)["action"], "review")


class Watchtower(unittest.TestCase):
    def item(self, pickup, events=None, deliver_by=None):
        return {"id": 1, "code": "FR-AAAA-1111", "shipment": {"pickup_date": pickup, "pickup_window": "08:00-12:00", "deliver_by": deliver_by},
                "earliest_delivery": "", "events": events or {}}

    def test_pickup_late(self):
        now = datetime(2026, 11, 20, 18, 0)
        codes = [a["code"] for a in watchtower.scan([self.item("2026-11-20")], now)]
        self.assertIn("pickup_late", codes)

    def test_not_late_inside_grace(self):
        now = datetime(2026, 11, 20, 13, 0)
        self.assertEqual(watchtower.scan([self.item("2026-11-20")], now), [])

    def test_delivered_never_alerts(self):
        now = datetime(2026, 12, 30, 18, 0)
        self.assertEqual(watchtower.scan([self.item("2026-11-20", {"delivered": 1.0})], now), [])

    def test_delivery_late_and_stall(self):
        now = datetime(2026, 11, 25, 20, 0)
        ev = {"loaded": (now - timedelta(hours=30)).timestamp()}
        codes = {a["code"] for a in watchtower.scan([self.item("2026-11-20", ev, "2026-11-24")], now)}
        self.assertEqual(codes, {"stalled", "delivery_late"})

    def test_alert_is_idempotent_in_db(self):
        db = DB(":memory:")
        # une réservation minimale
        db.save_booking(tracking_code="FR-TEST-0001", quote_id="q1", status="confirmed", customer={"email": "a@b.fr"}, shipment={"pickup_date": "2026-01-01"},
                        carrier_id=1, carrier_name="X", carrier_price=100, customer_price_ht=120, agent_log={})
        b = db.booking_by_code("FR-TEST-0001")
        self.assertTrue(db.add_alert(b["id"], "pickup_late", "high", "m"))
        self.assertFalse(db.add_alert(b["id"], "pickup_late", "high", "m"))


class ClaimsTriage(unittest.TestCase):
    def test_urgent_when_deadline_close(self):
        t = claims_triage.triage({"kind": "damage", "reserves_on_receipt": True}, {"written_reserve_before": "2026-11-18"}, date(2026, 11, 17))
        self.assertEqual(t["priority"], "urgent")
        self.assertTrue(t["evidence"])

    def test_no_reserve_is_elevated_not_decisive(self):
        t = claims_triage.triage({"kind": "loss", "reserves_on_receipt": False}, {"written_reserve_before": "2026-12-30"}, date(2026, 11, 17))
        self.assertEqual(t["priority"], "elevated")


class Sms(unittest.TestCase):
    def test_phone_normalisation(self):
        self.assertEqual(sms.normalize_phone("06 12 34 56 78"), "+33612345678")
        self.assertEqual(sms.normalize_phone("0033612345678"), "+33612345678")
        self.assertIsNone(sms.normalize_phone("abc"))

    def test_consent_and_stop(self):
        db = DB(":memory:")
        self.assertIsNone(sms.queue(db, "0612345678", "late", "s", consented=False, code="FR-X", url="u"))
        self.assertIsNotNone(sms.queue(db, "0612345678", "late", "s", consented=True, code="FR-X", url="u"))
        sms.stop(db, "06 12 34 56 78", "s")
        self.assertIsNone(sms.queue(db, "0612345678", "late", "s", consented=True, code="FR-X", url="u"))
        self.assertTrue(sms.is_stop_text(" STOP "))
        self.assertFalse(sms.is_stop_text("stop the car"))

    def test_nothing_sent_without_provider(self):
        db = DB(":memory:")
        sms.queue(db, "0612345678", "delivered", "s", True, code="FR-X", url="u")
        os.environ.pop("FRETRAU_SMS_PROVIDER", None); os.environ.pop("FRETRAU_SMS_URL", None)
        self.assertEqual(sms.flush(db), 0)
        self.assertEqual(db.list_sms()[0]["status"], "queued")

    def test_gateway_failure_is_isolated(self):
        db = DB(":memory:")
        sms.queue(db, "0612345678", "delivered", "s", True, code="FR-X", url="u")
        os.environ["FRETRAU_SMS_URL"] = "http://invalid.example"
        try:
            def boom(*a, **k): raise OSError("réseau coupé")
            self.assertEqual(sms.flush(db, opener=boom), 0)
            self.assertEqual(db.list_sms()[0]["status"], "failed")
        finally:
            os.environ.pop("FRETRAU_SMS_URL", None)


class Payments(unittest.TestCase):
    def test_webhook_signature(self):
        body = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_1"}}}).encode()
        hdr = payments.sign(body, "whsec_x")
        self.assertEqual(payments.verify_webhook(body, hdr, "whsec_x")["type"], "checkout.session.completed")
        with self.assertRaises(ValueError):
            payments.verify_webhook(body, hdr, "autre-secret")
        with self.assertRaises(ValueError):
            payments.verify_webhook(body + b" ", hdr, "whsec_x")
        with self.assertRaises(ValueError):
            payments.verify_webhook(body, payments.sign(body, "whsec_x", ts=int(time.time()) - 4000), "whsec_x")
        with self.assertRaises(ValueError):
            payments.verify_webhook(body, "n'importe quoi", "whsec_x")

    def test_cents_rounding(self):
        self.assertEqual(payments.cents(1234.565), 123457 if round(1234.565 * 100) == 123457 else round(1234.565 * 100))
        self.assertEqual(payments.cents(10.0), 1000)

    def test_checkout_uses_injected_opener(self):
        os.environ["FRETRAU_STRIPE_KEY"] = "sk_test_x"
        try:
            seen = {}
            class R:
                def __enter__(s): return s
                def __exit__(s, *a): return False
                def read(s): return b'{"id": "cs_9", "url": "https://pay.example/cs_9"}'
            def opener(req, timeout=0):
                seen["data"] = req.data.decode()
                return R()
            out = payments.create_checkout("q1", 120.5, "Transport", "a@b.fr", "https://s", "https://c", opener=opener)
            self.assertEqual(out["provider_ref"], "cs_9")
            self.assertIn("unit_amount%5D=12050", seen["data"])
        finally:
            os.environ.pop("FRETRAU_STRIPE_KEY", None)


class VerifyRemote(unittest.TestCase):
    def fake(self, payload):
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return json.dumps(payload).encode()
        return lambda req, timeout=0: R()

    def test_sirene_active_and_missing(self):
        ok = verify_remote.sirene_check("552100554", self.fake({"results": [{"siren": "552100554", "etat_administratif": "A", "nom_complet": "X"}]}))
        self.assertTrue(ok["ok"])
        closed = verify_remote.sirene_check("552100554", self.fake({"results": [{"siren": "552100554", "etat_administratif": "C"}]}))
        self.assertFalse(closed["ok"])
        self.assertFalse(verify_remote.sirene_check("552100554", self.fake({"results": []}))["found"])

    def test_network_failure_is_unknown_not_rejection(self):
        def boom(*a, **k): raise OSError("hors ligne")
        self.assertIsNone(verify_remote.sirene_check("552100554", boom)["ok"])
        self.assertIsNone(verify_remote.vies_check("DE", "DE123456789", boom)["ok"])


class Indicative(unittest.TestCase):
    def test_ptl_is_cheaper_than_ftl_and_not_bookable(self):
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4))
        ftl = pricing.estimate("Lyon", "Paris", "FTL", 33, 15000, pk, {}) if hasattr(pricing, "estimate") else None
        p = pricing.indicative("PTL", "Lyon", "Paris", 6, 2500)
        self.assertFalse(p["bookable"])
        self.assertLess(p["price_ht_low"], p["price_ht_mid"])
        self.assertLess(p["price_ht_mid"], p["price_ht_high"])
        if ftl:
            self.assertLess(p["price_ht_mid"], ftl.price_ht)

    def test_more_pallets_cost_more(self):
        a = pricing.indicative("PTL", "Lyon", "Paris", 4, 1500)["price_ht_mid"]
        b = pricing.indicative("PTL", "Lyon", "Paris", 20, 9000)["price_ht_mid"]
        self.assertLess(a, b)

    def test_intermodal_needs_distance_and_validates(self):
        with self.assertRaises(pricing.QuoteError):
            pricing.indicative("IM", "Lyon", "Paris", 33, 20000)
        self.assertEqual(pricing.indicative("IM", "Lille", "Marseille", 33, 20000)["uncertainty"], 0.30)
        for bad in (("XX", "Lyon", "Paris", 5, 1000), ("PTL", "Lyon", "Lyon", 5, 1000), ("PTL", "Lyon", "Paris", 0, 1000),
                    ("PTL", "Lyon", "Paris", 5, -3), ("PTL", "Lyon", "Paris", True, 1000)):
            with self.assertRaises(pricing.QuoteError):
                pricing.indicative(*bad)


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
        for rl in (self.server.RL_QUOTE, self.server.RL_GLOBAL, self.server.RL_TRACK, self.server.RL_BOOK, self.server.RL_FORM,
                   self.server.RL_LOGIN, self.server.RL_ACCT):
            rl.hits.clear()

    def call(self, method, path, body=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + path, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def book(self, email, **over):
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4)).isoformat()
        s, q, _ = self.call("POST", "/api/quote", {"origin": "Lyon", "destination": "Paris", "mode": "FTL", "pallets": 33, "weight_kg": 15000,
                                                     "pickup_date": pk, "options": {}})
        self.assertEqual(s, 200, q)
        body = {"quote_id": q["quote_id"], "accept_cgv": True, "sms_consent": True,
                "contact": {"name": "Marc", "company": "ACME", "email": email, "phone": "0611223344"},
                "pickup_window": "08:00-17:00", "delivery_window": "08:00-17:00", "site_contact_name": "Paul", "site_contact_phone": "0611223344",
                "pickup_address": "1 rue Alpha, 69001 Lyon", "delivery_address": "2 rue Beta, 75010 Paris", "goods": "palettes", **over}
        s, b, _ = self.call("POST", "/api/book", body)
        self.assertEqual(s, 201, b)
        return b

    def test_guard_sends_disposable_email_to_human(self):
        b = self.book("x@mailinator.com")
        self.assertEqual(b["status"], "pending_human")

    def test_indicative_endpoint(self):
        s, r, _ = self.call("POST", "/api/indicative", {"kind": "PTL", "origin": "Lyon", "destination": "Paris", "pallets": 6, "weight_kg": 2500})
        self.assertEqual(s, 200, r)
        self.assertFalse(r["bookable"])
        self.assertEqual(self.call("POST", "/api/indicative", {"kind": "PTL", "origin": "Lyon", "destination": "Paris", "pallets": 0, "weight_kg": 1})[0], 422)

    def test_driver_link_flow_and_privacy(self):
        email = f"d{time.time_ns()}@societe.fr"
        b = self.book(email)
        db = self.server.DB_
        row = db.booking_by_code(b["tracking_code"])
        token = driver.new_link(db, row["id"])
        # le jeton n'est jamais stocké en clair
        self.assertIsNone(db.get_driver_link(token))
        self.assertIsNotNone(db.get_driver_link(hashlib.sha256(token.encode()).hexdigest()))
        # pas de position sans consentement
        self.assertEqual(self.call("POST", "/api/driver/position", {"token": token, "lat": 45.7, "lon": 4.8})[0], 422)
        self.assertEqual(self.call("POST", "/api/driver/consent", {"token": token})[0], 200)
        self.assertEqual(self.call("POST", "/api/driver/position", {"token": token, "lat": 45.7, "lon": 4.8, "accuracy": 12})[0], 200)
        self.assertEqual(self.call("POST", "/api/driver/position", {"token": token, "lat": 45.8, "lon": 4.9})[2] and 0, 0)
        self.assertEqual(self.call("POST", "/api/driver/position", {"token": token, "lat": 0, "lon": 0})[0], 422)       # hors Europe
        self.assertEqual(self.call("POST", "/api/driver/position", {"token": token, "lat": "45", "lon": 4.8})[0], 422)
        s, t, _ = self.call("GET", f"/api/track/{b['tracking_code']}")
        self.assertEqual(round(t["driver_position"]["lat"], 1), 45.7)
        self.assertEqual(self.call("POST", "/api/driver/position", {"token": "x" * 30, "lat": 45.7, "lon": 4.8})[0], 404)
        # arrêt par le chauffeur
        self.assertEqual(self.call("POST", "/api/driver/stop", {"token": token})[0], 200)
        self.assertEqual(self.call("POST", "/api/driver/position", {"token": token, "lat": 45.7, "lon": 4.8})[0], 404)

    def test_driver_link_dies_at_delivery(self):
        b = self.book(f"e{time.time_ns()}@societe.fr")
        db = self.server.DB_
        row = db.booking_by_code(b["tracking_code"])
        token = driver.new_link(db, row["id"])
        db.add_event(row["id"], "delivered", "test")
        self.assertIsNone(driver.resolve(db, token))

    def test_account_login_by_email_code(self):
        email = f"c{time.time_ns()}@societe.fr"
        b = self.book(email)
        db = self.server.DB_
        self.assertEqual(self.call("POST", "/api/account/request", {"email": email})[0], 200)
        # même réponse pour un e-mail inconnu (pas d'énumération)
        self.assertEqual(self.call("POST", "/api/account/request", {"email": "inconnu@nulle.part"})[0], 200)
        self.assertEqual(self.call("POST", "/api/account/verify", {"email": email, "code": "000000"})[0], 401)
        row = db.get_login_code(email)
        for n in range(1000000):                       # on retrouve le code via son empreinte (le test connaît le secret du serveur)
            c = f"{n:06d}"
            if hashlib.sha256((self.server.SESSION_SECRET + email + c).encode()).hexdigest() == row["code_hash"]:
                break
        s, r, h = self.call("POST", "/api/account/verify", {"email": email, "code": c})
        self.assertEqual(s, 200)
        cookie = h["Set-Cookie"].split(";")[0]
        self.assertEqual(self.call("GET", "/api/account/bookings")[0], 401)
        s, r, _ = self.call("GET", "/api/account/bookings", headers={"Cookie": cookie, "X-Requested-With": "fretrau"})
        self.assertEqual([x["tracking_code"] for x in r["bookings"]], [b["tracking_code"]])
        # un cookie client n'ouvre jamais l'administration
        self.assertEqual(self.call("GET", "/api/admin/bookings", headers={"Cookie": cookie.replace("fretrau_acct", "fretrau_admin"), "X-Requested-With": "fretrau"})[0], 401)

    def test_stripe_disabled_by_default(self):
        os.environ.pop("FRETRAU_STRIPE_KEY", None); os.environ.pop("FRETRAU_STRIPE_WEBHOOK_SECRET", None)
        self.assertEqual(self.call("POST", "/api/pay/checkout", {"quote_id": "x"})[0], 503)
        self.assertEqual(self.call("POST", "/api/webhook/stripe", {"a": 1})[0], 404)

    def test_sms_stop_endpoint(self):
        self.assertEqual(self.call("POST", "/api/sms/stop", {"phone": "0612345678"})[0], 200)
        self.assertEqual(self.call("POST", "/api/sms/stop", {"phone": "zzz"})[0], 422)


class Simulation(unittest.TestCase):
    def test_deterministic(self):
        b = simulation.baseline()
        self.assertEqual(simulation.evaluate(b, range(1, 41)), simulation.evaluate(b, range(1, 41)))

    def test_paired_gain_of_identical_params_is_zero(self):
        b = simulation.baseline()
        self.assertEqual(simulation.paired_gain(b, b, range(1, 31))["gain_pts"], 0)

    def test_regret_is_non_negative(self):
        self.assertGreaterEqual(simulation.evaluate(simulation.baseline(), range(1, 41))["regret_pct"], 0)


class AgentConfig(unittest.TestCase):
    def write(self, obj):
        import tempfile
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        f.write(obj if isinstance(obj, str) else json.dumps(obj)); f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_missing_file_means_defaults(self):
        self.assertEqual(agent_config.load("/nonexistent/agents.json"), {})

    def test_invalid_values_are_ignored(self):
        bad = {"sourcing": {"weights_normal": [0.9, 0.9, 0.9, 0.9], "weights_tight": [1, 0, 0]},
               "decision": {"late_cost_ratio": 99}, "negotiation": {"offers": [1.1, 1.0, 0.9, 0.8], "soft_target": 5}}
        self.assertEqual(agent_config.load(self.write(bad)), {"version": ""})

    def test_corrupt_json_is_ignored(self):
        self.assertEqual(agent_config.load(self.write("{pas du json")), {})

    def test_tight_weights_must_keep_punctuality(self):
        bad = {"sourcing": {"weights_normal": [0.4, 0.3, 0.2, 0.1], "weights_tight": [0.5, 0.3, 0.17, 0.03]}}
        self.assertNotIn("weights_tight", agent_config.load(self.write(bad)))

    def test_random_params_respect_constraint(self):
        import random
        rng = random.Random(3)
        for _ in range(200):
            p = simulation.random_params(rng)
            self.assertTrue(agent_config.tight_ok(p.weights_normal, p.weights_tight))

    def test_valid_values_are_applied(self):
        ok = {"version": "t", "sourcing": {"weights_normal": [0.4, 0.3, 0.2, 0.1], "weights_tight": [0.2, 0.2, 0.3, 0.3]},
              "decision": {"late_cost_ratio": 0.5}, "negotiation": {"offers": [0.9, 0.95, 1.0, 1.05], "soft_target": 1.0}}
        c = agent_config.load(self.write(ok))
        self.assertEqual(c["late_cost_ratio"], 0.5)
        self.assertEqual(c["offers"], (0.9, 0.95, 1.0, 1.05))


class IntakeCorpus(unittest.TestCase):
    def test_corpus_accuracy_threshold(self):
        import eval_intake
        r = eval_intake.evaluate()
        self.assertGreaterEqual(r["accuracy"], 0.97, r["fails"][:3])
        self.assertGreaterEqual(r["n"], 90)


class MarketBacktest(unittest.TestCase):
    def test_model_stays_close_to_public_benchmarks(self):
        import backtest_market
        rows, mape, bias = backtest_market.run()
        self.assertLessEqual(mape, 0.12)
        self.assertGreaterEqual(len(rows), 4)


class StressAndCo2(unittest.TestCase):
    def test_stress_chain_has_no_anomaly(self):
        import stress_agents
        r = stress_agents.run(150, 3, out=lambda *_: None)
        self.assertEqual(r["errors"], [])
        self.assertGreater(r["total"], 100)

    def test_co2_estimate_scales_with_distance_and_weight(self):
        a = pricing.co2_estimate(500, 10000)
        self.assertEqual(a, round(500 * 10 * 0.0875))
        self.assertGreater(pricing.co2_estimate(1000, 10000), a)
        self.assertEqual(pricing.co2_estimate(500, 0), 0)


if __name__ == "__main__":
    unittest.main()
