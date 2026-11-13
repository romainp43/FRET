#!/usr/bin/env python3
"""Construit data/transporteurs.csv à partir de l'Annuaire des Entreprises (données publiques, Licence Ouverte).

API : https://recherche-entreprises.api.gouv.fr (sans clé). Codes NAF retenus :
  49.41A transports routiers de fret interurbains, 49.41B de proximité, 49.41C location de camions avec chauffeur.

Règles de sélection (à ne pas assouplir sans avis juridique) :
  - établissement actif situé dans le département interrogé ;
  - personnes morales uniquement (pas d'entrepreneurs individuels : données personnelles) ;
  - diffusion publique complète ET pas d'opposition à l'utilisation commerciale des données.

Ces entreprises sont des PROSPECTS : aucune n'est « vérifiée ». Avant toute affectation, il faut contrôler
licence, assurance, Kbis et attestation de vigilance (voir docs/DEMARRAGE.md).

Usage : python3 tools/import_transporteurs.py [code_postal_base]   (défaut 43290, Raucoules)
"""
import csv
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://recherche-entreprises.api.gouv.fr/search"
NAF = ["49.41A", "49.41B", "49.41C"]
DEPTS = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]


def base_point(cp):
    with open(os.path.join(ROOT, "data", "codes_postaux.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["code_postal"] == cp:
                return float(r["lat"]), float(r["lon"])
    raise SystemExit("Code postal de base inconnu : " + cp)


def km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "import-transporteurs/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except Exception as e:                       # 429 ou coupure réseau : on patiente puis on réessaie
            time.sleep(2 + attempt * 3)
            last = e
    raise last


def main():
    base_cp = sys.argv[1] if len(sys.argv) > 1 else "43290"
    base = base_point(base_cp)
    rows, skipped = {}, {"individuel": 0, "non_diffusible": 0, "opposition": 0}
    def one(dept):
        for naf in NAF:
            page = 1
            while True:
                d = get({"activite_principale": naf, "departement": dept, "etat_administratif": "A",
                         "per_page": 25, "page": page})
                for e in d.get("results", []):
                    if str(e.get("nature_juridique", ""))[:1] == "1":
                        skipped["individuel"] += 1
                        continue
                    if e.get("statut_diffusion") != "O":
                        skipped["non_diffusible"] += 1
                        continue
                    if e.get("opposition_diffusion_commerciale"):
                        skipped["opposition"] += 1
                        continue
                    for s in e.get("matching_etablissements") or []:
                        if s.get("etat_administratif") != "A" or not s.get("latitude") or s["siret"] in rows:
                            continue
                        if s.get("statut_diffusion_etablissement") not in (None, "O"):
                            continue
                        pt = (float(s["latitude"]), float(s["longitude"]))
                        ens = (s.get("liste_enseignes") or [None])[0]
                        rows[s["siret"]] = {
                            "siret": s["siret"], "siren": e["siren"], "nom": e.get("nom_complet") or "",
                            "enseigne": ens or "", "naf": s.get("activite_principale") or naf,
                            "adresse": s.get("adresse") or "", "code_postal": s.get("code_postal") or "",
                            "commune": s.get("libelle_commune") or "", "departement": dept,
                            "lat": round(pt[0], 5), "lon": round(pt[1], 5),
                            "effectif": s.get("tranche_effectif_salarie") or "",
                            "categorie": e.get("categorie_entreprise") or "",
                            "creation": s.get("date_creation") or "", "siege": "1" if s.get("est_siege") else "0",
                            "km_base": round(km(base, pt), 1),
                        }
                if page >= min(d.get("total_pages", 1), 400):
                    break
                page += 1
                time.sleep(0.16)
        print(dept, len(rows), flush=True)

    with ThreadPoolExecutor(max_workers=4) as pool:      # ~6 requêtes/s au total (limite de l'API : 7/s)
        list(pool.map(one, DEPTS))
    out = os.path.join(ROOT, "data", "transporteurs.csv")
    ordered = sorted(rows.values(), key=lambda r: r["km_base"])
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ordered[0]))
        w.writeheader()
        w.writerows(ordered)
    print(len(ordered), "établissements ->", out, "| écartés :", skipped)


if __name__ == "__main__":
    main()
