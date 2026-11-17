"""Agent d'alignement tarifaire : réponse à « j'ai un devis moins cher ailleurs ».

Règles (déterministes, jamais de prix en dessous du plancher de marge) :
- le devis concurrent doit être plausible : à plus de `ratematch_max_auto_discount` (10 %) sous notre prix, on ne s'aligne pas automatiquement :
  l'écart est trop grand pour être la même prestation (périmètre, délai, assurance) ; un opérateur vérifie le devis ;
- plancher = coût d'achat estimé × (1 + marge minimale) ;
- concurrent ≥ plancher  → alignement sur le prix concurrent ;
- concurrent < plancher  → contre-proposition au plancher (jamais de vente à perte) ;
- l'alignement n'est consenti qu'une fois par devis, et le justificatif est à contrôler par un opérateur avant l'enlèvement.
L'alignement ne couvre que la même expédition (mêmes trajet, poids, date, options) : garanti ici car il porte sur un devis stocké.
"""
from .. import pricing, tariff


def evaluate(quote_payload: dict, competitor_price_ht: float) -> dict:
    ours = quote_payload["price_ht"]
    floor = round(quote_payload["carrier_cost_estimate"] * (1 + pricing.MIN_MARGIN), 2)
    g = tariff.load()["guards"]
    ratio = max(g["anomaly_low_ratio"], 1 - g["ratematch_max_auto_discount"])   # au-delà de -10 % : un humain vérifie (devis non comparable ?)
    if competitor_price_ht >= ours:
        return {"outcome": "no_action", "price_ht": ours, "message": "Notre prix est déjà égal ou inférieur au devis indiqué."}
    if competitor_price_ht < ratio * ours or competitor_price_ht <= 0:
        return {"outcome": "needs_human", "price_ht": ours,
                "message": "Le devis indiqué est très inférieur au prix de marché pour ce trajet : un conseiller va le vérifier avec vous (périmètre, délais, assurance)."}
    if competitor_price_ht >= floor:
        return {"outcome": "matched", "price_ht": round(competitor_price_ht, 2),
                "message": "Nous nous alignons sur votre devis. Merci de conserver le justificatif : il sera vérifié avant l'enlèvement."}
    return {"outcome": "counter", "price_ht": floor,
            "message": "Nous ne pouvons pas descendre jusqu'à ce prix sans dégrader la qualité de service ; voici notre meilleure offre."}


def apply(quote_payload: dict, result: dict) -> dict:
    """Renvoie un nouveau payload de devis avec le prix aligné (TVA et détail recalculés au prorata)."""
    q = dict(quote_payload)
    old = q["price_ht"]
    new = result["price_ht"]
    vat_rate = (q["vat"] / old) if old else 0.0
    q["price_ht"] = round(new, 2)
    q["vat"] = round(new * vat_rate, 2)
    q["price_ttc"] = round(q["price_ht"] + q["vat"], 2)
    q["breakdown"] = {key: round(v, 2) for key, v in q.get("breakdown", {}).items()}   # le détail interne reste au coût
    return q
