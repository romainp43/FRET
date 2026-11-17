"""Agent d'accueil : transforme un e-mail de demande de prix « dans n'importe quel format » en demande structurée.

Principe de justesse : on n'invente JAMAIS une donnée critique. Poids, villes, date d'enlèvement (et nombre de palettes en
messagerie) doivent figurer dans le texte ; sinon la demande est déclarée incomplète et la réponse liste exactement ce qui manque.
Les choix par défaut (ex. mode déduit des palettes) sont listés dans `assumptions` pour être montrés au client.
Extraction déterministe (regex + base de villes), sans modèle de langage : reproductible et auditable.
"""
import re
import unicodedata
from datetime import date, timedelta

from .. import geo, places

WEEKDAYS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


DISCRIMINATORS = {"Valence (Drôme)": ("drome", "26000", "26"), "Valence (Espagne)": ("espagne", "spain", "espana", "46000")}


def _names():
    """(nom normalisé, ville ou liste de villes) — noms complets, formes sans parenthèse et alias."""
    out = {}
    for city in geo.CITIES:
        out[_norm(city)] = city
    for alias, target in geo.ALIASES.items():
        out.setdefault(_norm(alias), target)
    return out


STOP = {"pour", "de", "du", "des", "le", "la", "les", "un", "une", "et", "ou", "en", "par", "sur", "sous", "avec", "sans", "au", "aux",
        "bonjour", "merci", "demain", "prix", "devis", "camion", "palette", "palettes", "tonnes", "tonne", "kg", "complet", "svp",
        "cordialement", "madame", "monsieur", "urgent", "express", "enlevement", "livraison", "date", "lundi", "mardi", "mercredi",
        "jeudi", "vendredi", "samedi", "dimanche", "total", "poids", "adr", "hayon", "from", "to", "est", "ce", "ces", "mon", "ma", "mes"}
KEYWORDS = {"de", "depuis", "from", "a", "vers", "to", "pour", "jusqu", "au", "chez", "entre", "et"}
TOKEN = re.compile(r"\d{5}|[^\W\d_]+(?:[-'’][^\W\d_]+)*")


def _commune_mentions(text: str, seed_norms: set):
    """Communes (référentiel complet) citées dans le texte. Une commune n'est retenue que si le contexte indique un lieu
    (précédée de de/depuis/vers/à/→…, suivie de à/vers/→…, ou accolée à un code postal) : « Pour », « Merci » sont aussi des communes !"""
    if not places.available():
        return [], []
    toks = [(m.group(0), m.start(), m.end()) for m in TOKEN.finditer(text)]
    found, ambiguous, i = [], [], 0
    while i < len(toks):
        done = False
        for n in range(min(6, len(toks) - i), 0, -1):
            chunk = toks[i:i + n]
            if any(t[0].isdigit() for t in chunk):
                continue
            phrase = " ".join(t[0] for t in chunk)
            norm = places.normalize(phrase)
            if n == 1 and norm in STOP:
                continue
            if norm in seed_norms:
                break
            cands = places.by_name(phrase)
            if not cands:
                continue
            before = text[:chunk[0][1]].rstrip()
            after = text[chunk[-1][2]:].lstrip()
            prev_tok = toks[i - 1][0] if i > 0 else ""
            next_tok = toks[i + n][0] if i + n < len(toks) else ""
            postal = prev_tok if prev_tok.isdigit() else (next_tok if next_tok.isdigit() else None)
            ctx = (places.normalize(prev_tok) in KEYWORDS or before.endswith(("->", "→", "=>", ":", ">"))
                   or re.match(r"(?i)(à|a|vers|to|->|→|=>|>)\b|(->|→|=>)", after) is not None or postal is not None)
            if not ctx:
                continue
            if postal:
                byp = [c for c in cands if postal in places.by_postal_codes(c["label"])]
                if len(byp) == 1:
                    cands = byp
            if len(cands) == 1:
                found.append((chunk[0][1], cands[0]["label"], _norm(phrase)))
            else:
                ambiguous.append(f"« {phrase} » ({', '.join(c['label'] for c in cands[:4])}…) : précisez le code postal")
            i += n - 1
            done = True
            break
        i += 1
    return found, ambiguous


def _cities(text: str):
    """Villes reconnues (ordre d'apparition) sous forme (libellé, motif normalisé), villes ambiguës, texte normalisé."""
    n = _norm(text)
    found, ambiguous, taken = [], [], []
    seed_norms = set()
    for name, target in sorted(_names().items(), key=lambda kv: -len(kv[0])):
        seed_norms.add(places.normalize(name))
        for m in re.finditer(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", n):
            if any(s < m.end() and m.start() < e for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            if isinstance(target, list):
                pick = [c for c in target if any(d in n for d in DISCRIMINATORS.get(c, ()))]
                if len(pick) == 1:
                    found.append((m.start(), pick[0], name))
                else:
                    ambiguous.append(" ou ".join(target))
            else:
                found.append((m.start(), target, name))
    extra, amb2 = _commune_mentions(text, seed_norms)
    ambiguous += amb2
    found += [(pos, label, pat) for pos, label, pat in extra]
    ordered, seen = [], set()
    for _, label, pat in sorted(found):
        if label not in seen:
            seen.add(label)
            ordered.append((label, pat))
    return ordered, ambiguous, n


def _route(text):
    cities, ambiguous, n = _cities(text)
    if ambiguous:
        return None, None, "Lieu ambigu : " + " ; ".join(sorted(set(ambiguous))) + "."
    arrow = r"(?:a|vers|pour|to|jusqu a|jusqu'a|->|→|=>)"
    pairs = []
    for city_a, pa in cities:
        for city_b, pb in cities:
            if city_a == city_b:
                continue
            a, b = re.escape(pa), re.escape(pb)
            if re.search(rf"(?:de|depuis|from|au depart de|depart)\s+(?:\d{{5}}\s+)?{a}(?:\s+\d{{5}})?\s*(?:,|:)?\s*{arrow}\s+(?:\d{{5}}\s+)?{b}", n) or \
               re.search(rf"{a}(?:\s+\d{{5}})?\s*(?:->|→|=>|>|-)\s*(?:\d{{5}}\s+)?{b}", n) or re.search(rf"{a}(?:\s+\d{{5}})?\s+(?:vers|to)\s+(?:\d{{5}}\s+)?{b}", n):
                pairs.append((city_a, city_b))
    pairs = list(dict.fromkeys(pairs))
    labels = [c for c, _ in cities]
    if len(pairs) > 1:
        return None, None, ("Plusieurs trajets détectés (" + " ; ".join(f"{x} → {y}" for x, y in pairs)
                            + ") : envoyez une demande par trajet pour un prix exact.")
    if pairs:
        return pairs[0][0], pairs[0][1], None
    if len(labels) == 2:
        return labels[0], labels[1], "Sens du trajet déduit de l'ordre d'apparition des villes."
    if len(labels) > 2:
        return None, None, f"Plusieurs villes détectées ({', '.join(labels)}) : précisez le départ et l'arrivée."
    return None, None, None


def _weight(n):
    m = re.search(r"(\d[\d\s\.,]*)\s*(kg|kgs|kilos?|tonnes?|t)\b", n)
    if not m:
        return None
    raw = m.group(1).strip().replace(" ", "")
    unit = m.group(2)
    try:
        v = float(raw.replace(",", "."))
    except ValueError:
        return None
    if unit in ("t", "tonne", "tonnes"):
        v *= 1000
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):        # « 1.200 kg » : point = séparateur de milliers
        v = float(raw.replace(".", ""))
    return v


def _date(n, today: date):
    if re.search(r"apres[- ]demain", n):
        return today + timedelta(days=2), None
    if re.search(r"\bdemain\b", n):
        return today + timedelta(days=1), None
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", n)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])), None
        except ValueError:
            return None, "Date invalide."
    m = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", n)
    if m:
        d, mo = int(m[1]), int(m[2])
        y = int(m[3]) if m[3] else today.year
        y += 2000 if y < 100 else 0
        try:
            res = date(y, mo, d)
        except ValueError:
            return None, "Date invalide."
        note = None
        if not m[3] and res < today:                       # « 05/01 » écrit en novembre : année suivante
            res = date(y + 1, mo, d)
            note = f"Année supposée : {res.year}."
        return res, note
    for name, wd in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", n):
            delta = (wd - today.weekday()) % 7 or 7
            return today + timedelta(days=delta), f"« {name} » interprété comme le prochain {name} ({(today + timedelta(days=delta)).isoformat()})."
    return None, None


def parse(text: str, today: date = None) -> dict:
    today = today or date.today()
    text = (text or "")[:5000]
    origin, destination, route_note = _route(text)
    n = _norm(text)
    assumptions, fields = [], {}
    if origin and destination:
        fields["origin"], fields["destination"] = origin, destination
        if route_note:
            assumptions.append(route_note)
    weight = _weight(n)
    if weight:
        fields["weight_kg"] = weight
    m = re.search(r"(\d{1,2})\s*(?:palettes?|pal\b|europe?s?\b|epal)", n)
    pallets = int(m[1]) if m else None
    if pallets:
        fields["pallets"] = pallets
    pickup, dnote = _date(n, today)
    if pickup:
        fields["pickup_date"] = pickup.isoformat()
    if dnote:
        assumptions.append(dnote)
    # mode
    full = re.search(r"camion complet|lot complet|\bftl\b|complet", n)
    part = re.search(r"messagerie|groupage|\bltl\b|lot partiel", n)
    if full and not part:
        fields["mode"] = "FTL"
    elif part and not full:
        fields["mode"] = "LTL"
    elif pallets is not None and pallets <= 12:
        fields["mode"] = "LTL"
        assumptions.append("Mode « palettes (messagerie) » déduit du nombre de palettes ; indiquez « camion complet » si besoin.")
    elif pallets is not None:
        fields["mode"] = "FTL"
        assumptions.append("Mode « camion complet » déduit du nombre de palettes (13 ou plus).")
    options = {
        "adr": bool(re.search(r"\badr\b|matieres? dangereuses?|marchandises? dangereuses?", n)),
        "temperature": bool(re.search(r"temperature dirigee|frigo|refrigere|froid|reefer|\+4|\bsurgele", n)),
        "tail_lift": bool(re.search(r"hayon", n)),
        "urgent": bool(re.search(r"urgent|express|au plus vite|asap", n)),
        "flatbed": bool(re.search(r"\bplateau\b|savoyarde|porte[- ]?engins?|semi plateau", n)),
    }
    fields["options"] = {k: v for k, v in options.items() if v}
    ld = re.search(r"livr\w*\s+(?:au plus tard\s+)?(?:le\s+)?(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?", n)
    if ld and pickup:
        y = int(ld[3]) if ld[3] else pickup.year
        y += 2000 if y < 100 else 0
        try:
            fields["deliver_by"] = date(y, int(ld[2]), int(ld[1])).isoformat()
        except ValueError:
            pass
    missing = []
    if not (origin and destination):
        missing.append("villes de départ et d'arrivée")
    if "weight_kg" not in fields:
        missing.append("poids total (en kg ou tonnes)")
    if "pickup_date" not in fields:
        missing.append("date d'enlèvement")
    if fields.get("mode") == "LTL" and "pallets" not in fields:
        missing.append("nombre de palettes")
    if "mode" not in fields and "pallets" not in fields:
        missing.append("type de transport (camion complet ou palettes) / nombre de palettes")
    ambiguity = route_note if (route_note and not (origin and destination)) else None
    if not (origin and destination) and not ambiguity and re.search(r"\b\d{5}\b", text):
        ambiguity = "Code postal reconnu mais ville inconnue de notre base : indiquez la ville (ou la grande ville la plus proche)."
    return {"complete": not missing, "fields": fields, "missing": missing, "assumptions": assumptions, "ambiguity": ambiguity}


def reply_needing_info(result: dict) -> str:
    lines = ["Bonjour,", "", "Merci pour votre demande. Pour vous donner un prix exact sans approximation, il nous manque :"]
    lines += [f"  - {m}" for m in result["missing"]]
    if result.get("ambiguity"):
        lines += ["", result["ambiguity"]]
    lines += ["", "Répondez simplement à cet e-mail avec ces éléments : le prix vous sera communiqué aussitôt.", "", "L'équipe FRETRAU"]
    return "\n".join(lines)
