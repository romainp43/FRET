"""Agent de négociation par e-mail : traite la réponse d'un transporteur pour une réservation « à traiter ».

Sécurité (anti-injection de prompt) : le texte reçu n'est jamais exécuté ni confié à un LLM qui déciderait.
On en extrait UN montant en euros (security.parse_amount), validé par du code, puis on compare au plafond
d'achat qui garantit la marge minimale. Le transporteur est re-contrôlé par l'agent de conformité.
"""
import json
from datetime import date

from .. import pricing, security, tariff
from ..carriers import CARRIERS
from . import compliance

COUNTER_TOLERANCE = 1.10      # jusqu'à +10 % au-dessus du plafond : contre-proposition au plafond


def handle(db, code: str, carrier_id: int, text: str) -> dict:
    b = db.booking_by_code(code)
    if not b:
        return {"decision": "rejected", "reason": "Réservation inconnue."}
    if b["status"] != "pending_human":
        return {"decision": "rejected", "reason": "Réservation non éligible (déjà traitée)."}

    carrier = {c.id: c for c in CARRIERS}.get(carrier_id)
    if not carrier:
        return {"decision": "rejected", "reason": "Transporteur inconnu."}
    shipment = json.loads(b["shipment"])
    ok, reasons = compliance.check(carrier, shipment["mode"], shipment["origin"], shipment["destination"],
                                   date.fromisoformat(shipment["pickup_date"]), shipment.get("options"))
    if not ok:
        db.add_inbound(b["id"], carrier_id, text, None, "rejected_compliance")
        return {"decision": "rejected", "reason": "Non conforme : " + " ; ".join(reasons)}

    ceiling = round(b["customer_price_ht"] / (1 + pricing.MIN_MARGIN), 2)
    amount = security.parse_amount(text)
    stored = db.get_quote(b["quote_id"], max_age_s=None)
    if amount is not None and stored:
        # Anti-fraude / erreur : un prix très inférieur au coût estimé est suspect (usurpation de transporteur,
        # prestation incomplète, erreur de saisie). On n'accepte jamais seul : traitement humain.
        floor = stored["quote"]["carrier_cost_estimate"] * tariff.load()["guards"]["anomaly_low_ratio"]
        if amount < floor:
            db.add_inbound(b["id"], carrier_id, text, amount, "escalate_anomaly_low")
            return {"decision": "escalate", "amount": amount,
                    "reason": "Prix anormalement bas par rapport au marché : vérification humaine (risque d'erreur ou de fraude)."}
    if amount is None:
        db.add_inbound(b["id"], carrier_id, text, None, "escalate_no_amount")
        return {"decision": "escalate", "reason": "Montant absent, ambigu ou hors plage : traitement humain."}
    if amount <= ceiling:
        log = json.loads(b["agent_log"])
        log.setdefault("inbound", []).append({"carrier": carrier.name, "amount": amount, "ceiling": ceiling})
        db.assign_carrier(code, carrier.id, carrier.name, amount, log)
        db.add_inbound(b["id"], carrier_id, text, amount, "accepted")
        return {"decision": "accepted", "price": amount, "ceiling": ceiling}
    if amount <= ceiling * COUNTER_TOLERANCE:
        db.add_inbound(b["id"], carrier_id, text, amount, "counter")
        return {"decision": "counter", "amount": amount, "counter_price": ceiling}
    db.add_inbound(b["id"], carrier_id, text, amount, "escalate_too_high")
    return {"decision": "escalate", "reason": "Prix trop élevé pour la marge minimale.", "amount": amount}
