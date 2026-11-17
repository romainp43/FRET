"""Rapport « résultats réels » : compare ce que les agents avaient prévu à ce qui s'est passé.

Aucune modification automatique : le rapport indique des écarts, l'humain décide de recaler le barème ou la fiabilité
d'un transporteur. En dessous de 20 transports, tout est indicatif (échantillon trop petit pour conclure).
"""
MIN_SAMPLE = 20


def report(rows: list) -> dict:
    n = len(rows)
    out = {"count": n, "indicative_only": n < MIN_SAMPLE, "min_sample": MIN_SAMPLE}
    if not n:
        out.update(realized_margin_ht=0.0, realized_margin_pct=None, cost_vs_negotiated_pct=None, on_time_rate=None, carriers=[])
        return out
    revenue = sum(r["customer_price_ht"] for r in rows)
    cost = sum(r["actual_cost_ht"] for r in rows)
    negotiated = sum(r["carrier_price"] or 0 for r in rows)
    out["realized_margin_ht"] = round(revenue - cost, 2)
    out["realized_margin_pct"] = round(100 * (revenue - cost) / revenue, 1) if revenue else None
    out["cost_vs_negotiated_pct"] = round(100 * (cost - negotiated) / negotiated, 1) if negotiated else None
    out["on_time_rate"] = round(sum(r["on_time"] for r in rows) / n, 3)
    by = {}
    for r in rows:
        c = by.setdefault(r["carrier_id"], {"carrier": r["carrier_name"], "count": 0, "on_time": 0})
        c["count"] += 1
        c["on_time"] += r["on_time"]
    out["carriers"] = sorted(({"carrier": c["carrier"], "count": c["count"], "on_time_rate": round(c["on_time"] / c["count"], 3),
                               "indicative_only": c["count"] < 5} for c in by.values()), key=lambda x: -x["count"])
    return out
