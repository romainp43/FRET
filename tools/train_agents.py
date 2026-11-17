#!/usr/bin/env python3
"""Règle les paramètres des agents (poids du classement, ratio de retard, calendrier d'offres, objectif d'accord) dans le marché simulé.

  python3 tools/train_agents.py            # recherche + rapport, écrit config/agents.json si le gain est net
  python3 tools/train_agents.py --dry      # sans écrire

Méthode : recherche aléatoire sur des mondes d'ENTRAÎNEMENT ; les meilleurs réglages sont re-testés sur des mondes de
VALIDATION jamais vus ; le vainqueur n'est retenu que s'il bat le réglage actuel de façon nette (gain > 2 erreurs-types) ;
le gain final est mesuré sur des mondes de TEST encore différents. Voir les limites dans fretrau/simulation.py :
ce sont des gains sous les hypothèses du simulateur, pas une promesse sur le marché réel.
"""
import json
import os
import random
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import simulation as S  # noqa: E402

TRAIN, VALID, TEST = range(0, 500), range(10_000, 11_500), range(50_000, 52_500)
N_CANDIDATES, TOP_K = 800, 8


def to_config(p, report):
    return {"version": date.today().isoformat(), "source": "tools/train_agents.py (marché simulé)",
            "sourcing": {"weights_normal": list(p.weights_normal), "weights_tight": list(p.weights_tight)},
            "decision": {"late_cost_ratio": p.late_ratio, "candidates": p.candidates},
            "negotiation": {"offers": list(p.offers), "soft_target": p.soft_target},
            "report": report}


def main():
    dry = "--dry" in sys.argv
    base = S.baseline()
    rng = random.Random(2026)
    scored = []
    base_train = S.evaluate(base, TRAIN)["regret_pct"]
    for _ in range(N_CANDIDATES):
        p = S.random_params(rng)
        scored.append((S.evaluate(p, TRAIN)["regret_pct"], p))
    scored.sort(key=lambda x: x[0])
    best = None
    for tr, p in scored[:TOP_K]:
        g = S.paired_gain(base, p, VALID)
        if best is None or g["gain_pts"] > best[0]["gain_pts"]:
            best = (g, p, tr)
    g_valid, tuned, tr = best
    adopt = g_valid["gain_pts"] > 2 * g_valid["se"] and g_valid["gain_pts"] > 0.5
    final_p = tuned if adopt else base
    g_test = S.paired_gain(base, final_p, TEST)
    ev_base, ev_final = S.evaluate(base, TEST), S.evaluate(final_p, TEST)
    report = {"candidates_tried": N_CANDIDATES, "baseline_regret_test_pct": round(ev_base["regret_pct"], 2),
              "tuned_regret_test_pct": round(ev_final["regret_pct"], 2), "test_gain_pts": round(g_test["gain_pts"], 2),
              "test_gain_se": round(g_test["se"], 2), "valid_gain_pts": round(g_valid["gain_pts"], 2), "adopted": adopt,
              "agreement_rate_test": round(ev_final["agreement_rate"], 3), "worlds": {"train": len(TRAIN), "valid": len(VALID), "test": len(TEST)}}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("Réglage retenu :", final_p)
    # robustesse : le gain tient-il quand le coût réel d'un retard est connu (faible ou fort) ?
    for pen in (0.3, 0.8):
        b = [S.episode(s, base, pen)["regret_pct"] for s in range(60_000, 60_600) if S.episode(s, base, pen)]
        t = [S.episode(s, final_p, pen)["regret_pct"] for s in range(60_000, 60_600) if S.episode(s, final_p, pen)]
        print(f"  pénalité de retard {pen:.0%} : regret {sum(b)/len(b):.2f} → {sum(t)/len(t):.2f}")
    if not dry:
        cfg = to_config(final_p, report)
        with open(os.path.join(ROOT, "config", "agents.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("config/agents.json écrit.")


if __name__ == "__main__":
    main()
