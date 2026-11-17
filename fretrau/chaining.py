"""Chaînage de chargements : repérer des enchaînements de transports réservés (arrivée de l'un près du départ du suivant)
pour réduire les kilomètres à vide. Rapport pour l'exploitation ; aucune décision automatique.

Deux réservations A puis B s'enchaînent si : la destination de A est à moins de `max_gap_km` de l'origine de B, et la date
d'enlèvement de B tombe entre la livraison estimée de A et `max_wait_days` jours après. Le gain estimé est le coût du
trajet à vide évité (distance de retour du camion x indice marché), à confirmer avec le transporteur.
"""
from datetime import date, timedelta

from . import geo, tariff


def suggestions(items, max_gap_km=120, max_wait_days=2):
    """items : liste de dicts {code, origin, destination, pickup_date (ISO), earliest_delivery (ISO), mode}."""
    t = tariff.load()
    eur_km = t["market_index"]["eur_per_km"]
    out = []
    for a in items:
        for b in items:
            if a["code"] == b["code"] or a["mode"] != "FTL" or b["mode"] != "FTL":
                continue                                  # on ne chaîne que des camions complets
            try:
                end_a = date.fromisoformat(a["earliest_delivery"])
                start_b = date.fromisoformat(b["pickup_date"])
            except (ValueError, TypeError, KeyError):
                continue
            if not end_a <= start_b <= end_a + timedelta(days=max_wait_days):
                continue
            gap = geo.road_km(a["destination"], b["origin"])
            if gap > max_gap_km:
                continue
            direct_back = geo.road_km(a["destination"], a["origin"])
            saved_km = max(0.0, direct_back - gap)
            out.append({"first": a["code"], "second": b["code"], "gap_km": round(gap),
                        "route": f"{a['origin']} → {a['destination']} puis {b['origin']} → {b['destination']}",
                        "saved_empty_km": round(saved_km), "estimated_saving_eur": round(saved_km * eur_km * 0.5, 2)})
    out.sort(key=lambda x: -x["estimated_saving_eur"])
    return out
