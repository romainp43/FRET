#!/bin/sh
# Démarrage : installe le référentiel complet des communes s'il manque (nécessite Internet), puis lance le serveur.
set -e
cd "$(dirname "$0")/.."
export FRETRAU_PLACES_DB="${FRETRAU_PLACES_DB:-data/places.db}"
if [ ! -f "$FRETRAU_PLACES_DB" ]; then
  echo "[FRETRAU] Installation du référentiel des communes (première fois, ~1 min)…"
  python3 tools/import_places.py --db "$FRETRAU_PLACES_DB" || echo "[FRETRAU] Import impossible : seules les grandes villes seront proposées."
fi
python3 tools/build_legal.py >/dev/null 2>&1 || true
exec python3 server.py
