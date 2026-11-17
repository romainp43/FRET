#!/usr/bin/env python3
"""Relève une boîte IMAP, transmet les demandes de prix à FRETRAU et répond par SMTP. À lancer en boucle (systemd) ou par cron.

Variables : FRETRAU_URL (https://...), FRETRAU_WEBHOOK_SECRET, IMAP_HOST, IMAP_USER, IMAP_PASSWORD,
SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, MAIL_FROM (ex. devis@votre-domaine.fr).
Les secrets restent côté serveur. Non testé contre une vraie boîte dans cet environnement : validez-le d'abord sur une boîte de test.
"""
import imaplib
import os
import smtplib
import ssl
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fretrau import mailgate  # noqa: E402


def env(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Variable manquante : {name}")
    return v


def main(loop_seconds=0):
    url = env("FRETRAU_URL").rstrip("/") + "/api/intake/email"
    secret = env("FRETRAU_WEBHOOK_SECRET")
    mail_from = env("MAIL_FROM")
    limiter = mailgate.SenderLimiter()
    while True:
        ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(env("IMAP_HOST"), ssl_context=ctx) as imap:
            imap.login(env("IMAP_USER"), env("IMAP_PASSWORD"))
            imap.select("INBOX")
            _, data = imap.search(None, "UNSEEN")
            for num in data[0].split():
                _, fetched = imap.fetch(num, "(RFC822)")
                raw = fetched[0][1]
                try:
                    status, reply = mailgate.process(raw, lambda t: mailgate.signed_post(url, secret, {"text": t}), limiter, mail_from)
                except Exception as e:                      # une erreur ne doit jamais faire perdre ni répéter un message
                    status, reply = f"error:{type(e).__name__}", None
                print(time.strftime("%F %T"), status)
                if reply is not None:
                    with smtplib.SMTP(env("SMTP_HOST"), int(os.environ.get("SMTP_PORT", "587"))) as s:
                        s.starttls(context=ctx)
                        s.login(env("SMTP_USER"), env("SMTP_PASSWORD"))
                        s.send_message(reply)
                imap.store(num, "+FLAGS", "\\Seen")
        if not loop_seconds:
            return
        time.sleep(loop_seconds)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
