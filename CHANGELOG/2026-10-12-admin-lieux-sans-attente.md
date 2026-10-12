# Admin des lieux : plus d'emplacements en attente / Venues admin: no waiting slots

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** La liste `Customers > Client` ne montre plus les emplacements en attente de configuration (`WAITING_CONFIG`), même à un superuser. ROOT reste caché. Un superuser voit toujours META (agenda partagé) dans la liste ; l'autocomplétion le retire toujours.
/ Waiting slots are no longer listed, even for superusers. Superusers still see META in the list.

**Pourquoi / Why :** Les emplacements en attente encombraient la liste sans servir (retour du 2026-10-12, suite de `2026-10-12-admin-lieux-recherche-domaine-email.md`).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` (`TenantAdmin.get_queryset`) | `WAITING_CONFIG` exclu pour tous |
| `tests/pytest/test_admin_liste_des_lieux.py` | 3 cas (liste superuser, autocomplétion, gestionnaire), vérifiés par mutation |

## Comment tester (a la main) / Manual test
1. En superuser, ouvrir `https://codecommun.coop/admin/Customers/client/` : aucun lieu de catégorie « en attente » ; le lieu META « Code Commun » est présent.

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_admin_liste_des_lieux.py -q`
