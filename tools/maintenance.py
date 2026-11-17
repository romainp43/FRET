#!/usr/bin/env python3
"""Maintenance RGPD / rétention. À lancer chaque nuit (cron ou timer systemd).

  python3 tools/maintenance.py [--db data/fretrau.db]

- supprime les devis non transformés en commande après 30 jours
- anonymise les réservations plus anciennes que FRETRAU_RETENTION_YEARS (défaut 5 ans)
  (les factures restent conservées 10 ans : obligation comptable)
- purge les e-mails sortants après 90 jours
- supprime les demandes de contact (et candidatures refusées) de plus d'un an
- vérifie l'intégrité de la chaîne d'audit (code retour 2 si altérée)
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau.db import DB  # noqa: E402

DAY = 86400


def run(db, retention_years=5):
    res = {
        "quotes_purged": db.purge_quotes(30 * DAY),
        "bookings_anonymized": db.anonymize_older_than(int(retention_years * 365 * DAY)),
        "outbox_purged": db.purge_outbox(90 * DAY),
        "leads_purged": db.purge_leads(365 * DAY),
        "positions_purged": db.purge_positions(30 * DAY),
    }
    try:                                                  # veille des retards (le serveur peut aussi la lancer à la demande)
        from datetime import datetime
        from fretrau import watch_run
        res["watchtower"] = watch_run.run(db, datetime.now(), os.environ.get("FRETRAU_PUBLIC_URL", ""), os.environ.get("FRETRAU_SECRET", ""))
    except Exception as e:
        res["watchtower"] = {"error": str(e)[:80]}
    ok, bad = db.verify_audit_chain()
    res["audit_intact"] = ok
    res["audit_first_bad_id"] = bad
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("FRETRAU_DB", os.path.join(ROOT, "data", "fretrau.db")))
    a = ap.parse_args()
    years = float(os.environ.get("FRETRAU_RETENTION_YEARS", "5"))
    res = run(DB(a.db), years)
    print(res)
    sys.exit(0 if res["audit_intact"] else 2)


if __name__ == "__main__":
    main()
