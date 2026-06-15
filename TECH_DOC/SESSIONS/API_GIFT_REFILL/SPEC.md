# SPEC — Route API v2 « recharge cadeau » (gift token refill)

**Date :** 2026-05-21
**App principale :** `api_v2` (+ champ sur `BaseBillet.ExternalApiKey`)
**Statut :** implémenté.

> **Mise à jour 2026-05-21 :** le périmètre des catégories rechargeables a été
> élargi au-delà du seul `TNF`. Catégories autorisées désormais centralisées dans
> `AssetFedowPublic.REFILLABLE_CATEGORIES` = `TNF` (cadeau), `TIM` (monnaie temps),
> `FID` (fidélité), `BDG` (badgeuse). Restent exclues : fiduciaires (`TLF`, `FED`)
> et adhésion (`SUB`). Les passages ci-dessous mentionnant « TNF uniquement »
> sont remplacés par « catégorie ∈ REFILLABLE_CATEGORIES ».

---

## 1. Objectif

Exposer une route API permettant à un service externe de **créditer des tokens
« cadeau »** sur la tirelire (wallet Fedow) d'un·e utilisateur·ice, à partir de
son email — sans paiement.

Réplique, via une route HTTP authentifiée par clé API, ce que fait déjà le
trigger sur les tarifs d'adhésion (`Price.fedow_reward_*` →
`refill_from_lespass_to_user_wallet_from_price_solded`).

**Périmètre volontairement restreint** : uniquement les assets de catégorie
**`TNF` (`TOKEN_LOCAL_NOT_FIAT`, libellé « Cadeau »)**, et uniquement l'asset
explicitement autorisé sur la clé API.

---

## 2. Mécanisme existant réutilisé

| Élément | Emplacement |
|---|---|
| Crédit lieu → wallet user | `fedow_connect/fedow_api.py:1020` `TransactionFedow.refill_from_lespass_to_user_wallet(user, amount:int, asset, metadata)` |
| Trigger adhésion (référence) | `BaseBillet/tasks.py:1808` `refill_from_lespass_to_user_wallet_from_price_solded` |
| Catégorie « Cadeau » | `fedow_public/models.py:35` → `AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT = 'TNF'` |
| email → user | `AuthBillet/utils.py:44` `get_or_create_user(email)` (crée inactif + attache au tenant) |
| Garde Fedow actif | `FedowConfig.get_solo().can_fedow()` |
| Permission clé API v2 | `api_v2/permissions.py` `SemanticApiKeyPermission` (vérifie `api_permissions()[view.basename]`) |

`amount` est passé tel quel à Fedow en **unité brute (int)** — le trigger
historique fait `int(dround(decimal) * 100)`, mais ici le client envoie déjà
l'entier attendu.

---

## 3. Décisions de design (brainstorming)

1. **API** : `api_v2` (sémantique schema.org), nouveau ViewSet.
2. **Permission** : clé API seule (`SemanticApiKeyPermission`). Pas d'admin
   tenant requis — l'usage est machine-to-machine. La restriction asset est le
   garde-fou.
3. **Restriction asset** : **FK unique** `gift_asset` sur `ExternalApiKey`
   (`limit_choices_to={'category':'TNF'}`). La présence de la FK sert à la fois
   d'**interrupteur** (droit `walletrefill`) et de **restriction**.
4. **Unité du montant** : **unité brute (int)**, transmise telle quelle à Fedow.
5. **Plafond** : constante hardcodée `GIFT_REFILL_MAX_AMOUNT = 10000` (unité
   brute). `amount > 10000` → refus.
6. **Idempotence** : header `Idempotency-Key`. Mécanisme **cache Redis**
   (`django.core.cache`), best-effort, clé par tenant. Pas de table → pas de
   migration. Limite assumée : protection expire avec le TTL.

---

## 4. Contrat d'API

### Requête
```
POST /api/v2/wallet-refills/
Authorization: Api-Key <clé>
Idempotency-Key: <chaîne libre>   (optionnel mais recommandé)
Content-Type: application/json

{
  "email": "alice@example.org",
  "asset": "<uuid-asset-TNF>",
  "amount": 500
}
```

### Validation (ordre)
| # | Condition | Code | Message |
|---|---|---|---|
| 1 | clé valide + `gift_asset` défini (basename `walletrefill`) | 401/403 | permission |
| 2 | champs valides (`email`, `asset` uuid, `amount` int ≥ 1) | 400 | serializer |
| 3 | asset uuid introuvable | 404 | asset not found |
| 4 | `asset.category != 'TNF'` | 422 | asset n'est pas un token cadeau |
| 5 | `asset != clé.gift_asset` | 403 | asset non autorisé pour cette clé |
| 6 | `amount > GIFT_REFILL_MAX_AMOUNT (10000)` | 422 | montant au-dessus du plafond |
| 7 | `Idempotency-Key` déjà vu (cache) | 208 | renvoie la transaction stockée |
| 8 | `can_fedow()` faux | 503 | Fedow indisponible |

### Réponse 201 (schema.org `MoneyTransfer`)
```json
{
  "@context": "https://schema.org",
  "@type": "MoneyTransfer",
  "identifier": "<tx-uuid>",
  "amount": 500,
  "asset": "<uuid-asset>",
  "recipient": { "@type": "Person", "email": "alice@example.org" }
}
```

### Idempotence (détail)
- Clé de cache : `f"api:gift_refill:idem:{connection.tenant.pk}:{idempotency_key}"`.
- Au succès : stocker la réponse sérialisée (TTL ~48 h).
- Appel suivant avec la même `Idempotency-Key` (et même tenant) → renvoyer la
  valeur cachée, **sans** rappeler Fedow. Status `208 Already Reported` (et non 201).
- Sans header `Idempotency-Key` : pas de déduplication (chaque appel crédite).

---

## 5. Modèle de données

### `BaseBillet.ExternalApiKey` (+1 champ, +1 ligne)
```python
gift_asset = models.ForeignKey(
    "fedow_public.AssetFedowPublic",
    on_delete=models.SET_NULL, blank=True, null=True,
    limit_choices_to={"category": "TNF"},
    verbose_name=_("Gift token refill (asset)"),
    help_text=_("If set, this key can top-up this gift asset via /api/v2/wallet-refills/."),
)
```
```python
def api_permissions(self):
    return {
        ...
        "walletrefill": bool(self.gift_asset_id),
    }
```
Constante module (BaseBillet/models.py ou api_v2/views.py) :
```python
GIFT_REFILL_MAX_AMOUNT = 10000  # unité brute (cts) — plafond par recharge
```

> La FK tenant→`fedow_public.AssetFedowPublic` est déjà éprouvée :
> `Price.fedow_reward_asset` pointe exactement vers ce modèle.

### Migration
1 migration BaseBillet (ajout FK nullable). À appliquer via
`migrate_schemas --executor=multiprocessing`.

---

## 6. Fichiers à toucher

| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | `gift_asset` FK + `GIFT_REFILL_MAX_AMOUNT` + ligne `api_permissions()` |
| `BaseBillet/migrations/0XXX_externalapikey_gift_asset.py` | migration |
| `api_v2/serializers.py` | `WalletRefillCreateSerializer` (in) + sérialisation `MoneyTransfer` (out) |
| `api_v2/views.py` | `WalletRefillViewSet.create()` |
| `api_v2/urls.py` | `router.register(r"wallet-refills", WalletRefillViewSet, basename="walletrefill")` |
| `Administration/admin_tenant.py` | exposer `gift_asset` dans `fields` de `ExternalApiKeyAdmin` |
| `api_v2/openapi-schema.yaml` | doc de l'endpoint |
| `api_v2/README.md` + `api_v2/GUIDELINES.md` | mention de la route + droit |
| `tests/pytest/test_api_v2_wallet_refill.py` | tests (mock FedowAPI) |
| `CHANGELOG.md` | entrée bilingue |
| `A TESTER et DOCUMENTER/api-v2-wallet-refill.md` | checklist mainteneur |
| i18n FR/EN | nouvelles chaînes `_()` (makemessages **par le mainteneur**) |

---

## 7. Tests (pytest DB-only, FedowAPI mockée)

1. 401 sans header / clé invalide.
2. 403 clé sans `gift_asset`.
3. 403 asset demandé ≠ `gift_asset` de la clé.
4. 422 asset de catégorie ≠ TNF.
5. 422 `amount` > 10000.
6. 400 payload invalide (`amount` absent / négatif / email invalide).
7. 503 quand `can_fedow()` renvoie False (mock).
8. 201 nominal → `refill_from_lespass_to_user_wallet` appelé avec
   `(user, amount, asset, metadata)` corrects (mock), réponse MoneyTransfer.
9. Création de l'user si email inconnu (`get_or_create_user`).
10. Idempotence : 2ᵉ appel même `Idempotency-Key` → pas de 2ᵉ appel Fedow,
    réponse identique.

> Multi-tenant : utiliser `tenant_context(tenant)` + `APIClient` (Fedow et
> `AssetFedowPublic` sont en SHARED_APPS / public). Mocker `FedowAPI` pour ne
> pas dépendre du serveur Fedow.

---

## 8. Hors périmètre (YAGNI / plus tard)

- Recharge d'assets non-cadeau (TLF, TIM, FID…) — explicitement exclue.
- Plafond configurable par clé (ici hardcodé 10000).
- Idempotence durable (table dédiée) — cache best-effort suffit « pour l'instant ».
- Lecture de solde / liste de transactions via cette route.

---

## 9. Cohérence avec l'existant

La route wallet **v1** `/api/wallet/get_stripe_checkout_with_email/` reste
inchangée : elle crée un lien de recharge **payante** (Stripe). La nouvelle
route v2 est une recharge **cadeau gratuite** (tokens TNF offerts par le lieu).
Usages disjoints, pas de doublon ni de régression.
