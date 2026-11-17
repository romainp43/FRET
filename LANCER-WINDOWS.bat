@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (where python >nul 2>nul && (set PY=python) || (
  echo Python 3 n'est pas installe. Installez-le depuis https://www.python.org/downloads/ en cochant "Add python.exe to PATH", puis relancez ce fichier.
  start https://www.python.org/downloads/
  pause
  exit /b 1))
set FRETRAU_ADMIN_PASSWORD=demo-mot-de-passe-long-2026
set FRETRAU_DEMO_SPEED=360
if not exist data\places.db (
  echo Installation du referentiel des communes (premiere fois, ~1 min, Internet requis)...
  %PY% tools\import_places.py --db data\places.db
)
set FRETRAU_PLACES_DB=data\places.db
%PY% tools\build_legal.py
start "" http://127.0.0.1:8080
echo Site : http://127.0.0.1:8080   Administration : http://127.0.0.1:8080/admin.html  (utilisateur admin, mot de passe : demo-mot-de-passe-long-2026)
%PY% server.py
pause
