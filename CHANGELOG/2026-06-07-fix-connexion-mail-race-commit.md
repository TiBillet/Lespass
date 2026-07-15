# Fix — mail de connexion dispatché avant COMMIT (`DoesNotExist` Celery)

**Date :** 2026-06-07
**Migration :** Non

## Ce qui a été fait

La tâche Celery `connexion_celery_mailer` plantait par intermittence avec
`TibilletUser.DoesNotExist` dans le conteneur `lespass_celery`, pour des emails
de vrais utilisateurs (ex : `cygnetia@hotmail.fr`).

**Cause :** `sender_mail_connect()` (`AuthBillet/utils.py`) appelait
`connexion_celery_mailer.delay(...)` **pendant** une transaction encore ouverte.
Le worker Celery, sur sa propre connexion DB, lisait `User.objects.get(email=...)`
**avant le COMMIT** → l'utilisateur n'était pas encore visible → `DoesNotExist`.
`DoesNotExist` n'étant pas dans `autoretry_for`, la tâche échouait sans retry.

**Quand :** uniquement en contexte transactionnel. Hors admin, le projet est en
autocommit (`ATOMIC_REQUESTS=False`) : l'user est committé immédiatement, donc
les vues publiques (`connexion`, réservation/adhésion via formulaire public, API)
n'étaient **pas** touchées. Mais **l'admin Django enveloppe ses vues `changeform`
dans `transaction.atomic()`** : créer une adhésion (`admin_tenant.py` →
`MembershipForm.save`) ou une réservation (form admin) pour un **nouvel** email
crée l'user dans la transaction admin et dispatche le mail avant le COMMIT.

L'utilisateur **n'est jamais supprimé** : il existe bien après le COMMIT. Il
n'était simplement pas encore committé quand la tâche tournait.

**Correctif :** dispatch différé via `transaction.on_commit(...)`.
- Hors transaction → le callback s'exécute **immédiatement** (comportement public
  strictement inchangé).
- Dans une transaction → le callback s'exécute **après le COMMIT** (l'user est
  alors visible par le worker).
- Si la transaction admin rollback → le callback est abandonné → pas de mail
  orphelin (amélioration par rapport à l'ancien comportement).

### Modifications
| Fichier | Changement |
|---|---|
| `AuthBillet/utils.py` | Import `transaction` ; `connexion_celery_mailer.delay(...)` enveloppé dans `transaction.on_commit(...)` dans `sender_mail_connect()` |

## Tests à réaliser

### Test 1 : Création d'adhésion via l'admin (reproduction du bug)
1. Lancer un worker Celery réel (conteneur `lespass_celery`) et suivre ses logs :
   ```bash
   docker logs -f lespass_celery
   ```
2. Dans l'admin Django, créer une **adhésion** pour un email **qui n'a pas encore
   de compte** (ex : `nouvel-email-test@example.org`).
3. **Avant le fix** : le worker logge
   `ERROR ... connexion_celery_mailer ... DoesNotExist('TibilletUser ...')`.
4. **Après le fix (attendu)** : pas d'erreur `DoesNotExist`, le mail de connexion
   est dispatché normalement après le COMMIT
   (`INFO ... connexion_celery_mailer : nouvel-email-test@example.org`).
5. Idem en créant une **réservation** via l'admin pour un nouvel email.

### Test 2 : Non-régression du flow public (hors admin)
1. Page d'accueil → connexion par email (`/` → formulaire « se connecter »)
   avec un nouvel email.
2. Le mail de connexion doit partir **immédiatement** comme avant (vérifier le
   log `lespass_celery` : tâche reçue et `succeeded`).
3. Même vérification pour une **adhésion** et une **réservation** créées via le
   **formulaire public** (pas l'admin).

### Vérification en base (l'user existe bien après création admin)
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from AuthBillet.models import TibilletUser
print(TibilletUser.objects.filter(email='nouvel-email-test@example.org').exists())
"
```
Doit renvoyer `True` (l'user est committé).

## Compatibilité

- Sémantique `on_commit` garantie par Django 4.2 : exécution immédiate hors
  transaction → aucun changement pour les vues publiques.
- Aucun test existant n'asserte le dispatch de `connexion_celery_mailer` /
  `sender_mail_connect` → pas de test cassé.
- Le harness pytest du projet commit réellement (pas de rollback), donc
  `on_commit` fire normalement en test.
