#!/usr/bin/env python3
"""Démonstration en direct de la chaîne d'agents sur de vraies données du code (aucune donnée inventée à l'affichage).

  python3 tools/demo_agents.py ["texte d'une demande de prix"]

Chaque agent est appelé pour de vrai ; l'affichage montre ce que chacun reçoit, décide et justifie.
"""
import json
import os
import sys
import time
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import booking, pricing, tariff  # noqa: E402
from fretrau.agents import costcheck, guard, intake, llm, ratematch  # noqa: E402

DEFAULT = "Bonjour, il me faudrait 12 palettes de Lyon vers Lille, 6000 kg, enlèvement le {d}, avec hayon. Merci"


def step(n, title):
    print(f"\n[{n}] {title}\n" + "-" * 70)


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else DEFAULT.format(d=(date.today() + timedelta(days=3)).strftime("%d/%m/%Y"))
    print("DEMANDE REÇUE (texte libre) :\n  ", text)
    print(f"\nRédaction par modèle de langage : {'ACTIVE (API Claude)' if llm.available() else 'inactive (gabarits) — aucun LLM ne décide jamais'}")

    step(1, "Agent d'accueil (intake) : texte → demande structurée")
    r = intake.parse(text)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if not r["complete"]:
        print("\nDemande incomplète → réponse automatique :\n", intake.reply_needing_info(r))
        return
    f = r["fields"]
    pickup = date.fromisoformat(f["pickup_date"])

    step(2, "Moteur de prix + agent « second avis » (coût de revient indépendant)")
    q = pricing.build_quote(f["origin"], f["destination"], f["mode"], f.get("pallets") or 0, f["weight_kg"],
                            options=f.get("options") or None, pickup=pickup)
    qd = q.__dict__ if hasattr(q, "__dict__") else dict(q)
    print(f"Prix HT : {q.price_ht:.2f} €  | distance {q.distance_km} km | intervalle de coût {q.cost_low:.0f}–{q.cost_high:.0f} €")
    print("Second avis :", json.dumps(costcheck.review(q), ensure_ascii=False))

    step(3, "Agent d'alignement tarifaire : le client annonce un concurrent à -4 %")
    rm = ratematch.evaluate(qd, round(q.price_ht * 0.96, 2))
    print(json.dumps(rm, ensure_ascii=False, indent=2))

    step(4, "Agent de garde (fraude/incohérences) sur la réservation")
    g = guard.assess({"email": "logistique@carrelages-demo.fr", "company": "Carrelages Démo SAS", "phone": "04 77 12 34 56"},
                     {"goods": "palettes de carrelage", "weight_kg": f["weight_kg"], "pallets": f.get("pallets"),
                      "pickup_address": "12 rue de la République, 69002 Lyon", "delivery_address": "45 avenue du Peuple Belge, 59000 Lille",
                      "site_contact_phone": "06 12 34 56 78"},
                     q.price_ht, [], time.time())
    print(json.dumps(g, ensure_ascii=False, indent=2, default=str))

    step(5, "Pipeline d'affectation : conformité → risque → sourcing → négociation → décision")
    res = booking.run(qd, pickup, goods_value_eur=8000)
    lg = res["log"]
    print("Écartés par la conformité :", json.dumps(lg["rejected_by_compliance"], ensure_ascii=False)[:600])
    print("Classement (score pondéré) :")
    for row in lg["ranking"][:4]:
        print("  ", json.dumps(row, ensure_ascii=False, default=str)[:260])
    print("Négociations :")
    for n in lg["negotiations"][:3]:
        print("  ", json.dumps(n, ensure_ascii=False, default=str)[:260])
    print("Décision :", json.dumps(lg.get("decision", {}).get("chosen"), ensure_ascii=False), "| statut :", res["status"],
          "| prix d'achat :", res["price"])
    print("Alertes :", lg["alerts"] or "aucune")
    print("\nRappel : les transporteurs de la base de démonstration sont fictifs ; aucun prix réel n'est présenté comme tel.")


if __name__ == "__main__":
    main()
