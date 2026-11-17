import hashlib, hmac, json, os, sys, threading, time, unittest, urllib.request, urllib.error
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["FRETRAU_WEBHOOK_SECRET"] = os.environ.get("FRETRAU_WEBHOOK_SECRET", "secret-webhook-de-test")
os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")
from fretrau import calendar_fr, directory  # noqa: E402
from fretrau.agents import rfq  # noqa: E402
from fretrau.db import DB  # noqa: E402


def api_result(siren="123456789", state="A", lat="45.04", lon="4.17", naf="49.41A"):
    return {"siren": siren, "nom_complet": f"TRANSPORTS {siren}", "etat_administratif": state, "activite_principale": naf, "tranche_effectif_salarie": "11",
            "siege": {"libelle_commune": "MONISTROL-SUR-LOIRE", "code_postal": "43120", "departement": "43", "latitude": lat, "longitude": lon}}


class FakeResp:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return json.dumps(self.payload).encode()


class Directory(unittest.TestCase):
    def test_parse_filters_closed_and_invalid(self):
        self.assertEqual(directory.parse_company(api_result())["city"], "MONISTROL-SUR-LOIRE")
        self.assertIsNone(directory.parse_company(api_result(state="C")))
        self.assertIsNone(directory.parse_company(api_result(siren="12")))
        self.assertIsNone(directory.parse_company(api_result(siren="12345678x")))
        self.assertIsNone(directory.parse_company(api_result(lat=None, lon=None))["lat"])

    def test_pagination_and_idempotent_import_keeps_contacts(self):
        pages = {1: [api_result(str(100000000 + i)) for i in range(25)], 2: [api_result("200000001"), api_result("200000002", state="C")]}
        def opener(req, timeout=0):
            n = int(req.full_url.rsplit("page=", 1)[1].split("&")[0])
            return FakeResp({"results": pages.get(n, []), "total_pages": 2})
        db = DB(":memory:")
        self.assertEqual(directory.import_zone(db, ["43"], ("49.41A",), opener), 26)
        db.set_directory_contact("200000001", "a@transport.fr", "")
        self.assertEqual(directory.import_zone(db, ["43"], ("49.41A",), opener), 0)          # rien de nouveau
        self.assertEqual(db.directory_one("200000001")["email"], "a@transport.fr")             # contact conservé

    def test_network_error_propagates_cleanly(self):
        def boom(*a, **k): raise OSError("hors ligne")
        with self.assertRaises(OSError):
            list(directory.fetch("43", "49.41A", boom))


class Rfq(unittest.TestCase):
    def c(self, siren, lat, lon, **kw):
        base = {"siren": siren, "name": "T" + siren, "lat": lat, "lon": lon, "email": f"{siren}@t.fr", "size": "11", "optout": 0, "last_contacted": None}
        base.update(kw)
        return base

    def test_selection_rules(self):
        now = time.time()
        d = [self.c("1", 45.04, 4.17), self.c("2", 45.10, 4.20, optout=1), self.c("3", 45.1, 4.2, email=""), self.c("4", 48.85, 2.35),
             self.c("5", 45.2, 4.3, last_contacted=now - 3600), self.c("6", 45.3, 4.3, last_contacted=now - 9 * 86400), self.c("7", None, None)]
        ok, skipped = rfq.select(d, 45.04, 4.17, now)
        self.assertEqual([c["siren"] for c in ok], ["1", "6"])                      # le plus proche d'abord
        reasons = {s["siren"]: s["reason"] for s in skipped}
        self.assertIn("désinscrit", reasons["2"]); self.assertIn("e-mail", reasons["3"]); self.assertIn("km", reasons["4"])
        self.assertIn("7 jours", reasons["5"]); self.assertIn("position", reasons["7"])

    def test_max_targets(self):
        d = [self.c(str(i), 45.04 + i * 0.001, 4.17) for i in range(30)]
        self.assertEqual(len(rfq.select(d, 45.04, 4.17, time.time(), max_targets=10)[0]), 10)

    def test_draft_is_anonymous_and_has_optout(self):
        ref = rfq.new_ref()
        subj, body = rfq.draft(ref, {"origin": "Lyon", "destination": "Paris", "pickup_date": "2026-11-20", "pallets": 33, "weight_kg": 15000, "mode": "FTL", "options": {"tail_lift": True}}, "ops@fretrau.fr")
        self.assertTrue(rfq.REF_RE.fullmatch(ref))
        self.assertIn(ref, subj); self.assertIn("STOP", body); self.assertIn("tail_lift", body)
        for forbidden in ("customer", "client", "@societe"):
            self.assertNotIn(forbidden, body.lower().replace("transporteur", ""))

    def test_read_reply(self):
        ref = "RFQ-ABCD2345"
        self.assertEqual(rfq.read_reply(f"Re: [{ref}] OK pour 640 € HT")[:2], (ref, 640.0))
        self.assertEqual(rfq.read_reply("STOP")[2], True)
        self.assertIsNone(rfq.read_reply(f"[{ref}] entre 600 et 700 euros")[1])         # ambigu : jamais deviné
        self.assertIsNone(rfq.read_reply("bonjour")[0])


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
        for rl in (self.server.RL_QUOTE, self.server.RL_GLOBAL, self.server.RL_TRACK, self.server.RL_BOOK, self.server.RL_FORM, self.server.RL_LOGIN):
            rl.hits.clear()
        self.cookie = None

    def call(self, method, path, body=None, headers=None, raw=None, admin=False):
        h = {"Content-Type": "application/json", **(headers or {})}
        if admin:
            lg = urllib.request.Request(self.base + "/api/admin/login", method="POST", headers={**h, "X-Requested-With": "fretrau"},
                                        data=json.dumps({"user": "admin", "password": os.environ["FRETRAU_ADMIN_PASSWORD"]}).encode())
            with urllib.request.urlopen(lg) as r:
                h.update({"Cookie": r.headers["Set-Cookie"].split(";")[0], "X-Requested-With": "fretrau"})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, method=method, headers=h, data=data)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def signed(self, path, payload):
        raw = json.dumps(dict(payload, ts=time.time())).encode()
        return self.call("POST", path, headers={"X-Signature": hmac.new(self.server.WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()}, raw=raw)

    def test_full_rfq_flow(self):
        db = self.server.DB_
        for i, (sn, em) in enumerate([("900000001", "a@trans-lyon.fr"), ("900000002", "b@trans-lyon.fr"), ("900000003", None)]):
            db.upsert_directory({"siren": sn, "name": f"TRANSPORTS {i}", "city": "Lyon", "postcode": "69001", "dept": "69", "lat": 45.76 + i * 0.01, "lon": 4.84, "naf": "49.41A", "size": "11"})
            if em:
                db.set_directory_contact(sn, em, "")
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4)).isoformat()
        s, q = self.call("POST", "/api/quote", {"origin": "Lyon", "destination": "Paris", "mode": "FTL", "pallets": 33, "weight_kg": 15000, "pickup_date": pk, "options": {}})
        self.assertEqual(s, 200, q)
        self.assertEqual(self.call("POST", "/api/admin/rfq/draft", {"quote_id": q["quote_id"]})[0], 401)         # admin seulement
        s, dr = self.call("POST", "/api/admin/rfq/draft", {"quote_id": q["quote_id"], "radius_km": 50}, admin=True)
        self.assertEqual(s, 200, dr)
        self.assertEqual({t["siren"] for t in dr["targets"]}, {"900000001", "900000002"})
        self.assertTrue(any(x["siren"] == "900000003" for x in dr["skipped"]))
        self.assertEqual(len([m for m in db.queued_mails(1000) if "RFQ-" in m["subject"]]), 0)   # brouillon : rien n'est parti
        s, r = self.call("POST", "/api/admin/rfq/send", {"id": dr["id"]}, admin=True)
        self.assertEqual((s, r["sent"]), (200, 2))
        self.assertEqual(len([m for m in db.queued_mails(1000) if dr["ref"] in m["subject"]]), 2)
        self.assertEqual(self.call("POST", "/api/admin/rfq/send", {"id": dr["id"]}, admin=True)[0], 404)      # pas de double envoi
        ref = dr["ref"]
        s, r = self.signed("/api/webhook/rfq-reply", {"from_email": "a@trans-lyon.fr", "text": f"Re: [{ref}] Bonjour, 610 € HT."})
        self.assertEqual((s, r["decision"], r["amount"]), (200, "recorded", 610.0))
        self.assertEqual(self.signed("/api/webhook/rfq-reply", {"from_email": "intrus@x.fr", "text": f"[{ref}] 100 €"})[1]["decision"], "ignored")
        self.assertEqual(self.signed("/api/webhook/rfq-reply", {"from_email": "b@trans-lyon.fr", "text": f"[{ref}] prix : 590 € HT"})[1]["amount"], 590.0)
        s, lst = self.call("GET", "/api/admin/rfq", admin=True)
        me = next(x for x in lst["rfqs"] if x["ref"] == ref)
        self.assertEqual(me["best"], 590.0)
        self.assertFalse(lst["calibration"]["reliable"])                       # 2 réponses seulement : jamais présenté comme fiable
        # STOP : désinscription immédiate
        self.assertEqual(self.signed("/api/webhook/rfq-reply", {"from_email": "a@trans-lyon.fr", "text": "STOP"})[1]["decision"], "optout")
        self.assertEqual(db.directory_one("900000001")["optout"], 1)
        self.assertEqual(self.call("POST", "/api/webhook/rfq-reply", {"text": "x", "from_email": "a@b.fr", "ts": time.time()}, headers={"X-Signature": "00"})[0], 401)


if __name__ == "__main__":
    unittest.main()
