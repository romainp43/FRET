"""Agent de réception : transforme une demande de devis écrite en texte libre (e-mail) en devis chiffré.

Étapes :
  1. extraction par règles (codes postaux, villes, palettes, poids, date, options) ;
  2. si une clé API est configurée, le modèle de langage complète les champs manquants ;
  3. TOUS les champs, d'où qu'ils viennent, sont revalidés par le moteur de devis (pricing.build_quote) ;
  4. le prix est calculé par le code, jamais par le modèle ;
  5. s'il manque une information indispensable, l'agent la demande au lieu de deviner.
"""
import re
import secrets
import unicodedata
from dataclasses import asdict
from datetime import date, timedelta

from .. import geo, mailer, market, pricing
from . import llm

_WEIGHT_RE = re.compile(r"(\d{1,3}(?:[  .]\d{3})+|\d+)(?:[.,](\d{1,2}))?\s*(kg|kgs|kilos?|tonnes?|t)\b", re.I)
_PALLET_RE = re.compile(r"(\d{1,2})\s*(?:palettes?|pal\b|europalettes?)", re.I)
_DATE_RE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONEY_RE = re.compile(r"\d[\d  .,]*\s*(?:€|eur\b|euros?\b)", re.I)
_DEST_CUE = re.compile(r"(livraison|livrer|destination|arriv[ée]e|vers|jusqu)", re.I)
_ORIG_CUE = re.compile(r"(d[ée]part|enl[èe]vement|chargement|origine|depuis|au d[ée]part)", re.I)
_WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_OPTION_WORDS = {
    "adr": r"\b(adr|mati[èe]res? dangereuses?)\b", "tail_lift": r"\bhayon\b",
    "temperature": r"\b(frigo|frigorifique|temp[ée]rature dirig[ée]e|r[ée]frig[ée]r[ée])\b",
    "urgent": r"\b(urgent|express|en urgence)\b", "flatbed": r"\bplateau\b",
}


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def _places(text: str) -> list:
    """Lieux reconnus, dans l'ordre du texte : [(position, lieu)]."""
    found = []
    for m in re.finditer(r"(?<!\d)\d{5}(?!\d)", text):
        if geo.known(m.group()):
            found.append((m.start(), m.group()))
    folded = _fold(text)
    for city in geo.CITIES:
        for m in re.finditer(r"(?<![a-z])" + re.escape(_fold(city)) + r"(?![a-z])", folded):
            found.append((m.start(), city))
    found.sort()
    out = []
    for pos, place in found:                       # un code postal suivi du nom de sa ville ne compte qu'une fois
        if out and (place == out[-1][1] or pos - out[-1][0] < 30 and geo.haversine_km(place, out[-1][1]) < 25):
            continue
        out.append((pos, place))
    return out


def _route(text: str, places: list):
    if len(places) < 2:
        if places and any(0 <= places[0][0] - m.end() < 60 for m in _DEST_CUE.finditer(text)):
            return None, places[0][1]
        return (places[0][1] if places else None), None

    def after(cue):
        best = None
        for m in cue.finditer(text):
            nxt = [p for p in places if 0 <= p[0] - m.end() < 60]
            if nxt and (best is None or nxt[0][0] < best[0]):
                best = nxt[0]
        return best[1] if best else None

    origin, dest = after(_ORIG_CUE), after(_DEST_CUE)
    names = [p[1] for p in places]
    if origin and dest and origin != dest:
        return origin, dest
    if dest and not origin:
        origin = next((n for n in names if n != dest), None)
        return origin, dest
    if origin and not dest:
        return origin, next((n for n in names if n != origin), None)
    return names[0], names[1]


def _pickup(text: str, today: date):
    low = _fold(text)
    if "apres-demain" in low or "apres demain" in low:
        return today + timedelta(days=2)
    if "demain" in low:
        return today + timedelta(days=1)
    if "aujourd" in low:
        return today
    for i, day in enumerate(_WEEKDAYS):               # « mardi » : le prochain mardi
        if re.search(r"\b" + day + r"\b", low):
            return today + timedelta(days=(i - today.weekday() - 1) % 7 + 1)
    m = _ISO_RE.search(text)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        for m in _DATE_RE.finditer(text):
            year = int(m.group(3)) if m.group(3) else today.year
            year += 2000 if year < 100 else 0
            d = date(year, int(m.group(2)), int(m.group(1)))
            if not m.group(3) and d < today:
                d = date(year + 1, d.month, d.day)
            return d
    except ValueError:
        pass
    return None


def parse(text: str, today: date = None) -> dict:
    """Champs extraits par règles. Les valeurs absentes sont à None."""
    today = today or date.today()
    text = text[:5000]
    weight = None
    m = _WEIGHT_RE.search(text)
    if m:
        value = float(re.sub(r"[  .]", "", m.group(1)) + "." + (m.group(2) or "0"))
        weight = value * 1000 if m.group(3).lower().startswith("t") else value
    scrub = _MONEY_RE.sub(" ", _WEIGHT_RE.sub(" ", text))          # un poids ou un prix n'est pas un code postal
    origin, destination = _route(scrub, _places(scrub))
    m = _PALLET_RE.search(text)
    pallets = int(m.group(1)) if m else None
    low = _fold(text)
    if re.search(r"\b(lot partiel|demi[- ]camion|partiel)\b", low):
        mode = "PTL"
    elif re.search(r"\b(camion complet|complet|ftl|semi|semi-remorque)\b", low):
        mode = "FTL"
    elif pallets:
        mode = "LTL"
    else:
        mode = None
    options = {k: bool(re.search(rx, low)) for k, rx in _OPTION_WORDS.items()}
    return {"origin": origin, "destination": destination, "mode": mode, "pallets": pallets,
            "weight_kg": weight, "pickup_date": _pickup(text, today), "options": options}


def _complete_with_llm(fields: dict, text: str) -> dict:
    missing = [k for k in ("origin", "destination", "pallets", "weight_kg", "mode") if fields.get(k) is None]
    if not missing or not llm.available():
        return fields
    got = llm.extract(text, {
        "origin": "code postal français à 5 chiffres du lieu de chargement", "destination": "code postal français "
        "à 5 chiffres du lieu de livraison", "pallets": "nombre entier de palettes", "weight_kg": "poids total en kg",
        "mode": "FTL (camion complet), PTL (lot partiel) ou LTL (palettes)"})
    out = dict(fields)
    for k in missing:
        v = got.get(k)
        if k in ("origin", "destination") and isinstance(v, str) and geo.known(v.strip()):
            out[k] = v.strip()
        elif k == "pallets" and isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 33:
            out[k] = v
        elif k == "weight_kg" and isinstance(v, (int, float)) and not isinstance(v, bool) and 1 <= v <= pricing.FTL_MAX_KG:
            out[k] = float(v)
        elif k == "mode" and v in pricing.MODES:
            out[k] = v
    return out


MISSING_LABELS = {"origin": "le code postal de chargement", "destination": "le code postal de livraison",
                  "weight_kg": "le poids total (kg)", "pallets": "le nombre de palettes"}


def handle(db, from_addr: str, text: str, base_url: str, today: date = None) -> dict:
    """Traite un e-mail de demande de devis et met la réponse en file d'envoi."""
    today = today or date.today()
    f = _complete_with_llm(parse(text, today), text)
    assumptions = []
    if f["mode"] is None:
        f["mode"] = "FTL"
        assumptions.append("camion complet (aucun nombre de palettes indiqué)")
    if f["pickup_date"] is None or not today <= f["pickup_date"] <= today + timedelta(days=60):
        f["pickup_date"] = today + timedelta(days=1)
        assumptions.append(f"enlèvement le {f['pickup_date'].strftime('%d/%m/%Y')}")
    if f["mode"] == "FTL" and f["weight_kg"] is None:
        f["weight_kg"] = float(pricing.FTL_MAX_KG)
        assumptions.append("chargement jusqu'à 24 tonnes")
    needed = ["origin", "destination", "weight_kg"] + (["pallets"] if f["mode"] != "FTL" else [])
    missing = [k for k in needed if f.get(k) is None]

    if missing:
        body = ("Bonjour,\n\nMerci pour votre demande. Pour vous donner un prix, il nous manque : "
                + ", ".join(MISSING_LABELS[k] for k in missing)
                + ".\nRépondez simplement à ce message avec ces informations.\n\nL'équipe FRETRAU")
        mailer.queue(db, from_addr, "FRETRAU — précision nécessaire pour votre devis", body)
        db.add_inbound_quote(from_addr, text, None, "missing:" + ",".join(missing))
        return {"status": "missing", "missing": missing}

    try:
        q = pricing.build_quote(f["origin"], f["destination"], f["mode"], f["pallets"], f["weight_kg"], f["options"],
                                market_factor=market.factor(db, f["origin"], f["destination"]))
    except pricing.QuoteError as e:
        mailer.queue(db, from_addr, "FRETRAU — votre demande de devis",
                     f"Bonjour,\n\nNous ne pouvons pas chiffrer cette demande automatiquement : {e}\n"
                     "Un conseiller vous recontacte.\n\nL'équipe FRETRAU")
        db.add_inbound_quote(from_addr, text, None, "human")
        return {"status": "human", "reason": str(e)}

    quote_id = secrets.token_urlsafe(12)
    shipment = {"pallets": f["pallets"], "weight_kg": f["weight_kg"], "pickup_date": f["pickup_date"].isoformat(),
                "options": {k: v for k, v in f["options"].items() if v}}
    db.save_quote(quote_id, {"quote": asdict(q), "shipment": shipment})
    lines = [f"Trajet : {geo.label(q.origin)} -> {geo.label(q.destination)} ({q.distance_km:.0f} km)",
             f"Transport : {pricing.MODES[q.mode]}"
             + (f", {f['pallets']} palette(s)" if f["pallets"] and q.mode != "FTL" else "") + f", {f['weight_kg']:.0f} kg",
             f"Prix : {q.price_ht:.2f} € HT" + (f" ({q.price_ttc:.2f} € TTC)" if q.vat else ""),
             f"Délai estimé : {q.transit_days} jour(s)"]
    if assumptions:
        lines.append("Hypothèses retenues : " + " ; ".join(assumptions) + ".")
    body = ("Bonjour,\n\nVoici votre prix, valable 24 h :\n\n" + "\n".join(lines)
            + f"\n\nRéserver en ligne : {base_url}/?devis={quote_id}\n\nL'équipe FRETRAU")
    mailer.queue(db, from_addr, f"FRETRAU — votre devis {geo.label(q.origin)} -> {geo.label(q.destination)}", body)
    db.add_inbound_quote(from_addr, text, quote_id, "quoted")
    return {"status": "quoted", "quote_id": quote_id, "price_ht": q.price_ht, "assumptions": assumptions,
            "fields": {**{k: f[k] for k in ("origin", "destination", "mode", "pallets", "weight_kg")},
                       "pickup_date": f["pickup_date"].isoformat()}}
