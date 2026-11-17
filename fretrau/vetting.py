"""Candidature transporteur : contrôles de FORME automatiques, puis revue humaine.

Ce que ce module vérifie (hors ligne, sans erreur possible) : clé de contrôle SIREN/SIRET (Luhn), clé TVA française,
format des numéros de TVA européens, date et montant de l'assurance, cohérence des champs.
Ce qu'il NE PEUT PAS vérifier seul : que l'entreprise existe et est active (INSEE/Sirene, registre du commerce), que
la licence est valide (registre des entreprises de transport), que le numéro de TVA est actif (VIES de la Commission
européenne), que l'assurance existe réellement (attestation). Ces vérifications sont faites par un humain dans
l'administration, ou branchées plus tard sur ces services officiels. Une candidature n'est donc JAMAIS approuvée
automatiquement.
"""
import re
from datetime import date, timedelta

MIN_CMR_COVER_EUR = 100_000          # plafond de garantie RC marchandises transportées exigé par sinistre (à ajuster)
MIN_INSURANCE_DAYS = 30              # l'assurance doit couvrir au moins 30 jours à compter de la candidature
COUNTRIES = {"FR": "France", "ES": "Espagne", "PT": "Portugal", "IT": "Italie", "BE": "Belgique", "NL": "Pays-Bas",
             "LU": "Luxembourg", "DE": "Allemagne", "AT": "Autriche", "CH": "Suisse", "PL": "Pologne"}
EQUIPMENT = {"dry": "Fourgon / semi bâchée", "reefer": "Frigorifique", "flatbed": "Plateau / porte-engins",
             "tail_lift": "Hayon élévateur", "adr": "Matières dangereuses (ADR)", "ltl": "Groupage / palettes"}
VAT_PATTERNS = {   # formats publiés par la Commission européenne ; ne prouvent pas que le numéro est actif
    "ES": r"ES[A-Z0-9]\d{7}[A-Z0-9]", "PT": r"PT\d{9}", "IT": r"IT\d{11}", "BE": r"BE[01]\d{9}", "NL": r"NL\d{9}B\d{2}",
    "LU": r"LU\d{8}", "DE": r"DE\d{9}", "AT": r"ATU\d{8}", "PL": r"PL\d{10}", "CH": r"CHE\d{9}(MWST|TVA|IVA)?",
}


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def siren_ok(value: str) -> bool:
    v = re.sub(r"\s", "", value or "")
    return bool(re.fullmatch(r"\d{9}", v)) and _luhn(v)


def siret_ok(value: str) -> bool:
    v = re.sub(r"\s", "", value or "")
    if not re.fullmatch(r"\d{14}", v):
        return False
    if v.startswith("356000000"):                      # exception historique La Poste : somme multiple de 5
        return sum(int(c) for c in v) % 5 == 0
    return _luhn(v)


def fr_vat_ok(value: str, siren: str) -> bool:
    v = re.sub(r"\s", "", (value or "").upper())
    m = re.fullmatch(r"FR(\d{2})(\d{9})", v)
    if not m or m.group(2) != re.sub(r"\s", "", siren or ""):
        return False
    return int(m.group(1)) == (12 + 3 * (int(m.group(2)) % 97)) % 97


def vat_ok(value: str, country: str, siren: str = "") -> bool:
    v = re.sub(r"[\s.\-]", "", (value or "").upper())
    if country == "FR":
        return fr_vat_ok(v, siren)
    pat = VAT_PATTERNS.get(country)
    return bool(pat and re.fullmatch(pat, v))


def check(app: dict, today: date = None) -> dict:
    """Retourne {'ok': bool, 'checks': [(libellé, ok, détail)], 'errors': [...]}. N'approuve rien."""
    today = today or date.today()
    c = app.get("country")
    checks = []

    def add(label, ok, detail=""):
        checks.append({"label": label, "ok": bool(ok), "detail": detail})

    add("Pays desservi", c in COUNTRIES, "" if c in COUNTRIES else "Pays non pris en charge")
    if c == "FR":
        add("SIREN valide (clé de contrôle)", siren_ok(app.get("company_id", "")), "9 chiffres")
        if app.get("siret"):
            add("SIRET valide (clé de contrôle)", siret_ok(app["siret"]) and re.sub(r"\s", "", app["siret"]).startswith(
                re.sub(r"\s", "", app.get("company_id", ""))), "14 chiffres commençant par le SIREN")
    else:
        add("Numéro d'entreprise renseigné", len(app.get("company_id", "")) >= 5)
    add("N° de TVA au bon format", vat_ok(app.get("vat", ""), c, app.get("company_id", "")),
        "Format vérifié ; l'activité du numéro (VIES) est contrôlée par un humain")
    add("Licence / autorisation de transport renseignée", len(app.get("licence", "")) >= 4)
    try:
        exp = date.fromisoformat(app.get("insurance_until", ""))
        add(f"Assurance valable au moins {MIN_INSURANCE_DAYS} jours", exp >= today + timedelta(days=MIN_INSURANCE_DAYS),
            f"échéance {exp.isoformat()}")
    except ValueError:
        add("Date d'échéance de l'assurance lisible", False)
    cover = app.get("insurance_cover_eur") or 0
    add(f"Garantie RC marchandises ≥ {MIN_CMR_COVER_EUR:,} € par sinistre".replace(",", " "), cover >= MIN_CMR_COVER_EUR,
        f"{cover:,.0f} € déclarés".replace(",", " "))
    add("Au moins un type de véhicule", bool(app.get("equipment")))
    add("Charte transporteur acceptée", app.get("accept_charter") is True)
    errors = [f"{x['label']}" + (f" ({x['detail']})" if x["detail"] else "") for x in checks if not x["ok"]]
    return {"ok": not errors, "checks": checks, "errors": errors}
