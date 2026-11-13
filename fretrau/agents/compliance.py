"""Agent de conformité : écarte tout transporteur non conforme AVANT toute comparaison de prix."""
from datetime import date
from .. import geo


def check(carrier, mode: str, origin: str, destination: str, pickup: date) -> tuple[bool, list]:
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
    if ("FTL" if mode == "PTL" else mode) not in carrier.modes:
        reasons.append(f"Ne propose pas le mode {mode}")
    international = geo.country(origin) != geo.country(destination)
    if international and not carrier.europe:
        reasons.append("Non habilité au transport international")
    return (not reasons), reasons
