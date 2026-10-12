# Admin des lieux : recherche par domaine et par email d'admin / Venues admin: search by domain and admin email

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Dans l'admin `Customers > Client` (liste des lieux), la recherche trouve aussi un lieu par son nom de domaine. Pour les superusers seulement, et seulement quand le texte tapé contient un « @ », elle le trouve aussi par l'email de l'un de ses admins.
/ The venues admin search also matches domain names, and, for superusers only and when the text contains an "@", the email of a venue admin.
**Pourquoi / Why :** Retrouver vite un lieu depuis une URL ou depuis l'email d'un contact. Le « @ » est exigé : une même personne administre souvent des dizaines de lieux, et un simple mot (« commun ») remontait tous ses lieux, noyant le lieu cherché. L'email est réservé aux superusers : la liste et son autocomplétion sont ouvertes à tout admin de lieu, qui pourrait sinon découvrir quels lieux une personne administre.
/ Find a venue quickly from a URL or a contact email. Email search is superuser-only to avoid revealing who administers which venue.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `TenantAdmin.search_fields` + `domains__domain` ; `get_search_fields()` ajoute `user_admin__email` pour les superusers, si le texte contient « @ » |

---

## Comment tester (a la main) / Manual test
### Test 1 — domaine
1. En superuser : `/admin/Customers/client/`, chercher une partie d'un domaine (ex. `codecommun.tibillet`).
2. Le lieu apparaît, une seule fois.

### Test 2 — email d'admin (superuser)
1. Chercher l'email d'un admin de lieu (ou `prenom@`) → ses lieux apparaissent.
2. Chercher un simple mot (`commun`) → seuls les lieux dont le nom ou le domaine contient ce mot apparaissent.

### Test 3 — email d'admin (admin de lieu, non superuser)
1. Même recherche par email → aucun résultat. La recherche par nom et par domaine marche toujours.

### Superusers : tous les lieux, schéma et catégorie
**Quoi / What :** Un superuser voit dans la liste les lieux META (agenda partagé) et les emplacements en attente de configuration. ROOT (schéma public) reste toujours caché. Deux colonnes en plus pour lui : nom du schéma et catégorie. La recherche porte aussi sur le nom du schéma. L'autocomplétion (fédération, invitations) et les admins de lieu gardent l'exclusion des lieux techniques. La colonne « Domaine principal » affiche « - » pour un lieu sans domaine.
/ Superusers also see META venues and waiting slots in the list (never ROOT), with schema name and category columns, and can search by schema name. Autocomplete and venue admins keep the exclusion.
**Pourquoi / Why :** codecommun.tibillet.coop était introuvable : sa catégorie le faisait exclure de la liste, et son nom de schéma n'apparaissait nulle part.

**Test :** en superuser, chercher `codecommun` → le lieu apparaît avec son schéma et sa catégorie. En admin de lieu, il n'apparaît pas.
