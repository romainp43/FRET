"""Orchestrateur de réservation : conformité → comparaison → négociation → affectation."""
import secrets
from datetime import date

from . import pricing, registry
from .agents import sourcing, negotiation

MAX_CARRIERS_TRIED = 3
# Jalons de suivi (heures après la réservation) — démonstration ; en production : API télématique.
STEPS = [("confirmed", "Commande confirmée"), ("assigned", "Transporteur affecté"), ("loaded", "Chargement effectué"),
         ("transit", "En transit"), ("delivered", "Livré — preuve de livraison enregistrée")]
CARRIER_STEPS = ("loaded", "transit", "delivered")      # jalons déclarés par le transporteur, dans cet ordre
TIMELINE = [
    (0, "Commande confirmée"),
    (2, "Transporteur affecté"),
    (8, "Chargement effectué"),
    (14, "En transit"),
    (30, "Arrivée à destination"),
    (32, "Livré — preuve de livraison disponible"),
]


def quote_from_payload(p) -> pricing.Quote:
    return pricing.Quote(**p)


def run(quote_payload: dict, pickup: date, db=None) -> dict:
    """Retourne le statut, le transporteur retenu et la liste `to_offer` des transporteurs réels à solliciter.

    Les transporteurs simulés répondent tout de suite (démonstration). Les transporteurs réels reçoivent une
    offre et répondent plus tard : la réservation reste alors en « sourcing » (voir offers.py).
    """
    quote = quote_from_payload(quote_payload)
    pool = registry.pool(db)
    ranked, rejected = sourcing.rank(quote, pickup, carriers=pool)
    log = {"rejected_by_compliance": rejected, "ranking": ranked, "negotiations": [],
           "estimate": quote.carrier_cost_estimate}
    by_id = {c.id: c for c in pool}
    to_offer = []

    for cand in ranked[:MAX_CARRIERS_TRIED]:
        carrier = by_id[cand["carrier_id"]]
        if not carrier.simulated:
            to_offer.append(carrier)
            continue
        result = negotiation.negotiate(quote, cand, carrier)
        log["negotiations"].append({"carrier": carrier.name, **result})
        if result["accepted"]:
            return {"status": "confirmed", "carrier": carrier, "price": result["price"], "log": log, "to_offer": []}
    status = "sourcing" if to_offer else "pending_human"
    return {"status": status, "carrier": None, "price": None, "log": log, "to_offer": to_offer}


def new_tracking_code() -> str:
    # 12 caractères aléatoires non devinables (évite l'énumération des expéditions).
    return "FR-" + secrets.token_hex(6).upper()


def timeline(created_at: float, now: float, speed: float = 1.0) -> list:
    """Événements déjà survenus. speed > 1 accélère la démo (ex. 360 : 1 h = 10 s)."""
    elapsed_h = (now - created_at) / 3600.0 * speed
    return [{"label": label, "offset_h": h, "done": elapsed_h >= h} for h, label in TIMELINE]


def real_timeline(milestones: list) -> list:
    """Suivi réel : jalons déclarés par le transporteur depuis son espace."""
    done = {m["step"]: m for m in milestones}
    return [{"label": label, "done": step in done, "at": done[step]["ts"] if step in done else None}
            for step, label in STEPS]
