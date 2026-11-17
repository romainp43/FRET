"""Banc d'essai : le modèle de prix FRETRAU face aux relevés publics de data/market_benchmarks.json.

Mesure l'écart relatif entre le PRIX D'ACHAT estimé (coût transporteur, avant marge) et le tarif de marché de la liaison.
Un écart n'est pas une erreur prouvée : les relevés sont des moyennes de liaison, le modèle estime un envoi précis.
Usage : python3 tools/backtest_market.py [--max-mape 0.20]   (code de sortie 1 si l'écart moyen dépasse le seuil)
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import pricing  # noqa: E402


def run():
    with open(os.path.join(ROOT, "data", "market_benchmarks.json"), encoding="utf-8") as f:
        b = json.load(f)
    rows = []
    for ln in b["lanes"]:
        e = pricing.estimate_cost("FTL", ln["origin"], ln["destination"], 33, 15000, {})
        km = e["km"]
        model = e["mid"] / km
        mkt = (ln["contract"] + ln["spot"]) / 2
        rows.append({"lane": f"{ln['origin']} → {ln['destination']}", "km": round(km), "model": round(model, 3), "market": round(mkt, 3),
                     "in_range": ln["contract"] * 0.9 <= model <= ln["spot"] * 1.1, "err": (model - mkt) / mkt})
    mape = sum(abs(r["err"]) for r in rows) / len(rows)
    bias = sum(r["err"] for r in rows) / len(rows)
    return rows, mape, bias


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-mape", type=float, default=0.20)
    a = ap.parse_args()
    rows, mape, bias = run()
    for r in rows:
        print(f"{r['lane']:<26} {r['km']:>5} km  modèle {r['model']:.2f} €/km  marché {r['market']:.2f} €/km  écart {r['err']:+.1%}")
    print(f"Écart absolu moyen {mape:.1%} · biais {bias:+.1%} (sur {len(rows)} liaisons)")
    sys.exit(0 if mape <= a.max_mape else 1)


if __name__ == "__main__":
    main()
