"""Géographie : base de villes et distance routière estimée.

Approximation : distance à vol d'oiseau (haversine) x coefficient routier.
En production, remplacer par un service d'itinéraire (OSRM auto-hébergé, HERE, Google Routes).
"""
import math
import re

from . import places
from .places import PlaceError

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
    "Valence (Espagne)": ("ES", 39.4699, -0.3763),
    "Valence (Drôme)": ("FR", 44.9334, 4.8924),
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
    # --- France (extension) ---
    "Angers": ("FR", 47.4784, -0.5632),
    "Tours": ("FR", 47.3941, 0.6848),
    "Poitiers": ("FR", 46.5802, 0.3404),
    "Limoges": ("FR", 45.8336, 1.2611),
    "Caen": ("FR", 49.1829, -0.3707),
    "Reims": ("FR", 49.2583, 4.0317),
    "Amiens": ("FR", 49.8941, 2.2957),
    "Nancy": ("FR", 48.6921, 6.1844),
    "Mulhouse": ("FR", 47.7508, 7.3359),
    "Besançon": ("FR", 47.2378, 6.0241),
    "Avignon": ("FR", 43.9493, 4.8055),
    "Nîmes": ("FR", 43.8367, 4.3601),
    "Perpignan": ("FR", 42.6887, 2.8948),
    "Toulon": ("FR", 43.1242, 5.9280),
    "Brest": ("FR", 48.3904, -4.4861),
    "La Rochelle": ("FR", 46.1603, -1.1511),
    "Pau": ("FR", 43.2951, -0.3708),
    "Annecy": ("FR", 45.8992, 6.1294),
    "Chambéry": ("FR", 45.5646, 5.9178),
    "Le Mans": ("FR", 48.0061, 0.1996),
    "Dunkerque": ("FR", 51.0343, 2.3768),
    "Valenciennes": ("FR", 50.3590, 3.5233),
    "Roanne": ("FR", 46.0345, 4.0680),
    "Monistrol-sur-Loire": ("FR", 45.2955, 4.1741),
    "Vichy": ("FR", 46.1271, 3.4260),
    "Bourges": ("FR", 47.0810, 2.3988),
    "Troyes": ("FR", 48.2973, 4.0744),
    "Cherbourg": ("FR", 49.6337, -1.6221),
    "Saint-Nazaire": ("FR", 47.2734, -2.2138),
    "Lorient": ("FR", 47.7482, -3.3702),
    "Vannes": ("FR", 47.6582, -2.7608),
    "Beauvais": ("FR", 49.4295, 2.0807),
    "Aurillac": ("FR", 44.9253, 2.4393),
    # --- Europe (extension) ---
    "Séville": ("ES", 37.3891, -5.9845),
    "Saragosse": ("ES", 41.6488, -0.8891),
    "Bilbao": ("ES", 43.2630, -2.9350),
    "Porto": ("PT", 41.1579, -8.6291),
    "Gênes": ("IT", 44.4056, 8.9463),
    "Bologne": ("IT", 44.4949, 11.3426),
    "Florence": ("IT", 43.7696, 11.2558),
    "Vérone": ("IT", 45.4384, 10.9916),
    "Naples": ("IT", 40.8518, 14.2681),
    "Gand": ("BE", 51.0543, 3.7174),
    "Liège": ("BE", 50.6326, 5.5797),
    "Charleroi": ("BE", 50.4108, 4.4446),
    "Utrecht": ("NL", 52.0907, 5.1214),
    "Eindhoven": ("NL", 51.4416, 5.4697),
    "Düsseldorf": ("DE", 51.2277, 6.7735),
    "Dortmund": ("DE", 51.5136, 7.4653),
    "Duisbourg": ("DE", 51.4344, 6.7623),
    "Berlin": ("DE", 52.5200, 13.4050),
    "Nuremberg": ("DE", 49.4521, 11.0767),
    "Hanovre": ("DE", 52.3759, 9.7320),
    "Leipzig": ("DE", 51.3397, 12.3731),
    "Brême": ("DE", 53.0793, 8.8017),
    "Mannheim": ("DE", 49.4875, 8.4660),
    "Karlsruhe": ("DE", 49.0069, 8.4037),
    "Bâle": ("CH", 47.5596, 7.5886),
    "Berne": ("CH", 46.9480, 7.4474),
    "Lausanne": ("CH", 46.5197, 6.6323),
    "Salzbourg": ("AT", 47.8095, 13.0550),
    "Cracovie": ("PL", 50.0647, 19.9450),
    "Poznań": ("PL", 52.4064, 16.9252),
    "Wrocław": ("PL", 51.1079, 17.0385),
    "Gdańsk": ("PL", 54.3520, 18.6466),
}


# Alias usuels (noms locaux / anglais, sans accents ni casse) -> nom de la base. Un alias ambigu renvoie une liste.
ALIASES = {
    "koln": "Cologne", "milano": "Milan", "munchen": "Munich", "brussels": "Bruxelles", "bruxelles": "Bruxelles",
    "geneva": "Genève", "geneve": "Genève", "vienna": "Vienne", "wien": "Vienne", "warsaw": "Varsovie", "warszawa": "Varsovie",
    "lisbon": "Lisbonne", "lisboa": "Lisbonne", "barcelona": "Barcelone", "frankfurt": "Francfort", "hamburg": "Hambourg",
    "torino": "Turin", "roma": "Rome", "antwerp": "Anvers", "antwerpen": "Anvers", "zurich": "Zurich", "sevilla": "Séville",
    "zaragoza": "Saragosse", "genoa": "Gênes", "genova": "Gênes", "bologna": "Bologne", "florence": "Florence", "firenze": "Florence",
    "verona": "Vérone", "naples": "Naples", "napoli": "Naples", "gent": "Gand", "ghent": "Gand", "liege": "Liège",
    "dusseldorf": "Düsseldorf", "nuremberg": "Nuremberg", "nurnberg": "Nuremberg", "hannover": "Hanovre", "hanover": "Hanovre",
    "bremen": "Brême", "basel": "Bâle", "bale": "Bâle", "bern": "Berne", "salzburg": "Salzbourg", "krakow": "Cracovie",
    "cracow": "Cracovie", "poznan": "Poznań", "wroclaw": "Wrocław", "gdansk": "Gdańsk", "duisburg": "Duisbourg",
    "saint etienne": "Saint-Etienne", "st etienne": "Saint-Etienne", "st-etienne": "Saint-Etienne",
    "valence": ["Valence (Drôme)", "Valence (Espagne)"],
    "clermont": "Clermont-Ferrand", "le puy": "Le Puy-en-Velay", "monistrol": "Monistrol-sur-Loire",
}


def coords(label: str):
    """(pays, latitude, longitude) d'un libellé : grandes villes intégrées, sinon référentiel complet (places.py)."""
    if label in CITIES:
        return CITIES[label]
    p = places.get(label)
    if not p:
        raise KeyError(label)
    return (p["country"], p["lat"], p["lon"])


def known(city: str) -> bool:
    return city in CITIES or places.get(city) is not None


def country(city: str) -> str:
    return coords(city)[0]


def _seed_by_norm():
    out = {}
    for c in CITIES:
        out.setdefault(places.normalize(c), c)
    for alias, target in ALIASES.items():
        if isinstance(target, str):
            out.setdefault(places.normalize(alias), target)
    return out


def suggest(q: str, limit: int = 10):
    """Propositions pour la saisie semi-automatique : grandes villes d'abord, puis tout le référentiel."""
    qn = places.normalize(q)
    if len(qn) < 2:
        return []
    out, seen = [], set()
    for name in sorted(CITIES):
        if places.normalize(name).startswith(qn) and name not in seen:
            out.append({"label": name, "country": CITIES[name][0]})
            seen.add(name)
    seed_norms = _seed_by_norm()
    for r in places.search(q, limit * 2):
        if r["label"] in seen or places.normalize(r["label"].split(" (")[0]) in seed_norms:
            continue                        # la grande ville intégrée a déjà été proposée sous son nom habituel
        out.append({"label": r["label"], "country": r["country"], "postal": r["postal"]})
        seen.add(r["label"])
    return out[:limit]


def canonical(text: str) -> str:
    """Libellé valide à partir d'une saisie libre ; lève PlaceError (avec propositions) si introuvable ou ambigu."""
    text = (text or "").strip()
    if known(text):
        return text
    n = places.normalize(text)
    amb = ALIASES.get(n)
    if isinstance(amb, list):
        raise PlaceError(f"« {text} » est ambigu : précisez.", amb)
    seed = _seed_by_norm().get(n)
    if seed:
        return seed
    m = re.search(r"\b(\d{5})\b", n)
    name_part = re.sub(r"\b\d{5}\b", "", n).strip()
    cands = places.by_postal(m.group(1)) if m else []
    if cands and name_part:
        narrowed = [c for c in cands if places.normalize(c["label"].split(" (")[0]).startswith(name_part)]
        cands = narrowed or cands
    if not cands:
        cands = places.by_name(name_part or n)
    if len(cands) == 1:
        return cands[0]["label"]
    if len(cands) > 1:
        raise PlaceError(f"Plusieurs communes correspondent à « {text} » : choisissez-en une (ou ajoutez le code postal).",
                         [c["label"] for c in cands[:8]])
    sugg = [s["label"] for s in suggest(text, 5)]
    raise PlaceError(f"Lieu « {text} » introuvable." + ("" if places.available() else " Le référentiel complet des communes n'est pas installé (voir README)."), sugg)


def haversine_km(a: str, b: str) -> float:
    _, la1, lo1 = coords(a)
    _, la2, lo2 = coords(b)
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
