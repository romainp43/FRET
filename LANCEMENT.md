# Guide de lancement FRETRAU

1. `python3 tools/preflight.py` : liste ce qui bloque (BLOQUANT) et ce qui est risqué.
2. Compléter `config/company.json` (raison sociale, SIRET, licence de commissionnaire de transport, assurance, médiateur…).
3. Variables d'environnement : mot de passe admin, `FRETRAU_SECRET`, SMTP, URL publique, hôtes autorisés, base de données sur disque persistant.
4. Hébergement avec HTTPS (reverse proxy), domaine, sauvegardes (`tools/maintenance.py`).
5. Transporteurs : remplacer les transporteurs fictifs (`tools/import_carriers.py`, module RFQ) et faire valider assurance/licences.
6. Relecture juridique des CGV/mentions par un avocat ; validation des prestataires réels (paiement, SMS, vérification) avant ouverture.
