"""Couche SQLite. Toutes les requêtes sont paramétrées (pas d'injection SQL).

Le journal d'audit est « chaîné » : chaque ligne contient le hachage SHA-256 de la précédente.
Toute modification ou suppression a posteriori est détectable avec verify_audit_chain().
"""
import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime

_lock = threading.RLock()
GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_code TEXT UNIQUE NOT NULL, quote_id TEXT NOT NULL, created_at REAL NOT NULL,
    status TEXT NOT NULL, customer TEXT NOT NULL, shipment TEXT NOT NULL,
    carrier_id INTEGER, carrier_name TEXT, carrier_price REAL,
    customer_price_ht REAL NOT NULL, agent_log TEXT NOT NULL, account_id INTEGER
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, detail TEXT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE NOT NULL, year INTEGER NOT NULL,
    seq INTEGER NOT NULL, booking_id INTEGER UNIQUE NOT NULL, issued_at REAL NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, to_addr TEXT NOT NULL,
    subject TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL, error TEXT
);
CREATE TABLE IF NOT EXISTS inbound (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, carrier_id INTEGER,
    received_at REAL NOT NULL, raw TEXT NOT NULL, parsed_amount REAL, decision TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL,
    name TEXT NOT NULL, company TEXT NOT NULL, phone TEXT NOT NULL, carrier_id INTEGER, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS carriers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, status TEXT NOT NULL,
    name TEXT NOT NULL, siret TEXT UNIQUE, licence_no TEXT, insurance_until TEXT, base_place TEXT NOT NULL,
    modes TEXT NOT NULL, europe INTEGER NOT NULL DEFAULT 0, equipment TEXT NOT NULL DEFAULT '',
    email TEXT, phone TEXT, rating REAL NOT NULL DEFAULT 4.0, reliability REAL NOT NULL DEFAULT 0.9,
    km_base REAL, created_at REAL NOT NULL, verified_at REAL, note TEXT
);
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, carrier_id INTEGER NOT NULL,
    price REAL NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(booking_id, carrier_id)
);
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, ts REAL NOT NULL,
    step TEXT NOT NULL, note TEXT, actor TEXT NOT NULL, UNIQUE(booking_id, step)
);
CREATE TABLE IF NOT EXISTS payables (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER UNIQUE NOT NULL, carrier_id INTEGER NOT NULL,
    amount REAL NOT NULL, pod_at REAL NOT NULL, due_on TEXT NOT NULL, status TEXT NOT NULL, paid_at REAL
);
CREATE TABLE IF NOT EXISTS lane_stats (
    lane TEXT PRIMARY KEY, n INTEGER NOT NULL, ratio REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS price_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, account_id INTEGER NOT NULL, quote_id TEXT NOT NULL,
    competitor_price REAL NOT NULL, note TEXT, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inbound_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, received_at REAL NOT NULL, from_addr TEXT NOT NULL, raw TEXT NOT NULL,
    quote_id TEXT, status TEXT NOT NULL
);
"""
CARRIER_ID_BASE = 1000      # les identifiants 1 à 999 sont réservés au réseau de démonstration


def _audit_hash(prev, ts, actor, action, detail):
    return hashlib.sha256(f"{prev}|{ts!r}|{actor}|{action}|{detail}".encode()).hexdigest()


class DB:
    def __init__(self, path=":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with _lock:
            self.conn.executescript(SCHEMA)
            cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(bookings)")]
            if "account_id" not in cols:                       # base créée par une version antérieure
                self.conn.execute("ALTER TABLE bookings ADD COLUMN account_id INTEGER")
            if not self.conn.execute("SELECT 1 FROM sqlite_sequence WHERE name='carriers'").fetchone():
                self.conn.execute("INSERT INTO sqlite_sequence(name, seq) VALUES ('carriers', ?)", (CARRIER_ID_BASE,))
            self.conn.commit()

    def _exec(self, sql, params=()):
        with _lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def _all(self, sql, params=()):
        with _lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # ---- devis / réservations ----
    def save_quote(self, quote_id, payload):
        self._exec("INSERT INTO quotes(id, created_at, payload) VALUES (?,?,?)",
                   (quote_id, time.time(), json.dumps(payload)))

    def get_quote(self, quote_id, max_age_s=86400):
        rows = self._all("SELECT * FROM quotes WHERE id=?", (quote_id,))
        if not rows or time.time() - rows[0]["created_at"] > max_age_s:
            return None
        return json.loads(rows[0]["payload"])

    def save_booking(self, **b):
        self._exec(
            """INSERT INTO bookings(tracking_code, quote_id, created_at, status, customer, shipment,
               carrier_id, carrier_name, carrier_price, customer_price_ht, agent_log, account_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (b["tracking_code"], b["quote_id"], time.time(), b["status"],
             json.dumps(b["customer"]), json.dumps(b["shipment"]), b.get("carrier_id"),
             b.get("carrier_name"), b.get("carrier_price"), b["customer_price_ht"],
             json.dumps(b["agent_log"]), b.get("account_id")))

    def assign_carrier(self, code, carrier_id, carrier_name, price, agent_log):
        return self._exec("UPDATE bookings SET status='confirmed', carrier_id=?, carrier_name=?, carrier_price=?, "
                   "agent_log=? WHERE tracking_code=? AND status IN ('pending_human','sourcing')",
                          (carrier_id, carrier_name, price, json.dumps(agent_log), code)).rowcount > 0

    def booking_exists_for_quote(self, quote_id):
        return bool(self._all("SELECT 1 FROM bookings WHERE quote_id=?", (quote_id,)))

    def booking_by_code(self, code):
        rows = self._all("SELECT * FROM bookings WHERE tracking_code=?", (code,))
        return rows[0] if rows else None

    def booking_by_id(self, bid):
        rows = self._all("SELECT * FROM bookings WHERE id=?", (bid,))
        return rows[0] if rows else None

    def list_bookings(self, limit=200):
        return self._all("SELECT id, tracking_code, created_at, status, carrier_name, carrier_price, "
                         "customer_price_ht, shipment FROM bookings ORDER BY id DESC LIMIT ?", (limit,))

    def anonymize_booking(self, code):
        """RGPD : efface les données personnelles, conserve les données comptables."""
        anon = json.dumps({"name": "ANONYMISÉ", "company": "ANONYMISÉ", "email": "anonymise@invalid", "phone": "0"})
        cur = self._exec("UPDATE bookings SET customer=? WHERE tracking_code=?", (anon, code))
        if cur.rowcount:
            b = self.booking_by_code(code)
            s = json.loads(b["shipment"])
            for k in ("pickup_address", "delivery_address", "goods"):
                s[k] = "ANONYMISÉ"
            self._exec("UPDATE bookings SET shipment=? WHERE tracking_code=?", (json.dumps(s), code))
            self._exec("DELETE FROM outbox WHERE body LIKE ?", (f"%{code}%",))
        return cur.rowcount > 0

    # ---- audit chaîné ----
    def audit(self, actor, action, detail=""):
        detail = (detail or "")[:500]
        with _lock:
            row = self.conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            ts = time.time()
            h = _audit_hash(prev, ts, actor, action, detail)
            self.conn.execute("INSERT INTO audit_log(ts, actor, action, detail, prev_hash, hash) VALUES (?,?,?,?,?,?)",
                              (ts, actor, action, detail, prev, h))
            self.conn.commit()

    def audit_tail(self, limit=50):
        return self._all("SELECT ts, actor, action, detail FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

    def verify_audit_chain(self):
        """True si la chaîne est intacte ; sinon (False, id de la première ligne altérée)."""
        prev = GENESIS
        for r in self._all("SELECT * FROM audit_log ORDER BY id ASC"):
            if r["prev_hash"] != prev or r["hash"] != _audit_hash(prev, r["ts"], r["actor"], r["action"], r["detail"]):
                return False, r["id"]
            prev = r["hash"]
        return True, None

    # ---- factures (numérotation séquentielle sans trou, par année) ----
    def get_or_create_invoice(self, booking_id, data):
        with _lock:
            row = self.conn.execute("SELECT * FROM invoices WHERE booking_id=?", (booking_id,)).fetchone()
            if row:
                return json.loads(row["data"])
            year = datetime.now().year
            seq = (self.conn.execute("SELECT COALESCE(MAX(seq),0) FROM invoices WHERE year=?", (year,)).fetchone()[0]) + 1
            number = f"FA-{year}-{seq:05d}"
            data = dict(data, number=number, issued_on=datetime.now().date().isoformat())
            self.conn.execute("INSERT INTO invoices(number, year, seq, booking_id, issued_at, data) VALUES (?,?,?,?,?,?)",
                              (number, year, seq, booking_id, time.time(), json.dumps(data)))
            self.conn.commit()
            return data

    # ---- e-mails ----
    def queue_mail(self, to_addr, subject, body):
        self._exec("INSERT INTO outbox(created_at, to_addr, subject, body, status) VALUES (?,?,?,?, 'queued')",
                   (time.time(), to_addr, subject, body))

    def queued_mails(self, limit=50):
        return self._all("SELECT * FROM outbox WHERE status='queued' ORDER BY id LIMIT ?", (limit,))

    def mark_mail(self, mail_id, status, error=None):
        self._exec("UPDATE outbox SET status=?, error=? WHERE id=?", (status, (error or "")[:300], mail_id))

    def list_outbox(self, limit=30):
        return self._all("SELECT id, created_at, to_addr, subject, status FROM outbox ORDER BY id DESC LIMIT ?", (limit,))

    # ---- réponses entrantes des transporteurs ----
    def add_inbound(self, booking_id, carrier_id, raw, amount, decision):
        self._exec("INSERT INTO inbound(booking_id, carrier_id, received_at, raw, parsed_amount, decision) VALUES (?,?,?,?,?,?)",
                   (booking_id, carrier_id, time.time(), raw[:2000], amount, decision))

    def list_inbound(self, booking_id):
        return self._all("SELECT received_at, carrier_id, parsed_amount, decision, raw FROM inbound "
                         "WHERE booking_id=? ORDER BY id", (booking_id,))

    # ---- comptes (expéditeurs et transporteurs) ----
    def create_account(self, role, email, pw_hash, name, company, phone, carrier_id=None):
        try:
            return self._exec("INSERT INTO accounts(role, email, pw_hash, name, company, phone, carrier_id, created_at) "
                              "VALUES (?,?,?,?,?,?,?,?)",
                              (role, email, pw_hash, name, company, phone, carrier_id, time.time())).lastrowid
        except sqlite3.IntegrityError:
            return None

    def account_by_email(self, email):
        rows = self._all("SELECT * FROM accounts WHERE email=?", (email,))
        return rows[0] if rows else None

    def account_by_id(self, aid):
        rows = self._all("SELECT * FROM accounts WHERE id=?", (aid,))
        return rows[0] if rows else None

    def bookings_for_account(self, account_id):
        """Réservations passées en étant connecté. Aucun rattachement par adresse e-mail : tant que les adresses
        ne sont pas vérifiées, cela exposerait les envois d'un tiers à quiconque s'inscrit avec son adresse."""
        return self._all("SELECT * FROM bookings WHERE account_id=? ORDER BY id DESC LIMIT 500", (account_id,))

    # ---- transporteurs réels (prospects, candidats, vérifiés) ----
    def add_carrier(self, **c):
        try:
            return self._exec(
                "INSERT INTO carriers(source, status, name, siret, licence_no, insurance_until, base_place, modes, europe, "
                "equipment, email, phone, km_base, created_at, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c["source"], c["status"], c["name"], c.get("siret"), c.get("licence_no"), c.get("insurance_until"),
                 c["base_place"], c.get("modes", "FTL,LTL"), int(bool(c.get("europe"))), c.get("equipment", ""),
                 c.get("email"), c.get("phone"), c.get("km_base"), time.time(), c.get("note"))).lastrowid
        except sqlite3.IntegrityError:
            return None

    def add_prospects(self, rows):
        """Import en masse (une seule transaction). Les SIRET déjà présents sont ignorés."""
        with _lock:
            before = self.conn.total_changes
            self.conn.executemany(
                "INSERT OR IGNORE INTO carriers(source, status, name, siret, base_place, modes, km_base, created_at, note) "
                "VALUES ('registre', 'prospect', ?,?,?,?,?,?,?)",
                [(r["name"], r["siret"], r["base_place"], r["modes"], r["km_base"], time.time(), r.get("note")) for r in rows])
            self.conn.commit()
            return self.conn.total_changes - before

    def carrier_row(self, cid):
        rows = self._all("SELECT * FROM carriers WHERE id=?", (cid,))
        return rows[0] if rows else None

    def carrier_by_siret(self, siret):
        rows = self._all("SELECT * FROM carriers WHERE siret=?", (siret,))
        return rows[0] if rows else None

    def list_carriers(self, status=None, limit=200, search=None):
        sql, params = "SELECT * FROM carriers WHERE 1=1", []
        if status:
            sql += " AND status=?"
            params.append(status)
        if search:
            sql += " AND (name LIKE ? OR base_place LIKE ? OR siret LIKE ?)"
            params += [f"%{search}%", f"{search}%", f"{search}%"]
        return self._all(sql + " ORDER BY COALESCE(km_base, 1e9), id LIMIT ?", (*params, limit))

    def carrier_counts(self):
        return {r["status"]: r["n"] for r in self._all("SELECT status, COUNT(*) AS n FROM carriers GROUP BY status")}

    def update_carrier(self, cid, **fields):
        allowed = {"status", "licence_no", "insurance_until", "email", "phone", "modes", "europe", "equipment",
                   "note", "verified_at", "base_place", "name"}
        sets = [(k, v) for k, v in fields.items() if k in allowed]
        if not sets:
            return False
        sql = "UPDATE carriers SET " + ", ".join(f"{k}=?" for k, _ in sets) + " WHERE id=?"
        return self._exec(sql, (*[v for _, v in sets], cid)).rowcount > 0

    # ---- offres de chargement envoyées aux transporteurs ----
    def add_offer(self, booking_id, carrier_id, price):
        self._exec("INSERT OR IGNORE INTO offers(booking_id, carrier_id, price, status, created_at) VALUES (?,?,?, 'sent', ?)",
                   (booking_id, carrier_id, price, time.time()))

    def offers_for_carrier(self, carrier_id):
        return self._all("SELECT o.*, b.tracking_code, b.shipment, b.status AS booking_status FROM offers o "
                         "JOIN bookings b ON b.id=o.booking_id WHERE o.carrier_id=? ORDER BY o.id DESC LIMIT 100",
                         (carrier_id,))

    def offer(self, booking_id, carrier_id):
        rows = self._all("SELECT * FROM offers WHERE booking_id=? AND carrier_id=?", (booking_id, carrier_id))
        return rows[0] if rows else None

    def offers_for_booking(self, booking_id):
        return self._all("SELECT * FROM offers WHERE booking_id=? ORDER BY id", (booking_id,))

    def set_offer(self, booking_id, carrier_id, status, price=None):
        if price is None:
            self._exec("UPDATE offers SET status=? WHERE booking_id=? AND carrier_id=?", (status, booking_id, carrier_id))
        else:
            self._exec("UPDATE offers SET status=?, price=? WHERE booking_id=? AND carrier_id=?",
                       (status, price, booking_id, carrier_id))

    def close_other_offers(self, booking_id, winner_id):
        self._exec("UPDATE offers SET status='closed' WHERE booking_id=? AND carrier_id<>? AND status IN ('sent','countered')",
                   (booking_id, winner_id))

    def set_booking_status(self, code, status):
        self._exec("UPDATE bookings SET status=? WHERE tracking_code=?", (status, code))

    def bookings_by_status(self, statuses):
        marks = ",".join("?" for _ in statuses)
        return self._all(f"SELECT * FROM bookings WHERE status IN ({marks}) ORDER BY id DESC LIMIT 200", tuple(statuses))

    def bookings_for_carrier(self, carrier_id):
        return self._all("SELECT * FROM bookings WHERE carrier_id=? AND status='confirmed' ORDER BY id DESC LIMIT 200",
                         (carrier_id,))

    # ---- jalons de suivi réels ----
    def add_milestone(self, booking_id, step, actor, note=""):
        return self._exec("INSERT OR IGNORE INTO milestones(booking_id, ts, step, note, actor) VALUES (?,?,?,?,?)",
                          (booking_id, time.time(), step, (note or "")[:200], actor)).rowcount > 0

    def milestones(self, booking_id):
        return self._all("SELECT ts, step, note, actor FROM milestones WHERE booking_id=? ORDER BY id", (booking_id,))

    # ---- dettes transporteurs (paiement après preuve de livraison) ----
    def add_payable(self, booking_id, carrier_id, amount, due_on):
        self._exec("INSERT OR IGNORE INTO payables(booking_id, carrier_id, amount, pod_at, due_on, status) "
                   "VALUES (?,?,?,?,?, 'due')", (booking_id, carrier_id, amount, time.time(), due_on))

    def list_payables(self, carrier_id=None):
        sql = ("SELECT p.*, b.tracking_code, b.carrier_name FROM payables p JOIN bookings b ON b.id=p.booking_id"
               + (" WHERE p.carrier_id=?" if carrier_id else "") + " ORDER BY p.id DESC LIMIT 200")
        return self._all(sql, (carrier_id,) if carrier_id else ())

    def pay_payable(self, pid):
        return self._exec("UPDATE payables SET status='paid', paid_at=? WHERE id=? AND status='due'",
                          (time.time(), pid)).rowcount > 0

    # ---- apprentissage des prix par axe ----
    def lane_stat(self, lane):
        rows = self._all("SELECT * FROM lane_stats WHERE lane=?", (lane,))
        return rows[0] if rows else None

    def save_lane_stat(self, lane, n, ratio):
        self._exec("INSERT INTO lane_stats(lane, n, ratio, updated_at) VALUES (?,?,?,?) "
                   "ON CONFLICT(lane) DO UPDATE SET n=excluded.n, ratio=excluded.ratio, updated_at=excluded.updated_at",
                   (lane, n, ratio, time.time()))

    # ---- alignement de prix, demandes de devis reçues par e-mail ----
    def add_price_match(self, account_id, quote_id, competitor_price, note):
        self._exec("INSERT INTO price_matches(created_at, account_id, quote_id, competitor_price, note, status) "
                   "VALUES (?,?,?,?,?, 'open')", (time.time(), account_id, quote_id, competitor_price, (note or "")[:300]))

    def list_price_matches(self):
        return self._all("SELECT p.*, a.email, a.company FROM price_matches p JOIN accounts a ON a.id=p.account_id "
                         "ORDER BY p.id DESC LIMIT 100")

    def add_inbound_quote(self, from_addr, raw, quote_id, status):
        self._exec("INSERT INTO inbound_quotes(received_at, from_addr, raw, quote_id, status) VALUES (?,?,?,?,?)",
                   (time.time(), from_addr, raw[:4000], quote_id, status))

    def list_inbound_quotes(self, limit=30):
        return self._all("SELECT id, received_at, from_addr, quote_id, status FROM inbound_quotes ORDER BY id DESC LIMIT ?",
                         (limit,))
