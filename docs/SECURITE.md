# Sécurité et conformité : état des lieux

Aucun site n'est « 100 % sécurisé ». L'objectif réaliste est triple : rendre une attaque difficile, limiter
ce qu'elle peut atteindre, et pouvoir tout restaurer. Ce document dit ce qui est fait dans le code, et ce qui
dépend de l'hébergement et de l'organisation, donc de toi.

## 1. En place dans le logiciel

| Risque | Protection |
|---|---|
| Vol de mots de passe | Hachage scrypt, 10 caractères minimum, refus des mots de passe devinables, verrouillage après 5 échecs |
| Vol de session | Cookie `HttpOnly`, `SameSite=Strict`, `Secure` en HTTPS ; changer le mot de passe déconnecte tous les appareils |
| Prise de contrôle de l'admin | Double authentification (TOTP), session courte, jetons admin et client signés avec des clés distinctes |
| Usurpation d'adresse e-mail | Lien de confirmation à usage unique ; sans confirmation, un compte ne voit jamais les envois passés sans compte |
| Mot de passe oublié détourné | Lien valable 1 h, usage unique, stocké haché ; la réponse ne révèle pas si un compte existe |
| Injection (SQL, HTML, scripts) | Requêtes paramétrées, aucun script ni style inline, politique CSP stricte, affichage en texte seul |
| Requêtes forgées depuis un autre site | En-tête obligatoire sur toutes les actions connectées, contrôle de l'origine |
| Manipulation des agents IA par un message piégé | Le modèle ne fixe jamais un prix et n'attribue jamais un transport : il extrait des champs ou choisit entre trois mots, et le code revalide tout |
| Vente à perte, attribution hors règles | Plafond d'achat appliqué à tous les canaux, y compris l'admin |
| Transporteur non conforme | Contrôle automatique du SIRET, puis validation humaine des pièces obligatoire |
| Abus et robots | Limitation de débit par adresse IP, champs pièges, taille des requêtes bornée |
| Falsification de l'historique | Journal d'audit chaîné : toute modification est détectable |
| Perte de données | Base en mode WAL, sauvegarde vérifiée toutes les 6 h si `FRETRAU_BACKUP_DIR` est défini, 30 copies conservées |
| Conservation excessive | Purge automatique des devis non réservés (90 jours) et des e-mails bruts (1 an) |
| Droits des personnes (RGPD) | Export des données et suppression du compte depuis `/compte` |
| Preuve du consentement | Version des CGU/CGV acceptée et horodatage enregistrés avec le compte et chaque réservation |

## 2. Ce qui dépend de l'hébergement (à faire avant l'ouverture)

1. **HTTPS obligatoire** : serveur derrière un proxy TLS, `FRETRAU_HTTPS=1`, `FRETRAU_TRUST_PROXY=1`.
2. **Secrets** : `FRETRAU_SECRET`, `FRETRAU_ADMIN_PASSWORD`, `FRETRAU_ADMIN_TOTP_SECRET`, `FRETRAU_WEBHOOK_SECRET`
   générés aléatoirement, stockés dans le coffre de l'hébergeur, jamais dans le dépôt GitHub.
3. **Sauvegardes hors site** : `FRETRAU_BACKUP_DIR` sur un autre disque, puis copie quotidienne chiffrée chez un
   autre fournisseur. Tester une restauration complète une fois par mois (`tools/backup.py`).
4. **Disque chiffré** et hébergement dans l'Union européenne.
5. **Mises à jour** du système, pare-feu n'ouvrant que le port 443, accès serveur par clé uniquement.
6. **Supervision** : alerte si le site tombe, si une sauvegarde manque, si le journal d'audit est altéré.
7. **Dépôt GitHub en privé**, double authentification activée sur GitHub, l'hébergeur, la messagerie et le nom de domaine.
8. **Test d'intrusion** par un prestataire indépendant avant l'ouverture, puis une fois par an.

## 3. Ce qui dépend de l'organisation

- **Registre des traitements** (obligatoire) : la politique de confidentialité en donne la trame.
- **Contrats de sous-traitance** (article 28 du RGPD) avec l'hébergeur, le service d'e-mail et le fournisseur d'IA.
- **Violation de données** : notification à la CNIL sous 72 heures si elle présente un risque, information des
  personnes si le risque est élevé. Tenir un registre des incidents.
- **Assurance** : responsabilité civile professionnelle de commissionnaire, et une assurance cyber.
- **Textes légaux** : `/mentions-legales`, `/cgu`, `/cgv`, `/confidentialite` sont des modèles. Ils doivent être
  relus par un avocat et complétés avec les informations de la société (variables `FRETRAU_SELLER_*`,
  `FRETRAU_HOST_*`, `FRETRAU_DIRECTOR`, `FRETRAU_INSURER`, `FRETRAU_PRIVACY_EMAIL`).
- **Accès admin** : une personne, un compte. Le logiciel n'a aujourd'hui qu'un seul compte admin : à faire évoluer
  dès qu'une deuxième personne rejoint l'équipe.

## 4. Limites connues du prototype

- Serveur et base prévus pour un démarrage (SQLite, un seul processus). Au-delà de quelques dizaines de
  réservations par jour : PostgreSQL et un serveur d'application.
- Pas de dépôt de pièces en ligne (licence, assurance, preuve de livraison signée).
- Pas d'envoi de SMS ; les e-mails ne partent que si un service SMTP est configuré.
- Limitation de débit en mémoire : remise à zéro à chaque redémarrage.
- Aucun test d'intrusion externe n'a été réalisé.
