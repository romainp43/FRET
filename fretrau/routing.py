"""Distance routière : OSRM si configuré (FRETRAU_OSRM_URL, ex. votre instance auto-hébergée), sinon estimation.

L'estimation (haversine x 1,20 national / 1,25 international) donne en pratique +/- 10 % sur les grands axes
(vérifié sur Paris-Lyon, Paris-Marseille, Paris-Toulouse, Paris-Madrid). Pour un devis réel, utilisez OSRM/HERE.
Un résultat OSRM aberrant (hors 0,7x à 1,8x de la distance à vol d'oiseau) est ignoré : on retombe sur l'estimation.
"""
import json
import os
import threading
import urllib.request

from . import geo

_cache = {}
_lock = threading.Lock()


def _osrm(a: str, b: str):
    base = os.environ.get("FRETRAU_OSRM_URL")
    if not base:
        return None
    _, la1, lo1 = geo.coords(a)
    _, la2, lo2 = geo.coords(b)
    url = f"{base.rstrip('/')}/route/v1/driving/{lo1},{la1};{lo2},{la2}?overview=false"
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            data = json.loads(r.read())
        km = float(data["routes"][0]["distance"]) / 1000.0
    except Exception:
        return None
    straight = geo.haversine_km(a, b)
    return round(km, 1) if 0.7 * straight <= km <= 1.8 * straight else None


def distance(a: str, b: str):
    """Retourne (km, source) avec source = 'osrm' ou 'estimation'."""
    key = tuple(sorted((a, b)))
    with _lock:
        if key in _cache:
            return _cache[key]
    km = _osrm(a, b)
    res = (km, "osrm") if km is not None else (geo.road_km(a, b), "estimation")
    with _lock:
        _cache[key] = res
    return res
