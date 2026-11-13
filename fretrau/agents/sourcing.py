"""Agent de sourcing/comparaison : classe les transporteurs conformes selon un score pondéré.

Score = 40 % prix attendu + 20 % proximité du chargement + 20 % note + 20 % fiabilité.
Chaque ligne est accompagnée d'une explication lisible (utile pour l'audit et l'équipe).
"""
from datetime import date
from .. import geo
from ..carriers import CARRIERS
from . import compliance

W_PRICE, W_NEAR, W_RATING, W_RELIAB = 0.40, 0.20, 0.20, 0.20


def rank(quote, pickup: date, carriers=None, top_n=5):
    carriers = CARRIERS if carriers is None else carriers
    eligible, rejected = [], []
    for c in carriers:
        ok, reasons = compliance.check(c, quote.mode, quote.origin, quote.destination, pickup)
        if ok:
            eligible.append(c)
        else:
            rejected.append({"carrier": c.name, "reasons": reasons})
    if not eligible:
        return [], rejected

    expected = {c.id: quote.carrier_cost_estimate * c.price_factor for c in eligible}
    lo, hi = min(expected.values()), max(expected.values())
    scored = []
    for c in eligible:
        price_score = 1.0 if hi == lo else 1 - (expected[c.id] - lo) / (hi - lo)
        deadhead = geo.road_km(c.base_city, quote.origin) if c.base_city != quote.origin else 0.0
        near_score = max(0.0, 1 - deadhead / 600.0)
        score = (W_PRICE * price_score + W_NEAR * near_score
                 + W_RATING * (c.rating / 5.0) + W_RELIAB * c.reliability)
        scored.append({
            "carrier_id": c.id, "carrier": c.name, "score": round(score, 4),
            "expected_price": round(expected[c.id], 2), "deadhead_km": deadhead,
            "rating": c.rating, "reliability": c.reliability,
            "why": (f"prix attendu {expected[c.id]:.0f} €, base à {deadhead:.0f} km du chargement, "
                    f"note {c.rating}/5, ponctualité {c.reliability:.0%}"),
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_n], rejected
