"""Agent de conformité : écarte tout transporteur non conforme AVANT toute comparaison de prix.

Contrôles : liste d'exclusion, licence, assurance valide à la date d'enlèvement, mode, périmètre international,
et équipements exigés par la commande (ADR, hayon, température dirigée).
"""
from datetime import date
from .. import geo

EQUIPMENT = {"adr": ("adr", "habilitation ADR"), "tail_lift": ("tail_lift", "hayon élévateur"),
             "temperature": ("reefer", "groupe froid"), "flatbed": ("flatbed", "plateau")}


def check(carrier, mode: str, origin: str, destination: str, pickup: date, options: dict = None) -> tuple[bool, list]:
    reasons = []
    if carrier.blocked:
        reasons.append("Transporteur sur liste d'exclusion interne")
    if not carrier.licence_ok:
        reasons.append("Inscription au registre des transporteurs non vérifiée")
    try:
        if date.fromisoformat(carrier.insurance_until) < pickup:
            reasons.append(f"Assurance expirée au {carrier.insurance_until}")
    except ValueError:
        reasons.append("Date d'assurance illisible")
    if mode not in carrier.modes:
        reasons.append(f"Ne propose pas le mode {mode}")
    if geo.country(origin) != geo.country(destination) and not carrier.europe:
        reasons.append("Non habilité au transport international")
    for opt, (attr, label) in EQUIPMENT.items():
        if (options or {}).get(opt) and not getattr(carrier, attr):
            reasons.append(f"Équipement manquant : {label}")
    return (not reasons), reasons
