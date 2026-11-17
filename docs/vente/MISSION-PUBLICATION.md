# Consigne clé en main pour publier l'annonce (à confier à un proche, un freelance ou à faire soi-même)

Objectif : mettre FRETRAU en vente de façon confidentielle, sans que le nom du vendeur apparaisse
aux acheteurs. Durée : environ 30 minutes. Rien n'est à inventer : tous les textes et images sont prêts.

## Ce qu'il faut avoir sous la main
- Le dossier `dossier-vente.zip` (textes, accord de confidentialité, contrat).
- Le dossier `captures/` (7 images de l'application).
- Le titulaire du compte doit pouvoir passer la vérification d'identité (pièce d'identité) : c'est
  obligatoire sur les plateformes et c'est la seule étape qui engage une personne.

## Étapes
1. Créer un compte vendeur sur **Flippa** (flippa.com), puis un second sur **Acquire.com** si le
   projet y est accepté (le site vise les entreprises avec revenus ; un refus est possible).
2. Créer une annonce de type « SaaS & logiciels », en **annonce confidentielle** : le nom et l'adresse du
   projet restent masqués jusqu'à ce que le vendeur approuve l'accord de confidentialité d'un acheteur.
3. Coller le titre et la description ci-dessous. Ajouter les 7 captures d'écran.
4. Type de vente : cession d'actifs (code, nom, documentation). Chiffre d'affaires : 0. Clients : 0.
5. Prix demandé : 18 000 €, « ouvert aux offres ». Paiement par séquestre (Escrow.com).
6. Téléverser le modèle d'accord de confidentialité `NDA.md` (en PDF) si la plateforme le permet,
   sinon choisir son accord par défaut.
7. Publier. Ne communiquer ni le nom du vendeur, ni le dépôt GitHub, ni l'historique du code.

## Titre
FRETRAU : plateforme de courtage de fret routier par IA, code complet, pré-lancement

## Description
Plateforme web complète pour comparer, négocier et réserver du transport routier en France et en
Europe (camion complet et palettes).

Inclus : code source (Python, sans dépendance externe), 255 tests automatisés, moteur de devis,
agents de décision déterministes et auditables, espaces client, transporteur, chauffeur et
administrateur, facturation aux normes françaises, suivi, réclamations, sécurité renforcée,
déploiement Docker, documentation, nom.

À savoir : pas de clients, pas de transporteurs réels (données d'exemple), code développé avec l'aide
d'une IA sous direction humaine, textes juridiques à faire valider par un avocat, marque non déposée.
Démonstration locale sous accord de confidentialité.

Prix demandé : 18 000 €, ouvert aux offres. Paiement par séquestre.

## Quand un acheteur demande l'accès
1. Vérifier qu'il a signé l'accord de confidentialité (par la plateforme).
2. Lui remettre `fretrau-demo.zip` et lui expliquer : décompresser, lancer `LANCER-WINDOWS.bat` (ou
   `LANCER-MAC.command`), ouvrir http://127.0.0.1:8080. Python 3.11 ou plus récent est requis.
3. Transmettre chaque message reçu à Claude, qui prépare la réponse selon la stratégie de
   négociation du dossier. Le vendeur valide avant envoi.

## Questions fréquentes d'acheteurs (réponses prêtes)
- **Pourquoi vendre ?** Le vendeur n'a pas le temps de réaliser la partie commerciale et réglementaire.
- **Y a-t-il des clients ?** Non, le produit est en pré-lancement.
- **Les transporteurs sont-ils réels ?** Non, la base fournie est un exemple.
- **Le code est-il original ?** Il a été développé avec l'aide d'une IA sous la direction du vendeur ;
  la protection par le droit d'auteur n'est pas garantie dans toutes ses parties (écrit au contrat).
- **Peut-on l'exploiter en France sans licence ?** Non : l'exploitation d'un service de commission de
  transport suppose une inscription au registre des commissionnaires ; un modèle de simple mise en
  relation relève d'un autre régime. À faire valider par un juriste.
- **Quel support après la vente ?** Cinq heures d'assistance incluses, puis au tarif horaire convenu.
- **Peut-on tester ?** Oui, en local sous accord de confidentialité (paquet de démonstration).
