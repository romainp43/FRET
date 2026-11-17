"""Banc d'essai de la chaîne d'agents (classement → négociation → décision) dans un MARCHÉ SIMULÉ.

Principe : le simulateur tire un « monde caché » (vrais prix et vraie ponctualité de chaque transporteur, différents de ce
que les agents croient) et mesure le coût réel espéré du transporteur retenu, comparé à l'ORACLE (le meilleur choix si l'on
connaissait le monde caché). L'écart s'appelle le regret (en % du prix d'achat). Un agent est meilleur quand son regret baisse.

LIMITE ESSENTIELLE : le monde caché est écrit par nous. Les gains mesurés ici prouvent qu'un réglage est meilleur SOUS CES
HYPOTHÈSES ; ils ne prouvent pas une performance équivalente sur le vrai marché. Pour passer au réel, rejouer ce banc avec
l'historique de vos transports (voir tools/calibrate.py) et remplacer les lois du monde caché par ce que vous observez.
"""
import math
import random
from dataclasses import dataclass, replace
from datetime import date, timedelta

from . import calendar_fr, pricing
from .agents import decision, sourcing
from .carriers import CARRIERS

PRICE_NOISE = 0.06       # écart-type (log) entre le prix que l'on croit et le vrai prix du transporteur
RELIABILITY_NOISE = 0.03  # écart-type entre la ponctualité affichée et la vraie
PENALTY_RANGE = (0.30, 0.80)   # coût réel d'un retard, en part du prix (inconnu : tiré dans cette fourchette pour chaque monde)
WALK_AWAY = 0.92         # un transporteur refuse net une offre inférieure à 92 % de son prix de réserve (offre jugée insultante)
MANUAL_PREMIUM = 0.10    # surcoût estimé d'une escalade humaine (aucun accord)
LANES = [("Lyon", "Paris"), ("Paris", "Marseille"), ("Lille", "Lyon"), ("Bordeaux", "Toulouse"), ("Nantes", "Rennes"),
         ("Strasbourg", "Dijon"), ("Marseille", "Nice"), ("Toulouse", "Lyon"), ("Paris", "Rouen"), ("Lyon", "Milan"),
         ("Lille", "Bruxelles"), ("Strasbourg", "Munich"), ("Madrid", "Lyon"), ("Rennes", "Bordeaux"), ("Nancy", "Paris")]


@dataclass(frozen=True)
class Params:
    weights_normal: tuple = sourcing.W_NORMAL
    weights_tight: tuple = sourcing.W_TIGHT
    late_ratio: float = 0.5
    offers: tuple = (0.90, 0.94, 0.98, 1.04)
    soft_target: float = 1.03
    candidates: int = 5


def baseline() -> Params:
    from .agents import negotiation
    return Params(offers=tuple(negotiation.OFFERS), soft_target=negotiation.SOFT_TARGET)


def _world(rng, penalty):
    observed = [c for c in CARRIERS if not c.blocked and c.licence_ok and date.fromisoformat(c.insurance_until) > date(2026, 12, 31)]
    truth = {}
    for c in observed:
        truth[c.id] = replace(c, price_factor=c.price_factor * math.exp(rng.gauss(0, PRICE_NOISE)),
                              reliability=min(0.999, max(0.5, c.reliability + rng.gauss(0, RELIABILITY_NOISE))))
    return observed, truth


def episode(seed, params: Params, penalty=None):
    rng = random.Random(seed)
    penalty = rng.uniform(*PENALTY_RANGE) if penalty is None else penalty
    observed, truth = _world(rng, penalty)
    o, d = rng.choice(LANES)
    mode = rng.choice(["FTL", "LTL", "FTL"])
    pallets = 33 if mode == "FTL" else rng.randint(2, 10)
    weight = 15000 if mode == "FTL" else pallets * rng.randint(200, 700)
    pickup = calendar_fr.next_business_day(date(2026, 12, 1) + timedelta(days=rng.randint(0, 20)))
    q = pricing.build_quote(o, d, mode, pallets, weight, {}, pickup)
    tight_deadline = None
    if rng.random() < 0.25:
        tight_deadline = date.fromisoformat(q.earliest_delivery) + timedelta(days=rng.choice([0, 1]))
    w = params.weights_tight if (tight_deadline and (tight_deadline - date.fromisoformat(q.earliest_delivery)).days <= sourcing.TIGHT_SLACK_DAYS) else params.weights_normal
    ranked, _ = sourcing.rank(q, pickup, carriers=observed, top_n=params.candidates, deliver_by=tight_deadline, weights=w)
    if not ranked:
        return None
    by_id = {c.id: c for c in observed}
    dres = decision.choose(q, ranked, by_id, max_candidates=params.candidates, truth_by_id=truth, ratio=params.late_ratio,
                           offers=params.offers, soft_target_mult=params.soft_target, walk_away=WALK_AWAY)
    market = q.carrier_cost_estimate
    # oracle : meilleur coût réel espéré parmi les transporteurs éligibles, achetés à leur vrai prix de réserve
    def true_cost(price, car):
        return price * (1 + (1 - truth[car.id].reliability) * penalty)
    eligible_ids = {r["carrier_id"] for r in sourcing.rank(q, pickup, carriers=observed, top_n=99, deliver_by=tight_deadline)[0]}
    oracle = min(true_cost(round(market * truth[i].price_factor * 0.96, 2), truth[i]) for i in eligible_ids)
    if dres["best"]:
        row, car = dres["best"]
        paid = row["price"]
        cost = true_cost(paid, car)
        agreed = True
    else:
        cost = market * (1 + MANUAL_PREMIUM)
        agreed = False
    return {"cost": cost, "oracle": oracle, "regret_pct": (cost - oracle) / oracle * 100, "agreed": agreed}


def evaluate(params: Params, seeds):
    rows = [r for r in (episode(s, params) for s in seeds) if r]
    n = len(rows)
    mean = sum(r["regret_pct"] for r in rows) / n
    sd = (sum((r["regret_pct"] - mean) ** 2 for r in rows) / max(1, n - 1)) ** 0.5
    return {"n": n, "regret_pct": mean, "se": sd / math.sqrt(n), "agreement_rate": sum(r["agreed"] for r in rows) / n}


def paired_gain(base: Params, tuned: Params, seeds):
    """Gain moyen (points de regret) sur les MÊMES mondes, avec erreur-type : bien plus fiable que deux moyennes séparées."""
    diffs = []
    for s in seeds:
        a, b = episode(s, base), episode(s, tuned)
        if a and b:
            diffs.append(a["regret_pct"] - b["regret_pct"])
    n = len(diffs)
    mean = sum(diffs) / n
    sd = (sum((x - mean) ** 2 for x in diffs) / max(1, n - 1)) ** 0.5
    return {"n": n, "gain_pts": mean, "se": sd / math.sqrt(n)}


def random_params(rng) -> Params:
    def simplex(k):
        x = [rng.random() + 0.05 for _ in range(k)]
        t = sum(x)
        return tuple(round(v / t, 3) for v in x)
    from . import agent_config
    wn, wt = simplex(4), simplex(4)
    while not agent_config.tight_ok(wn, wt):          # contrainte métier : jamais de réglage qui sacrifie la ponctualité en délai serré
        wt = simplex(4)
    o1 = rng.uniform(0.84, 0.95)
    step = rng.uniform(0.02, 0.06)
    return Params(weights_normal=wn, weights_tight=wt, late_ratio=round(rng.uniform(0.2, 1.0), 2),
                  offers=(round(o1, 3), round(o1 + step, 3), round(o1 + 2 * step, 3), round(o1 + 3 * step + 0.02, 3)),
                  soft_target=round(rng.uniform(0.98, 1.08), 3), candidates=rng.choice([3, 4, 5]))
