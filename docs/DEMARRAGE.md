# Du prototype à l'activité réelle

Points réglementaires donnés à titre indicatif : à confirmer avec la DREAL Auvergne-Rhône-Alpes,
un expert-comptable et un assureur avant toute décision.

## 1. Le cadre légal (bloquant)

Revendre du transport routier en son nom sans posséder de camions, c'est l'activité de
**commissionnaire de transport**. Elle est réglementée.

| Étape | Ce que c'est |
|---|---|
| Attestation de capacité professionnelle de commissionnaire | Obtenue par examen, par équivalence de diplôme ou par expérience. Elle doit être détenue par la personne qui dirige effectivement l'activité. C'est l'étape la plus longue : à lancer en premier. |
| Création de la société | Forme, capital, siège (Raucoules), objet social mentionnant la commission de transport. |
| Inscription au registre des commissionnaires | Dossier auprès de la DREAL de la région du siège. Conditions : capacité professionnelle et honorabilité. |
| Assurance | Responsabilité civile professionnelle de commissionnaire, couvrant aussi la marchandise confiée. |
| Documents commerciaux | CGV (le contrat type « commission de transport » s'applique par défaut), mentions légales, politique de confidentialité. |

Le commissionnaire répond de ses transporteurs devant son client : une marchandise perdue ou un transporteur
défaillant, c'est lui qui indemnise d'abord. D'où l'importance de l'assurance et du contrôle des transporteurs.

Alternative pour démarrer sans la capacité : s'associer à (ou salarier) un titulaire de l'attestation, ou
travailler comme apporteur d'affaires d'un commissionnaire existant. À valider juridiquement.

## 2. Contrôler un transporteur avant de lui confier un chargement

Équivalent français du contrôle fait aux États-Unis sur la licence fédérale et l'assurance :

- licence de transport (communautaire ou intérieure) et inscription au registre des transporteurs ;
- attestation d'assurance en cours de validité (responsabilité civile et marchandises transportées) ;
- extrait Kbis récent ;
- attestation de vigilance URSSAF, à redemander tous les six mois dès 5 000 € HT de prestations.

Dans l'admin, la case « J'ai contrôlé les pièces » est obligatoire pour passer un transporteur en « Vérifié ».

## 3. Les comptes à ouvrir

Les fournisseurs de LinkLane ne sont pas publics, à une exception près (un service américain de vérification
des transporteurs, sans équivalent direct en France). Voici les briques équivalentes :

| Besoin | Exemples | Branchement |
|---|---|---|
| Lecture des e-mails et rédaction par IA | Clé API Claude | `ANTHROPIC_API_KEY` |
| E-mails sortants | Tout service SMTP | `FRETRAU_SMTP_*` |
| E-mails entrants (devis@, réponses transporteurs) | Service qui transforme un e-mail en appel web | `/api/webhook/inbound-quote` et `/api/webhook/inbound-mail`, `FRETRAU_WEBHOOK_SECRET` |
| Distances routières poids lourds | Service d'itinéraire | à brancher dans `fretrau/geo.py` |
| Prix de marché | Indices CNR (gazole, coûts), données de bourses de fret | `FRETRAU_FUEL_SURCHARGE`, barème de `fretrau/pricing.py` |
| Capacité complémentaire | Bourses de fret (B2PWeb, Teleroute, Timocom) | abonnement, usage manuel au début |
| Hébergement | Serveur avec HTTPS, base sauvegardée | voir README |
| Encaissement et factures | Banque, facturation électronique conforme à la réforme | à voir avec l'expert-comptable |

## 4. Ordre conseillé

1. Lancer la capacité professionnelle et choisir le nom (vérifier la marque à l'INPI et le nom de domaine).
2. Pendant ce temps : montrer la démonstration à quelques expéditeurs et transporteurs proches pour valider l'intérêt.
3. Créer la société, s'inscrire au registre, s'assurer.
4. Ouvrir les comptes du tableau, mettre en ligne, passer `FRETRAU_DEMO=0`.
5. Importer les prospects autour de Raucoules, les appeler, contrôler leurs pièces, valider les premiers.
6. Premiers transports réels avec un humain derrière chaque dossier ; recaler le barème sur les prix obtenus.
