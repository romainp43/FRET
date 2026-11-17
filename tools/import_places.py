#!/usr/bin/env python3
"""Installe le référentiel COMPLET des lieux (toutes les communes de France + localités d'Europe).

  python3 tools/import_places.py                    # télécharge les sources officielles (accès Internet requis)
  python3 tools/import_places.py --fr communes.json --geonames cities500.zip      # ou depuis des fichiers locaux

Sources :
  - France : API Découpage administratif (geo.api.gouv.fr) — toutes les communes, codes postaux, centre, population ;
  - Europe : GeoNames « cities500 » (localités de 500 habitants et plus), licence CC-BY 4.0 (citer GeoNames).
Seuls les pays pour lesquels le barème FRETRAU a un indice de coût sont importés. Ne sont PAS importés (pas de route continue
depuis le continent, traversée maritime non modélisée) : Corse, outre-mer, Sicile, Sardaigne, Baléares, Canaries, Madère, Açores.
Le fichier produit (data/places.db) est remplacé atomiquement : le serveur peut tourner pendant l'import.
"""
import argparse
import csv
import io
import json
import os
import sqlite3
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import places, tariff  # noqa: E402

FR_URL = "https://geo.api.gouv.fr/communes?fields=nom,code,codesPostaux,centre,population&format=json"
GEONAMES_URL = "https://download.geonames.org/export/dump/cities500.zip"
# (lat_min, lat_max, lon_min, lon_max) des territoires non desservis par route continue
ISLANDS = {
    "Sicile": (36.6, 38.4, 12.3, 15.7), "Sardaigne": (38.8, 41.3, 8.1, 9.9), "Baléares": (38.6, 40.2, 1.1, 4.4),
    "Canaries": (27.4, 29.6, -18.4, -13.2), "Madère": (32.3, 33.2, -17.4, -16.2), "Açores": (36.8, 39.8, -31.5, -24.9),
}


def is_island(lat, lon):
    return any(a <= lat <= b and c <= lon <= d for a, b, c, d in ISLANDS.values())


def read_source(src):
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src, headers={"User-Agent": "FRETRAU-import/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    with open(src, "rb") as f:
        return f.read()


def french_rows(data: bytes):
    skipped = 0
    for c in json.loads(data):
        code = str(c.get("code", ""))
        centre = (c.get("centre") or {}).get("coordinates")
        if not centre or code.startswith(("97", "98", "2A", "2B")):
            skipped += 1
            continue
        yield {"name": c["nom"], "country": "FR", "postal": c.get("codesPostaux") or [], "lat": centre[1], "lon": centre[0],
               "pop": int(c.get("population") or 0)}, skipped


def geonames_rows(data: bytes, countries):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if n.endswith(".txt") and "readme" not in n.lower())
        text = io.TextIOWrapper(z.open(name), encoding="utf-8")
        for r in csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(r) < 15:
                continue
            cc = r[8]
            if cc not in countries or cc == "FR":                 # la France vient des communes officielles
                continue
            lat, lon = float(r[4]), float(r[5])
            if is_island(lat, lon):
                continue
            yield {"name": r[1], "country": cc, "postal": [], "lat": lat, "lon": lon, "pop": int(r[14] or 0), "gid": r[0]}


def build(db_path, fr_data=None, gn_data=None, countries=None):
    countries = countries or {c for c in tariff.load()["country_cost_index"] if len(c) == 2}
    rows = []
    if fr_data is not None:
        rows += [r for r, _ in french_rows(fr_data)]
    if gn_data is not None:
        rows += list(geonames_rows(gn_data, countries))
    # libellé unique : nom si unique dans le pays, sinon « nom (code postal) » / « nom (PAYS #id) »
    from collections import Counter
    freq = Counter((places.normalize(r["name"]), r["country"]) for r in rows)
    used = set()
    tmp = db_path + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript(places.SCHEMA)
    for i, r in enumerate(rows, 1):
        key = (places.normalize(r["name"]), r["country"])
        if r["country"] == "FR":
            label = r["name"] if freq[key] == 1 else f"{r['name']} ({r['postal'][0] if r['postal'] else i})"
        else:
            label = f"{r['name']} ({r['country']})" if freq[key] == 1 else f"{r['name']} ({r['country']} #{r.get('gid', i)})"
        while label in used:
            label += f" #{i}"
        used.add(label)
        con.execute("INSERT INTO places(id,label,name,norm,country,postal,lat,lon,pop) VALUES (?,?,?,?,?,?,?,?,?)",
                    (i, label, r["name"], places.normalize(r["name"]), r["country"], " ".join(r["postal"]), r["lat"], r["lon"], r["pop"]))
        for pc in r["postal"]:
            con.execute("INSERT INTO place_postal(postal, place_id) VALUES (?,?)", (pc, i))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('built_at', datetime('now'))")
    con.execute("INSERT OR REPLACE INTO meta VALUES ('sources', 'geo.api.gouv.fr ; GeoNames cities500 (CC-BY 4.0)')")
    con.commit()
    con.close()
    os.replace(tmp, db_path)
    places.reset()
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=places.db_path())
    ap.add_argument("--fr", default=FR_URL)
    ap.add_argument("--geonames", default=GEONAMES_URL)
    ap.add_argument("--no-europe", action="store_true")
    a = ap.parse_args()
    print("Lecture des communes françaises…")
    fr = read_source(a.fr)
    gn = None if a.no_europe else read_source(a.geonames)
    n = build(a.db, fr, gn)
    if n < 30000 and a.fr == FR_URL:
        print(f"ATTENTION : seulement {n} lieux importés, la France seule en compte ~35 000. Vérifiez la source.")
    print(f"{n} lieux installés dans {a.db}")


if __name__ == "__main__":
    main()
