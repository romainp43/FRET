#!/usr/bin/env python3
"""Recense les transporteurs routiers de fret actifs d'une zone (annuaire officiel des entreprises).

Usage : python3 tools/import_carriers.py 43 42 69 07      (numéros de départements ; nécessite Internet)
Chaque transporteur est ajouté comme « prospect » sans e-mail : complétez e-mail/téléphone dans l'administration avant toute demande de devis.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import directory  # noqa: E402
from fretrau.db import DB  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
db = DB(os.environ.get("FRETRAU_DB", os.path.join(ROOT, "data", "fretrau.db")))
n = directory.import_zone(db, sys.argv[1:], sleep=time.sleep)
print(f"{n} nouveaux transporteurs recensés ; annuaire total : {len(db.list_directory(limit=100000))}.")
