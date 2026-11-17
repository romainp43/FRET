"""Agent « second avis » : coût de revient bottom-up, INDÉPENDANT de l'indice de marché.

Le prix est fixé par l'indice marché (pricing.py). Cet agent reconstruit le coût d'un camion complet à partir de ses
composantes (conducteur, véhicule, gazole, péages, frais généraux, marge transporteur) et compare. Un écart important
signale un trajet mal calibré (distance erronée, tarif obsolète, indice pays douteux) : il émet un AVERTISSEMENT, il ne change jamais le prix.
Valable pour le camion complet (FTL) uniquement ; les paramètres sont des hypothèses (confiance « low »).
"""
import math
from .. import tariff

MAX_RELIABLE_KM = 800


def bottom_up_cost(km: float, t: dict = None) -> dict:
    b = (t or tariff.load())["bottom_up"]
    drive_h = km / b["avg_speed_kmh"]
    # Réglementation sociale européenne : 9 h de conduite/jour (10 h 2 fois/semaine) → repos journalier de 11 h
    # pendant lequel le conducteur n'est pas "en route", mais le véhicule et le salaire courent : on compte un repos par tranche de 9 h.
    rests = max(0, math.ceil(drive_h / 9.0) - 1)
    hours = drive_h + b["load_unload_h"] + rests * 11.0 * 0.35       # 35 % du repos reste facturable (indemnités, immobilisation)
    labour_vehicle = hours * (b["driver_eur_per_h"] + b["vehicle_fixed_eur_per_h"])
    fuel = km * b["fuel_l_per_100km"] / 100.0 * b["diesel_eur_per_l_net"]
    tolls = km * b["tolls_eur_per_km"]
    base = labour_vehicle + fuel + tolls
    total = base * (1 + b["overhead_pct"]) * (1 + b["carrier_margin_pct"])
    return {"total": round(total, 2), "per_km": round(total / km, 3), "hours": round(hours, 1),
            "parts": {"conducteur_vehicule": round(labour_vehicle, 2), "gazole": round(fuel, 2), "peages": round(tolls, 2)}}


def review(quote) -> dict:
    """Compare au coût marché du devis. Renvoie un diagnostic ; `warning` est None si les deux méthodes concordent."""
    if quote.mode != "FTL":
        return {"applicable": False, "warning": None, "reason": "camion complet uniquement"}
    if quote.distance_km > MAX_RELIABLE_KM:
        # Au-delà, le coût réel dépend du chargement retour et des équipages doubles, non modélisés ici : le modèle
        # surestime (constaté : +25 à +35 % vs relevés de marché Paris–Madrid). Pas d'avis plutôt qu'un faux avis.
        return {"applicable": False, "warning": None, "reason": f"au-delà de {MAX_RELIABLE_KM} km (retour à vide / équipage non modélisés)"}
    t = tariff.load()
    bu = bottom_up_cost(quote.distance_km, t)
    market = quote.carrier_cost_estimate
    ratio = market / bu["total"]
    tol = t["bottom_up"]["max_divergence"]
    warning = None
    if ratio < 1 - tol:
        warning = (f"Coût marché ({market:.0f} €) inférieur de {(1 - ratio) * 100:.0f} % au coût de revient reconstitué "
                   f"({bu['total']:.0f} €) : risque de sous-évaluation, à vérifier avant de s'engager.")
    elif ratio > 1 + tol and market > t["ftl"]["min_charge_eur"] + 0.01:   # le minimum de facturation explique un écart sur très court trajet
        warning = (f"Coût marché ({market:.0f} €) supérieur de {(ratio - 1) * 100:.0f} % au coût de revient reconstitué "
                   f"({bu['total']:.0f} €) : prix possiblement trop élevé (court trajet ou indice pays majoré ?).")
    return {"applicable": True, "bottom_up_eur": bu["total"], "bottom_up_per_km": bu["per_km"],
            "market_eur": round(market, 2), "ratio": round(ratio, 3), "tolerance": tol, "warning": warning, "parts": bu["parts"]}
