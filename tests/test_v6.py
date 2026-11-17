import hashlib, hmac, json, os, sys, threading, time, unittest, urllib.request, urllib.error
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")
os.environ["FRETRAU_WEBHOOK_SECRET"] = os.environ.get("FRETRAU_WEBHOOK_SECRET", "secret-webhook-de-test")
from fretrau import pricing, calendar_fr  # noqa: E402
from fretrau.agents import intake, ratematch  # noqa: E402

TODAY = date(2026, 11, 17)   # mardi


class Intake(unittest.TestCase):
    def p(self, t):
        return intake.parse(t, TODAY)

    def test_french_ftl_email(self):
        r = self.p("Bonjour, il me faut un camion complet de Lyon à Paris, 18 tonnes, enlèvement le 24/11/2026. Merci")
        f = r["fields"]
        self.assertTrue(r["complete"], r)
        self.assertEqual((f["origin"], f["destination"], f["mode"]), ("Lyon", "Paris", "FTL"))
        self.assertEqual(f["weight_kg"], 18000)
        self.assertEqual(f["pickup_date"], "2026-11-24")

    def test_ltl_with_pallets_and_options(self):
        r = self.p("Demande de prix : 4 palettes, 1 200 kg, Saint-Etienne → Bordeaux demain, matières dangereuses ADR, hayon")
        f = r["fields"]
        self.assertTrue(r["complete"], r)
        self.assertEqual((f["origin"], f["destination"], f["mode"], f["pallets"], f["weight_kg"]), ("Saint-Etienne", "Bordeaux", "LTL", 4, 1200))
        self.assertEqual(f["pickup_date"], "2026-11-18")
        self.assertTrue(f["options"]["adr"] and f["options"]["tail_lift"])
        self.assertTrue(any("déduit" in a for a in r["assumptions"]))

    def test_accents_case_and_decimal_tonnes(self):
        r = self.p("FROM ORLÉANS TO LE HAVRE, 2,5 t, jeudi, 3 palettes")
        self.assertEqual((r["fields"]["origin"], r["fields"]["destination"], r["fields"]["weight_kg"]), ("Orléans", "Le Havre", 2500))
        self.assertEqual(r["fields"]["pickup_date"], "2026-11-19")

    def test_thousand_separators(self):
        self.assertEqual(self.p("Lyon vers Paris 1.200 kg 2 palettes demain")["fields"]["weight_kg"], 1200)
        self.assertEqual(self.p("Lyon vers Paris 1200kg 2 palettes demain")["fields"]["weight_kg"], 1200)

    def test_never_invents_missing_critical_data(self):
        r = self.p("Bonjour, pouvez-vous me faire un prix de Lyon à Paris ?")
        self.assertFalse(r["complete"])
        self.assertTrue(any("poids" in m for m in r["missing"]))
        self.assertTrue(any("date" in m for m in r["missing"]))
        self.assertNotIn("weight_kg", r["fields"])
        self.assertIn("poids", intake.reply_needing_info(r))

    def test_ambiguous_cities_not_guessed(self):
        r = self.p("Lyon, Paris, Lille : 10 tonnes demain camion complet")
        self.assertFalse(r["complete"])
        self.assertIsNotNone(r["ambiguity"])

    def test_invalid_date_and_past_year_rollover(self):
        self.assertIn("pickup_date", self.p("Lyon à Paris 5 t 05/01 camion complet")["fields"])
        self.assertEqual(self.p("Lyon à Paris 5 t 05/01 camion complet")["fields"]["pickup_date"], "2027-01-05")
        self.assertFalse(self.p("Lyon à Paris 5 t 31/02/2026 camion complet")["complete"])

    def test_aliases_and_new_cities(self):
        r = self.p("Cologne -> Berlin 10 tonnes demain camion complet")
        self.assertEqual((r["fields"]["origin"], r["fields"]["destination"]), ("Cologne", "Berlin"))
        r = self.p("Milano to München 5 t 3 palettes demain")
        self.assertEqual((r["fields"]["origin"], r["fields"]["destination"]), ("Milan", "Munich"))
        r = self.p("de Monistrol-sur-Loire à Lyon, 2 palettes, 800 kg, demain")
        self.assertEqual(r["fields"]["origin"], "Monistrol-sur-Loire")

    def test_ambiguous_valence_is_not_guessed(self):
        r = self.p("Valence vers Lyon 5 t camion complet demain")
        self.assertFalse(r["complete"])
        self.assertIn("ambigu", r["ambiguity"])
        ok = self.p("Valence (Drôme) vers Lyon 5 t camion complet demain")
        self.assertTrue(ok["complete"], ok)
        self.assertEqual(ok["fields"]["origin"], "Valence (Drôme)")
        es = self.p("Valence Espagne vers Lyon 5 t camion complet demain")
        self.assertEqual(es["fields"]["origin"], "Valence (Espagne)")

    def test_two_lanes_in_one_email_rejected(self):
        r = self.p("Lyon -> Paris 5 t demain camion complet ; Lille -> Nantes 3 t jeudi")
        self.assertFalse(r["complete"])
        self.assertIn("Plusieurs trajets", r["ambiguity"])

    def test_garbage_and_injection_safe(self):
        for t in ["", "   ", "<script>alert(1)</script>", "x" * 9000, "'; DROP TABLE quotes; --"]:
            r = self.p(t)
            self.assertFalse(r["complete"])

    def test_extracted_request_prices_correctly(self):
        r = self.p("camion complet de Lyon à Paris, 15 tonnes, le 2026-11-24")
        f = r["fields"]
        q = pricing.build_quote(f["origin"], f["destination"], f["mode"], f.get("pallets"), f["weight_kg"], f["options"], date(2026, 11, 24))
        self.assertGreater(q.price_ht, 0)


class RateMatch(unittest.TestCase):
    def quote(self):
        from dataclasses import asdict
        return asdict(pricing.build_quote("Lyon", "Paris", "FTL", 33, 15000, {}, calendar_fr.next_business_day(date.today() + timedelta(days=4))))

    def test_outcomes(self):
        q = self.quote()
        floor = q["carrier_cost_estimate"] * (1 + pricing.MIN_MARGIN)
        self.assertEqual(ratematch.evaluate(q, q["price_ht"] + 1)["outcome"], "no_action")
        mid = (floor + q["price_ht"]) / 2
        r = ratematch.evaluate(q, mid)
        self.assertEqual((r["outcome"], r["price_ht"]), ("matched", round(mid, 2)))
        comp = q["price_ht"] * 0.905           # dans la zone d'alignement automatique mais sous le plancher
        self.assertLess(comp, floor)
        low = ratematch.evaluate(q, comp)
        self.assertEqual(low["outcome"], "counter")
        self.assertAlmostEqual(low["price_ht"], round(floor, 2), places=2)
        self.assertEqual(ratematch.evaluate(q, q["price_ht"] * 0.85)["outcome"], "needs_human")   # > 10 % sous notre prix
        self.assertEqual(ratematch.evaluate(q, q["price_ht"] * 0.3)["outcome"], "needs_human")

    def test_never_below_minimum_margin(self):
        q = self.quote()
        for comp in [1, q["price_ht"] * 0.5, q["price_ht"] * 0.7, q["price_ht"] * 0.9]:
            r = ratematch.evaluate(q, comp)
            if r["outcome"] in ("matched", "counter"):
                self.assertGreaterEqual(r["price_ht"] / q["carrier_cost_estimate"] - 1, pricing.MIN_MARGIN - 1e-3)

    def test_apply_updates_vat_and_stays_a_valid_quote(self):
        q = self.quote()
        r = {"outcome": "matched", "price_ht": round(q["price_ht"] * 0.95, 2)}
        n = ratematch.apply(q, r)
        self.assertAlmostEqual(n["price_ttc"], n["price_ht"] * 1.2, places=1)
        pricing.Quote(**n)        # reste désérialisable par l'orchestrateur


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
        for rl in (self.server.RL_QUOTE, self.server.RL_GLOBAL, self.server.RL_TRACK, self.server.RL_BOOK):
            rl.hits.clear()

    def call(self, method, path, body=None, headers=None, raw_body=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, method=method, headers=h, data=data)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def signed(self, path, payload):
        payload = dict(payload, ts=time.time())
        raw = json.dumps(payload).encode()
        sig = hmac.new(self.server.WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        return self.call("POST", path, headers={"X-Signature": sig}, raw_body=raw)

    def make_quote(self):
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4)).isoformat()
        s, q = self.call("POST", "/api/quote", {"origin": "Lyon", "destination": "Paris", "mode": "FTL", "pallets": 33,
                                                 "weight_kg": 15000, "pickup_date": pk, "options": {}})
        self.assertEqual(s, 200, q)
        return q

    def test_intake_requires_signature(self):
        s, _ = self.call("POST", "/api/intake/email", {"text": "x", "ts": time.time()}, headers={"X-Signature": "00"})
        self.assertEqual(s, 401)

    def test_intake_quotes_then_view_by_id(self):
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4))
        s, r = self.signed("/api/intake/email", {"text": f"Camion complet Lyon vers Paris, 15 tonnes, le {pk.strftime('%d/%m/%Y')}"})
        self.assertEqual((s, r["status"]), (200, "quoted"), r)
        self.assertIn("€ HT", r["reply"])
        s2, v = self.call("GET", "/api/quote/" + r["quote"]["quote_id"])
        self.assertEqual((s2, v["price_ht"]), (200, r["quote"]["price_ht"]))

    def test_intake_incomplete_asks_for_missing(self):
        s, r = self.signed("/api/intake/email", {"text": "Un prix de Lyon à Paris svp"})
        self.assertEqual((s, r["status"]), (200, "needs_info"))
        self.assertIn("poids", r["reply"])

    def test_ratematch_flow_and_single_use(self):
        q = self.make_quote()
        comp = round(q["price_ht"] * 0.96, 2)
        s, r = self.call("POST", "/api/ratematch", {"quote_id": q["quote_id"], "competitor_price_ht": comp, "reference": "Concurrent X devis 123"})
        self.assertEqual(s, 200, r)
        self.assertIn(r["outcome"], ("matched", "counter"))
        self.assertLessEqual(r["quote"]["price_ht"], q["price_ht"])
        s2, _ = self.call("POST", "/api/ratematch", {"quote_id": q["quote_id"], "competitor_price_ht": comp, "reference": "autre"})
        self.assertEqual(s2, 409)

    def test_ratematch_requires_reference_and_valid_amount(self):
        q = self.make_quote()
        self.assertEqual(self.call("POST", "/api/ratematch", {"quote_id": q["quote_id"], "competitor_price_ht": 100})[0], 422)
        self.assertEqual(self.call("POST", "/api/ratematch", {"quote_id": q["quote_id"], "competitor_price_ht": "abc", "reference": "x"})[0], 422)
        self.assertEqual(self.call("POST", "/api/ratematch", {"quote_id": "inconnu", "competitor_price_ht": 100, "reference": "x"})[0], 404)

    def test_matched_booking_flags_proof_check(self):
        q = self.make_quote()
        floor_cost = self.server.DB_.get_quote(q["quote_id"])["quote"]["carrier_cost_estimate"]
        comp = round(max(q["price_ht"] * 0.97, floor_cost * 1.06), 2)
        s, r = self.call("POST", "/api/ratematch", {"quote_id": q["quote_id"], "competitor_price_ht": comp, "reference": "Conc. Y n°9"})
        self.assertEqual(r["outcome"], "matched", r)
        body = {"quote_id": q["quote_id"], "accept_cgv": True, "pickup_address": "1 rue A, Lyon", "delivery_address": "2 rue B, Paris",
                "goods": "palettes", "pickup_window": "08:00-12:00", "delivery_window": "09:00-17:00",
                "site_contact_name": "Marie", "site_contact_phone": "0611223344",
                "contact": {"name": "Jean", "company": "T SAS", "email": f"j{time.time_ns()}@t.fr", "phone": "0612345678"}}
        s, b = self.call("POST", "/api/book", body)
        self.assertEqual(s, 201, b)
        row = self.server.DB_.booking_by_code(b["tracking_code"])
        log = json.loads(row["agent_log"])
        self.assertTrue(any("Alignement tarifaire" in a for a in log["alerts"]))
        self.assertAlmostEqual(row["customer_price_ht"], comp, places=2)


if __name__ == "__main__":
    unittest.main()


from email.message import EmailMessage  # noqa: E402
from fretrau import mailgate  # noqa: E402


def raw_mail(body, subject="Demande de prix", frm="client@acme.fr", html_only=False, **headers):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = frm, "devis@fretrau.fr", subject, "<abc@acme.fr>"
    for k, v in headers.items():
        m[k.replace("_", "-")] = v
    if html_only:
        m.set_content("x")
        m.clear_content()
        m.set_content(body, subtype="html")
    else:
        m.set_content(body)
    return m.as_bytes()


class Gateway(unittest.TestCase):
    def run_gate(self, raw, limiter=None):
        calls = []
        def post(text):
            calls.append(text)
            return {"status": "quoted", "reply": "Prix : 893,44 € HT"}
        st, rep = mailgate.process(raw, post, limiter or mailgate.SenderLimiter(), "devis@fretrau.fr")
        return st, rep, calls

    def test_plain_mail_is_processed_and_replied_in_thread(self):
        st, rep, calls = self.run_gate(raw_mail("Camion complet de Lyon à Paris, 15 tonnes, demain.\n\n-- \nJean\nTél 0612345678"))
        self.assertEqual(st, "quoted")
        self.assertEqual(rep["To"], "client@acme.fr")
        self.assertEqual(rep["In-Reply-To"], "<abc@acme.fr>")
        self.assertTrue(rep["Subject"].startswith("Re:"))
        self.assertEqual(rep["Auto-Submitted"], "auto-replied")
        self.assertNotIn("0612345678", calls[0])             # signature coupée

    def test_html_only_mail(self):
        st, _, calls = self.run_gate(raw_mail("<html><body><p>Lyon vers Paris</p><p>15 tonnes demain camion complet</p><script>x()</script></body></html>", html_only=True))
        self.assertEqual(st, "quoted")
        self.assertIn("15 tonnes", calls[0])
        self.assertNotIn("x()", calls[0])

    def test_quoted_reply_not_reparsed(self):
        _, _, calls = self.run_gate(raw_mail("Merci, ok pour jeudi.\n\nLe 17 nov. 2026 à 10:00, FRETRAU a écrit :\n> Lyon vers Paris 15 t\n> prix 893 €"))
        self.assertNotIn("893", calls[0])

    def test_automatic_mails_ignored(self):
        for h in ({"Auto_Submitted": "auto-replied"}, {"Precedence": "bulk"}, {"List_Id": "<news.x>"}):
            self.assertEqual(self.run_gate(raw_mail("Lyon vers Paris 15 tonnes demain camion complet", **h))[0], "ignored_automatic")
        self.assertEqual(self.run_gate(raw_mail("Lyon vers Paris 15 tonnes demain camion complet", frm="no-reply@x.com"))[0], "ignored_automatic")
        self.assertEqual(self.run_gate(raw_mail("Lyon vers Paris 15 tonnes demain camion complet", frm="MAILER-DAEMON@x.com"))[0], "ignored_automatic")

    def test_sender_rate_limit(self):
        lim = mailgate.SenderLimiter(limit=2, window=3600)
        raw = raw_mail("Lyon vers Paris, 15 tonnes, demain, camion complet")
        self.assertEqual(self.run_gate(raw, lim)[0], "quoted")
        self.assertEqual(self.run_gate(raw, lim)[0], "quoted")
        self.assertEqual(self.run_gate(raw, lim)[0], "ignored_rate_limited")

    def test_header_injection_neutralised(self):
        m = EmailMessage()
        m["From"], m["To"], m["Message-ID"] = "c@acme.fr", "devis@fretrau.fr", "<i@acme.fr>"
        m["Subject"] = "Prix"
        m.set_content("Lyon vers Paris, 15 tonnes, demain, camion complet")
        orig = mailgate.email.message_from_bytes(m.as_bytes())
        orig.replace_header("Subject", "Prix\r\nBcc: victime@x.com")
        rep = mailgate.build_reply(orig, "ok", "devis@fretrau.fr")
        self.assertIsNone(rep["Bcc"])
        self.assertNotIn("\n", rep["Subject"].replace("\r", ""))

    def test_empty_ignored(self):
        self.assertEqual(self.run_gate(raw_mail("ok", subject=""))[0], "ignored_empty")

    def test_end_to_end_with_real_intake_endpoint(self):
        import server
        httpd = server.make_server("127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/api/intake/email"
            pk = calendar_fr.next_business_day(date.today() + timedelta(days=4)).strftime("%d/%m/%Y")
            raw = raw_mail(f"Bonjour,\nCamion complet Lyon vers Paris, 15 tonnes, enlèvement le {pk}.\nCordialement")
            st, rep = mailgate.process(raw, lambda t: mailgate.signed_post(url, server.WEBHOOK_SECRET, {"text": t}),
                                       mailgate.SenderLimiter(), "devis@fretrau.fr")
            self.assertEqual(st, "quoted")
            self.assertIn("€ HT", rep.get_content())
        finally:
            httpd.shutdown()


class TrackingAndPayables(Api):
    """Suivi réel par le transporteur, preuve de livraison, échéancier de paiement transporteur."""

    def confirmed_booking(self):
        q = self.make_quote()
        body = {"quote_id": q["quote_id"], "accept_cgv": True, "pickup_address": "1 rue A, Lyon", "delivery_address": "2 rue B, Paris",
                "goods": "palettes", "pickup_window": "08:00-12:00", "delivery_window": "09:00-17:00",
                "site_contact_name": "Marie", "site_contact_phone": "0611223344",
                "contact": {"name": "Jean", "company": "T SAS", "email": f"j{time.time_ns()}@t.fr", "phone": "0612345678"}}
        s, b = self.call("POST", "/api/book", body)
        self.assertEqual(s, 201, b)
        row = self.server.DB_.booking_by_code(b["tracking_code"])
        self.assertEqual(row["status"], "confirmed")
        return row

    def status(self, code, carrier_id, event):
        return self.signed("/api/webhook/carrier-status", {"tracking_code": code, "carrier_id": carrier_id, "event": event})

    def admin_cookie(self):
        h = {"Content-Type": "application/json", "X-Requested-With": "fretrau"}
        req = urllib.request.Request(self.base + "/api/admin/login", method="POST", headers=h,
                                     data=json.dumps({"user": "admin", "password": os.environ["FRETRAU_ADMIN_PASSWORD"]}).encode())
        with urllib.request.urlopen(req) as r:
            return r.headers["Set-Cookie"].split(";")[0]

    def admin(self, method, path, body=None):
        h = {"Content-Type": "application/json", "X-Requested-With": "fretrau", "Cookie": self.admin_cookie()}
        req = urllib.request.Request(self.base + path, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def setUp(self):
        super().setUp()
        self.server.RL_LOGIN.hits.clear()

    def test_status_requires_signature_and_right_carrier(self):
        b = self.confirmed_booking()
        s, _ = self.call("POST", "/api/webhook/carrier-status", {"tracking_code": b["tracking_code"], "carrier_id": b["carrier_id"], "event": "loaded", "ts": time.time()}, headers={"X-Signature": "0"})
        self.assertEqual(s, 401)
        self.assertEqual(self.status(b["tracking_code"], b["carrier_id"] + 1, "loaded")[0], 404)     # un autre transporteur n'a aucun droit
        self.assertEqual(self.status(b["tracking_code"], b["carrier_id"], "teleporte")[0], 422)
        self.assertEqual(self.status("FR-000000000000", b["carrier_id"], "loaded")[0], 404)

    def test_events_are_monotone_and_idempotent(self):
        b = self.confirmed_booking()
        c, code = b["carrier_id"], b["tracking_code"]
        self.assertEqual(self.status(code, c, "loaded")[1]["result"], "added")
        self.assertEqual(self.status(code, c, "loaded")[1]["result"], "duplicate")
        self.assertEqual(self.status(code, c, "in_transit")[1]["result"], "added")
        self.assertEqual(self.status(code, c, "loaded")[1]["result"], "duplicate")
        s, t = self.call("GET", "/api/track/" + code)
        self.assertEqual(t["events_source"], "carrier")
        done = [e["label"] for e in t["events"] if e["done"]]
        self.assertIn("En transit", done)
        self.assertNotIn("Livré — preuve de livraison enregistrée", done)

    def test_out_of_order_rejected(self):
        b = self.confirmed_booking()
        self.assertEqual(self.status(b["tracking_code"], b["carrier_id"], "arrived")[1]["result"], "added")
        self.assertEqual(self.status(b["tracking_code"], b["carrier_id"], "loaded")[1]["result"], "out_of_order")

    def test_delivery_creates_exactly_one_payable_with_carrier_cost(self):
        b = self.confirmed_booking()
        c, code = b["carrier_id"], b["tracking_code"]
        self.status(code, c, "in_transit")
        self.assertEqual(self.server.DB_.list_payables(), [p for p in self.server.DB_.list_payables() if p["booking_id"] != b["id"]])
        self.assertEqual(self.status(code, c, "delivered")[1]["result"], "added")
        self.assertEqual(self.status(code, c, "delivered")[1]["result"], "duplicate")
        mine = [p for p in self.server.DB_.list_payables() if p["booking_id"] == b["id"]]
        self.assertEqual(len(mine), 1)
        self.assertAlmostEqual(mine[0]["amount_ht"], b["carrier_price"], places=2)
        self.assertNotAlmostEqual(mine[0]["amount_ht"], b["customer_price_ht"], places=2)   # on paie le transporteur, pas le prix client
        self.assertEqual(mine[0]["status"], "due")
        self.assertEqual(mine[0]["due_on"], date.today().isoformat())

    def test_operator_pod_needs_a_milestone_first(self):
        b = self.confirmed_booking()
        self.assertEqual(self.admin("POST", "/api/admin/pod", {"tracking_code": b["tracking_code"]})[0], 409)
        self.status(b["tracking_code"], b["carrier_id"], "loaded")
        s, r = self.admin("POST", "/api/admin/pod", {"tracking_code": b["tracking_code"]})
        self.assertEqual((s, r["result"]), (200, "added"))

    def test_pay_once_with_reference(self):
        b = self.confirmed_booking()
        self.status(b["tracking_code"], b["carrier_id"], "in_transit")
        self.status(b["tracking_code"], b["carrier_id"], "delivered")
        pid = [p for p in self.server.DB_.list_payables() if p["booking_id"] == b["id"]][0]["id"]
        self.assertEqual(self.admin("POST", "/api/admin/payables/pay", {"id": pid})[0], 422)          # référence obligatoire
        self.assertEqual(self.admin("POST", "/api/admin/payables/pay", {"id": pid, "reference": "VIR-2026-001"})[0], 200)
        self.assertEqual(self.admin("POST", "/api/admin/payables/pay", {"id": pid, "reference": "VIR-2026-002"})[0], 409)   # jamais deux fois
        s, lst = self.admin("GET", "/api/admin/payables")
        self.assertEqual(s, 200)
        self.assertIn("total_due_ht", lst)

    def test_no_simulation_when_demo_timeline_off(self):
        b = self.confirmed_booking()
        old = self.server.DEMO_TIMELINE
        self.server.DEMO_TIMELINE = False
        try:
            s, t = self.call("GET", "/api/track/" + b["tracking_code"])
            self.assertEqual(t["events_source"], "carrier")
            self.assertEqual([e["done"] for e in t["events"]], [True, True, False, False, False, False])
        finally:
            self.server.DEMO_TIMELINE = old
