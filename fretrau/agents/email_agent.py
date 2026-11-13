"""Agent e-mail : traite la réponse d'un transporteur pour une réservation en attente d'attribution.

Sécurité (anti-injection de prompt) : le texte reçu n'est jamais exécuté ni confié à un LLM qui déciderait.
On en extrait UN montant en euros (security.parse_amount), validé par du code, puis la décision est prise
par offers.decide : plafond d'achat garantissant la marge minimale, contrôle de conformité du transporteur.
"""
from .. import offers, security

COUNTER_TOLERANCE = offers.COUNTER_TOLERANCE


def handle(db, code: str, carrier_id: int, text: str) -> dict:
    return offers.decide(db, code, carrier_id, security.parse_amount(text), raw=text, channel="email")
