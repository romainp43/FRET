"""Agent de veille (« watchtower ») : repère les envois en difficulté AVANT que le client appelle.

Règles (sur des réservations confirmées, à l'heure `now`) :
  pickup_late    — fenêtre d'enlèvement dépassée (+ 2 h de tolérance) sans jalon « chargé » ;
  stalled        — chargé mais aucun nouveau jalon depuis 24 h ;
  delivery_late  — date de livraison prévue dépassée (fin de journée) sans livraison ;
  pod_missing    — arrivé depuis plus de 24 h sans preuve de livraison (retarde le paiement du transporteur).
Chaque alerte est émise une seule fois par réservation (idempotence en base) ; les retards déclenchent un message au client.
Ce que l'agent NE sait PAS : la position réelle du camion (sauf si le chauffeur partage sa position, voir driver_link).
"""
from datetime import datetime, timedelta

GRACE_H = 2
STALL_H = 24
POD_H = 24

LABELS = {"pickup_late": "Enlèvement non confirmé après la fenêtre prévue", "stalled": "Aucun jalon depuis plus de 24 h",
          "delivery_late": "Livraison en retard sur la date prévue", "pod_missing": "Preuve de livraison manquante"}
NOTIFY_CUSTOMER = {"pickup_late", "delivery_late"}
SEVERITY = {"pickup_late": "high", "delivery_late": "high", "stalled": "medium", "pod_missing": "low"}


def _end_of_window(day: str, window: str, default="17:00"):
    end = (window or "").split("-")[-1].strip() or default
    try:
        hh, mm = (int(x) for x in end.split(":"))
    except ValueError:
        hh, mm = 17, 0
    return datetime.fromisoformat(day) + timedelta(hours=hh, minutes=mm)


def scan(items, now: datetime):
    """items : [{id, code, shipment(dict), earliest_delivery(str|''), events{kind: ts}}] → liste d'alertes (non dédupliquées)."""
    alerts = []
    for it in items:
        s, ev = it["shipment"], it["events"]
        if "delivered" in ev:
            continue
        found = []
        if "loaded" not in ev and "pickup_date" in s:
            if now > _end_of_window(s["pickup_date"], s.get("pickup_window")) + timedelta(hours=GRACE_H):
                found.append("pickup_late")
        if ev and "arrived" not in ev:
            last = max(ev.values())
            if "loaded" in ev and now.timestamp() - last > STALL_H * 3600:
                found.append("stalled")
        if "arrived" in ev and now.timestamp() - ev["arrived"] > POD_H * 3600:
            found.append("pod_missing")
        planned = s.get("deliver_by") or it.get("earliest_delivery")
        if planned:
            try:
                if now > _end_of_window(planned, s.get("delivery_window")):
                    found.append("delivery_late")
            except ValueError:
                pass
        for code in found:
            alerts.append({"booking_id": it["id"], "code": code, "tracking_code": it["code"], "severity": SEVERITY[code],
                           "message": LABELS[code], "notify_customer": code in NOTIFY_CUSTOMER})
    return alerts
