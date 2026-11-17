"""Réseau de transporteurs de DÉMONSTRATION (entreprises fictives).

En production : alimenter cette table depuis votre vrai référentiel transporteurs
(vérification licence, assurance, KBIS) et les bourses de fret (Trans.eu, Timocom, Teleroute).
"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Carrier:
    id: int
    name: str
    base_city: str
    rating: float          # 1 à 5
    reliability: float     # 0 à 1 : taux de livraison à l'heure
    price_factor: float    # multiplicateur sur le prix marché
    modes: tuple
    europe: bool
    licence_ok: bool       # inscription registre des transporteurs
    insurance_until: str   # ISO date
    blocked: bool = False
    adr: bool = False          # habilité matières dangereuses (formation + équipement)
    tail_lift: bool = False    # véhicule(s) avec hayon élévateur
    reefer: bool = False       # groupe froid / température dirigée
    insurance_cover_eur: float = 150000.0   # plafond de garantie RC marchandises transportées par sinistre (DÉMO)


TODAY_FALLBACK = date(2026, 11, 13)

CARRIERS = [
    Carrier(1, "Rhône Fret (démo)", "Lyon", 4.6, 0.96, 1.02, ("FTL", "LTL"), True, True, "2027-09-30", adr=True, tail_lift=True, insurance_cover_eur=300000.0),
    Carrier(2, "Nord Express Logistique (démo)", "Lille", 4.2, 0.93, 0.95, ("FTL",), True, True, "2027-03-31", reefer=True, insurance_cover_eur=250000.0),
    Carrier(3, "Atlantique Transports (démo)", "Nantes", 4.4, 0.95, 1.00, ("FTL", "LTL"), False, True, "2027-06-30", tail_lift=True),
    Carrier(4, "Garonne Routier (démo)", "Toulouse", 3.9, 0.90, 0.92, ("FTL", "LTL"), True, True, "2027-01-31", insurance_cover_eur=50000.0),
    Carrier(5, "Provence Cargo (démo)", "Marseille", 4.1, 0.92, 0.97, ("FTL", "LTL"), True, True, "2027-12-31", adr=True, reefer=True),
    Carrier(6, "Alsace Euro Trans (démo)", "Strasbourg", 4.7, 0.97, 1.08, ("FTL", "LTL"), True, True, "2027-08-31", adr=True, tail_lift=True, reefer=True, insurance_cover_eur=500000.0),
    Carrier(7, "Loire Palettes (démo)", "Saint-Etienne", 4.3, 0.94, 0.98, ("LTL",), False, True, "2027-05-31", insurance_cover_eur=80000.0),
    Carrier(8, "Paris Île-de-France Fret (démo)", "Paris", 4.0, 0.91, 1.05, ("FTL", "LTL"), True, True, "2027-10-31", tail_lift=True),
    Carrier(9, "Aquitaine Transit (démo)", "Bordeaux", 3.8, 0.88, 0.90, ("FTL",), True, True, "2027-02-28", insurance_cover_eur=50000.0),
    Carrier(10, "Bretagne Logistique (démo)", "Rennes", 4.5, 0.96, 1.01, ("FTL", "LTL"), False, True, "2027-07-31", reefer=True),
    # Cas de test pour l'agent de conformité :
    Carrier(11, "Assurance Expirée Trans (démo)", "Paris", 4.8, 0.99, 0.80, ("FTL", "LTL"), True, True, "2025-01-31"),
    Carrier(12, "Sans Licence Express (démo)", "Lyon", 4.9, 0.99, 0.75, ("FTL", "LTL"), True, False, "2027-12-31"),
    Carrier(13, "Liste Noire Fret (démo)", "Marseille", 2.1, 0.60, 0.70, ("FTL",), True, True, "2027-12-31", blocked=True),
]
