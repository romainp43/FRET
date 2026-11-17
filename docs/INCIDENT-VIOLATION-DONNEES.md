# Plan de réponse à incident / violation de données (modèle)

Brouillon à valider. Objectif : agir vite, tracer, notifier dans les délais légaux.

1. **Détecter** : alerte de la chaîne d'audit (`tools/maintenance.py` code retour 2), connexion admin inattendue, signalement via `/.well-known/security.txt`, comportement anormal des journaux.
2. **Contenir (0–2 h)** : désactiver les comptes concernés (`python3 tools/manage_users.py disable <nom>`), changer `FRETRAU_SECRET` (invalide toutes les sessions) et `FRETRAU_WEBHOOK_SECRET`, bloquer l'IP au pare-feu, isoler le serveur si besoin. Faire une **copie forensique** (`tools/backup.py backup`) avant toute remise en état.
3. **Évaluer (≤ 24 h)** : quelles données, combien de personnes, risque pour elles ? Consigner dans un registre des violations (même si non notifiée, art. 33.5).
4. **Notifier la CNIL dans les 72 h** après en avoir pris connaissance si la violation présente un risque pour les droits et libertés (téléservice de notification de la CNIL). Informer les personnes **sans délai** si le risque est élevé. Informer aussi les clients/sous-traitants concernés selon les contrats.
5. **Corriger** : cause racine, correctif, rotation des secrets, restauration depuis une sauvegarde vérifiée (`tools/backup.py verify` puis `restore`).
6. **Capitaliser** : post-mortem sans reproche, mise à jour de ce plan et des tests.

Contacts à renseigner : responsable sécurité, DPO/juriste, hébergeur (astreinte), assureur cyber.
