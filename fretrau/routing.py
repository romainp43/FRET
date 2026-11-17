"""Distance routière, par ordre de préférence :
  1. openrouteservice, profil POIDS LOURD (FRETRAU_ORS_KEY : clé gratuite, 2 000 itinéraires/jour et 40/minute) ;
  2. OSRM si configuré (FRETRAU_OSRM_URL, ex. votre instance auto-hébergée) ;
  3. estimation (haversine x coefficient).
Chaque couple de villes n'est demandé qu'une fois (cache mémoire + disque). Les quotas sont respectés côté FRETRAU :
au-delà, on retombe sur l'estimation au lieu d'insister.

L'estimation (haversine x 1,20 national / 1,25 international) donne en pratique +/- 10 % sur les grands axes
(vérifié sur Paris-Lyon, Paris-Marseille, Paris-Toulouse, Paris-Madrid). Pour un devis réel, utilisez OSRM/HERE.
Un résultat OSRM aberrant (hors 0,7x à 1,8x de la distance à vol d'oiseau) est ignoré : on retombe sur l'estimation.
"""
import json
import os
import threading
import time
import urllib.request

from . import geo

_cache = {}
_lock = threading.Lock()
CACHE_FILE = os.environ.get("FRETRAU_ROUTE_CACHE", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "routes_osrm.json"))


def _load_disk():
    """Distances OSRM déjà obtenues (une ligne par couple de villes) : évite de rappeler le service à chaque démarrage."""
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                a, b = k.split("|")
                _cache[(a, b)] = (float(v), "route")
    except (OSError, ValueError, TypeError):
        pass


def _save_disk():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        data = {"|".join(k): v[0] for k, v in _cache.items() if v[1] in ("osrm", "ors", "route")}
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


_load_disk()


ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv"
ORS_PER_MIN, ORS_PER_DAY = 35, 1900          # marges sous les limites gratuites (40/min, 2 000/jour)
_ors_hits = []


def _ors_allowed() -> bool:
    now = time.time()
    with _lock:
        _ors_hits[:] = [t for t in _ors_hits if now - t < 86400]
        if len(_ors_hits) >= ORS_PER_DAY or sum(1 for t in _ors_hits if now - t < 60) >= ORS_PER_MIN:
            return False
        _ors_hits.append(now)
        return True


def _ors(a: str, b: str):
    key = os.environ.get("FRETRAU_ORS_KEY")
    if not key or not _ors_allowed():
        return None
    _, la1, lo1 = geo.coords(a)
    _, la2, lo2 = geo.coords(b)
    body = json.dumps({"coordinates": [[lo1, la1], [lo2, la2]], "radiuses": [-1, -1]}).encode()   # -1 : accrocher à la route la plus proche
    req = urllib.request.Request(ORS_URL, data=body, headers={"Authorization": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            km = float(json.loads(r.read())["routes"][0]["summary"]["distance"]) / 1000.0
    except Exception:
        return None
    straight = geo.haversine_km(a, b)
    return round(km, 1) if 0.7 * straight <= km <= 1.8 * straight else None


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
    km = _ors(a, b)
    if km is not None:
        res = (km, "ors")
    else:
        km = _osrm(a, b)
        res = (km, "osrm") if km is not None else (geo.road_km(a, b), "estimation")
    with _lock:
        _cache[key] = res
        if res[1] in ("osrm", "ors"):
            _save_disk()
    return res
