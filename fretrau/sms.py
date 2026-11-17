"""Notifications SMS (THÉORIQUE tant qu'aucun opérateur n'est branché) : consentement, désinscription STOP, gabarits, file d'envoi.

- Aucun SMS ne part sans consentement enregistré (case cochée à la réservation) ni vers un numéro désinscrit (STOP).
- Sans configuration d'opérateur, les messages restent « queued » dans sms_outbox (visibles dans l'administration).
- Opérateurs prévus : Twilio (FRETRAU_SMS_PROVIDER=twilio + SID/TOKEN/FROM) ou toute passerelle JSON (FRETRAU_SMS_URL + FRETRAU_SMS_TOKEN).
  NON TESTÉ contre un vrai opérateur : à valider avec un compte d'essai avant usage.
"""
import base64
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request

TEMPLATES = {
    "pickup_confirmed": "FRETRAU : votre envoi {code} a ete charge. Suivi : {url} . STOP pour ne plus recevoir de SMS.",
    "late": "FRETRAU : votre envoi {code} a du retard. Nous gerons la situation et vous tenons informe. {url} . STOP = arret.",
    "delivered": "FRETRAU : votre envoi {code} est livre. Merci ! {url} . STOP = arret.",
    "invoice_ready": "FRETRAU : la facture de l'envoi {code} est disponible. {url} . STOP = arret.",
    "driver_link": "FRETRAU : partagez votre position pour la livraison {code} : {url}",
}


def normalize_phone(raw: str, default_cc="+33"):
    p = re.sub(r"[\s.\-()]", "", raw or "")
    if p.startswith("00"):
        p = "+" + p[2:]
    elif p.startswith("0") and len(p) == 10 and default_cc == "+33":
        p = "+33" + p[1:]
    return p if re.fullmatch(r"\+\d{8,15}", p) else None


def phone_hash(phone: str, secret: str) -> str:
    return hashlib.sha256((secret + "|" + phone).encode()).hexdigest()[:40]


def render(template: str, **kw) -> str:
    return TEMPLATES[template].format(**kw)


def queue(db, phone: str, template: str, secret: str, consented: bool = True, **kw):
    """Retourne l'identifiant du message en file, ou None si refusé (pas de consentement, numéro invalide, STOP)."""
    n = normalize_phone(phone)
    if not n or not consented or db.is_sms_optout(phone_hash(n, secret)):
        return None
    return db.queue_sms(n, render(template, **kw))


def stop(db, phone: str, secret: str) -> bool:
    n = normalize_phone(phone)
    if not n:
        return False
    db.add_sms_optout(phone_hash(n, secret))
    return True


def is_stop_text(text: str) -> bool:
    return bool(re.fullmatch(r"\s*(stop|arret|arrêt|stoppez)\s*[.!]?\s*", text or "", flags=re.I))


def flush(db, opener=urllib.request.urlopen) -> int:
    """Envoie les SMS en file. Retourne le nombre d'envois réussis (0 si aucun opérateur configuré)."""
    provider = os.environ.get("FRETRAU_SMS_PROVIDER", "")
    url = os.environ.get("FRETRAU_SMS_URL", "")
    if not provider and not url:
        return 0
    sent = 0
    for m in db.queued_sms():
        try:
            if provider == "twilio":
                sid, tok, frm = os.environ["FRETRAU_TWILIO_SID"], os.environ["FRETRAU_TWILIO_TOKEN"], os.environ["FRETRAU_TWILIO_FROM"]
                req = urllib.request.Request(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", method="POST",
                    data=urllib.parse.urlencode({"To": m["to_phone"], "From": frm, "Body": m["body"]}).encode(),
                    headers={"Authorization": "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode()})
            else:
                req = urllib.request.Request(url, method="POST", data=json.dumps({"to": m["to_phone"], "body": m["body"]}).encode(),
                                             headers={"Content-Type": "application/json",
                                                      "Authorization": "Bearer " + os.environ.get("FRETRAU_SMS_TOKEN", "")})
            with opener(req, timeout=15) as r:
                ok = 200 <= r.status < 300
            db.mark_sms(m["id"], "sent" if ok else "failed", None if ok else f"HTTP {r.status}")
            sent += ok
        except Exception as e:                                  # un échec ne bloque jamais le reste
            db.mark_sms(m["id"], "failed", str(e)[:120])
    return sent
