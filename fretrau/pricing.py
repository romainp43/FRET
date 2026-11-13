"""Moteur de devis FRETRAU.

Trois modes : FTL (camion complet, tarif au km), PTL (lot partiel, part de camion) et LTL (palettes / groupage).
Tous les paramètres tarifaires sont des valeurs de démonstration à calibrer
sur vos coûts réels et les indices du marché (CNR, bourses de fret).
"""
import os
from dataclasses import dataclass, field
from . import geo

FTL_MAX_KG = 24000
FTL_MAX_PALLETS = 33
LTL_MAX_PALLETS = 33

PTL_MIN_PALLETS, PTL_MAX_PALLETS = 4, 20
TRAILER_FLOOR_M = 13.6       # longueur utile d'une semi-remorque ; une palette 80x120 occupe 0,4 m de plancher


def _rate(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


FUEL_SURCHARGE = _rate("FRETRAU_FUEL_SURCHARGE", 0.08)   # à indexer chaque mois sur l'indice gazole CNR
TARGET_MARGIN = _rate("FRETRAU_TARGET_MARGIN", 0.12)     # marge cible sur le coût transporteur
MIN_MARGIN = _rate("FRETRAU_MIN_MARGIN", 0.05)           # plancher sous lequel les agents passent la main à un humain
VAT_FR = 0.20

OPTIONS = {
    "adr": "Matières dangereuses (ADR)",
    "tail_lift": "Hayon élévateur",
    "temperature": "Température dirigée",
    "urgent": "Express (moins de 24 h)",
    "flatbed": "Plateau (chargement latéral ou par le haut)",
}
MODES = {"FTL": "Camion complet", "PTL": "Lot partiel", "LTL": "Palettes"}


class QuoteError(ValueError):
    pass


@dataclass
class Quote:
    mode: str
    origin: str
    destination: str
    distance_km: float
    transit_days: int
    carrier_cost_estimate: float
    price_ht: float
    vat: float
    price_ttc: float
    breakdown: dict = field(default_factory=dict)


def _ftl_rate(km: float) -> float:
    if km <= 150:
        return 2.40
    if km <= 400:
        return 1.75
    if km <= 800:
        return 1.45
    return 1.30


def estimate_carrier_cost(mode, origin, destination, pallets, weight_kg, options):
    """Estimation du coût d'achat transport (ce que paierait FRETRAU à un transporteur)."""
    km = geo.road_km(origin, destination)
    international = geo.country(origin) != geo.country(destination)
    lines = {}

    if mode == "FTL":
        base = max(280.0, km * _ftl_rate(km))
        lines["transport_base"] = base
    elif mode == "PTL":
        share = min(0.90, max(0.45, pallets * 0.4 / TRAILER_FLOOR_M * 1.5))    # part de plancher, majorée de 50 %
        base = max(180.0, km * _ftl_rate(km) * share)
        lines["transport_base"] = base
    else:
        per_pallet = 14.0 + 0.085 * km
        density = max(1.0, weight_kg / max(1, pallets * 400.0))
        base = max(60.0, pallets * per_pallet * density)
        lines["transport_base"] = base

    if international:
        lines["supplement_international"] = base * 0.08
    subtotal = sum(lines.values())

    mult = 1.0
    if options.get("adr"):
        mult += 0.20
        lines["adr"] = subtotal * 0.20
    if options.get("temperature"):
        mult += 0.25
        lines["temperature"] = subtotal * 0.25
    if options.get("flatbed"):
        mult += 0.15
        lines["plateau"] = subtotal * 0.15
    if options.get("urgent"):
        mult += 0.30
        lines["express"] = subtotal * 0.30
    subtotal *= mult

    fuel = subtotal * FUEL_SURCHARGE
    lines["gazole"] = fuel
    subtotal += fuel

    if options.get("tail_lift"):
        lines["hayon"] = 45.0
        subtotal += 45.0

    return km, round(subtotal, 2), {k: round(v, 2) for k, v in lines.items()}


def build_quote(origin, destination, mode, pallets, weight_kg, options=None, market_factor=1.0) -> Quote:
    """market_factor : correction issue des prix réellement obtenus sur l'axe (voir market.py)."""
    options = {k: bool(v) for k, v in (options or {}).items() if k in OPTIONS}
    if not geo.known(origin) or not geo.known(destination):
        raise QuoteError("Lieu inconnu : indiquez un code postal français ou une ville de la liste.")
    if origin == destination:
        raise QuoteError("L'origine et la destination doivent être différentes.")
    if mode not in MODES:
        raise QuoteError("Mode de transport invalide.")
    if not isinstance(weight_kg, (int, float)) or not 1 <= weight_kg <= FTL_MAX_KG:
        raise QuoteError(f"Poids invalide (1 à {FTL_MAX_KG} kg).")
    if mode == "FTL":
        pallets = int(pallets or FTL_MAX_PALLETS)
        if not 1 <= pallets <= FTL_MAX_PALLETS:
            raise QuoteError("Nombre de palettes invalide pour un camion complet (1 à 33).")
    elif mode == "PTL":
        if isinstance(pallets, bool) or not isinstance(pallets, int) or not PTL_MIN_PALLETS <= pallets <= PTL_MAX_PALLETS:
            raise QuoteError(f"Un lot partiel compte {PTL_MIN_PALLETS} à {PTL_MAX_PALLETS} palettes.")
    else:
        if not isinstance(pallets, int) or not 1 <= pallets <= LTL_MAX_PALLETS:
            raise QuoteError("Nombre de palettes invalide (1 à 33).")
        if weight_kg > pallets * 1000:
            raise QuoteError("Poids par palette supérieur à 1 000 kg : contactez-nous pour un devis sur mesure.")

    km, cost, lines = estimate_carrier_cost(mode, origin, destination, pallets, weight_kg, options)
    if market_factor != 1.0:
        cost = round(cost * market_factor, 2)
        lines = {k: round(v * market_factor, 2) for k, v in lines.items()}
    price_ht = round(cost * (1 + TARGET_MARGIN), 2)
    domestic = geo.country(origin) == "FR" and geo.country(destination) == "FR"
    vat = round(price_ht * VAT_FR, 2) if domestic else 0.0
    return Quote(
        mode=mode, origin=origin, destination=destination, distance_km=km,
        transit_days=geo.transit_days(km, bool(options.get("urgent"))),
        carrier_cost_estimate=cost, price_ht=price_ht, vat=vat,
        price_ttc=round(price_ht + vat, 2), breakdown=lines,
    )
