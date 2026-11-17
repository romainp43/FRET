"""Moteur de devis FRETRAU, piloté par le barème config/tariff.json (voir tariff.py).

Coût d'achat transport estimé (ce que FRETRAU paierait à un transporteur) :
  FTL : km x indice marché (€/km) x multiplicateur de tranche de distance x indice pays moyen
  LTL : max(palettes, poids / 740 kg) unités x (base + €/km x km) x indice pays, plafonné au coût FTL du même trajet
Puis options, indexation gazole (CNR), intervalle d'incertitude, marge cible + prime de risque.
"""
from dataclasses import dataclass, field
from datetime import date

from . import calendar_fr, geo, routing, tariff

FTL_MAX_KG = 24000
MAX_PALLETS = 33
VAT_FR = 0.20
_T0 = tariff.load()
TARGET_MARGIN = _T0["margin"]["target"]
MIN_MARGIN = _T0["margin"]["minimum"]
OPTIONS = {
    "adr": "Matières dangereuses (ADR)",
    "tail_lift": "Hayon élévateur",
    "temperature": "Température dirigée",
    "urgent": "Express (livraison la plus rapide)",
}
ALPINE = {"IT", "CH"}


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
    options: dict = field(default_factory=dict)
    pallets: int = 0
    weight_kg: float = 0.0
    taxable_units: float = 0.0
    cost_low: float = 0.0
    cost_high: float = 0.0
    uncertainty: float = 0.0
    warnings: list = field(default_factory=list)
    tariff_version: str = ""
    km_source: str = ""
    earliest_delivery: str = ""


def _country_factor(t, origin, destination):
    idx = t["country_cost_index"]
    return (idx[geo.country(origin)] + idx[geo.country(destination)]) / 2.0


def _ftl_base(t, km, factor):
    bands = t["ftl"]["distance_band_multipliers"]
    mult = next(b["mult"] for b in bands if b["max_km"] is None or km <= b["max_km"])
    return max(t["ftl"]["min_charge_eur"], km * t["market_index"]["eur_per_km"] * mult * factor)


def _is_alpine(a, b):
    ca, cb = geo.country(a), geo.country(b)
    return ca != cb and bool({ca, cb} & ALPINE)


def estimate_cost(mode, origin, destination, pallets, weight_kg, options, t=None, km=None):
    """Retourne un dict : km, mid, low, high, uncertainty, lines, warnings, units."""
    t = t or tariff.load()
    if km is None:
        km = routing.distance(origin, destination)[0]
    factor = _country_factor(t, origin, destination)
    warnings, lines = [], {}
    ftl = _ftl_base(t, km, factor)
    units = 0.0
    if mode == "FTL":
        base = ftl
        lines["transport_base"] = base
    else:
        L = t["ltl"]
        units = max(float(pallets), weight_kg / L["kg_per_euro_pallet"])
        raw = max(L["min_charge_eur"], units * (L["per_unit_base_eur"] + L["per_unit_per_km_eur"] * km) * factor)
        cap = ftl * L["cap_ratio_vs_ftl"]
        base = min(raw, cap)
        if raw > cap:
            warnings.append("Prix groupage plafonné au prix d'un camion complet : réservez un camion complet.")
        elif units > 12:
            warnings.append("Au-delà de 12 palettes, un camion complet peut être plus avantageux.")
        lines["transport_base"] = base

    subtotal = base
    o = t["options"]
    for key, label in (("adr", "adr"), ("temperature", "temperature"), ("urgent", "express")):
        if options.get(key):
            lines[label] = base * o[key]["pct"]
            subtotal += lines[label]
    f = t["fuel"]
    if f.get("index_now") is not None:
        delta = f["weight"] * (f["index_now"] / f["index_ref"] - 1.0)
        lines["indexation_gazole"] = subtotal * delta
        subtotal += lines["indexation_gazole"]
    if options.get("tail_lift"):
        lines["hayon"] = o["tail_lift"]["eur"]
        subtotal += lines["hayon"]

    u = t["uncertainty"]
    international = geo.country(origin) != geo.country(destination)
    unc = u[("ftl_" if mode == "FTL" else "ltl_") + ("international" if international else "domestic")]
    if "CH" in (geo.country(origin), geo.country(destination)):
        unc += u["switzerland_extra"]
        warnings.append("Suisse : redevance poids lourds (RPLP) et douane possibles, prix indicatif.")
    if _is_alpine(origin, destination):
        unc += u["alpine_extra"]
        warnings.append("Traversée alpine : péages de tunnel et restrictions de circulation possibles.")
    mid = round(subtotal, 2)
    return {"km": km, "mid": mid, "low": round(mid * (1 - unc), 2), "high": round(mid * (1 + unc), 2),
            "uncertainty": round(unc, 3), "lines": {k: round(v, 2) for k, v in lines.items()},
            "warnings": warnings, "units": round(units, 2)}


def build_quote(origin, destination, mode, pallets, weight_kg, options=None, pickup: date = None,
                deliver_by: date = None) -> Quote:
    t = tariff.load()
    options = {k: bool(v) for k, v in (options or {}).items() if k in OPTIONS}
    if not geo.known(origin) or not geo.known(destination):
        raise QuoteError("Ville inconnue : choisissez une ville dans la liste proposée.")
    if origin == destination:
        raise QuoteError("L'origine et la destination doivent être différentes.")
    served = {c for c in t["country_cost_index"] if len(c) == 2}
    for place in (origin, destination):
        if geo.country(place) not in served:
            raise QuoteError(f"Pays non desservi pour l'instant : {geo.country(place)}.")
    if mode not in ("FTL", "LTL"):
        raise QuoteError("Mode de transport invalide.")
    if isinstance(weight_kg, bool) or not isinstance(weight_kg, (int, float)) or not 1 <= weight_kg <= FTL_MAX_KG:
        raise QuoteError(f"Poids invalide (1 à {FTL_MAX_KG} kg).")
    if mode == "FTL":
        pallets = int(pallets or MAX_PALLETS)
        if not 1 <= pallets <= MAX_PALLETS:
            raise QuoteError("Nombre de palettes invalide pour un camion complet (1 à 33).")
    else:
        if isinstance(pallets, bool) or not isinstance(pallets, int) or not 1 <= pallets <= MAX_PALLETS:
            raise QuoteError("Nombre de palettes invalide (1 à 33).")
        if weight_kg > pallets * 1000:
            raise QuoteError("Poids par palette supérieur à 1 000 kg : contactez-nous pour un devis sur mesure.")
    if options.get("temperature") and options.get("adr"):
        raise QuoteError("ADR et température dirigée ne sont pas combinables en ligne : contactez-nous.")

    est = estimate_cost(mode, origin, destination, pallets, weight_kg, options, t)
    km = est["km"]
    delivery_note = ""
    earliest = ""
    if pickup is not None:
        if not calendar_fr.is_business_day(pickup):
            raise QuoteError("L'enlèvement doit avoir lieu un jour ouvré (hors week-end et jours fériés).")
        e = calendar_fr.earliest_delivery(pickup, km, bool(options.get("urgent")))
        earliest = e.isoformat()
        if deliver_by is not None and e > deliver_by:
            fast = calendar_fr.earliest_delivery(pickup, km, True)
            if not options.get("urgent") and fast <= deliver_by:
                raise QuoteError(f"Livraison au plus tôt le {e.isoformat()} en standard. "
                                 f"Avec l'option Express, elle est possible le {fast.isoformat()}.")
            raise QuoteError(f"Délai impossible : livraison au plus tôt le {fast.isoformat()} "
                             f"(en Express). Reculez la date de livraison souhaitée.")

    m = t["margin"]
    price_ht = round(est["mid"] * (1 + m["target"] + m["risk_premium_share"] * est["uncertainty"]), 2)
    domestic = geo.country(origin) == "FR" and geo.country(destination) == "FR"
    vat = round(price_ht * VAT_FR, 2) if domestic else 0.0
    return Quote(
        mode=mode, origin=origin, destination=destination, distance_km=km,
        transit_days=calendar_fr.transit_days(km, bool(options.get("urgent"))),
        carrier_cost_estimate=est["mid"], price_ht=price_ht, vat=vat, price_ttc=round(price_ht + vat, 2),
        breakdown=est["lines"], options=options, pallets=pallets, weight_kg=float(weight_kg),
        taxable_units=est["units"], cost_low=est["low"], cost_high=est["high"], uncertainty=est["uncertainty"],
        warnings=est["warnings"], tariff_version=t["version"], km_source=routing.distance(origin, destination)[1],
        earliest_delivery=earliest)
