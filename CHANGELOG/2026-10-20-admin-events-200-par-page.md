# Admin : 200 événements par page / Admin: 200 events per page

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :** La liste admin des événements affiche 200 lignes par page au lieu de 20.
/ The admin event list shows 200 rows per page instead of 20.
**Pourquoi / Why :** Moins de pagination pour les lieux qui ont beaucoup d'événements.
/ Less paging for venues with many events.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `EventAdmin.list_per_page` : 20 → 200 |

---

## Comment tester (a la main) / Manual test
1. Ouvrir `/admin/BaseBillet/event/` sur un tenant qui a plus de 20 événements.
2. Tous les événements (jusqu'à 200) sont sur la première page.
3. Mesure en dev (140 événements sur une page) : 78 requêtes SQL, ~1 s, ~940 Ko de HTML.
