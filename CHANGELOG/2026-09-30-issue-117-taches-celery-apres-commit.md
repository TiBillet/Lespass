# Issue #117 : les tâches Celery d'une adhésion partent après le COMMIT / Membership Celery tasks are dispatched after COMMIT

**Date :** 2026-09-30
**Migration :** Non

**FR :** Une adhésion créée dans l'admin est écrite dans une transaction. Le worker Celery
a sa propre connexion à la base : une tâche partie avant le COMMIT ne trouve pas encore
l'utilisateur ou l'adhésion et plante sur « DoesNotExist » (issue GitHub #117).
Le mail de connexion était déjà corrigé (commit `cd1931f9`, `AuthBillet/utils.py`).
Les trois tâches lancées par `trigger_A` (mail de confirmation d'adhésion, Ghost, Brevo)
passent maintenant aussi par `transaction.on_commit`. Des tests de non-régression couvrent
les deux correctifs.

**EN :** A membership created in the admin is written inside a transaction. A Celery task
dispatched before COMMIT cannot find the user or the membership yet (GitHub issue #117).
The login mail was already fixed (commit `cd1931f9`). The three tasks fired by `trigger_A`
(membership confirmation mail, Ghost, Brevo) now also go through `transaction.on_commit`.
Regression tests cover both fixes.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/triggers.py` | `trigger_A` : les 3 `.delay()` partent dans `transaction.on_commit` |
| `tests/pytest/test_taches_celery_apres_commit_issue_117.py` | Nouveaux tests / New tests |
| `tests/pytest/test_commande_service.py`, `tests/pytest/test_parite_avec_sans_panier.py` | 3 tests jouent le COMMIT avec `django_capture_on_commit_callbacks` |
