"""Exécution de l'agent de veille sur la base : crée les alertes (une seule fois) et prévient le client en cas de retard."""
import json
from datetime import datetime

from .agents import watchtower
from . import mailer, sms


def run(db, now: datetime, public_url="", sms_secret=""):
    items = []
    for b in db.confirmed_bookings():
        sh = json.loads(b["shipment"])
        q = (db.get_quote(b["quote_id"], max_age_s=10 ** 9) or {}).get("quote", {})
        items.append({"id": b["id"], "code": b["tracking_code"], "shipment": sh, "earliest_delivery": q.get("earliest_delivery", ""),
                      "events": {e["kind"]: e["ts"] for e in db.events_for(b["id"])}, "_b": b})
    created, notified = 0, 0
    by_id = {i["id"]: i for i in items}
    for a in watchtower.scan(items, now):
        if not db.add_alert(a["booking_id"], a["code"], a["severity"], a["message"]):
            continue
        created += 1
        if a["notify_customer"]:
            b = by_id[a["booking_id"]]["_b"]
            cu = json.loads(b["customer"])
            url = f"{public_url}/suivi.html?code={b['tracking_code']}" if public_url else ""
            try:
                mailer.queue(db, cu["email"], f"Votre envoi {b['tracking_code']} : point de situation",
                             f"Bonjour {cu.get('name', '')},\n\nVotre envoi {b['tracking_code']} accuse un retard ({a['message'].lower()}). "
                             f"Nous gérons la situation avec le transporteur et revenons vers vous.\nSuivi : {url}\n\nL'équipe FRETRAU")
                notified += 1
                if cu.get("sms_consent") and cu.get("phone") and sms_secret:
                    sms.queue(db, cu["phone"], "late", sms_secret, True, code=b["tracking_code"], url=url)
            except Exception:
                pass
    return {"alerts_created": created, "customers_notified": notified}
