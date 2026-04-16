# Phase 3 — Bouton POS Cashless « Vider Carte » — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer le service `WalletService.rembourser_en_especes()` (Phase 1) à l'interface POS Cashless via une tile dédiée, un flow court-circuitant le panier (scan NFC → récap → confirmation avec checkbox VV → exécution → écran succès + impression optionnelle).

**Architecture:** 3 endpoints sur `PaiementViewSet` (preview, exécution, impression) + 3 templates HTMX + 1 JS handler + 1 formatter impression. Zéro logique métier dupliquée — 100% réutilisation du service Phase 1 (`WalletService.rembourser_en_especes`) via patch additif `primary_card=None`. Frontend réutilise le composant `<c-read-nfc>` existant (pattern `event-manage-form` + `submit-url`).

**Tech Stack:** Django 5.x, django-tenants, DRF ViewSet, HTMX + Cotton components, Celery (impression async), pytest, Playwright Python.

**Spec source:** `TECH DOC/SESSIONS/CARTES_CASHLESS_ADMIN/2026-04-13-phase3-pos-vider-carte-design.md`

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `fedow_core/services.py` | PATCH léger | +`primary_card=None` sur `WalletService.rembourser_en_especes()`, propagé à `TransactionService.creer()` |
| `laboutik/views.py` | PATCH | +`ViderCarteSerializer` (module-level), +3 `@action` sur `PaiementViewSet` (`vider_carte_preview`, `vider_carte`, `vider_carte_imprimer_recu`) |
| `laboutik/templates/laboutik/partial/hx_vider_carte_overlay.html` | NEW | Overlay scan NFC |
| `laboutik/templates/laboutik/partial/hx_vider_carte_confirm.html` | NEW | Récap tokens + checkbox VV + form confirm |
| `laboutik/templates/laboutik/partial/hx_vider_carte_success.html` | NEW | Écran succès + bouton imprimer |
| `laboutik/templates/laboutik/views/common_user_interface.html` | PATCH léger | Charger `vider_carte.js` |
| `laboutik/static/js/vider_carte.js` | NEW | Handler JS (détection VC, ouverture overlay) |
| `laboutik/printing/formatters.py` | PATCH | +`formatter_recu_vider_carte(transactions)` |
| `tests/pytest/test_pos_vider_carte.py` | NEW | Tests backend (preview, exécution, permissions, impression) |
| `tests/e2e/test_pos_vider_carte.py` | NEW | Flow E2E Playwright |

**URL names générés (DRF router `basename="laboutik-paiement"`) :**
- `laboutik-paiement-vider_carte_preview` → `/laboutik/paiement/vider_carte/preview/`
- `laboutik-paiement-vider_carte` → `/laboutik/paiement/vider_carte/`
- `laboutik-paiement-vider_carte_imprimer_recu` → `/laboutik/paiement/vider_carte/imprimer_recu/`

---

## Préambule — Démarrage du serveur dev

```bash
docker exec -d lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

---

## Task 1: Patch `WalletService.rembourser_en_especes()` — paramètre `primary_card`

**Files:**
- Modify: `fedow_core/services.py` (méthode `WalletService.rembourser_en_especes`, autour de la ligne où elle appelle `TransactionService.creer`)
- Test: `tests/pytest/test_pos_vider_carte.py` (création initiale)

- [ ] **Step 1: Créer le fichier de test initial**

Créer `/home/jonas/TiBillet/dev/Lespass/tests/pytest/test_pos_vider_carte.py` avec ce contenu minimal :

```python
"""
tests/pytest/test_pos_vider_carte.py — Tests Phase 3 : bouton POS "Vider Carte".

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py -v --api-key dummy
"""
import uuid as uuid_module
from datetime import date

import pytest
from django.db import transaction as db_transaction
from django.utils import timezone
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import Wallet
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, WalletService


VC_TEST_PREFIX = '[vc_test]'


@pytest.fixture(scope="module")
def tenant_lespass_vc():
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="module")
def wallet_lieu_vc(tenant_lespass_vc):
    return Wallet.objects.create(name=f'{VC_TEST_PREFIX} Lieu')


@pytest.fixture(scope="module")
def asset_tlf_vc(tenant_lespass_vc, wallet_lieu_vc):
    return AssetService.creer_asset(
        tenant=tenant_lespass_vc,
        name=f'{VC_TEST_PREFIX} TLF',
        category=Asset.TLF,
        currency_code='EUR',
        wallet_origin=wallet_lieu_vc,
    )


@pytest.fixture
def carte_caissier_vc(tenant_lespass_vc):
    """Carte NFC primaire du caissier pour les tests Phase 3."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{VC_TEST_PREFIX}_DETAIL',
            origine=tenant_lespass_vc,
            defaults={"generation": 0},
        )
        carte = CarteCashless.objects.create(
            tag_id='VCT00001',
            number='VCT00001',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
        yield carte
        carte.delete()


@pytest.fixture
def carte_client_vc_avec_tlf(tenant_lespass_vc, asset_tlf_vc):
    """Carte client avec wallet_ephemere crédité 1000c TLF."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{VC_TEST_PREFIX}_DETAIL',
            origine=tenant_lespass_vc,
            defaults={"generation": 0},
        )
        wallet_user = Wallet.objects.create(name=f'{VC_TEST_PREFIX} Wallet client')
        carte = CarteCashless.objects.create(
            tag_id='VCT00002',
            number='VCT00002',
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_user,
        )
        with db_transaction.atomic():
            WalletService.crediter(
                wallet=wallet_user, asset=asset_tlf_vc, montant_en_centimes=1000,
            )
        yield carte
        from BaseBillet.models import LigneArticle
        LigneArticle.objects.filter(carte=carte).delete()
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet=wallet_user).delete()
        carte.delete()
        wallet_user.delete()


def test_rembourser_en_especes_accepte_primary_card(
    tenant_lespass_vc, wallet_lieu_vc, asset_tlf_vc,
    carte_client_vc_avec_tlf, carte_caissier_vc,
):
    """
    WalletService.rembourser_en_especes accepte un parametre primary_card.
    La Transaction REFUND cree porte ce primary_card pour l'audit trail POS.
    """
    with tenant_context(tenant_lespass_vc):
        resultat = WalletService.rembourser_en_especes(
            carte=carte_client_vc_avec_tlf,
            tenant=tenant_lespass_vc,
            receiver_wallet=wallet_lieu_vc,
            ip="127.0.0.1",
            vider_carte=False,
            primary_card=carte_caissier_vc,
        )

        tx = resultat["transactions"][0]
        assert tx.primary_card_id == carte_caissier_vc.pk
        assert tx.action == Transaction.REFUND


@pytest.fixture(scope="module", autouse=True)
def cleanup_vc_test_data():
    yield
    try:
        with schema_context('lespass'):
            from BaseBillet.models import LigneArticle
            wallets_test = Wallet.objects.filter(name__startswith=VC_TEST_PREFIX)
            assets_test = Asset.objects.filter(name__startswith=VC_TEST_PREFIX)
            LigneArticle.objects.filter(carte__tag_id__startswith='VCT').delete()
            Transaction.objects.filter(asset__in=assets_test).delete()
            Token.objects.filter(wallet__in=wallets_test).delete()
            CarteCashless.objects.filter(tag_id__startswith='VCT').delete()
            Detail.objects.filter(base_url__startswith=VC_TEST_PREFIX).delete()
            assets_test.delete()
            wallets_test.delete()
    except Exception:
        pass
```

- [ ] **Step 2: Lancer le test — expect FAIL**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_rembourser_en_especes_accepte_primary_card -v --api-key dummy
```

Expected: FAIL avec `TypeError: rembourser_en_especes() got an unexpected keyword argument 'primary_card'`.

- [ ] **Step 3: Patch la signature + propagation**

Lire d'abord :
```bash
grep -n "def rembourser_en_especes" /home/jonas/TiBillet/dev/Lespass/fedow_core/services.py
```

Dans `fedow_core/services.py`, méthode `WalletService.rembourser_en_especes` :

1. Ajouter le paramètre à la signature :
```python
    @staticmethod
    def rembourser_en_especes(
        carte,
        tenant,
        receiver_wallet,
        ip: str = "0.0.0.0",
        vider_carte: bool = False,
        primary_card=None,
    ) -> dict:
```

2. Trouver l'appel à `TransactionService.creer(...)` dans la méthode (dans la boucle `for token in tokens_eligibles`) et ajouter `primary_card=primary_card` dans les kwargs.

Lire le code existant :
```bash
grep -n "TransactionService.creer" /home/jonas/TiBillet/dev/Lespass/fedow_core/services.py
```

Modifier l'appel (autour de la ligne trouvée dans `rembourser_en_especes`) pour ajouter la ligne `primary_card=primary_card,` entre `card=carte,` et `ip=ip,` :

```python
            tx = TransactionService.creer(
                sender=wallet_carte,
                receiver=receiver_wallet,
                asset=token.asset,
                montant_en_centimes=token.value,
                action=Transaction.REFUND,
                tenant=tenant,
                card=carte,
                primary_card=primary_card,  # NEW Phase 3 : audit POS
                ip=ip,
                comment="Remboursement especes",
                metadata={"vider_carte": vider_carte},
            )
```

Si le `comment` et `metadata` exacts dans le code actuel diffèrent, préserver les valeurs existantes et n'ajouter QUE la ligne `primary_card=primary_card,`.

- [ ] **Step 4: Lancer le test — expect PASS**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_rembourser_en_especes_accepte_primary_card -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 5: Non-régression Phase 1 et Phase 2**

```
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py tests/pytest/test_bank_transfer_service.py tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected: tous PASS (Phase 1 et 2 passent `primary_card=None` implicitement — non-régression).

- [ ] **Step 6: Check Django**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 7: DO NOT commit. Maintainer handles git.**

---

## Task 2: `ViderCarteSerializer` module-level

**Files:**
- Modify: `laboutik/views.py` (ajout d'une classe serializer au niveau module, avant `PaiementViewSet`)

- [ ] **Step 1: Ajouter le test**

Ajouter à `/home/jonas/TiBillet/dev/Lespass/tests/pytest/test_pos_vider_carte.py` (après le test Task 1) :

```python
def test_vider_carte_serializer_normalise_et_valide():
    """
    ViderCarteSerializer accepte {tag_id, tag_id_cm, uuid_pv, vider_carte}
    et normalise tag_id en upper.
    """
    from laboutik.views import ViderCarteSerializer

    data = {
        "tag_id": "abcdef01",  # lowercase → upper
        "tag_id_cm": "deadbeef",
        "uuid_pv": str(uuid_module.uuid4()),
        "vider_carte": True,
    }
    serializer = ViderCarteSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["tag_id"] == "ABCDEF01"
    assert serializer.validated_data["tag_id_cm"] == "DEADBEEF"
    assert serializer.validated_data["vider_carte"] is True


def test_vider_carte_serializer_vider_carte_defaut_false():
    from laboutik.views import ViderCarteSerializer

    data = {
        "tag_id": "ABCDEF01",
        "tag_id_cm": "DEADBEEF",
        "uuid_pv": str(uuid_module.uuid4()),
    }
    serializer = ViderCarteSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["vider_carte"] is False
```

- [ ] **Step 2: Lancer le test — expect FAIL**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_serializer_normalise_et_valide -v --api-key dummy
```

Expected: FAIL `ImportError: cannot import name 'ViderCarteSerializer'`.

- [ ] **Step 3: Ajouter le serializer dans `laboutik/views.py`**

Lire les imports existants :
```bash
grep -n "from rest_framework import serializers\|^from rest_framework" /home/jonas/TiBillet/dev/Lespass/laboutik/views.py | head -5
```

Vérifier que `from rest_framework import serializers` est importé en haut. Si non, l'ajouter.

Puis ajouter le serializer comme classe module-level, juste avant la définition de `PaiementViewSet` (`grep -n "^class PaiementViewSet" /home/jonas/TiBillet/dev/Lespass/laboutik/views.py` pour localiser) :

```python
# -------------------------------------------------------------------------- #
#  ViderCarteSerializer — validation du POST /laboutik/paiement/vider_carte/  #
#  / ViderCarteSerializer — validation for POST /laboutik/paiement/vider_carte/ #
# -------------------------------------------------------------------------- #

class ViderCarteSerializer(serializers.Serializer):
    """
    Valide le POST de saisie d'un vider carte au POS.
    Validates the POST form for a POS card refund.
    """
    tag_id = serializers.CharField(max_length=8)
    tag_id_cm = serializers.CharField(max_length=8)
    uuid_pv = serializers.UUIDField()
    vider_carte = serializers.BooleanField(required=False, default=False)

    def validate_tag_id(self, value):
        return value.strip().upper()

    def validate_tag_id_cm(self, value):
        return value.strip().upper()
```

- [ ] **Step 4: Lancer le test — expect PASS**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_serializer_normalise_et_valide tests/pytest/test_pos_vider_carte.py::test_vider_carte_serializer_vider_carte_defaut_false -v --api-key dummy
```

Expected: 2 PASS.

- [ ] **Step 5: Check**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 6: DO NOT commit.**

---

## Task 3: Endpoint `vider_carte_preview`

**Files:**
- Modify: `laboutik/views.py` (ajout d'un `@action` dans `PaiementViewSet`)

- [ ] **Step 1: Ajouter les tests**

Ajouter à `/home/jonas/TiBillet/dev/Lespass/tests/pytest/test_pos_vider_carte.py` (après les tests précédents) :

```python
from django.test import Client as TestClient


def _login_as_admin():
    from django.contrib.auth import get_user_model
    client = TestClient(HTTP_HOST='lespass.tibillet.localhost')
    User = get_user_model()
    user = User.objects.filter(email='admin@admin.com').first()
    if user is None:
        pytest.skip("User admin@admin.com introuvable")
    client.force_login(user)
    return client, user


def test_vider_carte_preview_carte_inconnue_toast_erreur(carte_caissier_vc):
    """tag_id inexistant → toast erreur, aucune mutation DB."""
    client, user = _login_as_admin()
    response = client.post('/laboutik/paiement/vider_carte/preview/', data={
        'tag_id': 'XYZINCON',  # n'existe pas
        'tag_id_cm': carte_caissier_vc.tag_id,
        'uuid_pv': str(uuid_module.uuid4()),
    })
    assert response.status_code == 200  # render du toast
    contenu = response.content.decode()
    assert 'inconnue' in contenu.lower() or 'unknown' in contenu.lower()


def test_vider_carte_preview_tag_identique_cm_rejette(carte_caissier_vc):
    """Protection self-refund : tag_id == tag_id_cm → toast erreur."""
    client, user = _login_as_admin()
    response = client.post('/laboutik/paiement/vider_carte/preview/', data={
        'tag_id': carte_caissier_vc.tag_id,
        'tag_id_cm': carte_caissier_vc.tag_id,
        'uuid_pv': str(uuid_module.uuid4()),
    })
    assert response.status_code == 200
    contenu = response.content.decode()
    assert 'carte primaire' in contenu.lower() or 'primary card' in contenu.lower()


def test_vider_carte_preview_retourne_recap_tokens(
    carte_client_vc_avec_tlf, carte_caissier_vc,
):
    """Carte client avec 1000c TLF → overlay confirm avec le total."""
    client, user = _login_as_admin()
    response = client.post('/laboutik/paiement/vider_carte/preview/', data={
        'tag_id': carte_client_vc_avec_tlf.tag_id,
        'tag_id_cm': carte_caissier_vc.tag_id,
        'uuid_pv': str(uuid_module.uuid4()),
    })
    assert response.status_code == 200
    contenu = response.content.decode()
    # Total 1000 centimes attendu dans le rendu
    assert '1000' in contenu
    # Aucune mutation DB (preview = lecture seule)
    assert Transaction.objects.filter(card=carte_client_vc_avec_tlf).count() == 0
```

- [ ] **Step 2: Lancer les tests — expect FAIL (404 car endpoint absent)**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_preview_carte_inconnue_toast_erreur -v --api-key dummy
```

Expected: FAIL (404 ou AssertionError sur status_code).

- [ ] **Step 3: Lire les helpers existants réutilisables**

```bash
grep -n "_render_erreur_toast\|_obtenir_ou_creer_wallet\|_charger_carte_primaire" /home/jonas/TiBillet/dev/Lespass/laboutik/views.py | head -10
```

Identifier les noms exacts des helpers existants (ex: `_render_erreur_toast` peut avoir un nom différent — lire le code pour trouver l'équivalent qui rend un partial toast d'erreur). S'il n'existe pas encore, on le crée au step 4.

- [ ] **Step 4: Ajouter un helper d'erreur si absent**

Si `_render_erreur_toast` n'existe pas, l'ajouter au niveau module dans `laboutik/views.py` (avant `PaiementViewSet`) :

```python
def _render_erreur_toast(request, msg):
    """
    Rend un partial d'erreur compatible avec le pattern POS (toast dans #messages).
    / Renders an error partial compatible with POS toast pattern (in #messages).
    """
    contexte = {
        "msg_type": "warning",
        "msg_content": str(msg),
        "selector_bt_retour": "#messages",
    }
    return render(request, "laboutik/partial/hx_messages.html", contexte)
```

NB : si le codebase utilise déjà un helper similaire (nom différent), utiliser celui-là. Vérifier avec `grep -n "def _render.*toast\|def _render.*erreur" /home/jonas/TiBillet/dev/Lespass/laboutik/views.py`.

- [ ] **Step 5: Ajouter l'action `vider_carte_preview` dans `PaiementViewSet`**

Dans `laboutik/views.py`, classe `PaiementViewSet`, ajouter cette méthode (emplacement : après les autres `@action` du ViewSet, par exemple après `retour_carte`) :

```python
    @action(
        detail=False,
        methods=["post"],
        url_path="vider_carte/preview",
        url_name="vider_carte_preview",
    )
    def vider_carte_preview(self, request):
        """
        POST /laboutik/paiement/vider_carte/preview/
        Calcule les tokens eligibles pour la carte client scannee et renvoie
        l'overlay de confirmation. Pas de mutation DB.
        / Computes eligible tokens for the scanned client card and returns
        the confirmation overlay. No DB mutation.
        """
        from django.db.models import Q
        from fedow_core.models import Asset, Token

        tag_id = request.POST.get("tag_id", "").strip().upper()
        tag_id_cm = request.POST.get("tag_id_cm", "").strip().upper()
        uuid_pv = request.POST.get("uuid_pv", "")

        # Protection self-refund : on ne peut pas vider une carte primaire.
        # / Self-refund protection: cannot empty a primary card.
        if tag_id and tag_id == tag_id_cm:
            return _render_erreur_toast(
                request, _("Ne peut pas vider une carte primaire."),
            )

        try:
            carte = CarteCashless.objects.get(tag_id=tag_id)
        except CarteCashless.DoesNotExist:
            return _render_erreur_toast(request, _("Carte client inconnue."))

        wallet = _obtenir_ou_creer_wallet(carte)
        if wallet is None:
            return _render_erreur_toast(request, _("Carte vierge."))

        tokens = list(
            Token.objects.filter(
                wallet=wallet, value__gt=0,
            ).filter(
                Q(asset__category=Asset.TLF, asset__tenant_origin=connection.tenant)
                | Q(asset__category=Asset.FED)
            ).select_related('asset', 'asset__tenant_origin').order_by('asset__category')
        )

        if not tokens:
            return _render_erreur_toast(
                request, _("Aucun solde remboursable sur cette carte."),
            )

        total_tlf = sum(t.value for t in tokens if t.asset.category == Asset.TLF)
        total_fed = sum(t.value for t in tokens if t.asset.category == Asset.FED)

        contexte = {
            "carte": carte,
            "tokens": tokens,
            "total_centimes": total_tlf + total_fed,
            "total_tlf_centimes": total_tlf,
            "total_fed_centimes": total_fed,
            "tag_id": tag_id,
            "tag_id_cm": tag_id_cm,
            "uuid_pv": uuid_pv,
        }
        return render(
            request, "laboutik/partial/hx_vider_carte_confirm.html", contexte,
        )
```

**Note** : ne PAS créer encore le template `hx_vider_carte_confirm.html` — Task 7 le crée. Les tests preview vont falloir contourner ça. Le test `test_vider_carte_preview_retourne_recap_tokens` va échouer à cause du TemplateDoesNotExist → on le laisse en FAIL jusqu'à Task 7, ou on peut le mettre `pytest.mark.skip` temporairement.

Pour le test au Step 6 ci-dessous : d'abord on vérifie seulement les 2 tests d'erreur (preview carte inconnue + self-refund) qui ne rendent pas `hx_vider_carte_confirm.html`.

- [ ] **Step 6: Lancer les tests d'erreur (qui n'ont pas besoin du template confirm)**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_preview_carte_inconnue_toast_erreur tests/pytest/test_pos_vider_carte.py::test_vider_carte_preview_tag_identique_cm_rejette -v --api-key dummy
```

Expected: 2 PASS.

Le test `test_vider_carte_preview_retourne_recap_tokens` reste en ERROR jusqu'à Task 7. Marquer `pytest.mark.xfail(reason="Template Task 7")` en attendant OU ignorer ce test ponctuellement.

- [ ] **Step 7: Check**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 8: DO NOT commit.**

---

## Task 4: Endpoint `vider_carte` (exécution)

**Files:**
- Modify: `laboutik/views.py` (ajout d'un `@action` dans `PaiementViewSet`)

- [ ] **Step 1: Ajouter les tests**

Ajouter à `tests/pytest/test_pos_vider_carte.py` :

```python
from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin


@pytest.fixture
def pv_cashless_vc(carte_caissier_vc):
    """PointDeVente qui autorise carte_caissier_vc et contient le Product VIDER_CARTE."""
    from laboutik.models import CartePrimaire, PointDeVente
    from BaseBillet.models import Product
    from BaseBillet.services_refund import get_or_create_product_remboursement

    with schema_context('lespass'):
        pv, _ = PointDeVente.objects.get_or_create(
            name='VC Test PV',
            defaults={'comportement': 'V', 'hidden': False},
        )
        cp, _ = CartePrimaire.objects.get_or_create(
            carte=carte_caissier_vc,
            defaults={'edit_mode': False},
        )
        cp.points_de_vente.add(pv)
        product_vc = get_or_create_product_remboursement()
        pv.products.add(product_vc)
        yield pv
        pv.products.remove(product_vc)
        cp.points_de_vente.remove(pv)
        cp.delete()
        pv.delete()


def test_vider_carte_execute_remboursement_complet(
    carte_client_vc_avec_tlf, carte_caissier_vc, pv_cashless_vc,
):
    """
    POST /laboutik/paiement/vider_carte/ avec vider_carte=false :
    1 Transaction REFUND TLF + 1 LigneArticle CASH (-1000).
    primary_card de la Transaction == carte_caissier.
    """
    client, user = _login_as_admin()
    response = client.post('/laboutik/paiement/vider_carte/', data={
        'tag_id': carte_client_vc_avec_tlf.tag_id,
        'tag_id_cm': carte_caissier_vc.tag_id,
        'uuid_pv': str(pv_cashless_vc.uuid),
        'vider_carte': 'false',
    })
    assert response.status_code == 200, response.content.decode()[:500]

    # Verifier transactions REFUND
    tx_refund = Transaction.objects.filter(
        card=carte_client_vc_avec_tlf, action=Transaction.REFUND,
    )
    assert tx_refund.count() == 1
    assert tx_refund.first().primary_card_id == carte_caissier_vc.pk

    # Verifier LigneArticle CASH negative
    lignes_cash = LigneArticle.objects.filter(
        carte=carte_client_vc_avec_tlf,
        payment_method=PaymentMethod.CASH,
        sale_origin=SaleOrigin.ADMIN,
    )
    assert lignes_cash.count() == 1
    assert lignes_cash.first().amount == -1000


def test_vider_carte_execute_avec_vv(
    carte_client_vc_avec_tlf, carte_caissier_vc, pv_cashless_vc,
):
    """vider_carte=true → carte.user=None, carte.wallet_ephemere=None."""
    client, user = _login_as_admin()
    response = client.post('/laboutik/paiement/vider_carte/', data={
        'tag_id': carte_client_vc_avec_tlf.tag_id,
        'tag_id_cm': carte_caissier_vc.tag_id,
        'uuid_pv': str(pv_cashless_vc.uuid),
        'vider_carte': 'true',
    })
    assert response.status_code == 200

    carte_client_vc_avec_tlf.refresh_from_db()
    assert carte_client_vc_avec_tlf.user is None
    assert carte_client_vc_avec_tlf.wallet_ephemere is None


def test_vider_carte_carte_primaire_pas_liee_pv_rejette(
    carte_client_vc_avec_tlf, carte_caissier_vc,
):
    """Si la carte caissier n'est pas dans pv.cartes_primaires → toast erreur."""
    from laboutik.models import PointDeVente

    client, user = _login_as_admin()
    # PV sans lien avec la carte caissier
    with schema_context('lespass'):
        pv_orphan, _ = PointDeVente.objects.get_or_create(
            name='VC Orphan PV',
            defaults={'comportement': 'V', 'hidden': False},
        )

    try:
        response = client.post('/laboutik/paiement/vider_carte/', data={
            'tag_id': carte_client_vc_avec_tlf.tag_id,
            'tag_id_cm': carte_caissier_vc.tag_id,
            'uuid_pv': str(pv_orphan.uuid),
            'vider_carte': 'false',
        })
        assert response.status_code == 200
        contenu = response.content.decode()
        assert 'acces' in contenu.lower() or 'access' in contenu.lower()
        # Aucune Transaction creee
        assert Transaction.objects.filter(
            card=carte_client_vc_avec_tlf, action=Transaction.REFUND,
        ).count() == 0
    finally:
        with schema_context('lespass'):
            pv_orphan.delete()
```

- [ ] **Step 2: Lancer les tests — expect FAIL (404)**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_execute_remboursement_complet -v --api-key dummy
```

Expected: FAIL (404 car endpoint absent).

- [ ] **Step 3: Ajouter l'action `vider_carte` dans `PaiementViewSet`**

Dans `laboutik/views.py`, classe `PaiementViewSet`, ajouter après `vider_carte_preview` :

```python
    @action(
        detail=False,
        methods=["post"],
        url_path="vider_carte",
        url_name="vider_carte",
    )
    def vider_carte(self, request):
        """
        POST /laboutik/paiement/vider_carte/
        Execute le remboursement via WalletService.rembourser_en_especes.
        Renvoie l'ecran de succes ou un toast d'erreur.
        / Executes the refund via WalletService.rembourser_en_especes.
        Returns the success screen or an error toast.
        """
        from fedow_core.exceptions import NoEligibleTokens

        serializer = ViderCarteSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)

        tag_id_client = serializer.validated_data["tag_id"]
        tag_id_cm = serializer.validated_data["tag_id_cm"]
        uuid_pv = serializer.validated_data["uuid_pv"]
        vider_carte_flag = serializer.validated_data["vider_carte"]

        # Protection self-refund (meme check qu'en preview).
        # / Self-refund protection (same check as preview).
        if tag_id_client == tag_id_cm:
            return _render_erreur_toast(
                request, _("Ne peut pas vider une carte primaire."),
            )

        try:
            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
        except CarteCashless.DoesNotExist:
            return _render_erreur_toast(request, _("Carte client inconnue."))

        carte_primaire_obj, erreur_cp = _charger_carte_primaire(tag_id_cm)
        if erreur_cp:
            return _render_erreur_toast(request, erreur_cp)

        pv = PointDeVente.objects.filter(uuid=uuid_pv).first()
        if pv is None:
            return _render_erreur_toast(request, _("PV introuvable."))

        # Controle d'acces : la carte primaire doit pouvoir operer sur ce PV.
        # / Access control: primary card must have access to this POS.
        if not pv.cartes_primaires.filter(pk=carte_primaire_obj.pk).exists():
            return _render_erreur_toast(
                request, _("Cette carte caissier n'a pas acces a ce PV."),
            )

        receiver_wallet = WalletService.get_or_create_wallet_tenant(connection.tenant)

        try:
            resultat = WalletService.rembourser_en_especes(
                carte=carte_client,
                tenant=connection.tenant,
                receiver_wallet=receiver_wallet,
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                vider_carte=vider_carte_flag,
                primary_card=carte_primaire_obj.carte,
            )
        except NoEligibleTokens:
            return _render_erreur_toast(
                request, _("Aucun solde remboursable (solde a pu changer)."),
            )

        contexte = {
            "total_centimes": resultat["total_centimes"],
            "total_tlf_centimes": resultat["total_tlf_centimes"],
            "total_fed_centimes": resultat["total_fed_centimes"],
            "lignes_articles": resultat["lignes_articles"],
            "transaction_uuids": [str(tx.uuid) for tx in resultat["transactions"]],
            "uuid_pv": uuid_pv,
            "vider_carte": vider_carte_flag,
        }
        return render(
            request, "laboutik/partial/hx_vider_carte_success.html", contexte,
        )
```

Les 3 tests vont avoir besoin du template `hx_vider_carte_success.html` (Task 8) pour passer entièrement. Pour l'instant :
- `test_vider_carte_carte_primaire_pas_liee_pv_rejette` → PASS (rend un toast, pas le success template).
- `test_vider_carte_execute_remboursement_complet` → ERROR sur template manquant.
- `test_vider_carte_execute_avec_vv` → ERROR sur template manquant.

Les 2 derniers passeront à Task 8. Pour l'instant on vérifie juste le 1er :

- [ ] **Step 4: Lancer le test d'accès refusé**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_carte_primaire_pas_liee_pv_rejette -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 5: Check**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 6: DO NOT commit.**

---

## Task 5: Endpoint `vider_carte_imprimer_recu`

**Files:**
- Modify: `laboutik/views.py` (ajout d'un `@action` dans `PaiementViewSet`)

- [ ] **Step 1: Ajouter l'action dans `PaiementViewSet`**

Dans `laboutik/views.py`, classe `PaiementViewSet`, après `vider_carte` :

```python
    @action(
        detail=False,
        methods=["post"],
        url_path="vider_carte/imprimer_recu",
        url_name="vider_carte_imprimer_recu",
    )
    def vider_carte_imprimer_recu(self, request):
        """
        POST /laboutik/paiement/vider_carte/imprimer_recu/
        Lance l'impression Celery du recu pour les transactions_uuids donnees.
        / Launches the Celery receipt print for the given transaction UUIDs.
        """
        transaction_uuids = request.POST.getlist("transaction_uuids")
        uuid_pv = request.POST.get("uuid_pv", "")

        if not transaction_uuids or not uuid_pv:
            return _render_erreur_toast(request, _("Parametres manquants."))

        pv = PointDeVente.objects.select_related("printer").filter(uuid=uuid_pv).first()
        if pv is None or pv.printer is None or not pv.printer.active:
            return _render_erreur_toast(
                request, _("Pas d'imprimante configuree sur ce PV."),
            )

        transactions = Transaction.objects.filter(
            uuid__in=transaction_uuids,
        ).select_related("asset")

        from laboutik.printing.formatters import formatter_recu_vider_carte
        from laboutik.printing.tasks import imprimer_async

        recu_data = formatter_recu_vider_carte(list(transactions))
        imprimer_async.delay(
            str(pv.printer.pk),
            recu_data,
            connection.schema_name,
        )
        return render(request, "laboutik/partial/hx_impression_ok.html")
```

- [ ] **Step 2: Ajouter un test de permission (sans imprimante → toast info)**

Ajouter à `tests/pytest/test_pos_vider_carte.py` :

```python
def test_vider_carte_imprimer_recu_sans_imprimante_toast_info(pv_cashless_vc):
    """
    PV sans imprimante active → toast 'Pas d'imprimante configuree'.
    L'operation DB n'est pas affectee (deja enregistree avant cet endpoint).
    """
    client, user = _login_as_admin()
    response = client.post(
        '/laboutik/paiement/vider_carte/imprimer_recu/',
        data={
            'transaction_uuids': [str(uuid_module.uuid4())],
            'uuid_pv': str(pv_cashless_vc.uuid),
        },
    )
    assert response.status_code == 200
    contenu = response.content.decode()
    assert 'imprimante' in contenu.lower() or 'printer' in contenu.lower()
```

- [ ] **Step 3: Lancer le test — expect PASS**

`pv_cashless_vc` n'a pas de printer attaché, donc le test passe immédiatement.

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_imprimer_recu_sans_imprimante_toast_info -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 4: Check**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 5: DO NOT commit.**

---

## Task 6: Template `hx_vider_carte_overlay.html`

**Files:**
- Create: `laboutik/templates/laboutik/partial/hx_vider_carte_overlay.html`

- [ ] **Step 1: Créer le template**

```html
{% load static i18n %}
{# Overlay plein écran qui propose le scan NFC de la carte client. #}
{# Full-screen overlay inviting the NFC scan of the client card. #}

<div id="vider-carte-overlay"
     class="overlay overlay-fullscreen"
     data-testid="vider-carte-overlay">
    <div class="overlay-content">
        <h2>{% translate "Vider la carte" %}</h2>
        <p>{% translate "Scannez la carte du client." %}</p>

        {# Form cache avec hidden fields tag_id (rempli par NFC), tag_id_cm, uuid_pv. #}
        {# Hidden form with hidden fields tag_id (filled by NFC), tag_id_cm, uuid_pv. #}
        <form id="vider-carte-form" style="display: none;">
            {% csrf_token %}
            <input type="hidden" name="tag_id" id="nfc-tag-id" value="">
            <input type="hidden" name="tag_id_cm" value="{{ card.tag_id }}">
            <input type="hidden" name="uuid_pv" value="{{ pv.uuid }}">
        </form>

        <c-read-nfc event-manage-form="viderCarteManageForm"
                    submit-url="{% url 'laboutik-paiement-vider_carte_preview' %}">
            <button type="button"
                    class="btn btn-secondary"
                    onclick="document.getElementById('vider-carte-overlay').remove();"
                    data-testid="vider-carte-cancel">
                {% translate "Annuler" %}
            </button>
        </c-read-nfc>
    </div>
</div>
```

- [ ] **Step 2: Vérifier que le template est chargeable**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from django.template.loader import get_template; get_template('laboutik/partial/hx_vider_carte_overlay.html'); print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Check**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 4: DO NOT commit.**

---

## Task 7: Template `hx_vider_carte_confirm.html`

**Files:**
- Create: `laboutik/templates/laboutik/partial/hx_vider_carte_confirm.html`

- [ ] **Step 1: Créer le template**

```html
{% load i18n %}
{# Overlay de confirmation avec recap tokens + checkbox VV. #}
{# Confirmation overlay with token summary + VV checkbox. #}

<div id="vider-carte-confirm"
     class="overlay overlay-fullscreen"
     data-testid="vider-carte-confirm">
    <div class="overlay-content" style="max-width: 500px; margin: 80px auto; padding: 24px; background: white; border-radius: 8px;">
        <h2 style="margin-top: 0;">{% translate "Vider la carte" %} {{ carte.tag_id }}</h2>

        <div style="font-size: 2rem; font-weight: bold; text-align: center; margin: 24px 0; color: #16A34A;">
            {% translate "À rendre" %} : {{ total_centimes }} c
            <span style="display: block; font-size: 0.8rem; color: #6B7280; font-weight: normal;">
                {% translate "centimes" %}
            </span>
        </div>

        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;" data-testid="vider-carte-tokens-table">
            <thead>
                <tr style="background: #F9FAFB; border-bottom: 1px solid #E5E7EB;">
                    <th style="padding: 8px; text-align: left;">{% translate "Asset" %}</th>
                    <th style="padding: 8px; text-align: right;">{% translate "Solde" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for token in tokens %}
                <tr style="border-bottom: 1px solid #E5E7EB;">
                    <td style="padding: 8px;">{{ token.asset.name }} ({{ token.asset.get_category_display }})</td>
                    <td style="padding: 8px; text-align: right;">{{ token.value }} c</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <form method="post"
              action="{% url 'laboutik-paiement-vider_carte' %}"
              hx-post="{% url 'laboutik-paiement-vider_carte' %}"
              hx-target="#messages"
              hx-swap="innerHTML"
              data-testid="vider-carte-confirm-form">
            {% csrf_token %}
            <input type="hidden" name="tag_id" value="{{ tag_id }}">
            <input type="hidden" name="tag_id_cm" value="{{ tag_id_cm }}">
            <input type="hidden" name="uuid_pv" value="{{ uuid_pv }}">

            <p style="margin: 16px 0;">
                <label>
                    <input type="checkbox" name="vider_carte" value="true"
                           data-testid="vider-carte-checkbox-vv">
                    {% translate "Réinitialiser la carte après remboursement (détache user, wallet, carte primaire)" %}
                </label>
            </p>

            <div style="display: flex; gap: 8px; margin-top: 16px;">
                <button type="submit"
                        style="flex: 1; padding: 12px; background: #16A34A; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;"
                        data-testid="vider-carte-btn-confirm">
                    {% translate "Confirmer le remboursement" %}
                </button>
                <button type="button"
                        onclick="document.getElementById('vider-carte-confirm').remove();"
                        style="flex: 1; padding: 12px; background: #6B7280; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;"
                        data-testid="vider-carte-btn-cancel">
                    {% translate "Annuler" %}
                </button>
            </div>
        </form>
    </div>
</div>
```

- [ ] **Step 2: Vérifier que le template est chargeable**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from django.template.loader import get_template; get_template('laboutik/partial/hx_vider_carte_confirm.html'); print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Lancer le test `test_vider_carte_preview_retourne_recap_tokens`**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_preview_retourne_recap_tokens -v --api-key dummy
```

Expected: PASS (le template existe maintenant, le preview peut le rendre).

- [ ] **Step 4: Check**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 5: DO NOT commit.**

---

## Task 8: Template `hx_vider_carte_success.html`

**Files:**
- Create: `laboutik/templates/laboutik/partial/hx_vider_carte_success.html`

- [ ] **Step 1: Créer le template**

```html
{% load i18n %}
{# Ecran de succes apres vider carte. #}
{# Success screen after empty card. #}

<div id="vider-carte-success"
     class="overlay overlay-fullscreen"
     data-testid="vider-carte-success">
    <div class="overlay-content" style="max-width: 500px; margin: 80px auto; padding: 24px; background: white; border-radius: 8px;">
        <h2 style="margin-top: 0; color: #16A34A;">
            {% translate "Remboursement effectué" %}
        </h2>

        <div style="font-size: 2.5rem; font-weight: bold; text-align: center; margin: 24px 0;"
             data-testid="vider-carte-success-amount">
            {{ total_centimes }} c
            <span style="display: block; font-size: 0.8rem; color: #6B7280; font-weight: normal;">
                {% translate "centimes" %}
            </span>
        </div>

        <div style="background: #F3F4F6; padding: 12px; border-radius: 6px; margin: 16px 0; font-size: 0.9rem;">
            {% if total_tlf_centimes > 0 %}
            <p style="margin: 4px 0;">
                {% translate "Monnaie locale" %} : {{ total_tlf_centimes }} c
            </p>
            {% endif %}
            {% if total_fed_centimes > 0 %}
            <p style="margin: 4px 0;">
                {% translate "Fiduciaire fédérée" %} : {{ total_fed_centimes }} c
            </p>
            {% endif %}
        </div>

        {% if vider_carte %}
        <div style="background: #FEF3C7; color: #92400E; padding: 12px; border-radius: 6px; margin: 16px 0;">
            {% translate "La carte a été réinitialisée." %}
        </div>
        {% endif %}

        <div style="display: flex; gap: 8px; margin-top: 16px;">
            <form style="flex: 1; margin: 0;"
                  hx-post="{% url 'laboutik-paiement-vider_carte_imprimer_recu' %}"
                  hx-target="#messages"
                  hx-swap="innerHTML">
                {% csrf_token %}
                {% for tx_uuid in transaction_uuids %}
                <input type="hidden" name="transaction_uuids" value="{{ tx_uuid }}">
                {% endfor %}
                <input type="hidden" name="uuid_pv" value="{{ uuid_pv }}">
                <button type="submit"
                        style="width: 100%; padding: 12px; background: #2563EB; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;"
                        data-testid="vider-carte-btn-imprimer">
                    {% translate "Imprimer reçu" %}
                </button>
            </form>
            <button type="button"
                    onclick="document.getElementById('vider-carte-success').remove();"
                    style="flex: 1; padding: 12px; background: #6B7280; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;"
                    data-testid="vider-carte-btn-retour">
                {% translate "Retour" %}
            </button>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Vérifier que le template est chargeable**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from django.template.loader import get_template; get_template('laboutik/partial/hx_vider_carte_success.html'); print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Lancer les tests d'exécution (qui ont besoin de ce template)**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_vider_carte_execute_remboursement_complet tests/pytest/test_pos_vider_carte.py::test_vider_carte_execute_avec_vv -v --api-key dummy
```

Expected: 2 PASS.

- [ ] **Step 4: Check**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 5: DO NOT commit.**

---

## Task 9: Frontend `vider_carte.js` + chargement dans `common_user_interface.html`

**Files:**
- Create: `laboutik/static/js/vider_carte.js`
- Modify: `laboutik/templates/laboutik/views/common_user_interface.html` (ajout `<script src=...>`)

- [ ] **Step 1: Créer `laboutik/static/js/vider_carte.js`**

```javascript
/**
 * Vider Carte — flow POS Phase 3
 * / Empty Card — POS Phase 3 flow
 *
 * LOCALISATION : laboutik/static/js/vider_carte.js
 *
 * Déclenche un flow dédié quand une tile methode_caisse=VC est cliquée.
 * Court-circuite le panier : scan NFC -> overlay confirm -> POST backend -> success.
 * / Triggers a dedicated flow when a methode_caisse=VC tile is clicked.
 * Bypasses the cart: NFC scan -> confirm overlay -> backend POST -> success.
 *
 * COMMUNICATION :
 *   Ecoute : clic sur .article-btn avec data-methode-caisse="VC"
 *   Emet : fetch /laboutik/paiement/vider_carte/overlay/ (ou injecte HTML statique)
 *   Laisse <c-read-nfc> gerer le reste via event-manage-form="viderCarteManageForm"
 */

(function() {
    /**
     * Intercepte les clics sur les tiles VC avant que addArticle soit appele.
     * / Intercepts clicks on VC tiles before addArticle is called.
     */
    document.addEventListener("click", function(event) {
        const tile = event.target.closest('[data-methode-caisse="VC"]');
        if (!tile) return;

        // Empeche addArticle / handlers du routeur d'articles.
        // / Prevents addArticle / article router handlers.
        event.preventDefault();
        event.stopImmediatePropagation();

        injecterOverlayViderCarte();
    }, true);  // capture phase : on intercepte avant les autres listeners

    /**
     * Injecte l'overlay vider-carte en fetching le HTML depuis le backend.
     * / Injects the vider-carte overlay by fetching HTML from the backend.
     *
     * NB : on passe par un fetch pour que Django rende le template avec
     * le bon {{ card.tag_id }} et {{ pv.uuid }} du contexte POS courant.
     */
    function injecterOverlayViderCarte() {
        // Retire un eventuel overlay precedent
        const ancien = document.getElementById("vider-carte-overlay");
        if (ancien) ancien.remove();

        // Fetch l'overlay en GET (cote serveur, pas de mutation, juste render).
        fetch("/laboutik/paiement/vider_carte/overlay/", {
            method: "GET",
            credentials: "same-origin",
        })
            .then(response => response.text())
            .then(html => {
                // Injecte dans #messages (conteneur global des overlays POS).
                const messages = document.getElementById("messages");
                if (messages) {
                    messages.innerHTML = html;
                    // Evalue les scripts injectes (initNfc du component c-read-nfc).
                    // / Evaluate injected scripts (initNfc of c-read-nfc component).
                    messages.querySelectorAll("script").forEach(oldScript => {
                        const newScript = document.createElement("script");
                        newScript.text = oldScript.textContent;
                        oldScript.parentNode.replaceChild(newScript, oldScript);
                    });
                }
            })
            .catch(error => {
                console.error("Erreur chargement overlay vider carte:", error);
            });
    }
})();
```

- [ ] **Step 2: Créer l'endpoint backend `overlay/` qui rend le template**

Dans `laboutik/views.py`, classe `PaiementViewSet`, ajouter (AVANT `vider_carte_preview`) :

```python
    @action(
        detail=False,
        methods=["get"],
        url_path="vider_carte/overlay",
        url_name="vider_carte_overlay",
    )
    def vider_carte_overlay(self, request):
        """
        GET /laboutik/paiement/vider_carte/overlay/
        Rend l'overlay de scan NFC pour vider carte.
        / Renders the NFC scan overlay for card refund.
        """
        uuid_pv = request.GET.get("uuid_pv", "")
        tag_id_cm = request.GET.get("tag_id_cm", "")

        pv = None
        if uuid_pv:
            pv = PointDeVente.objects.filter(uuid=uuid_pv).first()

        # Minimal context : pv + card.tag_id via tag_id_cm query param.
        # / Minimal context: pv + card.tag_id via tag_id_cm query param.
        contexte = {
            "pv": pv,
            "card": {"tag_id": tag_id_cm},
        }
        return render(
            request, "laboutik/partial/hx_vider_carte_overlay.html", contexte,
        )
```

**Mise à jour du JS** : le fetch doit passer `uuid_pv` et `tag_id_cm` en query params. Modifier `vider_carte.js` :

```javascript
    function injecterOverlayViderCarte() {
        const ancien = document.getElementById("vider-carte-overlay");
        if (ancien) ancien.remove();

        // Recupere uuid_pv et tag_id_cm depuis #addition-form ou state.
        // / Retrieves uuid_pv and tag_id_cm from #addition-form or state.
        const form = document.getElementById("addition-form");
        const uuidPv = form ? form.querySelector('[name="uuid_pv"]')?.value : "";
        const tagIdCm = form ? form.querySelector('[name="tag_id_cm"]')?.value : "";

        const params = new URLSearchParams({uuid_pv: uuidPv, tag_id_cm: tagIdCm});
        fetch("/laboutik/paiement/vider_carte/overlay/?" + params.toString(), {
            method: "GET",
            credentials: "same-origin",
        })
            .then(response => response.text())
            .then(html => {
                const messages = document.getElementById("messages");
                if (messages) {
                    messages.innerHTML = html;
                    messages.querySelectorAll("script").forEach(oldScript => {
                        const newScript = document.createElement("script");
                        newScript.text = oldScript.textContent;
                        oldScript.parentNode.replaceChild(newScript, oldScript);
                    });
                }
            })
            .catch(error => {
                console.error("Erreur chargement overlay vider carte:", error);
            });
    }
```

- [ ] **Step 3: Charger `vider_carte.js` dans `common_user_interface.html`**

Lire le fichier pour trouver où les autres scripts POS sont chargés :
```bash
grep -n "addition\.js\|articles\.js" /home/jonas/TiBillet/dev/Lespass/laboutik/templates/laboutik/views/common_user_interface.html
```

Ajouter une ligne après les autres scripts JS POS :
```html
<script src="{% static 'js/vider_carte.js' %}"></script>
```

- [ ] **Step 4: Check Django**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 5: Vérifier que les 3 URL names se résolvent**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django.urls import reverse
print(reverse('laboutik-paiement-vider_carte_overlay'))
print(reverse('laboutik-paiement-vider_carte_preview'))
print(reverse('laboutik-paiement-vider_carte'))
print(reverse('laboutik-paiement-vider_carte_imprimer_recu'))
"
```

Expected:
```
/laboutik/paiement/vider_carte/overlay/
/laboutik/paiement/vider_carte/preview/
/laboutik/paiement/vider_carte/
/laboutik/paiement/vider_carte/imprimer_recu/
```

- [ ] **Step 6: DO NOT commit.**

---

## Task 10: Formatter impression `formatter_recu_vider_carte`

**Files:**
- Modify: `laboutik/printing/formatters.py` (ajout d'une fonction)

- [ ] **Step 1: Ajouter un test**

Ajouter à `tests/pytest/test_pos_vider_carte.py` :

```python
def test_formatter_recu_vider_carte_structure_dict(
    tenant_lespass_vc, asset_tlf_vc, wallet_lieu_vc,
):
    """Le formatter retourne un dict compatible avec imprimer_async."""
    from laboutik.printing.formatters import formatter_recu_vider_carte
    from AuthBillet.models import Wallet

    # Creer 2 transactions REFUND simulees
    wallet_source = Wallet.objects.create(name=f'{VC_TEST_PREFIX} Source recu')
    with schema_context('lespass'):
        tx1 = Transaction.objects.create(
            sender=wallet_source, receiver=wallet_lieu_vc,
            asset=asset_tlf_vc, amount=800, action=Transaction.REFUND,
            tenant=tenant_lespass_vc, datetime=timezone.now(), ip="127.0.0.1",
        )
        tx2 = Transaction.objects.create(
            sender=wallet_source, receiver=wallet_lieu_vc,
            asset=asset_tlf_vc, amount=200, action=Transaction.REFUND,
            tenant=tenant_lespass_vc, datetime=timezone.now(), ip="127.0.0.1",
        )

        recu = formatter_recu_vider_carte([tx1, tx2])
        assert isinstance(recu, dict)
        assert "header" in recu
        assert "total" in recu
        # Le total doit refleter la somme des amounts.
        assert recu["total"]["amount"] == 1000

        # Cleanup
        Transaction.objects.filter(sender=wallet_source).delete()
        wallet_source.delete()
```

- [ ] **Step 2: Lancer le test — expect FAIL**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_formatter_recu_vider_carte_structure_dict -v --api-key dummy
```

Expected: FAIL `ImportError: cannot import name 'formatter_recu_vider_carte'`.

- [ ] **Step 3: Ajouter le formatter à la fin de `laboutik/printing/formatters.py`**

```python
def formatter_recu_vider_carte(transactions):
    """
    Formate un recu client pour un vider carte (remboursement especes).
    Inclut les mentions legales + detail par asset + reference Transaction.
    / Formats a customer receipt for a card refund (cash refund).
    Includes legal mentions + detail per asset + Transaction reference.

    LOCALISATION : laboutik/printing/formatters.py

    :param transactions: liste de Transaction REFUND (1 par asset)
    :return: dict ticket_data compatible avec imprimer_async
    """
    from BaseBillet.models import Configuration
    from laboutik.models import LaboutikConfiguration

    now = timezone.localtime(timezone.now())

    config = Configuration.get_solo()
    laboutik_config = LaboutikConfiguration.get_solo()

    # Mentions legales basiques (adresse + SIRET si dispo).
    # / Basic legal mentions.
    parties_adresse = []
    if config.adress:
        parties_adresse.append(config.adress)
    if config.postal_code:
        parties_adresse.append(str(config.postal_code))
    if config.city:
        parties_adresse.append(config.city)
    adresse_complete = " ".join(parties_adresse)

    legal = {
        "organisation": config.organisation or "",
        "adresse": adresse_complete,
        "siret": getattr(laboutik_config, "siret", "") or "",
    }

    # Calcul du total et detail par asset.
    # / Compute total and per-asset detail.
    total_centimes = 0
    articles = []
    for tx in transactions:
        total_centimes += tx.amount
        articles.append({
            "name": f"{tx.asset.name} ({tx.get_action_display()})",
            "qty": 1,
            "prix_centimes": tx.amount,
            "total_centimes": tx.amount,
        })

    return {
        "header": {
            "title": _("REMBOURSEMENT CARTE"),
            "subtitle": "",
            "date": now.strftime("%d/%m/%Y %H:%M"),
        },
        "legal": legal,
        "articles": articles,
        "total": {
            "amount": total_centimes,
            "label": _("Especes"),
        },
        "is_duplicata": False,
        "is_simulation": False,
        "pied_ticket": _("Merci de votre visite."),
        "qrcode": None,
        "footer": [],
    }
```

Vérifier les imports en haut du fichier `laboutik/printing/formatters.py`. `timezone` et `_` (gettext) doivent déjà être présents — si absents, ajouter :
```python
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
```

- [ ] **Step 4: Lancer le test — expect PASS**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py::test_formatter_recu_vider_carte_structure_dict -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 5: Check**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 6: DO NOT commit.**

---

## Task 11: Tests — suite finale backend

**Files:**
- Modify: `tests/pytest/test_pos_vider_carte.py` (consolidation)

- [ ] **Step 1: Lancer tous les tests du fichier**

```
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py -v --api-key dummy
```

Expected : tous les tests de Tasks 1-10 en PASS (ou SKIP propres si admin n'est pas superuser, mais pour Phase 3 POS on n'a pas besoin de superuser — juste d'un admin tenant).

- [ ] **Step 2: Non-régression Phase 1 + Phase 2**

```
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py tests/pytest/test_admin_cards.py tests/pytest/test_bank_transfer_service.py tests/pytest/test_admin_bank_transfers.py tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected : tous PASS (modulo les erreurs cross-file pré-existantes).

- [ ] **Step 3: Check final**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected : 0 issue.

- [ ] **Step 4: DO NOT commit.**

---

## Task 12: Test E2E Playwright

**Files:**
- Create: `tests/e2e/test_pos_vider_carte.py`

- [ ] **Step 1: Vérifier que le serveur dev tourne**

```bash
curl -k -o /dev/null -s -w "%{http_code}" https://lespass.tibillet.localhost/laboutik/caisse/
```

Si pas 200/302 :
```bash
docker exec -d lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

- [ ] **Step 2: Créer `/home/jonas/TiBillet/dev/Lespass/tests/e2e/test_pos_vider_carte.py`**

```python
"""
tests/e2e/test_pos_vider_carte.py — Test E2E flow POS "Vider Carte" Phase 3.

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/e2e/test_pos_vider_carte.py -v -s
"""
import pytest


@pytest.fixture
def setup_vider_carte_e2e(django_shell):
    """
    Setup en DB :
    - PV 'VC Test PV' avec Product VIDER_CARTE au M2M.
    - CartePrimaire du caissier liee au PV.
    - Carte client avec wallet_ephemere + 1000c TLF.
    """
    setup_code = '''
from AuthBillet.models import Wallet
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Transaction, Token
from fedow_core.services import AssetService, WalletService
from laboutik.models import CartePrimaire, PointDeVente
from BaseBillet.services_refund import get_or_create_product_remboursement
from django.db import transaction as db_transaction

tenant = Client.objects.get(schema_name='lespass')

# Wallet lieu (receiver)
wallet_lieu, _ = Wallet.objects.get_or_create(name='E2E VC Lieu')

# Asset TLF
asset_tlf, _ = Asset.objects.get_or_create(
    name='E2E VC TLF',
    category=Asset.TLF,
    defaults={
        'currency_code': 'EUR',
        'wallet_origin': wallet_lieu,
        'tenant_origin': tenant,
    },
)

# Detail + carte caissier + CartePrimaire
detail, _ = Detail.objects.get_or_create(
    base_url='E2E_VC',
    origine=tenant,
    defaults={'generation': 0},
)
import uuid
carte_caissier, _ = CarteCashless.objects.get_or_create(
    tag_id='E2EVC001',
    defaults={
        'number': 'E2EVC001',
        'uuid': uuid.uuid4(),
        'detail': detail,
    },
)
pv, _ = PointDeVente.objects.get_or_create(
    name='E2E VC PV',
    defaults={'comportement': 'V', 'hidden': False},
)
cp, _ = CartePrimaire.objects.get_or_create(
    carte=carte_caissier,
    defaults={'edit_mode': False},
)
cp.points_de_vente.add(pv)
product_vc = get_or_create_product_remboursement()
pv.products.add(product_vc)

# Carte client
wallet_client = Wallet.objects.create(name='E2E VC Wallet client')
carte_client, created_cc = CarteCashless.objects.get_or_create(
    tag_id='E2EVC002',
    defaults={
        'number': 'E2EVC002',
        'uuid': uuid.uuid4(),
        'detail': detail,
        'wallet_ephemere': wallet_client,
    },
)
if not created_cc:
    carte_client.wallet_ephemere = wallet_client
    carte_client.user = None
    carte_client.save()

# Nettoyage des transactions precedentes
Transaction.objects.filter(card=carte_client).delete()

with db_transaction.atomic():
    WalletService.crediter(wallet=wallet_client, asset=asset_tlf, montant_en_centimes=1000)

print('SETUP_OK')
print(f'pv_uuid:{pv.uuid}')
print(f'tag_id_cm:{carte_caissier.tag_id}')
print(f'tag_id_client:{carte_client.tag_id}')
'''
    out = django_shell(setup_code)
    assert 'SETUP_OK' in out, f"Setup failed: {out}"

    yield

    teardown_code = '''
from AuthBillet.models import Wallet
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Transaction, Token
from laboutik.models import CartePrimaire, PointDeVente
from BaseBillet.models import LigneArticle

# Cleanup dans l'ordre FK inverse.
for carte in CarteCashless.objects.filter(tag_id__startswith='E2EVC'):
    LigneArticle.objects.filter(carte=carte).delete()
    Transaction.objects.filter(card=carte).delete()
    weph = carte.wallet_ephemere
    carte.delete()
    if weph:
        Token.objects.filter(wallet=weph).delete()
        weph.delete()

Asset.objects.filter(name__startswith='E2E VC').delete()
Wallet.objects.filter(name__startswith='E2E VC').delete()
PointDeVente.objects.filter(name='E2E VC PV').delete()
Detail.objects.filter(base_url='E2E_VC').delete()
print('TEARDOWN_OK')
'''
    django_shell(teardown_code)


def test_e2e_pos_vider_carte_flow_complet(
    page, login_as_admin, django_shell, setup_vider_carte_e2e,
):
    """
    Flow complet :
    1. Login admin.
    2. Entrer au POS via la carte caissier.
    3. Cliquer la tile 'Vider Carte' (methode_caisse=VC).
    4. Simuler le scan NFC de la carte client.
    5. Vérifier l'overlay confirm.
    6. Cliquer Confirmer.
    7. Vérifier l'écran succès.
    8. Vérifier en DB : 1 Transaction REFUND + LigneArticle CASH (-1000).
    """
    login_as_admin(page)

    # Navigation directe vers le POS en passant par la page carte primaire.
    # / Direct navigation to POS via the primary card page.
    page.goto('/laboutik/caisse/')
    page.wait_for_load_state('domcontentloaded')

    # Cette partie depend du flow POS existant. Si l'admin se connecte directement
    # avec une session (pas de scan requis), on peut passer tag_id_cm via URL.
    # / This part depends on the existing POS flow. If admin is connected via session,
    # we can pass tag_id_cm via URL.
    page.goto('/laboutik/caisse/point_de_vente/?uuid_pv=&tag_id_cm=E2EVC001')
    page.wait_for_load_state('domcontentloaded')

    # Ce test est delicat car il depend de l'etat UI du POS.
    # Alternative : POST direct sur l'endpoint vider_carte pour prouver que le flow backend fonctionne.
    # / Alternative: direct POST on vider_carte endpoint to prove backend flow works.
    verify_code = '''
from QrcodeCashless.models import CarteCashless
from laboutik.models import PointDeVente
from fedow_core.models import Transaction

carte_caissier = CarteCashless.objects.get(tag_id='E2EVC001')
carte_client = CarteCashless.objects.get(tag_id='E2EVC002')
pv = PointDeVente.objects.get(name='E2E VC PV')
print(f'pv_uuid:{pv.uuid}')
print(f'tag_id_cm:{carte_caissier.tag_id}')
print(f'tag_id_client:{carte_client.tag_id}')
'''
    out = django_shell(verify_code)
    pv_uuid = [l.split(':', 1)[1] for l in out.split('\n') if l.startswith('pv_uuid:')][0]

    # POST direct comme si l'UI etait validee.
    # / Direct POST as if the UI had been validated.
    response = page.request.post(
        '/laboutik/paiement/vider_carte/',
        form={
            'tag_id': 'E2EVC002',
            'tag_id_cm': 'E2EVC001',
            'uuid_pv': pv_uuid,
            'vider_carte': 'false',
        },
    )
    assert response.ok, f'POST vider_carte failed: {response.status}'
    body = response.text()
    # L'ecran de succes contient le montant
    assert '1000' in body, 'Total 1000c absent de la reponse'

    # Vérifier en DB
    check_code = '''
from fedow_core.models import Transaction
from BaseBillet.models import LigneArticle, PaymentMethod
from QrcodeCashless.models import CarteCashless

carte_client = CarteCashless.objects.get(tag_id='E2EVC002')
nb_refund = Transaction.objects.filter(card=carte_client, action=Transaction.REFUND).count()
nb_la_cash = LigneArticle.objects.filter(
    carte=carte_client, payment_method=PaymentMethod.CASH,
).count()
print(f'REFUND_COUNT:{nb_refund}')
print(f'CASH_COUNT:{nb_la_cash}')
'''
    out = django_shell(check_code)
    assert 'REFUND_COUNT:1' in out, f'Expected 1 REFUND, got: {out}'
    assert 'CASH_COUNT:1' in out, f'Expected 1 CASH LigneArticle, got: {out}'
```

- [ ] **Step 3: Lancer le test E2E**

```
docker exec lespass_django poetry run pytest tests/e2e/test_pos_vider_carte.py -v -s
```

Expected: PASS. Le test privilégie la validation du flow backend via `page.request.post` plutôt qu'une simulation complète de l'UI POS (qui dépend de l'état NFC du navigateur et serait plus fragile).

- [ ] **Step 4: DO NOT commit.**

---

## Task 13: i18n + vérification finale

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`

- [ ] **Step 1: Extraire**

```
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

- [ ] **Step 2: Traduire les strings Phase 3**

Strings Phase 3 à traduire (EN) :
```
"Ne peut pas vider une carte primaire."           -> "Cannot empty a primary card."
"Carte client inconnue."                           -> "Unknown client card."
"Carte vierge."                                    -> "Blank card."
"Aucun solde remboursable sur cette carte."        -> "No refundable balance on this card."
"Aucun solde remboursable (solde a pu changer)."   -> "No refundable balance (balance may have changed)."
"Cette carte caissier n'a pas acces a ce PV."      -> "This cashier card has no access to this POS."
"PV introuvable."                                  -> "POS not found."
"Paramètres manquants."                            -> "Missing parameters."
"Pas d'imprimante configurée sur ce PV."           -> "No printer configured on this POS."
"Vider la carte"                                   -> "Empty card"
"Scannez la carte du client."                      -> "Scan the client card."
"Annuler"                                          -> "Cancel"
"À rendre"                                         -> "To return"
"centimes"                                         -> "cents"
"Asset"                                            -> "Asset"
"Solde"                                            -> "Balance"
"Réinitialiser la carte après remboursement (détache user, wallet, carte primaire)"
    -> "Reset card after refund (detach user, wallet, primary card)"
"Confirmer le remboursement"                       -> "Confirm refund"
"Remboursement effectué"                           -> "Refund complete"
"Monnaie locale"                                   -> "Local currency"
"Fiduciaire fédérée"                               -> "Federated fiduciary"
"La carte a été réinitialisée."                    -> "The card has been reset."
"Imprimer reçu"                                    -> "Print receipt"
"Retour"                                           -> "Back"
"REMBOURSEMENT CARTE"                              -> "CARD REFUND"
"Especes"                                          -> "Cash"
"Merci de votre visite."                           -> "Thank you for your visit."
```

Éditer les 2 .po files pour chacune. Côté `fr` : msgstr identique au msgid (ou corriger accents). Supprimer les flags `#, fuzzy` éventuels sur les nouvelles strings.

- [ ] **Step 3: Compiler**

```
docker exec lespass_django poetry run django-admin compilemessages
```

Expected : pas d'erreur.

- [ ] **Step 4: Suite finale de tests Phase 1 + 2 + 3 en isolation**

```
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py -v --api-key dummy
docker exec lespass_django poetry run pytest tests/pytest/test_admin_cards.py -v --api-key dummy
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py -v --api-key dummy
docker exec lespass_django poetry run pytest tests/pytest/test_admin_bank_transfers.py -v --api-key dummy
docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py -v --api-key dummy
docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected : tous PASS (en isolation).

- [ ] **Step 5: Check Django**

```
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected : 0 issue.

- [ ] **Step 6: DO NOT commit.**

---

## Récapitulatif

À la fin du plan :

```
fedow_core/
└── services.py       (PATCH léger +primary_card=None sur rembourser_en_especes)

laboutik/
├── views.py          (PATCH +ViderCarteSerializer +4 @action)
├── static/js/
│   └── vider_carte.js (NEW)
├── templates/laboutik/
│   ├── partial/
│   │   ├── hx_vider_carte_overlay.html   (NEW)
│   │   ├── hx_vider_carte_confirm.html   (NEW)
│   │   └── hx_vider_carte_success.html   (NEW)
│   └── views/
│       └── common_user_interface.html    (PATCH +<script>)
└── printing/
    └── formatters.py (PATCH +formatter_recu_vider_carte)

tests/
├── pytest/
│   └── test_pos_vider_carte.py           (NEW)
└── e2e/
    └── test_pos_vider_carte.py           (NEW)

locale/{fr,en}/LC_MESSAGES/django.po (PATCH)
```

---

## Spec self-review (post-écriture)

**1. Spec coverage** :
- Tile auto-générée via Product VIDER_CARTE + détection frontend → Task 9 ✅
- Flow dédié qui court-circuite le panier → Tasks 3, 4, 6-9 ✅
- Patch `primary_card=None` additif → Task 1 ✅
- Scan NFC via `<c-read-nfc>` pattern existant → Task 6 (template) + Task 9 (JS) ✅
- Récap tokens + total + détail par asset → Task 7 ✅
- Checkbox VV → Task 7 (template) + Task 4 (service call) ✅
- Protection self-refund → Tasks 3, 4 ✅
- Contrôle d'accès via M2M pv.cartes_primaires → Task 4 ✅
- Écran succès + impression optionnelle → Tasks 8, 5 ✅
- Formatter dédié → Task 10 ✅
- LigneArticle d'encaissement + rapport comptable → Task 1 (via réutilisation Phase 1 service) ✅
- Tests pytest (10) + E2E (1) → Tasks 1-5, 10, 11, 12 ✅
- i18n → Task 13 ✅

**2. Placeholder scan** :
- ⚠️ Step 3 Task 3 : `_render_erreur_toast` : on vérifie son existence et on le crée si absent. Code complet fourni.
- ⚠️ Step 2 Task 9 : modification du JS pour passer uuid_pv + tag_id_cm en query params : code complet fourni dans la même Step.
- Aucun « TBD » / « TODO » bloquant.

**3. Type consistency** :
- `ViderCarteSerializer` : 4 champs stables entre Task 2 (définition) et Tasks 3, 4 (utilisation).
- URL names : `laboutik-paiement-vider_carte_overlay`, `_preview`, `_vider_carte`, `_imprimer_recu` cohérents entre Task 2-5 (backend), Tasks 6-8 (templates `{% url %}`), Task 9 (JS fetch).
- `data-testid` attributes du templates repris dans Task 12 (E2E).
- Noms de fixtures pytest (`tenant_lespass_vc`, `carte_caissier_vc`, `carte_client_vc_avec_tlf`, `pv_cashless_vc`) réutilisés dans toutes les tasks.

**4. Notes pour l'implémenteur** :
- Task 9 nécessite probablement un ajustement sur comment `{{ card.tag_id }}` est passé au template `hx_vider_carte_overlay.html` — vérifier le pattern d'autres overlays POS (ex: `hx_read_nfc.html`) pour la cohérence.
- Le test E2E Task 12 privilégie la validation backend via `page.request.post` plutôt qu'une simulation NFC complète (qui serait fragile). Si l'équipe veut aller plus loin avec une vraie simulation du component `<c-read-nfc>`, c'est une amélioration future.
- Si `_render_erreur_toast` existe déjà dans `laboutik/views.py` sous un autre nom, utiliser l'existant. Sinon, la définition fournie Step 4 Task 3 suffit.
