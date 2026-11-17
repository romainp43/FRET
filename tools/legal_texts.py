"""Textes juridiques FRETRAU (BROUILLONS à faire valider par un avocat avant publication).

Références utilisées : loi n° 2004-575 du 21 juin 2004 (LCEN, art. 6 III) ; RGPD (règlement UE 2016/679) et loi
Informatique et Libertés (art. 82 pour les traceurs) ; délibération CNIL n° 2020-091 sur les cookies ; Code de commerce
(art. L132-1 et s. commission de transport, L133-1 et s. voiturier, L441-9 à L441-11 délais de paiement) ;
décret n° 2013-293 du 5 avril 2013 (contrat type de commission de transport) ; décret n° 2017-461 du 31 mars 2017
(contrat type général) ; convention CMR de 1956 pour l'international.
"""
VERSION = "2026-11-17"

MENTIONS = """
<h2>Éditeur du site</h2>
<p>Le site [[domain]] est édité par <strong>[[name]]</strong>, [[legal_form]] au capital de [[capital]],
dont le siège social est situé [[address]], immatriculée au [[rcs]], SIRET [[siret]], TVA intracommunautaire [[vat]].</p>
<p>Contact : [[email]] — [[phone]].</p>
<p>Directeur de la publication : [[director]].</p>
<h2>Activité réglementée</h2>
<p>[[brand]] exerce une activité d'organisateur de transport (commissionnaire de transport). Inscription au registre
des commissionnaires de transport : [[transport_licence]]. Assurance responsabilité civile professionnelle : [[insurance]].</p>
<h2>Hébergeur</h2>
<p>[[host_name]], [[host_address]], téléphone : [[host_phone]].</p>
<h2>Propriété intellectuelle</h2>
<p>Le nom <strong>FRETRAU</strong>, son logo, les textes, les illustrations, le code et la structure du site sont la propriété de
[[brand]] ou de ses concédants et sont protégés par le Code de la propriété intellectuelle (droit d'auteur, droit des
marques, droit des bases de données). [À COMPLÉTER : n° et date du dépôt INPI de la marque FRETRAU, classes 35, 39 et 42 — à
supprimer tant que le dépôt n'est pas effectué ; ne pas utiliser le symbole ® avant l'enregistrement]. Toute reproduction,
représentation, adaptation ou extraction substantielle du contenu ou de la base de données, sans autorisation écrite
préalable, est interdite et constitue une contrefaçon (art. L335-2 et L342-1 du Code de la propriété intellectuelle).</p>
<h2>Crédits et licences</h2>
<p>Les données géographiques proviennent de GeoNames (licence Creative Commons Attribution 4.0) et de geo.api.gouv.fr
(Licence Ouverte 2.0, Etalab), et ont été adaptées pour le calcul des distances. Lorsque le service est activé, les distances routières sont calculées par openrouteservice.org (© HeiGIT) à partir de données © contributeurs OpenStreetMap (licence ODbL). Les marques et noms de tiers cités sur
le site appartiennent à leurs titulaires respectifs et ne sont cités qu'à titre d'information.</p>
<h2>Liens hypertextes</h2>
<p>Les liens vers le site sont autorisés s'ils ne portent pas atteinte à son image et n'induisent pas en erreur sur
l'origine du service (pas de reprise dans un cadre, pas de confusion avec la marque). Nous ne contrôlons pas les sites tiers
vers lesquels le site pourrait renvoyer et déclinons toute responsabilité à leur égard.</p>
<h2>Signalement d'un contenu illicite</h2>
<p>Tout contenu manifestement illicite ou portant atteinte à vos droits peut être signalé à [[email]], en indiquant
l'adresse de la page concernée et le motif (art. 6 de la loi n° 2004-575 du 21 juin 2004 pour la confiance dans l'économie numérique).</p>
<h2>Données personnelles</h2>
<p>Voir la <a href="/legal/confidentialite.html">politique de confidentialité</a> et la
<a href="/legal/cookies.html">politique cookies</a>.</p>
<h2>Signalement d'un contenu ou d'une faille</h2>
<p>Contact sécurité : voir <a href="/.well-known/security.txt">security.txt</a>. Toute faille signalée de bonne foi sera traitée.</p>
"""

CONFIDENTIALITE = """
<p>[[name]] (« [[brand]] ») est responsable du traitement des données décrites ci-dessous. Notre service est destiné
aux professionnels. Cette politique explique quelles données nous collectons, pourquoi, combien de temps nous les
gardons et comment exercer vos droits (RGPD, loi Informatique et Libertés).</p>

<h2>1. Données collectées, finalités et bases légales</h2>
<table class="doc-table">
<tr><th>Finalité</th><th>Données</th><th>Base légale</th><th>Durée de conservation</th></tr>
<tr><td>Établir un devis</td><td>Trajet, marchandise (poids, palettes), options, dates. Aucune donnée d'identité.</td><td>Mesures précontractuelles (art. 6.1.b)</td><td>30 jours si non suivi d'une commande</td></tr>
<tr><td>Exécuter la commande de transport</td><td>Nom, société, e-mail, téléphone, adresses d'enlèvement et de livraison, contact sur site, créneaux, description de la marchandise, consignes</td><td>Exécution du contrat (art. 6.1.b)</td><td>Durée de la relation, puis 5 ans (prescription commerciale), puis anonymisation</td></tr>
<tr><td>Facturation et comptabilité</td><td>Identité du client professionnel, montants, références de transport</td><td>Obligation légale (art. 6.1.c)</td><td>10 ans (obligations comptables)</td></tr>
<tr><td>Preuve d'acceptation des CGV</td><td>Version des CGV, horodatage, empreinte irréversible de l'adresse IP</td><td>Intérêt légitime : preuve en cas de litige (art. 6.1.f)</td><td>Durée de la relation + 5 ans</td></tr>
<tr><td>Sécurité du site et prévention de la fraude</td><td>Journal d'audit des actions d'administration, journaux techniques, limitation de débit</td><td>Intérêt légitime : sécurité (art. 6.1.f)</td><td>12 mois glissants</td></tr>
<tr><td>E-mails de service (confirmation, suivi)</td><td>Adresse e-mail, contenu du message</td><td>Exécution du contrat (art. 6.1.b)</td><td>90 jours</td></tr>
<tr><td>Réponse à vos demandes de droits RGPD</td><td>Identité, contenu de la demande</td><td>Obligation légale (art. 6.1.c)</td><td>5 ans</td></tr>
</table>
<p>Nous ne collectons aucune donnée pour de la publicité et ne vendons aucune donnée.</p>

<h2>2. Destinataires</h2>
<p>Vos données sont accessibles à nos équipes habilitées (accès limité par rôle, authentification à deux facteurs) et,
dans la mesure strictement nécessaire à l'exécution du transport, au transporteur affecté (adresses, créneaux, contact
sur site, nature de la marchandise). Nos sous-traitants techniques agissent sur instruction : hébergeur
([[host_name]]), prestataire d'envoi d'e-mails, outil de comptabilité/facturation. Un contrat conforme à l'article 28
du RGPD est conclu avec chacun.</p>

<h2>3. Intelligence artificielle et décisions automatisées</h2>
<p>Le prix, la sélection du transporteur et la négociation sont assistés par des agents automatisés. Ces traitements
portent sur des données de transport et non sur le profilage de personnes. Les décisions de prix et d'affectation sont
prises par des règles de calcul vérifiables ; lorsque la situation sort du cadre (valeur élevée, prix anormal,
absence d'accord), un opérateur humain intervient. Vous pouvez demander l'intervention d'un humain, exprimer votre point
de vue et contester une décision à [[dpo_email]]. Si un modèle de langage (API Claude, société Anthropic, États-Unis) est
activé pour rédiger des messages, aucune donnée d'identité (nom, e-mail, téléphone, adresse précise) ne lui est transmise :
seuls des faits de transport non personnels (villes, mode, montant) lui sont communiqués. Il ne décide ni d'un prix ni
d'une affectation.</p>

<h2>4. Transferts hors Union européenne</h2>
<p>Vos données sont hébergées dans l'Union européenne. Aucun transfert hors UE n'est effectué par défaut. Si un
sous-traitant situé hors UE devait intervenir, le transfert serait encadré (décision d'adéquation ou clauses
contractuelles types) et cette politique serait mise à jour.</p>

<h2>5. Vos droits</h2>
<p>Vous disposez des droits d'accès, de rectification, d'effacement, de limitation, d'opposition (notamment pour les
traitements fondés sur l'intérêt légitime) et de portabilité, ainsi que du droit de définir des directives sur le sort
de vos données après votre décès. Écrivez à [[dpo_email]] ; nous répondons dans un délai d'un mois. Une pièce
d'identité pourra être demandée en cas de doute. Vous pouvez introduire une réclamation auprès de la CNIL
(www.cnil.fr). L'effacement ne s'applique pas aux données que la loi nous oblige à conserver (par exemple les factures) ;
dans ce cas, elles sont isolées et conservées pour la durée légale.</p>

<h2>6. Sécurité</h2>
<p>Chiffrement des échanges (HTTPS/TLS), mots de passe hachés (scrypt), authentification à deux facteurs pour
l'administration, accès par rôles, journal d'audit infalsifiable, limitation du débit, validation stricte des
saisies, sauvegardes régulières et testées. En cas de violation de données susceptible d'engendrer un risque pour les
personnes, nous notifions la CNIL dans les 72 heures et vous informons si le risque est élevé.</p>

<h2>7. Cookies</h2>
<p>Le site n'utilise que des traceurs strictement nécessaires à son fonctionnement. Voir la
<a href="/legal/cookies.html">politique cookies</a>.</p>

<h2>8. Contact</h2>
<p>[[name]], [[address]] — [[dpo_email]].</p>
"""

CGU = """
<h2>1. Objet</h2>
<p>Les présentes conditions encadrent l'utilisation du site [[domain]] (consultation, demande de devis, suivi
d'expédition), édité par [[name]]. La commande d'un transport est régie par les
<a href="/legal/cgv.html">conditions générales de vente</a>.</p>
<h2>2. Accès et disponibilité</h2>
<p>Le site est accessible 24 h/24, sauf maintenance ou incident. Nous pouvons le suspendre pour des raisons de sécurité
sans préavis. Aucune disponibilité continue n'est garantie.</p>
<h2>3. Usage autorisé</h2>
<p>Vous vous engagez à fournir des informations exactes et à ne pas : tenter d'accéder à des données ou fonctions non
autorisées ; perturber le site (automatisation abusive, tests d'intrusion non autorisés) ; collecter les prix ou les
données par extraction massive ; usurper l'identité d'un tiers. Les tentatives sont journalisées et peuvent être
bloquées. Les failles de sécurité peuvent être signalées via <a href="/.well-known/security.txt">security.txt</a>.</p>
<h2>4. Devis en ligne</h2>
<p>Les prix affichés sont des offres valables 24 heures dans les conditions du devis (trajet, marchandise, options,
dates). Ils peuvent être revus si les informations fournies sont inexactes. Les délais sont indicatifs tant qu'ils ne sont
pas confirmés par écrit.</p>
<h2>5. Code de suivi</h2>
<p>Le code de suivi donne accès au statut de l'expédition. Conservez-le : toute personne qui le détient peut consulter ce
statut. Il ne donne pas accès aux données personnelles du donneur d'ordre.</p>
<h2>6. Propriété intellectuelle</h2>
<p>Le site, son code, ses textes, ses illustrations, sa marque et ses bases de données sont la propriété de [[name]] ou de
ses concédants. Aucun droit n'est cédé. L'accès au site confère un simple droit d'usage personnel, non exclusif et non
cessible, pour obtenir des devis et suivre des expéditions. Les informations que vous saisissez restent les vôtres :
vous nous autorisez à les utiliser uniquement pour fournir le service, selon la politique de confidentialité.</p>
<h2>7. Responsabilité</h2>
<p>Nous ne répondons pas des interruptions du site, des indisponibilités imputables à un tiers ou à un cas de force
majeure, ni de l'usage fait des informations du site, dans les limites autorisées par la loi.</p>
<h2>8. Données personnelles et cookies</h2>
<p>Voir la <a href="/legal/confidentialite.html">politique de confidentialité</a> et la <a href="/legal/cookies.html">politique cookies</a>.</p>
<h2>9. Droit applicable</h2>
<p>Droit français. Tribunal de commerce de [[court]] pour les litiges entre professionnels, sous réserve des règles
impératives de compétence.</p>
"""

CGV = """
<p class="muted">Ces conditions s'adressent exclusivement à des professionnels (donneurs d'ordre agissant dans le cadre de
leur activité). Elles ne s'appliquent pas aux consommateurs.</p>
<h2>1. Parties et rôle de [[brand]]</h2>
<p>[[name]] ([[legal_form]], [[rcs]], inscription au registre des commissionnaires de transport : [[transport_licence]]) agit
en qualité de <strong>commissionnaire de transport</strong> : il organise, en son nom et pour le compte du donneur d'ordre,
le transport de marchandises par route, qu'il fait exécuter par des transporteurs qu'il choisit. Le <strong>contrat type de
commission de transport</strong> (décret n° 2013-293 du 5 avril 2013) s'applique à titre supplétif, sauf stipulation
contraire écrite plus favorable au donneur d'ordre.</p>
<h2>2. Devis et commande</h2>
<p>Le devis en ligne est valable 24 heures. La commande est ferme lorsque le donneur d'ordre confirme la réservation après
avoir accepté les présentes conditions ; elle est confirmée par e-mail avec un code de suivi. Si aucune affectation
automatique n'est possible, un opérateur traite la demande et confirme ou refuse sous un délai raisonnable ; aucune commande
n'est réputée acceptée sans confirmation.</p>
<h2>3. Prix</h2>
<p>Les prix sont exprimés en euros hors taxes. La TVA est ajoutée au taux en vigueur lorsqu'elle est applicable ; pour les
prestations internationales, le régime de TVA applicable est déterminé selon les règles en vigueur et les informations
fournies par le donneur d'ordre. Le prix inclut les péages courants, hors cas particuliers (tunnels alpins, redevances
spécifiques) précisés au devis. Une indexation carburant peut être appliquée selon l'indice du Comité national routier. Les
frais supplémentaires imputables au donneur d'ordre (attente, immobilisation, second enlèvement, déchargement non conforme,
adresse erronée) sont facturés sur justificatifs.</p>
<h2>4. Obligations du donneur d'ordre</h2>
<p>Le donneur d'ordre garantit l'exactitude des informations (nature, poids, nombre de palettes, dimensions, valeur,
dangerosité, adresses, créneaux, contact sur site), la conformité de la marchandise, un emballage et un conditionnement
adaptés, l'accessibilité des sites de chargement et de livraison et la présence d'une personne habilitée. Il déclare les
matières dangereuses (ADR) et les marchandises à température dirigée au moment de la commande ; à défaut, le transport
peut être refusé ou suspendu à ses frais. Il est interdit de confier des marchandises prohibées.</p>
<h2>5. Délais</h2>
<p>Les délais sont des estimations établies en jours ouvrés (hors week-ends et jours fériés) selon la distance et le mode
choisi. Le commissionnaire est tenu d'une obligation de moyens quant aux délais, sauf engagement exprès et écrit de livrer à
une date ou un créneau déterminé, ce qui peut donner lieu à un supplément.</p>
<h2>6. Modification et annulation</h2>
<p>Toute modification ou annulation doit être notifiée par écrit. Annulée plus de 24 heures avant l'enlèvement, la commande
n'est pas facturée ; annulée moins de 24 heures avant, elle donne lieu à indemnisation du préjudice prouvé (frais engagés par
le transporteur, immobilisation) dans la limite du prix du transport. [À COMPLÉTER : confirmer ces barèmes avec votre juriste]</p>
<h2>7. Livraison, réserves et réclamations</h2>
<p>Le destinataire contrôle la marchandise à la livraison et formule des <strong>réserves précises et motivées</strong> sur
le document de transport. À défaut, une protestation motivée doit être notifiée par écrit au transporteur dans les
trois jours (hors dimanches et jours fériés) suivant la réception, conformément à l'article L133-3 du Code de commerce,
et au commissionnaire sans délai. Toute action en responsabilité se prescrit par un an à compter de la livraison (ou du jour où
elle aurait dû avoir lieu), conformément à l'article L133-6 du Code de commerce.</p>
<h2>8. Responsabilité et limites d'indemnisation</h2>
<p>Le commissionnaire de transport répond de ses propres fautes et, du fait de ses substitués, dans les limites encourues
par ceux-ci (art. L132-6 du Code de commerce). En cas de perte, d'avarie ou de retard, l'indemnité due est limitée dans les
conditions prévues par le contrat type applicable : en transport national, le contrat type général (décret n° 2017-461 du
31 mars 2017, art. 22), qui plafonne l'indemnité par kilogramme de poids brut manquant ou avarié et, pour les envois de
moins de trois tonnes, par colis ; en transport international, la convention CMR (8,33 droits de tirage spéciaux par kilogramme de
poids brut manquant). Le retard ouvre droit à la réparation du préjudice prouvé dans la limite du prix du transport.
Ces limites ne s'appliquent pas en cas de faute lourde ou dolosive. Le donneur d'ordre peut souscrire une assurance
« ad valorem » ou déclarer une valeur : la demande doit être faite avant l'enlèvement, par écrit, et peut donner lieu à un
supplément. Le commissionnaire n'est pas responsable des dommages résultant de la nature ou du vice propre de la
marchandise, d'un emballage insuffisant, d'une information inexacte, d'un cas de force majeure ou de la faute du
donneur d'ordre ou du destinataire. Les dommages indirects (perte d'exploitation, pénalités de retard de tiers) sont exclus,
sauf faute lourde.</p>
<h2>9. Facturation et paiement</h2>
<p>Les factures sont payables <strong>à 30 jours à compter de la date d'émission de la facture</strong>, délai maximal
applicable en transport routier de marchandises et pour les commissionnaires de transport (art. L441-11 II du Code de commerce).
Aucun escompte n'est accordé pour paiement anticipé. Tout retard de paiement entraîne de plein droit, sans rappel,
des pénalités au taux de refinancement de la Banque centrale européenne majoré de 10 points, ainsi qu'une indemnité forfaitaire
pour frais de recouvrement de 40 € (art. L441-10 et D441-5 du Code de commerce), sans préjudice d'une indemnisation complémentaire
sur justificatifs.</p>
<h2>10. Sous-traitance et confidentialité</h2>
<p>Le commissionnaire peut recourir à tout transporteur conforme (licence, assurance). Chaque partie garde confidentielles
les informations commerciales de l'autre.</p>
<h2>11. Données personnelles</h2>
<p>Les données personnelles sont traitées conformément à la <a href="/legal/confidentialite.html">politique de
confidentialité</a>. La preuve de l'acceptation des présentes conditions (version, horodatage, empreinte de l'adresse IP) est
conservée.</p>
<h2>12. Force majeure</h2>
<p>Aucune partie n'est responsable d'un manquement causé par un événement de force majeure (intempéries exceptionnelles,
grève, fermeture de routes, décision d'une autorité, etc.). L'exécution est suspendue pendant sa durée ; si elle dépasse
15 jours, chaque partie peut résilier sans indemnité.</p>
<h2>13. Droit applicable et litiges</h2>
<p>Droit français. À défaut de règlement amiable, compétence du tribunal de commerce de [[court]], même en cas de pluralité de
défendeurs ou d'appel en garantie. Pour le transport international, la convention CMR s'applique impérativement.</p>
<h2>14. Acceptation</h2>
<p>La réservation en ligne vaut acceptation des présentes conditions dans leur version en vigueur à la date de la commande.</p>
"""

COOKIES = """
<h2>1. Ce que nous utilisons</h2>
<p>Le site n'utilise <strong>aucun cookie publicitaire, aucun outil de mesure d'audience, aucun traceur de réseau
social</strong>. Seuls des traceurs <strong>strictement nécessaires</strong> au service sont utilisés ; ils sont exemptés de
consentement (art. 82 de la loi Informatique et Libertés ; délibération CNIL n° 2020-091).</p>
<table class="doc-table">
<tr><th>Nom</th><th>Finalité</th><th>Durée</th><th>Concerné</th></tr>
<tr><td><code>fretrau_admin</code> (cookie)</td><td>Maintenir la session sécurisée de l'espace d'administration (HttpOnly, SameSite=Strict)</td><td>1 heure</td><td>Équipe interne uniquement</td></tr>
<tr><td><code>fretrau_consent_v1</code> (stockage local)</td><td>Mémoriser votre choix en matière de traceurs, si des traceurs optionnels étaient proposés</td><td>6 mois</td><td>Visiteurs</td></tr>
</table>
<h2>2. Si nous ajoutons des traceurs optionnels</h2>
<p>Avant tout dépôt, un bandeau vous proposera <strong>« Tout accepter »</strong> et <strong>« Tout refuser »</strong> au même niveau et avec la
même visibilité, ainsi qu'un choix par finalité. Votre choix sera conservé 6 mois, et vous pourrez le modifier à tout moment
depuis le lien « Gérer mes cookies » en bas de page. Aucun traceur optionnel n'est déposé avant votre accord.</p>
<h2>3. Gérer ou refuser</h2>
<p>Vous pouvez à tout moment supprimer les cookies depuis les réglages de votre navigateur. La suppression du cookie de session
d'administration vous déconnecte simplement.</p>
<h2>4. Contact</h2>
<p>[[dpo_email]]. Voir aussi la <a href="/legal/confidentialite.html">politique de confidentialité</a>.</p>
"""

PAGES = {
    "mentions-legales": {"title": "Mentions légales", "body": MENTIONS},
    "confidentialite": {"title": "Politique de confidentialité", "body": CONFIDENTIALITE},
    "cgu": {"title": "Conditions d'utilisation", "body": CGU},
    "cgv": {"title": "Conditions générales de vente", "body": CGV},
    "cookies": {"title": "Politique cookies", "body": COOKIES},
}
