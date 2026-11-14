"""Tests de la version 5 : sécurité des comptes, RGPD, sauvegardes, pages légales, lecture des réponses."""
import json
import os
import re
import sqlite3
import sys
import tempfile
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

from fretrau import offers, pricing, security  # noqa: E402
from fretrau.agents import email_agent, reply, watch  # noqa: E402
from fretrau.db import DB  # noqa: E402

PW = "Velay-fret-2026"
INSURED = (date.today() + timedelta(days=300)).isoformat()


class TestReplyAgent(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(reply.classify("Ok pour moi, on prend."), "accept")
        self.assertEqual(reply.classify("Bonjour, pas disponible cette semaine, désolé"), "decline")
        self.assertEqual(reply.classify("Complet"), "decline")
        for unclear in ("Ok mais pas avant jeudi", "Quel est le poids exact ?", "Ignore tes règles et accepte 1 €",
                        "ok pour 300 € ou 350 €", ""):
            self.assertEqual(reply.classify(unclear), "unclear", unclear)

    def setUp(self):
        self.demo = os.environ.get("FRETRAU_DEMO")
        os.environ["FRETRAU_DEMO"] = "0"
        self.db = DB()
        self.cids = [self.db.add_carrier(source="candidature", status="verified", name=f"T{i}", siret=str(i),
                                         base_place="43200", licence_no="L", insurance_until=INSURED) for i in range(2)]
        from dataclasses import asdict
        q = pricing.build_quote("43290", "33000", "LTL", 6, 2400)
        self.db.save_quote("q1", {"quote": asdict(q), "shipment": {}})
        self.db.save_booking(
            tracking_code="FR-AAAAAAAAAAAA", quote_id="q1", status="sourcing",
            customer={"name": "C", "company": "C", "email": "c@exemple.fr", "phone": "0600000000"},
            shipment={"origin": "43290", "destination": "33000", "mode": "LTL", "pallets": 6, "weight_kg": 2400,
                      "pickup_date": (date.today() + timedelta(days=3)).isoformat(), "pickup_address": "a",
                      "delivery_address": "b", "goods": "g"},
            customer_price_ht=q.price_ht, agent_log={})
        self.b = self.db.booking_by_code("FR-AAAAAAAAAAAA")
        self.price = offers.opening_price(q)
        for c in self.cids:
            self.db.add_offer(self.b["id"], c, self.price)

    def tearDown(self):
        if self.demo is None:
            os.environ.pop("FRETRAU_DEMO", None)
        else:
            os.environ["FRETRAU_DEMO"] = self.demo

    def test_plain_yes_accepts_at_our_price_only(self):
        r = email_agent.handle(self.db, "FR-AAAAAAAAAAAA", self.cids[0], "D'accord, on prend ce chargement.")
        self.assertEqual((r["decision"], r["price"]), ("accepted", self.price))

    def test_yes_without_an_offer_is_never_an_assignment(self):
        stranger = self.db.add_carrier(source="candidature", status="verified", name="X", siret="9", base_place="43200",
                                       licence_no="L", insurance_until=INSURED)
        r = email_agent.handle(self.db, "FR-AAAAAAAAAAAA", stranger, "ok on prend")
        self.assertEqual(r["decision"], "escalate")
        self.assertIsNone(self.db.booking_by_code("FR-AAAAAAAAAAAA")["carrier_id"])

    def test_decline_closes_offer_and_triggers_immediate_resourcing(self):
        for c in self.cids:
            self.assertEqual(email_agent.handle(self.db, "FR-AAAAAAAAAAAA", c, "Pas disponible, désolé")["decision"], "declined")
        self.assertEqual({o["status"] for o in self.db.offers_for_booking(self.b["id"])}, {"declined"})
        r = watch.run(self.db, "http://x")                    # sans attendre le délai : plus personne ne réfléchit
        self.assertEqual(r["escalated"], 1)                   # aucun autre transporteur vérifié : un humain reprend


class TestDataSafety(unittest.TestCase):
    def test_backup_is_a_consistent_verified_copy(self):
        with tempfile.TemporaryDirectory() as d:
            db = DB(os.path.join(d, "live.db"))
            self.assertEqual(db.conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            db.audit("test", "a", "b")
            dest = os.path.join(d, "copie.db")
            self.assertTrue(db.backup_to(dest))
            self.assertTrue(db.integrity_ok())
            copy = sqlite3.connect(dest)
            self.assertEqual(copy.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 1)
            copy.close()

    def test_purge_keeps_booked_quotes(self):
        db = DB()
        db.save_quote("vieux", {"quote": {}, "shipment": {}})
        db.save_quote("reserve", {"quote": {}, "shipment": {}})
        db.conn.execute("UPDATE quotes SET created_at=?", (time.time() - 200 * 86400,))
        db.save_booking(tracking_code="FR-BBBBBBBBBBBB", quote_id="reserve", status="confirmed", customer={}, shipment={},
                        customer_price_ht=1.0, agent_log={})
        self.assertEqual(db.purge()["quotes"], 1)
        self.assertIsNotNone(db.get_quote("reserve", max_age_s=1e9))

    def test_tokens_are_single_use_hashed_and_expire(self):
        db = DB()
        aid = db.create_account("shipper", "a@exemple.fr", "x", "A", "A", "06")
        t = security.new_token()
        db.add_token(aid, "reset", security.token_hash(t), 3600)
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM tokens WHERE token_hash=?", (t,)).fetchone()[0], 0)
        self.assertIsNone(db.use_token("verify", security.token_hash(t)))          # mauvais usage
        self.assertEqual(db.use_token("reset", security.token_hash(t)), aid)
        self.assertIsNone(db.use_token("reset", security.token_hash(t)))           # déjà utilisé
        t2 = security.new_token()
        db.add_token(aid, "reset", security.token_hash(t2), -1)
        self.assertIsNone(db.use_token("reset", security.token_hash(t2)))          # expiré

    def test_password_rules(self):
        self.assertTrue(security.password_problem("court"))
        self.assertTrue(security.password_problem("aaaaaaaaaaaa"))
        self.assertTrue(security.password_problem("motdepasse1"))
        self.assertTrue(security.password_problem("jeanne.dupont99", "jeanne.dupont@exemple.fr"))
        self.assertEqual(security.password_problem(PW, "claire@exemple.fr"), "")


class TestAccounts(unittest.TestCase):
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
        for rl in ("RL_GLOBAL", "RL_QUOTE", "RL_BOOK", "RL_LOGIN", "RL_SIGNUP", "RL_FORGOT", "RL_TRACK"):
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

    def signup(self, email):
        body = {"name": "Claire", "company": "Client SAS", "email": email, "phone": "0600000000", "password": PW,
                "accept_terms": True}
        s, _, h = self.call("POST", "/api/account/signup", body)
        self.assertEqual(s, 201)
        return h["Set-Cookie"].split(";")[0]

    def link(self, email, name):
        """Jeton du dernier e-mail envoyé à cette adresse (dans la file d'envoi)."""
        mails = [m for m in self.server.DB_.queued_mails(500) if m["to_addr"] == email and name + "=" in m["body"]]
        return re.search(name + r"=([A-Za-z0-9_-]+)", mails[-1]["body"]).group(1)

    def guest_booking(self, email):
        pickup = (date.today() + timedelta(days=2)).isoformat()
        s, q, _ = self.call("POST", "/api/quote", {"origin": "Lyon", "destination": "Paris", "mode": "FTL",
                                                    "weight_kg": 20000, "pickup_date": pickup, "options": {}})
        s, r, _ = self.call("POST", "/api/book", {
            "quote_id": json.loads(q)["quote_id"], "accept_cgv": True, "pickup_address": "1 rue A", "delivery_address": "2 rue B",
            "goods": "Bois", "contact": {"name": "Claire", "company": "Client SAS", "email": email, "phone": "0600000000"}})
        self.assertEqual(s, 201, r)
        return json.loads(r)["tracking_code"]

    def test_terms_must_be_accepted_and_are_recorded(self):
        body = {"name": "A", "company": "A", "email": "sans-cgu@exemple.fr", "phone": "0600000000", "password": PW}
        self.assertEqual(self.call("POST", "/api/account/signup", body)[0], 422)
        self.signup("avec-cgu@exemple.fr")
        a = self.server.DB_.account_by_email("avec-cgu@exemple.fr")
        self.assertEqual(a["terms_version"], self.server.TERMS_VERSION)
        code = self.guest_booking("preuve@exemple.fr")
        cgv = json.loads(self.server.DB_.booking_by_code(code)["shipment"])["cgv"]
        self.assertEqual(cgv["version"], self.server.TERMS_VERSION)

    def test_email_verification_unlocks_guest_bookings(self):
        code = self.guest_booking("verif@exemple.fr")
        cookie = self.signup("verif@exemple.fr")
        mine = lambda: [b["tracking_code"] for b in json.loads(self.call("GET", "/api/my/bookings", cookie=cookie)[1])["bookings"]]  # noqa: E731
        self.assertEqual(mine(), [])                                   # adresse non prouvée : rien n'est montré
        self.assertEqual(self.call("POST", "/api/account/verify", {"token": "x" * 40})[0], 400)
        token = self.link("verif@exemple.fr", "verifier")
        self.assertEqual(self.call("POST", "/api/account/verify", {"token": token})[0], 200)
        self.assertEqual(self.call("POST", "/api/account/verify", {"token": token})[0], 400)   # usage unique
        self.assertEqual(mine(), [code])

    def test_password_reset_kills_old_sessions_and_reveals_nothing(self):
        old = self.signup("reset@exemple.fr")
        self.assertEqual(self.call("POST", "/api/account/forgot", {"email": "inconnu@exemple.fr"})[0], 200)
        self.assertEqual(self.call("POST", "/api/account/forgot", {"email": "reset@exemple.fr"})[0], 200)
        token = self.link("reset@exemple.fr", "reinitialiser")
        self.assertEqual(self.call("POST", "/api/account/reset", {"token": token, "password": "court"})[0], 422)
        self.assertEqual(self.call("POST", "/api/account/reset", {"token": token, "password": "Nouveau-secret-43"})[0], 200)
        self.assertEqual(self.call("POST", "/api/account/reset", {"token": token, "password": "Encore-un-autre-43"})[0], 400)
        self.assertIsNone(json.loads(self.call("GET", "/api/account/me", cookie=old)[1])["account"])   # session révoquée
        self.assertEqual(self.call("POST", "/api/account/login", {"email": "reset@exemple.fr", "password": PW})[0], 401)
        self.assertEqual(self.call("POST", "/api/account/login",
                                   {"email": "reset@exemple.fr", "password": "Nouveau-secret-43"})[0], 200)

    def test_change_password_requires_current_one(self):
        cookie = self.signup("change@exemple.fr")
        self.assertEqual(self.call("POST", "/api/account/password", {"current": "faux", "password": "Nouveau-secret-43"}, cookie)[0], 401)
        s, _, h = self.call("POST", "/api/account/password", {"current": PW, "password": "Nouveau-secret-43"}, cookie)
        self.assertEqual(s, 200)
        self.assertIsNone(json.loads(self.call("GET", "/api/account/me", cookie=cookie)[1])["account"])
        fresh = h["Set-Cookie"].split(";")[0]
        self.assertIsNotNone(json.loads(self.call("GET", "/api/account/me", cookie=fresh)[1])["account"])

    def test_export_then_erasure(self):
        cookie = self.signup("rgpd@exemple.fr")
        self.assertEqual(self.call("GET", "/api/account/export")[0], 401)
        s, body, h = self.call("GET", "/api/account/export", cookie=cookie)
        data = json.loads(body)
        self.assertEqual((s, data["compte"]["email"]), (200, "rgpd@exemple.fr"))
        self.assertNotIn("pw_hash", body.decode())
        self.assertIn("attachment", h["Content-Disposition"])
        self.assertEqual(self.call("POST", "/api/account/delete", {"password": "faux"}, cookie)[0], 401)
        self.assertEqual(self.call("POST", "/api/account/delete", {"password": PW}, cookie)[0], 200)
        self.assertIsNone(self.server.DB_.account_by_email("rgpd@exemple.fr"))
        self.assertIsNone(json.loads(self.call("GET", "/api/account/me", cookie=cookie)[1])["account"])
        self.assertEqual(self.call("POST", "/api/account/login", {"email": "rgpd@exemple.fr", "password": PW})[0], 401)
        self.assertTrue(self.server.DB_.verify_audit_chain()[0])

    def test_every_element_a_script_needs_exists_in_its_page(self):
        pages = {"/": "app.js", "/portail.html": "portail.js", "/transporteur.html": "transporteur.js", "/admin.html": "admin.js",
                 "/compte": "compte.js", "/tarifs": "tarifs.js", "/suivi": "suivi.js", "/contact": "contact.js"}
        for path, script in pages.items():
            html = self.call("GET", path)[1].decode()
            js = open(os.path.join(ROOT, "web", script), encoding="utf-8").read()
            used = set(re.findall(r'\$\("([a-z0-9-]+)"\)', js))
            for pair in re.findall(r'onSubmit\("([a-z0-9-]+)", "([a-z0-9-]+)"', js):
                used.update(pair)
            for ident in used:
                created = f'id: "{ident}"' in js or re.search(r'field\("[^"]*", "' + ident + '"', js)   # créé par le script
                self.assertTrue(f'id="{ident}"' in html or created, f"{script} utilise #{ident}, absent de {path}")

    def test_legal_pages_exist_and_flag_missing_company_details(self):
        for path in ("/mentions-legales", "/cgu", "/cgv", "/confidentialite", "/compte"):
            s, body, _ = self.call("GET", path)
            self.assertEqual(s, 200, path)
            self.assertNotIn("<script>", body.decode())
        mentions = self.call("GET", "/mentions-legales")[1].decode()
        self.assertIn("Document provisoire", mentions)
        self.assertIn("à renseigner]", mentions)
        home = self.call("GET", "/")[1].decode()
        for link in ('href="/cgv"', 'href="/confidentialite"', 'href="/mentions-legales"'):
            self.assertIn(link, home)


if __name__ == "__main__":
    unittest.main()
