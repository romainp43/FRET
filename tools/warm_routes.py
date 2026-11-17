#!/usr/bin/env python3
"""Précalcule les distances routières (profil poids lourd) entre les villes principales, dans le respect du quota gratuit.

  set FRETRAU_ORS_KEY=votre_cle      (Windows ; sous Linux/Mac : export FRETRAU_ORS_KEY=...)
  py tools/warm_routes.py [nombre_max_de_trajets]     (défaut 1500 : sous la limite de 2 000 par jour)

Relançable : les trajets déjà enregistrés (data/routes_osrm.json) sont ignorés, on reprend là où on s'était arrêté.
"""
import itertools
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import geo, routing  # noqa: E402


def main():
    if not os.environ.get("FRETRAU_ORS_KEY"):
        sys.exit("Définissez d'abord FRETRAU_ORS_KEY (clé gratuite openrouteservice).")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    done = calls = 0
    for a, b in itertools.combinations(sorted(geo.CITIES), 2):
        key = tuple(sorted((a, b)))
        if key in routing._cache:
            continue
        if calls >= limit:
            break
        km, src = routing.distance(a, b)
        calls += 1
        if src == "ors":
            done += 1
        else:
            print(f"  ignoré {a} → {b} (service indisponible ou quota atteint)")
            if calls > 20 and done == 0:
                sys.exit("Aucun résultat du service : vérifiez la clé et la connexion.")
        time.sleep(1.8)                      # ~33 requêtes/minute, sous la limite de 40
    print(f"{done} trajets enregistrés ; relancez demain pour continuer.")


if __name__ == "__main__":
    main()
