"""Registre des transporteurs : réseau de démonstration + transporteurs réels enregistrés en base.

Statuts d'un transporteur réel :
  prospect        importé de l'annuaire public, jamais contacté ni contrôlé ;
  pending_review  a candidaté sur le site, pièces à contrôler par un humain ;
  verified        licence, assurance, Kbis et attestation de vigilance contrôlés : seul statut affectable ;
  blocked         exclu.
Le réseau de démonstration (sociétés fictives) n'est utilisé que si FRETRAU_DEMO vaut 1 (défaut).
"""
import os

from .carriers import CARRIERS, Carrier
from .db import CARRIER_ID_BASE


def demo_enabled() -> bool:
    return os.environ.get("FRETRAU_DEMO", "1") == "1"


def from_row(r) -> Carrier:
    return Carrier(
        id=r["id"], name=r["name"], base_city=r["base_place"], rating=r["rating"], reliability=r["reliability"],
        price_factor=1.0, modes=tuple(m for m in r["modes"].split(",") if m), europe=bool(r["europe"]),
        licence_ok=r["status"] == "verified" and bool(r["licence_no"]),
        insurance_until=r["insurance_until"] or "", blocked=r["status"] == "blocked",
        simulated=False, email=r["email"] or "")


def get(db, carrier_id):
    if isinstance(carrier_id, int) and carrier_id <= CARRIER_ID_BASE:
        return {c.id: c for c in CARRIERS}.get(carrier_id) if demo_enabled() else None
    row = db.carrier_row(carrier_id) if db is not None else None
    return from_row(row) if row else None


def pool(db) -> list:
    """Transporteurs proposables aux agents : démonstration (si activée) + réels vérifiés."""
    out = list(CARRIERS) if demo_enabled() else []
    if db is not None:
        out += [from_row(r) for r in db.list_carriers(status="verified", limit=5000)]
    return out
