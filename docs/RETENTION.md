# Durées de conservation

| Donnée | Durée | Mécanisme |
|---|---|---|
| Devis sans commande | 30 jours | `maintenance.py` |
| Réservation (données personnelles) | 5 ans (`FRETRAU_RETENTION_YEARS`) puis anonymisation | `maintenance.py` |
| Factures | 10 ans (obligation comptable) | conservées, non modifiées |
| E-mails sortants | 90 jours | `maintenance.py` |
| Journal d'audit | à définir (12 mois conseillés pour les journaux techniques) | exportez puis archivez ; la chaîne de hachage empêche la suppression silencieuse |
| Sauvegardes | 30 jours glissants (`--keep 30`) | rotation. **Attention** : une personne effacée reste dans les sauvegardes jusqu'à leur expiration ; c'est indiqué comme limite acceptable si la rotation est courte. |

Droit d'accès/portabilité : `GET /api/admin/gdpr/export/<code>` (rôle admin). Effacement : `POST /api/admin/gdpr/anonymize`.
