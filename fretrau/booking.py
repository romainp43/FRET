"""Orchestrateur de réservation : conformité → comparaison → négociation → affectation."""
import secrets
from datetime import date

from . import pricing, tariff
from .agents import sourcing, costcheck, risk, decision
from .carriers import CARRIERS

MAX_CARRIERS_TRIED = 3
# Jalons de suivi (heures après la réservation) — démonstration ; en production : API télématique.
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


def run(quote_payload: dict, pickup: date, deliver_by: date = None, goods_value_eur: float = None) -> dict:
    quote = quote_from_payload(quote_payload)
    ranked, rejected = sourcing.rank(quote, pickup, deliver_by=deliver_by)
    log = {"rejected_by_compliance": rejected, "ranking": ranked, "negotiations": [],
           "tariff_version": quote.tariff_version, "cost_interval": [quote.cost_low, quote.cost_high],
           "cost_crosscheck": costcheck.review(quote), "alerts": []}
    if log["cost_crosscheck"].get("warning"):
        log["alerts"].append(log["cost_crosscheck"]["warning"])
    threshold = tariff.load()["guards"]["high_value_goods_eur"]
    if goods_value_eur is not None and goods_value_eur > threshold:
        # Marchandise de forte valeur : l'assurance et la limite de responsabilité se valident avec un humain.
        log["escalation_reason"] = f"Valeur déclarée {goods_value_eur:.0f} € > seuil {threshold} €"
        return {"status": "pending_human", "carrier": None, "price": None, "log": log}
    by_id = {c.id: c for c in CARRIERS}

    ranked, risk_rejected, risk_alerts = risk.filter_candidates(ranked, by_id, goods_value_eur, quote.weight_kg)
    log["rejected_by_risk"] = risk_rejected
    log["alerts"] += risk_alerts
    if not ranked:
        log["escalation_reason"] = "Aucun transporteur conforme et assuré pour cette valeur."
        return {"status": "pending_human", "carrier": None, "price": None, "log": log}

    log["robustness"] = decision.robustness(quote, pickup, deliver_by)
    d = decision.choose(quote, ranked, by_id)
    log["decision"] = {"late_cost_ratio": d["late_cost_ratio"], "candidates": [
        {k: v for k, v in row.items() if k != "negotiation"} for row in d["table"]]}
    log["negotiations"] = [{"carrier": row["carrier"], **row["negotiation"]} for row in d["table"]]
    if d["best"]:
        row, carrier = d["best"]
        log["decision"]["chosen"] = carrier.name
        return {"status": "confirmed", "carrier": carrier, "price": row["price"], "log": log}
    return {"status": "pending_human", "carrier": None, "price": None, "log": log}


def new_tracking_code() -> str:
    # 12 caractères aléatoires non devinables (évite l'énumération des expéditions).
    return "FR-" + secrets.token_hex(6).upper()


def timeline(created_at: float, now: float, speed: float = 1.0) -> list:
    """Événements déjà survenus. speed > 1 accélère la démo (ex. 360 : 1 h = 10 s)."""
    elapsed_h = (now - created_at) / 3600.0 * speed
    return [{"label": label, "offset_h": h, "done": elapsed_h >= h} for h, label in TIMELINE]
