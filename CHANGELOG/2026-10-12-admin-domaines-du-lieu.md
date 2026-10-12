# Admin des lieux : domaines modifiables / Venues admin: editable domains

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Sur la fiche d'un lieu (`Customers > Client > modifier`), un **superuser** peut ajouter, modifier et supprimer les domaines du lieu, et cocher le **domaine principal** (inline `DomainesDuLieuInline`).
- Contrôles :
  - un seul domaine principal, au moins un domaine ;
  - le domaine est saisi seul (pas de `https://` ni de chemin) ; il est mis en minuscules.
- Après enregistrement, le cache du domaine principal du `CanonicalDomainRedirectMiddleware` (1 h, clé préfixée par le schéma du lieu) est vidé : les visiteurs ne sont pas redirigés vers l'ancien domaine.
- La fiche du lieu elle-même reste en lecture seule et n'est jamais enregistrée (`save_model` vide) : django-tenants refuse d'enregistrer un lieu depuis le schéma d'un autre lieu, et l'admin tourne toujours sur un lieu (ex. codecommun).
- Un admin de lieu non superuser ne voit pas les domaines et ne peut rien enregistrer sur la fiche.

/ Superusers can manage a venue's domains and its primary domain from the venue admin page; the redirect middleware cache is cleared on save.

**Hors périmètre / Out of scope :** un domaine propre (hors `*.tibillet.coop`) doit aussi être routé par Traefik et avoir son certificat ; le résumé SEO du lieu (domaine) se met à jour au prochain beat (4 h).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `DomaineDuLieuForm`, `DomainesDuLieuFormSet`, `DomainesDuLieuInline` ; `TenantAdmin` : `get_inlines`, `get_readonly_fields`, `has_change_permission` (superuser), `save_model`, `save_formset` |
| `tests/pytest/test_admin_domaines_du_lieu.py` | 7 tests (vérifiés par mutation) |

**i18n :** 5 nouvelles chaînes (`Domaine`, `Domaines`, `Cochez un seul domaine principal.`, `Un lieu doit garder au moins un domaine.`, `Saisissez le nom de domaine seul…`) — `makemessages` à lancer.

## Comment tester (a la main) / Manual test
1. En superuser, ouvrir `https://codecommun.coop/admin/Customers/client/<uuid>/change/` : tableau « Domaines » avec la case « principal ».
2. Ajouter un domaine, le cocher principal, enregistrer : l'ancien n'est plus principal ; le site redirige vers le nouveau.
3. Cocher deux principaux, ou saisir `https://x.fr/` : message d'erreur, rien n'est enregistré.
4. En admin de lieu non superuser : pas de tableau, pas de bouton d'enregistrement.

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_admin_domaines_du_lieu.py -q`
