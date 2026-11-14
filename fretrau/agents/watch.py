"""Agent de surveillance : relance la recherche de transporteur et signale les retards avant le client.

À chaque passage (toutes les quelques minutes) :
  1. réservation en recherche depuis trop longtemps -> nouvelle vague d'offres aux transporteurs suivants du
     classement ; après MAX_WAVES vagues sans accord, un humain reprend le dossier ;
  2. enlèvement prévu dépassé sans chargement déclaré -> rappel au transporteur + alerte ;
  3. livraison attendue dépassée sans livraison déclarée -> alerte + message au client ;
  4. assurance d'un transporteur vérifié arrivant à échéance sous 30 jours -> rappel + alerte.
Chaque alerte n'est créée qu'une fois. L'agent ne modifie jamais un prix et n'attribue jamais un transport.
"""
import json
import os
import time
from datetime import date, timedelta

from .. import booking, mailer, offers, registry
from . import sourcing

WAVE_SIZE = 3
MAX_WAVES = 3


def offer_wait_s() -> float:
    try:
        return float(os.environ.get("FRETRAU_OFFER_WAIT_MINUTES", "120")) * 60
    except ValueError:
        return 7200.0


def _mail(db, to, subject, body):
    try:
        if to:
            mailer.queue(db, to, subject, body)
    except ValueError:
        pass


def _resource(db, b, base_url, now):
    """Vague suivante d'offres pour une réservation restée sans accord."""
    existing = db.offers_for_booking(b["id"])
    last = max((o["created_at"] for o in existing), default=b["created_at"])
    if now - last < offer_wait_s():
        return None
    stored = db.get_quote(b["quote_id"], max_age_s=90 * 86400)
    waves = -(-len(existing) // WAVE_SIZE)
    if not stored or waves >= MAX_WAVES:
        db.set_booking_status(b["tracking_code"], "pending_human")
        db.add_alert("no_carrier", b["tracking_code"], "Aucun transporteur n'a accepté : dossier à reprendre.")
        return "escalated"
    quote = booking.quote_from_payload(stored["quote"])
    shipment = json.loads(b["shipment"])
    ranked, _ = sourcing.rank(quote, date.fromisoformat(shipment["pickup_date"]), carriers=registry.pool(db), top_n=50)
    asked = {o["carrier_id"] for o in existing}
    by_id = {c.id: c for c in registry.pool(db)}
    nxt = [by_id[r["carrier_id"]] for r in ranked if r["carrier_id"] not in asked and not by_id[r["carrier_id"]].simulated]
    if not nxt:
        db.set_booking_status(b["tracking_code"], "pending_human")
        db.add_alert("no_carrier", b["tracking_code"], "Plus aucun transporteur vérifié à solliciter.")
        return "escalated"
    offers.send(db, b, quote, nxt[:WAVE_SIZE], base_url)
    return "wave"


def run(db, base_url: str, now: float = None, today: date = None) -> dict:
    now = now or time.time()
    today = today or date.today()
    out = {"waves": 0, "escalated": 0, "alerts": 0}
    for b in db.bookings_by_status(("sourcing",)):
        r = _resource(db, b, base_url, now)
        if r == "wave":
            out["waves"] += 1
        elif r == "escalated":
            out["escalated"] += 1

    for b in db.bookings_by_status(("confirmed",)):
        carrier = registry.get(db, b["carrier_id"])
        if not carrier or carrier.simulated:
            continue                                   # les sociétés fictives ont un suivi simulé
        steps = {m["step"] for m in db.milestones(b["id"])}
        s, code = json.loads(b["shipment"]), b["tracking_code"]
        pickup = date.fromisoformat(s["pickup_date"])
        stored = db.get_quote(b["quote_id"], max_age_s=365 * 86400)
        transit = stored["quote"]["transit_days"] if stored else 2
        if "loaded" not in steps and today > pickup:
            if db.add_alert("late_pickup", code, f"Enlèvement prévu le {pickup.isoformat()} non déclaré par {carrier.name}."):
                out["alerts"] += 1
                _mail(db, carrier.email, f"FRETRAU — chargement à confirmer ({code})",
                      f"Bonjour,\n\nLe chargement {code} était prévu le {pickup.strftime('%d/%m/%Y')} et n'est pas "
                      f"déclaré. Merci de le confirmer dans votre espace : {base_url}/transporteur.html\n\nL'équipe FRETRAU")
        if "delivered" not in steps and today > pickup + timedelta(days=transit):
            if db.add_alert("late_delivery", code, f"Livraison attendue dépassée, transporteur {carrier.name}."):
                out["alerts"] += 1
                _mail(db, json.loads(b["customer"]).get("email"), f"FRETRAU — point sur votre envoi {code}",
                      f"Bonjour,\n\nVotre envoi {code} n'est pas encore déclaré livré. Nous contactons le transporteur "
                      f"et revenons vers vous.\nSuivi : {base_url}/suivi?code={code}\n\nL'équipe FRETRAU")

    for r in db.list_carriers(status="verified", limit=5000):
        try:
            until = date.fromisoformat(r["insurance_until"] or "")
        except ValueError:
            continue
        if until <= today + timedelta(days=30):
            if db.add_alert("insurance", f"{r['id']}:{until.isoformat()}", f"Assurance de {r['name']} à échéance le {until.isoformat()}."):
                out["alerts"] += 1
                _mail(db, r["email"], "FRETRAU — attestation d'assurance à renouveler",
                      f"Bonjour,\n\nVotre attestation d'assurance arrive à échéance le {until.strftime('%d/%m/%Y')}. "
                      "Sans nouvelle attestation, nous ne pourrons plus vous proposer de chargements.\n\nL'équipe FRETRAU")
    return out
