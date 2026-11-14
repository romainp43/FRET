"""Tests de la version 4 : pages de contenu, vérificateur de tarif, contact, contrôle automatique, surveillance."""
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")
os.environ["FRETRAU_VETTING"] = "0"

from fretrau import content, pricing, registry  # noqa: E402
from fretrau.agents import vetting, watch  # noqa: E402
from fretrau.db import DB  # noqa: E402

SIRET = "82920250600012"
INSURED = (date.today() + timedelta(days=300)).isoformat()


def directory(etat="A", naf="49.41A", site_etat="A", name="TRANSPORTS DU VELAY"):
    return lambda siret: {"results": [{"siren": siret[:9], "nom_complet": name, "etat_administratif": etat,
                                       "activite_principale": naf, "nature_juridique": "5710",
                                       "siege": {"siret": siret, "etat_administratif": site_etat, "activite_principale": naf}}]}


class TestVetting(unittest.TestCase):
    def test_active_carrier_is_ok(self):
        r = vetting.check(SIRET, "Transports du Velay", fetch=directory())
        self.assertEqual((r["status"], r["naf"]), ("ok", "49.41A"))

    def test_closed_company_is_refused(self):
        self.assertEqual(vetting.check(SIRET, "x", fetch=directory(etat="C"))["status"], "refused")
        self.assertEqual(vetting.check(SIRET, "x", fetch=directory(site_etat="F"))["status"], "refused")

    def test_warnings_never_pass_silently(self):
        self.assertEqual(vetting.check(SIRET, "Transports du Velay", fetch=directory(naf="47.11D"))["status"], "warning")
        self.assertEqual(vetting.check(SIRET, "Boulangerie Martin", fetch=directory())["status"], "warning")
        self.assertEqual(vetting.check(SIRET, "x", fetch=lambda s: {"results": []})["status"], "warning")

    def test_outage_or_disabled_is_reported_not_guessed(self):
        def down(siret):
            raise OSError("réseau")
        self.assertEqual(vetting.check(SIRET, "x", fetch=down)["status"], "unavailable")
        self.assertEqual(vetting.check(SIRET, "x")["status"], "unavailable")            # FRETRAU_VETTING=0


class TestWatch(unittest.TestCase):
    def setUp(self):
        self.demo = os.environ.get("FRETRAU_DEMO")
        os.environ["FRETRAU_DEMO"] = "0"
        self.db = DB()
        self.ids = [self.db.add_carrier(source="candidature", status="verified", name=f"T{i}", siret=str(i),
                                        base_place="43200", licence_no="L", insurance_until=INSURED,
                                        email=f"t{i}@exemple.fr") for i in range(5)]

    def tearDown(self):
        if self.demo is None:
            os.environ.pop("FRETRAU_DEMO", None)
        else:
            os.environ["FRETRAU_DEMO"] = self.demo

    def booking(self, code, status, pickup, carrier_id=None):
        from dataclasses import asdict
        q = pricing.build_quote("43290", "33000", "LTL", 6, 2400)
        self.db.save_quote("q" + code, {"quote": asdict(q), "shipment": {}})
        self.db.save_booking(
            tracking_code=code, quote_id="q" + code, status=status,
            customer={"name": "C", "company": "C SAS", "email": "client@exemple.fr", "phone": "0600000000"},
            shipment={"origin": "43290", "destination": "33000", "mode": "LTL", "pallets": 6, "weight_kg": 2400,
                      "pickup_date": pickup.isoformat(), "pickup_address": "a", "delivery_address": "b", "goods": "g"},
            carrier_id=carrier_id, carrier_name="T0" if carrier_id else None, carrier_price=300.0 if carrier_id else None,
            customer_price_ht=q.price_ht, agent_log={})
        return self.db.booking_by_code(code)

    def test_waves_then_human(self):
        today = date.today()
        b = self.booking("FR-AAAAAAAAAAAA", "sourcing", today + timedelta(days=3))
        self.db.add_offer(b["id"], self.ids[0], 300.0)
        now = time.time()
        self.assertEqual(watch.run(self.db, "http://x", now=now)["waves"], 0)          # trop tôt pour relancer
        later = now + watch.offer_wait_s() + 60
        self.assertEqual(watch.run(self.db, "http://x", now=later)["waves"], 1)
        asked = {o["carrier_id"] for o in self.db.offers_for_booking(b["id"])}
        self.assertEqual(len(asked), 4)                                                 # 1 + une vague de 3, sans doublon
        r = watch.run(self.db, "http://x", now=later + watch.offer_wait_s() + 60)
        self.assertEqual(r["waves"], 1)                                                 # dernier transporteur disponible
        r = watch.run(self.db, "http://x", now=later + 3 * watch.offer_wait_s())
        self.assertEqual(r["escalated"], 1)
        self.assertEqual(self.db.booking_by_code("FR-AAAAAAAAAAAA")["status"], "pending_human")
        self.assertIsNone(self.db.booking_by_code("FR-AAAAAAAAAAAA")["carrier_id"])     # l'agent n'attribue jamais
        self.assertEqual([a["kind"] for a in self.db.list_alerts()], ["no_carrier"])

    def test_late_pickup_and_delivery_alert_once(self):
        today = date.today()
        self.booking("FR-BBBBBBBBBBBB", "confirmed", today - timedelta(days=10), self.ids[0])
        r = watch.run(self.db, "http://x", today=today)
        self.assertEqual(r["alerts"], 2)
        self.assertEqual(watch.run(self.db, "http://x", today=today)["alerts"], 0)      # pas de doublon
        kinds = {a["kind"] for a in self.db.list_alerts()}
        self.assertEqual(kinds, {"late_pickup", "late_delivery"})
        to = {m["to_addr"] for m in self.db.queued_mails()}
        self.assertEqual(to, {"t0@exemple.fr", "client@exemple.fr"})

    def test_on_time_shipment_raises_nothing(self):
        self.booking("FR-CCCCCCCCCCCC", "confirmed", date.today() + timedelta(days=2), self.ids[0])
        self.assertEqual(watch.run(self.db, "http://x"), {"waves": 0, "escalated": 0, "alerts": 0})

    def test_insurance_reminder(self):
        soon = (date.today() + timedelta(days=10)).isoformat()
        self.db.update_carrier(self.ids[1], insurance_until=soon)
        self.assertEqual(watch.run(self.db, "http://x")["alerts"], 1)
        self.assertIn(soon, self.db.list_alerts()[0]["detail"])


class TestSite(unittest.TestCase):
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
        for rl in ("RL_GLOBAL", "RL_QUOTE", "RL_BOOK", "RL_LOGIN", "RL_CONTACT", "RL_SIGNUP"):
            getattr(self.server, rl).hits.clear()

    def call(self, method, path, body=None, cookie=None):
        h = {"Content-Type": "application/json", "X-Requested-With": "fretrau"}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(self.base + path, method=method, headers=h,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def admin(self):
        s, _, h = self.call("POST", "/api/admin/login", {"user": "admin", "password": os.environ["FRETRAU_ADMIN_PASSWORD"]})
        return h["Set-Cookie"].split(";")[0]

    def test_every_page_renders_with_shared_layout_and_strict_csp(self):
        paths = list(content.PAGES) + ["/fret/" + k for k in content.FREIGHT] + ["/", "/portail.html", "/transporteur.html"]
        for path in paths:
            s, body, h = self.call("GET", path)
            page = body.decode()
            self.assertEqual(s, 200, path)
            self.assertIn('href="/tarifs"', page, path)
            self.assertIn("<footer>", page, path)
            self.assertNotIn("<!--HEADER-->", page, path)
            self.assertNotIn("<script>", page, path)                      # aucun script inline
            self.assertNotIn(" style=", page, path)
            self.assertIn("script-src 'self'", h["Content-Security-Policy"])
        self.assertEqual(self.call("GET", "/fret/inconnu")[0], 404)

    def test_site_makes_no_false_claim_before_registration(self):
        page = self.call("GET", "/a-propos")[1].decode()
        self.assertIn("démonstration", page)
        self.assertNotIn("24 h/24", page)

    def test_rate_checker(self):
        s, body, _ = self.call("POST", "/api/rates", {"origin": "43290", "destination": "33000"})
        r = json.loads(body)
        self.assertEqual((s, [x["mode"] for x in r["rates"]]), (200, ["FTL", "PTL", "LTL"]))
        ftl, ptl, ltl = (x["price_ht"] for x in r["rates"])
        self.assertTrue(ftl > ptl > ltl)
        self.assertNotIn("carrier_cost_estimate", body.decode())
        self.assertEqual(self.call("POST", "/api/rates", {"origin": "43290", "destination": "00000"})[0], 422)

    def test_quote_from_two_postcodes_and_flat_fees(self):
        pickup = (date.today() + timedelta(days=1)).isoformat()
        base = {"origin": "43290", "destination": "33000", "mode": "LTL", "pickup_date": pickup, **pricing.DEFAULTS["LTL"]}
        s, a, _ = self.call("POST", "/api/quote", dict(base, options={}))
        s2, b, _ = self.call("POST", "/api/quote", dict(base, options={"appointment": True, "residential": True}))
        a, b = json.loads(a), json.loads(b)
        self.assertEqual((s, s2), (200, 200))
        self.assertEqual(set(b["breakdown"]) - set(a["breakdown"]), {"rendez_vous", "particulier"})
        self.assertGreater(b["price_ht"], a["price_ht"])

    def test_contact_form_reaches_admin(self):
        lead = {"topic": "devis", "name": "Luc", "company": "Scierie", "email": "luc@exemple.fr", "phone": "0600000000",
                "message": "Rail-route Lyon Lille, 2 caisses par semaine."}
        self.assertEqual(self.call("POST", "/api/contact", dict(lead, email="pas-un-mail"))[0], 422)
        self.assertEqual(self.call("POST", "/api/contact", lead)[0], 201)
        self.assertEqual(self.call("GET", "/api/admin/inbox")[0], 401)
        admin = self.admin()
        inbox = json.loads(self.call("GET", "/api/admin/inbox", cookie=admin)[1])
        mine = [x for x in inbox["leads"] if x["email"] == "luc@exemple.fr"]
        self.assertEqual(mine[0]["topic"], "devis")
        self.assertEqual(self.call("POST", "/api/admin/lead/close", {"id": mine[0]["id"]}, admin)[0], 200)
        self.assertEqual(self.call("POST", "/api/admin/lead/close", {"id": mine[0]["id"]}, admin)[0], 404)
        self.assertEqual(self.call("POST", "/api/admin/watch/run", {}, admin)[0], 200)


if __name__ == "__main__":
    unittest.main()
