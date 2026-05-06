# Plan d'implémentation — Session 31 Phase B

**Goal :** Gateway Stripe dédiée recharge FED + dispatch webhook + verrous admin. Phase A a posé les fondations (RefillService, bootstrap, serializer). Phase B connecte Stripe à ces fondations.

**Checkpoint sécurité obligatoire** : zone sensible (webhook Stripe). Anti-tampering + idempotence + zéro régression sur les autres sources `Paiement_stripe`.

**Architecture :** une classe dédiée `CreationPaiementStripeFederation` (compte central, pas de Connect, pas de SEPA), un handler webhook `_process_stripe_webhook_cashless_refill` placé avant le dispatch legacy dans `ApiBillet/views.py:1042`, appel final `RefillService.process_cashless_refill` (déjà testé Phase A). Admin verrouillé pour empêcher création manuelle de Product sur l'asset FED.

**Tech Stack :** Stripe Python SDK, DRF, pytest avec mock `stripe.checkout.Session.create` (pattern existant dans `tests/pytest/conftest.py`).

**Références :**
- Spec : `TECH DOC/Laboutik sessions/Session 31 - Recharge FED V2/SPEC_RECHARGE_FED_V2.md`
- Phase A : `PLAN_PHASE_A.md` (terminée)
- Service à appeler : `fedow_core.services.RefillService.process_cashless_refill`

**Contraintes projet** (inchangées vs Phase A) :
- Aucune opération git par les implementers
- FALC, commentaires FR/EN, noms verbeux
- Tests dans `tests/pytest/`, pattern `sys.path.insert` + `django.setup()`
- Leçon Phase A : pour les tâches multi-tenant complexes → exécuter en direct plutôt que dispatcher sonnet

---

## Cartographie des fichiers

**Créés :**
- `PaiementStripe/refill_federation.py` — classe `CreationPaiementStripeFederation`
- `tests/pytest/test_refill_federation_gateway.py` — tests gateway (sans Connect, sans SEPA)
- `tests/pytest/test_refill_webhook.py` — tests webhook (dispatch + anti-tampering + idempotence)

**Modifiés :**
- `ApiBillet/views.py` — ajout fonction `_process_stripe_webhook_cashless_refill` + dispatch dans `Webhook_stripe.post`
- `fedow_core/admin.py` — verrous lecture seule sur Asset FED
- `Administration/admin_tenant.py` — `ProductForm.asset.queryset.exclude(category=FED)`

---

## Task B1 — `CreationPaiementStripeFederation`

**Files :**
- Create: `PaiementStripe/refill_federation.py`
- Create: `tests/pytest/test_refill_federation_gateway.py`

### Steps

- [ ] **B1.1 Écrire les tests (TDD)** — 2 tests critiques :
  - `test_gateway_no_stripe_connect` : le `data_checkout` produit NE contient PAS `stripe_account`
  - `test_gateway_no_sepa` : `payment_method_types == ['card']` uniquement
  - `test_gateway_cree_paiement_stripe_avec_source_cashless_refill` : `Paiement_stripe.source == CASHLESS_REFILL`
  - `test_gateway_injecte_metadata_refill_type_fed` : metadata contient `refill_type='FED'` + `tenant` + `paiement_stripe_uuid`

- [ ] **B1.2 Mocker `stripe.checkout.Session.create`** (pas d'appel HTTP réel) via pytest-mock ou `unittest.mock.patch`

- [ ] **B1.3 Implémenter la classe** (inspirée de `CreationPaiementStripe`) :

```python
class CreationPaiementStripeFederation:
    """
    Gateway Stripe dediee aux recharges FED V2.
    - Pas de Stripe Connect (compte central root)
    - Pas de SEPA (UX recharge immediate uniquement)
    - Cree le Paiement_stripe(source=CASHLESS_REFILL) en base
    - Injecte la metadata PSP-agnostique (refill_type='FED')
    """
    def __init__(self, user, liste_ligne_article, wallet_receiver,
                 asset_fed, tenant_federation, absolute_domain, success_url):
        # Cree Paiement_stripe en base (source=CASHLESS_REFILL)
        # Construit data_checkout SANS stripe_account (compte central root)
        # payment_method_types=['card'] (pas de SEPA)
        # metadata = {tenant, paiement_stripe_uuid, refill_type='FED',
        #             wallet_receiver_uuid, asset_uuid}
        # Appelle stripe.checkout.Session.create(**data_checkout)
        # Persiste checkout_session_id_stripe + checkout_session_url sur le Paiement_stripe
```

- [ ] **B1.4 Lancer tests → PASS**
- [ ] **B1.5 Verify check + makemigrations OK**

---

## Task B2 — Fonction `_process_stripe_webhook_cashless_refill`

**Files :**
- Modify: `ApiBillet/views.py` (ajouter la fonction au niveau module, proche de `Webhook_stripe`)
- Create: `tests/pytest/test_refill_webhook.py`

### Steps

- [ ] **B2.1 Écrire les tests** — 4 tests critiques :
  - `test_webhook_dispatch_cashless_refill` : payload avec `refill_type=FED` → RefillService appelé, Paiement.status=PAID
  - `test_webhook_anti_tampering` : `stripe.amount_total != int(paiement.total() * 100)` → 400
  - `test_webhook_idempotent` : même event 2 fois → 1 seule Transaction REFILL
  - `test_webhook_reject_si_source_incorrecte` : metadata `refill_type=FED` mais `Paiement.source != CASHLESS_REFILL` → 400

- [ ] **B2.2 Implémenter la fonction** :

```python
def _process_stripe_webhook_cashless_refill(payload, request):
    """
    Traite un webhook Stripe de recharge FED V2.
    - Anti-tampering : compare stripe.amount_total et int(paiement.total() * 100)
    - Appelle RefillService.process_cashless_refill (idempotent)
    - Marque Paiement_stripe.status = PAID
    """
    # metadata['tenant'] → charger Client
    # tenant_context(tenant) → charger Paiement_stripe
    # check paiement.source == CASHLESS_REFILL, sinon 400
    # anti-tampering
    # RefillService.process_cashless_refill(...)
    # paiement.status = PAID; save
    # return 200
```

- [ ] **B2.3 Lancer tests → PASS**

---

## Task B3 — Dispatch dans `Webhook_stripe.post`

**Files :**
- Modify: `ApiBillet/views.py:1042` (ajouter branche `if metadata.get('refill_type') == 'FED'` avant le check legacy)

### Steps

- [ ] **B3.1 Lire le contexte actuel** (`ApiBillet/views.py:1030-1070`)
- [ ] **B3.2 Ajouter le dispatch avant le check legacy** :

```python
if payload.get('type') in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
    metadata = payload["data"]["object"].get("metadata") or {}

    # === DISPATCH V2 (NOUVEAU, avant tout le reste) ===
    if metadata.get('refill_type') == 'FED':
        return _process_stripe_webhook_cashless_refill(payload, request)

    # === LEGACY (inchangé) ===
    if "return_refill_wallet" in payload["data"]["object"]["success_url"]:
        return Response(...)
    # ... reste inchangé
```

- [ ] **B3.3 Vérifier non-régression sur les autres sources** — lancer `tests/pytest/test_stripe_*.py` complet :

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_membership_create.py tests/pytest/test_stripe_reservation.py tests/pytest/test_stripe_crowds.py -v
```
Expected : aucune régression.

---

## Task B4 — Verrous admin

**Files :**
- Modify: `fedow_core/admin.py` — `AssetAdmin` : override `has_change_permission`, `has_delete_permission` si `obj.category == Asset.FED`
- Modify: `Administration/admin_tenant.py` — `ProductForm.asset.queryset.exclude(category=Asset.FED)` (trouver le ModelForm `Product`)

### Steps

- [ ] **B4.1 `fedow_core/admin.py` verrous**

```python
class AssetAdmin(ModelAdmin):
    # ... existant ...

    def has_change_permission(self, request, obj=None):
        # Asset FED unique : lecture seule (cree par bootstrap_fed_asset).
        if obj is not None and obj.category == Asset.FED:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.category == Asset.FED:
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.category == Asset.FED:
            # Affichage seul : tous les champs en lecture seule
            return [f.name for f in self.model._meta.fields]
        return super().get_readonly_fields(request, obj)
```

- [ ] **B4.2 `Administration/admin_tenant.py`** : restreindre le queryset du champ `asset` sur le `ProductForm`/`ProductAdmin`. Grep :

```bash
docker exec lespass_django grep -n "class ProductAdmin\|class ProductForm" /DjangoFiles/Administration/admin_tenant.py
```

Ajouter un `formfield_for_foreignkey` ou `get_form` qui filtre `queryset=Asset.objects.exclude(category=Asset.FED)`.

- [ ] **B4.3 Test manuel** : aller dans l'admin, essayer de créer un Product avec asset FED → impossible. Essayer d'éditer l'Asset FED → champs grisés.

- [ ] **B4.4 Test Playwright (nice-to-have, reportable)** : création Product avec asset exclu → l'asset FED n'apparaît pas dans le dropdown.

---

## Task B5 — Validation Phase B

- [ ] **B5.1 Suite complète Phase B** :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_federation_gateway.py tests/pytest/test_refill_webhook.py -v
```
Expected : ≥ 8 tests PASS.

- [ ] **B5.2 Non-régression totale** :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bootstrap_fed_asset.py tests/pytest/test_refill_service.py tests/pytest/test_refill_serializer.py tests/pytest/test_refill_federation_gateway.py tests/pytest/test_refill_webhook.py tests/pytest/test_fedow_core.py tests/pytest/test_bank_transfer_service.py -v
```
Expected : Phase A + Phase B tous verts, 0 régression.

- [ ] **B5.3 Non-régression webhooks Stripe existants** :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_membership_create.py tests/pytest/test_stripe_reservation.py tests/pytest/test_stripe_crowds.py -v
```
Expected : 0 régression.

- [ ] **B5.4 `manage.py check`** : 0 issue.

---

## Checkpoint sécurité Phase B (obligatoire)

Avant de déclarer Phase B complète :

1. ✅ Le dispatch V2 est **avant** le dispatch legacy dans le webhook
2. ✅ Anti-tampering vérifié avec test explicite
3. ✅ Idempotence vérifiée avec test explicite
4. ✅ Pas de compte Stripe Connect utilisé (compte central uniquement)
5. ✅ SEPA rejeté (`payment_method_types=['card']`)
6. ✅ Aucune régression sur les 3 suites de tests Stripe existantes
7. ✅ Admin verrouillé : Asset FED non modifiable, Product de recharge non créable manuellement

## Messages de commit suggérés (mainteneur)

Un commit par task (B1, B2, B3, B4). Structure identique à Phase A : `feat(module): ...` + explication + `Part of Session 31 Phase B (recharge FED V2)`.
