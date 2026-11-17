"""Vérifications officielles EN LIGNE d'une candidature transporteur (THÉORIQUE : nécessite Internet, non testé ici contre les vrais services).

- Annuaire des entreprises (API publique et gratuite recherche-entreprises.api.gouv.fr, données Sirene) : l'entreprise existe-t-elle et est-elle active ?
- VIES (Commission européenne) : le numéro de TVA intracommunautaire est-il actif ?
Les résultats s'AJOUTENT aux contrôles de forme et sont montrés à l'humain qui approuve ; ils ne décident jamais seuls.
Chaque fonction accepte `opener` pour être testée sans réseau.
"""
import json
import re
import urllib.parse
import urllib.request

SIRENE = "https://recherche-entreprises.api.gouv.fr/search?q={q}&per_page=3"
VIES = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc}/vat/{num}"


def _get(url, opener):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "FRETRAU-verification"})
    with opener(req, timeout=12) as r:
        return json.loads(r.read())


def sirene_check(siren: str, opener=urllib.request.urlopen) -> dict:
    siren = re.sub(r"\s", "", siren or "")
    try:
        data = _get(SIRENE.format(q=urllib.parse.quote(siren)), opener)
        for res in data.get("results", []):
            if res.get("siren") == siren:
                active = res.get("etat_administratif") == "A"
                return {"source": "annuaire-entreprises", "ok": active, "found": True, "name": res.get("nom_complet", ""),
                        "detail": "Entreprise active" if active else "Entreprise NON active (cessée ?)"}
        return {"source": "annuaire-entreprises", "ok": False, "found": False, "detail": "SIREN introuvable dans l'annuaire"}
    except Exception as e:
        return {"source": "annuaire-entreprises", "ok": None, "found": None, "detail": f"Vérification indisponible : {str(e)[:80]}"}


def vies_check(country: str, vat: str, opener=urllib.request.urlopen) -> dict:
    num = re.sub(r"[\s.\-]", "", (vat or "").upper())
    if num.startswith(country):
        num = num[len(country):]
    try:
        data = _get(VIES.format(cc=country, num=urllib.parse.quote(num)), opener)
        ok = bool(data.get("isValid"))
        return {"source": "VIES", "ok": ok, "name": data.get("name", ""), "detail": "Numéro de TVA actif" if ok else "Numéro de TVA NON valide dans VIES"}
    except Exception as e:
        return {"source": "VIES", "ok": None, "detail": f"Vérification indisponible : {str(e)[:80]}"}


def run_all(app: dict, opener=urllib.request.urlopen) -> list:
    out = []
    if app.get("country") == "FR":
        out.append(sirene_check(app.get("company_id", ""), opener))
    if app.get("country") != "CH":
        out.append(vies_check(app.get("country", ""), app.get("vat", ""), opener))
    return out
