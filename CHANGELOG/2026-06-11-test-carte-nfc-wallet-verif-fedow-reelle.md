# Test carte NFC → wallet (vérif Fedow réelle) + bugfix lien carte hors transaction / NFC card → wallet test (real Fedow check) + card-link transaction bugfix

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** nouveau test d'intégration `tests/pytest/test_membership_card_wallet_fedow.py` :
création d'adhésion via le formulaire admin avec un numéro de carte NFC, puis vérification
RÉELLE chez Fedow (wallet `has_user_card=True`, carte plus éphémère), nettoyage rejouable
(`lost_my_card`). Skip explicite si `FEDOW_TEST_CARD_NUMBER` absent de l'environnement.

**Bugfix découvert par le test :** `MembershipAddForm.save()` liait la carte chez Fedow
pendant `form.save()` — que l'admin Django appelle AVANT de valider les inlines. Si un
formset était invalide, la transaction DB était annulée mais l'appel HTTP déjà parti :
**carte liée chez Fedow sans adhésion côté Lespass**. Corrigé avec `transaction.on_commit`.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | **Bugfix** : `linkwallet_card_number` déplacé dans `transaction.on_commit` (cohérence Lespass ↔ Fedow) |
| `tests/pytest/test_membership_card_wallet_fedow.py` | **Nouveau** — test d'intégration carte → wallet avec vrais appels Fedow |

### Note dev
- Pour rendre le test actif en permanence : ajouter `FEDOW_TEST_CARD_NUMBER=58515F52` au `.env`
  (une carte Fedow sans utilisateur ; voir le docstring du test pour en trouver une autre).
  Sans la variable, le test skip proprement.
- Piège documenté : un user créé dans un test pytest (transaction rollbackée) mais enregistré
  chez Fedow pendant la validation du formulaire laisse un FedowUser orphelin dont les clés de
  signature sont perdues — ses endpoints signés (dont `lost_my_card`) deviennent inaccessibles.
  Les cartes de démo consommées pendant la mise au point ont été libérées (opération identique
  à la vue `lost_my_card_by_signature` de Fedow, validée par le mainteneur).
