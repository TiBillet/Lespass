# Admin des lieux : recherche par domaine et par email d'admin / Venues admin: search by domain and admin email

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Dans l'admin `Customers > Client` (liste des lieux), la recherche trouve aussi un lieu par son nom de domaine. Pour les superusers seulement, elle le trouve aussi par l'email de l'un de ses admins.
/ The venues admin search also matches domain names, and, for superusers only, the email of a venue admin.
**Pourquoi / Why :** Retrouver vite un lieu depuis une URL ou depuis l'email d'un contact. L'email est réservé aux superusers : la liste et son autocomplétion sont ouvertes à tout admin de lieu, qui pourrait sinon découvrir quels lieux une personne administre.
/ Find a venue quickly from a URL or a contact email. Email search is superuser-only to avoid revealing who administers which venue.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `TenantAdmin.search_fields` + `domains__domain` ; `get_search_fields()` ajoute `user_admin__email` pour les superusers |

---

## Comment tester (a la main) / Manual test
### Test 1 — domaine
1. En superuser : `/admin/Customers/client/`, chercher une partie d'un domaine (ex. `codecommun.tibillet`).
2. Le lieu apparaît, une seule fois.

### Test 2 — email d'admin (superuser)
1. Chercher l'email d'un admin de lieu → ses lieux apparaissent.

### Test 3 — email d'admin (admin de lieu, non superuser)
1. Même recherche par email → aucun résultat. La recherche par nom et par domaine marche toujours.
