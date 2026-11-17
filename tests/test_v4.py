import gzip
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from fretrau.db import DB  # noqa: E402
import backup as bk  # noqa: E402
import maintenance  # noqa: E402
import legal_texts  # noqa: E402,F401


def make_booking(db, code="FR-AAAAAAAAAAAA", age_days=0):
    db.save_booking(tracking_code=code, quote_id="q" + code, status="confirmed",
                    customer={"name": "Jean Dupont", "company": "ACME", "email": "j@acme.fr", "phone": "0102030405"},
                    shipment={"origin": "Lyon", "destination": "Paris", "pickup_address": "1 rue X", "delivery_address": "2 rue Y",
                              "goods": "carrelage", "site_contact_name": "Marie", "site_contact_phone": "0607080910",
                              "loading_notes": "portail rouge"},
                    carrier_id=1, carrier_name="T", carrier_price=100.0, customer_price_ht=120.0, agent_log=[])
    if age_days:
        db._exec("UPDATE bookings SET created_at=? WHERE tracking_code=?", (time.time() - age_days * 86400, code))


class Rgpd(unittest.TestCase):
    def test_anonymize_clears_all_personal_fields(self):
        db = DB()
        make_booking(db)
        self.assertTrue(db.anonymize_booking("FR-AAAAAAAAAAAA"))
        b = db.booking_by_code("FR-AAAAAAAAAAAA")
        txt = b["customer"] + b["shipment"]
        for secret in ("Dupont", "acme", "0102030405", "Marie", "0607080910", "portail", "rue X", "carrelage"):
            self.assertNotIn(secret.lower(), txt.lower())

    def test_export_contains_personal_data(self):
        db = DB()
        make_booking(db)
        d = db.export_booking("FR-AAAAAAAAAAAA")
        self.assertEqual(d["customer"]["email"], "j@acme.fr")
        self.assertEqual(d["shipment"]["site_contact_name"], "Marie")
        self.assertIsNone(db.export_booking("FR-BBBBBBBBBBBB"))

    def test_retention_anonymizes_only_old(self):
        db = DB()
        make_booking(db, "FR-AAAAAAAAAAAA", age_days=6 * 365)
        make_booking(db, "FR-BBBBBBBBBBBB", age_days=10)
        res = maintenance.run(db, 5)
        self.assertEqual(res["bookings_anonymized"], 1)
        self.assertEqual(json.loads(db.booking_by_code("FR-BBBBBBBBBBBB")["customer"])["name"], "Jean Dupont")
        self.assertTrue(res["audit_intact"])

    def test_maintenance_detects_audit_tampering(self):
        db = DB()
        db.audit("a", "x", "1")
        db.audit("a", "y", "2")
        db._exec("UPDATE audit_log SET detail='falsifié' WHERE id=1")
        self.assertFalse(maintenance.run(db)["audit_intact"])


class Backup(unittest.TestCase):
    def test_backup_verify_restore_and_rotation(self):
        with tempfile.TemporaryDirectory() as d:
            dbp = os.path.join(d, "f.db")
            db = DB(dbp)
            make_booking(db)
            dest = os.path.join(d, "bk")
            outs = []
            for _ in range(3):
                outs.append(bk.backup(dbp, dest, keep=2))
                time.sleep(1.1)
            self.assertEqual(len([f for f in os.listdir(dest) if f.endswith(".db.gz")]), 2)
            last = outs[-1]
            self.assertTrue(bk.verify(last))
            self.assertEqual(oct(os.stat(last).st_mode & 0o777), "0o600")
            target = os.path.join(d, "restored.db")
            bk.restore(last, target)
            con = sqlite3.connect(target)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM bookings").fetchone()[0], 1)
            con.close()

    def test_corrupted_backup_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            dbp = os.path.join(d, "f.db")
            DB(dbp)
            out = bk.backup(dbp, os.path.join(d, "bk"))
            with open(out, "r+b") as f:
                f.seek(20)
                f.write(b"\x00\x00\x00")
            self.assertFalse(bk.verify(out))
            with self.assertRaises(SystemExit):
                bk.restore(out, os.path.join(d, "x.db"))


class Legal(unittest.TestCase):
    def test_pages_cover_required_topics(self):
        P = legal_texts.PAGES
        self.assertEqual(set(P), {"mentions-legales", "confidentialite", "cgu", "cgv", "cookies"})
        self.assertIn("30 jours", P["cgv"]["body"])
        self.assertIn("40 €", P["cgv"]["body"])
        self.assertIn("L133-6", P["cgv"]["body"])
        self.assertIn("72 heures", P["confidentialite"]["body"])
        self.assertIn("CNIL", P["confidentialite"]["body"])
        self.assertIn("Tout refuser", P["cookies"]["body"])
        self.assertIn("directeur de la publication", P["mentions-legales"]["body"].lower())

    def test_every_placeholder_is_declared_in_company_json(self):
        company = json.load(open(os.path.join(ROOT, "config", "company.json"), encoding="utf-8"))
        for slug, p in legal_texts.PAGES.items():
            for key in re.findall(r"\[\[(\w+)\]\]", p["body"]):
                self.assertIn(key, company, f"{slug}: [[{key}]] absent de company.json")

    def test_generated_pages_have_no_unresolved_template_tags(self):
        for slug in legal_texts.PAGES:
            with open(os.path.join(ROOT, "web", "legal", slug + ".html"), encoding="utf-8") as f:
                self.assertNotIn("[[", f.read())


class FrontEnd(unittest.TestCase):
    def test_no_inline_script_or_secret_in_web(self):
        bad = re.compile(r"(sk-ant-|ANTHROPIC_API_KEY|FRETRAU_SECRET|api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{12,})", re.I)
        for base, _, files in os.walk(os.path.join(ROOT, "web")):
            for fn in files:
                p = os.path.join(base, fn)
                txt = open(p, encoding="utf-8", errors="ignore").read()
                self.assertIsNone(bad.search(txt), p)
                if fn.endswith(".html"):
                    self.assertNotRegex(txt, r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>", p)
                    self.assertNotRegex(txt, r"\son\w+\s*=", p)

    def test_booking_form_has_all_required_server_fields(self):
        html_ = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
        js = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
        for f in ("pickup_window", "delivery_window", "site_contact_name", "site_contact_phone", "loading_notes", "goods_value_eur", "accept_cgv"):
            self.assertIn(f, js)
        for i in ("pw-start", "dw-end", "sc-name", "sc-phone", "goods-value", "deliver-by", "cookie-manage"):
            self.assertIn(f'id="{i}"', html_)
        self.assertIn("/legal/cgv.html", html_)


# ---------- RBAC sur un vrai serveur ----------
import threading  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")


class Rbac(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        import manage_users
        from fretrau import security
        cls.server, cls.mu, cls.sec = server, manage_users, security
        cls.httpd = server.make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.secrets = {}
        for name, role in (("alice", "ops"), ("bob", "finance"), ("root.admin", "admin")):
            cls.secrets[name] = manage_users.main(["add", name, role], db=server.DB_, password="Mot-de-passe-Solide-42")

    @classmethod
    def tearDownClass(cls):
        cls.server.DB_._exec("DELETE FROM users")
        cls.httpd.shutdown()

    def setUp(self):  # les limiteurs de débit sont testés ailleurs ; on les vide pour isoler chaque test
        self.server.RL_LOGIN.hits.clear()
        self.server.RL_GLOBAL.hits.clear()
        self.server.GUARD.__dict__.update({k: ({} if isinstance(v, dict) else v) for k, v in self.server.GUARD.__dict__.items()})

    def call(self, method, path, body=None, cookie=None):
        h = {"Content-Type": "application/json", "X-Requested-With": "fretrau"}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(self.base + path, method=method, headers=h,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read()), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def login(self, name, pw="Mot-de-passe-Solide-42", totp=True):
        body = {"user": name, "password": pw}
        if totp:
            body["totp"] = self.sec.totp(self.secrets[name])
        st, _, h = self.call("POST", "/api/admin/login", body)
        return st, (h.get("Set-Cookie") or "").split(";")[0]

    def test_roles(self):
        st, ops = self.login("alice")
        self.assertEqual(st, 200)
        self.assertEqual(self.call("GET", "/api/admin/me", cookie=ops)[1]["role"], "ops")
        self.assertEqual(self.call("GET", "/api/admin/outbox", cookie=ops)[0], 200)
        self.assertEqual(self.call("GET", "/api/admin/invoice/1", cookie=ops)[0], 403)
        self.assertEqual(self.call("GET", "/api/admin/gdpr/export/FR-AAAAAAAAAAAA", cookie=ops)[0], 403)
        st, fin = self.login("bob")
        self.assertEqual(self.call("GET", "/api/admin/outbox", cookie=fin)[0], 403)
        self.assertEqual(self.call("GET", "/api/admin/stats", cookie=fin)[0], 200)
        st, adm = self.login("root.admin")
        self.assertEqual(self.call("GET", "/api/admin/gdpr/export/FR-AAAAAAAAAAAA", cookie=adm)[0], 404)  # autorisé, réservation absente

    def test_mfa_required_and_wrong_password(self):
        self.assertEqual(self.login("alice", totp=False)[0], 401)
        self.assertEqual(self.login("alice", pw="mauvais-mot-de-passe-1")[0], 401)

    def test_env_admin_disabled_once_users_exist(self):
        st, _, _ = self.call("POST", "/api/admin/login", {"user": "admin", "password": "mot-de-passe-de-test-long"})
        self.assertEqual(st, 401)

    def test_disable_cuts_access_immediately(self):
        self.mu.main(["add", "temp.user", "ops"], db=self.server.DB_, password="Mot-de-passe-Solide-42")
        # secret non conservé par main() pour ce compte : on le relit en base
        secret = self.server.DB_.get_user("temp.user")["totp_secret"]
        self.secrets["temp.user"] = secret
        st, ck = self.login("temp.user")
        self.assertEqual(st, 200)
        self.assertEqual(self.call("GET", "/api/admin/me", cookie=ck)[0], 200)
        self.mu.main(["disable", "temp.user"], db=self.server.DB_)
        self.assertEqual(self.call("GET", "/api/admin/me", cookie=ck)[0], 401)

    def test_actions_are_audited_under_the_real_user(self):
        _, ck = self.login("root.admin")
        self.call("GET", "/api/admin/gdpr/export/FR-ZZZZZZZZZZZZ", cookie=ck)
        _, ops = self.login("alice")
        self.call("GET", "/api/admin/invoice/1", cookie=ops)   # refusé
        actors = {r["actor"] + ":" + r["action"] for r in self.server.DB_.audit_tail(50)}
        self.assertIn("alice:forbidden", actors)
        self.assertIn("root.admin:admin_login", actors)
        self.assertTrue(self.server.DB_.verify_audit_chain()[0])


if __name__ == "__main__":
    unittest.main()
