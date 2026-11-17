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
    customer_price_ht REAL NOT NULL, agent_log TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, ts REAL NOT NULL,
    kind TEXT NOT NULL, source TEXT NOT NULL, detail TEXT
);
CREATE TABLE IF NOT EXISTS carrier_payables (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER UNIQUE NOT NULL, carrier_id INTEGER, carrier_name TEXT,
    amount_ht REAL NOT NULL, pod_at REAL NOT NULL, due_on TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'due',
    paid_at REAL, payment_ref TEXT
);
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, totp_secret TEXT, role TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS inbound (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, carrier_id INTEGER,
    received_at REAL NOT NULL, raw TEXT NOT NULL, parsed_amount REAL, decision TEXT NOT NULL
);
"""


def _audit_hash(prev, ts, actor, action, detail):
    return hashlib.sha256(f"{prev}|{ts!r}|{actor}|{action}|{detail}".encode()).hexdigest()


class DB:
    def __init__(self, path=":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with _lock:
            self.conn.executescript(SCHEMA)

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

    def update_quote(self, quote_id, payload):
        self._exec("UPDATE quotes SET payload=? WHERE id=?", (json.dumps(payload), quote_id))

    def get_quote(self, quote_id, max_age_s=86400):
        """max_age_s=None : sans limite (contrôles internes sur une réservation existante)."""
        rows = self._all("SELECT * FROM quotes WHERE id=?", (quote_id,))
        if not rows or (max_age_s is not None and time.time() - rows[0]["created_at"] > max_age_s):
            return None
        return json.loads(rows[0]["payload"])

    def purge_quotes(self, older_than_s):
        return self._exec("DELETE FROM quotes WHERE created_at < ? AND id NOT IN (SELECT quote_id FROM bookings)",
                          (time.time() - older_than_s,)).rowcount

    def save_booking(self, **b):
        self._exec(
            """INSERT INTO bookings(tracking_code, quote_id, created_at, status, customer, shipment,
               carrier_id, carrier_name, carrier_price, customer_price_ht, agent_log)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (b["tracking_code"], b["quote_id"], time.time(), b["status"],
             json.dumps(b["customer"]), json.dumps(b["shipment"]), b.get("carrier_id"),
             b.get("carrier_name"), b.get("carrier_price"), b["customer_price_ht"],
             json.dumps(b["agent_log"])))

    def assign_carrier(self, code, carrier_id, carrier_name, price, agent_log):
        self._exec("UPDATE bookings SET status='confirmed', carrier_id=?, carrier_name=?, carrier_price=?, "
                   "agent_log=? WHERE tracking_code=? AND status='pending_human'",
                   (carrier_id, carrier_name, price, json.dumps(agent_log), code))

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
            for k in ("pickup_address", "delivery_address", "goods", "site_contact_name", "site_contact_phone",
                      "loading_notes"):
                if k in s and s[k]:
                    s[k] = "ANONYMISÉ"
            self._exec("UPDATE bookings SET shipment=? WHERE tracking_code=?", (json.dumps(s), code))
            self._exec("DELETE FROM outbox WHERE body LIKE ?", (f"%{code}%",))
            self._exec("DELETE FROM inbound WHERE booking_id=?", (b["id"],))
        return cur.rowcount > 0

    def export_booking(self, code):
        """RGPD art. 15/20 : toutes les données personnelles liées à une réservation (JSON portable)."""
        b = self.booking_by_code(code)
        if not b:
            return None
        inv = self._all("SELECT number, issued_at FROM invoices WHERE booking_id=?", (b["id"],))
        mails = self._all("SELECT created_at, to_addr, subject FROM outbox WHERE body LIKE ?", (f"%{code}%",))
        return {
            "tracking_code": b["tracking_code"], "created_at": b["created_at"], "status": b["status"],
            "customer": json.loads(b["customer"]), "shipment": json.loads(b["shipment"]),
            "price_ht": b["customer_price_ht"],
            "invoices": [dict(r) for r in inv], "emails_sent": [dict(r) for r in mails],
        }

    # ---- suivi réel : événements transporteur / opérateur ----
    EVENT_ORDER = ("assigned", "loaded", "in_transit", "arrived", "delivered")

    def add_event(self, booking_id, kind, source, detail="", ts=None):
        """Événement de suivi. Idempotent (même type deux fois = ignoré) et monotone (on ne revient pas en arrière).
        Renvoie 'added' | 'duplicate' | 'out_of_order'."""
        if kind not in self.EVENT_ORDER:
            raise ValueError("événement inconnu")
        with _lock:
            rows = self.conn.execute("SELECT kind FROM events WHERE booking_id=?", (booking_id,)).fetchall()
            seen = {r["kind"] for r in rows}
            if kind in seen:
                return "duplicate"
            if seen and self.EVENT_ORDER.index(kind) < max(self.EVENT_ORDER.index(k) for k in seen):
                return "out_of_order"
            self.conn.execute("INSERT INTO events(booking_id, ts, kind, source, detail) VALUES (?,?,?,?,?)",
                              (booking_id, ts or time.time(), kind, source, (detail or "")[:200]))
            self.conn.commit()
        return "added"

    def events_for(self, booking_id):
        return self._all("SELECT ts, kind, source, detail FROM events WHERE booking_id=? ORDER BY id", (booking_id,))

    # ---- paiement transporteur (déclenché par la preuve de livraison) ----
    def create_payable(self, booking, pod_at, due_on):
        if not booking["carrier_price"]:
            return None
        try:
            self._exec("INSERT INTO carrier_payables(booking_id, carrier_id, carrier_name, amount_ht, pod_at, due_on) VALUES (?,?,?,?,?,?)",
                       (booking["id"], booking["carrier_id"], booking["carrier_name"], booking["carrier_price"], pod_at, due_on))
        except sqlite3.IntegrityError:
            return None                      # déjà créé : jamais deux dettes pour une même livraison
        return True

    def list_payables(self, status=None):
        if status:
            return self._all("SELECT * FROM carrier_payables WHERE status=? ORDER BY due_on, id", (status,))
        return self._all("SELECT * FROM carrier_payables ORDER BY due_on, id")

    def mark_paid(self, payable_id, reference):
        """Atomique : ne paie qu'une fois (statut 'due' exigé)."""
        return self._exec("UPDATE carrier_payables SET status='paid', paid_at=?, payment_ref=? WHERE id=? AND status='due'",
                          (time.time(), reference[:80], payable_id)).rowcount > 0

    # ---- comptes du personnel (RBAC) ----
    ROLES = ("admin", "ops", "finance")

    def create_user(self, username, pw_hash, totp_secret, role):
        if role not in self.ROLES:
            raise ValueError("rôle inconnu")
        self._exec("INSERT INTO users(username, pw_hash, totp_secret, role, active, created_at) VALUES (?,?,?,?,1,?)",
                   (username, pw_hash, totp_secret, role, time.time()))

    def get_user(self, username):
        rows = self._all("SELECT * FROM users WHERE username=?", (username,))
        return rows[0] if rows else None

    def list_users(self):
        return self._all("SELECT username, role, active, (totp_secret IS NOT NULL) AS mfa, created_at FROM users ORDER BY username")

    def set_user_active(self, username, active):
        return self._exec("UPDATE users SET active=? WHERE username=?", (1 if active else 0, username)).rowcount > 0

    def set_user_password(self, username, pw_hash):
        return self._exec("UPDATE users SET pw_hash=? WHERE username=?", (pw_hash, username)).rowcount > 0

    def users_count(self):
        return self._all("SELECT COUNT(*) AS n FROM users")[0]["n"]

    # ---- rétention (voir docs/RETENTION.md) ----
    def purge_outbox(self, older_than_s):
        return self._exec("DELETE FROM outbox WHERE created_at < ?", (time.time() - older_than_s,)).rowcount

    def anonymize_older_than(self, older_than_s):
        """Anonymise les réservations plus anciennes que le délai ; les factures sont conservées (10 ans, comptabilité)."""
        rows = self._all("SELECT tracking_code, customer FROM bookings WHERE created_at < ?", (time.time() - older_than_s,))
        n = 0
        for r in rows:
            if json.loads(r["customer"]).get("name") != "ANONYMISÉ" and self.anonymize_booking(r["tracking_code"]):
                n += 1
        return n

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
