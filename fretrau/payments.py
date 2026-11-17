"""Paiement par carte (THÉORIQUE tant qu'aucun prestataire n'est configuré) : adaptateur Stripe Checkout + vérification des webhooks.

Fonctionnement prévu :
  1. le client réserve ; POST /api/pay/checkout crée une session de paiement pour le TTC du devis (montant relu en base, jamais envoyé par le navigateur) ;
  2. il paie chez le prestataire (FRETRAU ne voit jamais de numéro de carte : hors périmètre PCI-DSS lourd) ;
  3. le prestataire appelle /api/webhook/stripe ; la signature est vérifiée (HMAC-SHA256, tolérance 5 min) puis le paiement passe à « paid ».
Sans FRETRAU_STRIPE_KEY, le mode reste « facture » (paiement après transport). NON TESTÉ contre le vrai service : à valider en mode test Stripe.
La signature suit le schéma documenté par Stripe (en-tête « Stripe-Signature: t=…,v1=… », message « t.corps »).
"""
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request

API = "https://api.stripe.com/v1/checkout/sessions"
TOLERANCE_S = 300


def enabled() -> bool:
    return bool(os.environ.get("FRETRAU_STRIPE_KEY"))


def cents(amount_eur: float) -> int:
    return int(round(amount_eur * 100))


def create_checkout(quote_id: str, amount_ttc_eur: float, description: str, email: str, success_url: str, cancel_url: str,
                    opener=urllib.request.urlopen) -> dict:
    form = {
        "mode": "payment", "client_reference_id": quote_id, "customer_email": email, "success_url": success_url, "cancel_url": cancel_url,
        "line_items[0][quantity]": "1", "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(cents(amount_ttc_eur)),
        "line_items[0][price_data][product_data][name]": description[:120], "metadata[quote_id]": quote_id,
    }
    req = urllib.request.Request(API, method="POST", data=urllib.parse.urlencode(form).encode(),
                                 headers={"Authorization": "Bearer " + os.environ["FRETRAU_STRIPE_KEY"]})
    with opener(req, timeout=20) as r:
        data = json.loads(r.read())
    return {"provider_ref": data["id"], "url": data["url"]}


def sign(payload: bytes, secret: str, ts: int = None) -> str:
    ts = int(ts or time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify_webhook(payload: bytes, header: str, secret: str, now: float = None) -> dict:
    """Retourne l'événement décodé ou lève ValueError (signature absente, fausse, trop ancienne)."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        sigs = [v for k, v in (p.split("=", 1) for p in header.split(",")) if k == "v1"]
    except Exception:
        raise ValueError("En-tête de signature invalide.")
    if abs((now or time.time()) - ts) > TOLERANCE_S:
        raise ValueError("Signature trop ancienne (anti-rejeu).")
    good = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(good, s) for s in sigs):
        raise ValueError("Signature invalide.")
    return json.loads(payload)
