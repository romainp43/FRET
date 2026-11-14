"""Pages de contenu du site : textes et rendu HTML (tout est échappé, aucun script ni style inline)."""
import html
import os

e = html.escape

# (clé, libellé de menu, mode de devis pré-sélectionné, option pré-cochée)
FREIGHT = {
    "palettes": {
        "nav": "Palettes et groupage", "mode": "LTL", "option": None,
        "title": "Transport de palettes : prix immédiat",
        "lead": "Pour quelques palettes qui ne remplissent pas un camion. Deux codes postaux suffisent pour obtenir un prix.",
        "what": "Le groupage consiste à faire voyager vos palettes avec celles d'autres expéditeurs. Vous payez la place "
                "et le poids réellement utilisés, pas le camion entier. Le prix dépend du nombre de palettes, du poids, "
                "de la distance et des services demandés à la livraison : hayon, rendez-vous, livraison chez un particulier.",
        "fit": ["De 1 à 6 palettes environ", "Des envois réguliers vers des destinataires différents",
                "Un budget serré, quand un jour de délai en plus est acceptable"],
        "faq": [("Que faut-il indiquer pour un prix exact ?", "Les deux codes postaux suffisent pour une première estimation. "
                 "Le nombre de palettes, le poids total et la nature de la marchandise la rendent exacte."),
                ("Mon destinataire n'a pas de quai, est-ce un problème ?", "Non : cochez l'option hayon élévateur, le camion "
                 "dépose alors les palettes au sol."),
                ("Quel est le poids maximal par palette ?", "1 000 kg par palette pour un prix automatique. Au-delà, "
                 "demandez un devis sur mesure.")],
    },
    "camion-complet": {
        "nav": "Camion complet", "mode": "FTL", "option": None,
        "title": "Camion complet : un véhicule dédié, un prix ferme",
        "lead": "Un semi-remorque pour vous seul, de l'enlèvement à la livraison, sans rupture de charge.",
        "what": "En camion complet, le véhicule ne transporte que votre marchandise : jusqu'à 33 palettes et 24 tonnes. "
                "Il va directement du point de chargement au point de livraison, ce qui réduit les manipulations et les délais. "
                "Le prix est calculé à la distance, avec l'indexation gazole du moment.",
        "fit": ["À partir de 15 à 20 palettes ou de 10 tonnes", "Une marchandise fragile ou de valeur, à ne pas transborder",
                "Une date de livraison ferme"],
        "faq": [("Quels véhicules proposez-vous ?", "Semi-remorque bâchée par défaut. Frigorifique et plateau sont proposés "
                 "en option dans le devis."),
                ("Le prix peut-il changer après la réservation ?", "Non, tant que l'envoi correspond à ce qui a été déclaré : "
                 "le prix réservé est le prix facturé."),
                ("En combien de temps le transporteur est-il trouvé ?", "Les transporteurs vérifiés reçoivent l'offre dès la "
                 "réservation. Vous êtes prévenu par e-mail dès que l'un d'eux est affecté.")],
    },
    "lot-partiel": {
        "nav": "Lot partiel", "mode": "PTL", "option": None,
        "title": "Lot partiel : entre la palette et le camion complet",
        "lead": "De 4 à 20 palettes : vous réservez une partie du plancher d'un camion, sans passage à quai.",
        "what": "Le lot partiel partage un camion entre quelques expéditeurs, mais sans transiter par des plateformes de tri : "
                "la marchandise reste à bord jusqu'à la livraison. C'est plus rapide et plus sûr que le groupage, et moins "
                "cher qu'un camion entier. Le prix dépend des mètres de plancher occupés et de la distance.",
        "fit": ["Entre 4 et 20 palettes", "Une marchandise qui supporte mal les manipulations", "Un envoi trop lourd pour le groupage"],
        "faq": [("Quelle différence avec le groupage ?", "Pas de rupture de charge : vos palettes ne changent pas de camion."),
                ("Le délai est-il garanti ?", "Le délai affiché est une estimation. Le camion pouvant charger pour d'autres "
                 "clients sur le trajet, prévoyez une marge d'une demi-journée.")],
    },
    "frigorifique": {
        "nav": "Frigorifique", "mode": "FTL", "option": "temperature",
        "title": "Transport frigorifique : température dirigée",
        "lead": "Produits frais, surgelés ou sensibles à la chaleur, en camion complet ou en palettes.",
        "what": "Le véhicule maintient une température de consigne pendant tout le trajet. Indiquez dans la description de "
                "la marchandise la plage de température attendue : elle est transmise au transporteur avec l'offre. "
                "L'option ajoute un supplément au prix de base, affiché ligne par ligne dans le devis.",
        "fit": ["Alimentaire frais ou surgelé", "Produits pharmaceutiques et cosmétiques", "Végétaux, peintures, produits craignant le gel"],
        "faq": [("Comment indiquer la température ?", "Dans le champ Marchandise lors de la réservation, par exemple "
                 "« produits laitiers, +2 à +4 °C »."),
                ("Tous les transporteurs peuvent-ils répondre ?", "Non : seuls ceux qui ont déclaré du matériel frigorifique "
                 "sont retenus par notre équipe.")],
    },
    "plateau": {
        "nav": "Plateau", "mode": "FTL", "option": "flatbed",
        "title": "Transport sur plateau",
        "lead": "Pour ce qui se charge par le côté ou par le haut : matériaux, machines, charpentes, bois.",
        "what": "Un plateau n'a ni parois ni toit : le chargement se fait à la grue, au pont roulant ou au chariot latéral. "
                "L'arrimage et le bâchage éventuel sont à préciser dans la description de la marchandise. "
                "Les convois exceptionnels (hors gabarit) ne sont pas chiffrés automatiquement : demandez un devis sur mesure.",
        "fit": ["Matériaux de construction, acier, bois", "Machines et engins", "Pièces longues qui n'entrent pas dans une remorque bâchée"],
        "faq": [("Mon chargement dépasse les dimensions habituelles, que faire ?", "Utilisez le formulaire de contact : "
                 "un conseiller étudie l'itinéraire et les autorisations nécessaires."),
                ("Qui arrime la marchandise ?", "Le chargement et le calage sont réalisés par l'expéditeur, l'arrimage par "
                 "le conducteur, sauf accord différent précisé à la réservation.")],
    },
    "express": {
        "nav": "Express", "mode": "FTL", "option": "urgent",
        "title": "Transport express",
        "lead": "Une ligne de production à l'arrêt, un client qui attend : départ au plus vite, trajet direct.",
        "what": "En express, le véhicule est affecté en priorité et roule sans détour ni arrêt intermédiaire. "
                "Le délai estimé est réduit d'une journée par rapport au service standard, et le supplément apparaît "
                "sur une ligne distincte du devis.",
        "fit": ["Dépannage industriel", "Rattrapage d'un retard", "Événement à date fixe"],
        "faq": [("Peut-on enlever le jour même ?", "Choisissez la date du jour dans le devis. La faisabilité dépend de "
                 "l'heure et des transporteurs disponibles à proximité : un conseiller vous confirme rapidement."),
                ("L'express existe-t-il pour une seule palette ?", "Oui, l'option s'applique aux trois types de transport.")],
    },
    "rail-route": {
        "nav": "Rail-route", "mode": None, "option": None,
        "title": "Transport combiné rail-route",
        "lead": "Sur les longues distances, la caisse voyage par le train entre deux terminaux, puis par camion.",
        "what": "Le transport combiné réduit le coût et les émissions sur les grands axes, au prix d'un délai un peu plus long "
                "et d'horaires de terminaux à respecter. Chaque demande est étudiée par un conseiller : il n'y a pas de "
                "prix automatique pour ce service.",
        "fit": ["Des trajets de plus de 600 km", "Des flux réguliers et planifiables", "Un objectif de réduction des émissions"],
        "faq": [("Pourquoi n'y a-t-il pas de prix immédiat ?", "Le prix dépend des places disponibles sur les trains et des "
                 "terminaux desservis : il doit être demandé aux opérateurs."),
                ("Comment faire une demande ?", "Par le formulaire de contact, en choisissant « Devis sur mesure ».")],
    },
}

GENERAL_FAQ = [
    ("Comment est calculé un prix ?", "Chaque devis part du trajet, du type de transport, du poids et de la date. Le barème "
     "est recalé en continu sur les prix réellement obtenus auprès des transporteurs, axe par axe."),
    ("En combien de temps ai-je mon prix ?", "Tout de suite sur le site. Par e-mail, la réponse part dès que la demande est lue "
     "par notre agent ; s'il manque une information, il vous la demande."),
    ("Possédez-vous des camions ?", "Non. Nous organisons le transport et le confions à un transporteur dont nous avons "
     "contrôlé la licence et l'assurance. N'étant liés à aucune flotte, nous comparons les offres."),
    ("Comment les transporteurs sont-ils contrôlés ?", "Existence et activité de l'entreprise auprès de l'INSEE, puis contrôle "
     "par notre équipe de la licence de transport, de l'attestation d'assurance, du Kbis et de l'attestation de vigilance."),
    ("Puis-je suivre mon envoi ?", "Oui, avec le code reçu par e-mail à la réservation, sur la page Suivre un envoi. "
     "Vous recevez aussi un message à chaque étape."),
    ("J'ai reçu un prix inférieur ailleurs.", "Envoyez-le depuis votre espace client, sur le devis concerné : "
     "un conseiller étudie un alignement."),
]

INDUSTRIES = ["Agroalimentaire et boissons", "Bâtiment et matériaux", "Industrie et mécanique", "Bois et ameublement",
              "Plasturgie et chimie", "Emballage et papier", "Textile", "Distribution et e-commerce", "Agriculture",
              "Métallurgie"]


def site() -> dict:
    g = os.environ.get
    return {"phone": g("FRETRAU_PHONE", ""), "email": g("FRETRAU_CONTACT_EMAIL", ""),
            "quote_email": g("FRETRAU_QUOTE_EMAIL", ""), "licence": g("FRETRAU_SELLER_LICENCE", ""),
            "company": g("FRETRAU_SELLER_NAME", "")}


def header() -> str:
    return ('<header class="top"><div class="wrap"><a class="brand" href="/">FRET<b>RAU</b></a>'
            '<nav><a href="/solutions">Solutions</a><a href="/clients">Clients</a><a href="/transporteur.html">Transporteurs</a>'
            '<a href="/tarifs">Tarifs</a><a href="/suivi">Suivre un envoi</a><a href="/portail.html">Espace client</a>'
            '<a class="nav-cta" href="/contact">Contact</a></nav></div></header>')


def footer() -> str:
    s = site()
    freight = "".join(f'<a href="/fret/{k}">{e(v["nav"])}</a>' for k, v in FREIGHT.items())
    contact = "".join(f"<span>{e(x)}</span>" for x in (s["phone"], s["email"]) if x)
    legal = (f"{e(s['company'])} — commissionnaire de transport inscrit au registre sous le n° {e(s['licence'])}."
             if s["company"] and s["licence"] else
             "Site de démonstration : aucune prestation de transport n'est vendue tant que la société n'est pas "
             "inscrite au registre des commissionnaires de transport.")
    return ('<footer><div class="wrap foot"><div><a class="brand" href="/">FRET<b>RAU</b></a>'
            f'<p>Courtage de fret routier, France et Europe.</p>{contact}</div>'
            '<div><b>Société</b><a href="/a-propos">À propos</a><a href="/solutions">Solutions</a>'
            '<a href="/clients">Clients</a><a href="/transporteur.html">Transporteurs</a><a href="/contact">Contact</a></div>'
            f'<div><b>Transports</b><a href="/tarifs">Vérificateur de tarif</a>{freight}</div>'
            '<div><b>Accès</b><a href="/suivi">Suivre un envoi</a><a href="/portail.html">Espace client</a>'
            '<a href="/transporteur.html">Espace transporteur</a><a href="/compte">Mon compte</a></div></div>'
            f'<div class="wrap legal">{legal}<span class="legal-links"><a href="/mentions-legales">Mentions légales</a>'
            '<a href="/cgu">Conditions d\'utilisation</a><a href="/cgv">Conditions de vente</a>'
            '<a href="/confidentialite">Confidentialité</a></span></div></footer>')


def layout(title: str, description: str, body: str, scripts=()) -> str:
    tags = "".join(f'<script src="{e(src)}"></script>' for src in scripts)
    return ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{e(title)} — FRETRAU</title><meta name=\"description\" content=\"{e(description)}\">"
            '<link rel="stylesheet" href="/styles.css"></head><body>'
            f"{header()}<main>{body}</main>{footer()}{tags}</body></html>")


def quick_form(mode="FTL", option=None, label="Voir mon prix") -> str:
    """Devis en deux codes postaux : simple formulaire GET vers la page d'accueil, qui calcule le prix."""
    radios = "".join(
        f'<input type="radio" name="mode" id="q-{k}" value="{k}"{" checked" if k == mode else ""}><label for="q-{k}">{e(v)}</label>'
        for k, v in (("FTL", "Camion complet"), ("PTL", "Lot partiel"), ("LTL", "Palettes")))
    opt = f'<input type="hidden" name="option" value="{e(option)}">' if option else ""
    return ('<form class="card quick" action="/" method="get"><h2>Prix immédiat</h2>'
            f'<div class="seg three" role="radiogroup" aria-label="Type de transport">{radios}</div>{opt}'
            '<div class="row"><div><label for="q-o">Code postal de départ</label>'
            '<input id="q-o" name="depart" inputmode="numeric" maxlength="5" pattern="[0-9]{5}" required placeholder="43290"></div>'
            '<div><label for="q-d">Code postal d\'arrivée</label>'
            '<input id="q-d" name="arrivee" inputmode="numeric" maxlength="5" pattern="[0-9]{5}" required placeholder="33000"></div></div>'
            f'<button class="full" type="submit">{e(label)}</button>'
            '<p class="muted small">Deux codes postaux suffisent. Vous précisez ensuite palettes, poids et date.</p></form>')


def faq_block(items, title="Questions fréquentes") -> str:
    rows = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in items)
    return f'<section class="block"><div class="wrap narrow"><h2>{e(title)}</h2><div class="faq">{rows}</div></div></section>'


def hero(title, lead, aside="") -> str:
    return (f'<section class="hero sub"><div class="wrap grid"><div><h1>{e(title)}</h1><p class="lead">{e(lead)}</p></div>'
            f"{aside}</div></section>")


def cards(items) -> str:
    return '<div class="steps">' + "".join(
        f'<div class="card"><h3>{e(t)}</h3><p class="muted">{e(d)}</p></div>' for t, d in items) + "</div>"


def freight_page(key: str):
    f = FREIGHT.get(key)
    if not f:
        return None
    aside = quick_form(f["mode"], f["option"]) if f["mode"] else (
        '<div class="card"><h2>Devis sur mesure</h2><p class="muted">Ce service est chiffré par un conseiller.</p>'
        '<a class="btn" href="/contact?sujet=devis">Faire une demande</a></div>')
    fit = "".join(f"<li>{e(x)}</li>" for x in f["fit"])
    others = "".join(f'<a class="chip" href="/fret/{k}">{e(v["nav"])}</a>' for k, v in FREIGHT.items() if k != key)
    body = (hero(f["title"], f["lead"], aside)
            + f'<section class="block"><div class="wrap two"><div><h2>En quoi ça consiste</h2><p>{e(f["what"])}</p></div>'
              f'<div><h2>Quand le choisir</h2><ul class="ticks">{fit}</ul></div></div></section>'
            + '<section class="block alt"><div class="wrap"><h2>Comment le prix est établi</h2>'
            + cards([("Le trajet", "Lieu d'enlèvement, lieu de livraison, type de véhicule et date."),
                     ("Le marché", "Le barème est recalé sur les prix réellement obtenus auprès des transporteurs sur cet axe."),
                     ("Un prix ferme", "Le prix affiché se réserve en ligne pendant 24 heures. Le prix réservé est le prix facturé.")])
            + "</div></section>" + faq_block(f["faq"])
            + f'<section class="block"><div class="wrap"><h2>Autres transports</h2><div class="chips">{others}</div></div></section>')
    return layout(f["title"], f["lead"], body)


def page_solutions():
    freight = "".join(f'<a class="card link" href="/fret/{k}"><h3>{e(v["nav"])}</h3><p class="muted">{e(v["lead"])}</p></a>'
                      for k, v in FREIGHT.items())
    s = site()
    mail = (f" ou écrivez à {s['quote_email']} dans la forme qui vous convient" if s["quote_email"] else "")
    body = (hero("Devis, réservation et suivi au même endroit",
                 "Pour les expéditeurs qui veulent un prix avant de s'engager, sans appeler plusieurs affréteurs. "
                 "Pour les transporteurs qui veulent des chargements réguliers et des règles de paiement claires.",
                 quick_form())
            + '<section class="block"><div class="wrap"><h2>Ce que fait la plateforme</h2>'
            + cards([("Prix immédiat", f"Saisissez deux codes postaux sur le site{mail} : le prix arrive tout de suite."),
                     ("Transporteurs contrôlés", "Aucun chargement n'est confié sans contrôle de l'entreprise, de sa licence et de son assurance."),
                     ("Prix ferme", "Le prix réservé est le prix facturé, tant que l'envoi correspond à la demande."),
                     ("Suivi à chaque étape", "Chargement, départ, livraison : vous êtes prévenu, et les retards sont signalés avant que vous ne les découvriez."),
                     ("Alignement de prix", "Un prix inférieur reçu ailleurs pour le même envoi ? Transmettez-le, un conseiller l'étudie."),
                     ("Des personnes derrière l'outil", "Les agents automatiques traitent le courant. Dès qu'un dossier sort du cadre, un conseiller le reprend.")])
            + '</div></section><section class="block alt"><div class="wrap"><h2>Les transports chiffrés</h2>'
            + f'<div class="steps">{freight}</div></div></section>' + faq_block(GENERAL_FAQ))
    return layout("Solutions", "Devis immédiat, transporteurs contrôlés, prix ferme et suivi de bout en bout.", body)


def page_clients():
    industries = "".join(f'<span class="chip">{e(x)}</span>' for x in INDUSTRIES)
    body = (hero("Conçu pour les deux côtés du chargement",
                 "Que vous expédiiez de la marchandise ou que vous la transportiez, chaque étape est plus simple.")
            + '<section class="block"><div class="wrap"><h2>Expéditeurs</h2>'
            + cards([("Pris en charge de bout en bout", "Vous réservez, nous trouvons le transporteur contrôlé, planifions l'enlèvement et vous informons à chaque étape."),
                     ("Les imprévus traités", "Un camion en retard, un enlèvement manqué : l'alerte arrive chez nous d'abord, avec une solution."),
                     ("Une facture claire", "Un prix ferme, une facture par transport, une échéance à 30 jours.")])
            + '<p class="center"><a class="btn" href="/">Obtenir un prix</a></p></div></section>'
            + '<section class="block alt"><div class="wrap"><h2>Transporteurs</h2>'
            + cards([("Un règlement prévisible", "Paiement à 30 jours après la preuve de livraison. Le prix accepté est le prix payé."),
                     ("Des chargements réguliers", "Les offres vous sont proposées selon votre base, votre matériel et vos axes."),
                     ("Un interlocuteur", "Attente au quai, enlèvement décalé : nous réglons la question avec l'expéditeur pendant que vous roulez.")])
            + '<p class="center"><a class="btn" href="/transporteur.html">Rejoindre le réseau</a></p></div></section>'
            + f'<section class="block"><div class="wrap"><h2>Secteurs servis</h2><div class="chips">{industries}</div></div></section>')
    return layout("Clients", "Une plateforme pour les expéditeurs et pour les transporteurs.", body)


def page_about():
    s = site()
    status = (f"{s['company']} est inscrite au registre des commissionnaires de transport sous le n° {s['licence']}."
              if s["company"] and s["licence"] else
              "La société est en cours de création : ce site est une démonstration du service.")
    body = (hero("À propos de FRETRAU", "Un courtier en fret routier né en Haute-Loire, qui veut rendre l'achat de transport "
                 "aussi simple que n'importe quel achat en ligne.")
            + '<section class="block"><div class="wrap two"><div><h2>Pourquoi</h2><p>Le transport routier fonctionne encore '
              "beaucoup au téléphone et par e-mail : des heures d'attente pour un prix, des tarifs qui varient sans explication, "
              "peu de visibilité une fois le camion parti. Nous réunissons le devis, la réservation et le suivi dans un seul "
              'outil, avec une équipe qui reprend la main dès que c\'est nécessaire.</p></div>'
              f'<div><h2>Notre statut</h2><p>{e(status)}</p><p>Nous ne possédons pas de camions : nous sélectionnons, pour chaque '
              "envoi, un transporteur dont l'entreprise, la licence et l'assurance ont été contrôlées.</p></div></div></section>"
            + '<section class="block alt"><div class="wrap"><h2>Ce qui nous guide</h2>'
            + cards([("Partir du client", "Comprendre ce qui ralentit vos expéditions, puis construire ce qui le résout."),
                     ("Gagner ensemble", "Le bon prix et le bon transporteur pour chaque envoi : votre intérêt est le nôtre."),
                     ("Rapide, sûr, humain", "L'outil pour la vitesse, les contrôles pour la sécurité, des personnes pour le reste.")])
            + "</div></section>" + faq_block(GENERAL_FAQ))
    return layout("À propos", "Courtier en fret routier basé en Haute-Loire.", body)


def page_tarifs():
    body = (hero("Vérificateur de tarif", "Comparez en une fois le prix d'un trajet en camion complet, en lot partiel et en palettes.")
            + '<section class="block"><div class="wrap narrow"><form id="rates-form" class="card"><div class="row">'
              '<div><label for="r-o">Code postal ou ville de départ</label><input id="r-o" required placeholder="43290"></div>'
              '<div><label for="r-d">Code postal ou ville d\'arrivée</label><input id="r-d" required placeholder="33000"></div></div>'
              '<button class="full" type="submit">Comparer</button><div id="rates-error" class="err hidden" role="alert"></div></form>'
              '<div id="rates-out" class="stack"></div>'
              '<p class="muted small">Estimations hors taxes sur des hypothèses standard, pour un enlèvement demain. '
              "Le prix ferme est celui du devis détaillé.</p></div></section>")
    return layout("Tarifs", "Estimez le prix d'un transport routier entre deux codes postaux.", body, ("/common.js", "/tarifs.js"))


def page_suivi():
    body = (hero("Suivre un envoi", "Saisissez le code reçu par e-mail à la réservation.")
            + '<section class="block"><div class="wrap narrow"><div class="card"><form id="track-form" class="row" novalidate>'
              '<input id="track-code" placeholder="FR-XXXXXXXXXXXX" aria-label="Code de suivi" autocomplete="off">'
              '<button type="submit">Suivre</button></form><div id="track-error" class="err hidden" role="alert"></div>'
              '<div id="track-result"></div></div></div></section>')
    return layout("Suivre un envoi", "Suivi d'expédition par code.", body, ("/common.js", "/suivi.js"))


def page_contact():
    s = site()
    direct = "".join(f"<p><b>{e(k)}</b> {e(v)}</p>" for k, v in (("Téléphone :", s["phone"]), ("E-mail :", s["email"])) if v)
    body = (hero("Parler à un conseiller", "Une question, un transport particulier, une demande de rappel : écrivez-nous.")
            + '<section class="block"><div class="wrap narrow"><form id="contact-form" class="card" novalidate>'
              '<div class="hp" aria-hidden="true"><label>Ne pas remplir<input name="website" tabindex="-1" autocomplete="off"></label></div>'
              '<label for="k-topic">Objet</label><select id="k-topic"><option value="rappel">Être rappelé</option>'
              '<option value="devis">Devis sur mesure (rail-route, hors gabarit, flux régulier)</option>'
              '<option value="transporteur">Je suis transporteur</option><option value="autre">Autre question</option></select>'
              '<div class="row"><div><label for="k-name">Nom</label><input id="k-name" autocomplete="name" required></div>'
              '<div><label for="k-company">Société</label><input id="k-company" autocomplete="organization" required></div></div>'
              '<div class="row"><div><label for="k-email">E-mail</label><input id="k-email" type="email" autocomplete="email" required></div>'
              '<div><label for="k-phone">Téléphone</label><input id="k-phone" type="tel" autocomplete="tel" required></div></div>'
              '<label for="k-message">Votre message</label><textarea id="k-message" required></textarea>'
              '<button class="full" type="submit">Envoyer</button><div id="contact-error" class="err hidden" role="alert"></div>'
              f'<div id="contact-ok" class="ok-box hidden">Message reçu : un conseiller vous répond rapidement.</div></form>{direct}</div></section>')
    return layout("Contact", "Contacter un conseiller ou demander un devis sur mesure.", body, ("/common.js", "/contact.js"))


PAGES = {"/solutions": page_solutions, "/clients": page_clients, "/a-propos": page_about, "/tarifs": page_tarifs,
         "/suivi": page_suivi, "/contact": page_contact}


def render(path: str):
    """HTML de la page de contenu, ou None si le chemin n'en est pas une."""
    if path in PAGES:
        return PAGES[path]()
    if path.startswith("/fret/"):
        return freight_page(path[6:])
    return None
