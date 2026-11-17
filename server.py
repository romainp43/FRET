#!/usr/bin/env python3
"""Serveur FRETRAU (bibliothèque standard uniquement, aucune dépendance).

Lancement :  FRETRAU_ADMIN_PASSWORD='un-mot-de-passe-long' python3 server.py
Variables :  PORT, HOST, FRETRAU_DB, FRETRAU_SECRET, FRETRAU_HTTPS=1, FRETRAU_TRUST_PROXY=1,
             FRETRAU_DEMO_SPEED (1 = temps réel, 360 = 1 h simulée en 10 s), ANTHROPIC_API_KEY (optionnel)
"""
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import statistics
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from fretrau import booking, chaining, claims, driver, geo, vetting, invoicing, mailer, payments, places, pricing, security, sms, watch_run
from fretrau.agents import claims_triage, guard, rfq
from fretrau.agents import email_agent, intake, ratematch, llm
from fretrau.db import DB

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8", ".ico": "image/x-icon"}

HTTPS = os.environ.get("FRETRAU_HTTPS") == "1"
TRUST_PROXY = os.environ.get("FRETRAU_TRUST_PROXY") == "1"
DEMO_SPEED = float(os.environ.get("FRETRAU_DEMO_SPEED", "1"))
DEMO_TIMELINE = os.environ.get("FRETRAU_DEMO_TIMELINE", "1") == "1"      # 0 en production : aucun jalon simulé, seulement des événements réels
CARRIER_PAY_DAYS = int(os.environ.get("FRETRAU_CARRIER_PAY_DAYS", "0"))  # délai de paiement transporteur après preuve de livraison
if not 0 <= CARRIER_PAY_DAYS <= 30:
    raise SystemExit("[FRETRAU] FRETRAU_CARRIER_PAY_DAYS doit être compris entre 0 et 30 (plafond légal : 30 jours, art. L441-11 C. com.).")

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
LEGAL_VERSION = os.environ.get("FRETRAU_LEGAL_VERSION", "2026-11-17")   # version des CGV / politique de confidentialité
if not TOTP_SECRET:
    print("[FRETRAU] ATTENTION : 2FA admin désactivée. Générez un secret : "
          "python3 -c \"from fretrau.security import new_totp_secret as n; print(n())\" "
          "puis FRETRAU_ADMIN_TOTP_SECRET=... (à ajouter dans une application d'authentification).")
ALLOWED_HOSTS = {h.strip().lower() for h in os.environ.get("FRETRAU_ALLOWED_HOSTS", "").split(",") if h.strip()}
SESSION_SECRET = os.environ.get("FRETRAU_SECRET", secrets.token_hex(32))
SESSIONS = security.Sessions(SESSION_SECRET.encode())
ACCT_SESSIONS = security.Sessions((SESSION_SECRET + "|compte").encode(), ttl=86400 * 7)   # secret distinct : un cookie client n'ouvre jamais l'admin
RL_ACCT = security.RateLimiter(5, 900)

DB_ = DB(os.environ.get("FRETRAU_DB", os.path.join(ROOT, "fretrau.db")))
RL_GLOBAL = security.RateLimiter(120, 60)
TEMPERATURE_RANGES = {"+2/+4 °C": "Frais (+2 à +4 °C)", "0/+2 °C": "Frais (0 à +2 °C)", "-18 °C": "Surgelé (−18 °C)", "-25 °C": "Surgelé (−25 °C)", "+15/+25 °C": "Tempéré (+15 à +25 °C)"}
RL_QUOTE = security.RateLimiter(20, 60)
RL_BOOK = security.RateLimiter(5, 600)
RL_LOGIN = security.RateLimiter(10, 900)
RL_TRACK = security.RateLimiter(30, 60)
RL_FORM = security.RateLimiter(6, 3600)                       # candidatures, demandes de contact, réclamations
OPS_EMAIL = os.environ.get("FRETRAU_OPS_EMAIL", "")           # reçoit les alertes (candidature, contact, réclamation)
GUARD = security.LoginGuard()


class ApiError(Exception):
    def __init__(self, status, message, extra=None):
        self.extra = extra or {}
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

    def admin_user(self):  # renvoie (nom, rôle) ou None
        if self.headers.get("X-Requested-With") != "fretrau":
            return None
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "fretrau_admin":
                name = SESSIONS.verify(v)
                return self.resolve_role(name) if name else None
        return None

    def resolve_role(self, name):
        """Le rôle est relu à chaque requête : désactiver un compte coupe l'accès immédiatement."""
        if DB_.users_count() == 0:
            return (name, "admin") if name == "admin" else None   # mode démo : compte unique via variables d'environnement
        u = DB_.get_user(name)
        return (name, u["role"]) if u and u["active"] else None

    def require_admin(self):
        user = self.admin_user()
        if not user:
            raise ApiError(401, "Authentification requise.")
        return user

    PERMS = {  # rôle -> préfixes/points d'accès autorisés
        "admin": None,
        "ops": ("bookings", "booking", "outbox", "stats", "me", "pod", "carriers", "contacts", "claims", "chaining", "watchtower", "driver-link", "sms", "directory", "rfq"),
        "finance": ("bookings", "invoice", "stats", "me", "payables"),
    }

    def allow(self, role, resource):
        allowed = self.PERMS.get(role)
        return allowed is None or resource in allowed

    # ---------- routage ----------
    def dispatch(self, method):
        try:
            if ALLOWED_HOSTS and (self.headers.get("Host") or "").split(":")[0].lower() not in ALLOWED_HOSTS:
                raise ApiError(400, "Hôte non autorisé.")     # anti Host-header injection / DNS rebinding
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
            self.send_json(e.status, {"error": e.message, **e.extra})
        except Exception:
            self.send_json(500, {"error": "Erreur interne."})      # jamais de trace au client

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    # ---------- fichiers statiques ----------
    def static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        full = os.path.realpath(os.path.join(WEB, path.lstrip("/")))
        ext = os.path.splitext(full)[1].lower()
        if not full.startswith(WEB + os.sep) or ext not in MIME or not os.path.isfile(full):
            page = os.path.join(WEB, "404.html")
            if os.path.isfile(page) and "text/html" in (self.headers.get("Accept") or ""):
                with open(page, "rb") as f:
                    return self.send_bytes(404, MIME[".html"], f.read())
            raise ApiError(404, "Introuvable.")
        with open(full, "rb") as f:
            self.send_bytes(200, MIME[ext], f.read())

    # ---------- API ----------
    def api(self, method, path):
        if method == "GET" and path == "/api/cities":
            return self.send_json(200, {"cities": sorted(geo.CITIES), "options": pricing.OPTIONS, "temperature_ranges": TEMPERATURE_RANGES, "llm": llm.available(),
                                        "coverage": {"complete": places.available(), "places": places.count() + len(geo.CITIES)}})
        if method == "GET" and path == "/api/places":
            if not RL_TRACK.allow(self.ip()):
                raise ApiError(429, "Trop de requêtes.")
            q = (parse_qs(urlparse(self.path).query).get("q") or [""])[0][:80]
            return self.send_json(200, {"results": geo.suggest(q, 10), "complete": places.available()})
        if method == "POST" and path == "/api/quote":
            return self.api_quote()
        m = re.fullmatch(r"/api/quote/([A-Za-z0-9_-]{8,40})", path)
        if method == "GET" and m:
            return self.api_quote_get(m.group(1))
        if method == "POST" and path == "/api/ratematch":
            return self.api_ratematch()
        if method == "POST" and path == "/api/intake/email":
            return self.api_intake_email()
        if method == "POST" and path == "/api/book":
            return self.api_book()
        m = re.fullmatch(r"/api/track/([^/]+)", path)
        if method == "GET" and m:
            return self.api_track(m.group(1))
        m = re.fullmatch(r"/api/doc/([^/]+)", path)
        if method == "GET" and m:
            return self.api_doc(m.group(1))
        if method == "POST" and path == "/api/webhook/carrier-status":
            return self.api_carrier_status()
        if method == "POST" and path == "/api/webhook/inbound-mail":
            return self.api_inbound_mail()
        if method == "POST" and path == "/api/webhook/rfq-reply":
            return self.api_rfq_reply()
        if method == "POST" and path == "/api/carrier/apply":
            return self.api_carrier_apply()
        if method == "POST" and path == "/api/contact":
            return self.api_contact()
        if method == "POST" and path == "/api/claim":
            return self.api_claim()
        if method == "POST" and path.startswith(("/api/indicative", "/api/sms/", "/api/driver/", "/api/pay/", "/api/webhook/stripe", "/api/account/")):
            return self.api_extra(path)
        if method == "GET" and path == "/api/account/bookings":
            return self.api_account_bookings()
        if path.startswith("/api/admin/"):
            return self.api_admin(method, path)
        raise ApiError(404, "Introuvable.")

    # ---------- modules complémentaires (SMS, chauffeur, paiement, compte client, estimations) ----------
    def api_extra(self, path):
        if path == "/api/webhook/stripe":
            secret = os.environ.get("FRETRAU_STRIPE_WEBHOOK_SECRET", "")
            if not secret:
                raise ApiError(404, "Introuvable.")
            raw = []
            self.read_json(raw_out=raw)
            try:
                ev = payments.verify_webhook(raw[0] if raw else b"", self.headers.get("Stripe-Signature", ""), secret)
            except ValueError as e:
                raise ApiError(400, str(e))
            obj = (ev.get("data") or {}).get("object") or {}
            if ev.get("type") == "checkout.session.completed" and obj.get("id") and DB_.get_payment_by_ref(obj["id"]):
                DB_.set_payment_status(obj["id"], "paid")
                DB_.audit("stripe", "payment_paid", obj["id"])
            return self.send_json(200, {"received": True})
        d = self.read_json()
        if path == "/api/indicative":
            if not RL_FORM.allow(self.ip() + "|ind") and not RL_TRACK.allow(self.ip()):
                raise ApiError(429, "Trop de requêtes.")
            try:
                return self.send_json(200, pricing.indicative(str(d.get("kind", "")), str(d.get("origin", ""))[:80], str(d.get("destination", ""))[:80],
                                                              d.get("pallets"), d.get("weight_kg")))
            except pricing.QuoteError as e:
                raise ApiError(422, str(e))
        if path == "/api/sms/stop":
            if not RL_FORM.allow(self.ip() + "|sms"):
                raise ApiError(429, "Trop de requêtes.")
            if d.get("website"):
                return self.send_json(200, {"ok": True})
            if not sms.stop(DB_, str(d.get("phone", "")), SESSION_SECRET):
                raise ApiError(422, "Numéro invalide.")
            DB_.audit("public", "sms_optout", "")
            return self.send_json(200, {"ok": True})
        if path.startswith("/api/driver/"):
            token = str(d.get("token", ""))
            if not RL_TRACK.allow(self.ip()):
                raise ApiError(429, "Trop de requêtes.")
            r = driver.resolve(DB_, token)
            if not r:
                raise ApiError(404, "Lien invalide ou expiré.")
            link, b = r
            th = driver._h(token)
            if path == "/api/driver/consent":
                DB_.consent_driver_link(th)
                return self.send_json(200, {"ok": True, "code": b["tracking_code"]})
            if path == "/api/driver/stop":
                DB_.revoke_driver_link(th)
                return self.send_json(200, {"ok": True})
            if path == "/api/driver/position":
                res = driver.record(DB_, token, d.get("lat"), d.get("lon"), d.get("accuracy"))
                if res in ("bad_position", "no_consent"):
                    raise ApiError(422, "Position refusée.")
                return self.send_json(200, {"ok": True, "result": res})
            raise ApiError(404, "Introuvable.")
        if path == "/api/pay/checkout":
            if not payments.enabled():
                raise ApiError(503, "Le paiement en ligne n'est pas activé : la facture est payable après le transport.")
            stored = DB_.get_quote(str(d.get("quote_id", ""))[:40])
            if not stored:
                raise ApiError(404, "Devis introuvable ou expiré.")
            q = stored["quote"]
            email = security.clean_text(d.get("email"), 254)
            if not security.EMAIL_RE.match(email):
                raise ApiError(422, "E-mail invalide.")
            try:
                sess = payments.create_checkout(d["quote_id"], q["price_ttc"], f"Transport {q['origin']} → {q['destination']}", email,
                                                f"{PUBLIC_URL}/suivi.html?paiement=ok", f"{PUBLIC_URL}/?paiement=annule")
            except Exception:
                raise ApiError(502, "Le prestataire de paiement est indisponible.")
            DB_.add_payment(d["quote_id"], "stripe", sess["provider_ref"], payments.cents(q["price_ttc"]))
            return self.send_json(200, {"url": sess["url"]})
        if path in ("/api/account/request", "/api/account/verify"):
            email = security.clean_text(d.get("email"), 254).lower()
            if not security.EMAIL_RE.match(email) or not RL_ACCT.allow(self.ip()):
                raise ApiError(429 if security.EMAIL_RE.match(email) else 422, "Requête refusée.")
            if path == "/api/account/request":
                if DB_.bookings_for_email(email, 1):                     # réponse identique que le compte existe ou non (pas d'énumération)
                    code = f"{secrets.randbelow(10 ** 6):06d}"
                    DB_.set_login_code(email, hashlib.sha256((SESSION_SECRET + email + code).encode()).hexdigest(), time.time() + 600)
                    mailer.queue(DB_, email, "Votre code de connexion FRETRAU", f"Votre code : {code}\nValable 10 minutes. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.")
                    try:
                        mailer.flush(DB_)
                    except Exception:
                        pass
                return self.send_json(200, {"ok": True})
            row = DB_.get_login_code(email)
            good = False
            if row and row["attempts"] < 5 and row["expires_at"] > time.time():
                DB_.bump_login_attempt(email)
                cand = hashlib.sha256((SESSION_SECRET + email + str(d.get("code", ""))).encode()).hexdigest()
                good = hmac.compare_digest(cand, row["code_hash"])
            if not good:
                raise ApiError(401, "Code invalide ou expiré.")
            DB_.delete_login_code(email)
            cookie = f"fretrau_acct={ACCT_SESSIONS.issue(email)}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800" + ("; Secure" if HTTPS else "")
            return self.send_json(200, {"ok": True}, {"Set-Cookie": cookie})
        raise ApiError(404, "Introuvable.")

    def api_account_bookings(self):
        if self.headers.get("X-Requested-With") != "fretrau":
            raise ApiError(401, "Authentification requise.")
        email = None
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "fretrau_acct":
                email = ACCT_SESSIONS.verify(v)
        if not email:
            raise ApiError(401, "Authentification requise.")
        out = []
        for r in DB_.bookings_for_email(email):
            sh = json.loads(r["shipment"])
            out.append({"tracking_code": r["tracking_code"], "status": r["status"], "origin": sh.get("origin"), "destination": sh.get("destination"),
                        "pickup_date": sh.get("pickup_date"), "price_ht": r["customer_price_ht"]})
        return self.send_json(200, {"bookings": out})

    # ---------- formulaires publics : candidature transporteur, contact / rendez-vous, réclamation ----------
    def _form_guard(self):
        if not RL_FORM.allow(self.ip()):
            raise ApiError(429, "Trop de demandes envoyées depuis votre connexion, réessayez plus tard.")
        d = self.read_json()
        if d.get("website"):                                   # champ piège anti-robots
            raise ApiError(200, "ok", {"ok": True})
        return d

    def _notify_ops(self, subject, body):
        if OPS_EMAIL:
            try:
                mailer.queue(DB_, OPS_EMAIL, subject, body)
                mailer.flush(DB_)
            except Exception:
                pass

    def api_carrier_apply(self):
        try:
            d = self._form_guard()
        except ApiError as e:
            if e.status == 200:
                return self.send_json(200, {"ok": True})
            raise
        try:
            c = lambda k, n=120: security.clean_text(d.get(k), n)          # noqa: E731
            country = c("country", 2).upper()
            equipment = [x for x in (d.get("equipment") if isinstance(d.get("equipment"), list) else []) if x in vetting.EQUIPMENT]
            fleet = d.get("fleet_size")
            cover = d.get("insurance_cover_eur")
            if isinstance(fleet, bool) or not isinstance(fleet, int) or not 1 <= fleet <= 5000:
                raise ValueError("Taille de flotte invalide (1 à 5 000 véhicules).")
            if isinstance(cover, bool) or not isinstance(cover, (int, float)) or not 0 < cover <= 50_000_000:
                raise ValueError("Montant de garantie d'assurance invalide.")
            app = {"company": c("company"), "country": country, "company_id": c("company_id", 20), "siret": (c("siret", 20) if d.get("siret") else ""),
                   "vat": c("vat", 20), "licence": c("licence", 60), "insurer": c("insurer", 80),
                   "insurance_until": c("insurance_until", 10), "insurance_cover_eur": float(cover), "fleet_size": fleet,
                   "equipment": equipment, "countries": [x for x in (d.get("countries") if isinstance(d.get("countries"), list) else []) if x in vetting.COUNTRIES],
                   "contact_name": c("contact_name", 80), "email": c("email", 254), "phone": c("phone", 20),
                   "accept_charter": d.get("accept_charter") is True, "consent_at": time.time()}
            if not security.EMAIL_RE.match(app["email"]) or not security.PHONE_RE.match(app["phone"]):
                raise ValueError("Coordonnées invalides.")
        except ValueError as e:
            raise ApiError(422, str(e) if str(e) not in ("Champ vide ou trop long.", "Champ texte attendu.") else "Formulaire incomplet ou invalide : vérifiez chaque champ.")
        res = vetting.check(app)
        if not res["ok"]:
            raise ApiError(422, "Votre dossier ne peut pas être enregistré en l'état.", {"problems": res["errors"]})
        app_id = DB_.add_application(app, res["checks"])
        DB_.audit("public", "carrier_application", str(app_id))
        self._notify_ops(f"[FRETRAU] Nouvelle candidature transporteur #{app_id}", f"{app['company']} ({app['country']}) — à examiner dans l'administration.")
        self.send_json(201, {"ok": True, "reference": f"T-{app_id:05d}",
                             "message": "Dossier reçu. Nous vérifions l'entreprise, la licence et l'assurance avant tout transport, puis nous vous répondons par e-mail."})

    CONTACT_TOPICS = {"privacy": "Exercice de mes droits (données personnelles)", "quote": "Demande de prix", "intermodal": "Combiné rail-route (sur devis)", "special": "Transport spécial / hors gabarit",
                      "account": "Compte entreprise / contrat annuel", "claim": "Question sur un envoi", "other": "Autre"}

    def api_contact(self):
        try:
            d = self._form_guard()
        except ApiError as e:
            if e.status == 200:
                return self.send_json(200, {"ok": True})
            raise
        try:
            topic = d.get("topic") if d.get("topic") in self.CONTACT_TOPICS else "other"
            req = {"name": security.clean_text(d.get("name"), 80), "company": security.clean_text(d.get("company"), 120) if d.get("company") else "",
                   "email": security.clean_text(d.get("email"), 254), "phone": security.clean_text(d.get("phone"), 20) if d.get("phone") else "",
                   "topic": topic, "message": security.clean_text(d.get("message"), 1500),
                   "slot": security.clean_text(d.get("slot"), 80) if d.get("slot") else "",
                   "consent": d.get("consent") is True, "consent_at": time.time()}
            if not security.EMAIL_RE.match(req["email"]) or (req["phone"] and not security.PHONE_RE.match(req["phone"])):
                raise ValueError
            if not req["consent"]:
                raise ApiError(422, "Merci de cocher la case pour que nous puissions vous répondre.")
        except ValueError:
            raise ApiError(422, "Formulaire incomplet ou invalide : nom, e-mail valide et message sont requis.")
        cid = DB_.add_contact(req)
        DB_.audit("public", "contact_request", str(cid))
        self._notify_ops(f"[FRETRAU] Demande de contact #{cid} — {self.CONTACT_TOPICS[topic]}", f"{req['name']} <{req['email']}> : {req['message'][:300]}")
        self.send_json(201, {"ok": True, "message": "Message reçu, nous vous répondons dès que possible."})

    def api_claim(self):
        try:
            d = self._form_guard()
        except ApiError as e:
            if e.status == 200:
                return self.send_json(200, {"ok": True})
            raise
        code = str(d.get("tracking_code", ""))
        email = str(d.get("email", "")).strip().lower()
        b = DB_.booking_by_code(code) if security.CODE_RE.match(code) else None
        cust = json.loads(b["customer"]) if b else {}
        if not b or b["status"] != "confirmed" or cust.get("email", "").lower() != email:
            raise ApiError(404, "Aucun envoi ne correspond à ce code et à cet e-mail.")     # message unique : pas d'énumération
        try:
            kind = d.get("kind") if d.get("kind") in claims.KINDS else "other"
            delivered_on = date.fromisoformat(security.clean_text(d.get("delivered_on"), 10))
            if not date.today() - timedelta(days=400) <= delivered_on <= date.today():
                raise ValueError
            item = {"kind": kind, "delivered_on": delivered_on.isoformat(),
                    "description": security.clean_text(d.get("description"), 1500),
                    "reserves_on_receipt": d.get("reserves_on_receipt") is True,
                    "amount_eur": security.clean_amount(d.get("amount_eur"))}
        except ValueError:
            raise ApiError(422, "Date de livraison (passée, de moins d'un an) et description du problème requises.")
        s = json.loads(b["shipment"])
        intl = geo.country(s["origin"]) != geo.country(s["destination"])
        dl = claims.deadlines(kind, delivered_on, intl)
        cid = DB_.add_claim(b["id"], item, dl)
        DB_.audit("customer", "claim_filed", f"{code} #{cid}")
        self._notify_ops(f"[FRETRAU] Réclamation #{cid} — {code}", f"{claims.KINDS[kind]} : {item['description'][:300]}")
        try:
            mailer.queue(DB_, cust["email"], f"FRETRAU — réclamation enregistrée ({code})",
                         f"Bonjour,\n\nNous avons enregistré votre réclamation n°{cid} pour l'envoi {code} ({claims.KINDS[kind]}).\n"
                         f"Pour préserver vos droits, envoyez une protestation écrite avant le {dl['written_reserve_before']} ({dl['rule']}).\n"
                         f"L'action en justice se prescrit le {dl['limitation_date']}.\n\nL'équipe FRETRAU")
            mailer.flush(DB_)
        except Exception:
            pass
        self.send_json(201, {"ok": True, "claim": cid, "deadlines": dl,
                             "message": "Réclamation enregistrée. Conservez vos photos et le récépissé de livraison."})

    def api_quote(self):
        if not RL_QUOTE.allow(self.ip()):
            raise ApiError(429, "Trop de devis demandés, patientez un instant.")
        d = self.read_json()
        try:
            origin = geo.canonical(security.clean_text(d.get("origin"), 80))
            destination = geo.canonical(security.clean_text(d.get("destination"), 80))
            mode = security.clean_text(d.get("mode"), 3)
            pallets = d.get("pallets")
            weight = d.get("weight_kg")
            if isinstance(pallets, bool) or isinstance(weight, bool):
                raise ValueError("Valeur numérique invalide.")
            options = d.get("options") if isinstance(d.get("options"), dict) else {}
            pickup = date.fromisoformat(security.clean_text(d.get("pickup_date"), 10))
            deliver_by = d.get("deliver_by")
            deliver_by = date.fromisoformat(security.clean_text(deliver_by, 10)) if deliver_by else None
            today = date.today()
            if not today <= pickup <= today + timedelta(days=60):
                raise pricing.QuoteError("La date d'enlèvement doit être dans les 60 prochains jours.")
            if deliver_by is not None and deliver_by < pickup:
                raise pricing.QuoteError("La livraison souhaitée ne peut pas précéder l'enlèvement.")
            q = pricing.build_quote(origin, destination, mode, pallets, weight, options, pickup, deliver_by)
        except places.PlaceError as e:
            raise ApiError(422, str(e), {"suggestions": e.suggestions})
        except pricing.QuoteError as e:
            raise ApiError(422, str(e))
        except ValueError:
            raise ApiError(422, "Données invalides : vérifiez le formulaire.")
        quote_id = secrets.token_urlsafe(12)
        shipment = {"pallets": q.pallets, "weight_kg": weight, "pickup_date": pickup.isoformat(),
                    "deliver_by": deliver_by.isoformat() if deliver_by else None, "options": q.options}
        trange = d.get("temperature_range")
        if q.options.get("temperature") and trange in TEMPERATURE_RANGES:
            shipment["temperature_range"] = trange
        DB_.save_quote(quote_id, {"quote": asdict(q), "shipment": shipment})
        view = self.quote_view(quote_id, asdict(q))
        view["alternatives"] = self.quote_alternatives(origin, destination, mode, pallets, weight, options,
                                                       pickup, deliver_by, q, view)
        self.send_json(200, view)

    @staticmethod
    def quote_alternatives(origin, destination, mode, pallets, weight, options, pickup, deliver_by, q, view):
        """Formule inverse (Express si Standard demandé, et inversement), calculée par la même grille.
        Ce ne sont pas des offres de transporteurs distincts : le prix reste calculé par FRETRAU."""
        want_urgent = not bool(options.get("urgent"))
        alt_options = dict(options)
        alt_options["urgent"] = want_urgent
        try:
            alt = pricing.build_quote(origin, destination, mode, pallets, weight, alt_options, pickup, deliver_by)
        except (pricing.QuoteError, places.PlaceError, ValueError):
            return []
        if alt.price_ht == q.price_ht and alt.transit_days == q.transit_days:
            return []
        alt_id = secrets.token_urlsafe(12)
        DB_.save_quote(alt_id, {"quote": asdict(alt), "shipment": {
            "pallets": alt.pallets, "weight_kg": weight, "pickup_date": pickup.isoformat(),
            "deliver_by": deliver_by.isoformat() if deliver_by else None, "options": alt.options}})
        return [{"quote_id": alt_id, "label": "Express" if want_urgent else "Standard",
                 "price_ht": alt.price_ht, "transit_days": alt.transit_days,
                 "earliest_delivery": alt.earliest_delivery,
                 "delta_ht": round(alt.price_ht - q.price_ht, 2)}]

    @staticmethod
    def quote_view(quote_id, q):
        """Vue client d'un devis : le détail inclut la marge, jamais le coût d'achat brut."""
        scale = q["price_ht"] / q["carrier_cost_estimate"]
        return {
            "quote_id": quote_id, "price_ht": q["price_ht"], "vat": q["vat"], "price_ttc": q["price_ttc"],
            "distance_km": q["distance_km"], "transit_days": q["transit_days"],
            "breakdown": {k: round(v * scale, 2) for k, v in q["breakdown"].items()},
            "valid_hours": 24, "mode": q["mode"], "origin": q["origin"], "destination": q["destination"],
            "earliest_delivery": q["earliest_delivery"], "warnings": q["warnings"], "pallets": q["pallets"],
            "co2_kg": q.get("co2_kg", 0.0),
        }

    def api_quote_get(self, quote_id):
        if not RL_TRACK.allow(self.ip()):
            raise ApiError(429, "Trop de requêtes.")
        stored = DB_.get_quote(quote_id[:40])
        if not stored:
            raise ApiError(404, "Devis introuvable ou expiré.")
        self.send_json(200, self.quote_view(quote_id, stored["quote"]))

    def api_ratematch(self):
        """Garantie d'alignement : « j'ai un devis moins cher pour la même expédition »."""
        if not RL_QUOTE.allow(self.ip()):
            raise ApiError(429, "Trop de demandes, patientez un instant.")
        d = self.read_json()
        qid = str(d.get("quote_id", ""))[:40]
        stored = DB_.get_quote(qid)
        if not stored:
            raise ApiError(404, "Devis introuvable ou expiré.")
        if DB_.booking_exists_for_quote(qid):
            raise ApiError(409, "Ce devis a déjà été réservé.")
        if stored.get("rate_match"):
            raise ApiError(409, "Un alignement a déjà été étudié pour ce devis.")
        try:
            price = security.clean_amount(d.get("competitor_price_ht"))
            reference = security.clean_text(d.get("reference"), 120)
        except ValueError:
            price = reference = None
        if not price or not reference:
            raise ApiError(422, "Indiquez le prix HT du devis concurrent et sa référence (société, numéro de devis).")
        result = ratematch.evaluate(stored["quote"], price)
        stored["rate_match"] = {"outcome": result["outcome"], "previous_price_ht": stored["quote"]["price_ht"],
                                "competitor_price_ht": price, "reference": reference}
        if result["outcome"] in ("matched", "counter"):
            stored["quote"] = ratematch.apply(stored["quote"], result)
            DB_.audit("system", "ratematch_" + result["outcome"], f"{qid} {price}")
        DB_.update_quote(qid, stored)
        self.send_json(200, {"outcome": result["outcome"], "message": result["message"],
                             "quote": self.quote_view(qid, stored["quote"])})

    def verify_signed(self):
        """Corps JSON signé HMAC (X-Signature) avec horodatage anti-rejeu : utilisé par les webhooks e-mail."""
        if not WEBHOOK_SECRET:
            raise ApiError(503, "Webhook non configuré.")
        raw = []
        d = self.read_json(raw)
        import hmac
        expected = hmac.new(WEBHOOK_SECRET.encode(), raw[0], hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, self.headers.get("X-Signature", "")):
            DB_.audit("anonymous", "webhook_bad_signature", self.ip())
            raise ApiError(401, "Signature invalide.")
        ts = d.get("ts")
        if not isinstance(ts, (int, float)) or abs(time.time() - ts) > 300:
            raise ApiError(400, "Horodatage invalide ou expiré.")
        return d

    def api_intake_email(self):
        """E-mail de demande de prix en texte libre → devis structuré (ou liste précise des informations manquantes)."""
        d = self.verify_signed()
        text = d.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            raise ApiError(422, "Texte invalide.")
        res = intake.parse(text)
        if not res["complete"]:
            return self.send_json(200, {"status": "needs_info", "missing": res["missing"],
                                        "reply": intake.reply_needing_info(res)})
        f = res["fields"]
        try:
            q = pricing.build_quote(f["origin"], f["destination"], f["mode"], f.get("pallets"), f["weight_kg"],
                                    f.get("options", {}), date.fromisoformat(f["pickup_date"]),
                                    date.fromisoformat(f["deliver_by"]) if f.get("deliver_by") else None)
        except pricing.QuoteError as e:
            return self.send_json(200, {"status": "needs_info", "missing": [str(e)],
                                        "reply": intake.reply_needing_info({"missing": [str(e)]})})
        qid = secrets.token_urlsafe(12)
        shipment = {"pallets": q.pallets, "weight_kg": f["weight_kg"], "pickup_date": f["pickup_date"],
                    "deliver_by": f.get("deliver_by"), "options": q.options}
        DB_.save_quote(qid, {"quote": asdict(q), "shipment": shipment, "source": "email"})
        DB_.audit("email_agent", "intake_quote", qid)
        link = f"{PUBLIC_URL}/#devis={qid}"
        mode_txt = "camion complet" if q.mode == "FTL" else "palettes"
        reply = (f"Bonjour,\n\nVoici votre prix pour {q.origin} → {q.destination} ({mode_txt}, {q.distance_km:.0f} km) : "
                 f"{q.price_ht:.2f} € HT, valable 24 h.\n"
                 + ("\nHypothèses retenues :\n" + "\n".join(f"  - {a}" for a in res["assumptions"]) + "\n" if res["assumptions"] else "")
                 + f"\nPour réserver : {link}\n\nL'équipe FRETRAU")
        self.send_json(200, {"status": "quoted", "quote": self.quote_view(qid, asdict(q)),
                             "assumptions": res["assumptions"], "reply": reply})

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
            customer["consent"] = {
                "cgv_version": LEGAL_VERSION, "accepted_at": time.time(),
                "ip_hash": hashlib.sha256((self.ip() + SESSION_SECRET).encode()).hexdigest()[:32],  # preuve sans stocker l'IP
            }
            shipment = dict(stored["shipment"])
            shipment.update({
                "pickup_window": security.clean_window(d.get("pickup_window")),
                "delivery_window": security.clean_window(d.get("delivery_window")),
                "site_contact_name": security.clean_text(d.get("site_contact_name"), 80),
                "site_contact_phone": security.clean_text(d.get("site_contact_phone"), 20),
                "loading_notes": (security.clean_text(d["loading_notes"], 300) if d.get("loading_notes") else ""),
                "goods_value_eur": security.clean_amount(d.get("goods_value_eur")),
                "origin": stored["quote"]["origin"], "destination": stored["quote"]["destination"],
                "mode": stored["quote"]["mode"],
                "pickup_address": security.clean_text(d.get("pickup_address"), 200),
                "delivery_address": security.clean_text(d.get("delivery_address"), 200),
                "goods": security.clean_text(d.get("goods"), 200),
            })
        except ValueError as e:
            raise ApiError(422, str(e))

        if not security.PHONE_RE.match(shipment["site_contact_phone"]):
            raise ApiError(422, "Téléphone du contact sur site invalide.")
        customer["sms_consent"] = d.get("sms_consent") is True
        assessment = guard.assess(customer, shipment, stored["quote"]["price_ht"], DB_.recent_customer_activity(time.time() - 86400), time.time())
        if assessment["action"] == "review":
            result = {"status": "pending_human", "carrier": None, "price": None,
                      "log": {"escalation_reason": "Contrôle anti-fraude : " + " ; ".join(assessment["flags"]), "alerts": [], "ranking": [],
                              "rejected_by_compliance": [], "negotiations": []}}
        else:
            result = booking.run(stored["quote"], date.fromisoformat(shipment["pickup_date"]),
                                 date.fromisoformat(shipment["deliver_by"]) if shipment.get("deliver_by") else None,
                                 shipment.get("goods_value_eur"))
        result["log"]["guard"] = assessment
        if stored.get("rate_match") and stored["rate_match"]["outcome"] in ("matched", "counter"):
            rm = stored["rate_match"]
            result["log"].setdefault("alerts", []).append(
                f"Alignement tarifaire ({rm['outcome']}) : prix initial {rm['previous_price_ht']} € → {stored['quote']['price_ht']} € HT. "
                f"Justificatif à contrôler avant l'enlèvement : {rm['reference']}.")
        code = booking.new_tracking_code()
        carrier = result["carrier"]
        DB_.save_booking(
            tracking_code=code, quote_id=quote_id, status=result["status"], customer=customer,
            shipment=shipment, carrier_id=carrier.id if carrier else None,
            carrier_name=carrier.name if carrier else None, carrier_price=result["price"],
            customer_price_ht=stored["quote"]["price_ht"], agent_log=result["log"])
        DB_.audit("system", "booking_created", f"{code} status={result['status']}")
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

    LABELS = {"assigned": "Transporteur affecté", "loaded": "Chargement effectué", "in_transit": "En transit",
              "arrived": "Arrivée à destination", "delivered": "Livré — preuve de livraison enregistrée"}

    def tracking_events(self, b):
        """Jalons réels (transporteur / opérateur) ; la simulation n'existe que si FRETRAU_DEMO_TIMELINE=1 et sans événement réel."""
        if b["status"] != "confirmed":
            return [], "none"
        real = {e["kind"]: e for e in DB_.events_for(b["id"])}
        if not real and DEMO_TIMELINE:
            return booking.timeline(b["created_at"], time.time(), DEMO_SPEED), "simulation"
        out = [{"label": "Commande confirmée", "done": True}, {"label": self.LABELS["assigned"], "done": True}]
        for kind in DB.EVENT_ORDER[1:]:
            out.append({"label": self.LABELS[kind], "done": kind in real, **({"at": real[kind]["ts"]} if kind in real else {})})
        return out, "carrier"

    def record_event(self, b, kind, source, detail=""):
        status = DB_.add_event(b["id"], kind, source, detail)
        if status == "added":
            DB_.audit(source, "event_" + kind, b["tracking_code"])
            if kind == "delivered":
                due = (date.today() + timedelta(days=CARRIER_PAY_DAYS)).isoformat()
                if DB_.create_payable(b, time.time(), due):
                    DB_.audit("system", "payable_created", f"{b['tracking_code']} due {due}")
        return status

    def api_carrier_status(self):
        """Statut poussé par le transporteur / sa télématique (signé HMAC). Un transporteur ne peut mettre à jour que SES expéditions."""
        d = self.verify_signed()
        code, carrier_id, event = d.get("tracking_code"), d.get("carrier_id"), d.get("event")
        if (not isinstance(code, str) or not security.CODE_RE.match(code) or isinstance(carrier_id, bool)
                or not isinstance(carrier_id, int) or event not in DB.EVENT_ORDER[1:]):
            raise ApiError(422, "Données invalides.")
        b = DB_.booking_by_code(code)
        if not b or b["status"] != "confirmed" or b["carrier_id"] != carrier_id:
            DB_.audit("anonymous", "carrier_status_rejected", f"{code} carrier={carrier_id}")
            raise ApiError(404, "Expédition introuvable pour ce transporteur.")
        detail = security.clean_text(d.get("detail"), 200) if d.get("detail") else ""
        status = self.record_event(b, event, f"carrier:{carrier_id}", detail)
        self.send_json(200, {"result": status})

    def api_track(self, code):
        b = self._public_booking(code)
        shipment = json.loads(b["shipment"])
        events, source = self.tracking_events(b)
        self.send_json(200, {
            "driver_position": (lambda p: {"lat": p["lat"], "lon": p["lon"], "ts": p["ts"]} if p and time.time() - p["ts"] < 86400 else None)(DB_.last_position(b["id"])),
            "tracking_code": code, "status": b["status"], "origin": shipment["origin"],
            "destination": shipment["destination"], "events": events, "events_source": source,
            "message": None if b["status"] == "confirmed" else
            "Votre demande est en cours de traitement par notre équipe, vous serez contacté rapidement.",
        })

    def api_doc(self, code):
        b = self._public_booking(code)
        if b["status"] != "confirmed":
            raise ApiError(409, "Document disponible après confirmation du transport.")
        s, cu = json.loads(b["shipment"]), json.loads(b["customer"])
        e = lambda v: html.escape(str(v))                       # noqa: E731 — échappement XSS
        rows = [("Expéditeur", f"{cu['name']} — {cu['company']}"), ("Lieu d'enlèvement", s["pickup_address"]),
                ("Lieu de livraison", s["delivery_address"]), ("Marchandise", s["goods"]), ("Plage de température", TEMPERATURE_RANGES.get(s.get("temperature_range"), "—")),
                ("Palettes", s.get("pallets")), ("Poids (kg)", s["weight_kg"]),
                ("Date d'enlèvement", f"{s['pickup_date']} — créneau {s.get('pickup_window', '')}"),
                ("Livraison", f"créneau {s.get('delivery_window', '')}" + (f" — au plus tard le {s['deliver_by']}" if s.get('deliver_by') else "")),
                ("Contact sur site", f"{s.get('site_contact_name', '')} — {s.get('site_contact_phone', '')}"),
                ("Consignes", s.get("loading_notes") or "—"),
                ("Valeur déclarée (€)", s.get("goods_value_eur") or "non déclarée"),
                ("Transporteur", b["carrier_name"])]
        body = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
        page = (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Lettre de voiture {e(code)}</title>"
                f"<link rel='stylesheet' href='/styles.css'></head><body class='doc'><h1>Lettre de voiture</h1>"
                f"<p class='muted'>N° {e(code)} — document de démonstration, à remplacer par un modèle CMR "
                f"conforme avant tout usage réel.</p><table class='doc-table'>{body}</table></body></html>")
        self.send_bytes(200, "text/html; charset=utf-8", page.encode())

    def api_inbound_mail(self):
        """Réponse e-mail d'un transporteur (relayée par votre service de messagerie). Signature HMAC obligatoire."""
        d = self.verify_signed()
        code, carrier_id, text = d.get("tracking_code"), d.get("carrier_id"), d.get("text")
        if (not isinstance(code, str) or not security.CODE_RE.match(code) or isinstance(carrier_id, bool)
                or not isinstance(carrier_id, int) or not isinstance(text, str) or len(text) > 5000):
            raise ApiError(422, "Données invalides.")
        result = email_agent.handle(DB_, code, carrier_id, text)
        DB_.audit("email_agent", "inbound_" + result["decision"], f"{code} carrier={carrier_id}")
        if result["decision"] == "accepted":
            b = DB_.booking_by_code(code)
            cu, sh = json.loads(b["customer"]), json.loads(b["shipment"])
            try:
                subject, body = mailer.booking_confirmation(cu, code, sh, b["customer_price_ht"], PUBLIC_URL)
                mailer.queue(DB_, cu["email"], subject, body)
                mailer.flush(DB_)
            except Exception:
                pass
        self.send_json(200, result)

    def api_rfq_reply(self):
        """Réponse e-mail d'un transporteur à une demande de devis (relayée par votre messagerie, signature HMAC obligatoire)."""
        d = self.verify_signed()
        text, sender = d.get("text"), str(d.get("from_email", "")).strip().lower()
        if not isinstance(text, str) or len(text) > 5000 or not security.EMAIL_RE.match(sender):
            raise ApiError(422, "Données invalides.")
        ref, amount, stop = rfq.read_reply(text)
        if stop:
            DB_.optout_by_email(sender)
            DB_.audit("rfq_agent", "rfq_optout", "")
            return self.send_json(200, {"decision": "optout"})
        r = DB_.rfq_by_ref(ref) if ref else None
        if not r:
            return self.send_json(200, {"decision": "ignored", "reason": "Référence de demande inconnue."})
        siren = next((t["siren"] for t in DB_.rfq_targets(r["id"]) if (t["email"] or "").lower() == sender), None)
        if not siren:
            return self.send_json(200, {"decision": "ignored", "reason": "Expéditeur non sollicité pour cette demande."})
        DB_.add_rfq_reply(r["id"], siren, amount, text)
        DB_.audit("rfq_agent", "rfq_reply", f"{ref} siren={siren} amount={amount}")
        return self.send_json(200, {"decision": "recorded", "amount": amount})

    # ---------- admin ----------
    def api_admin(self, method, path):
        if method == "POST" and path == "/api/admin/login":
            ip = self.ip()
            if not RL_LOGIN.allow(ip) or GUARD.locked(ip):
                raise ApiError(429, "Trop de tentatives. Réessayez plus tard.")
            d = self.read_json()
            name = d.get("user") if isinstance(d.get("user"), str) else ""
            pw = d.get("password") if isinstance(d.get("password"), str) else ""
            if DB_.users_count() == 0:                          # mode démo (un seul compte « admin » via l'environnement)
                stored, totp_secret, known = ADMIN_HASH, TOTP_SECRET, name == "admin"
            else:
                u = DB_.get_user(name[:64])
                known = bool(u and u["active"])
                stored, totp_secret = (u["pw_hash"], u["totp_secret"]) if u else (ADMIN_HASH, None)
            ok = security.verify_password(pw, stored) and known   # toujours calculer le hachage (pas de fuite par le temps)
            if ok and totp_secret and not security.verify_totp(totp_secret, str(d.get("totp", ""))):
                ok = False
            if not ok:
                GUARD.fail(ip)
                DB_.audit("anonymous", "admin_login_failed", ip)
                raise ApiError(401, "Identifiants invalides.")
            GUARD.ok(ip)
            DB_.audit(name, "admin_login", ip)
            cookie = (f"fretrau_admin={SESSIONS.issue(name)}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600"
                      + ("; Secure" if HTTPS else ""))
            return self.send_json(200, {"ok": True}, {"Set-Cookie": cookie})
        who, role = self.require_admin()
        resource = path.split("/")[3] if path.count("/") >= 3 else ""
        if not self.allow(role, resource):
            DB_.audit(who, "forbidden", path[:100])
            raise ApiError(403, "Droits insuffisants pour cette action.")
        if method == "GET" and path == "/api/admin/me":
            return self.send_json(200, {"user": who, "role": role})
        if method == "GET" and path == "/api/admin/bookings":
            rows = DB_.list_bookings()
            for r in rows:
                s = json.loads(r.pop("shipment"))
                r["route"] = f"{s['origin']} → {s['destination']}"
            return self.send_json(200, {"bookings": rows})
        m = re.fullmatch(r"/api/admin/booking/(\d{1,9})", path)
        if method == "GET" and m:
            b = DB_.booking_by_id(int(m.group(1)))
            if not b:
                raise ApiError(404, "Introuvable.")
            for k in ("customer", "shipment", "agent_log"):
                b[k] = json.loads(b[k])
            DB_.audit(who, "view_booking", str(b["id"]))
            return self.send_json(200, b)
        m = re.fullmatch(r"/api/admin/invoice/(\d{1,9})", path)
        if method == "GET" and m:
            b = DB_.booking_by_id(int(m.group(1)))
            if not b or b["status"] != "confirmed":
                raise ApiError(404, "Facture indisponible (transport non confirmé).")
            inv = DB_.get_or_create_invoice(b["id"], invoicing.build(b))
            DB_.audit(who, "invoice", inv["number"])
            return self.send_json(200, inv)
        if method == "GET" and path == "/api/admin/outbox":
            return self.send_json(200, {"mails": DB_.list_outbox()})
        if method == "POST" and path == "/api/admin/gdpr/anonymize":
            code = str(self.read_json().get("tracking_code", ""))
            if not security.CODE_RE.match(code) or not DB_.anonymize_booking(code):
                raise ApiError(404, "Réservation introuvable.")
            DB_.audit(who, "gdpr_anonymize", code)
            return self.send_json(200, {"ok": True})
        if method == "POST" and path == "/api/admin/pod":
            code = str(self.read_json().get("tracking_code", ""))
            b = DB_.booking_by_code(code) if security.CODE_RE.match(code) else None
            if not b or b["status"] != "confirmed":
                raise ApiError(404, "Réservation confirmée introuvable.")
            # l'opérateur ne peut confirmer une livraison que si le transport est déjà parti : pas de saut direct vers « livré » depuis zéro
            seen = {e["kind"] for e in DB_.events_for(b["id"])}
            if not seen & {"loaded", "in_transit", "arrived"}:
                raise ApiError(409, "Aucun jalon de transport enregistré : impossible de confirmer la livraison.")
            return self.send_json(200, {"result": self.record_event(b, "delivered", f"operator:{who}", "preuve de livraison validée")})
        if method == "GET" and path == "/api/admin/payables":
            rows = DB_.list_payables()
            return self.send_json(200, {"payables": rows, "total_due_ht": round(sum(r["amount_ht"] for r in rows if r["status"] == "due"), 2)})
        if method == "POST" and path == "/api/admin/payables/pay":
            d = self.read_json()
            ref = security.clean_text(d.get("reference"), 80) if d.get("reference") else ""
            pid = d.get("id")
            if isinstance(pid, bool) or not isinstance(pid, int) or not ref:
                raise ApiError(422, "Identifiant et référence de virement requis.")
            if not DB_.mark_paid(pid, ref):
                raise ApiError(409, "Paiement introuvable ou déjà effectué.")
            DB_.audit(who, "payable_paid", f"{pid} {ref}")
            return self.send_json(200, {"ok": True})
        m = re.fullmatch(r"/api/admin/gdpr/export/([^/]+)", path)
        if method == "GET" and m:
            if not security.CODE_RE.match(m.group(1)):
                raise ApiError(404, "Réservation introuvable.")
            data = DB_.export_booking(m.group(1))
            if not data:
                raise ApiError(404, "Réservation introuvable.")
            DB_.audit(who, "gdpr_export", m.group(1))
            return self.send_json(200, data)
        if method == "GET" and path == "/api/admin/carriers":
            rows = DB_.list_applications()
            for r in rows:
                r["data"], r["checks"] = json.loads(r["data"]), json.loads(r["checks"])
            return self.send_json(200, {"applications": rows})
        if method == "POST" and path == "/api/admin/carriers/decision":
            d = self.read_json()
            status = d.get("status")
            aid = d.get("id")
            if status not in ("approved", "rejected", "more_info", "to_review") or isinstance(aid, bool) or not isinstance(aid, int):
                raise ApiError(422, "Décision invalide.")
            note = security.clean_text(d["note"], 300) if d.get("note") else ""
            if status == "approved" and not note:
                raise ApiError(422, "Pour approuver, indiquez dans la note ce que vous avez vérifié (SIREN, licence, assurance, VIES).")
            if not DB_.decide_application(aid, status, who, note):
                raise ApiError(404, "Candidature introuvable.")
            DB_.audit(who, "carrier_" + status, str(aid))
            return self.send_json(200, {"ok": True})
        if method == "GET" and path == "/api/admin/contacts":
            rows = DB_.list_contacts()
            for r in rows:
                r["data"] = json.loads(r["data"])
            return self.send_json(200, {"contacts": rows})
        if method == "POST" and path == "/api/admin/contacts/status":
            d = self.read_json()
            if d.get("status") not in ("new", "done") or isinstance(d.get("id"), bool) or not isinstance(d.get("id"), int) or not DB_.set_contact_status(d["id"], d["status"]):
                raise ApiError(422, "Requête invalide.")
            DB_.audit(who, "contact_" + d["status"], str(d["id"]))
            return self.send_json(200, {"ok": True})
        if method == "GET" and path == "/api/admin/claims":
            rows = DB_.list_claims()
            for r in rows:
                r["data"], r["deadlines"] = json.loads(r["data"]), json.loads(r["deadlines"])
                b = DB_.booking_by_id(r["booking_id"])
                r["tracking_code"] = b["tracking_code"] if b else ""
                try:
                    r["triage"] = claims_triage.triage({**r["data"], "kind": r.get("kind"), "amount_eur": r["data"].get("amount_eur")}, r["deadlines"])
                except Exception:
                    r["triage"] = None
            return self.send_json(200, {"claims": rows})
        if path == "/api/admin/watchtower":
            if method == "POST":
                res = watch_run.run(DB_, datetime.now(), PUBLIC_URL, SESSION_SECRET)
                DB_.audit(who, "watchtower_run", json.dumps(res))
                return self.send_json(200, res)
            return self.send_json(200, {"alerts": DB_.list_alerts()})
        if method == "GET" and path == "/api/admin/sms":
            return self.send_json(200, {"sms": DB_.list_sms(), "configured": bool(os.environ.get("FRETRAU_SMS_PROVIDER") or os.environ.get("FRETRAU_SMS_URL"))})
        if method == "POST" and path == "/api/admin/driver-link":
            d = self.read_json()
            b = DB_.booking_by_code(str(d.get("tracking_code", ""))) if security.CODE_RE.match(str(d.get("tracking_code", ""))) else None
            if not b or b["status"] != "confirmed":
                raise ApiError(404, "Envoi introuvable.")
            token = driver.new_link(DB_, b["id"])
            url = f"{PUBLIC_URL}/chauffeur.html#{token}"
            DB_.audit(who, "driver_link_created", b["tracking_code"])
            return self.send_json(200, {"url": url})
        if method == "POST" and path == "/api/admin/claims/status":
            d = self.read_json()
            note = security.clean_text(d["note"], 300) if d.get("note") else ""
            if d.get("status") not in ("received", "filed_with_carrier", "settled", "rejected") or isinstance(d.get("id"), bool) or not isinstance(d.get("id"), int) or not DB_.set_claim_status(d["id"], d["status"], note):
                raise ApiError(422, "Requête invalide.")
            DB_.audit(who, "claim_" + d["status"], str(d["id"]))
            return self.send_json(200, {"ok": True})
        if method == "GET" and path == "/api/admin/chaining":
            items = []
            for r in DB_.list_bookings(1000):
                if r["status"] != "confirmed":
                    continue
                sh = json.loads(r["shipment"])
                q = (DB_.get_quote(r["quote_id"], max_age_s=10 ** 9) or {}).get("quote", {})
                items.append({"code": r["tracking_code"], "origin": sh["origin"], "destination": sh["destination"], "mode": sh["mode"],
                              "pickup_date": sh["pickup_date"], "earliest_delivery": q.get("earliest_delivery", "")})
            return self.send_json(200, {"suggestions": chaining.suggestions(items)})
        if method == "GET" and path == "/api/admin/directory":
            q = parse_qs(urlparse(self.path).query)
            return self.send_json(200, {"carriers": DB_.list_directory((q.get("dept") or [None])[0])})
        if method == "POST" and path == "/api/admin/directory/contact":
            d = self.read_json()
            email = security.clean_text(d.get("email"), 254)
            phone = security.clean_text(d.get("phone"), 20) if d.get("phone") else ""
            if not security.EMAIL_RE.match(email) or (phone and not security.PHONE_RE.match(phone)) or not DB_.set_directory_contact(str(d.get("siren", ""))[:9], email, phone):
                raise ApiError(422, "Requête invalide.")
            DB_.audit(who, "directory_contact", str(d.get("siren")))
            return self.send_json(200, {"ok": True})
        if method == "POST" and path == "/api/admin/rfq/draft":
            d = self.read_json()
            stored = DB_.get_quote(str(d.get("quote_id", ""))[:40], max_age_s=None)
            if not stored:
                raise ApiError(404, "Devis introuvable.")
            qt, sh = stored["quote"], stored["shipment"]
            lane = {"origin": qt["origin"], "destination": qt["destination"], "pickup_date": sh["pickup_date"], "pallets": sh.get("pallets"),
                    "weight_kg": sh.get("weight_kg"), "mode": qt["mode"], "options": sh.get("options") or {}}
            try:
                _, lat, lon = geo.coords(qt["origin"])
            except KeyError:
                raise ApiError(422, "Lieu de départ inconnu.")
            radius = d.get("radius_km") if isinstance(d.get("radius_km"), (int, float)) and not isinstance(d.get("radius_km"), bool) and 10 <= d["radius_km"] <= 500 else rfq.DEFAULT_RADIUS_KM
            targets, skipped = rfq.select(DB_.list_directory(limit=100000), lat, lon, time.time(), radius)
            ref = rfq.new_ref()
            rid = DB_.create_rfq(ref, d["quote_id"], json.dumps(lane), qt.get("carrier_cost_estimate"), [t["siren"] for t in targets])
            subject, body = rfq.draft(ref, lane, OPS_EMAIL or "contact")
            DB_.audit(who, "rfq_draft", f"{ref} targets={len(targets)}")
            return self.send_json(200, {"id": rid, "ref": ref, "subject": subject, "body": body, "targets": [{"siren": t["siren"], "name": t["name"], "city": t["city"], "distance_km": t["distance_km"]} for t in targets], "skipped": skipped[:50]})
        if method == "POST" and path == "/api/admin/rfq/send":
            d = self.read_json()
            r = DB_.rfq_by_id(d["id"]) if isinstance(d.get("id"), int) and not isinstance(d.get("id"), bool) else None
            if not r or r["status"] != "draft":
                raise ApiError(404, "Demande introuvable ou déjà envoyée.")
            lane = json.loads(r["lane"])
            subject, body = rfq.draft(r["ref"], lane, OPS_EMAIL or "contact")
            sent = 0
            for t in DB_.rfq_targets(r["id"]):
                c = DB_.directory_one(t["siren"])
                if c and c["email"] and not c["optout"]:           # re-contrôle au moment de l'envoi
                    mailer.queue(DB_, c["email"], subject, body)
                    DB_.mark_rfq_sent(r["id"], t["siren"])
                    sent += 1
            try:
                mailer.flush(DB_)
            except Exception:
                pass
            DB_.audit(who, "rfq_send", f"{r['ref']} sent={sent}")
            return self.send_json(200, {"sent": sent})
        if method == "GET" and path == "/api/admin/rfq":
            out = []
            for r in DB_.list_rfqs():
                reps = DB_.rfq_replies(r["id"])
                priced = [x for x in reps if x["amount"] is not None]
                out.append({"id": r["id"], "ref": r["ref"], "status": r["status"], "lane": json.loads(r["lane"]), "estimate_eur": r["estimate_eur"],
                            "targets": len(DB_.rfq_targets(r["id"])), "replies": [{"name": x["name"], "amount": x["amount"]} for x in reps],
                            "best": min((x["amount"] for x in priced), default=None)})
            ratios = DB_.rfq_price_ratios()
            cal = {"n": len(ratios), "median_ratio": round(statistics.median(ratios), 3) if ratios else None,
                   "reliable": len(ratios) >= 20,
                   "note": "Rapport prix réels / estimation. Moins de 20 réponses chiffrées : indicatif seulement, ne recalez pas le barème."}
            return self.send_json(200, {"rfqs": out, "calibration": cal})
        if method == "GET" and path == "/api/admin/stats":
            rows = DB_.list_bookings(10000)
            done = [r for r in rows if r["status"] == "confirmed"]
            revenue = sum(r["customer_price_ht"] for r in done)
            cost = sum(r["carrier_price"] or 0 for r in done)
            return self.send_json(200, {
                "bookings": len(rows), "confirmed": len(done), "places": places.count() + len(geo.CITIES), "places_complete": places.available(),
                "pending_human": len(rows) - len(done),
                "revenue_ht": round(revenue, 2), "margin_ht": round(revenue - cost, 2),
                "audit": DB_.audit_tail(20), "audit_intact": DB_.verify_audit_chain()[0]})
        raise ApiError(404, "Introuvable.")


def make_server(host="127.0.0.1", port=8080):
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    print(f"[FRETRAU] http://{host}:{port}  (admin : /admin.html)  LLM: {'actif' if llm.available() else 'gabarits'}")
    make_server(host, port).serve_forever()
