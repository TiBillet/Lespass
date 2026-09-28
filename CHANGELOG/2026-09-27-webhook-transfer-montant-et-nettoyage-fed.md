# Webhook transfer.created : montant vérifié chez Stripe / transfer.created webhook: amount checked against Stripe

**Date :** 2026-09-27
**Migration :** Non

## Resume / Summary

**Quoi / What :** le webhook Stripe `transfer.created` refuse désormais un payload dont
le montant contredit celui que Stripe confirme (même garde que pour le destinataire).
Le nettoyage de `tests/pytest/test_bank_transfer_service.py` supprime aussi les tokens
de son asset FED de test et ne cache plus ses échecs. /
The `transfer.created` webhook now refuses a payload whose amount contradicts Stripe.
The bank transfer test cleanup now deletes its FED asset tokens and no longer hides
failures.

**Pourquoi / Why :** le Fedow relit Stripe, mais l'ancien LaBoutik (`amount / 100`) et
`Paiement_stripe.total()` lisent le payload : un montant falsifié s'afficherait en caisse
et dans l'admin. Côté tests : un token de l'asset FED de test restait dans le wallet du
lieu (`Token.asset` en PROTECT), l'asset ne pouvait pas être supprimé, un
`except Exception: pass` avalait l'erreur, et l'asset FED résiduel faisait échouer trois
autres tests (contrainte `unique_fed_asset`). /
Legacy LaBoutik and `Paiement_stripe.total()` read the payload amount. A leftover test
FED asset broke three other tests.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | `transfer.created` : réponse 400 + journal si le montant (nouveau) ou le destinataire (existant, était une exception → 500) contredit Stripe ; variable `amount` inutilisée retirée |
| `tests/pytest/test_webhook_transfer_created.py` | tests A et C : attendent exactement 400 (au lieu de `>= 400`) |
| `tests/pytest/test_bank_transfer_service.py` | nettoyage : tokens, transactions et lignes supprimés par asset ET par wallet, plus de `try/except` silencieux |

### Tests et mutation
- `test_webhook_transfer_created.py::test_C_un_montant_falsifie_dans_le_payload_est_refuse`
  était rouge (201) ; vert après correctif.
- Mutation : garde remplacée par `if False:` → `test_C` tombe. Restaurée, sha256 vérifié.
- Mutations (relecture) : garde du montant remise en exception → `test_C` tombe ; garde du
  destinataire remise en exception → `test_A` tombe.

### Purge de la base de dev (accord du mainteneur, 2026-09-27)
Script protégé par `settings.DEBUG and settings.TEST`, une transaction, passage à blanc
d'abord. Supprimé : l'asset `[bt_test] FED`, ses 4 tokens, les 4 wallets
`[bt_test] Pot central`. Aucune ligne de vente ni transaction concernée.

---

## Comment tester (a la main) / Manual test

### Test 1 — webhook falsifié
1. Rejouer un événement `transfer.created` en modifiant `data.object.amount`.
2. Attendu : réponse d'erreur, aucun `Paiement_stripe` créé, rien envoyé au Fedow
   ni à LaBoutik.

### Test 2 — tests FED
```bash
make test ARGS="tests/pytest/test_bank_transfer_service.py"
docker exec -i lespass_django poetry run python /DjangoFiles/manage.py shell -c \
  "from fedow_core.models import Asset; print(list(Asset.objects.filter(category='FED')))"
# attendu : []
```
