#!/bin/sh
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 est requis : installez-le depuis https://www.python.org/downloads/ puis relancez."
  open https://www.python.org/downloads/
  exit 1
fi
export FRETRAU_ADMIN_PASSWORD="demo-mot-de-passe-long-2026" FRETRAU_DEMO_SPEED=360
(sleep 3; open http://127.0.0.1:8080) &
echo "Site : http://127.0.0.1:8080   Administration : /admin.html  (utilisateur admin, mot de passe : $FRETRAU_ADMIN_PASSWORD)"
sh deploy/start.sh
