#!/usr/bin/env python3
"""Construit data/codes_postaux.csv (code postal -> commune principale, latitude, longitude).

Source : https://geo.api.gouv.fr/communes?fields=nom,codesPostaux,centre,population&format=json (Licence Ouverte).
Usage : python3 tools/build_codes_postaux.py communes.json
"""
import csv
import json
import os
import sys

src = sys.argv[1]
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "codes_postaux.csv")
acc = {}
for c in json.load(open(src, encoding="utf-8")):
    if not c.get("centre"):
        continue
    lon, lat = c["centre"]["coordinates"]
    pop = max(1, c.get("population") or 1)
    for cp in c.get("codesPostaux", []):
        if cp[:2] in ("97", "98"):          # métropole + Corse uniquement (transport routier)
            continue
        a = acc.setdefault(cp, {"w": 0, "lat": 0.0, "lon": 0.0, "best": (0, "")})
        a["w"] += pop
        a["lat"] += lat * pop
        a["lon"] += lon * pop
        if pop > a["best"][0]:
            a["best"] = (pop, c["nom"])
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["code_postal", "commune", "lat", "lon"])
    for cp in sorted(acc):
        a = acc[cp]
        w.writerow([cp, a["best"][1], round(a["lat"] / a["w"], 4), round(a["lon"] / a["w"], 4)])
print(len(acc), "codes postaux ->", out)
