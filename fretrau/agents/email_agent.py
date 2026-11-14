"""Agent e-mail : traite la réponse d'un transporteur pour une réservation en attente d'attribution.

Sécurité (anti-injection de prompt) : le texte reçu n'est jamais exécuté ni confié à un LLM qui déciderait.
  - s'il contient UN montant en euros lisible, c'est une proposition chiffrée : offers.decide tranche
    (plafond d'achat garantissant la marge minimale, contrôle de conformité du transporteur) ;
  - sinon, reply.classify dit seulement « accepte notre prix », « refuse » ou « à lire par un humain ».
"""
from .. import offers, security
from . import reply

COUNTER_TOLERANCE = offers.COUNTER_TOLERANCE


def handle(db, code: str, carrier_id: int, text: str) -> dict:
    amount = security.parse_amount(text)
    if amount is None:
        b = db.booking_by_code(code)
        offer = db.offer(b["id"], carrier_id) if b else None
        if offer and offer["status"] in ("sent", "countered") and b["status"] in offers.OPEN_STATUSES:
            intent = reply.classify(text)
            if intent == "accept":
                amount = offer["price"]                      # notre prix, jamais un prix venu du texte
            elif intent == "decline":
                db.set_offer(b["id"], carrier_id, "declined")
                db.add_inbound(b["id"], carrier_id, text, None, "declined")
                return {"decision": "declined"}
    return offers.decide(db, code, carrier_id, amount, raw=text, channel="email")
