# Plan d'implémentation — Route API v2 « recharge cadeau »

> **Spec :** [SPEC.md](SPEC.md). Implémentation **inline** dans cette session.
> **Contraintes projet :** aucune opération git de l'assistant (le mainteneur
> committe) · pas de `makemessages`/`compilemessages` auto · règle des 3 fichiers
> avant `manage.py check` + tests · serveur tenu par le mainteneur dans byobu.

**Goal :** crédit de tokens cadeau (TNF) sur la tirelire d'un user via
`POST /api/v2/wallet-refills/`, authentifié par clé API restreinte à un asset.

**Architecture :** ViewSet api_v2 + `SemanticApiKeyPermission`. La clé porte une
FK `gift_asset` (TNF) qui sert d'interrupteur (`api_permissions["walletrefill"]`)
et de restriction. Crédit délégué à `FedowAPI.transaction.refill_from_lespass_to_user_wallet`.

**Tech stack :** Django, DRF (`viewsets.ViewSet`, `serializers.Serializer`),
django-tenants, cache Redis, `djangorestframework-api-key`, Fedow (HTTP).

---

## Task 1 — Modèle `ExternalApiKey` + migration

**Files :** Modify `BaseBillet/models.py` (classe `ExternalApiKey` ~3321-3375).

- [ ] **1.1** Ajouter le champ FK après `crowd` :
```python
    gift_asset = models.ForeignKey(
        "fedow_public.AssetFedowPublic",
        on_delete=models.SET_NULL, blank=True, null=True,
        limit_choices_to={"category": "TNF"},
        related_name="api_keys_gift_refill",
        verbose_name=_("Gift token refill (asset)"),
        help_text=_("If set, this key can top-up this gift asset via /api/v2/wallet-refills/."),
    )
```
- [ ] **1.2** Ajouter la clé dans `api_permissions()` (le `bool(...)` = interrupteur) :
```python
            # Recharge cadeau : autorisée seulement si un asset cadeau est défini
            # / Gift refill: allowed only if a gift asset is set
            "walletrefill": bool(self.gift_asset_id),
```
- [ ] **1.3** Générer la migration :
`docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet`
- [ ] **1.4** Appliquer :
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
- [ ] **1.5** `manage.py check` → 0 issue.

---

## Task 2 — Serializer d'entrée

**Files :** Modify `api_v2/serializers.py` (fin de fichier).

- [ ] **2.1** Ajouter :
```python
class WalletRefillCreateSerializer(serializers.Serializer):
    """
    Entree pour recharger des tokens cadeau (TNF) sur la tirelire d'un user.
    / Input serializer for gift token wallet refill (API v2).
    """
    email = serializers.EmailField(required=True)
    asset = serializers.UUIDField(required=True)
    amount = serializers.IntegerField(required=True, min_value=1)
```

---

## Task 3 — ViewSet + URL

**Files :** Modify `api_v2/views.py`, `api_v2/urls.py`.

- [ ] **3.1** Dans `api_v2/views.py`, ajouter l'import du serializer dans le bloc
`from .serializers import (...)` : `WalletRefillCreateSerializer`.
- [ ] **3.2** Ajouter la constante + le ViewSet (après `MembershipViewSet`) :
```python
# Plafond par recharge cadeau, en unite brute (cf SPEC API_GIFT_REFILL)
# / Per-call gift refill cap, raw unit
GIFT_REFILL_MAX_AMOUNT = 10000


class WalletRefillViewSet(viewsets.ViewSet):
    """
    Recharge de tokens cadeau (TNF) sur la tirelire d'un user.
    / Gift token (TNF) wallet refill.

    Header: Authorization: Api-Key <key> (cle restreinte a un asset cadeau)
    Header optionnel: Idempotency-Key (anti double-credit, best-effort cache)
    """
    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def create(self, request):
        from ApiBillet.permissions import get_apikey_valid
        from fedow_public.models import AssetFedowPublic
        from fedow_connect.models import FedowConfig
        from fedow_connect.fedow_api import FedowAPI
        from AuthBillet.utils import get_or_create_user

        # 1. Recupere l'objet cle API pour connaitre l'asset autorise
        # / Get the API key object to know the allowed asset
        api_key = get_apikey_valid(self)
        if not api_key or not api_key.gift_asset_id:
            return Response({"detail": _("API key not allowed for gift refill.")},
                            status=status.HTTP_403_FORBIDDEN)

        # 2. Validation du payload / Validate payload
        input_serializer = WalletRefillCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        email = input_serializer.validated_data["email"]
        asset_uuid = input_serializer.validated_data["asset"]
        amount = input_serializer.validated_data["amount"]

        # 3. Resolution de l'asset / Resolve asset
        asset = get_object_or_404(AssetFedowPublic, uuid=asset_uuid)

        # 4. Categorie cadeau obligatoire / Gift category required
        if asset.category != AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT:
            return Response({"detail": _("Asset is not a gift token.")},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 5. L'asset doit etre celui autorise sur la cle / Must match key asset
        if asset.uuid != api_key.gift_asset_id:
            return Response({"detail": _("Asset not allowed for this API key.")},
                            status=status.HTTP_403_FORBIDDEN)

        # 6. Plafond / Cap
        if amount > GIFT_REFILL_MAX_AMOUNT:
            return Response({"detail": _("Amount above the maximum allowed.")},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 7. Idempotence (cache best-effort, cle par tenant)
        # / Idempotency (best-effort cache, per-tenant key)
        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        cache_key = None
        if idempotency_key:
            cache_key = f"api:gift_refill:idem:{connection.tenant.pk}:{idempotency_key}"
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached, status=status.HTTP_200_OK)

        # 8. User / User
        user = get_or_create_user(email)
        if not user:
            return Response({"detail": _("Invalid email.")},
                            status=status.HTTP_406_NOT_ACCEPTABLE)

        # 9. Fedow dispo ? / Fedow available?
        if not FedowConfig.get_solo().can_fedow():
            return Response({"detail": _("Fedow service unavailable.")},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # 10. Credit / Refill
        fedowAPI = FedowAPI()
        metadata = {
            "reason": f"API gift refill: {amount} {asset.name}",
            "api_key": api_key.name,
        }
        if idempotency_key:
            metadata["idempotency_key"] = idempotency_key
        reward_tx = fedowAPI.transaction.refill_from_lespass_to_user_wallet(
            user=user, amount=amount, asset=asset, metadata=metadata,
        )

        # 11. Reponse schema.org MoneyTransfer
        payload = {
            "@context": "https://schema.org",
            "@type": "MoneyTransfer",
            "identifier": str(reward_tx.get("uuid")),
            "amount": amount,
            "asset": str(asset.uuid),
            "recipient": {"@type": "Person", "email": email},
        }
        if cache_key:
            cache.set(cache_key, payload, timeout=60 * 60 * 48)  # 48h
        return Response(payload, status=status.HTTP_201_CREATED)
```
- [ ] **3.3** Dans `api_v2/urls.py`, importer `WalletRefillViewSet` et enregistrer :
```python
router.register(r"wallet-refills", WalletRefillViewSet, basename="walletrefill")
```
- [ ] **3.4** `manage.py check` → 0 issue.

---

## Task 4 — Admin `ExternalApiKey`

**Files :** Modify `Administration/admin_tenant.py` (`ExternalApiKeyAdmin` ~129-156).

- [ ] **4.1** Ajouter `'gift_asset'` dans `fields` (avant `'user'`) :
```python
        ('wallet', 'sale'),
        'gift_asset',
        'user',
```
- [ ] **4.2** (`limit_choices_to` filtre déjà le widget sur les assets TNF — rien d'autre.)
- [ ] **4.3** `manage.py check` → 0 issue.

---

## Task 5 — Tests pytest (FedowAPI mockée)

**Files :** Create `tests/pytest/test_api_v2_wallet_refill.py`.

Squelette (les fixtures exactes seront calées sur `tests/pytest/conftest.py` au
moment du code : tenant `lespass`, `tenant_context`, `APIClient`, création
`ExternalApiKey` via `APIKey.objects.create_key`, `AssetFedowPublic` TNF) :

- [ ] **5.1** Helpers : créer une clé API avec `gift_asset` (asset TNF), retourner
le header `Authorization: Api-Key <key>`.
- [ ] **5.2** Tests (mock `fedow_connect.fedow_api.FedowAPI` et
`FedowConfig.can_fedow`) :
  - `test_refill_sans_cle_401_403`
  - `test_refill_cle_sans_gift_asset_403`
  - `test_refill_asset_non_autorise_403`
  - `test_refill_asset_non_tnf_422`
  - `test_refill_au_dessus_plafond_422`
  - `test_refill_payload_invalide_400`
  - `test_refill_fedow_indisponible_503`
  - `test_refill_nominal_201_appelle_fedow`
  - `test_refill_cree_user_si_inconnu`
  - `test_refill_idempotent_ne_recredite_pas`
- [ ] **5.3** Lancer :
`docker exec lespass_django poetry run pytest tests/pytest/test_api_v2_wallet_refill.py -v`

---

## Task 6 — Documentation + API files

**Files :** Modify `api_v2/openapi-schema.yaml`, `api_v2/README.md`,
`api_v2/GUIDELINES.md`, `CHANGELOG.md` ; Create
`A TESTER et DOCUMENTER/api-v2-wallet-refill.md`.

- [ ] **6.1** `openapi-schema.yaml` : path `POST /api/v2/wallet-refills/`
(requestBody email/asset/amount + header Idempotency-Key + réponses 201/403/422/503).
- [ ] **6.2** `README.md` + `GUIDELINES.md` : décrire la route, le droit
`walletrefill` (activé par `gift_asset`), la catégorie TNF, le plafond, l'idempotence.
- [ ] **6.3** `CHANGELOG.md` : entrée bilingue (Quoi/What, Pourquoi/Why, fichiers, migration Oui).
- [ ] **6.4** `A TESTER et DOCUMENTER/api-v2-wallet-refill.md` : scénarios manuels + curl.
- [ ] **6.5** i18n : signaler au mainteneur de lancer makemessages/compilemessages
(nouvelles chaînes `_()`). **Ne pas le faire soi-même.**

---

## Ordre & checkpoints
1. Task 1 (modèle+migration) → check.
2. Tasks 2+3 (serializer+vue+url) → check.
3. Task 4 (admin) → check.
4. Task 5 (tests) → pytest vert.
5. Task 6 (doc).
Le mainteneur committe et lance i18n.
