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
CREATE TABLE IF NOT EXISTS outcomes (
    booking_id INTEGER PRIMARY KEY, actual_cost_ht REAL NOT NULL, on_time INTEGER NOT NULL,
    note TEXT, recorded_by TEXT NOT NULL, created_at REAL NOT NULL
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
CREATE TABLE IF NOT EXISTS carrier_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'to_review',
    data TEXT NOT NULL, checks TEXT NOT NULL, decided_by TEXT, decided_at REAL, note TEXT
);
CREATE TABLE IF NOT EXISTS contact_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'new', data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'received', data TEXT NOT NULL, deadlines TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, code TEXT NOT NULL, created_at REAL NOT NULL,
    severity TEXT NOT NULL, message TEXT NOT NULL, UNIQUE(booking_id, code)
);
CREATE TABLE IF NOT EXISTS sms_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, to_phone TEXT NOT NULL, body TEXT NOT NULL,
    status TEXT NOT NULL, error TEXT
);
CREATE TABLE IF NOT EXISTS sms_optout (phone_hash TEXT PRIMARY KEY, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS driver_links (
    token_hash TEXT PRIMARY KEY, booking_id INTEGER NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
    consent_at REAL, revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS driver_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, ts REAL NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, accuracy REAL
);
CREATE TABLE IF NOT EXISTS login_codes (
    email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id TEXT NOT NULL, booking_code TEXT, provider TEXT NOT NULL, provider_ref TEXT,
    amount_cents INTEGER NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS carrier_directory (
    siren TEXT PRIMARY KEY, name TEXT NOT NULL, city TEXT, postcode TEXT, dept TEXT, lat REAL, lon REAL, naf TEXT, size TEXT,
    email TEXT, phone TEXT, status TEXT NOT NULL DEFAULT 'prospect', optout INTEGER NOT NULL DEFAULT 0, last_contacted REAL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rfq (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT NOT NULL UNIQUE, quote_id TEXT, created_at REAL NOT NULL, lane TEXT NOT NULL,
    estimate_eur REAL, status TEXT NOT NULL DEFAULT 'draft'
);
CREATE TABLE IF NOT EXISTS rfq_targets (
    rfq_id INTEGER NOT NULL, siren TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', sent_at REAL, PRIMARY KEY (rfq_id, siren)
);
CREATE TABLE IF NOT EXISTS rfq_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, rfq_id INTEGER NOT NULL, siren TEXT, amount REAL, raw TEXT NOT NULL, received_at REAL NOT NULL
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

    # ---- résultats réels (boucle d'apprentissage) ----
    def record_outcome(self, booking_id, actual_cost_ht, on_time, note, who):
        """Un seul résultat par réservation (INSERT OR REPLACE : une correction remplace la saisie précédente)."""
        self._exec("INSERT OR REPLACE INTO outcomes(booking_id, actual_cost_ht, on_time, note, recorded_by, created_at) VALUES (?,?,?,?,?,?)",
                   (booking_id, float(actual_cost_ht), 1 if on_time else 0, (note or "")[:300], who, time.time()))

    def list_outcomes(self):
        return self._all("""SELECT o.booking_id, o.actual_cost_ht, o.on_time, o.note, b.tracking_code, b.carrier_id, b.carrier_name,
                            b.carrier_price, b.customer_price_ht FROM outcomes o JOIN bookings b ON b.id=o.booking_id""")

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

    # ---- candidatures transporteurs, contacts, réclamations ----
    def add_application(self, data, checks):
        with _lock:
            cur = self.conn.execute("INSERT INTO carrier_applications (created_at, data, checks) VALUES (?,?,?)",
                                    (time.time(), json.dumps(data), json.dumps(checks)))
            self.conn.commit()
            return cur.lastrowid

    def list_applications(self, limit=200):
        return self._all("SELECT * FROM carrier_applications ORDER BY id DESC LIMIT ?", (limit,))

    def decide_application(self, app_id, status, who, note):
        with _lock:
            cur = self.conn.execute("UPDATE carrier_applications SET status=?, decided_by=?, decided_at=?, note=? WHERE id=?",
                                    (status, who, time.time(), note, app_id))
            self.conn.commit()
            return cur.rowcount == 1

    def add_contact(self, data):
        with _lock:
            cur = self.conn.execute("INSERT INTO contact_requests (created_at, data) VALUES (?,?)", (time.time(), json.dumps(data)))
            self.conn.commit()
            return cur.lastrowid

    def list_contacts(self, limit=200):
        return self._all("SELECT * FROM contact_requests ORDER BY id DESC LIMIT ?", (limit,))

    def set_contact_status(self, cid, status):
        with _lock:
            cur = self.conn.execute("UPDATE contact_requests SET status=? WHERE id=?", (status, cid))
            self.conn.commit()
            return cur.rowcount == 1

    def add_claim(self, booking_id, data, deadlines):
        with _lock:
            cur = self.conn.execute("INSERT INTO claims (booking_id, created_at, data, deadlines) VALUES (?,?,?,?)",
                                    (booking_id, time.time(), json.dumps(data), json.dumps(deadlines)))
            self.conn.commit()
            return cur.lastrowid

    def claims_for(self, booking_id):
        return self._all("SELECT * FROM claims WHERE booking_id=? ORDER BY id", (booking_id,))

    def list_claims(self, limit=200):
        return self._all("SELECT * FROM claims ORDER BY id DESC LIMIT ?", (limit,))

    def set_claim_status(self, claim_id, status, note):
        with _lock:
            cur = self.conn.execute("UPDATE claims SET status=?, note=? WHERE id=?", (status, note, claim_id))
            self.conn.commit()
            return cur.rowcount == 1

    def purge_leads(self, older_than_s):
        """Supprime contacts et candidatures refusées/anciennes (minimisation RGPD)."""
        cutoff = time.time() - older_than_s
        with _lock:
            a = self.conn.execute("DELETE FROM contact_requests WHERE created_at < ?", (cutoff,)).rowcount
            b = self.conn.execute("DELETE FROM carrier_applications WHERE created_at < ? AND status='rejected'", (cutoff,)).rowcount
            self.conn.commit()
        return a + b

    # ---- alertes de suivi (veille retards) ----
    def add_alert(self, booking_id, code, severity, message):
        """Vrai si l'alerte est nouvelle (idempotent : une alerte donnée n'est émise qu'une fois par réservation)."""
        with _lock:
            cur = self.conn.execute("INSERT OR IGNORE INTO alerts (booking_id, code, created_at, severity, message) VALUES (?,?,?,?,?)",
                                    (booking_id, code, time.time(), severity, message))
            self.conn.commit()
            return cur.rowcount == 1

    def list_alerts(self, limit=200):
        return self._all("SELECT a.*, b.tracking_code FROM alerts a JOIN bookings b ON b.id=a.booking_id ORDER BY a.id DESC LIMIT ?", (limit,))

    def confirmed_bookings(self, limit=2000):
        return self._all("SELECT * FROM bookings WHERE status='confirmed' ORDER BY id DESC LIMIT ?", (limit,))

    def recent_customer_activity(self, since_ts):
        """(e-mail, empreinte IP, date) des réservations récentes : sert à la garde anti-fraude, jamais affiché."""
        out = []
        for r in self._all("SELECT customer, created_at FROM bookings WHERE created_at >= ?", (since_ts,)):
            c = json.loads(r["customer"])
            out.append({"email": (c.get("email") or "").lower(), "ip_hash": (c.get("consent") or {}).get("ip_hash", ""), "created_at": r["created_at"]})
        return out

    # ---- annuaire des transporteurs et demandes de devis ----
    def upsert_directory(self, row):
        """Ajoute ou met à jour (sans écraser e-mail, téléphone, statut, désinscription). Retourne 1 si nouvelle ligne."""
        with _lock:
            exists = self.conn.execute("SELECT 1 FROM carrier_directory WHERE siren=?", (row["siren"],)).fetchone()
            if exists:
                self.conn.execute("UPDATE carrier_directory SET name=?, city=?, postcode=?, dept=?, lat=?, lon=?, naf=?, size=?, updated_at=? WHERE siren=?",
                                  (row["name"], row["city"], row["postcode"], row["dept"], row["lat"], row["lon"], row["naf"], row["size"], time.time(), row["siren"]))
            else:
                self.conn.execute("INSERT INTO carrier_directory (siren,name,city,postcode,dept,lat,lon,naf,size,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (row["siren"], row["name"], row["city"], row["postcode"], row["dept"], row["lat"], row["lon"], row["naf"], row["size"], time.time()))
            self.conn.commit()
        return 0 if exists else 1

    def list_directory(self, dept=None, limit=500):
        if dept:
            return self._all("SELECT * FROM carrier_directory WHERE dept=? ORDER BY name LIMIT ?", (dept, limit))
        return self._all("SELECT * FROM carrier_directory ORDER BY name LIMIT ?", (limit,))

    def directory_one(self, siren):
        r = self._all("SELECT * FROM carrier_directory WHERE siren=?", (siren,))
        return r[0] if r else None

    def set_directory_contact(self, siren, email, phone):
        return self._exec("UPDATE carrier_directory SET email=?, phone=?, updated_at=? WHERE siren=?", (email, phone, time.time(), siren)).rowcount == 1

    def set_directory_optout(self, siren):
        self._exec("UPDATE carrier_directory SET optout=1, updated_at=? WHERE siren=?", (time.time(), siren))

    def optout_by_email(self, email):
        self._exec("UPDATE carrier_directory SET optout=1, updated_at=? WHERE lower(email)=?", (time.time(), email.lower()))

    def create_rfq(self, ref, quote_id, lane_json, estimate, sirens):
        with _lock:
            cur = self.conn.execute("INSERT INTO rfq (ref, quote_id, created_at, lane, estimate_eur) VALUES (?,?,?,?,?)", (ref, quote_id, time.time(), lane_json, estimate))
            rid = cur.lastrowid
            for sr in sirens:
                self.conn.execute("INSERT OR IGNORE INTO rfq_targets (rfq_id, siren) VALUES (?,?)", (rid, sr))
            self.conn.commit()
        return rid

    def rfq_by_id(self, rid):
        r = self._all("SELECT * FROM rfq WHERE id=?", (rid,))
        return r[0] if r else None

    def rfq_by_ref(self, ref):
        r = self._all("SELECT * FROM rfq WHERE ref=?", (ref,))
        return r[0] if r else None

    def rfq_targets(self, rid):
        return self._all("SELECT t.*, d.name, d.email, d.city FROM rfq_targets t JOIN carrier_directory d ON d.siren=t.siren WHERE t.rfq_id=?", (rid,))

    def mark_rfq_sent(self, rid, siren):
        now = time.time()
        with _lock:
            self.conn.execute("UPDATE rfq_targets SET status='sent', sent_at=? WHERE rfq_id=? AND siren=?", (now, rid, siren))
            self.conn.execute("UPDATE carrier_directory SET last_contacted=? WHERE siren=?", (now, siren))
            self.conn.execute("UPDATE rfq SET status='sent' WHERE id=?", (rid,))
            self.conn.commit()

    def add_rfq_reply(self, rid, siren, amount, raw):
        self._exec("INSERT INTO rfq_replies (rfq_id, siren, amount, raw, received_at) VALUES (?,?,?,?,?)", (rid, siren, amount, raw[:2000], time.time()))
        if siren:
            self._exec("UPDATE rfq_targets SET status='replied' WHERE rfq_id=? AND siren=?", (rid, siren))

    def rfq_replies(self, rid):
        return self._all("SELECT r.*, d.name FROM rfq_replies r LEFT JOIN carrier_directory d ON d.siren=r.siren WHERE r.rfq_id=? ORDER BY r.amount IS NULL, r.amount", (rid,))

    def list_rfqs(self, limit=50):
        return self._all("SELECT * FROM rfq ORDER BY id DESC LIMIT ?", (limit,))

    def rfq_price_ratios(self):
        """(montant de réponse / estimation du modèle) pour chaque réponse chiffrée : sert à recaler le barème sur des prix réels."""
        return [r["amount"] / r["estimate_eur"] for r in self._all(
            "SELECT p.amount, q.estimate_eur FROM rfq_replies p JOIN rfq q ON q.id=p.rfq_id WHERE p.amount IS NOT NULL AND q.estimate_eur > 0")]

    # ---- compte client (code par e-mail) ----
    def set_login_code(self, email, code_hash, expires_at):
        self._exec("INSERT OR REPLACE INTO login_codes (email, code_hash, expires_at, attempts) VALUES (?,?,?,0)", (email, code_hash, expires_at))

    def get_login_code(self, email):
        rows = self._all("SELECT * FROM login_codes WHERE email=?", (email,))
        return rows[0] if rows else None

    def bump_login_attempt(self, email):
        self._exec("UPDATE login_codes SET attempts=attempts+1 WHERE email=?", (email,))

    def delete_login_code(self, email):
        self._exec("DELETE FROM login_codes WHERE email=?", (email,))

    def bookings_for_email(self, email, limit=100):
        out = []
        for r in self._all("SELECT * FROM bookings ORDER BY id DESC LIMIT 5000"):
            if json.loads(r["customer"]).get("email", "").lower() == email:
                out.append(r)
                if len(out) >= limit:
                    break
        return out

    def get_payment_by_ref(self, ref):
        rows = self._all("SELECT * FROM payments WHERE provider_ref=?", (ref,))
        return rows[0] if rows else None

    def add_payment(self, quote_id, provider, ref, amount_cents, status="pending"):
        self._exec("INSERT INTO payments (quote_id, provider, provider_ref, amount_cents, currency, status, created_at, updated_at) VALUES (?,?,?,?, 'eur', ?,?,?)",
                   (quote_id, provider, ref, amount_cents, status, time.time(), time.time()))

    def set_payment_status(self, ref, status):
        self._exec("UPDATE payments SET status=?, updated_at=? WHERE provider_ref=?", (status, time.time(), ref))

    # ---- SMS ----
    def queue_sms(self, phone, body):
        with _lock:
            cur = self.conn.execute("INSERT INTO sms_outbox (created_at, to_phone, body, status) VALUES (?,?,?, 'queued')", (time.time(), phone, body))
            self.conn.commit()
            return cur.lastrowid

    def queued_sms(self, limit=50):
        return self._all("SELECT * FROM sms_outbox WHERE status='queued' ORDER BY id LIMIT ?", (limit,))

    def list_sms(self, limit=30):
        return self._all("SELECT id, created_at, to_phone, body, status, error FROM sms_outbox ORDER BY id DESC LIMIT ?", (limit,))

    def mark_sms(self, sms_id, status, error=None):
        self._exec("UPDATE sms_outbox SET status=?, error=? WHERE id=?", (status, error, sms_id))

    def is_sms_optout(self, phone_hash):
        return bool(self._all("SELECT 1 FROM sms_optout WHERE phone_hash=?", (phone_hash,)))

    def add_sms_optout(self, phone_hash):
        self._exec("INSERT OR IGNORE INTO sms_optout (phone_hash, created_at) VALUES (?,?)", (phone_hash, time.time()))

    # ---- suivi chauffeur ----
    def add_driver_link(self, token_hash, booking_id, expires_at):
        self._exec("INSERT INTO driver_links (token_hash, booking_id, created_at, expires_at) VALUES (?,?,?,?)",
                   (token_hash, booking_id, time.time(), expires_at))

    def get_driver_link(self, token_hash):
        rows = self._all("SELECT * FROM driver_links WHERE token_hash=?", (token_hash,))
        return rows[0] if rows else None

    def consent_driver_link(self, token_hash):
        self._exec("UPDATE driver_links SET consent_at=COALESCE(consent_at, ?) WHERE token_hash=?", (time.time(), token_hash))

    def revoke_driver_link(self, token_hash):
        self._exec("UPDATE driver_links SET revoked=1 WHERE token_hash=?", (token_hash,))

    def add_position(self, booking_id, lat, lon, accuracy):
        self._exec("INSERT INTO driver_positions (booking_id, ts, lat, lon, accuracy) VALUES (?,?,?,?,?)", (booking_id, time.time(), lat, lon, accuracy))

    def last_position(self, booking_id):
        rows = self._all("SELECT ts, lat, lon, accuracy FROM driver_positions WHERE booking_id=? ORDER BY id DESC LIMIT 1", (booking_id,))
        return rows[0] if rows else None

    def purge_positions(self, older_than_s):
        with _lock:
            n = self.conn.execute("DELETE FROM driver_positions WHERE ts < ?", (time.time() - older_than_s,)).rowcount
            self.conn.commit()
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
