#!/usr/bin/env python3
"""Contrôle de mise en ligne : liste ce qui BLOQUE le lancement, ce qui est risqué, et ce qui est prêt.

Usage : FRETRAU_...=... python3 tools/preflight.py     (mêmes variables d'environnement que le serveur ; code de sortie 1 s'il reste un BLOQUANT)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import places, tariff  # noqa: E402


def check(env=None, root=ROOT):
    env = os.environ if env is None else env
    out = []                                              # (niveau, texte) ; niveau : BLOQUANT | RISQUE | OK

    def add(level, text):
        out.append((level, text))

    with open(os.path.join(root, "config", "company.json"), encoding="utf-8") as f:
        company = json.load(f)
    todo = [k for k, v in company.items() if "À COMPLÉTER" in str(v)]
    add("BLOQUANT" if todo else "OK", f"Mentions légales : {len(todo)} champ(s) à compléter dans config/company.json ({', '.join(todo[:6])}{'…' if len(todo) > 6 else ''})" if todo else "Mentions légales complètes")
    pw = env.get("FRETRAU_ADMIN_PASSWORD", "")
    add("BLOQUANT" if len(pw) < 12 else "OK", "Mot de passe admin : à définir (12 caractères minimum)" if len(pw) < 12 else "Mot de passe admin défini")
    add("BLOQUANT" if len(env.get("FRETRAU_SECRET", "")) < 32 else "OK", "FRETRAU_SECRET (32 caractères minimum) manquant : les sessions seraient perdues à chaque redémarrage" if len(env.get("FRETRAU_SECRET", "")) < 32 else "Secret de session défini")
    add("BLOQUANT" if env.get("FRETRAU_HTTPS") != "1" else "OK", "HTTPS non activé (FRETRAU_HTTPS=1 derrière un certificat SSL)" if env.get("FRETRAU_HTTPS") != "1" else "HTTPS activé")
    add("BLOQUANT" if env.get("FRETRAU_DEMO_TIMELINE", "1") != "0" else "OK", "Suivi simulé actif : mettez FRETRAU_DEMO_TIMELINE=0 (sinon des clients verraient de faux jalons)" if env.get("FRETRAU_DEMO_TIMELINE", "1") != "0" else "Aucun jalon simulé")
    pub = env.get("FRETRAU_PUBLIC_URL", "")
    add("BLOQUANT" if not pub.startswith("https://") else "OK", "FRETRAU_PUBLIC_URL doit être l'adresse publique en https://" if not pub.startswith("https://") else f"Adresse publique : {pub}")
    add("RISQUE" if not env.get("FRETRAU_ADMIN_TOTP_SECRET") else "OK", "Double authentification admin non activée" if not env.get("FRETRAU_ADMIN_TOTP_SECRET") else "Double authentification admin activée")
    add("BLOQUANT" if not env.get("FRETRAU_SMTP_HOST") else "OK", "E-mail non configuré (FRETRAU_SMTP_HOST…) : aucune confirmation de réservation ne partirait" if not env.get("FRETRAU_SMTP_HOST") else "Envoi d'e-mails configuré")
    add("RISQUE" if not env.get("FRETRAU_OPS_EMAIL") else "OK", "FRETRAU_OPS_EMAIL absent : vous ne seriez pas alerté des réclamations et candidatures" if not env.get("FRETRAU_OPS_EMAIL") else "Alertes exploitation configurées")
    add("RISQUE" if not env.get("FRETRAU_WEBHOOK_SECRET") else "OK", "FRETRAU_WEBHOOK_SECRET absent : réponses des transporteurs par e-mail désactivées" if not env.get("FRETRAU_WEBHOOK_SECRET") else "Webhooks e-mail signés")
    add("RISQUE" if not env.get("FRETRAU_ALLOWED_HOSTS") else "OK", "FRETRAU_ALLOWED_HOSTS absent (liste des noms de domaine autorisés)" if not env.get("FRETRAU_ALLOWED_HOSTS") else "Noms d'hôte restreints")
    db = env.get("FRETRAU_DB", "")
    add("BLOQUANT" if not db or db.startswith("/tmp") else "OK", "FRETRAU_DB doit pointer vers un disque PERSISTANT (sinon les réservations disparaissent au redémarrage)" if not db or db.startswith("/tmp") else f"Base de données : {db}")
    n = places.count()
    add("OK" if n >= 60000 else "RISQUE", f"Référentiel de lieux : {n} (complet)" if n >= 60000 else f"Référentiel de lieux incomplet ({n}) : lancez tools/import_places.py")
    for w in tariff.freshness_warnings():
        add("RISQUE", w)
    add("RISQUE", "Aucun transporteur réel dans la base (carriers.py contient des transporteurs FICTIFS) : sans transporteurs réels aucune réservation ne peut être honorée")
    add("RISQUE", "Pas de sauvegarde planifiée détectée : planifiez tools/backup.py (cron)") if not env.get("FRETRAU_BACKUP_DIR") else add("OK", "Dossier de sauvegarde défini")
    return out


if __name__ == "__main__":
    res = check()
    for lvl, txt in sorted(res, key=lambda r: ["BLOQUANT", "RISQUE", "OK"].index(r[0])):
        print(f"[{lvl:<8}] {txt}")
    blockers = sum(1 for l, _ in res if l == "BLOQUANT")
    print(f"\n{blockers} bloquant(s), {sum(1 for l, _ in res if l == 'RISQUE')} risque(s).")
    sys.exit(1 if blockers else 0)
