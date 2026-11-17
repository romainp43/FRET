"""Agent de décision : négocie avec PLUSIEURS transporteurs puis choisit le meilleur résultat final.

Avant : le premier transporteur qui acceptait était retenu. Maintenant : on obtient les offres des N meilleurs candidats,
et on retient celui dont le COÛT ATTENDU est le plus bas :
    coût attendu = prix négocié × (1 + (1 − ponctualité) × late_cost_ratio)
Un transporteur un peu moins cher mais peu ponctuel ne gagne donc pas automatiquement. En cas d'égalité : meilleur score de classement.
Le détail de chaque candidat est conservé (audit). Le paramètre late_cost_ratio est une hypothèse (tariff.json, confiance « low »).

Robustesse : le classement est recalculé sous plusieurs jeux de pondérations ; on rapporte si le premier reste le même
(stabilité). Une faible stabilité signale un choix fragile, utile à l'opérateur.
"""
from .. import tariff
from . import negotiation, sourcing

MAX_CANDIDATES = 5
SCENARIOS = {
    "base": sourcing.W_NORMAL,
    "prix_prioritaire": (0.60, 0.15, 0.10, 0.15),
    "qualite_prioritaire": (0.20, 0.20, 0.30, 0.30),
    "delai_serre": sourcing.W_TIGHT,
}


def expected_cost(price: float, reliability: float, ratio: float) -> float:
    return price * (1 + (1 - reliability) * ratio)


def choose(quote, ranked: list, carriers_by_id: dict, max_candidates: int = MAX_CANDIDATES, truth_by_id=None,
           ratio=None, offers=None, soft_target_mult=None, walk_away=None) -> dict:
    from ..agent_config import CONFIG
    ratio = CONFIG.get("late_cost_ratio", tariff.load()["decision"]["late_cost_ratio"]) if ratio is None else ratio
    table, accepted = [], []
    for cand in ranked[:max_candidates]:
        carrier = carriers_by_id[cand["carrier_id"]]
        res = negotiation.negotiate(quote, cand, carrier, truth=(truth_by_id or {}).get(carrier.id), offers=offers,
                                    soft_target_mult=soft_target_mult, walk_away=walk_away)
        row = {"carrier": carrier.name, "carrier_id": carrier.id, "score": cand["score"], "accepted": res["accepted"],
               "price": res["price"], "reliability": carrier.reliability, "negotiation": res}
        if res["accepted"]:
            row["expected_cost"] = round(expected_cost(res["price"], carrier.reliability, ratio), 2)
            accepted.append((row, carrier))
        table.append(row)
    best = None
    if accepted:
        best = min(accepted, key=lambda rc: (rc[0]["expected_cost"], -rc[0]["score"]))
    return {"table": table, "best": best, "late_cost_ratio": ratio}


def robustness(quote, pickup, deliver_by=None, equipment_filter=None) -> dict:
    """Part des scénarios de pondération dans lesquels le même transporteur arrive premier."""
    winners = {}
    for name, w in SCENARIOS.items():
        ranked, _ = sourcing.rank(quote, pickup, deliver_by=deliver_by, weights=w, top_n=1)
        winners[name] = ranked[0]["carrier"] if ranked else None
    base = winners.get("base")
    same = sum(1 for v in winners.values() if v == base)
    return {"winners": winners, "stability": round(same / len(winners), 2), "fragile": same / len(winners) < 0.75}
