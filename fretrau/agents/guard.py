"""Agent de garde (fraude et incohérences) : note chaque réservation avant l'affectation d'un transporteur.

Il ne bloque jamais seul un client de bonne foi : au-dessus du seuil, la réservation passe en REVUE HUMAINE (aucun transport
engagé automatiquement) avec la liste exacte des signaux. Les règles sont volontairement simples, explicables et auditables.
"""
import re

DISPOSABLE = {"mailinator.com", "yopmail.com", "yopmail.fr", "guerrillamail.com", "tempmail.com", "10minutemail.com", "trashmail.com",
              "sharklasers.com", "getnada.com", "temp-mail.org", "maildrop.cc"}
FREE_MAIL = {"gmail.com", "hotmail.com", "hotmail.fr", "outlook.com", "outlook.fr", "yahoo.com", "yahoo.fr", "live.fr", "free.fr",
             "orange.fr", "wanadoo.fr", "icloud.com", "laposte.net", "sfr.fr"}
REVIEW_THRESHOLD = 40
HIGH_VALUE_EUR = 5000
MAX_PER_EMAIL_24H = 3
MAX_PER_IP_24H = 6


def assess(customer: dict, shipment: dict, price_ht: float, recent: list, now_ts: float) -> dict:
    flags, score = [], 0

    def add(points, text):
        nonlocal score
        score += points
        flags.append(text)

    email = (customer.get("email") or "").lower()
    domain = email.rsplit("@", 1)[-1]
    if domain in DISPOSABLE:
        add(60, "Adresse e-mail jetable")
    digits = re.sub(r"\D", "", customer.get("phone") or "")
    if len(set(digits)) <= 2 or len(digits) < 9:
        add(25, "Numéro de téléphone peu plausible")
    sc = re.sub(r"\D", "", shipment.get("site_contact_phone") or "")
    if sc and len(set(sc)) <= 2:
        add(10, "Téléphone du contact sur site peu plausible")
    if domain in FREE_MAIL and price_ht >= HIGH_VALUE_EUR:
        add(30, f"Transport de {price_ht:.0f} € HT réservé avec une adresse e-mail grand public : vérifier la société (SIREN)")
    if (shipment.get("pickup_address") or "").strip().lower() == (shipment.get("delivery_address") or "").strip().lower():
        add(40, "Adresses d'enlèvement et de livraison identiques")
    for key in ("pickup_address", "delivery_address"):
        a = shipment.get(key) or ""
        if len(a) < 8 or not re.search(r"\d", a):
            add(10, f"Adresse peu précise ({'enlèvement' if key == 'pickup_address' else 'livraison'})")
    day = now_ts - 86400
    same_email = sum(1 for r in recent if r["email"] == email and r["created_at"] >= day)
    if same_email >= MAX_PER_EMAIL_24H:
        add(30, f"{same_email} réservations en 24 h avec la même adresse e-mail")
    ip = (customer.get("consent") or {}).get("ip_hash")
    if ip and sum(1 for r in recent if r["ip_hash"] == ip and r["created_at"] >= day) >= MAX_PER_IP_24H:
        add(30, "Nombre inhabituel de réservations depuis la même connexion en 24 h")
    return {"score": min(100, score), "flags": flags, "action": "review" if score >= REVIEW_THRESHOLD else "ok"}
