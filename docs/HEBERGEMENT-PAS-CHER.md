# Héberger FRETRAU au plus bas coût

Trois étapes, de la moins chère à la plus solide. Les prix sont ceux relevés en novembre 2026 : vérifiez-les avant de payer.

## Étape 0 — Démonstration gratuite (0 €)
But : montrer le site à des interlocuteurs, sans vrais clients.
- Sur votre PC : `py server.py`, puis ouvrir http://127.0.0.1:8080.
- Pour le rendre visible à distance (sans nom de domaine) : le service gratuit Cloudflare Tunnel en mode « rapide » donne une adresse temporaire en https ; elle disparaît quand vous fermez le programme et n'est pas faite pour la production.
- Autre option : `render.yaml` (déploiement « Blueprint » sur render.com, offre gratuite). Attention : le disque est éphémère, les réservations sont perdues à chaque redémarrage. Démonstration uniquement.
- Gardez `FRETRAU_DEMO_TIMELINE` actif : le suivi est simulé, ce qui est normal en démonstration.

## Étape 1 — Lancement réel au plus bas coût (environ 5 à 10 € par mois, domaine inclus)
- **Serveur** : une petite machine virtuelle Linux. Deux pistes : l'offre « Always Free » d'Oracle Cloud (gratuite, mais carte bancaire demandée à l'inscription, capacité parfois indisponible, quota réduit en 2026 à 2 processeurs et 12 Go) ou un petit serveur payant chez un hébergeur européen (compter environ 5 à 6 € par mois).
- **Nom de domaine** : environ 10 € par an chez un bureau d'enregistrement.
- **HTTPS** : gratuit avec Caddy (`deploy/Caddyfile`, certificat automatique Let's Encrypt).
- **Installation** : `docker compose up -d` (voir `docker-compose.yml`) après avoir copié `.env.example` vers `.env`.
- **Sauvegarde** : `tools/backup.py` chaque nuit (voir `deploy/fretrau-maintenance.timer`), avec copie hors du serveur.
- **E-mails** : le plan gratuit de Brevo (300 e-mails par jour, sans carte bancaire) suffit au démarrage. Dans `.env` : `FRETRAU_SMTP_HOST`, `FRETRAU_SMTP_PORT=587`, `FRETRAU_SMTP_USER`, `FRETRAU_SMTP_PASSWORD`, `FRETRAU_SMTP_FROM` (valeurs fournies dans votre compte Brevo ; il faut valider votre domaine).
- **Itinéraires poids lourd** : clé gratuite openrouteservice dans `FRETRAU_ORS_KEY` (2 000 itinéraires par jour).

## Étape 2 — Quand il y a du volume
Serveur plus gros, base de données sauvegardée en continu, plan e-mail payant, support. Rien à faire avant.

## Variables à définir (étape 1)
FRETRAU_ADMIN_PASSWORD (12 caractères minimum) · FRETRAU_SECRET (32 caractères minimum) · FRETRAU_HTTPS=1 · FRETRAU_TRUST_PROXY=1 ·
FRETRAU_PUBLIC_URL=https://votre-domaine · FRETRAU_ALLOWED_HOSTS=votre-domaine · FRETRAU_DB=/data/fretrau.db ·
FRETRAU_DEMO_TIMELINE=0 · FRETRAU_OPS_EMAIL · FRETRAU_ORS_KEY · FRETRAU_SMTP_*
Vérification finale : `python3 tools/preflight.py` doit n'afficher aucun BLOQUANT.

## Ce qui ne doit pas être économisé
Assurance de responsabilité civile, inscription au registre des commissionnaires, relecture des conditions de vente : ce ne sont pas des coûts d'hébergement, et les omettre expose à un risque bien supérieur.
