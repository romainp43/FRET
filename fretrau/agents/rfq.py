"""Agent de demande de devis (RFQ) : choisit les transporteurs réels de la zone, rédige une demande anonyme, lit les réponses.

Garde-fous :
- RIEN n'est envoyé sans validation humaine (l'agent prépare, vous envoyez) ;
- la demande est ANONYME : jamais le nom ni les coordonnées du client final ;
- on ne contacte que des professionnels ayant une adresse renseignée, jamais un opt-out, au plus une fois tous les 7 jours ;
- chaque message porte un lien de désinscription (répondre STOP) conformément à la prospection B2B encadrée par la CNIL ;
- le texte reçu n'est jamais exécuté : un seul montant est extrait par du code (security.parse_amount), comme pour l'agent e-mail.
"""
import math
import re
import secrets

from .. import security

REF_RE = re.compile(r"RFQ-[A-Z0-9]{8}")
COOLDOWN_S = 7 * 86400
DEFAULT_RADIUS_KM = 80
MAX_TARGETS = 10
SIZE_RANK = {"": 0, "NN": 0, "00": 1, "01": 2, "02": 3, "03": 4, "11": 5, "12": 6, "21": 7, "22": 8, "31": 9, "32": 10}


def new_ref() -> str:
    return "RFQ-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))


def _dist(a_lat, a_lon, b_lat, b_lon):
    p = math.pi / 180
    h = math.sin((b_lat - a_lat) * p / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin((b_lon - a_lon) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def select(directory, origin_lat, origin_lon, now_ts, radius_km=DEFAULT_RADIUS_KM, max_targets=MAX_TARGETS):
    """Transporteurs contactables, du plus proche (puis du plus gros) au plus éloigné. Exclusions expliquées dans `skipped`."""
    ok, skipped = [], []
    for c in directory:
        why = None
        if c.get("optout"):
            why = "s'est désinscrit"
        elif not c.get("email") or not security.EMAIL_RE.match(c["email"]):
            why = "aucune adresse e-mail renseignée"
        elif c.get("lat") is None or c.get("lon") is None:
            why = "position inconnue"
        elif c.get("last_contacted") and now_ts - c["last_contacted"] < COOLDOWN_S:
            why = "contacté depuis moins de 7 jours"
        else:
            d = _dist(origin_lat, origin_lon, c["lat"], c["lon"])
            if d > radius_km:
                why = f"à {d:.0f} km du départ (> {radius_km} km)"
            else:
                ok.append((d, -SIZE_RANK.get(c.get("size", ""), 0), c, d))
        if why:
            skipped.append({"siren": c["siren"], "name": c["name"], "reason": why})
    ok.sort(key=lambda t: (t[0], t[1]))
    return [dict(c, distance_km=round(d, 1)) for _, _, c, d in ok[:max_targets]], skipped


def draft(ref, shipment, public_reply_to):
    """(objet, corps) : demande anonyme, un seul montant attendu, désinscription en une ligne."""
    opts = ", ".join(k for k, v in (shipment.get("options") or {}).items() if v) or "aucune"
    subject = f"[{ref}] Demande de prix : {shipment['origin']} → {shipment['destination']}, {shipment['pickup_date']}"
    body = (f"Bonjour,\n\nNous recherchons un transporteur pour le transport suivant (référence {ref}) :\n"
            f"- Départ : {shipment['origin']} — Arrivée : {shipment['destination']}\n"
            f"- Enlèvement : {shipment['pickup_date']}\n"
            f"- Marchandise : {shipment.get('pallets', '?')} palettes, {shipment.get('weight_kg', '?')} kg ({shipment.get('mode', 'FTL')})\n"
            f"- Options : {opts}\n\n"
            f"Pouvez-vous répondre à cet e-mail en indiquant UN prix en euros HT, tout compris, pour ce transport, ainsi que sa durée de validité ?\n"
            f"Conservez la référence {ref} dans l'objet.\n\n"
            f"Cordialement,\nFRETRAU — {public_reply_to}\n\n"
            f"Vous ne souhaitez plus recevoir de demandes de prix de notre part : répondez simplement STOP.")
    return subject, body


RANGE_RE = re.compile(r"entre\s+\d|\bde\s+\d[\d\s.,]*(?:€|euros?)?\s*à\s*\d|\d\s*(?:€|euros?)?\s*(?:-|–|à)\s*\d[\d\s.,]*\s*(?:€|euros?)", re.I)


def read_reply(text: str):
    """(référence, montant, stop) extraits d'une réponse. Montant None si absent ou ambigu."""
    m = REF_RE.search(text or "")
    stop = bool(re.search(r"(?im)^\s*stop\s*[.!]?\s*$", text or ""))
    amount = None if stop or RANGE_RE.search(text or "") else security.parse_amount(text or "")     # une fourchette n'est pas un prix : jamais devinée
    return (m.group(0) if m else None), amount, stop
