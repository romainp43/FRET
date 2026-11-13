"""Facturation client : mentions obligatoires françaises, numérotation séquentielle sans trou.

À valider avec votre expert-comptable avant usage réel (régime de TVA, mentions propres à votre société,
facture électronique : plateforme agréée et format Factur-X selon le calendrier de la réforme).
"""
import json
import os
from datetime import date, timedelta

from . import geo, pricing

VAT_RATE = 0.20


def seller() -> dict:
    e = os.environ.get
    return {
        "name": e("FRETRAU_SELLER_NAME", "[RAISON SOCIALE À RENSEIGNER]"),
        "legal_form": e("FRETRAU_SELLER_FORM", "[FORME JURIDIQUE ET CAPITAL]"),
        "address": e("FRETRAU_SELLER_ADDRESS", "[ADRESSE DU SIÈGE]"),
        "siret": e("FRETRAU_SELLER_SIRET", "[SIRET]"),
        "vat_number": e("FRETRAU_SELLER_VAT", "[N° TVA INTRACOMMUNAUTAIRE]"),
        "licence": e("FRETRAU_SELLER_LICENCE", "[N° INSCRIPTION REGISTRE TRANSPORTEURS]"),
    }


def build(booking: dict) -> dict:
    s, cu = json.loads(booking["shipment"]), json.loads(booking["customer"])
    ht = round(booking["customer_price_ht"], 2)
    domestic = geo.country(s["origin"]) == "FR" and geo.country(s["destination"]) == "FR"
    vat = round(ht * VAT_RATE, 2) if domestic else 0.0
    return {
        "seller": seller(),
        "buyer": {"name": cu["name"], "company": cu["company"], "email": cu["email"]},
        "line": f"Transport routier {geo.label(s['origin'])} → {geo.label(s['destination'])} "
                f"({pricing.MODES.get(s['mode'], s['mode']).lower()}), "
                f"enlèvement le {s['pickup_date']} — réf. {booking['tracking_code']}",
        "total_ht": ht, "vat_rate": VAT_RATE if domestic else 0.0, "vat": vat, "total_ttc": round(ht + vat, 2),
        "vat_note": None if domestic else
        "Prestation internationale : TVA selon le régime applicable (autoliquidation possible) — à confirmer avec votre expert-comptable.",
        "due_on": (date.today() + timedelta(days=30)).isoformat(),
        "legal": ["Paiement à 30 jours à compter de la date de facture.",
                  "Pénalité de retard : trois fois le taux d'intérêt légal.",
                  "Indemnité forfaitaire pour frais de recouvrement en cas de retard : 40 €."],
    }
