"""Offres de chargement aux transporteurs réels et décision sur leurs réponses.

Une réponse (e-mail ou portail) se résume à UN montant validé par du code. La décision est déterministe :
  montant <= plafond d'achat (marge minimale garantie)  -> transport attribué ;
  montant <= plafond + 10 %                             -> contre-proposition au plafond ;
  au-delà, ou montant illisible                         -> un humain reprend le dossier.
Le premier transporteur conforme qui accepte obtient le transport ; les autres offres sont closes.
"""
import json
from datetime import date

from . import geo, mailer, market, pricing, registry
from .agents import compliance

COUNTER_TOLERANCE = 1.10
OPENING_DISCOUNT = 0.94          # première offre : 94 % du coût estimé, sans jamais dépasser le plafond
OPEN_STATUSES = ("pending_human", "sourcing")


def ceiling(customer_price_ht: float) -> float:
    return round(customer_price_ht / (1 + pricing.MIN_MARGIN), 2)


def opening_price(quote) -> float:
    return round(min(quote.carrier_cost_estimate * OPENING_DISCOUNT, ceiling(quote.price_ht)), 2)


def public_load(booking: dict) -> dict:
    """Ce qu'un transporteur a le droit de voir : jamais le client ni le prix de vente."""
    s = json.loads(booking["shipment"])
    return {"code": booking["tracking_code"], "origin": geo.label(s["origin"]), "destination": geo.label(s["destination"]),
            "mode": s["mode"], "pallets": s.get("pallets"), "weight_kg": s.get("weight_kg"),
            "pickup_date": s["pickup_date"], "options": [k for k, v in (s.get("options") or {}).items() if v],
            "goods": s.get("goods", "")}


def send(db, booking: dict, quote, carriers: list, base_url: str) -> list:
    """Crée une offre par transporteur et la lui envoie par e-mail. Retourne les noms contactés."""
    price = opening_price(quote)
    load = public_load(booking)
    sent = []
    for c in carriers:
        db.add_offer(booking["id"], c.id, price)
        sent.append(c.name)
        if c.email:
            try:
                mailer.queue(db, c.email, f"FRETRAU — chargement proposé ({load['code']})",
                             f"Bonjour,\n\nChargement {load['origin']} -> {load['destination']} le {load['pickup_date']} "
                             f"({pricing.MODES.get(load['mode'], load['mode'])}, {load['weight_kg']} kg).\n"
                             f"Prix proposé : {price:.2f} € HT.\n\nRépondez depuis votre espace : {base_url}/transporteur.html\n"
                             f"ou par retour d'e-mail en indiquant votre prix en euros.\n\nL'équipe FRETRAU")
            except ValueError:
                pass
    return sent


def decide(db, code: str, carrier_id: int, amount, raw: str = "", channel: str = "email") -> dict:
    b = db.booking_by_code(code)
    if not b:
        return {"decision": "rejected", "reason": "Réservation inconnue."}
    if b["status"] not in OPEN_STATUSES:
        return {"decision": "rejected", "reason": "Réservation non éligible (déjà traitée)."}
    carrier = registry.get(db, carrier_id)
    if not carrier:
        return {"decision": "rejected", "reason": "Transporteur inconnu."}
    shipment = json.loads(b["shipment"])
    ok, reasons = compliance.check(carrier, shipment["mode"], shipment["origin"], shipment["destination"],
                                   date.fromisoformat(shipment["pickup_date"]))
    if not ok:
        db.add_inbound(b["id"], carrier_id, raw, None, "rejected_compliance")
        return {"decision": "rejected", "reason": "Non conforme : " + " ; ".join(reasons)}

    top = ceiling(b["customer_price_ht"])
    if amount is None:
        db.add_inbound(b["id"], carrier_id, raw, None, "escalate_no_amount")
        return {"decision": "escalate", "reason": "Montant absent, ambigu ou hors plage : traitement humain."}
    if amount <= top:
        log = json.loads(b["agent_log"])
        log.setdefault("inbound", []).append({"carrier": carrier.name, "amount": amount, "ceiling": top, "channel": channel})
        if not db.assign_carrier(code, carrier.id, carrier.name, amount, log):
            return {"decision": "rejected", "reason": "Réservation non éligible (déjà traitée)."}
        db.add_inbound(b["id"], carrier_id, raw, amount, "accepted")
        db.set_offer(b["id"], carrier.id, "accepted", amount)
        db.close_other_offers(b["id"], carrier.id)
        if not carrier.simulated:
            db.add_milestone(b["id"], "confirmed", "system")
            db.add_milestone(b["id"], "assigned", "system", carrier.name)
            estimate = (log.get("estimate") or 0)
            market.record(db, shipment["origin"], shipment["destination"], estimate, amount)
        return {"decision": "accepted", "price": amount, "ceiling": top}
    if amount <= top * COUNTER_TOLERANCE:
        db.add_inbound(b["id"], carrier_id, raw, amount, "counter")
        db.set_offer(b["id"], carrier.id, "countered", top)
        return {"decision": "counter", "amount": amount, "counter_price": top}
    db.add_inbound(b["id"], carrier_id, raw, amount, "escalate_too_high")
    if b["status"] == "sourcing" and all(o["carrier_id"] == carrier.id or o["status"] != "sent"
                                         for o in db.offers_for_booking(b["id"])):
        db.set_booking_status(code, "pending_human")          # plus aucune offre en attente : un humain reprend
    return {"decision": "escalate", "reason": "Prix trop élevé pour la marge minimale.", "amount": amount}
