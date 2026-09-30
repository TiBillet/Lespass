# Issue #117 : tâches Celery d'une adhésion après le COMMIT

## Ce qui a été fait
Dans `BaseBillet/triggers.py` (`trigger_A`), le mail de confirmation d'adhésion et les envois
Ghost / Brevo partent maintenant dans `transaction.on_commit`. Le mail de connexion d'un
nouvel utilisateur (`AuthBillet/utils.py`, `sender_mail_connect`) l'était déjà.

Détails : `CHANGELOG/2026-09-30-issue-117-taches-celery-apres-commit.md`.

## Tests à réaliser

### Test 1 : adhésion créée dans l'admin, nouvel email
1. Admin > Adhésions > Ajouter, avec un email qui n'existe pas encore.
2. Enregistrer.
3. Logs du worker Celery : pas de `TibilletUser.DoesNotExist` ni de `Membership.DoesNotExist`,
   pas de message « not found, retrying ».
4. L'adhérent reçoit le mail de connexion et le mail de confirmation d'adhésion.

### Test 2 : adhésion avec newsletter (Ghost / Brevo configurés)
1. Prendre une adhésion en cochant la newsletter.
2. Le contact apparaît dans Ghost et dans Brevo.

### Test 3 : formulaire admin invalide
1. Admin > Adhésions > Ajouter, avec une erreur dans le formulaire.
2. Aucun mail ne part.

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_taches_celery_apres_commit_issue_117.py -v
```

## Compatibilité
Hors transaction, `on_commit` lance la fonction tout de suite : aucun changement.
Les `time.sleep` et nouveaux essais des tâches (`BaseBillet/tasks.py`) sont conservés.
