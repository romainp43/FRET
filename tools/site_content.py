"""Contenu éditorial des pages publiques (français). Chaque page a une FAQ rendue aussi en données structurées (JSON-LD).
Les [[champs]] sont remplacés par config/company.json. Rien ici n'annonce une fonction qui n'existe pas dans l'application."""

COMMON_Q = [
    ("Comment obtenir un prix ?", "Indiquez le départ, l'arrivée, le poids et la date d'enlèvement dans le formulaire de la page d'accueil : le prix s'affiche immédiatement. Vous pouvez aussi nous écrire par e-mail en texte libre : notre assistant lit votre demande et vous répond avec un prix ou la liste exacte de ce qui manque."),
    ("Que faut-il indiquer pour un prix précis ?", "Villes (ou codes postaux) de départ et d'arrivée, nombre de palettes, poids total, nature de la marchandise et date d'enlèvement. Précisez toute contrainte : hayon, température, ADR, plateau, livraison avant une date."),
    ("J'ai déjà un devis moins cher ailleurs : que faire ?", "Après votre devis, utilisez « Un devis moins cher ailleurs ? » avec le prix HT et la référence du concurrent. Pour la même expédition, nous étudions un alignement. Il est encadré : un justificatif peut vous être demandé avant l'enlèvement."),
    ("Puis-je suivre mon envoi ?", "Oui. Votre code de suivi (FR-…) vous est envoyé par e-mail à la réservation ; saisissez-le sur la page d'accueil. Les jalons affichés sont ceux transmis par le transporteur ou validés par notre exploitation."),
    ("FRETRAU est-il autorisé à organiser des transports ?", "FRETRAU agit comme commissionnaire de transport : nous organisons le transport avec des transporteurs routiers autorisés, sans posséder de camions. Notre inscription au registre des commissionnaires de transport est indiquée dans les mentions légales ([[transport_licence]])."),
]

SERVICES = {
    "camion-complet": {
        "title": "Camion complet (FTL)", "short": "Un camion pour vous seul, du chargement à la livraison, sans rupture de charge.",
        "intro": "Le camion complet convient quand votre marchandise remplit un véhicule ou doit voyager seule, directement de l'enlèvement à la livraison, sans transiter par un entrepôt.",
        "what": ["Un semi-remorque ou porteur dédié à votre expédition, jusqu'à 33 palettes et 24 tonnes.", "Trajet direct : pas de manutention intermédiaire, donc moins de risque de casse et des délais plus courts.", "Le prix dépend surtout du trajet, de la date, du type de véhicule et de la disponibilité de camions sur l'axe."],
        "fits": ["Marchandise qui remplit la plupart du camion", "Livraison avec créneau fixe", "Produits fragiles ou à éviter de manipuler"],
        "faq": [("Quelle est la différence entre camion complet et palettes ?", "En camion complet, le véhicule est à vous seul et le prix est celui du trajet. En palettes (groupage), vous payez la place et le poids que vous occupez, partagés avec d'autres expéditeurs."),
                ("Combien de palettes et quel poids ?", "Jusqu'à 33 palettes Europe et 24 tonnes. Au-delà, ou pour une marchandise hors norme, contactez-nous pour un devis sur mesure."),
                ("Sur quoi le prix est-il basé ?", "Sur la distance du trajet, une courbe de prix au kilomètre qui dépend de cette distance, les pays traversés, les options choisies et l'indexation du gazole. Chaque devis indique la version du barème utilisée."),
                ("Quel délai de livraison ?", "Le délai affiché tient compte des jours ouvrés et fériés. L'option Express réduit le délai quand le trajet le permet.")]},
    "groupage-palettes": {
        "title": "Palettes en groupage (LTL)", "short": "Quelques palettes qui ne remplissent pas un camion : vous ne payez que votre place.",
        "intro": "Le groupage transporte vos palettes avec celles d'autres expéditeurs. Vous payez l'espace et le poids occupés, pas le camion entier.",
        "what": ["Idéal de 1 à une dizaine de palettes.", "Le prix tient compte du nombre de palettes et du poids : une palette de 740 kg ou plus compte comme un emplacement plein (règle du poids payant).", "Options : hayon élévateur, livraison express, température dirigée."],
        "fits": ["Quelques palettes qui ne remplissent pas un camion", "Expéditions régulières vers des destinataires variés", "Éviter de payer une place vide"],
        "faq": [("Quand passer au camion complet ?", "Quand le prix du groupage s'approche de celui d'un camion complet, généralement au-delà d'une douzaine de palettes. Notre calculateur vous avertit quand un camion complet est plus avantageux."),
                ("Comment le poids est-il pris en compte ?", "Nous retenons le plus élevé entre le nombre de palettes et le poids converti en emplacements (740 kg par emplacement). Une marchandise très lourde est donc facturée selon son poids."),
                ("Quelles dimensions pour une palette ?", "Nous raisonnons en palettes Europe (80 × 120 cm). Pour une palette hors gabarit ou de plus de 1 000 kg, demandez un devis sur mesure."),
                ("Le hayon est-il possible ?", "Oui, en option. Indiquez-le dès la demande : tous les transporteurs n'en sont pas équipés, nous ne retenons que ceux qui le sont.")]},
    "lot-partiel": {
        "title": "Lot partiel (entre groupage et camion complet)", "short": "Trop de palettes pour le groupage, pas assez pour un camion : nous comparons pour vous.",
        "intro": "Un lot partiel est un envoi de plusieurs palettes qui occupe une partie importante d'un camion, parfois partagé, souvent sans passage par un entrepôt de messagerie.",
        "what": ["Typiquement de 8 à 20 palettes.", "Moins de manutention qu'en groupage classique.", "Notre calculateur compare le prix en palettes et en camion complet et vous signale la meilleure formule."],
        "fits": ["Envois multi-palettes volumineux", "Marchandise qui supporte mal les transbordements", "Pas besoin d'un camion entier"],
        "faq": [("Comment choisir entre groupage et lot partiel ?", "Cela dépend du nombre de palettes, du poids et de la tolérance de votre marchandise à la manutention. Faites le calcul en palettes : si le prix s'approche d'un camion complet, nous vous le signalons."),
                ("Y a-t-il un prix en ligne pour le lot partiel ?", "Le calcul en ligne couvre le groupage jusqu'à 33 palettes et le camion complet. Pour un lot partiel avec contraintes (partage, rupture de charge limitée), envoyez-nous la demande : nous répondons sur mesure."),
                ("J'ai déjà un devis moins cher ailleurs ?", "Envoyez-le-nous : nous étudions un alignement pour la même expédition."),
                ("Puis-je suivre mon lot ?", "Oui, avec le même code de suivi que pour tout envoi.")]},
    "frigorifique": {
        "title": "Transport frigorifique (température dirigée)", "short": "Frais, surgelé ou sensible à la chaleur : une température tenue du début à la fin.",
        "intro": "Un camion frigorifique maintient une température constante pendant tout le trajet (réfrigéré ou surgelé). La température demandée influence le prix.",
        "what": ["Alimentaire frais ou surgelé, produits pharmaceutiques ou chimiques sensibles.", "Option « température dirigée » : nous ne retenons que des transporteurs équipés d'un groupe froid.", "Indiquez la plage de température dans les consignes de la réservation."],
        "fits": ["Produits frais, réfrigérés ou surgelés", "Produits sensibles à la chaleur ou au gel", "Chaîne du froid à respecter"],
        "faq": [("Comment demander une température dirigée ?", "Cochez « Température dirigée » dans le formulaire de prix et indiquez la plage de température (par exemple +2 °C à +6 °C) dans les consignes de la réservation."),
                ("Que dois-je préciser ?", "Départ, arrivée, date, nature de la marchandise, poids et plage de température à respecter pendant tout le transport."),
                ("La température est-elle garantie ?", "Le transporteur doit maintenir la température demandée ; une information fausse ou incomplète sur les exigences peut entraîner des frais supplémentaires. Prévenez-nous de toute exigence particulière avant la réservation."),
                ("Peut-on combiner ADR et température dirigée en ligne ?", "Non : cette combinaison demande une étude. Contactez-nous.")]},
    "plateau": {
        "title": "Plateau et chargements spéciaux", "short": "Matériaux, acier, machines : un plateau chargé par le côté, par le haut ou à la grue.",
        "intro": "Le plateau est un camion sans parois ni toit : il se charge par le côté ou par le haut, ce qui convient aux chargements longs, lourds ou volumineux.",
        "what": ["Matériaux de construction, acier, bois, tuyaux, machines.", "Option « Plateau » dans le calculateur (camion complet).", "Dimensions, poids, arrimage et bâchage influencent le prix : indiquez-les."],
        "fits": ["Marchandise chargée par grue ou chariot latéral", "Charges longues ou hors-norme", "Machines et équipements"],
        "faq": [("Comment demander un plateau ?", "Cochez l'option « Plateau » dans le formulaire (en camion complet) et précisez dimensions, poids et besoin de bâche dans les consignes."),
                ("Le plateau est-il disponible en groupage ?", "Non : le plateau se commande en camion complet."),
                ("Les transports exceptionnels sont-ils possibles ?", "Les convois exceptionnels (largeur, longueur ou poids hors norme) exigent une autorisation préfectorale et un itinéraire : demandez un devis sur mesure via la page Contact."),
                ("Quels transporteurs retenez-vous ?", "Uniquement ceux équipés de plateaux, avec licence et assurance valides à la date d'enlèvement.")]},
    "express": {
        "title": "Transport express (urgent)", "short": "Un camion dédié, au plus vite, quand la date compte plus que le prix.",
        "intro": "L'express est un transport direct sur un véhicule dédié, parfois avec deux conducteurs, quand la date de livraison est la priorité (pièces de production, remplacement urgent).",
        "what": ["Option « Express » : délai réduit selon la distance, avec la date de livraison au plus tôt affichée.", "Pas de rupture de charge.", "Utile aussi pour rattraper un enlèvement manqué."],
        "fits": ["Pièces pour une chaîne de production", "Livraison avec date impérative", "Rattrapage d'un enlèvement raté"],
        "faq": [("Comment demander un transport express ?", "Cochez « Express » dans le formulaire et indiquez la date de livraison souhaitée. Si le délai standard ne suffit pas, nous vous disons s'il est possible avec l'option express."),
                ("Que faut-il indiquer ?", "Départ, arrivée, date et heure de disponibilité, date de livraison impérative, poids et dimensions."),
                ("L'express coûte-t-il plus cher ?", "Oui : un véhicule dédié et un délai court ont un coût. Le supplément est visible dans le détail du prix."),
                ("Livrez-vous le week-end ?", "L'enlèvement a lieu un jour ouvré. Pour un besoin particulier (week-end, jour férié), passez par la page Contact.")]},
    "combine-rail-route": {
        "title": "Combiné rail-route (intermodal)", "short": "Sur longues distances, le conteneur voyage en train : à étudier sur devis.",
        "intro": "Le combiné rail-route déplace une unité de chargement (caisse, conteneur, semi-remorque) par camion puis par train sur la partie longue, sans déballer la marchandise.",
        "what": ["Adapté aux longues distances avec des dates de livraison flexibles et des flux réguliers.", "Le prix dépend de la distance entre vos sites et les terminaux, et des horaires des trains.", "Pas de prix en ligne : chaque lien est étudié et comparé au tout-camion."],
        "fits": ["Longues distances avec délai flexible", "Flux réguliers entre deux mêmes régions", "Comparer le rail à la route"],
        "faq": [("Le combiné est-il toujours moins cher que la route ?", "Non. Cela dépend du trajet, de la distance aux terminaux et des horaires. Nous recommandons de demander les deux et de comparer."),
                ("Comment demander un devis combiné ?", "Passez par la page Contact, sujet « Combiné rail-route », avec départ, arrivée, volumes et fréquence."),
                ("Y a-t-il un prix instantané ?", "Pas pour l'instant : nous préférons ne pas afficher un prix approximatif pour ce mode."),
                ("Puis-je suivre un envoi combiné ?", "Le suivi dépend des informations transmises par les opérateurs ; nous vous indiquons ce qui est disponible lors du devis.")]},
}

SECTORS = [("Automobile", "Pièces et composants en flux tendu, livraisons express."), ("BTP et matériaux", "Plateaux, palettes lourdes, chantiers."),
           ("Chimie et plastiques", "Produits en palettes ; ADR sur demande."), ("Produits de grande consommation", "Palettes régulières vers entrepôts et magasins."),
           ("Énergie", "Équipements et pièces, camions plateau."), ("Alimentaire et boissons", "Frais, surgelé, sec, température dirigée."),
           ("Santé et pharmacie", "Produits sensibles, température tenue."), ("Industrie et mécanique", "Machines, pièces, plateau ou camion complet."),
           ("Métallurgie et acier", "Longs, lourds, plateau."), ("Papier et emballage", "Bobines et palettes volumineuses."),
           ("Fruits, légumes et produits frais", "Température dirigée, délais courts."), ("Commerce et e-commerce", "Réapprovisionnement d'entrepôts, palettes en groupage.")]

VALUES = [("Partir du client", "Écouter ce qui ralentit le transport et le corriger."), ("Gagner ensemble", "Le meilleur prix et le meilleur délai se construisent à plusieurs."),
          ("Relever le niveau", "Rendre le transport plus transparent, plus rapide et moins fatigant, en alliant technologie et expertise humaine."),
          ("Rapide, sûr, humain", "La rapidité et la sécurité d'abord, avec une vraie personne quand il le faut.")]

GENERAL_FAQ = COMMON_Q + [
    ("Possédez-vous des camions ?", "Non. Sans flotte propre, nous comparons plusieurs transporteurs pour chaque envoi et choisissons l'offre la plus avantageuse parmi ceux qui sont conformes."),
    ("Comment vérifiez-vous les transporteurs ?", "Avant tout transport, un agent de conformité écarte tout transporteur sans licence, sans assurance valable à la date d'enlèvement, sans l'équipement demandé ou sur liste d'exclusion. Un agent de risque contrôle ensuite que la garantie d'assurance couvre la valeur de la marchandise."),
    ("Le prix est-il ferme ?", "Le prix affiché est valable 24 heures. À la réservation, il est enregistré et ne change pas, tant que les caractéristiques de l'expédition (trajet, poids, date, options) restent identiques."),
    ("Que se passe-t-il si je dois annuler ?", "Une annulation plus de 24 heures avant l'enlèvement est gratuite. Au-delà, des frais peuvent s'appliquer (voir les conditions générales de vente)."),
    ("Que se passe-t-il si le camion attend au chargement ou à la livraison ?", "Les frais d'attente et d'immobilisation imputables au donneur d'ordre peuvent être facturés (voir les conditions générales de vente)."),
    ("Comment signaler une avarie, un manque ou un retard ?", "Faites des réserves précises sur le récépissé du transporteur à la livraison, puis déclarez la réclamation sur la page Réclamation : elle calcule vos délais légaux et notre équipe la traite."),
    ("Quelles marchandises sont acceptées ?", "La plupart des marchandises en palettes ou en vrac chargeable. Les matières dangereuses (ADR) sont possibles sur demande avec des transporteurs habilités. Les combinaisons particulières (ADR avec froid) et les chargements hors gabarit passent par la page Contact."),
    ("Dois-je décrire exactement ma marchandise ?", "Oui. Si les dimensions, le poids ou les exigences (température, ADR) sont inexacts, le transporteur peut réviser le prix et la différence vous est facturée."),
    ("Comment paie-t-on ?", "Vous recevez une facture après le transport. Le paiement par carte à la réservation n'est pas encore disponible."),
    ("Quelle est la couverture géographique ?", "France métropolitaine (hors Corse pour l'instant) et Europe : Espagne, Portugal, Italie (hors îles), Belgique, Pays-Bas, Luxembourg, Allemagne, Autriche, Suisse, Pologne."),
    ("Mes données sont-elles protégées ?", "Oui : nous les utilisons pour réaliser le transport, ne les vendons pas, et vous pouvez demander l'accès, la rectification ou l'effacement via l'adresse indiquée dans la politique de confidentialité."),
    ("Je suis transporteur : comment travailler avec vous ?", "Déposez votre dossier sur la page Transporteurs. Nous vérifions l'entreprise, la licence et l'assurance avant de confier un chargement."),
]

CARRIER_FAQ = [
    ("Quels documents faut-il ?", "Vos numéros d'entreprise (SIREN et TVA), votre licence ou autorisation de transport, et votre attestation d'assurance responsabilité civile marchandises transportées en cours de validité."),
    ("Quel niveau d'assurance exigez-vous ?", "Une garantie d'au moins 100 000 € par sinistre pour la marchandise transportée, valable au moins 30 jours après votre candidature. Selon la valeur des marchandises, nous pouvons exiger davantage."),
    ("Quand suis-je payé ?", "Après la preuve de livraison. Le délai de paiement vous est indiqué avant le premier transport."),
    ("Puis-je sous-traiter un chargement ?", "Non, pas sans notre accord écrit."),
    ("Comment fonctionne la vérification ?", "Des contrôles automatiques vérifient la forme des numéros et des dates, puis une personne vérifie la réalité (existence de l'entreprise, licence, assurance). Aucun dossier n'est approuvé automatiquement."),
    ("Comment êtes-vous informés des chargements ?", "Après approbation, nous vous contactons pour les chargements adaptés à votre flotte et à vos zones ; vous nous transmettez ensuite les jalons de livraison."),
]
