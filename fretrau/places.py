"""Référentiel de lieux : TOUTES les communes (France) et localités (Europe), en base SQLite locale.

- Le référentiel complet s'installe avec `tools/import_places.py` (sources officielles : geo.api.gouv.fr pour les ~35 000
  communes françaises, GeoNames pour l'Europe). Sans lui, seules les ~100 grandes villes intégrées au code sont disponibles
  et l'API l'indique (`coverage: "limited"`) : aucune couverture complète n'est jamais prétendue à tort.
- Les libellés sont uniques : « Monistrol-sur-Loire » si le nom est unique dans le pays, sinon « Saint-Martin (01700) ».
- La recherche est insensible à la casse, aux accents, aux tirets et à Saint/St.
"""
import os
import re
import sqlite3
import threading
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data", "places.db")
_lock = threading.Lock()
_conn = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY, label TEXT UNIQUE NOT NULL, name TEXT NOT NULL, norm TEXT NOT NULL,
    country TEXT NOT NULL, postal TEXT NOT NULL DEFAULT '', lat REAL NOT NULL, lon REAL NOT NULL, pop INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_places_norm ON places(norm);
CREATE TABLE IF NOT EXISTS place_postal (postal TEXT NOT NULL, place_id INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_postal ON place_postal(postal);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class PlaceError(ValueError):
    """Lieu introuvable ou ambigu ; `suggestions` contient des libellés valides à proposer au client."""

    def __init__(self, message, suggestions=None):
        super().__init__(message)
        self.suggestions = suggestions or []


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[-'’_.,]+", " ", s)
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\bsainte\b", "ste", s)
    return re.sub(r"\s+", " ", s).strip()


def db_path():
    return os.environ.get("FRETRAU_PLACES_DB", DEFAULT_DB)


def _db():
    path = db_path()
    with _lock:
        if path not in _conn:
            if not os.path.exists(path):
                _conn[path] = None
            else:
                c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
                c.row_factory = sqlite3.Row
                _conn[path] = c
        return _conn[path]


def reset():
    """Ferme les connexions (tests, ou après un nouvel import)."""
    with _lock:
        for c in _conn.values():
            if c:
                c.close()
        _conn.clear()


def available() -> bool:
    return _db() is not None


def count() -> int:
    c = _db()
    return c.execute("SELECT COUNT(*) FROM places").fetchone()[0] if c else 0


def get(label: str):
    c = _db()
    if not c:
        return None
    r = c.execute("SELECT * FROM places WHERE label=?", (label,)).fetchone()
    return dict(r) if r else None


def _row_view(r):
    return {"label": r["label"], "country": r["country"], "postal": (r["postal"] or "").split(" ")[0], "lat": r["lat"], "lon": r["lon"], "pop": r["pop"]}


def by_postal(postal: str, limit=10):
    c = _db()
    if not c:
        return []
    rows = c.execute("SELECT p.* FROM place_postal pp JOIN places p ON p.id = pp.place_id WHERE pp.postal=? ORDER BY p.pop DESC LIMIT ?",
                     (postal, limit)).fetchall()
    return [_row_view(r) for r in rows]


def by_name(name: str, country=None):
    """Toutes les localités dont le nom normalisé est exactement `name`."""
    c = _db()
    if not c:
        return []
    q, params = "SELECT * FROM places WHERE norm=?", [normalize(name)]
    if country:
        q, params = q + " AND country=?", params + [country]
    return [_row_view(r) for r in c.execute(q + " ORDER BY pop DESC", params).fetchall()]


def search(q: str, limit: int = 10):
    """Saisie semi-automatique : code postal, ou début de nom (ou de mot) ; les plus peuplées d'abord."""
    c = _db()
    qn = normalize(q)
    if not c or len(qn) < 2:
        return []
    m = re.search(r"\b(\d{5}|\d{4})\b", qn)
    if m:
        return by_postal(m.group(1), limit)
    rows = c.execute("SELECT * FROM places WHERE norm LIKE ? ORDER BY pop DESC, length(norm) LIMIT ?", (qn + "%", limit)).fetchall()
    out = [_row_view(r) for r in rows]
    if len(out) < limit:
        seen = {r["label"] for r in out}
        more = c.execute("SELECT * FROM places WHERE norm LIKE ? AND norm NOT LIKE ? ORDER BY pop DESC LIMIT ?",
                         ("% " + qn + "%", qn + "%", limit - len(out))).fetchall()
        out += [_row_view(r) for r in more if r["label"] not in seen]
    return out


def by_postal_codes(label: str):
    """Codes postaux d'une localité (liste)."""
    c = _db()
    if not c:
        return []
    r = c.execute("SELECT postal FROM places WHERE label=?", (label,)).fetchone()
    return (r["postal"] or "").split() if r else []
