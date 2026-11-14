"""Agent de contrôle des transporteurs : vérifie un SIRET auprès de l'Annuaire des Entreprises (source publique).

C'est l'équivalent français du contrôle automatique de l'autorisation d'exercer : l'agent confirme que
l'entreprise existe, que l'établissement est actif et que son activité déclarée est le transport routier de fret.
Il ne remplace PAS le contrôle humain des pièces (licence, assurance, Kbis, attestation de vigilance) : son
rapport est joint au dossier, et seule une société radiée ou fermée est refusée automatiquement.

Désactivé si FRETRAU_VETTING=0 (tests, absence de réseau). Toute panne du service donne « indisponible ».
"""
import json
import os
import time
import unicodedata
import urllib.parse
import urllib.request

API = "https://recherche-entreprises.api.gouv.fr/search"
TRANSPORT_NAF = {"49.41A": "Transports routiers de fret interurbains", "49.41B": "Transports routiers de fret de proximité",
                 "49.41C": "Location de camions avec chauffeur", "53.20Z": "Autres activités de poste et de courrier"}


def enabled() -> bool:
    return os.environ.get("FRETRAU_VETTING", "1") == "1"


def _fetch(siret: str) -> dict:
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode({"q": siret, "per_page": 5}),
                                 headers={"User-Agent": "fretrau-vetting/1.0"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read())


def _fold(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return "".join(c for c in s.upper() if c.isalnum())


def check(siret: str, declared_name: str = "", fetch=None) -> dict:
    """Rapport : status = ok | warning | refused | unavailable, plus les constats lisibles."""
    report = {"checked_at": time.time(), "siret": siret, "status": "unavailable", "findings": []}
    if fetch is None and not enabled():
        report["findings"].append("Contrôle automatique désactivé.")
        return report
    try:
        data = (fetch or _fetch)(siret)
    except Exception:
        report["findings"].append("Annuaire des Entreprises injoignable : contrôle à refaire.")
        return report
    company = site = None
    for e in data.get("results") or []:
        if e.get("siren") != siret[:9]:
            continue
        company = e
        for s in [e.get("siege") or {}] + (e.get("matching_etablissements") or []):
            if s.get("siret") == siret:
                site = s
        break
    if not company:
        report.update(status="warning")
        report["findings"].append("SIRET introuvable dans l'Annuaire des Entreprises (société non diffusible ou numéro erroné).")
        return report
    report["official_name"] = company.get("nom_complet") or ""
    naf = (site or {}).get("activite_principale") or company.get("activite_principale") or ""
    report["naf"] = naf
    if company.get("etat_administratif") != "A" or (site and site.get("etat_administratif") != "A"):
        report.update(status="refused")
        report["findings"].append("Entreprise ou établissement fermé selon l'INSEE.")
        return report
    problems = []
    if not site:
        problems.append("Établissement non retrouvé : vérifier le SIRET sur le Kbis.")
    if naf not in TRANSPORT_NAF:
        problems.append(f"Activité déclarée {naf or 'inconnue'} : ce n'est pas un code de transport routier de fret.")
    else:
        report["findings"].append(f"Activité : {TRANSPORT_NAF[naf]} ({naf}).")
    a, b = _fold(declared_name), _fold(report["official_name"])
    if a and b and a not in b and b not in a:
        problems.append(f"Raison sociale déclarée différente du nom officiel « {report['official_name']} ».")
    if str(company.get("nature_juridique", ""))[:1] == "1":
        report["findings"].append("Entrepreneur individuel.")
    report["findings"] += problems
    report["status"] = "warning" if problems else "ok"
    if not problems:
        report["findings"].insert(0, "Entreprise active, établissement retrouvé.")
    return report
