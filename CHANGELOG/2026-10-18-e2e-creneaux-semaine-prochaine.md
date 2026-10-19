# Tests E2E : les créneaux de ressource pris la semaine prochaine / E2E tests: resource slots taken next week

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** trois tests E2E ouvrent désormais la page d'une ressource sur la semaine prochaine (`?semaine=<lundi prochain>`, dans le fuseau du lieu) avant de cliquer le premier créneau libre : `test_booking_formulaire_dynamique.py` (ses deux tests, via `ouvrir_le_formulaire_du_premier_creneau`) et `test_panier_flow.py::test_e4_…`. Refactoring interne des tests / Internal test refactoring.
/ Three E2E tests now open the resource page on next week before clicking the first free slot.

**Pourquoi / Why :** depuis `2026-10-18-booking-calendrier-une-semaine.md`, la page d'une ressource ne rend que la semaine en cours. Un dimanche soir, cette semaine n'a plus aucun créneau libre : les trois tests attendaient 30 s un créneau qui n'existait pas. La semaine prochaine en a toujours (même motif que `test_booking_calendrier_semaine.py`).
/ The resource page now renders the current week only; on a Sunday evening it has no free slot left.

**Aussi / Also :** `test_adhesion_recompense_puis_qrcode.py`, `_solde_depensable` lit un solde nul tant que l'adhérent n'a pas de portefeuille. Il est créé par la tâche Celery de récompense, juste avant le versement ; tant qu'elle n'a pas tourné, la lecture plantait (`'NoneType' object has no attribute 'uuid'`) au lieu de laisser la boucle d'attente continuer. Échec intermittent, vu une fois sur trois passages.
/ `_solde_depensable` reads a zero balance while the member has no wallet yet (the Celery reward task creates it), instead of crashing the polling loop.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_booking_formulaire_dynamique.py` | `lundi_prochain_au_lieu(django_shell)` ; `ouvrir_le_formulaire_du_premier_creneau` prend `django_shell` et ouvre `?semaine=` |
| `tests/e2e/test_panier_flow.py` | `test_e4_…` ouvre la salle sur la semaine prochaine |
| `tests/e2e/test_adhesion_recompense_puis_qrcode.py` | `_solde_depensable` : pas de portefeuille = solde nul |

---

## Comment tester (a la main) / Manual test
### Test 1 — un dimanche soir
1. `make e2e ARGS="tests/e2e/test_booking_formulaire_dynamique.py tests/e2e/test_panier_flow.py -q"` un dimanche après la fermeture des créneaux du jour.
2. Les trois tests passent (les tests `stripe_listen` du panier exigent `stripe listen`).
