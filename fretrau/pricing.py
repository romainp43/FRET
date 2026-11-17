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
    "flatbed": "Plateau / semi-remorque non bâchée (camion complet)",
    "appointment": "Livraison sur rendez-vous",
    "residential": "Livraison chez un particulier",
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
    co2_kg: float = 0.0


def co2_estimate(km: float, weight_kg: float, t=None) -> float:
    """kg CO2e indicatifs = distance x tonnes x facteur par défaut (tariff.json → co2). Jamais présenté comme le calcul réglementaire."""
    t = t or tariff.load()
    return round(km * (weight_kg / 1000.0) * t["co2"]["kg_per_tkm"], 0)


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
    for key, label in (("adr", "adr"), ("temperature", "temperature"), ("urgent", "express"), ("flatbed", "plateau")):
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
    for key, label in (("appointment", "rendez_vous"), ("residential", "particulier")):
        if options.get(key):
            lines[label] = o[key]["eur"]
            subtotal += lines[label]

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
                deliver_by: date = None, pallet_height_cm=None, stackable=False) -> Quote:
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
    if options.get("flatbed") and mode != "FTL":
        raise QuoteError("Le plateau se commande en camion complet : choisissez « Camion complet » ou contactez-nous.")
    if options.get("flatbed") and options.get("temperature"):
        raise QuoteError("Plateau et température dirigée sont incompatibles.")
    if options.get("temperature") and options.get("adr"):
        raise QuoteError("ADR et température dirigée ne sont pas combinables en ligne : contactez-nous.")

    priced_pallets = pallets
    stack_note = None
    if mode == "LTL" and pallet_height_cm is not None:
        if isinstance(pallet_height_cm, bool) or not isinstance(pallet_height_cm, (int, float)) or not 20 <= pallet_height_cm <= 300:
            raise QuoteError("Hauteur de palette invalide (20 à 300 cm).")
        if pallet_height_cm > 220:
            raise QuoteError("Palette de plus de 2,20 m : hors gabarit standard, contactez-nous pour un devis sur mesure.")
        if stackable and pallet_height_cm <= 120:
            priced_pallets = max(1, -(-pallets // 2))
            stack_note = "Palettes gerbables de 1,20 m maximum : deux palettes par emplacement (à confirmer au chargement)."
    est = estimate_cost(mode, origin, destination, priced_pallets, weight_kg, options, t)
    if stack_note:
        est["warnings"].append(stack_note)
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
        earliest_delivery=earliest, co2_kg=co2_estimate(km, float(weight_kg), t))


def indicative(kind, origin, destination, pallets, weight_kg, pickup=None):
    """ESTIMATION non réservable pour le lot partiel (PTL) et le combiné rail-route (IM). Hypothèses : tariff.json → « indicative »."""
    t = tariff.load()
    ind = t["indicative"]
    if kind not in ("PTL", "IM"):
        raise QuoteError("Type d'estimation invalide.")
    if not geo.known(origin) or not geo.known(destination) or origin == destination:
        raise QuoteError("Départ et arrivée invalides.")
    served = {c for c in t["country_cost_index"] if len(c) == 2}
    if geo.country(origin) not in served or geo.country(destination) not in served:
        raise QuoteError("Pays non desservi pour l'instant.")
    if isinstance(weight_kg, bool) or not isinstance(weight_kg, (int, float)) or not 1 <= weight_kg <= FTL_MAX_KG:
        raise QuoteError(f"Poids invalide (1 à {FTL_MAX_KG} kg).")
    km = routing.distance(origin, destination)[0]
    ftl = _ftl_base(t, km, _country_factor(t, origin, destination))
    unc = ind["uncertainty_ptl"] if kind == "PTL" else ind["uncertainty_im"]
    notes = ["Estimation indicative non réservable en ligne : un devis ferme vous est envoyé après étude."]
    if kind == "PTL":
        if isinstance(pallets, bool) or not isinstance(pallets, int) or not 1 <= pallets <= MAX_PALLETS:
            raise QuoteError("Nombre de palettes invalide (1 à 33).")
        share = max(pallets * ind["ldm_per_pallet"] / ind["trailer_ldm"], weight_kg / FTL_MAX_KG)
        mid = ftl * min(ind["ptl_max_share"], max(ind["ptl_min_share"], share * ind["ptl_factor"]))
        transit = calendar_fr.transit_days(km)
    else:
        if km < ind["im_min_km"]:
            raise QuoteError(f"Le combiné rail-route n'est pertinent qu'à partir de {ind['im_min_km']} km : choisissez le camion complet.")
        mid = ftl * ind["im_factor"] + ind["im_terminal_eur"]
        transit = calendar_fr.transit_days(km) + ind["im_extra_transit_days"]
        notes.append("Délais plus longs et horaires de trains : à confirmer. Le combiné n'est pas toujours moins cher que la route.")
    m = t["margin"]
    sell = lambda cost: round(cost * (1 + m["target"] + m["risk_premium_share"] * unc), 2)  # noqa: E731
    return {"kind": kind, "origin": origin, "destination": destination, "distance_km": km, "transit_days": transit,
            "price_ht_low": sell(mid * (1 - unc)), "price_ht_mid": sell(mid), "price_ht_high": sell(mid * (1 + unc)),
            "uncertainty": unc, "bookable": False, "confidence": ind["confidence"], "notes": notes}
