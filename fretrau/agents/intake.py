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
            if re.search(rf"(?:vers|a destination de|livrer a|livraison a|livraison de)\s+(?:\d{{5}}\s+)?{b}[^.;\n]{{0,40}}?(?:depuis|au depart de|en provenance de)\s+(?:\d{{5}}\s+)?{a}\b", n) or \
               re.search(rf"(?:depart|chargement|enlevement|origine)[^.\n]{{0,15}}?{a}[^.\n]{{0,40}}?(?:livraison|arrivee|destination)[^.\n]{{0,15}}?{b}", n) or \
               re.search(rf"(?:de|depuis|from|au depart de|depart)\s+(?:\d{{5}}\s+)?{a}(?:\s+\d{{5}})?\s*(?:,|:)?\s*{arrow}\s+(?:\d{{5}}\s+)?{b}", n) or \
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
    m = re.search(r"(\d{1,3}(?:[ \u00a0.]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*(kg|kgs|kilos?|tonnes?|t)\b", n)
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


MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
          "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
_MONTH_RE = "|".join(MONTHS)
DELIVERY_CUE = re.compile(r"(livr\w*|arrive\w*|au plus tard)[^,.;\n]{0,25}$")


def _clean(text: str) -> str:
    """Retire les parties citées d'un e-mail (lignes « > », « X a écrit : », message d'origine) : leurs dates et villes ne sont pas la demande."""
    out = []
    for line in text.splitlines():
        low = line.strip().lower()
        if re.match(r"^-{2,}\s*(original message|message d'origine|message transfere)", _norm(low)) or re.match(r"^(de|from)\s*:", low):
            break
        if low.startswith(">") or re.search(r"a ecrit\s*:\s*$", _norm(low)):
            continue
        out.append(line)
    return "\n".join(out)


def _dates(n, today: date):
    """Toutes les dates citées, dans l'ordre : [(date, est_livraison, note)]. Une date précédée de « livraison… »/« au plus tard »
    (sans virgule entre les deux) est une date de livraison, pas d'enlèvement."""
    found = []

    def add(pos, d, note=None):
        found.append((pos, d, bool(DELIVERY_CUE.search(n[max(0, pos - 40):pos])), note))

    for m in re.finditer(r"apres[- ]demain", n):
        add(m.start(), today + timedelta(days=2))
    for m in re.finditer(r"\bdemain\b", n):
        if not re.match(r"apres", n[max(0, m.start() - 6):m.start()]):
            add(m.start(), today + timedelta(days=1))
    for m in re.finditer(r"\b(20\d{2})-(\d{2})-(\d{2})\b", n):
        try:
            add(m.start(), date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            return [(None, False, "Date invalide.")]
    spans = []
    for m in re.finditer(rf"\b(\d{{1,2}})\s*(?:er)?\s+({_MONTH_RE})\b(?:\s+(20\d{{2}}))?", n):
        d_, mo = int(m[1]), MONTHS[m[2]]
        y = int(m[3]) if m[3] else today.year
        try:
            res = date(y, mo, d_)
        except ValueError:
            return [(None, False, "Date invalide.")]
        note = None
        if not m[3] and res < today:
            res = date(y + 1, mo, d_)
            note = f"Année supposée : {res.year}."
        add(m.start(), res, note)
        spans.append((m.start(), m.end()))
    for m in re.finditer(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", n):
        if re.match(r"\d{4}-", n[m.start():m.start() + 5]):
            continue
        d_, mo = int(m[1]), int(m[2])
        y = int(m[3]) if m[3] else today.year
        y += 2000 if y < 100 else 0
        try:
            res = date(y, mo, d_)
        except ValueError:
            return [(None, False, "Date invalide.")]
        note = None
        if not m[3] and res < today:                       # « 05/01 » écrit en novembre : année suivante
            res = date(y + 1, mo, d_)
            note = f"Année supposée : {res.year}."
        add(m.start(), res, note)
    if not found:
        for name, wd in WEEKDAYS.items():
            for m in re.finditer(rf"\b{name}\b", n):
                delta = (wd - today.weekday()) % 7 or 7
                d_ = today + timedelta(days=delta)
                add(m.start(), d_, f"« {name} » interprété comme le prochain {name} ({d_.isoformat()}).")
    elif not any(not f[2] for f in found):
        pass
    found.sort(key=lambda f: f[0] if f[0] is not None else 0)
    return [(f[1], f[2], f[3]) for f in found]


def _date(n, today: date):
    """Date d'enlèvement : la première date qui n'est pas une date de livraison."""
    for d_, is_delivery, note in _dates(n, today):
        if d_ is None:
            return None, note
        if not is_delivery:
            return d_, note
    return None, None


def _deliver_by(n, today: date):
    for d_, is_delivery, _ in _dates(n, today):
        if d_ is not None and is_delivery:
            return d_
    return None


NEG_BEFORE = re.compile(r"(sans|pas de|pas d'|aucun|aucune|ni|non)\b[^,.;\n]{0,15}$")
NEG_AFTER = re.compile(r"^[^,.;\n]{0,20}?(non (requis|necessaire|obligatoire|souhaite)|pas (necessaire|requis|besoin|obligatoire)|inutile|exclu)")


def _flag(n, pattern):
    """Vrai si l'option est demandée : au moins une mention non niée (« sans hayon », « hayon non requis » ne comptent pas)."""
    for m in re.finditer(pattern, n):
        if NEG_BEFORE.search(n[max(0, m.start() - 22):m.start()]) or NEG_AFTER.match(n[m.end():m.end() + 30]):
            continue
        return True
    return False


def parse(text: str, today: date = None) -> dict:
    today = today or date.today()
    text = _clean((text or "")[:5000])
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
    options_flatbed = _flag(n, r"\bplateau\b|savoyarde|porte[- ]?engins?|semi plateau")
    # mode
    full = re.search(r"camion complet|lot complet|\bftl\b|complet", n)
    part = re.search(r"messagerie|groupage|\bltl\b|lot partiel", n)
    if full and not part:
        fields["mode"] = "FTL"
    elif part and not full:
        fields["mode"] = "LTL"
    elif options_flatbed and pallets is None:
        fields["mode"] = "FTL"
        assumptions.append("Plateau : commandé en camion complet (le plateau n'existe pas en groupage).")
    elif pallets is not None and pallets <= 12:
        fields["mode"] = "LTL"
        assumptions.append("Mode « palettes (messagerie) » déduit du nombre de palettes ; indiquez « camion complet » si besoin.")
    elif pallets is not None:
        fields["mode"] = "FTL"
        assumptions.append("Mode « camion complet » déduit du nombre de palettes (13 ou plus).")
    options = {
        "adr": _flag(n, r"\badr\b|matieres? dangereuses?|marchandises? dangereuses?"),
        "temperature": _flag(n, r"temperature dirigee|frigo|refrigere|\bfroid\b|reefer|\+4|\bsurgele"),
        "tail_lift": _flag(n, r"hayon"),
        "urgent": _flag(n, r"urgent|express|au plus vite|asap"),
        "flatbed": _flag(n, r"\bplateau\b|savoyarde|porte[- ]?engins?|semi plateau"),
    }
    fields["options"] = {k: v for k, v in options.items() if v}
    db_ = _deliver_by(n, today)
    if db_ and pickup:
        fields["deliver_by"] = db_.isoformat()
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
