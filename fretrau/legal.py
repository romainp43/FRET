"""Pages légales : mentions légales, conditions d'utilisation, conditions de vente, confidentialité.

MODÈLES À FAIRE VALIDER PAR UN AVOCAT avant mise en ligne. Les informations de la société viennent des
variables d'environnement FRETRAU_SELLER_* et FRETRAU_HOST_* ; tant qu'elles manquent, un bandeau le signale.
"""
import os

from . import content

e = content.e
UPDATED = "novembre 2026"


def company() -> dict:
    g = os.environ.get
    return {"name": g("FRETRAU_SELLER_NAME", ""), "form": g("FRETRAU_SELLER_FORM", ""),
            "address": g("FRETRAU_SELLER_ADDRESS", ""), "siret": g("FRETRAU_SELLER_SIRET", ""),
            "vat": g("FRETRAU_SELLER_VAT", ""), "licence": g("FRETRAU_SELLER_LICENCE", ""),
            "rcs": g("FRETRAU_SELLER_RCS", ""), "director": g("FRETRAU_DIRECTOR", ""),
            "email": g("FRETRAU_CONTACT_EMAIL", ""), "phone": g("FRETRAU_PHONE", ""),
            "privacy_email": g("FRETRAU_PRIVACY_EMAIL", "") or g("FRETRAU_CONTACT_EMAIL", ""),
            "host": g("FRETRAU_HOST_NAME", ""), "host_address": g("FRETRAU_HOST_ADDRESS", ""),
            "insurer": g("FRETRAU_INSURER", ""), "mediator": g("FRETRAU_MEDIATOR", "")}


def v(value: str, what: str) -> str:
    """Valeur de la société, ou un repère visible tant qu'elle n'est pas renseignée."""
    return e(value) if value else f'<mark>[{e(what)} à renseigner]</mark>'


def doc(title: str, intro: str, sections: list) -> str:
    c = company()
    banner = "" if c["name"] and c["siret"] else (
        '<div class="err">Document provisoire : la société n\'est pas encore immatriculée. Les mentions entre crochets '
        "sont à compléter et le texte doit être relu par un avocat avant toute mise en ligne.</div>")
    toc = "".join(f'<li><a href="#s{i}">{e(h)}</a></li>' for i, (h, _) in enumerate(sections, 1))
    body = "".join(f'<h2 id="s{i}">{i}. {e(h)}</h2>{html}' for i, (h, html) in enumerate(sections, 1))
    page = (content.hero(title, intro)
            + f'<section class="block"><div class="wrap narrow legal-doc">{banner}<p class="muted">Dernière mise à jour : '
              f'{UPDATED}.</p><ol class="toc">{toc}</ol>{body}</div></section>')
    return content.layout(title, intro, page)


def p(*paragraphs) -> str:
    return "".join(f"<p>{x}</p>" for x in paragraphs)


def ul(*items) -> str:
    return "<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"


def page_mentions():
    c = company()
    return doc("Mentions légales", "Qui édite ce site et qui l'héberge.", [
        ("Éditeur du site", p(
            f"{v(c['name'], 'Raison sociale')}, {v(c['form'], 'forme juridique et capital')}, dont le siège est situé "
            f"{v(c['address'], 'adresse du siège')}.",
            f"SIRET : {v(c['siret'], 'SIRET')} — RCS : {v(c['rcs'], 'ville et numéro RCS')} — "
            f"TVA intracommunautaire : {v(c['vat'], 'numéro de TVA')}.",
            f"Téléphone : {v(c['phone'], 'téléphone')} — E-mail : {v(c['email'], 'e-mail de contact')}.",
            f"Directeur de la publication : {v(c['director'], 'nom du représentant légal')}.")),
        ("Activité réglementée", p(
            f"Commissionnaire de transport inscrit au registre des commissionnaires de transport sous le numéro "
            f"{v(c['licence'], 'numéro d\'inscription')}, délivré par la DREAL Auvergne-Rhône-Alpes.",
            f"Assurance de responsabilité civile professionnelle : {v(c['insurer'], 'assureur, numéro de police et étendue géographique')}.")),
        ("Hébergeur", p(f"{v(c['host'], 'Nom de l\'hébergeur')}, {v(c['host_address'], 'adresse et téléphone de l\'hébergeur')}.")),
        ("Propriété intellectuelle", p(
            "Les textes, la marque, le logo et le logiciel de ce site sont protégés. Toute reproduction sans accord écrit "
            "est interdite, hors usage strictement personnel.")),
        ("Signaler un problème", p(
            f"Pour signaler un contenu, un dysfonctionnement ou une faille de sécurité : {v(c['email'], 'e-mail de contact')}. "
            'Les chercheurs en sécurité trouveront nos coordonnées dans <a href="/.well-known/security.txt">security.txt</a>.')),
    ])


def page_cgu():
    c = company()
    return doc("Conditions générales d'utilisation", "Les règles d'utilisation du site et des espaces client et transporteur.", [
        ("Objet", p(
            "Ces conditions encadrent l'accès au site et l'utilisation des comptes. Les prestations de transport sont régies "
            'par les <a href="/cgv">conditions générales de vente</a>.')),
        ("Accès au site", p(
            "Le site est accessible gratuitement. Nous mettons en œuvre les moyens raisonnables pour le maintenir disponible, "
            "sans garantie d'absence d'interruption : maintenance, panne ou cas de force majeure peuvent le suspendre.")),
        ("Création de compte", p(
            "Le compte est réservé aux professionnels. Vous garantissez l'exactitude des informations fournies et vous "
            "confirmez votre adresse e-mail par le lien qui vous est envoyé.",
            "Vos identifiants sont personnels. Choisissez un mot de passe unique, ne le communiquez à personne et "
            "prévenez-nous sans délai de toute utilisation non autorisée. Les actions réalisées depuis votre compte "
            "sont réputées faites par vous.")),
        ("Devis et prix affichés", p(
            "Un prix affiché est une offre valable 24 heures, pour l'envoi tel que vous l'avez décrit. "
            "Une description inexacte (poids, dimensions, nature, adresses, accessibilité) peut entraîner une révision du prix.",
            "Les prix sont calculés automatiquement. Vous pouvez à tout moment demander qu'un conseiller examine votre demande.")),
        ("Transporteurs", p(
            "L'inscription d'un transporteur n'est effective qu'après contrôle de ses pièces. Le transporteur s'engage à "
            "tenir à jour sa licence, son assurance et son attestation de vigilance, et à déclarer sans délai toute suspension. "
            "Un chargement accepté dans l'espace transporteur vaut engagement ferme au prix accepté.")),
        ("Usages interdits", ul(
            "tenter d'accéder aux données d'un autre utilisateur ou de contourner les protections du site ;",
            "extraire automatiquement les prix ou les données du site ;",
            "utiliser le site pour un transport illicite ou une marchandise interdite ;",
            "fournir de fausses informations ou usurper l'identité d'une entreprise.")
            + p("Tout manquement peut entraîner la suspension immédiate du compte.")),
        ("Responsabilité", p(
            "Nous répondons du bon fonctionnement du site dans la limite d'une obligation de moyens. Nous ne sommes pas "
            "responsables des dommages résultant d'informations erronées saisies par l'utilisateur, ni d'une indisponibilité "
            "due à un tiers (réseau, hébergeur) ou à un cas de force majeure.")),
        ("Données personnelles", p(
            'Le traitement de vos données est décrit dans la <a href="/confidentialite">politique de confidentialité</a>.')),
        ("Modification et droit applicable", p(
            "Ces conditions peuvent évoluer ; la version applicable est celle en ligne lors de votre utilisation, et toute "
            "modification importante vous est signalée. Elles sont soumises au droit français. À défaut d'accord amiable, "
            f"le litige relève des tribunaux compétents du ressort du siège de {v(c['name'], 'la société')}.")),
    ])


def page_cgv():
    c = company()
    return doc("Conditions générales de vente", "Les conditions applicables aux transports que vous nous confiez.", [
        ("Champ d'application", p(
            f"{v(c['name'], 'La société')} agit en qualité de commissionnaire de transport : elle organise le transport "
            "en son nom et le fait exécuter par des transporteurs qu'elle choisit. Ces conditions s'appliquent à toute "
            "commande passée par un professionnel et prévalent sur ses conditions d'achat, sauf accord écrit contraire.",
            "Pour tout ce qu'elles ne règlent pas, le contrat type de commission de transport prévu par le code des "
            "transports s'applique.")),
        ("Commande", p(
            "La commande est formée lorsque vous confirmez la réservation d'un devis en cours de validité et acceptez "
            "les présentes conditions. Un e-mail récapitulatif vous est adressé avec votre code de suivi.",
            "Tant qu'aucun transporteur n'est affecté, la réservation est en attente : vous en êtes informé, et vous "
            "pouvez l'annuler sans frais.")),
        ("Obligations du donneur d'ordre", ul(
            "décrire exactement la marchandise : nature, poids, dimensions, nombre de colis ou palettes, particularités "
            "(matières dangereuses, température, valeur) ;",
            "conditionner, emballer et étiqueter la marchandise pour qu'elle supporte un transport routier normal ;",
            "indiquer des adresses complètes, les horaires et les contraintes d'accès ;",
            "remettre les documents nécessaires au transport.")
            + p("Les conséquences d'une déclaration inexacte ou incomplète sont à la charge du donneur d'ordre.")),
        ("Marchandises exclues", p(
            "Sauf accord écrit préalable : animaux vivants, espèces, métaux précieux, œuvres d'art, armes, déchets, "
            "marchandises illicites, et matières dangereuses non déclarées.")),
        ("Prix", p(
            "Le prix réservé est ferme pour l'envoi tel que décrit. Il comprend le transport et les options choisies ; "
            "il ne comprend pas les frais nés d'un fait qui ne nous est pas imputable : immobilisation du véhicule au-delà "
            "des durées prévues par le contrat type, nouvelle présentation, marchandise non conforme à la description, "
            "droits et taxes éventuels. Ces frais sont facturés sur justificatif.")),
        ("Annulation", p(
            "L'annulation est gratuite tant qu'aucun transporteur n'est affecté. Après affectation, une annulation ou un "
            "déplacement à vide peut donner lieu à un dédommagement du transporteur, refacturé sur justificatif.")),
        ("Livraison et réserves", p(
            "Les délais indiqués sont des estimations, sauf engagement écrit de notre part. À la livraison, le destinataire "
            "vérifie la marchandise et porte sur le document de transport des réserves précises et motivées en cas de "
            "dommage ou de manquant ; il les confirme au transporteur par lettre recommandée dans les trois jours ouvrables. "
            "Faute de quoi, aucune réclamation ne peut aboutir.")),
        ("Responsabilité", p(
            "Nous répondons de nos fautes personnelles et, en qualité de garant, de celles des transporteurs que nous "
            "choisissons, dans les limites d'indemnisation fixées par les contrats types applicables. "
            "Pour une marchandise dont la valeur dépasse ces limites, demandez-nous une déclaration de valeur ou une "
            "assurance complémentaire avant l'enlèvement.")),
        ("Facturation et paiement", p(
            "Le transport est facturé à l'issue de la livraison. Le paiement est dû à 30 jours à compter de la date "
            "d'émission de la facture. Tout retard entraîne, sans rappel, des pénalités au taux de trois fois le taux "
            "d'intérêt légal et une indemnité forfaitaire de 40 € pour frais de recouvrement. Aucun escompte n'est "
            "accordé pour paiement anticipé.")),
        ("Réclamations et prescription", p(
            f"Toute réclamation est à adresser à {v(c['email'], 'l\'e-mail de contact')} avec le code de suivi et les "
            "justificatifs. Les actions nées du contrat se prescrivent par un an à compter de la livraison ou du jour "
            "où elle aurait dû avoir lieu.")),
        ("Droit applicable et litiges", p(
            "Ces conditions sont soumises au droit français. À défaut d'accord amiable, le tribunal de commerce du "
            f"ressort du siège de {v(c['name'], 'la société')} est seul compétent.")),
    ])


def page_privacy():
    c = company()
    return doc("Politique de confidentialité", "Quelles données nous traitons, pourquoi, combien de temps, et quels sont vos droits.", [
        ("Responsable du traitement", p(
            f"{v(c['name'], 'Raison sociale')}, {v(c['address'], 'adresse du siège')}. "
            f"Contact pour toute question sur vos données : {v(c['privacy_email'], 'e-mail dédié aux données personnelles')}.")),
        ("Données traitées et finalités",
         '<div class="table-scroll"><table class="data"><thead><tr><th>Données</th><th>Pourquoi</th><th>Base légale</th></tr></thead><tbody>'
         "<tr><td>Nom, société, e-mail, téléphone</td><td>Créer votre compte, établir les devis, vous tenir informé de vos envois</td><td>Exécution du contrat</td></tr>"
         "<tr><td>Adresses d'enlèvement et de livraison, nature de la marchandise</td><td>Organiser et exécuter le transport</td><td>Exécution du contrat</td></tr>"
         "<tr><td>Factures et pièces comptables</td><td>Tenue de la comptabilité</td><td>Obligation légale</td></tr>"
         "<tr><td>Pièces des transporteurs (SIRET, licence, assurance)</td><td>Contrôler la capacité à transporter</td><td>Obligation légale et intérêt légitime</td></tr>"
         "<tr><td>Journal des connexions et des actions, adresse IP</td><td>Sécurité du site, prévention de la fraude</td><td>Intérêt légitime</td></tr>"
         "<tr><td>Messages que vous nous envoyez (e-mail, formulaire)</td><td>Répondre à votre demande</td><td>Mesures précontractuelles</td></tr>"
         "</tbody></table></div>"
         + p("Nous ne collectons pas de données sensibles et ne revendons aucune donnée.")),
        ("Traitements automatisés", p(
            "Les prix sont calculés par un programme. Les demandes de devis reçues par e-mail sont lues par un modèle "
            "d'intelligence artificielle qui en extrait le trajet, le poids et la date ; le prix reste calculé par nos "
            "règles, jamais par ce modèle. Aucune décision produisant des effets importants à votre égard n'est prise "
            "sans qu'une personne puisse intervenir : vous pouvez demander à tout moment l'examen de votre dossier par un conseiller.")),
        ("Destinataires", ul(
            "le transporteur affecté à votre envoi, pour les seules informations nécessaires à son exécution ;",
            "nos prestataires techniques : hébergement, envoi d'e-mails, et le fournisseur du modèle d'intelligence "
            "artificielle pour la lecture des e-mails ;",
            "notre expert-comptable et, sur demande légale, les autorités.")
            + p("Certains prestataires peuvent être établis hors de l'Union européenne. Dans ce cas, le transfert est "
                "encadré par les clauses contractuelles types de la Commission européenne. La liste des prestataires est "
                "communiquée sur demande.")),
        ("Durées de conservation", ul(
            "devis non réservés : 90 jours ;",
            "compte : jusqu'à sa suppression, puis anonymisation ;",
            "dossiers de transport : 5 ans après la livraison ;",
            "factures et pièces comptables : 10 ans ;",
            "journal de sécurité : 12 mois ;",
            "messages de contact : 3 ans après le dernier échange.")),
        ("Sécurité", p(
            "Mots de passe hachés, connexion chiffrée, accès administrateur protégé par double authentification, "
            "journal d'audit infalsifiable, sauvegardes régulières et vérifiées. En cas de violation de données "
            "présentant un risque pour vous, vous en êtes informé dans les meilleurs délais.")),
        ("Vos droits", p(
            "Vous disposez d'un droit d'accès, de rectification, d'effacement, de limitation, d'opposition et de "
            "portabilité. Depuis la page <a href=\"/compte\">Mon compte</a>, vous pouvez télécharger vos données et "
            f"supprimer votre compte. Pour toute autre demande : {v(c['privacy_email'], 'e-mail dédié')}. Nous répondons "
            "sous un mois.",
            "Si vous estimez que vos droits ne sont pas respectés, vous pouvez saisir la CNIL (cnil.fr).")),
        ("Cookies", p(
            "Le site n'utilise qu'un cookie de session, strictement nécessaire à la connexion à votre espace. "
            "Il n'y a ni cookie publicitaire, ni mesure d'audience tierce : aucun bandeau de consentement n'est donc requis.")),
    ])


def page_compte():
    body = (content.hero("Mon compte", "Adresse e-mail, mot de passe, données personnelles.")
            + '<section class="block"><div class="wrap narrow stack">'
              '<div id="c-status" class="ok-box hidden"></div><div id="c-error" class="err hidden" role="alert"></div>'
              '<form id="reset-form" class="card hidden" novalidate><h2>Choisir un nouveau mot de passe</h2>'
              '<label for="n-pw">Nouveau mot de passe (10 caractères minimum)</label>'
              '<input id="n-pw" type="password" autocomplete="new-password" minlength="10" required>'
              '<button class="full" type="submit">Enregistrer</button><div id="reset-error" class="err hidden" role="alert"></div></form>'
              '<form id="forgot-form" class="card hidden" novalidate><h2>Mot de passe oublié</h2>'
              '<p class="muted">Indiquez l\'adresse de votre compte : si elle est connue, un lien valable une heure y est envoyé.</p>'
              '<label for="f-email">E-mail</label><input id="f-email" type="email" autocomplete="email" required>'
              '<button class="full" type="submit">Recevoir le lien</button><div id="forgot-error" class="err hidden" role="alert"></div></form>'
              '<div id="settings" class="stack hidden">'
              '<div class="card"><h2>Adresse e-mail</h2><p id="s-email"></p>'
              '<button type="button" class="ghost hidden" id="s-resend">Renvoyer le lien de confirmation</button></div>'
              '<form id="pw-form" class="card" novalidate><h2>Changer de mot de passe</h2>'
              '<label for="p-current">Mot de passe actuel</label><input id="p-current" type="password" autocomplete="current-password" required>'
              '<label for="p-new">Nouveau mot de passe</label><input id="p-new" type="password" autocomplete="new-password" minlength="10" required>'
              '<button class="full" type="submit">Changer</button><div id="pw-error" class="err hidden" role="alert"></div></form>'
              '<div class="card"><h2>Mes données</h2><p class="muted">Téléchargez l\'ensemble des données liées à votre compte.</p>'
              '<a class="btn" id="s-export" href="#">Télécharger mes données</a></div>'
              '<form id="delete-form" class="card" novalidate><h2>Supprimer mon compte</h2>'
              '<p class="muted">Vos données personnelles sont effacées. Les factures sont conservées, comme la loi l\'impose. '
              'Cette action est définitive.</p><label for="d-pw">Mot de passe</label>'
              '<input id="d-pw" type="password" autocomplete="current-password" required>'
              '<button class="full danger" type="submit">Supprimer définitivement mon compte</button>'
              '<div id="delete-error" class="err hidden" role="alert"></div></form></div></div></section>')
    return content.layout("Mon compte", "Gestion du compte.", body, ("/common.js", "/compte.js"))


content.PAGES.update({"/mentions-legales": page_mentions, "/cgu": page_cgu, "/cgv": page_cgv,
                      "/confidentialite": page_privacy, "/compte": page_compte})
