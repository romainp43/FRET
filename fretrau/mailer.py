"""E-mails sortants via une file d'attente (outbox).

- Sans configuration SMTP, les e-mails restent « queued » (visibles dans l'admin) : aucun envoi accidentel.
- Avec FRETRAU_SMTP_HOST (+ PORT, USER, PASSWORD, FROM) : envoi en STARTTLS avec vérification du certificat.
- EmailMessage encode les en-têtes proprement ; on refuse en plus tout retour chariot (injection d'en-têtes).
"""
import os
import smtplib
import ssl
from email.message import EmailMessage

from . import geo, security


def queue(db, to_addr: str, subject: str, body: str):
    if any(c in to_addr + subject for c in "\r\n") or not security.EMAIL_RE.match(to_addr):
        raise ValueError("Adresse ou objet invalide.")
    db.queue_mail(to_addr, subject[:200], body)


def flush(db) -> int:
    """Envoie les e-mails en attente. Retourne le nombre d'envois réussis."""
    host = os.environ.get("FRETRAU_SMTP_HOST")
    if not host:
        return 0
    sent = 0
    sender = os.environ.get("FRETRAU_SMTP_FROM", "no-reply@localhost")
    try:
        with smtplib.SMTP(host, int(os.environ.get("FRETRAU_SMTP_PORT", "587")), timeout=15) as s:
            s.starttls(context=ssl.create_default_context())
            if os.environ.get("FRETRAU_SMTP_USER"):
                s.login(os.environ["FRETRAU_SMTP_USER"], os.environ.get("FRETRAU_SMTP_PASSWORD", ""))
            for m in db.queued_mails():
                msg = EmailMessage()
                msg["From"], msg["To"], msg["Subject"] = sender, m["to_addr"], m["subject"]
                msg.set_content(m["body"])
                try:
                    s.send_message(msg)
                    db.mark_mail(m["id"], "sent")
                    sent += 1
                except Exception as e:
                    db.mark_mail(m["id"], "failed", str(e))
    except Exception:
        pass                       # SMTP indisponible : les messages restent en file
    return sent


def booking_confirmation(customer, code, shipment, price_ht, base_url) -> tuple[str, str]:
    subject = f"FRETRAU — transport confirmé ({code})"
    body = (f"Bonjour {customer['name']},\n\nVotre transport {geo.label(shipment['origin'])} → "
            f"{geo.label(shipment['destination'])} "
            f"est confirmé pour un montant de {price_ht:.2f} € HT.\n\nCode de suivi : {code}\n"
            f"Suivi : {base_url}/#{code}\n\nCordialement,\nL'équipe FRETRAU")
    return subject, body


def booking_pending(customer, code, base_url) -> tuple[str, str]:
    return (f"FRETRAU — demande reçue ({code})",
            f"Bonjour {customer['name']},\n\nNous avons bien reçu votre demande. Un conseiller la traite "
            f"et reviendra vers vous rapidement.\n\nCode de suivi : {code}\nSuivi : {base_url}/#{code}\n\n"
            f"Cordialement,\nL'équipe FRETRAU")
