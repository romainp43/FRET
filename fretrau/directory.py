"""Annuaire des transporteurs réels d'une zone, issu de l'annuaire officiel des entreprises (données Sirene, Licence Ouverte).

Ce que la source donne : nom, SIREN, adresse du siège, position, tranche d'effectif, état (actif/cessé).
Ce qu'elle NE donne PAS : e-mail, téléphone, flotte, licence de transport, assurance, prix. Ces champs se complètent à la main
(ou via la candidature transporteur) ; un transporteur recensé reste « prospect » tant qu'il n'a pas été vérifié (vetting).
"""
import json
import urllib.parse
import urllib.request

API = "https://recherche-entreprises.api.gouv.fr/search"
NAF_FREIGHT = ("49.41A", "49.41B")           # A : transport routier de fret interurbain ; B : de proximité
PER_PAGE = 25
MAX_PAGES = 400                               # l'API limite à 10 000 résultats par recherche


def parse_company(r: dict):
    """Un résultat de l'API → ligne d'annuaire, ou None si inexploitable (cessée, sans siren, hors France)."""
    siren = str(r.get("siren") or "")
    s = r.get("siege") or {}
    if len(siren) != 9 or not siren.isdigit() or r.get("etat_administratif") != "A":
        return None
    lat, lon = s.get("latitude"), s.get("longitude")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        lat = lon = None
    return {"siren": siren, "name": (r.get("nom_complet") or "")[:120], "city": (s.get("libelle_commune") or "")[:80],
            "postcode": (s.get("code_postal") or "")[:5], "dept": (s.get("departement") or "")[:3], "lat": lat, "lon": lon,
            "naf": (r.get("activite_principale") or s.get("activite_principale") or "")[:8], "size": str(r.get("tranche_effectif_salarie") or "")[:3]}


def fetch(dept: str, naf: str, opener=urllib.request.urlopen, max_pages=MAX_PAGES):
    """Itère sur toutes les entreprises actives d'un département pour un code NAF."""
    for page in range(1, max_pages + 1):
        q = urllib.parse.urlencode({"activite_principale": naf, "departement": dept, "etat_administratif": "A", "per_page": PER_PAGE, "page": page})
        req = urllib.request.Request(f"{API}?{q}", headers={"Accept": "application/json", "User-Agent": "FRETRAU-recensement"})
        with opener(req, timeout=20) as r:
            data = json.loads(r.read())
        results = data.get("results") or []
        for res in results:
            row = parse_company(res)
            if row:
                yield row
        if len(results) < PER_PAGE or page >= (data.get("total_pages") or 1):
            return


def import_zone(db, depts, nafs=NAF_FREIGHT, opener=urllib.request.urlopen, sleep=None):
    n = 0
    for d in depts:
        for naf in nafs:
            for row in fetch(d, naf, opener):
                n += db.upsert_directory(row)
            if sleep:
                sleep(0.2)                    # l'API publique est limitée en débit : on reste poli
    return n
