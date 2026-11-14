#!/usr/bin/env python3
"""Serveur FRETRAU (bibliothèque standard uniquement, aucune dépendance).

Lancement :  FRETRAU_ADMIN_PASSWORD='un-mot-de-passe-long' python3 server.py
Variables :  PORT, HOST, FRETRAU_DB, FRETRAU_SECRET, FRETRAU_HTTPS=1, FRETRAU_TRUST_PROXY=1,
             FRETRAU_DEMO_SPEED (1 = temps réel, 360 = 1 h simulée en 10 s), ANTHROPIC_API_KEY (optionnel)
"""
import html
import json
import os
import csv
import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import asdict
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from fretrau import legal  # noqa: F401 — enregistre les pages légales
from fretrau import booking, content, geo, invoicing, mailer, market, offers, pricing, registry, security
from fretrau.agents import compliance, email_agent, intake, llm, vetting, watch
from fretrau.db import DB

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8", ".ico": "image/x-icon"}

HTTPS = os.environ.get("FRETRAU_HTTPS") == "1"
TRUST_PROXY = os.environ.get("FRETRAU_TRUST_PROXY") == "1"
DEMO_SPEED = float(os.environ.get("FRETRAU_DEMO_SPEED", "1"))

_admin_pw = os.environ.get("FRETRAU_ADMIN_PASSWORD")
if not _admin_pw:
    _admin_pw = secrets.token_urlsafe(16)
    print(f"[FRETRAU] Aucun FRETRAU_ADMIN_PASSWORD défini. Mot de passe admin temporaire : {_admin_pw}")
if len(_admin_pw) < 12:
    raise SystemExit("[FRETRAU] FRETRAU_ADMIN_PASSWORD doit contenir au moins 12 caractères.")
ADMIN_HASH = security.hash_password(_admin_pw)
del _admin_pw
TOTP_SECRET = os.environ.get("FRETRAU_ADMIN_TOTP_SECRET")          # 2FA admin (recommandé)
WEBHOOK_SECRET = os.environ.get("FRETRAU_WEBHOOK_SECRET", "")       # signe les e-mails entrants
PUBLIC_URL = os.environ.get("FRETRAU_PUBLIC_URL", "http://127.0.0.1:8080")
if not TOTP_SECRET:
    print("[FRETRAU] ATTENTION : 2FA admin désactivée. Générez un secret : "
          "python3 -c \"from fretrau.security import new_totp_secret as n; print(n())\" "
          "puis FRETRAU_ADMIN_TOTP_SECRET=... (à ajouter dans une application d'authentification).")
_secret = os.environ.get("FRETRAU_SECRET", secrets.token_hex(32)).encode()
SESSIONS = security.Sessions(hmac.new(_secret, b"admin", hashlib.sha256).digest())
USER_SESSIONS = security.Sessions(hmac.new(_secret, b"comptes", hashlib.sha256).digest(), ttl=12 * 3600)
del _secret
PROSPECTS_CSV = os.path.join(ROOT, "data", "transporteurs.csv")
STEP_LABELS = dict(booking.STEPS)

DB_ = DB(os.environ.get("FRETRAU_DB", os.path.join(ROOT, "fretrau.db")))
RL_GLOBAL = security.RateLimiter(120, 60)
RL_QUOTE = security.RateLimiter(20, 60)
RL_BOOK = security.RateLimiter(5, 600)
RL_LOGIN = security.RateLimiter(10, 900)
RL_TRACK = security.RateLimiter(30, 60)
RL_SIGNUP = security.RateLimiter(5, 3600)
RL_CONTACT = security.RateLimiter(5, 3600)
WINDOWS = {"journee": "Dans la journée", "matin": "Matin (8 h - 12 h)", "apres-midi": "Après-midi (13 h - 17 h)"}
LEAD_TOPICS = ("rappel", "devis", "transporteur", "autre")
TERMS_VERSION = "2026-11"            # à incrémenter à chaque modification des CGU, CGV ou de la politique de confidentialité
RL_FORGOT = security.RateLimiter(5, 3600)
BACKUP_DIR = os.environ.get("FRETRAU_BACKUP_DIR", "")
BACKUP_KEEP = 30
GUARD = security.LoginGuard()


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Handler(BaseHTTPRequestHandler):
    server_version = "FRETRAU"
    sys_version = ""

    # ---------- utilitaires ----------
    def log_message(self, fmt, *args):          # pas de corps de requête dans les logs
        pass

    def ip(self):
        if TRUST_PROXY and self.headers.get("X-Forwarded-For"):
            return self.headers["X-Forwarded-For"].split(",")[0].strip()
        return self.client_address[0]

    def _headers(self, status, ctype, length, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        for k, v in security.SECURITY_HEADERS.items():
            self.send_header(k, v)
        if HTTPS:
            self.send_header("Strict-Transport-Security", security.HSTS)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def send_json(self, status, obj, extra=None):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(body), extra)
        self.wfile.write(body)

    def send_bytes(self, status, ctype, body, extra=None):
        self._headers(status, ctype, len(body), extra)
        self.wfile.write(body)

    def read_json(self, raw_out=None):
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise ApiError(415, "Content-Type application/json requis.")
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(400, "Requête invalide.")
        if n <= 0 or n > security.MAX_BODY:
            raise ApiError(413, "Corps de requête invalide ou trop volumineux.")
        try:
            raw = self.rfile.read(n)
            if raw_out is not None:
                raw_out.append(raw)
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(400, "JSON invalide.")
        if not isinstance(data, dict):
            raise ApiError(400, "Objet JSON attendu.")
        return data

    def admin_user(self):
        if self.headers.get("X-Requested-With") != "fretrau":
            return None
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "fretrau_admin":
                return "admin" if SESSIONS.verify(v) == "admin" else None
        return None

    def account(self, role=None):
        """Compte connecté (expéditeur ou transporteur), sinon None. En-tête anti-CSRF obligatoire."""
        if self.headers.get("X-Requested-With") != "fretrau":
            return None
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "fretrau_user":
                parts = (USER_SESSIONS.verify(v) or "").split(":")
                if len(parts) == 3 and parts[0] == "acct" and parts[1].isdigit() and parts[2].isdigit():
                    acct = DB_.account_by_id(int(parts[1]))
                    # la version de session change à chaque changement de mot de passe : les anciennes sessions tombent
                    if (acct and not acct["deleted_at"] and acct["session_version"] == int(parts[2])
                            and (role is None or acct["role"] == role)):
                        return acct
        return None

    def require_account(self, role):
        acct = self.account(role)
        if not acct:
            raise ApiError(401, "Connexion requise.")
        return acct

    def query(self):
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def signed_json(self):
        """Corps JSON d'un webhook : signature HMAC-SHA256 (X-Signature) et horodatage récent obligatoires."""
        if not WEBHOOK_SECRET:
            raise ApiError(503, "Webhook non configuré.")
        raw = []
        d = self.read_json(raw)
        expected = hmac.new(WEBHOOK_SECRET.encode(), raw[0], hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, self.headers.get("X-Signature", "")):
            DB_.audit("anonymous", "webhook_bad_signature", self.ip())
            raise ApiError(401, "Signature invalide.")
        ts = d.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or abs(time.time() - ts) > 300:   # anti-rejeu
            raise ApiError(400, "Horodatage invalide ou expiré.")
        return d

    def notify_customer(self, b, subject, body):
        try:
            mailer.queue(DB_, json.loads(b["customer"])["email"], subject, body)
            mailer.flush(DB_)
        except Exception:
            pass                                              # un e-mail en échec ne bloque jamais l'opération

    def after_decision(self, code, result):
        """Suites d'une réponse de transporteur : confirmation au client si le transport est attribué."""
        if result["decision"] == "accepted":
            b = DB_.booking_by_code(code)
            cu, sh = json.loads(b["customer"]), json.loads(b["shipment"])
            self.notify_customer(b, *mailer.booking_confirmation(cu, code, sh, b["customer_price_ht"], PUBLIC_URL))

    def require_admin(self):
        user = self.admin_user()
        if not user:
            raise ApiError(401, "Authentification requise.")
        return user

    # ---------- routage ----------
    def dispatch(self, method):
        try:
            if not RL_GLOBAL.allow(self.ip()):
                raise ApiError(429, "Trop de requêtes, réessayez dans une minute.")
            path = urlparse(self.path).path
            origin = self.headers.get("Origin")
            if method == "POST" and origin and urlparse(origin).netloc != self.headers.get("Host"):
                raise ApiError(403, "Origine non autorisée.")
            if path.startswith("/api/"):
                return self.api(method, path)
            if method != "GET":
                raise ApiError(405, "Méthode non autorisée.")
            return self.static(path)
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
        except Exception:
            self.send_json(500, {"error": "Erreur interne."})      # jamais de trace au client

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    # ---------- fichiers statiques ----------
    def static(self, path):
        page = content.render(path.rstrip("/") or "/")
        if page is not None:
            return self.send_bytes(200, "text/html; charset=utf-8", page.encode())
        if path in ("/", ""):
            path = "/index.html"
        full = os.path.realpath(os.path.join(WEB, path.lstrip("/")))
        ext = os.path.splitext(full)[1].lower()
        if not full.startswith(WEB + os.sep) or ext not in MIME or not os.path.isfile(full):
            raise ApiError(404, "Introuvable.")
        with open(full, "rb") as f:
            body = f.read()
        if ext == ".html":                              # en-tête et pied de page communs à tout le site
            body = body.replace(b"<!--HEADER-->", content.header().encode()).replace(b"<!--FOOTER-->", content.footer().encode())
        self.send_bytes(200, MIME[ext], body)

    # ---------- API ----------
    def api(self, method, path):
        if method == "GET" and path == "/api/cities":
            return self.send_json(200, {"cities": sorted(geo.CITIES), "options": pricing.OPTIONS,
                                        "modes": pricing.MODES, "llm": llm.available(),
                                        "defaults": pricing.DEFAULTS, "windows": WINDOWS,
                                        "quote_email": os.environ.get("FRETRAU_QUOTE_EMAIL", "")})
        if method == "POST" and path == "/api/rates":
            return self.api_rates()
        if method == "POST" and path == "/api/contact":
            return self.api_contact()
        m = re.fullmatch(r"/api/quote/([A-Za-z0-9_-]{8,40})", path)
        if method == "GET" and m:
            return self.api_quote_view(m.group(1))
        if method == "POST" and path == "/api/webhook/inbound-quote":
            return self.api_inbound_quote()
        if path.startswith("/api/account/"):
            return self.api_account(method, path)
        if path.startswith("/api/my/"):
            return self.api_my(method, path)
        if path.startswith("/api/carrier/"):
            return self.api_carrier(method, path)
        if method == "POST" and path == "/api/quote":
            return self.api_quote()
        if method == "POST" and path == "/api/book":
            return self.api_book()
        m = re.fullmatch(r"/api/track/([^/]+)", path)
        if method == "GET" and m:
            return self.api_track(m.group(1))
        m = re.fullmatch(r"/api/doc/([^/]+)", path)
        if method == "GET" and m:
            return self.api_doc(m.group(1))
        if method == "POST" and path == "/api/webhook/inbound-mail":
            return self.api_inbound_mail()
        if path.startswith("/api/admin/"):
            return self.api_admin(method, path)
        raise ApiError(404, "Introuvable.")

    def api_rates(self):
        """Vérificateur de tarif : estimation des trois types de transport sur un trajet, sans créer de devis."""
        if not RL_QUOTE.allow(self.ip()):
            raise ApiError(429, "Trop de demandes, patientez un instant.")
        d = self.read_json()
        try:
            origin, destination = security.clean_text(d.get("origin"), 60), security.clean_text(d.get("destination"), 60)
        except ValueError:
            raise ApiError(422, "Indiquez un départ et une arrivée.")
        factor = market.factor(DB_, origin, destination) if geo.known(origin) and geo.known(destination) else 1.0
        rates = []
        try:
            for mode, label in pricing.MODES.items():
                a = pricing.DEFAULTS[mode]
                q = pricing.build_quote(origin, destination, mode, a["pallets"], a["weight_kg"], {}, market_factor=factor)
                rates.append({"mode": mode, "label": label, "price_ht": q.price_ht, "per_km": round(q.price_ht / q.distance_km, 2),
                              "transit_days": q.transit_days, "pallets": a["pallets"], "weight_kg": a["weight_kg"]})
        except pricing.QuoteError as e:
            raise ApiError(422, str(e))
        self.send_json(200, {"origin": geo.label(origin), "destination": geo.label(destination),
                             "distance_km": q.distance_km, "rates": rates})

    def api_contact(self):
        if not RL_CONTACT.allow(self.ip()):
            raise ApiError(429, "Trop de messages, réessayez plus tard.")
        d = self.read_json()
        if d.get("website"):
            return self.send_json(200, {"ok": True})
        try:
            lead = {"topic": d.get("topic") if d.get("topic") in LEAD_TOPICS else "autre",
                    "name": security.clean_text(d.get("name"), 80), "company": security.clean_text(d.get("company"), 120),
                    "email": security.clean_text(d.get("email"), 254).lower(), "phone": security.clean_text(d.get("phone"), 20),
                    "message": security.clean_text(d.get("message"), 2000)}
        except ValueError:
            raise ApiError(422, "Tous les champs sont obligatoires.")
        if not security.EMAIL_RE.match(lead["email"]) or not security.PHONE_RE.match(lead["phone"]):
            raise ApiError(422, "Coordonnées invalides.")
        DB_.add_lead(**lead)
        DB_.audit("anonymous", "lead_" + lead["topic"], self.ip())
        self.send_json(201, {"ok": True})

    def api_quote(self):
        if not RL_QUOTE.allow(self.ip()):
            raise ApiError(429, "Trop de devis demandés, patientez un instant.")
        d = self.read_json()
        try:
            origin = security.clean_text(d.get("origin"), 60)
            destination = security.clean_text(d.get("destination"), 60)
            mode = security.clean_text(d.get("mode"), 3)
            pallets = d.get("pallets")
            weight = d.get("weight_kg")
            if isinstance(pallets, bool) or isinstance(weight, bool):
                raise ValueError("Valeur numérique invalide.")
            options = d.get("options") if isinstance(d.get("options"), dict) else {}
            q = pricing.build_quote(origin, destination, mode, pallets, weight, options,
                                    market_factor=market.factor(DB_, origin, destination))
            pickup = date.fromisoformat(security.clean_text(d.get("pickup_date"), 10))
        except pricing.QuoteError as e:
            raise ApiError(422, str(e))
        except ValueError:
            raise ApiError(422, "Données invalides : vérifiez le formulaire.")
        today = date.today()
        if not today <= pickup <= today + timedelta(days=60):
            raise ApiError(422, "La date d'enlèvement doit être dans les 60 prochains jours.")

        quote_id = secrets.token_urlsafe(12)
        shipment = {"pallets": pallets, "weight_kg": weight, "pickup_date": pickup.isoformat(),
                    "options": {k: bool(v) for k, v in options.items() if k in pricing.OPTIONS}}
        DB_.save_quote(quote_id, {"quote": asdict(q), "shipment": shipment})
        self.send_json(200, self.quote_view(quote_id, asdict(q), shipment))

    @staticmethod
    def quote_view(quote_id, q, shipment):
        """Vue publique d'un devis : le détail inclut la marge, jamais le coût d'achat brut."""
        scale = q["price_ht"] / q["carrier_cost_estimate"]
        return {"quote_id": quote_id, "price_ht": q["price_ht"], "vat": q["vat"], "price_ttc": q["price_ttc"],
                "distance_km": q["distance_km"], "transit_days": q["transit_days"],
                "breakdown": {k: round(v * scale, 2) for k, v in q["breakdown"].items()},
                "valid_hours": 24, "mode": q["mode"], "origin": geo.label(q["origin"]),
                "destination": geo.label(q["destination"]), "pickup_date": shipment["pickup_date"]}

    def api_quote_view(self, quote_id):
        if not RL_TRACK.allow(self.ip()):
            raise ApiError(429, "Trop de requêtes.")
        stored = DB_.get_quote(quote_id)
        if not stored:
            raise ApiError(404, "Devis introuvable ou expiré.")
        view = self.quote_view(quote_id, stored["quote"], stored["shipment"])
        view["booked"] = DB_.booking_exists_for_quote(quote_id)
        self.send_json(200, view)

    def api_inbound_quote(self):
        """Demande de devis reçue par e-mail (relayée par le service de messagerie), signée."""
        d = self.signed_json()
        sender, text = d.get("from"), d.get("text")
        if (not isinstance(sender, str) or not security.EMAIL_RE.match(sender) or any(c in sender for c in "\r\n")
                or not isinstance(text, str) or not text.strip() or len(text) > 20000):
            raise ApiError(422, "Données invalides.")
        result = intake.handle(DB_, sender, text, PUBLIC_URL)
        DB_.audit("intake_agent", "quote_" + result["status"], result.get("quote_id", ""))
        try:
            mailer.flush(DB_)
        except Exception:
            pass
        self.send_json(200, result)

    def api_book(self):
        if not RL_BOOK.allow(self.ip()):
            raise ApiError(429, "Trop de réservations, patientez avant de réessayer.")
        d = self.read_json()
        if d.get("website"):                                  # champ piège anti-robots (honeypot)
            return self.send_json(200, {"ok": True})
        if d.get("accept_cgv") is not True:
            raise ApiError(422, "Vous devez accepter les conditions générales.")
        stored = DB_.get_quote(str(d.get("quote_id", ""))[:40])
        if not stored:
            raise ApiError(404, "Devis introuvable ou expiré.")
        quote_id = d["quote_id"]
        if DB_.booking_exists_for_quote(quote_id):
            raise ApiError(409, "Ce devis a déjà été réservé.")
        c = d.get("contact") if isinstance(d.get("contact"), dict) else {}
        try:
            customer = {
                "name": security.clean_text(c.get("name"), 80),
                "company": security.clean_text(c.get("company"), 120),
                "email": security.clean_text(c.get("email"), 254),
                "phone": security.clean_text(c.get("phone"), 20),
            }
            if not security.EMAIL_RE.match(customer["email"]) or not security.PHONE_RE.match(customer["phone"]):
                raise ValueError("Coordonnées invalides.")
            shipment = dict(stored["shipment"])
            shipment.update({
                "origin": stored["quote"]["origin"], "destination": stored["quote"]["destination"],
                "mode": stored["quote"]["mode"],
                "pickup_address": security.clean_text(d.get("pickup_address"), 200),
                "delivery_address": security.clean_text(d.get("delivery_address"), 200),
                "goods": security.clean_text(d.get("goods"), 200),
                "cgv": {"version": TERMS_VERSION, "accepted_at": int(time.time())},
                "pickup_window": d.get("pickup_window") if d.get("pickup_window") in WINDOWS else "journee",
                "delivery_window": d.get("delivery_window") if d.get("delivery_window") in WINDOWS else "journee",
            })
        except ValueError as e:
            raise ApiError(422, str(e))

        acct = self.account("shipper")
        result = booking.run(stored["quote"], date.fromisoformat(shipment["pickup_date"]), DB_)
        code = booking.new_tracking_code()
        carrier = result["carrier"]
        DB_.save_booking(
            tracking_code=code, quote_id=quote_id, status=result["status"], customer=customer,
            shipment=shipment, carrier_id=carrier.id if carrier else None,
            carrier_name=carrier.name if carrier else None, carrier_price=result["price"],
            customer_price_ht=stored["quote"]["price_ht"], agent_log=result["log"],
            account_id=acct["id"] if acct else None)
        DB_.audit("system", "booking_created", f"{code} status={result['status']}")
        if result["to_offer"]:
            sent = offers.send(DB_, DB_.booking_by_code(code), booking.quote_from_payload(stored["quote"]),
                               result["to_offer"], PUBLIC_URL)
            DB_.audit("sourcing_agent", "offers_sent", f"{code} -> {', '.join(sent)}"[:480])
        subject, body = (mailer.booking_confirmation(customer, code, shipment, stored["quote"]["price_ht"], PUBLIC_URL)
                         if result["status"] == "confirmed" else mailer.booking_pending(customer, code, PUBLIC_URL))
        try:
            mailer.queue(DB_, customer["email"], subject, body)
            mailer.flush(DB_)
        except Exception:
            pass                                              # un e-mail en échec ne bloque jamais la réservation
        self.send_json(201, {"tracking_code": code, "status": result["status"]})

    def _public_booking(self, code):
        if not RL_TRACK.allow(self.ip()):
            raise ApiError(429, "Trop de requêtes.")
        if not security.CODE_RE.match(code):
            raise ApiError(404, "Code de suivi inconnu.")
        b = DB_.booking_by_code(code)
        if not b:
            raise ApiError(404, "Code de suivi inconnu.")
        return b

    def api_track(self, code):
        b = self._public_booking(code)
        self.send_json(200, self.tracking_view(b))

    @staticmethod
    def tracking_view(b):
        shipment = json.loads(b["shipment"])
        events = []
        if b["status"] == "confirmed":
            real = DB_.milestones(b["id"])
            events = (booking.real_timeline(real) if real
                      else booking.timeline(b["created_at"], time.time(), DEMO_SPEED))
        message = None
        if b["status"] == "sourcing":
            message = "Nous recherchons le meilleur transporteur vérifié pour votre envoi. Vous serez prévenu par e-mail."
        elif b["status"] != "confirmed":
            message = "Votre demande est en cours de traitement par notre équipe, vous serez contacté rapidement."
        return {"tracking_code": b["tracking_code"], "status": b["status"], "origin": geo.label(shipment["origin"]),
                "destination": geo.label(shipment["destination"]), "events": events, "message": message}

    def api_doc(self, code):
        b = self._public_booking(code)
        if b["status"] != "confirmed":
            raise ApiError(409, "Document disponible après confirmation du transport.")
        s, cu = json.loads(b["shipment"]), json.loads(b["customer"])
        e = lambda v: html.escape(str(v))                       # noqa: E731 — échappement XSS
        rows = [("Expéditeur", f"{cu['name']} — {cu['company']}"), ("Lieu d'enlèvement", s["pickup_address"]),
                ("Lieu de livraison", s["delivery_address"]),
                ("Trajet", f"{geo.label(s['origin'])} → {geo.label(s['destination'])}"), ("Marchandise", s["goods"]),
                ("Palettes", s.get("pallets")), ("Poids (kg)", s["weight_kg"]),
                ("Date d'enlèvement", f"{s['pickup_date']} — {WINDOWS.get(s.get('pickup_window'), WINDOWS['journee'])}"),
                ("Créneau de livraison", WINDOWS.get(s.get("delivery_window"), WINDOWS["journee"])),
                ("Transporteur", b["carrier_name"])]
        body = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
        page = (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Lettre de voiture {e(code)}</title>"
                f"<link rel='stylesheet' href='/styles.css'></head><body class='doc'><h1>Lettre de voiture</h1>"
                f"<p class='muted'>N° {e(code)} — document de démonstration, à remplacer par un modèle CMR "
                f"conforme avant tout usage réel.</p><table class='doc-table'>{body}</table></body></html>")
        self.send_bytes(200, "text/html; charset=utf-8", page.encode())

    def api_inbound_mail(self):
        """Réponse e-mail d'un transporteur (relayée par votre service de messagerie). Signature HMAC obligatoire."""
        d = self.signed_json()
        code, carrier_id, text = d.get("tracking_code"), d.get("carrier_id"), d.get("text")
        if (not isinstance(code, str) or not security.CODE_RE.match(code) or isinstance(carrier_id, bool)
                or not isinstance(carrier_id, int) or not isinstance(text, str) or len(text) > 5000):
            raise ApiError(422, "Données invalides.")
        result = email_agent.handle(DB_, code, carrier_id, text)
        DB_.audit("email_agent", "inbound_" + result["decision"], f"{code} carrier={carrier_id}")
        self.after_decision(code, result)
        self.send_json(200, result)

    # ---------- comptes ----------
    def session_cookie(self, account_id=None):
        value = ""
        if account_id:
            value = USER_SESSIONS.issue(f"acct:{account_id}:{DB_.account_by_id(account_id)['session_version']}")
        age = 12 * 3600 if account_id else 0
        return (f"fretrau_user={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}"
                + ("; Secure" if HTTPS else ""))

    def read_identity(self, d):
        """Champs communs à toute création de compte, validés."""
        try:
            ident = {"name": security.clean_text(d.get("name"), 80), "company": security.clean_text(d.get("company"), 120),
                     "email": security.clean_text(d.get("email"), 254).lower(),
                     "phone": security.clean_text(d.get("phone"), 20)}
        except ValueError as e:
            raise ApiError(422, str(e))
        if not security.EMAIL_RE.match(ident["email"]) or not security.PHONE_RE.match(ident["phone"]):
            raise ApiError(422, "Coordonnées invalides.")
        pw = d.get("password")
        problem = security.password_problem(pw, ident["email"])
        if problem:
            raise ApiError(422, problem)
        if d.get("accept_terms") is not True:
            raise ApiError(422, "Vous devez accepter les conditions d'utilisation et la politique de confidentialité.")
        return ident, pw

    def send_account_link(self, account, kind):
        """Envoie un lien à usage unique : vérification d'adresse (48 h) ou nouveau mot de passe (1 h)."""
        token = security.new_token()
        DB_.add_token(account["id"], kind, security.token_hash(token), 48 * 3600 if kind == "verify" else 3600)
        if kind == "verify":
            subject = "FRETRAU — confirmez votre adresse e-mail"
            body = (f"Bonjour {account['name']},\n\nConfirmez votre adresse en ouvrant ce lien (valable 48 h) :\n"
                    f"{PUBLIC_URL}/compte?verifier={token}\n\nSi vous n'avez pas créé de compte, ignorez ce message.\n\n"
                    "L'équipe FRETRAU")
        else:
            subject = "FRETRAU — nouveau mot de passe"
            body = (f"Bonjour {account['name']},\n\nPour choisir un nouveau mot de passe, ouvrez ce lien (valable 1 h, "
                    f"utilisable une seule fois) :\n{PUBLIC_URL}/compte?reinitialiser={token}\n\n"
                    "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : votre mot de passe reste inchangé."
                    "\n\nL'équipe FRETRAU")
        try:
            mailer.queue(DB_, account["email"], subject, body)
            mailer.flush(DB_)
        except Exception:
            pass

    def api_account(self, method, path):
        if method == "GET" and path == "/api/account/me":
            a = self.account()
            if not a:
                return self.send_json(200, {"account": None})
            view = {k: a[k] for k in ("role", "email", "name", "company", "phone")}
            view["email_verified"] = bool(a["email_verified"])
            return self.send_json(200, {"account": view})
        if method == "GET" and path == "/api/account/export":
            return self.api_account_export(self.require_account(None))
        if method != "POST" or self.headers.get("X-Requested-With") != "fretrau":
            raise ApiError(404, "Introuvable.")
        if path == "/api/account/logout":
            return self.send_json(200, {"ok": True}, {"Set-Cookie": self.session_cookie()})
        ip = self.ip()
        if path == "/api/account/signup":
            if not RL_SIGNUP.allow(ip):
                raise ApiError(429, "Trop de créations de compte, réessayez plus tard.")
            d = self.read_json()
            if d.get("website"):
                return self.send_json(200, {"ok": True})
            ident, pw = self.read_identity(d)
            aid = DB_.create_account("shipper", ident["email"], security.hash_password(pw), ident["name"],
                                     ident["company"], ident["phone"])
            if not aid:
                raise ApiError(409, "Un compte existe déjà avec cette adresse e-mail.")
            DB_.set_terms(aid, TERMS_VERSION)
            self.send_account_link(DB_.account_by_id(aid), "verify")
            DB_.audit("account", "signup_shipper", f"{aid} cgu={TERMS_VERSION}")
            return self.send_json(201, {"ok": True, "role": "shipper"}, {"Set-Cookie": self.session_cookie(aid)})
        if path == "/api/account/login":
            d = self.read_json()
            email = str(d.get("email", "")).strip().lower()[:254]
            key = f"{ip}|{email}"
            if not RL_LOGIN.allow(ip) or GUARD.locked(key):
                raise ApiError(429, "Trop de tentatives. Réessayez plus tard.")
            a = DB_.account_by_email(email)
            # même coût de calcul que le compte existe ou non (pas d'énumération par le temps de réponse)
            ok = security.verify_password(str(d.get("password", "")), a["pw_hash"] if a else ADMIN_HASH) and bool(a)
            if not ok:
                GUARD.fail(key)
                DB_.audit("anonymous", "account_login_failed", ip)
                raise ApiError(401, "Identifiants invalides.")
            GUARD.ok(key)
            return self.send_json(200, {"ok": True, "role": a["role"]}, {"Set-Cookie": self.session_cookie(a["id"])})
        if path == "/api/account/verify":
            token = str(self.read_json().get("token", ""))
            aid = DB_.use_token("verify", security.token_hash(token)) if security.TOKEN_RE.match(token) else None
            if not aid:
                raise ApiError(400, "Lien invalide ou expiré. Demandez un nouveau lien depuis votre espace.")
            DB_.set_email_verified(aid)
            DB_.audit("account", "email_verified", str(aid))
            return self.send_json(200, {"ok": True})
        if path == "/api/account/resend":
            a = self.require_account(None)
            if not RL_FORGOT.allow(f"resend|{a['id']}"):
                raise ApiError(429, "Trop de demandes, réessayez plus tard.")
            if not a["email_verified"]:
                self.send_account_link(a, "verify")
            return self.send_json(200, {"ok": True})
        if path == "/api/account/forgot":
            email = str(self.read_json().get("email", "")).strip().lower()[:254]
            if not RL_FORGOT.allow(ip) or not RL_FORGOT.allow("mail|" + email):
                raise ApiError(429, "Trop de demandes, réessayez plus tard.")
            a = DB_.account_by_email(email)
            if a and not a["deleted_at"]:
                self.send_account_link(a, "reset")
                DB_.audit("account", "password_reset_requested", str(a["id"]))
            # même réponse que le compte existe ou non : on ne révèle pas qui est inscrit
            return self.send_json(200, {"ok": True})
        if path == "/api/account/reset":
            d = self.read_json()
            token = str(d.get("token", ""))
            if not security.TOKEN_RE.match(token):
                raise ApiError(400, "Lien invalide ou expiré.")
            problem = security.password_problem(d.get("password"))
            if problem:
                raise ApiError(422, problem)
            aid = DB_.use_token("reset", security.token_hash(token))
            if not aid:
                raise ApiError(400, "Lien invalide ou expiré.")
            DB_.set_password(aid, security.hash_password(d["password"]))
            DB_.set_email_verified(aid)                       # le lien prouve l'accès à la boîte e-mail
            DB_.audit("account", "password_reset_done", str(aid))
            return self.send_json(200, {"ok": True}, {"Set-Cookie": self.session_cookie()})
        if path == "/api/account/password":
            a = self.require_account(None)
            d = self.read_json()
            if not security.verify_password(str(d.get("current", "")), a["pw_hash"]):
                raise ApiError(401, "Mot de passe actuel incorrect.")
            problem = security.password_problem(d.get("password"), a["email"])
            if problem:
                raise ApiError(422, problem)
            DB_.set_password(a["id"], security.hash_password(d["password"]))
            DB_.audit("account", "password_changed", str(a["id"]))
            return self.send_json(200, {"ok": True}, {"Set-Cookie": self.session_cookie(a["id"])})
        if path == "/api/account/delete":
            a = self.require_account(None)
            if not security.verify_password(str(self.read_json().get("password", "")), a["pw_hash"]):
                raise ApiError(401, "Mot de passe incorrect.")
            DB_.erase_account(a["id"])
            DB_.audit("account", "account_erased", str(a["id"]))
            return self.send_json(200, {"ok": True}, {"Set-Cookie": self.session_cookie()})
        raise ApiError(404, "Introuvable.")

    def api_account_export(self, a):
        """Droit d'accès et portabilité : toutes les données du compte, dans un format lisible par machine."""
        out = {"compte": {k: a[k] for k in ("role", "email", "name", "company", "phone", "created_at", "terms_version")},
               "export_du": time.strftime("%Y-%m-%d %H:%M:%S")}
        if a["role"] == "shipper":
            rows = DB_.bookings_for_account(a["id"], a["email"] if a["email_verified"] else None)
            out["expeditions"] = [{"code": b["tracking_code"], "statut": b["status"], "cree_le": b["created_at"],
                                   "prix_ht": b["customer_price_ht"], "contact": json.loads(b["customer"]),
                                   "envoi": json.loads(b["shipment"])} for b in rows]
        else:
            c = DB_.carrier_row(a["carrier_id"]) or {}
            out["transporteur"] = {k: c.get(k) for k in ("name", "siret", "licence_no", "insurance_until", "base_place",
                                                          "modes", "equipment", "email", "phone", "status")}
        DB_.audit("account", "data_export", str(a["id"]))
        body = json.dumps(out, ensure_ascii=False, indent=2).encode()
        self.send_bytes(200, "application/json; charset=utf-8", body,
                        {"Content-Disposition": 'attachment; filename="mes-donnees-fretrau.json"'})

    # ---------- espace expéditeur ----------
    def api_my(self, method, path):
        acct = self.require_account("shipper")
        mine = DB_.bookings_for_account(acct["id"], acct["email"] if acct["email_verified"] else None)
        if method == "GET" and path == "/api/my/bookings":
            out = []
            for b in mine:
                s = json.loads(b["shipment"])
                view = self.tracking_view(b)
                view.update({"created_at": b["created_at"], "price_ht": b["customer_price_ht"], "mode": s["mode"],
                             "pickup_date": s["pickup_date"], "goods": s.get("goods", ""),
                             "carrier": b["carrier_name"] if b["status"] == "confirmed" else None})
                out.append(view)
            return self.send_json(200, {"bookings": out})
        m = re.fullmatch(r"/api/my/invoice/([^/]+)", path)
        if method == "GET" and m:
            b = next((x for x in mine if x["tracking_code"] == m.group(1)), None)
            if not b or b["status"] != "confirmed":
                raise ApiError(404, "Facture indisponible.")
            return self.send_json(200, DB_.get_or_create_invoice(b["id"], invoicing.build(b)))
        if method == "POST" and path == "/api/my/price-match":
            d = self.read_json()
            quote_id, price = str(d.get("quote_id", ""))[:40], d.get("competitor_price")
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not 20 <= price <= 50000:
                raise ApiError(422, "Montant invalide.")
            if not DB_.get_quote(quote_id):
                raise ApiError(404, "Devis introuvable ou expiré.")
            note = d.get("note") if isinstance(d.get("note"), str) else ""
            DB_.add_price_match(acct["id"], quote_id, float(price), "".join(c for c in note if c.isprintable())[:300])
            DB_.audit("account", "price_match_request", quote_id)
            return self.send_json(201, {"ok": True})
        raise ApiError(404, "Introuvable.")

    # ---------- espace transporteur ----------
    def api_carrier(self, method, path):
        if method == "POST" and path == "/api/carrier/apply":
            return self.api_carrier_apply()
        acct = self.require_account("carrier")
        row = DB_.carrier_row(acct["carrier_id"])
        if not row:
            raise ApiError(404, "Transporteur introuvable.")
        me = registry.from_row(row)
        if method == "GET" and path == "/api/carrier/loads":
            return self.api_carrier_loads(row, me)
        if row["status"] != "verified":
            raise ApiError(403, "Votre dossier doit être validé avant de prendre des chargements.")
        if method == "POST" and path == "/api/carrier/respond":
            d = self.read_json()
            code, amount = str(d.get("code", "")), d.get("amount")
            if (not security.CODE_RE.match(code) or isinstance(amount, bool) or not isinstance(amount, (int, float))
                    or not 20 <= amount <= 20000):
                raise ApiError(422, "Données invalides.")
            b = DB_.booking_by_code(code)
            if not b or b["status"] not in offers.OPEN_STATUSES:
                raise ApiError(409, "Ce chargement n'est plus disponible.")
            if not DB_.offer(b["id"], me.id):
                stored = DB_.get_quote(b["quote_id"], max_age_s=90 * 86400)
                if not stored:
                    raise ApiError(409, "Ce chargement n'est plus disponible.")
                DB_.add_offer(b["id"], me.id, offers.opening_price(booking.quote_from_payload(stored["quote"])))
            result = offers.decide(DB_, code, me.id, round(float(amount), 2), raw="réponse depuis le portail",
                                   channel="portail")
            DB_.audit("carrier", "offer_" + result["decision"], f"{code} carrier={me.id}")
            self.after_decision(code, result)
            return self.send_json(200, result)
        if method == "GET" and path == "/api/carrier/my":
            out = []
            for b in DB_.bookings_for_carrier(me.id):
                s, cu = json.loads(b["shipment"]), json.loads(b["customer"])
                load = offers.public_load(b)
                load.update({"price": b["carrier_price"], "pickup_address": s["pickup_address"],
                             "pickup_window": WINDOWS.get(s.get("pickup_window"), WINDOWS["journee"]),
                             "delivery_window": WINDOWS.get(s.get("delivery_window"), WINDOWS["journee"]),
                             "delivery_address": s["delivery_address"], "contact": f"{cu['name']} — {cu['phone']}",
                             "steps": [m["step"] for m in DB_.milestones(b["id"])]})
                out.append(load)
            return self.send_json(200, {"loads": out, "payables": [
                {"code": p["tracking_code"], "amount": p["amount"], "due_on": p["due_on"], "status": p["status"]}
                for p in DB_.list_payables(me.id)]})
        if method == "POST" and path == "/api/carrier/milestone":
            d = self.read_json()
            code, step = str(d.get("code", "")), d.get("step")
            b = DB_.booking_by_code(code) if security.CODE_RE.match(code) else None
            if not b or b["carrier_id"] != me.id or b["status"] != "confirmed" or step not in booking.CARRIER_STEPS:
                raise ApiError(404, "Chargement introuvable.")
            done = [m["step"] for m in DB_.milestones(b["id"])]
            expected = next((x for x in booking.CARRIER_STEPS if x not in done), None)
            if step != expected:
                raise ApiError(409, "Étape déjà enregistrée ou hors séquence.")
            note = ""
            if step == "delivered":
                try:
                    note = "Reçu par : " + security.clean_text(d.get("received_by"), 80)
                except ValueError:
                    raise ApiError(422, "Indiquez le nom de la personne qui a réceptionné la marchandise.")
            DB_.add_milestone(b["id"], step, f"carrier:{me.id}", note)
            DB_.audit("carrier", "milestone_" + step, f"{code} carrier={me.id}")
            if step == "delivered":
                DB_.add_payable(b["id"], me.id, b["carrier_price"], (date.today() + timedelta(days=30)).isoformat())
            self.notify_customer(b, f"FRETRAU — {STEP_LABELS[step]} ({code})",
                                 f"Bonjour,\n\nVotre envoi {code} : {STEP_LABELS[step]}.\n"
                                 f"Suivi : {PUBLIC_URL}/#{code}\n\nL'équipe FRETRAU")
            return self.send_json(200, {"ok": True, "step": step})
        raise ApiError(404, "Introuvable.")

    def api_carrier_loads(self, row, me):
        if row["status"] != "verified":
            return self.send_json(200, {"status": row["status"], "loads": []})
        loads, seen = [], set()
        for o in DB_.offers_for_carrier(me.id):
            if o["booking_status"] in offers.OPEN_STATUSES and o["status"] in ("sent", "countered"):
                load = offers.public_load(o)
                load.update({"price": o["price"], "offer": o["status"]})
                loads.append(load)
                seen.add(o["tracking_code"])
        for b in DB_.bookings_by_status(offers.OPEN_STATUSES):       # bourse interne : chargements encore ouverts
            if b["tracking_code"] in seen:
                continue
            s = json.loads(b["shipment"])
            stored = DB_.get_quote(b["quote_id"], max_age_s=90 * 86400)
            if not stored or not compliance.check(me, s["mode"], s["origin"], s["destination"],
                                                  date.fromisoformat(s["pickup_date"]))[0]:
                continue
            load = offers.public_load(b)
            load.update({"price": offers.opening_price(booking.quote_from_payload(stored["quote"])), "offer": "open"})
            loads.append(load)
        self.send_json(200, {"status": "verified", "loads": loads})

    def api_carrier_apply(self):
        if self.headers.get("X-Requested-With") != "fretrau":
            raise ApiError(404, "Introuvable.")
        if not RL_SIGNUP.allow(self.ip()):
            raise ApiError(429, "Trop de demandes, réessayez plus tard.")
        d = self.read_json()
        if d.get("website"):
            return self.send_json(200, {"ok": True})
        ident, pw = self.read_identity(d)
        siret = re.sub(r"\s", "", str(d.get("siret", "")))
        modes = [m for m in (d.get("modes") if isinstance(d.get("modes"), list) else []) if m in ("FTL", "LTL")]
        try:
            licence = security.clean_text(d.get("licence_no"), 40)
            insurance = date.fromisoformat(security.clean_text(d.get("insurance_until"), 10))
            base = security.clean_text(d.get("postcode"), 5)
            equipment = security.clean_text(d.get("equipment") or "-", 120)
        except ValueError:
            raise ApiError(422, "Dossier incomplet : licence, date d'assurance et code postal sont obligatoires.")
        if not security.valid_siret(siret):
            raise ApiError(422, "Numéro SIRET invalide.")
        if not modes or geo.locate(base) is None or base in geo.CITIES:
            raise ApiError(422, "Indiquez un code postal français valide et au moins un type de transport.")
        if insurance <= date.today():
            raise ApiError(422, "L'attestation d'assurance doit être en cours de validité.")
        if DB_.account_by_email(ident["email"]):
            raise ApiError(409, "Un compte existe déjà avec cette adresse e-mail.")
        report = vetting.check(siret, ident["company"])
        if report["status"] == "refused":
            DB_.audit("vetting_agent", "application_refused", siret)
            raise ApiError(422, "Cette entreprise apparaît comme fermée dans l'Annuaire des Entreprises. Contactez-nous en cas d'erreur.")
        fields = {"status": "pending_review", "licence_no": licence, "insurance_until": insurance.isoformat(),
                  "vetting": json.dumps(report, ensure_ascii=False),
                  "email": ident["email"], "phone": ident["phone"], "modes": ",".join(modes),
                  "europe": int(d.get("europe") is True), "equipment": equipment, "base_place": base}
        existing = DB_.carrier_by_siret(siret)
        if existing and existing["status"] != "prospect":
            raise ApiError(409, "Un dossier existe déjà pour ce SIRET.")
        if existing:
            DB_.update_carrier(existing["id"], **fields)
            cid = existing["id"]
        else:
            cid = DB_.add_carrier(source="candidature", name=ident["company"], siret=siret, **fields)
        aid = DB_.create_account("carrier", ident["email"], security.hash_password(pw), ident["name"],
                                 ident["company"], ident["phone"], carrier_id=cid)
        DB_.set_terms(aid, TERMS_VERSION)
        self.send_account_link(DB_.account_by_id(aid), "verify")
        DB_.audit("account", "carrier_application", f"carrier={cid} cgu={TERMS_VERSION}")
        self.send_json(201, {"ok": True, "role": "carrier"}, {"Set-Cookie": self.session_cookie(aid)})

    # ---------- admin ----------
    def api_admin(self, method, path):
        if method == "POST" and path == "/api/admin/login":
            ip = self.ip()
            if not RL_LOGIN.allow(ip) or GUARD.locked(ip):
                raise ApiError(429, "Trop de tentatives. Réessayez plus tard.")
            d = self.read_json()
            ok = (d.get("user") == "admin" and isinstance(d.get("password"), str)
                  and security.verify_password(d["password"], ADMIN_HASH))
            if ok and TOTP_SECRET and not security.verify_totp(TOTP_SECRET, str(d.get("totp", ""))):
                ok = False
            if not ok:
                GUARD.fail(ip)
                DB_.audit("anonymous", "admin_login_failed", ip)
                raise ApiError(401, "Identifiants invalides.")
            GUARD.ok(ip)
            DB_.audit("admin", "admin_login", ip)
            cookie = (f"fretrau_admin={SESSIONS.issue('admin')}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600"
                      + ("; Secure" if HTTPS else ""))
            return self.send_json(200, {"ok": True}, {"Set-Cookie": cookie})
        self.require_admin()
        if method == "GET" and path == "/api/admin/bookings":
            rows = DB_.list_bookings()
            for r in rows:
                s = json.loads(r.pop("shipment"))
                r["route"] = f"{geo.label(s['origin'])} → {geo.label(s['destination'])}"
            return self.send_json(200, {"bookings": rows})
        m = re.fullmatch(r"/api/admin/booking/(\d{1,9})", path)
        if method == "GET" and m:
            b = DB_.booking_by_id(int(m.group(1)))
            if not b:
                raise ApiError(404, "Introuvable.")
            for k in ("customer", "shipment", "agent_log"):
                b[k] = json.loads(b[k])
            DB_.audit("admin", "view_booking", str(b["id"]))
            return self.send_json(200, b)
        m = re.fullmatch(r"/api/admin/invoice/(\d{1,9})", path)
        if method == "GET" and m:
            b = DB_.booking_by_id(int(m.group(1)))
            if not b or b["status"] != "confirmed":
                raise ApiError(404, "Facture indisponible (transport non confirmé).")
            inv = DB_.get_or_create_invoice(b["id"], invoicing.build(b))
            DB_.audit("admin", "invoice", inv["number"])
            return self.send_json(200, inv)
        if method == "GET" and path == "/api/admin/carriers":
            q = self.query()
            status = q.get("status") if q.get("status") in ("prospect", "pending_review", "verified", "blocked") else None
            search = "".join(c for c in q.get("q", "") if c.isalnum() or c in " -'")[:40] or None
            rows = DB_.list_carriers(status=status, limit=100, search=search)
            keys = ("id", "status", "source", "name", "siret", "licence_no", "insurance_until", "base_place", "modes",
                    "europe", "equipment", "email", "phone", "km_base", "note")
            out = []
            for r in rows:
                item = {k: r[k] for k in keys}
                item["vetting"] = json.loads(r["vetting"]) if r["vetting"] else None
                out.append(item)
            return self.send_json(200, {"carriers": out,
                                        "counts": DB_.carrier_counts(), "demo": registry.demo_enabled(),
                                        "prospects_file": os.path.isfile(PROSPECTS_CSV)})
        if method == "POST" and path == "/api/admin/carrier/recheck":
            cid = self.read_json().get("id")
            row = DB_.carrier_row(cid) if isinstance(cid, int) and not isinstance(cid, bool) else None
            if not row or not row["siret"]:
                raise ApiError(404, "Transporteur introuvable ou sans SIRET.")
            report = vetting.check(row["siret"], row["name"].split(" (")[0])
            DB_.update_carrier(cid, vetting=json.dumps(report, ensure_ascii=False))
            DB_.audit("vetting_agent", "recheck_" + report["status"], f"carrier={cid}")
            return self.send_json(200, report)
        if method == "GET" and path == "/api/admin/inbox":
            return self.send_json(200, {"alerts": DB_.list_alerts(), "leads": DB_.list_leads()})
        if method == "POST" and path in ("/api/admin/alert/close", "/api/admin/lead/close"):
            rid = self.read_json().get("id")
            close = DB_.close_alert if "alert" in path else DB_.close_lead
            if isinstance(rid, bool) or not isinstance(rid, int) or not close(rid):
                raise ApiError(404, "Introuvable ou déjà traité.")
            DB_.audit("admin", path.rsplit("/", 2)[1] + "_closed", str(rid))
            return self.send_json(200, {"ok": True})
        if method == "POST" and path == "/api/admin/watch/run":
            result = watch.run(DB_, PUBLIC_URL)
            DB_.audit("admin", "watch_run", json.dumps(result))
            return self.send_json(200, result)
        if method == "POST" and path == "/api/admin/carrier/update":
            return self.api_admin_carrier_update()
        if method == "POST" and path == "/api/admin/prospects/import":
            return self.api_admin_import(self.read_json())
        if method == "GET" and path == "/api/admin/payables":
            return self.send_json(200, {"payables": DB_.list_payables(), "price_matches": DB_.list_price_matches(),
                                        "inbound_quotes": DB_.list_inbound_quotes()})
        if method == "POST" and path == "/api/admin/payable/pay":
            pid = self.read_json().get("id")
            if isinstance(pid, bool) or not isinstance(pid, int) or not DB_.pay_payable(pid):
                raise ApiError(404, "Paiement introuvable ou déjà réglé.")
            DB_.audit("admin", "payable_paid", str(pid))
            return self.send_json(200, {"ok": True})
        if method == "POST" and path == "/api/admin/intake":
            d = self.read_json()
            sender, text = str(d.get("from", "")).strip().lower(), d.get("text")
            if not security.EMAIL_RE.match(sender) or not isinstance(text, str) or not text.strip() or len(text) > 20000:
                raise ApiError(422, "Adresse e-mail ou texte invalide.")
            result = intake.handle(DB_, sender, text, PUBLIC_URL)
            DB_.audit("admin", "intake_" + result["status"], result.get("quote_id", ""))
            return self.send_json(200, result)
        if method == "POST" and path == "/api/admin/assign":
            d = self.read_json()
            code, cid, amount = str(d.get("code", "")), d.get("carrier_id"), d.get("amount")
            if (not security.CODE_RE.match(code) or isinstance(cid, bool) or not isinstance(cid, int)
                    or isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 20 <= amount <= 20000):
                raise ApiError(422, "Données invalides.")
            result = offers.decide(DB_, code, cid, round(float(amount), 2), raw="attribution manuelle", channel="admin")
            DB_.audit("admin", "assign_" + result["decision"], f"{code} carrier={cid}")
            self.after_decision(code, result)
            return self.send_json(200, result)
        if method == "GET" and path == "/api/admin/outbox":
            return self.send_json(200, {"mails": DB_.list_outbox()})
        if method == "POST" and path == "/api/admin/gdpr/anonymize":
            code = str(self.read_json().get("tracking_code", ""))
            if not security.CODE_RE.match(code) or not DB_.anonymize_booking(code):
                raise ApiError(404, "Réservation introuvable.")
            DB_.audit("admin", "gdpr_anonymize", code)
            return self.send_json(200, {"ok": True})
        if method == "GET" and path == "/api/admin/stats":
            rows = DB_.list_bookings(10000)
            done = [r for r in rows if r["status"] == "confirmed"]
            revenue = sum(r["customer_price_ht"] for r in done)
            cost = sum(r["carrier_price"] or 0 for r in done)
            return self.send_json(200, {
                "bookings": len(rows), "confirmed": len(done),
                "pending_human": sum(1 for r in rows if r["status"] == "pending_human"),
                "sourcing": sum(1 for r in rows if r["status"] == "sourcing"),
                "carriers": DB_.carrier_counts(), "alerts": len(DB_.list_alerts()),
                "leads": sum(1 for x in DB_.list_leads() if x["status"] == "open"),
                "revenue_ht": round(revenue, 2), "margin_ht": round(revenue - cost, 2),
                "audit": DB_.audit_tail(20), "audit_intact": DB_.verify_audit_chain()[0],
                "db_intact": DB_.integrity_ok(), "last_backup": last_backup()})
        if method == "POST" and path == "/api/admin/backup":
            if not BACKUP_DIR:
                raise ApiError(409, "Sauvegardes non configurées : définissez FRETRAU_BACKUP_DIR.")
            name = run_backup()
            if not name:
                raise ApiError(500, "La sauvegarde a échoué.")
            DB_.audit("admin", "backup", name)
            return self.send_json(200, {"file": name})
        raise ApiError(404, "Introuvable.")


    def api_admin_carrier_update(self):
        d = self.read_json()
        cid = d.get("id")
        row = DB_.carrier_row(cid) if isinstance(cid, int) and not isinstance(cid, bool) else None
        if not row:
            raise ApiError(404, "Transporteur introuvable.")
        fields = {}
        try:
            for key, size in (("licence_no", 40), ("note", 300), ("phone", 20)):
                if d.get(key):
                    fields[key] = security.clean_text(d[key], size)
            if d.get("insurance_until"):
                fields["insurance_until"] = date.fromisoformat(security.clean_text(d["insurance_until"], 10)).isoformat()
            if d.get("email"):
                fields["email"] = security.clean_text(d["email"], 254).lower()
                if not security.EMAIL_RE.match(fields["email"]):
                    raise ValueError
        except ValueError:
            raise ApiError(422, "Champ invalide.")
        status = d.get("status")
        if status is not None:
            if status not in ("prospect", "pending_review", "verified", "blocked"):
                raise ApiError(422, "Statut invalide.")
            if status == "verified":
                merged = {**row, **fields}
                if d.get("checks_done") is not True:
                    raise ApiError(422, "Confirmez que licence, assurance, Kbis et attestation de vigilance ont été contrôlés.")
                if not merged.get("licence_no") or not merged.get("insurance_until") \
                        or date.fromisoformat(merged["insurance_until"]) <= date.today():
                    raise ApiError(422, "Numéro de licence et assurance en cours de validité obligatoires pour valider.")
                fields["verified_at"] = time.time()
            fields["status"] = status
        if not DB_.update_carrier(cid, **fields):
            raise ApiError(422, "Aucune modification.")
        DB_.audit("admin", "carrier_update", f"carrier={cid} " + ",".join(sorted(k for k in fields if k != "note")))
        self.send_json(200, {"ok": True})

    def api_admin_import(self, d):
        """Charge les prospects de data/transporteurs.csv situés dans le rayon demandé autour de la base."""
        radius = d.get("radius_km")
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not 1 <= radius <= 2000:
            raise ApiError(422, "Rayon invalide (1 à 2000 km).")
        if not os.path.isfile(PROSPECTS_CSV):
            raise ApiError(404, "Fichier data/transporteurs.csv absent : lancez tools/import_transporteurs.py.")
        rows = []
        with open(PROSPECTS_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                km = float(r["km_base"])
                if km > radius:
                    break                                       # le fichier est trié par distance croissante
                if r["code_postal"] not in geo.POSTCODES:
                    continue
                name = r["nom"] + (f" ({r['enseigne']})" if r["enseigne"] and r["enseigne"] not in r["nom"] else "")
                rows.append({"name": name[:160], "siret": r["siret"], "base_place": r["code_postal"],
                             "modes": "FTL,LTL", "km_base": km,
                             "note": f"NAF {r['naf']} — {r['adresse']}"[:300]})
        added = DB_.add_prospects(rows)
        DB_.audit("admin", "prospects_import", f"rayon={radius} lus={len(rows)} ajoutés={added}")
        self.send_json(200, {"read": len(rows), "added": added})


def make_server(host="127.0.0.1", port=8080):
    return ThreadingHTTPServer((host, port), Handler)


def last_backup():
    """Nom et date de la dernière sauvegarde, ou None."""
    try:
        files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("fretrau-") and f.endswith(".db"))
    except OSError:
        return None
    return files[-1] if files else None


def run_backup():
    """Sauvegarde vérifiée de la base dans FRETRAU_BACKUP_DIR ; conserve les BACKUP_KEEP plus récentes."""
    try:
        os.makedirs(BACKUP_DIR, mode=0o700, exist_ok=True)
        name = time.strftime("fretrau-%Y%m%d-%H%M%S.db")
        tmp = os.path.join(BACKUP_DIR, name + ".tmp")
        if not DB_.backup_to(tmp):
            os.remove(tmp)
            return None
        os.chmod(tmp, 0o600)
        os.replace(tmp, os.path.join(BACKUP_DIR, name))
        files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("fretrau-") and f.endswith(".db"))
        for old in files[:-BACKUP_KEEP]:
            os.remove(os.path.join(BACKUP_DIR, old))
        return name
    except OSError:
        return None


def start_maintenance(interval_s: float = 6 * 3600):
    """Toutes les 6 h : sauvegarde (si configurée) et purge des données périmées."""
    def loop():
        while True:
            try:
                if BACKUP_DIR and run_backup():
                    DB_.audit("system", "backup", last_backup() or "")
                purged = DB_.purge()
                if any(purged.values()):
                    DB_.audit("system", "purge", json.dumps(purged))
            except Exception:
                pass
            time.sleep(interval_s)
    threading.Thread(target=loop, daemon=True).start()


def start_watch(interval_s: float):
    """Lance l'agent de surveillance en tâche de fond (relances d'offres, retards, assurances)."""
    def loop():
        while True:
            time.sleep(interval_s)
            try:
                result = watch.run(DB_, PUBLIC_URL)
                if any(result.values()):
                    DB_.audit("watch_agent", "run", json.dumps(result))
                mailer.flush(DB_)
            except Exception:
                pass                                  # l'agent ne doit jamais faire tomber le serveur
    threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    print(f"[FRETRAU] http://{host}:{port}  (admin : /admin.html)  LLM: {'actif' if llm.available() else 'gabarits'}")
    _watch = float(os.environ.get("FRETRAU_WATCH_SECONDS", "300"))
    if _watch > 0:
        start_watch(_watch)
    start_maintenance()
    if not BACKUP_DIR:
        print("[FRETRAU] ATTENTION : aucune sauvegarde automatique. Définissez FRETRAU_BACKUP_DIR (idéalement un autre disque).")
    make_server(host, port).serve_forever()
