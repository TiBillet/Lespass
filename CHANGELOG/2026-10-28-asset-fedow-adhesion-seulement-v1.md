# Asset Fedow : adhésions seulement, et seulement avec LaBoutik V1 / Fedow asset: memberships only, and only with LaBoutik V1

**Date :** 2026-10-28
**Migration :** Non

## Resume / Summary
**Quoi / What :** à l'enregistrement d'un produit, Lespass ne crée (ou n'archive) un asset Fedow que pour une ADHESION, et seulement si le lieu a une caisse LaBoutik V1 (`server_cashless` et `key_cashless` remplis). Les produits BADGE ne sont plus jamais envoyés. Le signal `send_membership_and_badge_product_to_fedow` devient `send_membership_product_to_fedow`.
/ On product save, Lespass creates (or archives) a Fedow asset only for a MEMBERSHIP, and only when the venue has a LaBoutik V1 POS. BADGE products are no longer sent. The signal is renamed `send_membership_product_to_fedow`.

**Pourquoi / Why :** l'asset d'adhésion ne sert qu'au comptoir V1 (vente au comptoir, puis webhook `Membership_fwh`). La récompense d'adhésion (`fedow_reward_enabled`) verse une autre monnaie et n'en a pas besoin. Le badge est du code mort : le bouton de la pointeuse est commenté dans les gabarits. Les envois inutiles produisaient des erreurs Fedow, par exemple « Asset already exists » à la duplication d'une adhésion (Sentry FEDOW-DJANGO-54, BILLETTERIE-COOP-VK/VJ) ou 404 à l'archivage (BILLETTERIE-COOP-VM/VN).
/ The membership asset is only used by the V1 counter; badges are dead code. Useless pushes caused Fedow errors.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/signals.py` | Signal renommé `send_membership_product_to_fedow` ; ADHESION seulement, et sortie immédiate sans V1. |
| `BaseBillet/models.py`, `BaseBillet/triggers.py` | Nom du signal mis à jour dans les commentaires. |
| `tests/pytest/test_signal_asset_fedow_adhesion_v1.py` | Nouveau : 4 tests unitaires (adhésion avec/sans V1, archivage sans V1, badge avec V1). |
| `tests/pytest/test_signaux_proxys_product.py`, `tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py` | Nom du signal mis à jour. |
| `tests/e2e/test_federation_asset_legacy_inter_lieux.py` | Retrait de la précondition « le produit adhésion existe sur le Fedow » : la récompense n'en dépend pas. |
| `tests/PIEGES.md` | Piège 13.2 mis à jour. |

### Limite connue / Known limit
Un lieu qui branche une caisse V1 **après** avoir créé ses adhésions n'a pas leurs assets dans Fedow. Il suffit de réenregistrer chaque adhésion dans l'admin pour les envoyer.
/ A venue pairing a V1 POS after creating its memberships must re-save them in the admin.

---

## Comment tester (a la main) / Manual test
### Test 1 — lieu sans V1
1. Sur `lespass` (pas de `server_cashless`), créer ou dupliquer une adhésion dans l'admin.
2. Attendu : aucune ligne « send_membership_product_to_fedow ERREUR Fedow » dans les logs, aucun appel `asset/create_membership_asset` côté Fedow.

### Test 2 — lieu avec V1
1. Sur un lieu legacy avec `server_cashless` et `key_cashless`, créer une adhésion.
2. Attendu : log « send_membership_product_to_fedow : created : True », l'asset existe sur Fedow avec l'UUID du produit.

### Test 3 — badge
1. Sur n'importe quel lieu, créer un produit BADGE.
2. Attendu : aucun appel à Fedow.

### Verifs
- `docker exec lespass_django poetry run pytest tests/pytest/test_signal_asset_fedow_adhesion_v1.py tests/pytest/test_signaux_proxys_product.py -v`
