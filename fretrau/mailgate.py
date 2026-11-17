"""Passerelle e-mail : relie une vraie boîte (IMAP/SMTP) à l'accueil automatique `/api/intake/email`.

Tout le contenu d'un e-mail est NON FIABLE : il n'est jamais exécuté ni recopié tel quel dans la réponse ; seul le texte
produit par le serveur FRETRAU est renvoyé. Garde-fous : pas de réponse aux messages automatiques (anti-boucle), limite par
expéditeur, en-têtes nettoyés (anti-injection), corps signé HMAC avec horodatage.
"""
import email
import hashlib
import hmac
import html
import json
import re
import time
import urllib.request
from email.message import EmailMessage
from email.utils import parseaddr

AUTO_FROM = re.compile(r"(^|[^a-z])(no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounce|notifications?)([^a-z]|$)", re.I)
QUOTE_CUT = re.compile(r"^(le .{5,120} a écrit\s*:|on .{5,120} wrote\s*:|-{2,}\s*(message d'origine|original message)|de\s*:\s.+|from\s*:\s.+)$", re.I)


def is_automatic(msg) -> bool:
    """Réponses automatiques, listes de diffusion, bounces : on ne répond jamais (évite les boucles entre robots)."""
    if (msg.get("Auto-Submitted") or "no").strip().lower() != "no":
        return True
    if (msg.get("Precedence") or "").strip().lower() in ("bulk", "junk", "list", "auto_reply"):
        return True
    if msg.get("List-Id") or msg.get("X-Auto-Response-Suppress"):
        return True
    return bool(AUTO_FROM.search(parseaddr(msg.get("From", ""))[1]))


def _strip_html(h: str) -> str:
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", h)
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


def extract_text(msg, max_len: int = 5000) -> str:
    """Texte utile : partie text/plain (sinon HTML nettoyé), sans réponse citée ni signature."""
    plain = html_part = None
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except (LookupError, ValueError):
            continue
        if ctype == "text/plain" and plain is None:
            plain = text
        elif ctype == "text/html" and html_part is None:
            html_part = text
    body = plain if plain is not None else _strip_html(html_part or "")
    kept = []
    for line in body.replace("\r", "").split("\n"):
        s = line.strip()
        if s == "--" or s == "-- " or QUOTE_CUT.match(s):
            break                                   # signature ou début de la réponse citée
        if s.startswith(">"):
            continue
        kept.append(line)
    text = re.sub(r"[ \t]+", " ", "\n".join(kept)).strip()
    subject = re.sub(r"[\r\n]+", " ", msg.get("Subject", ""))[:200]
    return (subject + "\n" + text)[:max_len]


class SenderLimiter:
    """Au plus `limit` demandes par expéditeur et par fenêtre (anti-spam et anti-abus de la boîte)."""

    def __init__(self, limit=5, window=3600):
        self.limit, self.window, self.hits = limit, window, {}

    def allow(self, sender: str, now=None) -> bool:
        now = now or time.time()
        q = [t for t in self.hits.get(sender.lower(), []) if now - t < self.window]
        if len(q) >= self.limit:
            self.hits[sender.lower()] = q
            return False
        q.append(now)
        self.hits[sender.lower()] = q
        return True


def build_reply(original, body: str, from_addr: str) -> EmailMessage:
    r = EmailMessage()
    r["From"] = from_addr
    r["To"] = parseaddr(original.get("Reply-To") or original.get("From", ""))[1]
    subj = re.sub(r"[\r\n]+", " ", original.get("Subject", ""))[:150]
    r["Subject"] = subj if subj.lower().startswith("re:") else "Re: " + subj
    mid = original.get("Message-ID")
    if mid:
        r["In-Reply-To"] = mid.strip()
        r["References"] = mid.strip()
    r["Auto-Submitted"] = "auto-replied"                  # le destinataire (ou son robot) ne nous répondra pas en boucle
    r.set_content(body)
    return r


def signed_post(url: str, secret: str, payload: dict, timeout=15) -> dict:
    payload = dict(payload, ts=time.time())
    raw = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    req = urllib.request.Request(url, data=raw, method="POST",
                                 headers={"Content-Type": "application/json", "X-Signature": sig})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def process(raw_bytes: bytes, post, limiter: SenderLimiter, from_addr: str):
    """Traite un e-mail brut. `post(text) -> dict` appelle l'accueil. Renvoie (statut, réponse|None)."""
    msg = email.message_from_bytes(raw_bytes)
    sender = parseaddr(msg.get("From", ""))[1]
    if not sender or "@" not in sender:
        return "ignored_no_sender", None
    if is_automatic(msg):
        return "ignored_automatic", None
    if not limiter.allow(sender):
        return "ignored_rate_limited", None
    text = extract_text(msg)
    if len(text.strip()) < 15:
        return "ignored_empty", None
    result = post(text)
    return result.get("status", "error"), build_reply(msg, result.get("reply", ""), from_addr)
