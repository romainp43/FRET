"""Protections applicatives : limitation de débit, authentification admin, en-têtes, validation."""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time

# --- En-têtes de sécurité (CSP stricte : aucun script/style inline, aucune ressource externe) ---
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}
HSTS = "max-age=31536000; includeSubDomains"   # ajouté si FRETRAU_HTTPS=1 (derrière un proxy TLS)

MAX_BODY = 64 * 1024


class RateLimiter:
    """Fenêtre glissante par clé (IP). `limit` requêtes par `window` secondes."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self.hits = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            q = [t for t in self.hits.get(key, []) if now - t < self.window]
            if len(q) >= self.limit:
                self.hits[key] = q
                return False
            q.append(now)
            self.hits[key] = q
            if len(self.hits) > 10000:          # borne mémoire
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.window}
            return True


def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return salt.hex() + "$" + h.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split("$")
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h.hex(), h_hex)      # comparaison à temps constant
    except Exception:
        return False


class Sessions:
    """Jetons de session admin signés HMAC, expirants (pas de stockage serveur nécessaire)."""

    def __init__(self, secret: bytes, ttl: int = 3600):
        self.secret, self.ttl = secret, ttl

    def issue(self, user: str) -> str:
        exp = int(time.time()) + self.ttl
        body = f"{user}|{exp}|{secrets.token_hex(8)}"
        sig = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}|{sig}"

    def verify(self, token: str):
        try:
            user, exp, nonce, sig = token.split("|")
            body = f"{user}|{exp}|{nonce}"
            good = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig, good) and int(exp) > time.time():
                return user
        except Exception:
            pass
        return None


class LoginGuard:
    """Verrouille un compte/IP après 5 échecs pendant 15 minutes."""

    def __init__(self, max_fail=5, lock_s=900):
        self.max_fail, self.lock_s = max_fail, lock_s
        self.fails = {}
        self.lock = threading.Lock()

    def locked(self, key):
        with self.lock:
            n, ts = self.fails.get(key, (0, 0))
            return n >= self.max_fail and time.time() - ts < self.lock_s

    def fail(self, key):
        with self.lock:
            n, _ = self.fails.get(key, (0, 0))
            self.fails[key] = (n + 1, time.time())

    def ok(self, key):
        with self.lock:
            self.fails.pop(key, None)


# --- Validation ---
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[0-9+()\-. ]{6,20}$")
CODE_RE = re.compile(r"^FR-[0-9A-F]{12}$")


def clean_text(value, max_len=200) -> str:
    if not isinstance(value, str):
        raise ValueError("Champ texte attendu.")
    value = "".join(ch for ch in value if ch.isprintable() or ch in "\n ").strip()
    if not value or len(value) > max_len:
        raise ValueError("Champ vide ou trop long.")
    return value


# --- 2FA : TOTP (RFC 6238, SHA-1, 6 chiffres, pas de 30 s) en bibliothèque standard ---
import base64
import struct


def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode()


def totp(secret_b32: str, at: float = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32.upper().replace(" ", ""), casefold=True)
    counter = int((at if at is not None else time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
        return False
    now = time.time()
    return any(hmac.compare_digest(totp(secret_b32, now + d * 30), code) for d in range(-window, window + 1))


# --- Extraction d'un montant depuis un texte libre (réponse d'un transporteur) ---
# Le texte n'est JAMAIS interprété comme une instruction : on n'en tire qu'un nombre, validé.
_AMOUNT_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[  .]\d{3})+|\d+)(?:[.,](\d{1,2}))?\s*(?:€|eur\b|euros?\b)", re.I)


def parse_amount(text: str, lo: float = 20.0, hi: float = 20000.0):
    """Retourne l'unique montant en euros trouvé (float) ou None si absent, multiple ou hors plage."""
    found = set()
    for whole, dec in _AMOUNT_RE.findall(text or ""):
        whole = re.sub(r"[  .]", "", whole)
        value = float(f"{whole}.{dec or '0'}")
        if lo <= value <= hi:
            found.add(round(value, 2))
    return found.pop() if len(found) == 1 else None


def valid_siret(siret: str) -> bool:
    """14 chiffres et clé de Luhn correcte."""
    if not isinstance(siret, str) or not re.fullmatch(r"\d{14}", siret):
        return False
    total = 0
    for i, ch in enumerate(reversed(siret)):
        n = int(ch) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0
