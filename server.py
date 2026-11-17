#!/usr/bin/env python3
"""Serveur FRETRAU (bibliothèque standard uniquement, aucune dépendance).

Lancement :  FRETRAU_ADMIN_PASSWORD='un-mot-de-passe-long' python3 server.py
Variables :  PORT, HOST, FRETRAU_DB, FRETRAU_SECRET, FRETRAU_HTTPS=1, FRETRAU_TRUST_PROXY=1,
             FRETRAU_DEMO_SPEED (1 = temps réel, 360 = 1 h simulée en 10 s), ANTHROPIC_API_KEY (optionnel)
"""
import hashlib
import html
import json
import os
import re
import secrets
import time
from dataclasses import asdict
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from fretrau import booking, geo, invoicing, mailer, places, pricing, security
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

DB_ = DB(os.environ.get("FRETRAU_DB", os.path.join(ROOT, "fretrau.db")))
RL_GLOBAL = security.RateLimiter(120, 60)
RL_QUOTE = security.RateLimiter(20, 60)
RL_BOOK = security.RateLimiter(5, 600)
RL_LOGIN = security.RateLimiter(10, 900)
RL_TRACK = security.RateLimiter(30, 60)
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
        "ops": ("bookings", "booking", "outbox", "stats", "me", "pod"),
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
            raise ApiError(404, "Introuvable.")
        with open(full, "rb") as f:
            self.send_bytes(200, MIME[ext], f.read())

    # ---------- API ----------
    def api(self, method, path):
        if method == "GET" and path == "/api/cities":
            return self.send_json(200, {"cities": sorted(geo.CITIES), "options": pricing.OPTIONS, "llm": llm.available(),
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
        if path.startswith("/api/admin/"):
            return self.api_admin(method, path)
        raise ApiError(404, "Introuvable.")

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
        DB_.save_quote(quote_id, {"quote": asdict(q), "shipment": shipment})
        self.send_json(200, self.quote_view(quote_id, asdict(q)))

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
        result = booking.run(stored["quote"], date.fromisoformat(shipment["pickup_date"]),
                             date.fromisoformat(shipment["deliver_by"]) if shipment.get("deliver_by") else None,
                             shipment.get("goods_value_eur"))
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
                ("Lieu de livraison", s["delivery_address"]), ("Marchandise", s["goods"]),
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
