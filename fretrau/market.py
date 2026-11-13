"""Calage des prix sur le marché réel, axe par axe.

Chaque transport confié à un vrai transporteur compare le prix d'achat obtenu à l'estimation du moteur.
Le rapport est lissé par axe (département de départ > département d'arrivée) et corrige les devis suivants,
dans une fourchette bornée, à partir de MIN_SAMPLES transports. Les transporteurs simulés ne comptent pas.
"""
from . import geo

MIN_SAMPLES = 3
ALPHA = 0.3                 # poids du dernier prix observé
LOW, HIGH = 0.85, 1.15      # correction maximale de l'estimation


def lane(origin: str, destination: str) -> str:
    return f"{geo.department(origin) or origin}>{geo.department(destination) or destination}"


def factor(db, origin: str, destination: str) -> float:
    st = db.lane_stat(lane(origin, destination)) if db is not None else None
    if not st or st["n"] < MIN_SAMPLES:
        return 1.0
    return round(min(HIGH, max(LOW, st["ratio"])), 4)


def record(db, origin: str, destination: str, estimate: float, actual: float):
    if not estimate or not actual:
        return
    obs = min(1.5, max(0.5, actual / estimate))
    key = lane(origin, destination)
    st = db.lane_stat(key)
    if st:
        db.save_lane_stat(key, st["n"] + 1, round((1 - ALPHA) * st["ratio"] + ALPHA * obs, 4))
    else:
        db.save_lane_stat(key, 1, round(obs, 4))
