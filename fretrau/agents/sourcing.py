"""Agent de sourcing/comparaison : classe les transporteurs conformes selon un score pondéré.

Score = 40 % prix attendu + 20 % proximité du chargement + 20 % note + 20 % ponctualité.
Si le délai de livraison demandé est serré (marge <= 1 jour), la pondération passe à 25/20/20/35 : la ponctualité prime.
Chaque ligne est accompagnée d'une explication lisible (utile pour l'audit et l'équipe).
"""
from datetime import date
from .. import geo
from ..carriers import CARRIERS
from . import compliance

W_NORMAL = (0.40, 0.20, 0.20, 0.20)     # prix, proximité, note, ponctualité
W_TIGHT = (0.25, 0.20, 0.20, 0.35)      # délai serré : la ponctualité prime sur le prix
TIGHT_SLACK_DAYS = 1


def rank(quote, pickup: date, carriers=None, top_n=5, deliver_by: date = None, weights=None):
    carriers = CARRIERS if carriers is None else carriers
    eligible, rejected = [], []
    for c in carriers:
        ok, reasons = compliance.check(c, quote.mode, quote.origin, quote.destination, pickup,
                                       getattr(quote, "options", None))
        if ok:
            eligible.append(c)
        else:
            rejected.append({"carrier": c.name, "reasons": reasons})
    if not eligible:
        return [], rejected

    tight = False
    if deliver_by is not None and quote.earliest_delivery:
        tight = (deliver_by - date.fromisoformat(quote.earliest_delivery)).days <= TIGHT_SLACK_DAYS
    w_price, w_near, w_rating, w_reliab = weights or (W_TIGHT if tight else W_NORMAL)
    expected = {c.id: quote.carrier_cost_estimate * c.price_factor for c in eligible}
    lo, hi = min(expected.values()), max(expected.values())
    scored = []
    for c in eligible:
        price_score = 1.0 if hi == lo else 1 - (expected[c.id] - lo) / (hi - lo)
        deadhead = geo.road_km(c.base_city, quote.origin) if c.base_city != quote.origin else 0.0
        near_score = max(0.0, 1 - deadhead / 600.0)
        score = (w_price * price_score + w_near * near_score
                 + w_rating * (c.rating / 5.0) + w_reliab * c.reliability)
        scored.append({
            "carrier_id": c.id, "carrier": c.name, "score": round(score, 4),
            "expected_price": round(expected[c.id], 2), "deadhead_km": deadhead,
            "rating": c.rating, "reliability": c.reliability,
            "tight_deadline": tight,
            "why": (f"prix attendu {expected[c.id]:.0f} €, base à {deadhead:.0f} km du chargement, "
                    f"note {c.rating}/5, ponctualité {c.reliability:.0%}"),
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_n], rejected
