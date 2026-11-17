"""Agent de risque marchandise : compare la valeur déclarée à la garantie d'assurance du transporteur.

- valeur déclarée > garantie du transporteur  → transporteur écarté pour cette expédition ;
- valeur déclarée absente mais incohérente avec la nature (très élevée au kilo) → alerte pour l'opérateur ;
- aucun transporteur couvrant la valeur → escalade humaine (assurance « ad valorem » à souscrire).
La garantie contractuelle réelle doit être vérifiée sur l'attestation d'assurance du transporteur (champ `insurance_cover_eur` à alimenter).
"""


def filter_candidates(ranked: list, carriers_by_id: dict, goods_value_eur, weight_kg: float):
    """Renvoie (candidats couverts, écartés, alertes)."""
    kept, rejected, alerts = [], [], []
    if goods_value_eur:
        if weight_kg and goods_value_eur / weight_kg > 300:
            alerts.append(f"Valeur au kilo élevée ({goods_value_eur / weight_kg:.0f} €/kg) : vérifier la nature de la marchandise et l'emballage.")
    for cand in ranked:
        c = carriers_by_id[cand["carrier_id"]]
        if goods_value_eur and goods_value_eur > c.insurance_cover_eur:
            rejected.append({"carrier": c.name, "reasons": [
                f"Garantie d'assurance {c.insurance_cover_eur:,.0f} € < valeur déclarée {goods_value_eur:,.0f} €".replace(",", " ")]})
        else:
            kept.append(cand)
    return kept, rejected, alerts
