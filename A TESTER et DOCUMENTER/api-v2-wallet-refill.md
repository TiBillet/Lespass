# API v2 — Recharge de tokens « cadeau » (`POST /api/v2/wallet-refills/`)

## Ce qui a été fait

Route API v2 qui crédite des tokens **non adossés à l'euro** sur la tirelire d'un
user, sans paiement. Réplique en API le trigger `Price.fedow_reward_*` (qui
crédite des tokens à l'achat d'une adhésion). Délègue le crédit à
`FedowAPI.transaction.refill_from_lespass_to_user_wallet`.

Catégories rechargeables (`AssetFedowPublic.REFILLABLE_CATEGORIES`) : `TNF`
(cadeau), `TIM` (monnaie temps), `FID` (fidélité), `BDG` (badgeuse). Exclues :
fiduciaires (`TLF`, `FED`) et adhésion (`SUB`).

La clé API porte une FK `gift_asset` (admin `ExternalApiKey`) limitée à ces
catégories. Sa présence **active** le droit `walletrefill` **et restreint** la
clé à ce seul asset.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | Champ `gift_asset` + `api_permissions()["walletrefill"]` |
| `BaseBillet/migrations/0211_externalapikey_gift_asset.py` | Migration |
| `api_v2/serializers.py` | `WalletRefillCreateSerializer` |
| `api_v2/views.py` | `WalletRefillViewSet` + `GIFT_REFILL_MAX_AMOUNT=10000` |
| `api_v2/urls.py` | Route `wallet-refills` |
| `Administration/admin_tenant.py` | `gift_asset` dans les `fields` |

## Tests automatiques

```bash
docker exec -e API_KEY=dummy lespass_django poetry run pytest tests/pytest/test_api_v2_wallet_refill.py -v
```
> `-e API_KEY=dummy` : court-circuite la fixture `_inject_cli_env` qui sinon
> tente un `docker exec` (impossible depuis l'intérieur du conteneur). Les tests
> créent leurs propres clés API, la valeur de `API_KEY` n'est pas utilisée.

10 tests : autorisation (sans clé, clé sans `gift_asset`, asset non autorisé,
asset non TNF, plafond, payload invalide), 503 Fedow indispo, 201 nominal,
création user, idempotence. FedowAPI est mockée.

## Tests manuels

### Préparation
1. Admin → **Api keys** → créer une clé.
2. Renseigner **Wallet refill (asset)** : choisir un asset rechargeable
   (Cadeau, Monnaie temps, Points de fidélité ou Badgeuse). Sauvegarder →
   **copier la clé affichée** (une seule fois).
3. Noter l'`uuid` de l'asset (admin Fedow ou shell).

### Scénario nominal (201)
```bash
curl -k -X POST https://lespass.tibillet.localhost/api/v2/wallet-refills/ \
  -H "Authorization: Api-Key <CLE>" \
  -H "Idempotency-Key: test-001" \
  -H "Content-Type: application/json" \
  -d '{"email":"membre@example.org","asset":"<UUID_ASSET_TNF>","amount":500}'
```
Attendu : `201` + objet `MoneyTransfer`. Vérifier dans « Ma tirelire » que le
membre a bien reçu les tokens.

### Idempotence (208)
Rejouer exactement la même requête (même `Idempotency-Key`) → `208 Already
Reported`, **même** `identifier`, **pas** de second crédit.

### Cas d'erreur
- Sans header `Authorization` → 403.
- Clé sans `gift_asset` → 403.
- `asset` = un autre asset rechargeable que celui de la clé → 403.
- `asset` = un asset fiduciaire (TLF/FED) ou adhésion (SUB) → 422.
- `amount` = 10001 → 422 (plafond).
- `amount` absent / négatif → 400.
- Fedow non configuré sur le tenant → 503.

## Vérification en base
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
t=Client.objects.get(schema_name='lespass')
with tenant_context(t):
    from BaseBillet.models import ExternalApiKey
    for k in ExternalApiKey.objects.exclude(gift_asset=None):
        print(k.name, '->', k.gift_asset.name, k.gift_asset.category)
"
```

## Compatibilité
Additif : champ FK nullable, nouvelle route, nouvel import. La route v1
`/api/wallet/get_stripe_checkout_with_email/` (recharge payante Stripe) est
inchangée. Aucune régression sur les vues BaseBillet qui utilisent fedow_connect.
