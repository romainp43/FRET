"""Suivi par le chauffeur : lien personnel à usage unique pour partager sa position (le seul vrai « suivi en direct » sans télématique).

Sécurité et vie privée :
- le jeton (24 octets aléatoires) n'est JAMAIS stocké : seule son empreinte SHA-256 l'est ; il voyage dans le fragment d'URL (#…),
  donc n'apparaît pas dans les journaux du serveur ;
- aucune position n'est enregistrée tant que le chauffeur n'a pas accepté (consentement explicite sur la page) ; il peut arrêter à tout moment ;
- le lien expire (96 h par défaut) et s'arrête à la livraison ; une position au plus toutes les 20 s ;
- les positions sont supprimées après 30 jours (maintenance) ; le client ne voit que la dernière position et la distance restante.
"""
import hashlib
import secrets
import time

TTL_H = 96
MIN_INTERVAL_S = 20
EUROPE = (34.0, 72.0, -12.0, 32.0)           # lat min, lat max, lon min, lon max (boîte englobante large)


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_link(db, booking_id: int, ttl_h: int = TTL_H) -> str:
    token = secrets.token_urlsafe(24)
    db.add_driver_link(_h(token), booking_id, time.time() + ttl_h * 3600)
    return token


def resolve(db, token: str):
    """(lien, réservation) si le jeton est valide, non révoqué, non expiré et la livraison pas encore faite ; sinon None."""
    if not isinstance(token, str) or not 20 <= len(token) <= 60:
        return None
    link = db.get_driver_link(_h(token))
    if not link or link["revoked"] or link["expires_at"] < time.time():
        return None
    b = db.booking_by_id(link["booking_id"])
    if not b or b["status"] != "confirmed" or any(e["kind"] == "delivered" for e in db.events_for(b["id"])):
        return None
    return link, b


def record(db, token: str, lat, lon, accuracy=None):
    r = resolve(db, token)
    if not r:
        return "invalid"
    link, b = r
    if not link["consent_at"]:
        return "no_consent"
    if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return "bad_position"
    if not (EUROPE[0] <= lat <= EUROPE[1] and EUROPE[2] <= lon <= EUROPE[3]):
        return "bad_position"
    last = db.last_position(b["id"])
    if last and time.time() - last["ts"] < MIN_INTERVAL_S:
        return "too_soon"
    acc = float(accuracy) if isinstance(accuracy, (int, float)) and not isinstance(accuracy, bool) and 0 <= accuracy < 100000 else None
    db.add_position(b["id"], float(lat), float(lon), acc)
    return "ok"
