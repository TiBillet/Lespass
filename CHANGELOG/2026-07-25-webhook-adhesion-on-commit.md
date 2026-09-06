# Webhook d'adhésion : envoi différé au COMMIT / Membership webhook: dispatch deferred to COMMIT

**Date :** 2026-07-25
**Migration :** Non

## Resume / Summary

**Quoi / What :** créer une adhésion depuis l'admin (`/admin/BaseBillet/membership/add/`)
faisait planter la tâche Celery `webhook_membership` en `Membership.DoesNotExist`
(Sentry `BILLETTERIE-COOP-DR`). Le webhook configuré n'était donc pas envoyé.
/ Creating a membership from the admin made the `webhook_membership` Celery task
crash with `Membership.DoesNotExist`, so the configured webhook was never sent.

**Pourquoi / Why :** le receveur `post_save` appelait `webhook_membership.delay()`
**pendant** la transaction. Le worker Celery a sa propre connexion à la base : il
lisait l'adhésion avant le `COMMIT` et ne la trouvait pas. Deux chemins mènent à
l'erreur, et le second est définitif :
/ The `post_save` receiver called `webhook_membership.delay()` **inside** the
transaction. The Celery worker has its own DB connection: it read the membership
before the `COMMIT` and could not find it.

- les vues `changeform` de l'admin Django sont `atomic` — course entre le worker et
  le `COMMIT` ;
- `MembershipAddForm.save()` est appelé **avant** la validation des inlines : si un
  formset est invalide, la transaction est annulée et l'adhésion n'existera **jamais**.
  Le message Celery déjà parti ne peut plus être rattrapé.

Le dispatch passe désormais par `transaction.on_commit()` : le webhook part après le
`COMMIT`, et il ne part pas du tout si la transaction est annulée. Hors transaction
(vues publiques en autocommit), `on_commit` exécute le callback immédiatement — le
comportement ne change pas. C'est le même correctif que celui déjà appliqué à
`AuthBillet/utils.py` (`sender_mail_connect`) et à la liaison de carte Fedow dans
`MembershipAddForm.save()`.
/ Dispatch now goes through `transaction.on_commit()`: the webhook is sent after the
`COMMIT`, and not at all if the transaction is rolled back. Outside a transaction the
callback runs immediately, so behaviour is unchanged.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/signals.py` | `create_lignearticle_if_membership_created_on_admin` : le dispatch `webhook_membership.delay()` passe par `transaction.on_commit()` ; import de `transaction` |
| `tests/pytest/test_webhook_membership_on_commit.py` | Nouveau — 2 tests : le dispatch est différé au `COMMIT` avec le bon `pk` ; aucun webhook si la transaction est annulée |

---

## Comment tester (a la main) / Manual test

### Test 1 — le webhook part bien après création depuis l'admin

1. Admin → **Webhooks** → créer un webhook `event = Confirmed subscription`, `active = ✔`,
   avec une URL d'écoute (par ex. un endpoint https://webhook.site).
2. Admin → **Adhésions** → *Ajouter* : renseigner un email, un tarif, une date de fin
   (`deadline`), puis **Enregistrer**.
3. Vérifier côté endpoint que le POST JSON de l'adhésion est bien arrivé.
4. Vérifier les logs Celery : `webhook_membership : <pk>` puis la réponse, **sans**
   `Membership.DoesNotExist`.

```bash
docker logs lespass_celery --tail 50 | grep webhook_membership
```

### Test 2 — formset invalide : aucun webhook parasite

1. Même formulaire d'ajout d'adhésion, mais rendre un **inline invalide** (valeur
   refusée dans un formset de la page) pour provoquer l'annulation de la transaction.
2. Le formulaire revient en erreur, aucune adhésion n'est créée.
3. Vérifier que **rien** n'est arrivé sur l'endpoint du webhook, et qu'aucune tâche
   `webhook_membership` n'apparaît dans les logs Celery.

### Verif automatisee / Automated check

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_webhook_membership_on_commit.py -v
```
