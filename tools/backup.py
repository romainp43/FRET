#!/usr/bin/env python3
"""Sauvegarde cohérente de la base SQLite (API de sauvegarde en ligne), compressée, avec empreinte SHA-256 et rotation.

  python3 tools/backup.py backup  [--db DB] [--dest DIR] [--keep 14] [--encrypt-to AGE_RECIPIENT]
  python3 tools/backup.py restore FICHIER.db.gz [--db DB_CIBLE]
  python3 tools/backup.py verify  FICHIER.db.gz

Une sauvegarde qui reste sur le même serveur n'est pas une sauvegarde : copiez DEST vers un stockage EXTERNE
(autre fournisseur / autre région, par ex. rclone/rsync vers un bucket S3 compatible chiffré). Voir docs/SECURITE.md.
Si --encrypt-to est fourni et que `age` est installé, le fichier est chiffré (.age) ; conservez la clé privée HORS serveur.
"""
import argparse
import gzip
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def integrity_ok(db_path):
    con = sqlite3.connect(db_path)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def backup(db, dest, keep=14, recipient=None):
    os.makedirs(dest, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "snap.db")
        src = sqlite3.connect(db)
        dst = sqlite3.connect(raw)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        if not integrity_ok(raw):
            raise SystemExit("ÉCHEC : la copie ne passe pas le contrôle d'intégrité.")
        out = os.path.join(dest, f"fretrau-{stamp}.db.gz")
        with open(raw, "rb") as fi, gzip.open(out, "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo)
    os.chmod(out, 0o600)
    if recipient:
        if not shutil.which("age"):
            raise SystemExit("`age` introuvable : chiffrement impossible (installez age ou retirez --encrypt-to).")
        subprocess.run(["age", "-r", recipient, "-o", out + ".age", out], check=True)
        os.remove(out)
        out += ".age"
        os.chmod(out, 0o600)
    with open(out + ".sha256", "w") as f:
        f.write(f"{sha256(out)}  {os.path.basename(out)}\n")
    files = sorted(x for x in os.listdir(dest) if x.startswith("fretrau-") and not x.endswith(".sha256"))
    for old in files[:-keep] if keep > 0 else []:
        for suffix in ("", ".sha256"):
            try:
                os.remove(os.path.join(dest, old + suffix))
            except FileNotFoundError:
                pass
    return out


def verify(path):
    sumfile = path + ".sha256"
    if not os.path.exists(sumfile):
        return False
    expected = open(sumfile).read().split()[0]
    if sha256(path) != expected:
        return False
    if path.endswith(".age"):
        return True  # contenu chiffré : seule l'empreinte est vérifiable sans la clé
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "x.db")
        with gzip.open(path, "rb") as fi, open(raw, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        return integrity_ok(raw)


def restore(path, db):
    if not verify(path):
        raise SystemExit("ÉCHEC : sauvegarde corrompue ou empreinte invalide.")
    if path.endswith(".age"):
        raise SystemExit("Déchiffrez d'abord : age -d -i cle.txt -o fichier.db.gz fichier.db.gz.age")
    tmp = db + ".restore"
    with gzip.open(path, "rb") as fi, open(tmp, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    os.replace(tmp, db)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backup", "restore", "verify"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--db", default=os.environ.get("FRETRAU_DB", os.path.join(ROOT, "data", "fretrau.db")))
    ap.add_argument("--dest", default=os.path.join(ROOT, "backups"))
    ap.add_argument("--keep", type=int, default=14)
    ap.add_argument("--encrypt-to", default=None)
    a = ap.parse_args()
    if a.cmd == "backup":
        print(backup(a.db, a.dest, a.keep, a.encrypt_to))
    elif a.cmd == "verify":
        ok = verify(a.file)
        print("OK" if ok else "INVALIDE")
        sys.exit(0 if ok else 1)
    else:
        restore(a.file, a.db)
        print("Restauration effectuée :", a.db)


if __name__ == "__main__":
    main()
