#!/usr/bin/env python3
"""Usage : python3 tools/calibrate.py historique.csv   — affiche l'erreur du modèle et les correctifs proposés."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fretrau import calibration, tariff  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
samples = calibration.load_samples(sys.argv[1])
print(json.dumps(calibration.evaluate(samples), ensure_ascii=False, indent=2))
print("\nCorrectifs proposés (à reporter dans config/tariff.json après relecture) :")
print(json.dumps(calibration.suggest(samples), ensure_ascii=False, indent=2))
for w in tariff.freshness_warnings():
    print("ATTENTION :", w)
