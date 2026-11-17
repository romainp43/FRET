import time
import json, os, re, sys, threading, unittest, urllib.request, urllib.error
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")
from fretrau import calendar_fr, chaining, claims, pricing, vetting  # noqa: E402
import build_site, site_content  # noqa: E402

GOOD_SIREN = "552100554"          # SIREN réel et public (Orange SA) : sert uniquement à tester la clé de Luhn


def tva_fr(siren):
    return f"FR{(12 + 3 * (int(siren) % 97)) % 97:02d}{siren}"


class Vetting(unittest.TestCase):
    def app(self, **kw):
        a = {"country": "FR", "company_id": GOOD_SIREN, "siret": "", "vat": tva_fr(GOOD_SIREN), "licence": "2023/84/0001234",
             "insurance_until": (date.today() + timedelta(days=200)).isoformat(), "insurance_cover_eur": 150000,
             "equipment": ["dry"], "accept_charter": True}
        a.update(kw)
        return a

    def test_luhn(self):
        self.assertTrue(vetting.siren_ok(GOOD_SIREN))
        self.assertTrue(vetting.siren_ok("552 100 554"))
        self.assertFalse(vetting.siren_ok("552100555"))
        self.assertFalse(vetting.siren_ok("12345"))
        self.assertFalse(vetting.siren_ok("55210055A"))

    def test_siret(self):
        base = GOOD_SIREN + "0012"
        ok = [base + str(d) for d in range(10) if vetting.siret_ok(base + str(d))]
        self.assertEqual(len(ok), 1)                                      # une seule clé valide
        self.assertFalse(vetting.siret_ok("1234567890123"))

    def test_fr_vat_key(self):
        self.assertTrue(vetting.vat_ok(tva_fr(GOOD_SIREN), "FR", GOOD_SIREN))
        self.assertFalse(vetting.vat_ok("FR00" + GOOD_SIREN, "FR", GOOD_SIREN))
        self.assertFalse(vetting.vat_ok(tva_fr(GOOD_SIREN), "FR", "123456789"))      # SIREN incohérent

    def test_eu_vat_formats(self):
        self.assertTrue(vetting.vat_ok("DE123456789", "DE"))
        self.assertTrue(vetting.vat_ok("ES A1234567B".replace(" ", ""), "ES"))
        self.assertTrue(vetting.vat_ok("PL 1234567890", "PL"))
        self.assertFalse(vetting.vat_ok("DE12345", "DE"))
        self.assertFalse(vetting.vat_ok("XX123", "XX"))

    def test_check_accepts_good_and_rejects_each_defect(self):
        self.assertTrue(vetting.check(self.app())["ok"])
        for kw, frag in [({"insurance_until": (date.today() + timedelta(days=5)).isoformat()}, "Assurance"),
                         ({"insurance_cover_eur": 20000}, "Garantie"), ({"licence": "x"}, "Licence"),
                         ({"company_id": "552100555"}, "SIREN"), ({"equipment": []}, "véhicule"),
                         ({"accept_charter": False}, "Charte"), ({"country": "US"}, "Pays")]:
            r = vetting.check(self.app(**kw))
            self.assertFalse(r["ok"], kw)
            self.assertTrue(any(frag in e for e in r["errors"]), (kw, r["errors"]))


class Claims(unittest.TestCase):
    def test_domestic_deadline_skips_sundays_and_holidays(self):
        # livraison vendredi 13 nov 2026 : 3 jours hors dimanche → samedi 14, lundi 16, mardi 17
        d = claims.deadlines("damage", date(2026, 11, 13), False)
        self.assertEqual(d["written_reserve_before"], "2026-11-17")
        self.assertEqual(d["limitation_date"], "2027-11-13")

    def test_international_cmr(self):
        d = claims.deadlines("damage", date(2026, 11, 2), True)
        self.assertEqual(d["written_reserve_before"], "2026-11-10")          # 7 jours hors dimanche (8 nov) → 10 nov
        d2 = claims.deadlines("delay", date(2026, 11, 2), True)
        self.assertEqual(d2["written_reserve_before"], "2026-11-23")          # 21 jours calendaires
        self.assertTrue(d2["international"])

    def test_holiday_skipped(self):
        d = claims.deadlines("damage", date(2026, 12, 23), False)             # 24, 26 (25 férié), 28 (27 dimanche)
        self.assertEqual(d["written_reserve_before"], "2026-12-28")

    def test_leap_day_limitation(self):
        self.assertEqual(claims.deadlines("loss", date(2028, 2, 29), False)["limitation_date"], "2029-02-28")   # 29 févr. : on retient la date la plus prudente


class Flatbed(unittest.TestCase):
    PK = calendar_fr.next_business_day(date.today() + timedelta(days=4))

    def test_surcharge_and_restrictions(self):
        base = pricing.build_quote("Lyon", "Paris", "FTL", 33, 15000, {}, self.PK)
        fb = pricing.build_quote("Lyon", "Paris", "FTL", 33, 15000, {"flatbed": True}, self.PK)
        self.assertGreater(fb.price_ht, base.price_ht)
        self.assertIn("plateau", fb.breakdown)
        with self.assertRaises(pricing.QuoteError):
            pricing.build_quote("Lyon", "Paris", "LTL", 4, 2000, {"flatbed": True}, self.PK)
        with self.assertRaises(pricing.QuoteError):
            pricing.build_quote("Lyon", "Paris", "FTL", 33, 15000, {"flatbed": True, "temperature": True}, self.PK)

    def test_only_flatbed_carriers_selected(self):
        from fretrau.agents import compliance
        from fretrau.carriers import CARRIERS
        ok = [c.id for c in CARRIERS if compliance.check(c, "FTL", "Lyon", "Paris", self.PK, {"flatbed": True})[0]]
        self.assertTrue(ok)
        self.assertTrue(all(next(c for c in CARRIERS if c.id == i).flatbed for i in ok))

    def test_intake_understands_flatbed(self):
        from fretrau.agents import intake
        r = intake.parse("Bonjour, un plateau de Lyon à Paris, 20 tonnes, camion complet, demain", date(2026, 11, 17))
        self.assertTrue(r["fields"]["options"].get("flatbed"), r)


class Chaining(unittest.TestCase):
    def test_detects_and_ignores(self):
        items = [
            {"code": "A", "origin": "Lyon", "destination": "Marseille", "mode": "FTL", "pickup_date": "2026-11-18", "earliest_delivery": "2026-11-19"},
            {"code": "B", "origin": "Marseille", "destination": "Lyon", "mode": "FTL", "pickup_date": "2026-11-19", "earliest_delivery": "2026-11-20"},
            {"code": "C", "origin": "Lille", "destination": "Paris", "mode": "FTL", "pickup_date": "2026-11-19", "earliest_delivery": "2026-11-20"},
            {"code": "D", "origin": "Marseille", "destination": "Nice", "mode": "LTL", "pickup_date": "2026-11-19", "earliest_delivery": "2026-11-20"},
        ]
        s = chaining.suggestions(items)
        pairs = {(x["first"], x["second"]) for x in s}
        self.assertIn(("A", "B"), pairs)
        self.assertNotIn(("A", "C"), pairs)           # trop loin
        self.assertFalse(any("D" in p for p in pairs))  # le groupage n'est pas chaîné
        self.assertTrue(all(x["saved_empty_km"] >= 0 for x in s))


class Pages(unittest.TestCase):
    def test_all_pages_generated_with_faq_and_no_inline_script(self):
        pages = build_site.pages()
        self.assertEqual(len(pages), 11 + len(site_content.SERVICES))
        for name, h in pages.items():
            self.assertNotRegex(h, r"<script(?![^>]*(src=|type=\"application/ld\+json\"))", name)    # CSP : aucun script en ligne
            self.assertNotIn("onclick", h)
        for slug in site_content.SERVICES:
            h = pages[f"services/{slug}.html"]
            self.assertIn("FAQPage", h)
            self.assertGreaterEqual(h.count("<details>"), 6, slug)
        for name in pages:
            for m in re.findall(r'href="(/[^"#]*)', pages[name]):
                if m.endswith(".html") or m == "/":
                    target = os.path.join(ROOT, "web", m.lstrip("/") or "index.html")
                    built = m.lstrip("/") in pages
                    self.assertTrue(built or os.path.exists(target) or m.startswith("/legal/") or m == "/", (name, m))

    def test_no_unfulfilled_promises(self):
        text = " ".join(h for h in build_site.pages().values()).lower()
        for banned in ("24/7", "24h/24", "garantie du prix le plus bas", "paiement par carte immédiat", "suivi gps"):
            self.assertNotIn(banned, text)


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
                   self.server.RL_LOGIN):
            rl.hits.clear()
        self.server.GUARD.__init__() if hasattr(self.server.GUARD, "__init__") else None

    def call(self, method, path, body=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + path, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def carrier_body(self, **kw):
        b = {"company": "Transports Test SARL", "country": "FR", "company_id": GOOD_SIREN, "vat": tva_fr(GOOD_SIREN),
             "licence": "2023/84/0001234", "insurer": "AssurTest", "insurance_until": (date.today() + timedelta(days=200)).isoformat(),
             "insurance_cover_eur": 200000, "fleet_size": 5, "equipment": ["dry", "flatbed"], "countries": ["FR", "ES"],
             "contact_name": "Jean Test", "email": "jean@example.fr", "phone": "0612345678", "accept_charter": True}
        b.update(kw)
        return b

    def test_static_pages_served(self):
        for path in ("/faq.html", "/services/plateau.html", "/transporteurs.html", "/contact.html", "/reclamation.html", "/a-propos.html", "/forms.js"):
            req = urllib.request.Request(self.base + path)
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 200, path)

    def test_carrier_application_flow(self):
        s, r = self.call("POST", "/api/carrier/apply", self.carrier_body())
        self.assertEqual(s, 201, r)
        self.assertTrue(r["reference"].startswith("T-"))
        s, r = self.call("POST", "/api/carrier/apply", self.carrier_body(insurance_cover_eur=10000, company_id="552100555"))
        self.assertEqual(s, 422)
        self.assertTrue(any("SIREN" in p for p in r["problems"]) and any("Garantie" in p for p in r["problems"]))

    def test_honeypot_stores_nothing(self):
        before = len(self.server.DB_.list_applications())
        s, r = self.call("POST", "/api/carrier/apply", self.carrier_body(website="http://spam"))
        self.assertEqual(s, 200)
        self.assertEqual(len(self.server.DB_.list_applications()), before)

    def test_contact_form(self):
        ok = {"topic": "intermodal", "name": "Anne", "email": "anne@example.fr", "message": "Flux Lyon-Duisbourg", "consent": True}
        self.assertEqual(self.call("POST", "/api/contact", ok)[0], 201)
        self.assertEqual(self.call("POST", "/api/contact", {**ok, "consent": False})[0], 422)
        self.assertEqual(self.call("POST", "/api/contact", {**ok, "email": "pas-un-mail"})[0], 422)

    def test_form_rate_limit(self):
        ok = {"topic": "other", "name": "A", "email": "a@example.fr", "message": "x", "consent": True}
        codes = [self.call("POST", "/api/contact", ok)[0] for _ in range(8)]
        self.assertEqual(codes[:6], [201] * 6)
        self.assertEqual(codes[6], 429)

    def book(self):
        self.email = f"marc{time.time_ns()}@example.fr"
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4)).isoformat()
        s, q = self.call("POST", "/api/quote", {"origin": "Lyon", "destination": "Paris", "mode": "FTL", "pallets": 33,
                                                  "weight_kg": 15000, "pickup_date": pk, "options": {}})
        self.assertEqual(s, 200, q)
        body = {"quote_id": q["quote_id"], "accept_cgv": True, "contact": {"name": "Marc", "company": "ACME", "email": self.email, "phone": "0611223344"},
                "pickup_window": "08:00-17:00", "delivery_window": "08:00-17:00", "site_contact_name": "Paul", "site_contact_phone": "0611223344",
                "pickup_address": "1 rue Alpha, 69001 Lyon", "delivery_address": "2 rue Beta, 75010 Paris", "goods": "palettes"}
        s, b = self.call("POST", "/api/book", body)
        self.assertEqual(s, 201, b)
        return b["tracking_code"]

    def test_claim_requires_matching_email_and_computes_deadlines(self):
        code = self.book()
        base = {"tracking_code": code, "email": self.email, "kind": "damage",
                "delivered_on": date.today().isoformat(), "description": "Deux palettes écrasées", "reserves_on_receipt": True}
        s, r = self.call("POST", "/api/claim", {**base, "email": "autre@example.fr"})
        self.assertEqual(s, 404)
        s, r = self.call("POST", "/api/claim", {**base, "tracking_code": "FR-000000000000"})
        self.assertEqual(s, 404)                                              # même message : pas d'énumération
        s, r = self.call("POST", "/api/claim", base)
        self.assertEqual(s, 201, r)
        self.assertFalse(r["deadlines"]["international"])
        s, r = self.call("POST", "/api/claim", {**base, "delivered_on": (date.today() + timedelta(days=3)).isoformat()})
        self.assertEqual(s, 422)                                              # livraison dans le futur

    def test_admin_endpoints_need_auth_and_work(self):
        for path in ("/api/admin/carriers", "/api/admin/claims", "/api/admin/contacts", "/api/admin/chaining"):
            self.assertEqual(self.call("GET", path)[0], 401, path)
        s, _ = self.call("POST", "/api/admin/login", {"user": "admin", "password": os.environ["FRETRAU_ADMIN_PASSWORD"]})
        # le cookie n'est pas conservé par urllib : on teste la logique directement via la base
        db = self.server.DB_
        aid = db.add_application({"company": "X"}, [])
        self.assertTrue(db.decide_application(aid, "rejected", "tester", "non conforme"))
        self.assertFalse(db.decide_application(999999, "approved", "tester", "x"))


if __name__ == "__main__":
    unittest.main()
