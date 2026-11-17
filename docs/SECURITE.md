# Sécurité — ce qui est en place, ce qui reste à faire

## Mapping avec vos exigences
| Exigence | Réponse dans FRETRAU |
|---|---|
| **Certificat SSL / HTTPS** | `deploy/Caddyfile` (certificat Let's Encrypt automatique + renouvellement) ou `deploy/nginx.conf` + certbot. HSTS, redirection 80→443. Cookies `Secure` avec `FRETRAU_HTTPS=1`. **Le certificat ne peut être délivré que sur votre serveur avec votre nom de domaine** : il n'est pas "installé" par le code. |
| **Mises à jour régulières** | Pas de CMS, **aucune dépendance Python** (bibliothèque standard) : surface d'attaque minimale. À mettre à jour : Python (image `python:3.13-slim`, Dependabot hebdomadaire pour Docker et GitHub Actions), système d'exploitation, Caddy. Politique : correctifs de sécurité sous 7 jours. |
| **Mots de passe / MFA / moindre privilège** | Comptes nominatifs `tools/manage_users.py` : rôles admin / ops / finance, mot de passe ≥ 12 car. (scrypt), **2FA TOTP obligatoire**, verrouillage après 5 échecs, désactivation immédiate, actions journalisées au nom de l'utilisateur. |
| **Pas de secrets côté navigateur** | Tous les secrets en variables d'environnement (`.env` chmod 600, jamais commité : `.gitignore`). Un test échoue si `web/` contient une clé ou un script inline. |
| **Validation des entrées** | Validation stricte serveur (types, longueurs, listes blanches, regex), requêtes SQL paramétrées, échappement HTML, CSP sans script inline, limite de taille de corps, anti-CSRF (en-tête + cookie SameSite=Strict + contrôle d'origine), honeypot, limitation de débit. |
| **Authentification reconnue** | Le code utilise scrypt + TOTP (standards). Pour la production grand public ou plusieurs dizaines d'employés, un fournisseur d'identité dédié est préférable à un système maison : **Keycloak/Authelia auto-hébergé, ou Clerk/Supabase Auth (région UE)**. Le point d'intégration est `resolve_role()` dans `server.py`. |
| **Sauvegardes** | `tools/backup.py` : copie cohérente (API de sauvegarde SQLite), contrôle d'intégrité, SHA-256, chiffrement `age` optionnel, rotation, `verify` et `restore`. Planifiée chaque nuit (`deploy/fretrau-maintenance.timer`). **Copie externe obligatoire** (autre fournisseur/région) et **test de restauration trimestriel**. Sauvegarder aussi `config/` et le code (Git). |
| **Rétention RGPD** | `tools/maintenance.py` : purge devis 30 j, anonymisation 5 ans, e-mails 90 j, vérification de la chaîne d'audit. |

## Limites honnêtes
- Ce n'est **pas** un audit de sécurité. Faites réaliser un test d'intrusion avant d'exposer des clients réels.
- SQLite convient à un démarrage ; passez à PostgreSQL managé (UE) quand vous avez plusieurs instances ou un volume important.
- Les limiteurs de débit sont en mémoire (une instance). Derrière plusieurs instances, déplacez-les dans Redis ou le proxy.
- Les e-mails entrants (négociation) reposent sur un webhook signé : protégez le secret et la source.
