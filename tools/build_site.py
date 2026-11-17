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
    js = "".join(f'<script src="{u}"></script>' for u in (["/common.js"] + [x for x in script.split(",")] if script and script != "/forms.js" else ([script] if script else [])))
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)} — FRETRAU</title><meta name="description" content="{E(desc)}"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/styles.css">{ld}</head>
<body class="legal"><header class="top"><div class="wrap"><a class="brand" href="/"><img src="/logo-mark.svg" alt="" width="28" height="28">FRET<b>RAU</b></a><nav>{nav}</nav></div></header>
<main class="wrap page">{body}</main>
{footer()}{js}</body></html>
"""


def footer():
    return ('<footer><div class="wrap"><span>© FRETRAU</span><a href="/a-propos.html">À propos</a>'
            '<a href="/reclamation.html">Réclamation</a><a href="/legal/mentions-legales.html">Mentions légales</a>'
            '<a href="/legal/cgv.html">CGV</a><a href="/legal/cgu.html">CGU</a><a href="/legal/confidentialite.html">Confidentialité</a>'
            '<a href="/legal/cookies.html">Cookies</a><a href="/confidentialite-choix.html">Vos choix</a><a href="/compte.html">Espace client</a><a href="/estimation.html">Estimation PTL / combiné</a>'
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
        ("account", "Compte entreprise / contrat annuel"), ("claim", "Question sur un envoi"), ("privacy", "Exercice de mes droits (données personnelles)"), ("other", "Autre")])
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


def driver_page():
    body = """<h1>Partager ma position — livraison</h1>
<p class="lead2">Votre position n'est envoyée que si vous appuyez sur « Accepter et partager », uniquement pendant cette livraison, et vous pouvez arrêter à tout moment. Elle est supprimée sous 30 jours.</p>
<div class="card" id="drv-card"><p id="drv-status" class="muted" role="status">Vérification du lien…</p>
<button id="drv-start" class="full hidden" type="button">Accepter et partager ma position</button>
<button id="drv-stop" class="full alt hidden" type="button">Arrêter le partage</button>
<div id="drv-error" class="err hidden" role="alert"></div></div>
<p class="muted small">Gardez cette page ouverte pendant la route. Nous ne collectons ni votre nom ni votre numéro. Aucune position n'est transmise sans votre accord.</p>"""
    return shell("Partage de position chauffeur", "Partager sa position pour une livraison FRETRAU.", body, None, "/chauffeur.js")


def account_page():
    body = """<h1>Mon espace client</h1>
<p class="lead2">Retrouvez vos envois. Pas de mot de passe : un code à 6 chiffres vous est envoyé par e-mail.</p>
<form id="acct-form" class="card" novalidate>
<label for="a-email">E-mail utilisé pour vos réservations</label><input id="a-email" name="email" type="email" autocomplete="email" required>
<button id="acct-send" class="full" type="submit">Recevoir mon code</button>
<div id="acct-code-box" class="hidden"><label for="a-code">Code reçu par e-mail</label><input id="a-code" name="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code">
<button id="acct-verify" class="full" type="button">Me connecter</button></div>
<div id="acct-msg" class="muted" role="status"></div><div id="acct-error" class="err hidden" role="alert"></div></form>
<div id="acct-list"></div>"""
    return shell("Mon espace client", "Consultez vos envois FRETRAU.", body, None, "/compte.js")


def estimate_page():
    body = """<h1>Estimation lot partiel et combiné rail-route</h1>
<p class="lead2">Ces deux modes ne se réservent pas en ligne : voici une fourchette indicative, puis nous vous envoyons un devis ferme après étude.</p>
<form id="est-form" class="card" novalidate>
<label for="e-kind">Mode</label><select id="e-kind" name="kind"><option value="PTL">Lot partiel (quelques palettes)</option><option value="IM">Combiné rail-route (à partir de 600 km)</option></select>
<div class="row"><div><label for="e-o">Départ (ville)</label><input id="e-o" name="origin" required autocomplete="off"></div><div><label for="e-d">Arrivée (ville)</label><input id="e-d" name="destination" required autocomplete="off"></div></div>
<div class="row"><div><label for="e-p">Palettes</label><input id="e-p" name="pallets" type="number" min="1" max="33" value="6"></div><div><label for="e-w">Poids (kg)</label><input id="e-w" name="weight_kg" type="number" min="1" value="2500"></div></div>
<button class="full" type="submit">Estimer</button><div id="est-error" class="err hidden" role="alert"></div></form>
<div id="est-result"></div>
<p class="muted small">Fourchette sans engagement, basée sur des hypothèses de travail (pas encore sur des tarifs de marché). <a href="/contact.html">Demander un devis ferme</a>.</p>"""
    return shell("Estimation indicative", "Estimation lot partiel ou combiné rail-route.", body, None, "/estimate.js")


def privacy_choices_page():
    body = """<h1>Vos choix de confidentialité</h1>
<div class="card"><h2>Ne plus recevoir de SMS</h2>
<p>Entrez votre numéro : nous cessons immédiatement tout SMS vers ce numéro (les e-mails de service liés à un transport en cours restent envoyés).</p>
<form id="stop-form" novalidate><div class="hp" aria-hidden="true"><label>Ne pas remplir<input name="website" tabindex="-1" autocomplete="off"></label></div>
<label for="s-phone">Téléphone</label><input id="s-phone" name="phone" type="tel" autocomplete="tel" required>
<button class="full" type="submit">Arrêter les SMS</button><div id="stop-msg" class="muted" role="status"></div><div id="stop-error" class="err hidden" role="alert"></div></form></div>
<div class="card"><h2>Accéder à mes données, les corriger ou les supprimer</h2><p>Faites une demande via le <a href="/contact.html">formulaire de contact</a> en choisissant le sujet « Exercice de mes droits ». Nous répondons sous un mois.</p></div>
<div class="card"><h2>Cookies et traceurs</h2><p>FRETRAU n'utilise aucun traceur publicitaire ni outil de mesure d'audience tiers. Voir la <a href="/legal/cookies.html">page cookies</a>.</p></div>"""
    return shell("Choix de confidentialité", "Gérer vos SMS et exercer vos droits.", body, None, "/privacy.js")


def tracking_page():
    body = """<h1>Suivre un envoi</h1>
<form id="track-form" class="card row" novalidate><input id="track-code" placeholder="FR-XXXXXXXXXXXX" aria-label="Code de suivi" autocomplete="off"><button type="submit">Suivre</button></form>
<div id="track-error" class="err hidden" role="alert"></div><div id="track-result"></div>
<p class="muted small">Un problème sur un envoi ? <a href="/reclamation.html">Déclarez-le ici</a>. Retrouver tous vos envois : <a href="/compte.html">espace client</a>.</p>"""
    return shell("Suivi d'envoi", "Suivez votre envoi FRETRAU avec son code.", body, None, "/suivi.js")


def pages():
    out = {"a-propos.html": about(), "secteurs.html": sectors(), "faq.html": faq_page(), "transporteurs.html": carriers_page(),
           "contact.html": contact_page(), "reclamation.html": claim_page(), "chauffeur.html": driver_page(), "compte.html": account_page(),
           "estimation.html": estimate_page(), "confidentialite-choix.html": privacy_choices_page(), "suivi.html": tracking_page()}
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
