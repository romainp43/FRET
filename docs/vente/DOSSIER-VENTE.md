# FRETRAU — Dossier de vente

Document interne du vendeur (Romain Pichon). Il rassemble tout ce qu'il faut pour vendre
FRETRAU : ce qui est vendu, comment le présenter honnêtement, à quel prix, et comment négocier.

## 1. Ce qui est vendu (périmètre à écrire dans l'offre)

Un actif logiciel complet, prêt à lancer :
- **Code source** : application web en Python 3.11+ sans dépendance externe, environ 9 800 lignes de
  Python et 1 600 lignes d'interface web, 255 tests automatisés qui passent.
- **Moteur de devis** : tarification au kilomètre (camion complet) et à la palette (lots), options
  ADR, hayon, température, express, indice gazole, marge cible 12 % et plancher 5 %.
- **Agents d'aide à la décision** (règles déterministes, un modèle de langage n'invente jamais un
  prix) : saisie, contrôle de coût, rapprochement de tarifs, garde-fous, conformité, risque,
  sourcing, négociation, décision, e-mail, appel d'offres, veille, tri des réclamations.
- **Parcours complet** : devis, réservation, suivi, espace transporteur, espace chauffeur,
  facturation avec mentions françaises, réclamations, espace admin avec droits par rôle.
- **Sécurité** : en-têtes stricts, journal d'audit chaîné, double authentification, webhooks signés,
  limitation de débit.
- **Itinéraires** : openrouteservice (poids lourd) puis OSRM, avec repli sur estimation prudente.
- **Textes** : mentions légales, CGV, CGU, confidentialité, cookies (à faire valider par un juriste
  avant exploitation).
- **Déploiement** : Docker, Caddy, scripts de sauvegarde, guide d'hébergement gratuit.
- **Marque FRETRAU** : non déposée à ce jour. Elle est cédée avec le projet, à titre de nom d'usage,
  sans garantie de disponibilité.

## 2. Ce qu'il faut dire sans détour (transparence obligatoire)

Une vente se défait si l'acheteur découvre ensuite un point caché. L'annonce, la présentation et
le contrat doivent donc dire clairement :
1. **Aucun client, aucun chiffre d'affaires.** C'est un produit pré-lancement.
2. **Aucun transporteur réel.** La base de transporteurs est fictive et à remplacer.
3. **Le code a été écrit avec l'aide d'une IA.** Le vendeur a dirigé et arbitré le projet, mais la
   protection par le droit d'auteur d'un code très largement généré par une machine n'est pas
   garantie. Ne pas le cacher, ne pas garantir l'originalité absolue.
4. **Textes juridiques non validés** par un avocat spécialisé en transport.
5. **Pas d'inscription de commissionnaire** : la société n'existe pas et aucune inscription n'est
   faite. L'acheteur exploitant le service doit avoir son propre statut.
6. **Itinéraires réels non testés contre le service en production** (testés avec simulation).

Ces points se négocient bien (ils justifient un prix bas), et les cacher exposerait Romain à une
action en nullité ou en dommages-intérêts pour réticence dolosive.

## 3. Positionnement : à qui parler et avec quel argument

| Acheteur | Ce qu'il veut | Argument |
|---|---|---|
| Petit éditeur ou studio (Acquire.com, Flippa) | Un produit prêt à monétiser | « Gagnez six mois de développement, tout est testé et documenté » |
| Transporteur ou commissionnaire régional agréé | Digitaliser son offre de devis | « Votre site de devis en ligne avec votre marque, en une semaine » |
| Courtier ou réseau de palettes | Comparer les offres et automatiser | « Moteur de prix et agents prêts à brancher sur vos tarifs » |
| Éditeur de logiciel de transport (TMS) | Une brique IA | « Agents de décision auditables, sans dépendance » |
| Créateur de start-up fret | Partir plus vite | « Base technique et sécurité déjà posées, vous ajoutez les clients » |

## 4. Prix et stratégie

Valeurs de marché : un projet sans chiffre d'affaires se vend le plus souvent entre 500 et
25 000 dollars, et un produit qui fonctionne sans utilisateurs se situe plutôt entre 500 et
3 000 dollars. Il ne faut donc pas espérer un prix à six chiffres sans clients.

Recommandation (mon estimation, pas un barème) :
- **Prix demandé affiché : 18 000 €**, « ouvert aux offres ». Un prix d'ancrage haut donne de la marge
  de négociation, sans mentir sur le contenu.
- **Résultat réaliste : 2 000 à 8 000 €** pour une cession complète. Plus si un acheteur stratégique
  veut un accès exclusif.
- **Licence non exclusive** (alternative) : 1 500 à 4 000 € par installation, ou 150 à 400 € par mois.
  Elle permet de vendre plusieurs fois et de garder la propriété.
- **Exclusivité temporaire** : 30 jours d'exclusivité contre une avance non remboursable de 10 à 20 %
  du prix.

Règles de négociation :
1. Ne jamais donner son prix plancher ; demander d'abord le budget et le calendrier de l'acheteur.
2. Toujours échanger une concession contre une autre (réduction contre paiement comptant, exclusivité
   contre avance, assistance contre prix plus élevé).
3. Séparer le prix du code (cession), du temps d'assistance (facturé à l'heure) et de la marque.
4. Paiement uniquement par **séquestre** (Escrow.com ou plateforme), jamais de remise du code avant
   paiement bloqué.
5. Plusieurs acheteurs en parallèle : le simple fait de le mentionner fait monter les offres.
6. Délai : annoncer 14 jours pour une réponse ferme.

## 5. Déroulé de la vente

1. Annonce publique, sans détail technique sensible, sur les plateformes.
2. Un acheteur intéressé signe l'**accord de confidentialité** (`NDA.md`).
3. Démonstration en ligne (je fournis le script et les données d'exemple).
4. Accès au code en lecture seule dans une salle de données (dépôt privé GitHub).
5. Offre écrite, puis négociation selon la section 4.
6. Contrat de cession (`CESSION.md`) signé, prix bloqué sous séquestre.
7. Livraison : transfert du dépôt, remise des fichiers, assistance de 5 heures, libération du séquestre.

## 6. Ce que Romain doit faire lui-même (inévitable)

- Valider l'envoi de chaque message (aucun n'est envoyé sans son accord).
- Créer le compte sur les plateformes (vérification d'identité) et accepter leurs conditions.
- Signer l'accord de confidentialité et le contrat de cession.
- Recevoir le paiement et le déclarer (voir ci-dessous).

## 7. Fiscalité à vérifier (à ton niveau d'expert)

Le prix perçu relève, selon le cas, de la cession de droits d'auteur (régime des droits d'auteur ou
BNC), ou d'une recette de ton activité existante. La micro-entreprise a un plafond partagé avec ton
activité actuelle. À arbitrer avant la première signature, avec ton comptable.
