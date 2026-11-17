"""Chargement et validation du barème (config/tariff.json). Le barème est de la DONNÉE, pas du code :
on le met à jour chaque mois sans toucher à l'application, et chaque devis enregistre la version utilisée."""
import json
import os
from datetime import date

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "tariff.json")
STALE_DAYS = 45
_cache = {}


class TariffError(ValueError):
    pass


def validate(t: dict) -> dict:
    try:
        idx = t["market_index"]["eur_per_km"]
        if not 0.8 <= idx <= 4.0:
            raise TariffError("market_index.eur_per_km hors plage plausible (0,8 à 4,0).")
        bands = t["ftl"]["distance_band_multipliers"]
        maxes = [b["max_km"] for b in bands]
        if maxes[-1] is not None or any(m is None for m in maxes[:-1]):
            raise TariffError("La dernière tranche FTL doit avoir max_km = null (et seulement elle).")
        if maxes[:-1] != sorted(maxes[:-1]):
            raise TariffError("Les tranches de distance FTL doivent être croissantes.")
        if any(not 0.3 <= b["mult"] <= 3 for b in bands):
            raise TariffError("Multiplicateur de tranche hors plage.")
        for c, v in t["country_cost_index"].items():
            if len(c) == 2 and not 0.4 <= v <= 3:
                raise TariffError(f"Indice pays {c} hors plage.")
        m = t["margin"]
        if not 0 < m["minimum"] <= m["target"] < 0.5:
            raise TariffError("Marges incohérentes (0 < minimum <= cible < 50 %).")
        if t["ltl"]["kg_per_euro_pallet"] <= 0:
            raise TariffError("kg_per_euro_pallet invalide.")
        b = t["bottom_up"]
        for k in ("driver_eur_per_h", "vehicle_fixed_eur_per_h", "avg_speed_kmh", "fuel_l_per_100km", "diesel_eur_per_l_net"):
            if not b[k] > 0:
                raise TariffError(f"bottom_up.{k} doit être > 0.")
        if not 0 < b["max_divergence"] < 1 or not 0 <= t["decision"]["late_cost_ratio"] <= 3:
            raise TariffError("Paramètres bottom_up/decision hors plage.")
        date.fromisoformat(t["version"])
        date.fromisoformat(t["market_index"]["as_of"])
    except KeyError as e:
        raise TariffError(f"Paramètre manquant dans le barème : {e}")
    return t


def load(path=None) -> dict:
    path = path or os.environ.get("FRETRAU_TARIFF", DEFAULT_PATH)
    mtime = os.path.getmtime(path)
    if path not in _cache or _cache[path][0] != mtime:          # rechargement à chaud si le fichier change
        with open(path, encoding="utf-8") as f:
            _cache[path] = (mtime, validate(json.load(f)))
    return _cache[path][1]


def freshness_warnings(t: dict = None, today: date = None) -> list:
    t = t or load()
    today = today or date.today()
    out = []
    age = (today - date.fromisoformat(t["market_index"]["as_of"])).days
    if age > STALE_DAYS:
        out.append(f"Indice marché daté de {age} jours (> {STALE_DAYS}) : mettez à jour config/tariff.json.")
    f = t["fuel"]
    if f.get("index_now") is None:
        out.append("Indexation gazole inactive : renseignez fuel.index_now (dernier indice CNR gazole professionnel).")
    return out
