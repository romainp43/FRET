"""Réclamations (avarie, manque, perte, retard) : calcul des délais légaux à partir de la date de livraison.

Repères (à faire valider par votre juriste ; ils ne remplacent pas un avis) :
- France / France : protestation motivée par lettre recommandée dans les 3 jours suivant la réception, dimanches et jours
  fériés non compris (Code de commerce, art. L133-3) ; prescription de l'action : 1 an (art. L133-6).
- International (Convention CMR) : réserves écrites dans les 7 jours suivant la livraison pour un dommage non apparent,
  dimanches et jours fériés non compris ; 21 jours pour un retard (art. 30) ; prescription : 1 an (art. 32).
- Dans tous les cas : des réserves précises et datées sur le récépissé du transporteur À LA LIVRAISON protègent le mieux.
"""
from datetime import date, timedelta

from . import calendar_fr

KINDS = {"damage": "Marchandise abîmée", "shortage": "Manque / colis manquant", "loss": "Marchandise perdue",
         "delay": "Retard de livraison", "other": "Autre problème"}


def _add_days_excl_sundays_holidays(start: date, n: int) -> date:
    d, left = start, n
    while left:
        d += timedelta(days=1)
        if d.weekday() != 6 and d not in calendar_fr.holidays(d.year):
            left -= 1
    return d


def deadlines(kind: str, delivered_on: date, international: bool) -> dict:
    if international:
        days = 21 if kind == "delay" else 7
        rule = "CMR art. 30 : réserves écrites " + ("dans les 21 jours (retard)" if kind == "delay" else "dans les 7 jours (dommage non apparent)")
        written = delivered_on + timedelta(days=days) if kind == "delay" else _add_days_excl_sundays_holidays(delivered_on, days)
    else:
        rule = "Code de commerce L133-3 : protestation motivée par lettre recommandée sous 3 jours (hors dimanches et jours fériés)"
        written = _add_days_excl_sundays_holidays(delivered_on, 3)
    try:
        limitation = delivered_on.replace(year=delivered_on.year + 1)
    except ValueError:
        limitation = delivered_on + timedelta(days=365)
    return {"written_reserve_before": written.isoformat(), "limitation_date": limitation.isoformat(), "rule": rule,
            "international": international}
