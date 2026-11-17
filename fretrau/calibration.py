"""Calibration du modèle de coût sur vos prix transporteurs RÉELS.

À partir de l'historique (CSV : origin,destination,mode,pallets,weight_kg,adr,tail_lift,temperature,urgent,actual_price_ht)
on mesure l'erreur du modèle (MAPE, biais, couverture de l'intervalle) par mode et tranche de distance, et on propose
des multiplicateurs correctifs avec rétrécissement vers 1 quand l'échantillon est petit (n / (n + 10)).
Rien n'est appliqué automatiquement : vous relisez, puis vous mettez à jour config/tariff.json.
"""
import csv
import statistics

from . import pricing, tariff

SHRINK_K = 10


def load_samples(path):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "origin": r["origin"], "destination": r["destination"], "mode": r["mode"],
                "pallets": int(r["pallets"]) if r.get("pallets") else None, "weight_kg": float(r["weight_kg"]),
                "options": {k: str(r.get(k, "")).lower() in ("1", "true", "oui", "x") for k in
                            ("adr", "tail_lift", "temperature", "urgent")},
                "actual": float(r["actual_price_ht"]),
            })
    return out


def _band(km, t):
    for b in t["ftl"]["distance_band_multipliers"]:
        if b["max_km"] is None or km <= b["max_km"]:
            return f"<= {b['max_km']} km" if b["max_km"] else "> " + str(
                t["ftl"]["distance_band_multipliers"][-2]["max_km"]) + " km"


def evaluate(samples, t=None):
    t = t or tariff.load()
    rows = []
    for s in samples:
        pallets = s["pallets"] or (33 if s["mode"] == "FTL" else 1)
        est = pricing.estimate_cost(s["mode"], s["origin"], s["destination"], pallets, s["weight_kg"], s["options"], t)
        rows.append({"mode": s["mode"], "band": _band(est["km"], t), "pred": est["mid"], "low": est["low"],
                     "high": est["high"], "actual": s["actual"]})
    if not rows:
        return {"n": 0}
    def stats(rs):
        ratios = [r["actual"] / r["pred"] for r in rs]
        return {"n": len(rs),
                "mape": round(statistics.mean(abs(r["actual"] - r["pred"]) / r["actual"] for r in rs), 4),
                "bias_median_ratio": round(statistics.median(ratios), 4),
                "coverage": round(sum(r["low"] <= r["actual"] <= r["high"] for r in rs) / len(rs), 3)}
    groups = {}
    for r in rows:
        groups.setdefault((r["mode"], r["band"]), []).append(r)
    return {"overall": stats(rows), "groups": {f"{m} {b}": stats(rs) for (m, b), rs in sorted(groups.items())}}


def suggest(samples, t=None):
    """Multiplicateurs correctifs proposés par (mode, tranche) ; 1.0 = ne rien changer."""
    rep = evaluate(samples, t)
    out = {}
    for g, st in rep.get("groups", {}).items():
        shrink = st["n"] / (st["n"] + SHRINK_K)
        out[g] = {"n": st["n"], "suggested_multiplier": round(1 + shrink * (st["bias_median_ratio"] - 1), 3)}
    return out
