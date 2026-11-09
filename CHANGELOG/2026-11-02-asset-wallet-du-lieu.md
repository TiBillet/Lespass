# Un asset créé dans l'admin appartient au wallet du lieu / An admin-created asset belongs to the venue wallet

**Date :** 2026-11-02
**Migration :** Non

## Resume / Summary
**Quoi / What :** `AssetAdmin.save_model` pose désormais `wallet_origin` sur le wallet du lieu (`Lieu <schema>`), via `WalletService.get_or_create_wallet_tenant`. / `AssetAdmin.save_model` now sets `wallet_origin` to the venue wallet.

**Pourquoi / Why :** l'ancien code prenait le premier wallet du lieu par ordre d'UUID, qui pouvait être celui d'un client. Les ventes cashless de l'asset arrivaient alors sur la carte de ce client. / The previous code took the venue's first wallet by UUID order, which could be a customer's. Cashless sales then landed on that customer's card.

Le correctif protège uniquement les nouveaux assets. Les assets déjà en base gardent leur `wallet_origin`. La Cabine demande une reprise séparée de ses 4 assets et du solde concerné. / This fix only protects new assets. La Cabine needs a separate repair.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_core/admin.py` | `save_model` utilise le wallet du lieu ; import `Wallet` retiré, import `WalletService` ajouté |
| `tests/pytest/test_asset_wallet_du_lieu.py` | Nouveau test : un wallet client en tête du tri n'est pas retenu |

---

## Comment tester (a la main) / Manual test
### Test 1 — scénario nominal
1. Sur un lieu V2 de dev, ouvrir l'admin, section Fedow, puis Assets.
2. Créer un asset de catégorie « Token local fiduciaire ».
3. Vérifier en base que l'asset pointe vers le wallet du lieu :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from fedow_core.models import Asset
asset = Asset.objects.order_by('-created_at').first()
print(asset.name, asset.wallet_origin.name)
"
```

Résultat attendu : `Lieu <schema>`.

### Verifs DB / Playwright
- Test automatique : `docker exec lespass_django poetry run pytest tests/pytest/test_asset_wallet_du_lieu.py -q`
