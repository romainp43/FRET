"""Géographie : villes, codes postaux français et distance routière estimée.

Un « lieu » est soit un nom de ville de CITIES, soit un code postal français à 5 chiffres
(data/codes_postaux.csv, construit par tools/build_codes_postaux.py).

Approximation : distance à vol d'oiseau (haversine) x coefficient routier.
En production, remplacer par un service d'itinéraire (OSRM auto-hébergé, HERE, Google Routes).
"""
import csv
import math
import os
import re

# nom: (pays, latitude, longitude)
CITIES = {
    "Paris": ("FR", 48.8566, 2.3522),
    "Lyon": ("FR", 45.7640, 4.8357),
    "Marseille": ("FR", 43.2965, 5.3698),
    "Toulouse": ("FR", 43.6047, 1.4442),
    "Bordeaux": ("FR", 44.8378, -0.5792),
    "Nantes": ("FR", 47.2184, -1.5536),
    "Lille": ("FR", 50.6292, 3.0573),
    "Strasbourg": ("FR", 48.5734, 7.7521),
    "Rennes": ("FR", 48.1173, -1.6778),
    "Montpellier": ("FR", 43.6108, 3.8767),
    "Nice": ("FR", 43.7102, 7.2620),
    "Grenoble": ("FR", 45.1885, 5.7245),
    "Dijon": ("FR", 47.3220, 5.0415),
    "Clermont-Ferrand": ("FR", 45.7772, 3.0870),
    "Saint-Etienne": ("FR", 45.4397, 4.3872),
    "Le Puy-en-Velay": ("FR", 45.0430, 3.8850),
    "Rouen": ("FR", 49.4432, 1.0993),
    "Le Havre": ("FR", 49.4944, 0.1079),
    "Metz": ("FR", 49.1193, 6.1757),
    "Orléans": ("FR", 47.9029, 1.9093),
    "Madrid": ("ES", 40.4168, -3.7038),
    "Barcelone": ("ES", 41.3874, 2.1686),
    "Valence": ("ES", 39.4699, -0.3763),
    "Lisbonne": ("PT", 38.7223, -9.1393),
    "Milan": ("IT", 45.4642, 9.1900),
    "Turin": ("IT", 45.0703, 7.6869),
    "Rome": ("IT", 41.9028, 12.4964),
    "Bruxelles": ("BE", 50.8503, 4.3517),
    "Anvers": ("BE", 51.2194, 4.4025),
    "Amsterdam": ("NL", 52.3676, 4.9041),
    "Rotterdam": ("NL", 51.9244, 4.4777),
    "Francfort": ("DE", 50.1109, 8.6821),
    "Munich": ("DE", 48.1351, 11.5820),
    "Hambourg": ("DE", 53.5511, 9.9937),
    "Cologne": ("DE", 50.9375, 6.9603),
    "Stuttgart": ("DE", 48.7758, 9.1829),
    "Zurich": ("CH", 47.3769, 8.5417),
    "Genève": ("CH", 46.2044, 6.1432),
    "Luxembourg": ("LU", 49.6116, 6.1319),
    "Varsovie": ("PL", 52.2297, 21.0122),
    "Vienne": ("AT", 48.2082, 16.3738),
}


_CP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "codes_postaux.csv")
_CP_RE = re.compile(r"^\d{5}$")
POSTCODES = {}          # code postal -> (commune, latitude, longitude)


def _load_postcodes():
    try:
        with open(_CP_FILE, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                POSTCODES[r["code_postal"]] = (r["commune"], float(r["lat"]), float(r["lon"]))
    except OSError:
        pass                # sans le fichier, seuls les noms de villes sont acceptés


_load_postcodes()


def locate(place: str):
    """(pays, latitude, longitude) d'un lieu connu, sinon None."""
    if place in CITIES:
        return CITIES[place]
    if isinstance(place, str) and _CP_RE.match(place) and place in POSTCODES:
        _, lat, lon = POSTCODES[place]
        return ("FR", lat, lon)
    return None


def known(place: str) -> bool:
    return locate(place) is not None


def label(place: str) -> str:
    """Libellé lisible : « 43290 Montfaucon-en-Velay » pour un code postal, le nom pour une ville."""
    if place in POSTCODES and place not in CITIES:
        return f"{place} {POSTCODES[place][0]}"
    return place


def department(place: str) -> str:
    """Département (2 caractères) d'un code postal français, pays pour une ville étrangère, '' sinon."""
    if place in POSTCODES and place not in CITIES:
        return "2A" if place[:3] in ("200", "201") else "2B" if place[:2] == "20" else place[:2]
    loc = CITIES.get(place)
    return "" if not loc else (loc[0] if loc[0] != "FR" else "")


def country(place: str) -> str:
    return locate(place)[0]


def haversine_km(a: str, b: str) -> float:
    _, la1, lo1 = locate(a)
    _, la2, lo2 = locate(b)
    r = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi = p2 - p1
    dl = math.radians(lo2 - lo1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def road_km(a: str, b: str) -> float:
    """Distance routière estimée (coefficient 1,20 national, 1,25 international)."""
    if a == b:
        return 0.0
    coef = 1.20 if country(a) == country(b) else 1.25
    return round(haversine_km(a, b) * coef, 1)


def transit_days(km: float, urgent: bool = False) -> int:
    """Délai estimé : ~600 km/jour de route, +1 jour de chargement/livraison."""
    days = math.ceil(km / 600.0) + (0 if urgent else 1)
    return max(1, days)
