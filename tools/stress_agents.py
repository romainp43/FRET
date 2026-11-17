#!/usr/bin/env python3
"""Test de charge réaliste : N envois entre communes tirées au hasard dans TOUT le référentiel (pondérées par la population quand elle est connue),
poids/palettes/options plausibles, passés dans devis → conformité → risque → décision → négociation.

Vérifie à chaque envoi des invariants (jamais de plantage, marge >= minimum, prix > coût estimé, transporteur choisi conforme, délais cohérents)
et affiche la répartition des issues. Les transporteurs restent SIMULÉS : ce test éprouve la robustesse de la chaîne, pas les prix du marché.
Usage : python3 tools/stress_agents.py [N=500] [seed=1]
"""
import random
import sqlite3
import sys
import time
from collections import Counter
from datetime import date, timedelta

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])
from fretrau import booking, calendar_fr, pricing, places  # noqa: E402
from dataclasses import asdict  # noqa: E402


def sample_places(rng, n):
    con = sqlite3.connect(f"file:{places.db_path()}?mode=ro", uri=True)
    rows = con.execute("SELECT label, country FROM places").fetchall()
    return [rng.choice(rows) for _ in range(n * 2)]


def run(n=500, seed=1, out=print):
    rng = random.Random(seed)
    pool = sample_places(rng, n)
    stats, errors, margins, times = Counter(), [], [], []
    today = calendar_fr.next_business_day(date.today() + timedelta(days=3))
    for i in range(n):
        (o, oc), (d, dc) = pool[2 * i], pool[2 * i + 1]
        if o == d:
            continue
        mode = rng.choice(["FTL", "FTL", "LTL"])
        pallets = 33 if mode == "FTL" else rng.randint(1, 20)
        weight = rng.choice([8000, 12000, 15000, 22000, 24000]) if mode == "FTL" else rng.randint(100 * pallets, 900 * pallets)
        opts = {k: True for k in rng.sample(["tail_lift", "adr", "urgent"], rng.randint(0, 1))}
        pickup = calendar_fr.next_business_day(today + timedelta(days=rng.randint(0, 6)))
        t0 = time.perf_counter()
        try:
            q = pricing.build_quote(o, d, mode, pallets, weight, opts, pickup)
        except pricing.QuoteError:
            stats["devis refusé (règle métier)"] += 1
            continue
        except Exception as e:                                      # noqa: BLE001 — c'est précisément ce qu'on cherche
            errors.append(f"build_quote {o}→{d}: {type(e).__name__} {e}")
            continue
        try:
            res = booking.run(asdict(q), pickup, None, rng.choice([None, 2000, 8000, 45000]))
        except Exception as e:                                      # noqa: BLE001
            errors.append(f"booking.run {o}→{d}: {type(e).__name__} {e}")
            continue
        times.append(time.perf_counter() - t0)
        stats[res["status"]] += 1
        m = q.price_ht / q.carrier_cost_estimate - 1
        margins.append(m)
        if q.price_ht <= q.carrier_cost_estimate:
            errors.append(f"prix <= coût {o}→{d}")
        if m < pricing.MIN_MARGIN - 1e-9:
            errors.append(f"marge {m:.3f} sous le minimum {o}→{d}")
        if res["status"] == "confirmed":
            if res["price"] is None or res["carrier"] is None:
                errors.append(f"confirmé sans transporteur/prix {o}→{d}")
            elif res["price"] > q.price_ht / (1 + pricing.MIN_MARGIN) + 0.01:
                errors.append(f"achat {res['price']} > plafond {o}→{d}")
        if q.transit_days < 1 or q.distance_km <= 0:
            errors.append(f"délai/distance incohérents {o}→{d}")
    total = sum(stats.values())
    out(f"{total} envois simulés ({seed=}) — lieux tirés parmi {places.count()} du référentiel")
    for k, v in stats.most_common():
        out(f"  {k:<34} {v:>5}  ({v / max(1, total):.0%})")
    if margins:
        ms = sorted(margins)
        out(f"Marge sur coût estimé : médiane {ms[len(ms) // 2]:.1%}, min {ms[0]:.1%}, max {ms[-1]:.1%}")
        ts = sorted(times)
        out(f"Temps par envoi : médiane {ts[len(ts) // 2] * 1000:.0f} ms, p95 {ts[int(len(ts) * .95)] * 1000:.0f} ms")
    out(f"Anomalies : {len(errors)}")
    for e in errors[:15]:
        out("  - " + e)
    return {"total": total, "errors": errors, "stats": dict(stats)}


if __name__ == "__main__":
    r = run(int(sys.argv[1]) if len(sys.argv) > 1 else 500, int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    sys.exit(1 if r["errors"] else 0)
