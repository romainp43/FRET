#!/usr/bin/env python3
"""Génère les pages publiques (services, à propos, secteurs, FAQ, transporteurs, contact, réclamation) dans web/.

  python3 tools/build_site.py

Les textes viennent de tools/site_content.py, les coordonnées de config/company.json (comme les pages légales).
Aucun script en ligne (CSP stricte) : les formulaires sont gérés par web/forms.js.
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import site_content as C  # noqa: E402
from fretrau import claims as claims_mod, vetting  # noqa: E402

E = html.escape
NAV = [("/#services", "Services"), ("/secteurs.html", "Secteurs"), ("/faq.html", "Questions fréquentes"),
       ("/transporteurs.html", "Transporteurs"), ("/contact.html", "Contact"), ("/#suivi", "Suivre un envoi")]
SOCIAL_NOTE = ""


def shell(title, desc, body, jsonld=None, script=None):
    nav = "".join(f'<a href="{u}">{E(t)}</a>' for u, t in NAV)
    ld = ("<script type=\"application/ld+json\">" + json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/") + "</script>") if jsonld else ""
    js = f'<script src="{script}"></script>' if script else ""
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)} — FRETRAU</title><meta name="description" content="{E(desc)}"><link rel="stylesheet" href="/styles.css">{ld}</head>
<body class="legal"><header class="top"><div class="wrap"><a class="brand" href="/">FRET<b>RAU</b></a><nav>{nav}</nav></div></header>
<main class="wrap page">{body}</main>
{footer()}{js}</body></html>
"""


def footer():
    return ('<footer><div class="wrap"><span>© FRETRAU</span><a href="/a-propos.html">À propos</a>'
            '<a href="/reclamation.html">Réclamation</a><a href="/legal/mentions-legales.html">Mentions légales</a>'
            '<a href="/legal/cgv.html">CGV</a><a href="/legal/cgu.html">CGU</a><a href="/legal/confidentialite.html">Confidentialité</a>'
            '<a href="/legal/cookies.html">Cookies</a>'
            '<span class="muted small">Données géographiques : GeoNames (CC BY 4.0) et geo.api.gouv.fr (Licence Ouverte).</span></div></footer>')


def faq_html(items):
    return "".join(f"<details><summary>{E(q)}</summary><p>{E(a)}</p></details>" for q, a in items)


def faq_ld(items):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]}


def cta():
    return '<p class="cta"><a class="btn" href="/#quote-card">Obtenir un prix maintenant</a> <a class="btn alt" href="/contact.html">Parler à un expert</a></p>'


def service_page(slug, s):
    items = s["faq"] + C.COMMON_Q[:1] + C.COMMON_Q[2:4]
    body = (f'<p class="crumb"><a href="/#services">Services</a> › {E(s["title"])}</p><h1>{E(s["title"])}</h1>'
            f'<p class="lead2">{E(s["intro"])}</p>{cta()}'
            f'<h2>Ce que vous obtenez</h2><ul>{"".join(f"<li>{E(x)}</li>" for x in s["what"])}</ul>'
            f'<h2>Quand choisir ce service</h2><ul>{"".join(f"<li>{E(x)}</li>" for x in s["fits"])}</ul>'
            f'<h2>Comment ça marche</h2><ol><li>Vous indiquez le trajet et la marchandise : le prix s\'affiche (ou vous demandez un devis).</li>'
            f'<li>Vous réservez : nous retenons un transporteur contrôlé (licence, assurance, équipement).</li>'
            f'<li>Vous suivez l\'envoi avec votre code et téléchargez la lettre de voiture.</li></ol>'
            f'<h2>Questions fréquentes</h2>{faq_html(items)}{cta()}')
    return shell(s["title"], s["short"], body, faq_ld(items))


def cards(items, link=True):
    out = ""
    for slug, s in items:
        out += f'<a class="svc" href="/services/{slug}.html"><b>{E(s["title"])}</b><span>{E(s["short"])}</span></a>'
    return f'<div class="svc-grid">{out}</div>'


def about():
    vals = "".join(f"<li><b>{E(t)}</b> — {E(d)}</li>" for t, d in C.VALUES)
    body = ('<h1>À propos de FRETRAU</h1>'
            '<p class="lead2">FRETRAU est un courtier en transport routier pour la France et l\'Europe : un prix en quelques secondes, '
            'un transporteur contrôlé, un suivi de bout en bout.</p>'
            '<h2>Notre mission</h2><p>Le transport routier reste trop souvent organisé par téléphone et par e-mail, avec des délais de réponse longs, '
            'des prix peu comparables et peu de visibilité après l\'enlèvement. Notre objectif : rendre le transport aussi simple et fiable qu\'un achat en ligne, '
            'avec des assistants automatiques pour le travail de routine et des personnes pour les exceptions.</p>'
            '<h2>Ce que nous faisons</h2><p>Nous organisons des transports en camion complet et en palettes (groupage) en France et en Europe. '
            'Après votre réservation, nos agents sélectionnent un transporteur conforme, comparent les offres et suivent l\'envoi jusqu\'à la livraison. '
            'Nous ne possédons pas de camions : nous pouvons ainsi comparer plusieurs transporteurs.</p>'
            f'<h2>Nos engagements</h2><ul>{vals}</ul>'
            '<h2>Cadre légal</h2><p>FRETRAU agit en qualité de commissionnaire de transport. Dénomination, adresse et inscription au registre sont indiquées dans les '
            '<a href="/legal/mentions-legales.html">mentions légales</a>.</p>'
            f'<h2>Questions fréquentes</h2>{faq_html(C.GENERAL_FAQ[:6])}{cta()}')
    return shell("À propos", "Qui est FRETRAU et comment fonctionne le courtage de fret routier.", body, faq_ld(C.GENERAL_FAQ[:6]))


def sectors():
    items = "".join(f'<li class="card"><b>{E(t)}</b><span class="muted">{E(d)}</span></li>' for t, d in C.SECTORS)
    body = (f'<h1>Les secteurs que nous transportons</h1><p class="lead2">Quelle que soit votre activité, le principe reste le même : un prix clair, '
            f'un transporteur contrôlé et un suivi. Voici des exemples de flux que nous organisons.</p><ul class="sector-grid">{items}</ul>'
            f'<p>Votre secteur n\'est pas listé ? <a href="/contact.html">Écrivez-nous</a>.</p><h2>Services</h2>{cards(C.SERVICES.items())}{cta()}')
    return shell("Secteurs", "Secteurs d'activité transportés par FRETRAU.", body)


def faq_page():
    allq = list(C.GENERAL_FAQ)
    body = f'<h1>Questions fréquentes</h1>{faq_html(allq)}<h2>Une autre question ?</h2><p><a href="/contact.html">Contactez-nous</a>.</p>'
    return shell("Questions fréquentes", "Réponses sur les prix, la réservation, le suivi, les réclamations et les transporteurs.", body, faq_ld(allq))


def form_field(name, label, typ="text", required=True, extra=""):
    return f'<label for="f-{name}">{E(label)}</label><input id="f-{name}" name="{name}" type="{typ}" {"required" if required else ""} {extra}>'


def carriers_page():
    equip = "".join(f'<label class="checks"><input type="checkbox" name="equipment" value="{k}"> {E(v)}</label>' for k, v in vetting.EQUIPMENT.items())
    ctry = "".join(f'<label class="checks"><input type="checkbox" name="countries" value="{k}"> {E(v)}</label>' for k, v in vetting.COUNTRIES.items())
    opts = "".join(f'<option value="{k}">{E(v)}</option>' for k, v in vetting.COUNTRIES.items())
    body = f"""<h1>Transporteurs : travaillons ensemble</h1>
<p class="lead2">Des chargements réguliers, des conditions de paiement claires, moins de kilomètres à vide. Déposez votre dossier : nous contrôlons l'entreprise, la licence et l'assurance avant de vous confier un transport.</p>
<form id="carrier-form" class="card" novalidate>
<div class="hp" aria-hidden="true"><label>Ne pas remplir<input name="website" tabindex="-1" autocomplete="off"></label></div>
<h2>Votre entreprise</h2>
<div class="row"><div>{form_field("company", "Raison sociale")}</div><div><label for="f-country">Pays d'immatriculation</label><select id="f-country" name="country">{opts}</select></div></div>
<div class="row"><div>{form_field("company_id", "SIREN (France) ou n° d'entreprise")}</div><div>{form_field("siret", "SIRET (facultatif, France)", required=False)}</div></div>
<div class="row"><div>{form_field("vat", "N° de TVA intracommunautaire")}</div><div>{form_field("licence", "N° de licence / autorisation de transport")}</div></div>
<h2>Assurance</h2>
<div class="row"><div>{form_field("insurer", "Assureur")}</div><div>{form_field("insurance_until", "Fin de validité de l'assurance", "date")}</div></div>
{form_field("insurance_cover_eur", "Garantie marchandises transportées, par sinistre (€)", "number", extra='min="1" inputmode="numeric"')}
<h2>Flotte</h2>
{form_field("fleet_size", "Nombre de véhicules", "number", extra='min="1" max="5000" inputmode="numeric"')}
<label>Véhicules et équipements</label><div class="checks-col">{equip}</div>
<label>Pays desservis</label><div class="checks-col">{ctry}</div>
<h2>Contact</h2>
<div class="row"><div>{form_field("contact_name", "Nom du contact")}</div><div>{form_field("phone", "Téléphone", "tel")}</div></div>
{form_field("email", "E-mail", "email")}
<label class="checks"><input type="checkbox" name="accept_charter"> J'accepte la charte transporteur : licence et assurance en règle et vérifiables, signature de la lettre de voiture, pas de sous-traitance sans accord écrit de FRETRAU, délai de paiement après preuve de livraison. Mes données servent à examiner ma candidature (<a href="/legal/confidentialite.html" target="_blank" rel="noopener">politique de confidentialité</a>).</label>
<button class="full" type="submit">Envoyer ma candidature</button>
<div id="form-msg" class="muted" role="status"></div><div id="form-error" class="err hidden" role="alert"></div>
</form>
<h2>Questions fréquentes</h2>{faq_html(C.CARRIER_FAQ)}"""
    return shell("Transporteurs", "Rejoignez le réseau de transporteurs FRETRAU.", body, faq_ld(C.CARRIER_FAQ), "/forms.js")


def contact_page():
    topics = "".join(f'<option value="{k}">{E(v)}</option>' for k, v in [
        ("quote", "Demande de prix"), ("intermodal", "Combiné rail-route (sur devis)"), ("special", "Transport spécial / hors gabarit"),
        ("account", "Compte entreprise / contrat annuel"), ("claim", "Question sur un envoi"), ("other", "Autre")])
    body = f"""<h1>Parler à un expert</h1>
<p class="lead2">Une question, un transport particulier, un contrat annuel : laissez-nous un message et un créneau de rappel, nous vous répondons.</p>
<div class="row"><form id="contact-form" class="card" novalidate>
<div class="hp" aria-hidden="true"><label>Ne pas remplir<input name="website" tabindex="-1" autocomplete="off"></label></div>
<label for="f-topic">Sujet</label><select id="f-topic" name="topic">{topics}</select>
<div class="row"><div>{form_field("name", "Nom")}</div><div>{form_field("company", "Société", required=False)}</div></div>
<div class="row"><div>{form_field("email", "E-mail", "email")}</div><div>{form_field("phone", "Téléphone (facultatif)", "tel", required=False)}</div></div>
{form_field("slot", "Créneau de rappel souhaité (facultatif)", required=False, extra='placeholder="Ex. mardi après-midi"')}
<label for="f-message">Votre message</label><textarea id="f-message" name="message" rows="5" maxlength="1500" required></textarea>
<label class="checks"><input type="checkbox" name="consent"> J'accepte que FRETRAU traite ces informations pour me répondre (<a href="/legal/confidentialite.html" target="_blank" rel="noopener">politique de confidentialité</a>).</label>
<button class="full" type="submit">Envoyer</button><div id="form-msg" class="muted" role="status"></div><div id="form-error" class="err hidden" role="alert"></div></form>
<div class="card"><h2>Coordonnées</h2><p>E-mail : [[email]]<br>Téléphone : [[phone]]</p><p class="muted small">Pour un prix, le plus rapide reste le <a href="/#quote-card">calculateur</a>.</p></div></div>"""
    return shell("Contact", "Contactez un expert FRETRAU.", body, None, "/forms.js")


def claim_page():
    kinds = "".join(f'<option value="{k}">{E(v)}</option>' for k, v in claims_mod.KINDS.items())
    body = f"""<h1>Déclarer un problème sur un envoi</h1>
<p class="lead2">Avarie, manque, perte ou retard : déclarez-le ici. Nous calculons vos délais légaux et notre équipe traite la réclamation avec le transporteur.</p>
<div class="card"><p><b>À faire dès la livraison :</b> inscrivez des réserves précises et datées sur le récépissé du transporteur, photographiez la marchandise et l'emballage. Ces preuves sont les plus importantes.</p></div>
<form id="claim-form" class="card" novalidate>
<div class="hp" aria-hidden="true"><label>Ne pas remplir<input name="website" tabindex="-1" autocomplete="off"></label></div>
<div class="row"><div>{form_field("tracking_code", "Code de suivi (FR-…)", extra='autocomplete="off"')}</div><div>{form_field("email", "E-mail de la réservation", "email")}</div></div>
<div class="row"><div><label for="f-kind">Nature du problème</label><select id="f-kind" name="kind">{kinds}</select></div><div>{form_field("delivered_on", "Date de livraison", "date")}</div></div>
<label for="f-description">Description</label><textarea id="f-description" name="description" rows="5" maxlength="1500" required></textarea>
{form_field("amount_eur", "Montant estimé du préjudice (€, facultatif)", "number", required=False, extra='min="1" inputmode="decimal"')}
<label class="checks"><input type="checkbox" name="reserves_on_receipt"> J'ai inscrit des réserves sur le récépissé à la livraison</label>
<button class="full" type="submit">Déclarer</button><div id="form-msg" class="muted" role="status"></div><div id="form-error" class="err hidden" role="alert"></div></form>
<div id="claim-deadlines"></div>
<p class="muted small">Délais indicatifs (à faire valider par votre conseil) : en France, protestation motivée par lettre recommandée sous 3 jours hors dimanches et jours fériés ; à l'international (CMR), 7 jours pour un dommage non apparent, 21 jours pour un retard ; prescription d'un an.</p>"""
    return shell("Réclamation", "Déclarer une avarie, un manque, une perte ou un retard.", body, None, "/forms.js")


def pages():
    out = {"a-propos.html": about(), "secteurs.html": sectors(), "faq.html": faq_page(), "transporteurs.html": carriers_page(),
           "contact.html": contact_page(), "reclamation.html": claim_page()}
    for slug, s in C.SERVICES.items():
        out[f"services/{slug}.html"] = service_page(slug, s)
    return out


def main():
    with open(os.path.join(ROOT, "config", "company.json"), encoding="utf-8") as f:
        company = json.load(f)
    n = 0
    for rel, h in pages().items():
        for k, v in company.items():
            h = h.replace(f"[[{k}]]", E(str(v)))
        path = os.path.join(ROOT, "web", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(h)
        n += 1
    # fragment réutilisé par la page d'accueil (grille des services)
    print(f"{n} pages générées dans web/")


if __name__ == "__main__":
    main()
