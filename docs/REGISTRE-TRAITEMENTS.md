# Registre des activités de traitement (RGPD art. 30) — modèle FRETRAU

> Brouillon à faire valider par un juriste / DPO. Les durées reprennent la politique de confidentialité (`web/legal`) et l'automatisation `tools/maintenance.py`.

Responsable de traitement : [À COMPLÉTER : société]. Contact : [À COMPLÉTER : e-mail RGPD]. DPO : à désigner si requis (traitement à grande échelle improbable au démarrage ; à réévaluer).

| # | Traitement | Finalité | Personnes | Données | Base légale | Destinataires | Conservation | Mesures de sécurité |
|---|-----------|----------|-----------|---------|-------------|---------------|--------------|---------------------|
| 1 | Devis | Calculer un prix | Visiteurs (aucune identité) | Trajet, poids, options, dates | Précontractuel | Interne | 30 j si pas de commande (purge auto) | HTTPS, limitation de débit |
| 2 | Commande de transport | Exécuter le transport | Contacts du donneur d'ordre, contact sur site | Nom, société, e-mail, tél., adresses, créneaux, marchandise, consignes | Contrat | Transporteur affecté, hébergeur, e-mail | 5 ans puis anonymisation auto | Accès par rôle + 2FA, journal d'audit chaîné |
| 3 | Facturation | Obligations comptables | Clients professionnels | Identité, montants | Obligation légale | Expert-comptable | 10 ans | Numérotation séquentielle, accès finance/admin |
| 4 | Preuve d'acceptation des CGV | Preuve en cas de litige | Donneurs d'ordre | Version CGV, horodatage, empreinte IP | Intérêt légitime | Interne | Durée relation + 5 ans | IP jamais stockée en clair |
| 5 | Sécurité | Prévenir fraude / abus | Tous | Journal d'audit, limitation de débit | Intérêt légitime | Interne | 12 mois (journaux techniques) | Chaîne de hachage vérifiée chaque nuit |
| 6 | E-mails de service | Confirmations, suivi | Contacts | Adresse, contenu | Contrat | Prestataire SMTP | 90 j (purge auto) | TLS SMTP |
| 7 | Demandes de droits | Répondre aux personnes | Demandeurs | Identité, demande | Obligation légale | Interne | 5 ans | Accès admin uniquement |

Transferts hors UE : aucun prévu. Décisions automatisées : prix et affectation par règles vérifiables ; escalade humaine pour valeur élevée / anomalies ; droit de contestation décrit dans la politique de confidentialité.

**Analyse d'impact (AIPD)** : non requise a priori (pas de profilage de personnes, pas de données sensibles). À revoir si vous ajoutez de la géolocalisation en continu des chauffeurs (suivi GPS de salariés de transporteurs = traitement à évaluer).

## Sous-traitants (art. 28) — contrats à signer
| Sous-traitant | Rôle | À faire |
|---|---|---|
| Hébergeur [À COMPLÉTER] | Hébergement de la base | DPA + région UE |
| Prestataire SMTP [À COMPLÉTER] | Envoi d'e-mails | DPA, TLS |
| Expert-comptable / logiciel de facturation | Comptabilité | DPA |
| Anthropic (API Claude, optionnel) | Rédaction de messages | N'envoyer **aucune** donnée d'identité (déjà le cas dans le code) ; vérifier le DPA et les conditions de transfert avant activation |
| Stockage de sauvegarde externe [À COMPLÉTER] | Copie hors site | Chiffrement `age` avant envoi ; région UE |
