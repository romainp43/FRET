#!/usr/bin/env python3
"""Gestion des comptes du personnel (RBAC). Rôles : admin (tout), ops (réservations, e-mails), finance (factures, statistiques).

  python3 tools/manage_users.py add alice ops          # demande un mot de passe (≥ 12 car.), affiche le secret 2FA
  python3 tools/manage_users.py list
  python3 tools/manage_users.py disable alice          # coupe l'accès immédiatement
  python3 tools/manage_users.py enable alice
  python3 tools/manage_users.py passwd alice
Dès qu'un compte existe en base, le compte unique « admin » des variables d'environnement est désactivé.
Principe du moindre privilège : un seul ou deux admins ; les autres en ops/finance. 2FA obligatoire pour tous les comptes créés ici.
"""
import getpass
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import security  # noqa: E402
from fretrau.db import DB  # noqa: E402

NAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


def ask_password():
    pw = getpass.getpass("Mot de passe (≥ 12 caractères) : ")
    if len(pw) < 12 or pw.lower() == pw or not re.search(r"\d", pw):
        raise SystemExit("Refusé : 12 caractères minimum, avec majuscule(s) et chiffre(s).")
    if pw != getpass.getpass("Confirmer : "):
        raise SystemExit("Les mots de passe diffèrent.")
    return pw


def main(argv, db=None, password=None):
    db = db or DB(os.environ.get("FRETRAU_DB", os.path.join(ROOT, "fretrau.db")))
    if not argv:
        raise SystemExit(__doc__)
    cmd = argv[0]
    if cmd == "list":
        for u in db.list_users():
            print(f"{u['username']:<20} {u['role']:<8} {'actif' if u['active'] else 'DÉSACTIVÉ':<10} 2FA={'oui' if u['mfa'] else 'NON'}")
    elif cmd == "add" and len(argv) == 3:
        name, role = argv[1], argv[2]
        if not NAME_RE.match(name) or role not in DB.ROLES:
            raise SystemExit("Nom invalide (a-z 0-9 . _ -) ou rôle inconnu (admin, ops, finance).")
        if db.get_user(name):
            raise SystemExit("Ce compte existe déjà.")
        pw = password or ask_password()
        secret = security.new_totp_secret()
        db.create_user(name, security.hash_password(pw), secret, role)
        db.audit("cli", "user_created", f"{name}:{role}")
        print(f"Compte créé : {name} ({role}).")
        print(f"Secret 2FA (à saisir dans l'application d'authentification, affiché une seule fois) : {secret}")
        print(f"otpauth://totp/FRETRAU:{name}?secret={secret}&issuer=FRETRAU")
        return secret
    elif cmd in ("disable", "enable") and len(argv) == 2:
        if not db.set_user_active(argv[1], cmd == "enable"):
            raise SystemExit("Compte introuvable.")
        db.audit("cli", f"user_{cmd}d", argv[1])
        print("OK")
    elif cmd == "passwd" and len(argv) == 2:
        if not db.get_user(argv[1]):
            raise SystemExit("Compte introuvable.")
        db.set_user_password(argv[1], security.hash_password(password or ask_password()))
        db.audit("cli", "user_password_changed", argv[1])
        print("OK")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
