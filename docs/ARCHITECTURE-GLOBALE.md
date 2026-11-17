# FRETRAU — vue globale du projet

Légende d'état : **✅ réalisé et testé** · **🧪 simulé** (fonctionne, mais sur des données/hypothèses de simulation) · **📐 théorique** (code écrit et testé hors ligne avec des simulateurs, **jamais exécuté contre le vrai prestataire** : à valider avant usage) · **⛔ impossible sans partenaire** (réseau, contrat, licence).

Source de comparaison : les onglets et fonctions visibles sur linklane.ai (pages publiques consultées). Ce que LinkLane fait *derrière* son interface (algorithmes, réseau de transporteurs) n'est pas visible : FRETRAU recrée le comportement visible avec ses propres règles.

## 1. Rubriques du site

| Rubrique LinkLane | Équivalent FRETRAU | État |
|---|---|---|
| Camion complet (FTL) | `services/camion-complet.html` + calculateur | ✅ |
| Lot partiel (partial) | `services/lot-partiel.html` + `/estimation.html` (fourchette) | 📐 estimation non réservable, hypothèses `tariff.json → indicative` |
| Messagerie palettes (LTL) | `services/messagerie.html` | ✅ page ; tarification palettes via calculateur |
| Frigorifique (reefer) | `services/frigorifique.html`, option température | ✅ |
| Plateau (flatbed) | `services/plateau.html`, option `flatbed` (FTL) | ✅ (supplément 15 %, confiance faible) |
| Express | `services/express.html` | ✅ |
| Combiné rail-route (intermodal) | `services/combine.html` + `/estimation.html` | 📐 fourchette uniquement ; terminaux et horaires de trains non connectés |
| Questions fréquentes | `faq.html` + données structurées FAQPage | ✅ |
| À propos / Secteurs | `a-propos.html`, `secteurs.html` | ✅ (texte à relire par vous) |
| Devenir transporteur | `transporteurs.html` + `/api/carrier/apply` + contrôles `vetting` | ✅ contrôles de forme ; 📐 contrôles officiels en ligne (`verify_remote`) |
| Contact / prendre rendez-vous | `contact.html` (+ sujet « droits RGPD ») | ✅ |
| Suivi par code | `suivi.html` + accueil | ✅ jalons réels ; 🧪 timeline simulée si `FRETRAU_DEMO_TIMELINE=1` |
| Réclamation depuis l'envoi | `reclamation.html` + délais légaux + triage | ✅ |
| Choix de confidentialité | `confidentialite-choix.html` (STOP SMS, droits) | ✅ |
| Espace client | `compte.html` (code par e-mail, sans mot de passe) | ✅ testé avec un faux envoi d'e-mail ; 📐 envoi réel dépend de la config SMTP |
| Attribution GeoNames (CC-BY) | pied de page de toutes les pages | ✅ |

## 2. Fonctions de la plateforme

| Fonction | Où | État |
|---|---|---|
| Prix instantané FTL/messagerie, intervalle, marge | `pricing.py`, `tariff.json` | ✅ code ; 🧪 **les coefficients tarifaires sont des hypothèses**, à recaler sur vos vrais coûts |
| Toutes les communes (France + Europe) | `places.py`, `tools/import_places.py` | ✅ 70 353 lieux livrés dans `seed/places.db.gz` (35 434 communes françaises hors Corse/outre-mer + 34 919 localités de plus de 1 000 habitants dans les pays desservis) ; `tools/import_places.py` permet de rafraîchir |
| Conformité transporteur (licence, assurance, équipement, pays) | agent `compliance` | ✅ |
| Classement des transporteurs | agent `sourcing` (poids appris + règle de ponctualité) | 🧪 |
| Négociation automatique | agent `negotiation` (transporteurs simulés) | 🧪 jamais testée face à de vrais transporteurs |
| Décision multi-offres (coût espéré) | agent `decision` | 🧪 |
| Contrôle du risque (valeur vs assurance) | agent `risk` | ✅ |
| Second avis de coût | agent `costcheck` | ✅ |
| Saisie par e-mail (« envoyez votre demande ») | agent `intake`, `/api/intake/email`, passerelle | ✅ corpus 98/98 (auto-écrit) |
| Alignement sur un prix concurrent | agent `ratematch` | ✅ avec justificatif obligatoire |
| Anti-fraude à la réservation | agent `guard` | ✅ règles explicables ; passe en revue humaine, ne refuse jamais seul |
| Veille des retards (avant l'appel du client) | agent `watchtower`, `/api/admin/watchtower`, maintenance | ✅ |
| Triage des réclamations | agent `claims_triage` | ✅ |
| Enchaînement de chargements (« AI chains loads ») | `chaining.py` (écart ≤ 120 km, ≤ 2 jours) | ✅ suggestions pour l'humain, pas d'automatisme |
| Annulation 24 h gratuite, TONU, détention | CGV (`legal_texts`) | ✅ texte juridique, à faire valider par un avocat |
| Garantie de prix | CGV + alignement | ✅ texte |
| SMS (enlèvement, retard, livraison, facture ; STOP/HELP) | `sms.py`, `sms_outbox` | 📐 file + consentement + STOP testés ; envoi réel (Twilio ou passerelle) non testé |
| Position du chauffeur (lien personnel) | `driver.py`, `chauffeur.html` | ✅ logique et confidentialité testées ; 📐 la géolocalisation navigateur n'a pas été essayée sur un vrai téléphone |
| Paiement par carte (clients sans crédit) | `payments.py`, Stripe Checkout + webhook signé | 📐 signature et formulaire testés avec simulateur ; jamais appelé chez Stripe |
| Facture à 14 jours (clients avec crédit) | `invoicing.py` | ✅ |
| Paiement transporteur à échéance | `payables` | ✅ |
| Vérification SIREN/TVA officielle | `verify_remote.py` (annuaire des entreprises, VIES) | 📐 jamais exécuté en ligne ici |
| Annuaire des transporteurs réels d'une zone (Sirene, NAF 49.41A/B) | `directory.py`, `tools/import_carriers.py` | 📐 logique testée avec un faux service ; l'import réel exige Internet et n'a pas été lancé ici. Pas d'e-mail ni de prix dans la source : à compléter |
| Demande de devis aux transporteurs, lecture des réponses, comparaison | agent `rfq`, `/api/admin/rfq/*`, `/api/webhook/rfq-reply` | ✅ testé de bout en bout (envoi sur validation humaine, STOP, anti-doublon) ; 📐 réception réelle des e-mails à brancher (même passerelle que l'agent e-mail) |
| Recalage du barème sur les prix réels reçus | `/api/admin/rfq` → calibration | ✅ calcul ; jugé « fiable » seulement à partir de 20 réponses chiffrées |
| Administration (rôles, 2FA TOTP, audit chaîné) | `server.py`, `admin.html` | ✅ |
| Sauvegardes, rétention RGPD, anonymisation | `tools/backup.py`, `tools/maintenance.py` | ✅ |
| Télématique (position GPS du camion automatique) | — | ⛔ nécessite des contrats avec transporteurs/fournisseurs de télématique ; remplacée par le lien chauffeur |
| Réseau réel de transporteurs et tarifs de marché | — | ⛔ à constituer (candidatures, contrats) |
| Application mobile native | — | ⛔ non prévue ; le site est utilisable sur mobile |
| Assurance marchandises / responsabilité | — | ⛔ contrat d'assurance à souscrire |
| SSL / hébergement | `Dockerfile`, `render.yaml`, `deploy/` | ✅ fichiers ; ⛔ déploiement réel à faire par vous |

## 3. Ce qui reste à faire dans le monde réel

1. Communes : déjà livrées (seed). Rafraîchir si besoin.
2. Recaler `config/tariff.json` sur vos vrais coûts transporteurs (`tools/calibrate.py`).
3. Recruter des transporteurs réels ; les contrôles `vetting` + `verify_remote` aident à les valider.
4. Faire relire par un avocat : CGV, charte transporteur, mentions légales, politique de confidentialité.
5. Souscrire l'assurance ; ouvrir un compte Stripe en mode test pour valider le paiement ; ouvrir un compte SMS d'essai.
6. Déployer (SSL, sauvegardes planifiées, variables d'environnement) et activer la 2FA admin.
