#!/usr/bin/env python3
"""Sauvegarde ou vérification manuelle de la base.

  python3 tools/backup.py sauvegarder fretrau.db /chemin/sauvegardes
  python3 tools/backup.py verifier /chemin/sauvegardes/fretrau-20261114-030000.db

Restauration : arrêter le serveur, copier la sauvegarde à la place de la base (FRETRAU_DB), supprimer les fichiers
« -wal » et « -shm » voisins s'ils existent, relancer le serveur.
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "sauvegarder":
        from fretrau.db import DB
        os.makedirs(sys.argv[3], mode=0o700, exist_ok=True)
        dest = os.path.join(sys.argv[3], time.strftime("fretrau-%Y%m%d-%H%M%S.db"))
        ok = DB(sys.argv[2]).backup_to(dest)
        os.chmod(dest, 0o600)
        print(("Sauvegarde vérifiée : " if ok else "ÉCHEC de vérification : ") + dest)
        sys.exit(0 if ok else 1)
    if len(sys.argv) == 3 and sys.argv[1] == "verifier":
        conn = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        n = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        print(f"Intégrité : {result} — {n} réservation(s)")
        sys.exit(0 if result == "ok" else 1)
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main()
