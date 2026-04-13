# Phase 1 — Admin web cartes NFC + remboursement en espèces — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer un admin web Unfold pour `CarteCashless` et `Detail`, avec une page dédiée de remboursement en espèces (TLF du tenant + FED) qui crée Transactions REFUND + LigneArticles, plus un nettoyage du code mort dans `admin_root.py`.

**Architecture:** Service métier `WalletService.rembourser_en_especes()` dans `fedow_core/services.py` (réutilisable par le POS Phase 3). Helpers Product/PriceSold partagés dans `BaseBillet/services_refund.py`. Admin Unfold avec URLs custom via `get_urls()`. ViewSet DRF pour le flow remboursement (FALC patterns `/djc`).

**Tech Stack:** Django 5.x, django-tenants, Django Unfold (admin), DRF (ViewSet + serializers), HTMX, pytest, Playwright Python.

**Spec source:** `TECH DOC/SESSIONS/CARTES_CASHLESS_ADMIN/2026-04-13-phase1-admin-cartes-design.md`

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `fedow_core/exceptions.py` | PATCH | +`NoEligibleTokens` |
| `fedow_core/services.py` | PATCH | +`WalletService.rembourser_en_especes()` |
| `fedow_core/REFUND.md` | NEW | Doc mécanisme remboursement TLF + FED + roadmap dette pot central |
| `BaseBillet/services_refund.py` | NEW | `get_or_create_product_remboursement()`, `get_or_create_pricesold_refund()` |
| `Administration/serializers.py` | NEW | `CardRefundConfirmSerializer` |
| `Administration/views_cards.py` | NEW | `CardRefundViewSet(viewsets.ViewSet)` |
| `Administration/admin/cards.py` | NEW | `CarteCashlessAdmin` + `DetailAdmin` + `get_urls()` |
| `Administration/admin_tenant.py` | PATCH | `from Administration.admin import cards  # noqa` |
| `Administration/admin/dashboard.py` | PATCH | +2 items dans la section Fedow |
| `Administration/admin_root.py` | PATCH | Commenter le code restant + bandeau d'en-tête |
| `Administration/templates/admin/cards/refund.html` | NEW | Page Unfold avec formulaire HTMX |
| `tests/pytest/test_card_refund_service.py` | NEW | Tests unitaires `WalletService.rembourser_en_especes()` |
| `tests/pytest/test_admin_cards.py` | NEW | Tests permissions + filter `CarteCashlessAdmin` |
| `tests/e2e/test_admin_card_refund.py` | NEW | Test E2E Playwright bout en bout |

---

## Préambule — Démarrage du serveur dev

Démarrage du serveur Django dans le conteneur (à faire une fois en début de session) :

```bash
docker exec -d lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

Pour suivre les logs en temps réel pendant l'implémentation :
```bash
tail -f /tmp/claude-1000/-home-jonas-TiBillet-dev-Lespass/tasks/<task_id>.output
```

---

## Task 1: Exception `NoEligibleTokens`

**Files:**
- Modify: `fedow_core/exceptions.py`
- Test: `tests/pytest/test_card_refund_service.py` (création initiale)

- [ ] **Step 1: Lire le fichier exceptions.py existant**

```bash
cat /home/jonas/TiBillet/dev/Lespass/fedow_core/exceptions.py
```

Expected: voir la classe `SoldeInsuffisant` existante comme modèle de style.

- [ ] **Step 2: Créer le test qui vérifie l'exception**

Créer `tests/pytest/test_card_refund_service.py` :

```python
"""
tests/pytest/test_card_refund_service.py — Tests unitaires WalletService.rembourser_en_especes (Phase 1).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py -v --api-key dummy
"""
import pytest
from django.utils.translation import gettext_lazy as _

from fedow_core.exceptions import NoEligibleTokens


def test_no_eligible_tokens_exception_message():
    """
    Verifie que l'exception NoEligibleTokens porte un message explicite
    et que str(exc) renvoie ce message.
    / Verifies NoEligibleTokens carries an explicit message.
    """
    exc = NoEligibleTokens(carte_tag_id="ABCD1234")
    assert "ABCD1234" in str(exc)
```

- [ ] **Step 3: Lancer le test pour confirmer l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py::test_no_eligible_tokens_exception_message -v --api-key dummy
```

Expected: FAIL avec `ImportError: cannot import name 'NoEligibleTokens'`.

- [ ] **Step 4: Ajouter l'exception dans `fedow_core/exceptions.py`**

Ajouter à la fin du fichier :

```python
class NoEligibleTokens(Exception):
    """
    Levee quand une carte n'a aucun token eligible au remboursement.
    Raised when a card has no eligible tokens for refund.

    Tokens eligibles = TLF dont asset.tenant_origin == tenant courant + FED.
    Cas typiques : carte vierge, solde 0, ou tokens uniquement en categories
    non remboursables (TNF, TIM, FID).
    """

    def __init__(self, carte_tag_id: str = ""):
        self.carte_tag_id = carte_tag_id
        message = _(
            "Aucun solde remboursable sur la carte {tag_id}."
        ).format(tag_id=carte_tag_id)
        super().__init__(message)
```

- [ ] **Step 5: Lancer le test pour vérifier le passage**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py::test_no_eligible_tokens_exception_message -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 6: Vérifier qu'aucun test existant n'est cassé**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected: tous les tests existants passent.

- [ ] **Step 7: Commit**

```bash
git add fedow_core/exceptions.py tests/pytest/test_card_refund_service.py
git commit -m "feat(fedow_core): add NoEligibleTokens exception for card refund flow"
```

---

## Task 2: Helpers Product & PriceSold partagés (`BaseBillet/services_refund.py`)

**Files:**
- Create: `BaseBillet/services_refund.py`
- Test: `tests/pytest/test_card_refund_service.py` (ajout)

- [ ] **Step 1: Vérifier les modèles Product / ProductSold / PriceSold**

```bash
docker exec lespass_django poetry run python -c "from BaseBillet.models import Product, ProductSold, PriceSold; print(Product.VIDER_CARTE)"
```

Expected: `VC`.

- [ ] **Step 2: Ajouter les tests dans `tests/pytest/test_card_refund_service.py`**

Ajouter à la fin du fichier après le test précédent :

```python
from decimal import Decimal
from django.db import connection
from django_tenants.utils import schema_context

from BaseBillet.models import Product, ProductSold, PriceSold
from BaseBillet.services_refund import (
    get_or_create_product_remboursement,
    get_or_create_pricesold_refund,
)


def test_get_or_create_product_remboursement_creates_once():
    """
    Premier appel cree le Product systeme, deuxieme appel le reutilise.
    First call creates the system Product, second call reuses it.
    """
    with schema_context('lespass'):
        # Nettoyage prealable au cas ou le test a deja tourne
        Product.objects.filter(
            methode_caisse=Product.VIDER_CARTE,
            name__startswith="[refund_test]",
        ).delete()

        product_a = get_or_create_product_remboursement()
        product_b = get_or_create_product_remboursement()

        assert product_a.pk == product_b.pk
        assert product_a.methode_caisse == Product.VIDER_CARTE


def test_get_or_create_pricesold_refund_creates_once():
    """
    Le PriceSold de remboursement est unique et reutilisable.
    Refund PriceSold is unique and reusable.
    """
    with schema_context('lespass'):
        product = get_or_create_product_remboursement()
        ps_a = get_or_create_pricesold_refund(product)
        ps_b = get_or_create_pricesold_refund(product)
        assert ps_a.pk == ps_b.pk
        assert ps_a.productsold.product.pk == product.pk
```

- [ ] **Step 3: Lancer les tests pour confirmer l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py::test_get_or_create_product_remboursement_creates_once -v --api-key dummy
```

Expected: FAIL avec `ImportError: cannot import name 'get_or_create_product_remboursement'`.

- [ ] **Step 4: Créer `BaseBillet/services_refund.py`**

```python
"""
BaseBillet/services_refund.py — Helpers partages pour les remboursements de cartes.
BaseBillet/services_refund.py — Shared helpers for card refunds.

Utilise par :
- Administration/views_cards.py (admin web, Phase 1)
- laboutik/views.py (POS Cashless, Phase 3)

Le Product systeme "Remboursement carte" et son PriceSold associe sont crees
a la demande au premier appel, puis reutilises pour toutes les LigneArticle
de remboursement (TLF + FED + sortie cash).
"""
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from BaseBillet.models import Price, PriceSold, Product, ProductSold


def get_or_create_product_remboursement() -> Product:
    """
    Retourne le Product systeme "Remboursement carte" du tenant courant.
    Returns the system Product "Card refund" for the current tenant.

    Cree le Product la premiere fois, le reutilise ensuite.
    Identifie par methode_caisse=VIDER_CARTE (un seul par tenant).

    Created on first call, reused thereafter.
    Identified by methode_caisse=VIDER_CARTE (one per tenant).
    """
    product = Product.objects.filter(
        methode_caisse=Product.VIDER_CARTE,
    ).first()
    if product is not None:
        return product

    product = Product.objects.create(
        name=str(_("Remboursement carte")),
        methode_caisse=Product.VIDER_CARTE,
        publish=False,
    )
    return product


def get_or_create_pricesold_refund(product: Product) -> PriceSold:
    """
    Retourne le PriceSold systeme associe au Product de remboursement.
    Returns the system PriceSold associated with the refund Product.

    Cree un Price a 0 et un PriceSold a 0 si necessaire (le montant reel
    est porte par LigneArticle.amount).

    Creates a Price at 0 and a PriceSold at 0 if needed (real amount carried
    by LigneArticle.amount).
    """
    # Price systeme partage : nom fixe "Refund", prix=0 (montant reel sur LigneArticle)
    # / Shared system Price: fixed name "Refund", prix=0 (real amount on LigneArticle)
    price, _created_price = Price.objects.get_or_create(
        product=product,
        name="Refund",
        defaults={"prix": Decimal(0)},
    )

    productsold, _created_ps = ProductSold.objects.get_or_create(
        product=product,
        event=None,
        defaults={"categorie_article": product.categorie_article},
    )

    pricesold, _created_pxs = PriceSold.objects.get_or_create(
        productsold=productsold,
        price=price,
        defaults={"prix": Decimal(0)},
    )
    return pricesold
```

- [ ] **Step 5: Lancer les tests pour vérifier le passage**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py::test_get_or_create_product_remboursement_creates_once tests/pytest/test_card_refund_service.py::test_get_or_create_pricesold_refund_creates_once -v --api-key dummy
```

Expected: 2 PASS.

- [ ] **Step 6: Lancer un check Django**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 7: Commit**

```bash
git add BaseBillet/services_refund.py tests/pytest/test_card_refund_service.py
git commit -m "feat(BaseBillet): add shared refund Product/PriceSold helpers"
```

---

## Task 3: Service `WalletService.rembourser_en_especes()`

**Files:**
- Modify: `fedow_core/services.py`
- Test: `tests/pytest/test_card_refund_service.py` (ajout)

- [ ] **Step 1: Ajouter les fixtures et le 1er test (TLF seul)**

Ajouter en haut du fichier `tests/pytest/test_card_refund_service.py`, après les imports :

```python
import uuid as uuid_module
from django.db import connection, transaction as db_transaction
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import Wallet
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, TransactionService, WalletService

REFUND_TEST_PREFIX = '[refund_test]'


@pytest.fixture(scope="module")
def tenant_lespass():
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="module")
def wallet_lieu_lespass(tenant_lespass):
    """Wallet du lieu lespass (recepteur des refunds)."""
    wallet = Wallet.objects.create(name=f'{REFUND_TEST_PREFIX} Lieu Lespass')
    # On rattache ce wallet comme tenant.wallet de fait : on le retournera
    # via une fixture dediee plutot que de muter Client (qui n'a pas de FK wallet).
    return wallet


@pytest.fixture(scope="module")
def asset_tlf_lespass(tenant_lespass, wallet_lieu_lespass):
    return AssetService.creer_asset(
        tenant=tenant_lespass,
        name=f'{REFUND_TEST_PREFIX} TLF Lespass',
        category=Asset.TLF,
        currency_code='EUR',
        wallet_origin=wallet_lieu_lespass,
    )


@pytest.fixture(scope="module")
def asset_fed_unique(tenant_lespass, wallet_lieu_lespass):
    """L'asset FED unique du systeme (decision projet : 1 seul FED)."""
    existing = Asset.objects.filter(category=Asset.FED).first()
    if existing is not None:
        return existing
    return AssetService.creer_asset(
        tenant=tenant_lespass,
        name=f'{REFUND_TEST_PREFIX} FED',
        category=Asset.FED,
        currency_code='EUR',
        wallet_origin=wallet_lieu_lespass,
    )


@pytest.fixture
def carte_avec_solde_tlf(tenant_lespass, asset_tlf_lespass):
    """Carte identifiee avec un wallet user et 1000 centimes TLF."""
    with schema_context('lespass'):
        # Detail rattache au tenant lespass
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{REFUND_TEST_PREFIX}_TEST',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        wallet_user = Wallet.objects.create(
            name=f'{REFUND_TEST_PREFIX} Wallet user TLF',
        )
        # Carte sans user : on attache le wallet via wallet_ephemere (anonyme)
        carte = CarteCashless.objects.create(
            tag_id='RFT00001',
            number='RFT00001',
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_user,
        )
        # Crediter le wallet
        with db_transaction.atomic():
            WalletService.crediter(
                wallet=wallet_user,
                asset=asset_tlf_lespass,
                montant_en_centimes=1000,
            )
        yield carte
        # Cleanup
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet=wallet_user).delete()
        carte.delete()
        wallet_user.delete()


def test_rembourser_carte_avec_user_tlf_seul(
    tenant_lespass, wallet_lieu_lespass, asset_tlf_lespass, carte_avec_solde_tlf,
):
    """
    Carte avec 1000 centimes TLF (origine lespass) -> 1 Transaction REFUND
    + 1 LigneArticle CASH negative de -1000.
    Le solde est mis a 0.
    / Card with 1000c TLF (lespass origin) -> 1 REFUND tx + 1 CASH LigneArticle.
    Balance set to 0.
    """
    # On doit injecter wallet_lieu_lespass comme "tenant.wallet". Notre service
    # reel doit accepter explicitement le wallet receveur. Pour le test, on
    # appelle directement le service avec ce wallet.
    with tenant_context(tenant_lespass):
        from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
        resultat = WalletService.rembourser_en_especes(
            carte=carte_avec_solde_tlf,
            tenant=tenant_lespass,
            receiver_wallet=wallet_lieu_lespass,
            ip="127.0.0.1",
            vider_carte=False,
        )

        assert resultat["total_centimes"] == 1000
        assert resultat["total_tlf_centimes"] == 1000
        assert resultat["total_fed_centimes"] == 0
        assert len(resultat["transactions"]) == 1

        # Verifier le solde
        wallet_user = carte_avec_solde_tlf.wallet_ephemere
        solde = WalletService.obtenir_solde(
            wallet=wallet_user, asset=asset_tlf_lespass,
        )
        assert solde == 0

        # Verifier les LigneArticle
        lignes_cash = LigneArticle.objects.filter(
            carte=carte_avec_solde_tlf,
            payment_method=PaymentMethod.CASH,
            sale_origin=SaleOrigin.ADMIN,
        )
        assert lignes_cash.count() == 1
        assert lignes_cash.first().amount == -1000

        # Pas de LigneArticle FED (pas de solde FED)
        lignes_fed = LigneArticle.objects.filter(
            carte=carte_avec_solde_tlf,
            payment_method=PaymentMethod.STRIPE_FED,
        )
        assert lignes_fed.count() == 0
```

- [ ] **Step 2: Lancer le test pour confirmer l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py::test_rembourser_carte_avec_user_tlf_seul -v --api-key dummy
```

Expected: FAIL avec `AttributeError: type object 'WalletService' has no attribute 'rembourser_en_especes'`.

- [ ] **Step 3: Implémenter `WalletService.rembourser_en_especes()` dans `fedow_core/services.py`**

Ajouter dans la classe `WalletService`, après `debiter()` :

```python
    @staticmethod
    def rembourser_en_especes(
        carte,
        tenant,
        receiver_wallet,
        ip: str = "0.0.0.0",
        vider_carte: bool = False,
    ) -> dict:
        """
        Rembourse en especes les tokens eligibles d'une carte.
        Refunds in cash the eligible tokens of a card.

        Tokens eligibles / Eligible tokens :
        - TLF avec asset.tenant_origin == tenant
        - FED (toutes valeurs, sans filtre origine — un seul FED dans le systeme)

        Cree :
        - 1 Transaction(action=REFUND, sender=wallet_carte, receiver=receiver_wallet) par asset
        - 1 LigneArticle FED (encaissement positif STRIPE_FED) si solde FED > 0
        - 1 LigneArticle CASH negative (sortie cash totale TLF + FED)
        - Si vider_carte=True : carte.user=None, carte.wallet_ephemere=None,
          CartePrimaire.objects.filter(carte=carte).delete()

        Tout dans un seul transaction.atomic().
        All in a single transaction.atomic() block.

        :param carte: CarteCashless (la carte a vider / the card to empty)
        :param tenant: Client (le tenant courant / the current tenant)
        :param receiver_wallet: Wallet (le wallet receveur des REFUND, generalement le wallet du lieu)
        :param ip: str (adresse IP de la requete / request IP)
        :param vider_carte: bool (si True, reset user + wallet_ephemere + CartePrimaire)

        :return: dict {
            "transactions": list[Transaction],
            "lignes_articles": list[LigneArticle],
            "total_centimes": int,
            "total_tlf_centimes": int,
            "total_fed_centimes": int,
        }
        :raises NoEligibleTokens: si aucun token eligible n'a value > 0
        """
        # Imports locaux pour eviter le cycle (BaseBillet est en TENANT_APPS)
        # / Local imports to avoid cycle (BaseBillet is in TENANT_APPS)
        from django.db.models import Q
        from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
        from BaseBillet.services_refund import (
            get_or_create_product_remboursement,
            get_or_create_pricesold_refund,
        )
        from fedow_core.exceptions import NoEligibleTokens

        # 1. Charger le wallet de la carte
        # / 1. Load the card's wallet
        wallet_carte = None
        if carte.user is not None and carte.user.wallet is not None:
            wallet_carte = carte.user.wallet
        elif carte.wallet_ephemere is not None:
            wallet_carte = carte.wallet_ephemere

        if wallet_carte is None:
            raise NoEligibleTokens(carte_tag_id=carte.tag_id)

        # 2. Filtrer les tokens eligibles : TLF du tenant + FED
        # / 2. Filter eligible tokens: tenant's TLF + FED
        tokens_eligibles = list(
            Token.objects.filter(
                wallet=wallet_carte,
                value__gt=0,
            ).filter(
                Q(asset__category=Asset.TLF, asset__tenant_origin=tenant)
                | Q(asset__category=Asset.FED)
            ).select_related('asset', 'asset__tenant_origin')
        )

        if not tokens_eligibles:
            raise NoEligibleTokens(carte_tag_id=carte.tag_id)

        # 3. Atomic : transactions REFUND + LigneArticle + reset eventuel
        # / 3. Atomic: REFUND transactions + LigneArticle + optional reset
        transactions_creees = []
        total_tlf = 0
        total_fed = 0

        with transaction.atomic():
            for token in tokens_eligibles:
                tx = TransactionService.creer(
                    sender=wallet_carte,
                    receiver=receiver_wallet,
                    asset=token.asset,
                    montant_en_centimes=token.value,
                    action=Transaction.REFUND,
                    tenant=tenant,
                    card=carte,
                    ip=ip,
                    comment="Remboursement especes admin",
                    metadata={
                        "vider_carte": vider_carte,
                    },
                )
                transactions_creees.append(tx)
                if token.asset.category == Asset.TLF:
                    total_tlf += token.value
                elif token.asset.category == Asset.FED:
                    total_fed += token.value

            # 4. Creer les LigneArticle (Product/PriceSold systeme partages)
            # / 4. Create LigneArticle (shared system Product/PriceSold)
            product_refund = get_or_create_product_remboursement()
            pricesold_refund = get_or_create_pricesold_refund(product_refund)

            lignes_creees = []

            if total_fed > 0:
                # Recupere l'asset FED unique
                # / Get the unique FED asset
                fed_asset = Asset.objects.get(category=Asset.FED)
                ligne_fed = LigneArticle.objects.create(
                    pricesold=pricesold_refund,
                    qty=1,
                    amount=total_fed,
                    payment_method=PaymentMethod.STRIPE_FED,
                    status=LigneArticle.VALID,
                    sale_origin=SaleOrigin.ADMIN,
                    carte=carte,
                    wallet=wallet_carte,
                    asset=fed_asset.uuid,
                )
                lignes_creees.append(ligne_fed)

            ligne_cash = LigneArticle.objects.create(
                pricesold=pricesold_refund,
                qty=1,
                amount=-(total_tlf + total_fed),
                payment_method=PaymentMethod.CASH,
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.ADMIN,
                carte=carte,
                wallet=wallet_carte,
            )
            lignes_creees.append(ligne_cash)

            # 5. Reset optionnel de la carte (action VV)
            # / 5. Optional card reset (VV action)
            if vider_carte:
                # Import local : laboutik n'est pas toujours dispo selon le contexte
                # / Local import: laboutik may not be available depending on context
                try:
                    from laboutik.models import CartePrimaire
                    CartePrimaire.objects.filter(carte=carte).delete()
                except ImportError:
                    pass
                carte.user = None
                carte.wallet_ephemere = None
                carte.save(update_fields=["user", "wallet_ephemere"])

        return {
            "transactions": transactions_creees,
            "lignes_articles": lignes_creees,
            "total_centimes": total_tlf + total_fed,
            "total_tlf_centimes": total_tlf,
            "total_fed_centimes": total_fed,
        }
```

- [ ] **Step 4: Lancer le test 1 (TLF seul)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py::test_rembourser_carte_avec_user_tlf_seul -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 5: Ajouter les autres tests (FED seul, TLF+FED, exclusions, vider_carte, NoEligibleTokens)**

Ajouter à `tests/pytest/test_card_refund_service.py` :

```python
@pytest.fixture
def carte_avec_solde_fed(tenant_lespass, asset_fed_unique):
    """Carte anonyme avec wallet_ephemere et 500 centimes FED."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{REFUND_TEST_PREFIX}_TEST',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        wallet_user = Wallet.objects.create(
            name=f'{REFUND_TEST_PREFIX} Wallet user FED',
        )
        carte = CarteCashless.objects.create(
            tag_id='RFT00002',
            number='RFT00002',
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_user,
        )
        with db_transaction.atomic():
            WalletService.crediter(
                wallet=wallet_user, asset=asset_fed_unique, montant_en_centimes=500,
            )
        yield carte
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet=wallet_user).delete()
        carte.delete()
        wallet_user.delete()


def test_rembourser_carte_avec_user_fed_seul(
    tenant_lespass, wallet_lieu_lespass, asset_fed_unique, carte_avec_solde_fed,
):
    """500c FED seul -> 1 LigneArticle FED (+500) + 1 LigneArticle CASH (-500)."""
    with tenant_context(tenant_lespass):
        from BaseBillet.models import LigneArticle, PaymentMethod
        resultat = WalletService.rembourser_en_especes(
            carte=carte_avec_solde_fed,
            tenant=tenant_lespass,
            receiver_wallet=wallet_lieu_lespass,
        )
        assert resultat["total_fed_centimes"] == 500
        assert resultat["total_tlf_centimes"] == 0

        ligne_fed = LigneArticle.objects.filter(
            carte=carte_avec_solde_fed, payment_method=PaymentMethod.STRIPE_FED,
        )
        assert ligne_fed.count() == 1
        assert ligne_fed.first().amount == 500

        ligne_cash = LigneArticle.objects.filter(
            carte=carte_avec_solde_fed, payment_method=PaymentMethod.CASH,
        )
        assert ligne_cash.count() == 1
        assert ligne_cash.first().amount == -500


def test_rembourser_exclut_tnf_tim_fid(tenant_lespass, wallet_lieu_lespass):
    """
    Tokens TNF/TIM/FID sont ignores : rien rembourse, exception levee.
    TNF/TIM/FID tokens ignored: nothing refunded, exception raised.
    """
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{REFUND_TEST_PREFIX}_TEST',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        wallet_eph = Wallet.objects.create(name=f'{REFUND_TEST_PREFIX} TNF only')
        carte = CarteCashless.objects.create(
            tag_id='RFT00003',
            number='RFT00003',
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_eph,
        )
        wallet_origine_tnf = Wallet.objects.create(name=f'{REFUND_TEST_PREFIX} TNF orig')
        asset_tnf = AssetService.creer_asset(
            tenant=tenant_lespass,
            name=f'{REFUND_TEST_PREFIX} TNF cadeau',
            category=Asset.TNF,
            currency_code='EUR',
            wallet_origin=wallet_origine_tnf,
        )
        with db_transaction.atomic():
            WalletService.crediter(wallet=wallet_eph, asset=asset_tnf, montant_en_centimes=300)

        with tenant_context(tenant_lespass):
            from fedow_core.exceptions import NoEligibleTokens
            with pytest.raises(NoEligibleTokens):
                WalletService.rembourser_en_especes(
                    carte=carte,
                    tenant=tenant_lespass,
                    receiver_wallet=wallet_lieu_lespass,
                )

        # Cleanup
        Token.objects.filter(wallet=wallet_eph).delete()
        carte.delete()
        wallet_eph.delete()
        Asset.objects.filter(name=f'{REFUND_TEST_PREFIX} TNF cadeau').delete()
        wallet_origine_tnf.delete()


def test_rembourser_avec_vider_carte_reset(
    tenant_lespass, wallet_lieu_lespass, asset_tlf_lespass, carte_avec_solde_tlf,
):
    """
    vider_carte=True -> carte.user=None, wallet_ephemere=None.
    vider_carte=True -> carte.user=None, wallet_ephemere=None.
    """
    with tenant_context(tenant_lespass):
        WalletService.rembourser_en_especes(
            carte=carte_avec_solde_tlf,
            tenant=tenant_lespass,
            receiver_wallet=wallet_lieu_lespass,
            vider_carte=True,
        )
        carte_avec_solde_tlf.refresh_from_db()
        assert carte_avec_solde_tlf.user is None
        assert carte_avec_solde_tlf.wallet_ephemere is None


def test_rembourser_carte_vide_raise_no_eligible(tenant_lespass, wallet_lieu_lespass):
    """Carte sans wallet -> NoEligibleTokens."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{REFUND_TEST_PREFIX}_TEST',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte_vide = CarteCashless.objects.create(
            tag_id='RFT00004',
            number='RFT00004',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
        with tenant_context(tenant_lespass):
            from fedow_core.exceptions import NoEligibleTokens
            with pytest.raises(NoEligibleTokens):
                WalletService.rembourser_en_especes(
                    carte=carte_vide,
                    tenant=tenant_lespass,
                    receiver_wallet=wallet_lieu_lespass,
                )
        carte_vide.delete()
```

- [ ] **Step 6: Ajouter le cleanup module dans `tests/pytest/test_card_refund_service.py`**

Ajouter à la fin du fichier :

```python
@pytest.fixture(scope="module", autouse=True)
def cleanup_refund_test_data():
    """Nettoyage en fin de module : Detail, LigneArticle, Product systeme."""
    yield
    try:
        with schema_context('lespass'):
            from BaseBillet.models import LigneArticle, Product, PriceSold, ProductSold
            wallets_test = Wallet.objects.filter(name__startswith=REFUND_TEST_PREFIX)
            assets_test = Asset.objects.filter(name__startswith=REFUND_TEST_PREFIX)
            Transaction.objects.filter(asset__in=assets_test).delete()
            Token.objects.filter(wallet__in=wallets_test).delete()
            CarteCashless.objects.filter(tag_id__startswith='RFT').delete()
            Detail.objects.filter(base_url=f'{REFUND_TEST_PREFIX}_TEST').delete()
            assets_test.delete()
            wallets_test.delete()
            # On laisse Product/PriceSold systeme en place : reutilisable au prochain run
    except Exception:
        pass
```

- [ ] **Step 7: Lancer tous les tests refund**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py -v --api-key dummy
```

Expected: tous les tests PASS.

- [ ] **Step 8: Vérifier qu'aucun test fedow_core existant n'est cassé**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add fedow_core/services.py tests/pytest/test_card_refund_service.py
git commit -m "feat(fedow_core): WalletService.rembourser_en_especes for TLF + FED refunds"
```

---

## Task 4: README mécanisme de remboursement (`fedow_core/REFUND.md`)

**Files:**
- Create: `fedow_core/REFUND.md`

- [ ] **Step 1: Créer le fichier**

```markdown
# Mécanisme de remboursement de carte NFC

Document de référence pour le flow « Vider une carte / Remboursement en espèces »
implémenté par `WalletService.rembourser_en_especes()` (`fedow_core/services.py`).

## Vue d'ensemble

Quand une personne veut récupérer son solde en espèces (carte rendue, fin de festival,
remboursement à la demande), le lieu effectue un « refund » qui :

1. Lit les tokens éligibles du wallet de la carte.
2. Crée une `Transaction(action=REFUND)` par asset (transfert wallet_carte → wallet du lieu).
3. Crée des `LigneArticle` comptables qui apparaissent dans les rapports caisse/admin.
4. Optionnellement : réinitialise la carte (action VV — détache user, supprime wallet_ephemere,
   supprime la `CartePrimaire` associée).

## Tokens éligibles

| Catégorie | Éligible ? | Filtre |
|---|---|---|
| TLF — Token Local Fiduciaire | ✅ | `asset.tenant_origin == tenant courant` |
| FED — Fiduciaire Federée | ✅ | aucun filtre origine (1 seul Asset FED dans le système) |
| TNF — Token Local Cadeau | ❌ | non remboursable par nature |
| TIM — Monnaie Temps | ❌ | non monétaire |
| FID — Points de Fidélité | ❌ | non monétaire |

**Règle principale** : un lieu ne rembourse en espèces **que ses propres tokens locaux fiduciaires**
plus la part fédérée Stripe. Pour les TLF d'un autre lieu, le porteur doit aller dans ce lieu.

## Sortie comptable (LigneArticle)

Pour un remboursement de 10€ TLF + 5€ FED, le service crée :

| LigneArticle | `payment_method` | `amount` (centimes) | `sale_origin` | Sens comptable |
|---|---|---|---|---|
| 1 | `STRIPE_FED` | +500 | `ADMIN` | Encaissement de la part fédérée par le lieu |
| 2 | `CASH` | -1500 | `ADMIN` | Sortie de caisse totale |

Le `pricesold` de chaque ligne pointe vers le `Product` système « Remboursement carte »
(`methode_caisse=VC`) créé à la demande par `BaseBillet/services_refund.py`.

Les rapports comptables (caisse, admin tenant) peuvent identifier ces opérations en filtrant :
- `LigneArticle.pricesold.product.methode_caisse == 'VC'` ET `LigneArticle.sale_origin == 'AD'`
- Ou via `LigneArticle.payment_method == CASH AND amount < 0` couplé au product VC.

## Dette du pot central → tenant (FED)

La part FED remboursée à la personne **a été initialement encaissée par le pot central Stripe**
(quand la personne a fait sa recharge). Quand le lieu rend du FED en espèces, le pot central
**doit ce montant au lieu**. Le mécanisme actuel (V1) : virement bancaire du pot central vers
le compte du lieu, à la fin de chaque mois, pour la somme des FED remboursés.

**Phase 2 du chantier mono-repo (à venir)** : nouvelle action `Transaction.BANK_TRANSFER` qui
trace le virement reçu. Le solde de la dette se calcule par requête :

```python
# Dette pot central → tenant pour les FED remboursés
total_refund_fed = Transaction.objects.filter(
    action=Transaction.REFUND,
    asset__category=Asset.FED,
    receiver=tenant.wallet,
).aggregate(Sum('amount'))['amount__sum'] or 0

total_virements_recus = Transaction.objects.filter(
    action=Transaction.BANK_TRANSFER,  # à créer en Phase 2
    asset__category=Asset.FED,
    receiver=tenant.wallet,
).aggregate(Sum('amount'))['amount__sum'] or 0

dette_pot_central = total_refund_fed - total_virements_recus
```

## Action « VV » — Réinitialisation de la carte

Si l'admin coche la case « Réinitialiser la carte » :

```python
CartePrimaire.objects.filter(carte=carte).delete()  # carte ne peut plus être primaire
carte.user = None                                    # détache la personne
carte.wallet_ephemere = None                         # détache le wallet (reste en BDD pour audit)
carte.save(update_fields=["user", "wallet_ephemere"])
```

Cas typique : carte perdue, carte rendue par une personne qui ne reviendra pas, carte récupérée
en fin de festival pour réutilisation.

**Le wallet n'est jamais supprimé** : il reste en base pour conserver l'audit trail des
transactions historiques. Il est juste détaché de la carte.

## Origine du mécanisme

Reproduit le flow legacy V1 :

- **Côté Fedow** : `OLD_REPOS/Fedow/fedow_core/serializers.py:174 CardRefundOrVoidValidator`
  + endpoint `card/refund` (`OLD_REPOS/Fedow/fedow_core/views.py:253`).
- **Côté LaBoutik** : `OLD_REPOS/LaBoutik/webview/views.py:1396 methode_VC` (Vider Carte) et
  `methode_VV` (Void Carte). 2 `ArticleVendu` créés (encaissement FED + sortie CASH du total),
  miroir des `LigneArticle` actuels.

La V2 fait la même chose en accès DB direct (plus de HTTP inter-service), via un service
unique réutilisable par l'admin web (Phase 1) et le POS Cashless (Phase 3).

## Roadmap

| Phase | Périmètre |
|---|---|
| **1** (en cours) | Admin web cartes + page remboursement + service `WalletService.rembourser_en_especes()` |
| **2** | Action `Transaction.BANK_TRANSFER` + suivi de la dette pot central → tenant |
| **3** | Bouton POS Cashless « Vider Carte / Void Carte », utilise le même service |
```

- [ ] **Step 2: Commit**

```bash
git add fedow_core/REFUND.md
git commit -m "docs(fedow_core): add REFUND.md mechanism reference"
```

---

## Task 5: `CardRefundConfirmSerializer` + `CardRefundViewSet`

**Files:**
- Create: `Administration/serializers.py`
- Create: `Administration/views_cards.py`

- [ ] **Step 1: Créer `Administration/serializers.py`**

```python
"""
Administration/serializers.py — DRF serializers pour les vues admin custom.
Administration/serializers.py — DRF serializers for custom admin views.
"""
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _


class CardRefundConfirmSerializer(serializers.Serializer):
    """
    Valide le formulaire POST de confirmation d'un remboursement de carte.
    Validates the POST form for confirming a card refund.

    Champs :
    - vider_carte (bool) : si True, reset user + wallet_ephemere + CartePrimaire (action VV).
    """
    vider_carte = serializers.BooleanField(
        required=False,
        default=False,
        help_text=_("Si coche, reinitialise la carte apres remboursement (VV)."),
    )
```

- [ ] **Step 2: Créer `Administration/views_cards.py`**

```python
"""
Administration/views_cards.py — Vues custom admin pour les cartes NFC.
Administration/views_cards.py — Custom admin views for NFC cards.

Patterns FALC /djc :
- viewsets.ViewSet (NOT ModelViewSet), methodes explicites
- serializers.Serializer pour la validation
- HTML server-rendered (HTMX)
- Permissions : superuser OU admin tenant ET carte du tenant
"""
import logging
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from ApiBillet.permissions import TenantAdminPermissionWithRequest
from Administration.serializers import CardRefundConfirmSerializer
from QrcodeCashless.models import CarteCashless
from fedow_core.exceptions import NoEligibleTokens
from fedow_core.models import Asset, Token
from fedow_core.services import WalletService

logger = logging.getLogger(__name__)


def _check_admin_or_superuser_for_card(request, carte: CarteCashless) -> None:
    """
    Verifie que l'utilisateur peut acceder a cette carte.
    Verifies the user can access this card.

    - Superuser : OK toutes les cartes.
    - Admin tenant : OK seulement si carte.detail.origine == tenant courant.
    """
    if request.user.is_superuser:
        return
    if not TenantAdminPermissionWithRequest(request):
        raise PermissionDenied(_("Acces administrateur requis."))
    if carte.detail is None or carte.detail.origine_id != connection.tenant.pk:
        raise PermissionDenied(
            _("Cette carte n'appartient pas a votre lieu.")
        )


def _wallet_de_la_carte(carte: CarteCashless):
    """Retourne le wallet actif de la carte (user.wallet ou wallet_ephemere)."""
    if carte.user is not None and carte.user.wallet is not None:
        return carte.user.wallet
    return carte.wallet_ephemere


def _tokens_eligibles(wallet, tenant):
    """Tokens eligibles au remboursement : TLF du tenant + FED, value > 0."""
    from django.db.models import Q
    return Token.objects.filter(
        wallet=wallet,
        value__gt=0,
    ).filter(
        Q(asset__category=Asset.TLF, asset__tenant_origin=tenant)
        | Q(asset__category=Asset.FED)
    ).select_related('asset', 'asset__tenant_origin').order_by('asset__category')


def _get_or_create_wallet_lieu(tenant):
    """
    Recupere ou cree le wallet recepteur des refunds pour le tenant.
    Convention : un wallet par tenant, identifie par origin=tenant et name connu.

    NB : a remplacer par tenant.wallet quand la convention sera formalisee.
    """
    from AuthBillet.models import Wallet
    wallet = Wallet.objects.filter(
        origin=tenant,
        name=f"Lieu {tenant.schema_name}",
    ).first()
    if wallet is None:
        wallet = Wallet.objects.create(
            origin=tenant,
            name=f"Lieu {tenant.schema_name}",
        )
    return wallet


class CardRefundViewSet(viewsets.ViewSet):
    """
    Page dediee de remboursement carte (admin web).
    Dedicated card refund page (admin web).

    URLs montees par CarteCashlessAdmin.get_urls() :
    - GET  /admin/QrcodeCashless/cartecashless/<uuid>/refund/         -> retrieve()
    - POST /admin/QrcodeCashless/cartecashless/<uuid>/refund/confirm/ -> confirm()
    """
    permission_classes = [IsAuthenticated]

    def retrieve(self, request, pk=None):
        """GET : affiche le recap des tokens eligibles + formulaire confirmation."""
        carte = get_object_or_404(CarteCashless, uuid=pk)
        _check_admin_or_superuser_for_card(request, carte)

        tenant = connection.tenant
        wallet = _wallet_de_la_carte(carte)

        if wallet is None:
            contexte = {
                "carte": carte,
                "wallet": None,
                "tokens_eligibles": [],
                "total_tlf_centimes": 0,
                "total_fed_centimes": 0,
                "total_centimes": 0,
                "carte_vierge": True,
            }
            return render(request, "admin/cards/refund.html", contexte)

        tokens = list(_tokens_eligibles(wallet, tenant))
        total_tlf = sum(t.value for t in tokens if t.asset.category == Asset.TLF)
        total_fed = sum(t.value for t in tokens if t.asset.category == Asset.FED)

        contexte = {
            "carte": carte,
            "wallet": wallet,
            "tokens_eligibles": tokens,
            "total_tlf_centimes": total_tlf,
            "total_fed_centimes": total_fed,
            "total_centimes": total_tlf + total_fed,
            "carte_vierge": False,
        }
        return render(request, "admin/cards/refund.html", contexte)

    def confirm(self, request, pk=None):
        """POST : execute le remboursement via WalletService."""
        carte = get_object_or_404(CarteCashless, uuid=pk)
        _check_admin_or_superuser_for_card(request, carte)

        serializer = CardRefundConfirmSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)
        vider_carte = serializer.validated_data["vider_carte"]

        tenant = connection.tenant
        receiver_wallet = _get_or_create_wallet_lieu(tenant)

        try:
            resultat = WalletService.rembourser_en_especes(
                carte=carte,
                tenant=tenant,
                receiver_wallet=receiver_wallet,
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                vider_carte=vider_carte,
            )
        except NoEligibleTokens:
            messages.warning(
                request,
                _("Aucun solde remboursable sur cette carte."),
            )
            return redirect(reverse(
                "staff_admin:QrcodeCashless_cartecashless_change",
                args=[carte.uuid],
            ))

        montant_total_euros = resultat["total_centimes"] / 100
        messages.success(
            request,
            _("Remboursement effectue : {amount}EUR").format(
                amount=montant_total_euros,
            ),
        )
        return redirect(reverse(
            "staff_admin:QrcodeCashless_cartecashless_change",
            args=[carte.uuid],
        ))
```

- [ ] **Step 3: Vérifier que les imports passent**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 4: Commit**

```bash
git add Administration/serializers.py Administration/views_cards.py
git commit -m "feat(Administration): CardRefundViewSet + CardRefundConfirmSerializer"
```

---

## Task 6: Template `refund.html`

**Files:**
- Create: `Administration/templates/admin/cards/refund.html`

- [ ] **Step 1: Vérifier que le dossier `templates/admin/cards/` n'existe pas encore**

```bash
ls /home/jonas/TiBillet/dev/Lespass/Administration/templates/admin/cards/ 2>/dev/null
```

Expected: « No such file or directory ».

- [ ] **Step 2: Créer le template**

```html
{% extends "admin/base_site.html" %}
{% load i18n unfold %}

{% block title %}{% translate "Remboursement carte" %} {{ carte.tag_id }}{% endblock %}

{% block extrastyle %}
    {{ block.super }}
    <style>
        .refund-container { padding: 24px; }
        .refund-card { background: var(--color-base-0); border-radius: 8px; padding: 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .refund-table { width: 100%; border-collapse: collapse; margin: 16px 0; }
        .refund-table th, .refund-table td { padding: 12px; text-align: left; border-bottom: 1px solid var(--color-base-200); }
        .refund-table th { background: var(--color-base-100); font-weight: 600; }
        .refund-total { font-size: 1.5rem; font-weight: bold; color: var(--color-primary-600); margin: 16px 0; }
        .btn-confirm { background: #16a34a; color: white; padding: 12px 24px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; }
        .btn-cancel { background: #6b7280; color: white; padding: 12px 24px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
        .alert-info { background: #dbeafe; color: #1e40af; padding: 16px; border-radius: 6px; margin: 16px 0; }
        .alert-warning { background: #fef3c7; color: #92400e; padding: 16px; border-radius: 6px; margin: 16px 0; }
    </style>
{% endblock %}

{% block content %}
<div class="refund-container" data-testid="card-refund-page">
    <h1>{% translate "Remboursement en especes" %} — {{ carte.tag_id }}</h1>

    <div class="refund-card">
        <p><strong>{% translate "Carte" %}:</strong> {{ carte.tag_id }} ({{ carte.number }})</p>
        {% if carte.user %}
            <p><strong>{% translate "Identifiee a" %}:</strong> {{ carte.user.email }}</p>
        {% else %}
            <p><strong>{% translate "Carte anonyme" %}</strong> ({% translate "wallet ephemere" %})</p>
        {% endif %}

        {% if carte_vierge %}
            <div class="alert-info" data-testid="card-refund-empty">
                {% translate "Cette carte n'a jamais ete utilisee. Aucun solde a rembourser." %}
            </div>
            <a href="{% url 'staff_admin:QrcodeCashless_cartecashless_change' carte.uuid %}"
               class="btn-cancel">
                {% translate "Retour a la fiche carte" %}
            </a>
        {% elif total_centimes == 0 %}
            <div class="alert-info" data-testid="card-refund-no-tokens">
                {% translate "Aucun solde remboursable sur cette carte (TLF du lieu ou FED requis)." %}
            </div>
            <a href="{% url 'staff_admin:QrcodeCashless_cartecashless_change' carte.uuid %}"
               class="btn-cancel">
                {% translate "Retour a la fiche carte" %}
            </a>
        {% else %}
            <h2>{% translate "Tokens a rembourser" %}</h2>
            <table class="refund-table" data-testid="refund-tokens-table">
                <thead>
                    <tr>
                        <th>{% translate "Asset" %}</th>
                        <th>{% translate "Categorie" %}</th>
                        <th>{% translate "Solde" %}</th>
                    </tr>
                </thead>
                <tbody>
                    {% for token in tokens_eligibles %}
                    <tr>
                        <td>{{ token.asset.name }}</td>
                        <td>{{ token.asset.get_category_display }}</td>
                        <td>{{ token.value|floatformat:0 }} {% translate "centimes" %}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <div class="refund-total" data-testid="refund-total">
                {% translate "Total a rembourser en especes" %} :
                {{ total_centimes|floatformat:0 }} {% translate "centimes" %}
                ({{ total_centimes|floatformat:0 }}c)
            </div>

            <form method="post"
                  action="{% url 'staff_admin:QrcodeCashless_cartecashless_refund_confirm' carte.uuid %}"
                  data-testid="refund-form">
                {% csrf_token %}
                <p>
                    <label>
                        <input type="checkbox" name="vider_carte" value="true"
                               data-testid="checkbox-vider-carte">
                        {% translate "Reinitialiser la carte (detache user, wallet, carte primaire)" %}
                    </label>
                </p>
                <button type="submit" class="btn-confirm" data-testid="btn-refund-confirm">
                    {% translate "Confirmer le remboursement" %}
                </button>
                <a href="{% url 'staff_admin:QrcodeCashless_cartecashless_change' carte.uuid %}"
                   class="btn-cancel" data-testid="btn-refund-cancel">
                    {% translate "Annuler" %}
                </a>
            </form>
        {% endif %}
    </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Vérifier que le template est trouvé**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from django.template.loader import get_template; get_template('admin/cards/refund.html'); print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add Administration/templates/admin/cards/refund.html
git commit -m "feat(Administration): refund.html template for card refund flow"
```

---

## Task 7: `CarteCashlessAdmin` + `DetailAdmin` + URLs custom

**Files:**
- Create: `Administration/admin/cards.py`
- Modify: `Administration/admin_tenant.py`

- [ ] **Step 1: Créer `Administration/admin/cards.py`**

```python
"""
Administration/admin/cards.py — Admin Unfold pour CarteCashless et Detail.
Administration/admin/cards.py — Unfold admin for CarteCashless and Detail.

Filtre par detail.origine == tenant courant pour les non-superusers.
Creation et suppression reservees aux superusers.
"""
from django.contrib import admin
from django.db import connection
from django.db.models import Count, Q
from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from Administration.admin.site import staff_admin_site
from Administration import views_cards
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from QrcodeCashless.models import CarteCashless, Detail


# ---------------------------------------------------------------------------
# Helpers module-level (jamais dans une classe ModelAdmin Unfold !)
# Module-level helpers (NEVER inside a ModelAdmin class with Unfold!)
# Cf. tests/PIEGES.md "Ne JAMAIS definir de methodes helper dans un ModelAdmin Unfold"
# ---------------------------------------------------------------------------

def _user_link(carte: CarteCashless) -> str:
    if carte.user is None:
        return format_html('<span style="opacity:0.5">{}</span>', _("(anonyme)"))
    return format_html('{}', carte.user.email)


def _detail_origine(carte: CarteCashless) -> str:
    if carte.detail is None or carte.detail.origine is None:
        return "—"
    return carte.detail.origine.name


def _wallet_status(carte: CarteCashless) -> str:
    if carte.user is not None:
        return _("Identifiee")
    if carte.wallet_ephemere is not None:
        return _("Anonyme (ephemere)")
    return _("Vierge")


def _detail_nb_cartes(detail: Detail) -> int:
    return CarteCashless.objects.filter(detail=detail).count()


# ---------------------------------------------------------------------------
# CarteCashlessAdmin
# ---------------------------------------------------------------------------

@admin.register(CarteCashless, site=staff_admin_site)
class CarteCashlessAdmin(ModelAdmin):
    list_display = ("tag_id", "number", "user_link", "detail_origine", "wallet_status")
    search_fields = ("tag_id", "number", "user__email")
    list_filter = ("detail__origine",)
    readonly_fields = ("tag_id", "number", "uuid")

    def user_link(self, obj):
        return _user_link(obj)
    user_link.short_description = _("Utilisateur·ice")

    def detail_origine(self, obj):
        return _detail_origine(obj)
    detail_origine.short_description = _("Lieu d'origine")

    def wallet_status(self, obj):
        return _wallet_status(obj)
    wallet_status.short_description = _("Statut")

    # --- Permissions : 4 methodes obligatoires ---
    # Cf. tests/PIEGES.md "TOUJOURS definir les 4 methodes has_*_permission"
    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # --- Filtre tenant ---
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("user", "detail__origine")
        if request.user.is_superuser:
            return qs
        return qs.filter(detail__origine_id=connection.tenant.pk)

    # --- URLs custom : page de remboursement ---
    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:pk>/refund/",
                self.admin_site.admin_view(
                    views_cards.CardRefundViewSet.as_view({"get": "retrieve"})
                ),
                name="QrcodeCashless_cartecashless_refund",
            ),
            path(
                "<uuid:pk>/refund/confirm/",
                self.admin_site.admin_view(
                    views_cards.CardRefundViewSet.as_view({"post": "confirm"})
                ),
                name="QrcodeCashless_cartecashless_refund_confirm",
            ),
        ]
        return custom_urls + super().get_urls()


# ---------------------------------------------------------------------------
# DetailAdmin
# ---------------------------------------------------------------------------

@admin.register(Detail, site=staff_admin_site)
class DetailAdmin(ModelAdmin):
    list_display = ("slug", "base_url", "origine", "generation", "nb_cartes")
    search_fields = ("slug", "base_url")
    list_filter = ("origine", "generation")
    readonly_fields = ("uuid",)

    def nb_cartes(self, obj):
        return _detail_nb_cartes(obj)
    nb_cartes.short_description = _("Nombre de cartes")

    # --- Permissions ---
    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # --- Filtre tenant ---
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("origine")
        if request.user.is_superuser:
            return qs
        return qs.filter(origine_id=connection.tenant.pk)
```

- [ ] **Step 2: Importer le module dans `Administration/admin_tenant.py`**

Lire le fichier puis ajouter l'import :

```bash
grep -n "from Administration.admin" /home/jonas/TiBillet/dev/Lespass/Administration/admin_tenant.py | head -5
```

Ajouter dans `Administration/admin_tenant.py`, dans la liste des imports `from Administration.admin import ...`, le module `cards`. Si la liste est sous forme :

```python
from Administration.admin.dashboard import (...)
```

ajouter une ligne (style import side-effect) :

```python
from Administration.admin import cards  # noqa: F401
```

(à placer après les autres imports `Administration.admin`).

- [ ] **Step 3: Vérifier le check Django**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue. Si erreur sur `staff_admin:QrcodeCashless_cartecashless_change`, vérifier que l'URL est bien générée par Unfold (changelist + change auto-générées).

- [ ] **Step 4: Vérifier l'admin dans le navigateur**

```bash
docker exec lespass_django poetry run python -c "
from django.urls import reverse
print(reverse('staff_admin:QrcodeCashless_cartecashless_changelist'))
print(reverse('staff_admin:QrcodeCashless_detail_changelist'))
"
```

Expected:
```
/admin/QrcodeCashless/cartecashless/
/admin/QrcodeCashless/detail/
```

- [ ] **Step 5: Commit**

```bash
git add Administration/admin/cards.py Administration/admin_tenant.py
git commit -m "feat(Administration): CarteCashlessAdmin + DetailAdmin with custom refund URL"
```

---

## Task 8: Sidebar items dans la section Fedow

**Files:**
- Modify: `Administration/admin/dashboard.py:308` (fin de la liste `items` de la section Fedow)

- [ ] **Step 1: Lire le contexte exact**

```bash
sed -n '270,315p' /home/jonas/TiBillet/dev/Lespass/Administration/admin/dashboard.py
```

- [ ] **Step 2: Ajouter les 2 items après `Federations`**

Modifier `Administration/admin/dashboard.py`. Trouver le bloc :

```python
                    {
                        "title": _("Federations"),
                        "icon": "hub",
                        "link": reverse_lazy(
                            "staff_admin:fedow_core_federation_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )
```

Insérer **avant** la fermeture `]` (juste après l'item Federations) :

```python
                    {
                        "title": _("Cartes NFC"),
                        "icon": "credit_card",
                        "link": reverse_lazy(
                            "staff_admin:QrcodeCashless_cartecashless_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Lots de cartes"),
                        "icon": "inventory_2",
                        "link": reverse_lazy(
                            "staff_admin:QrcodeCashless_detail_changelist"
                        ),
                        "permission": admin_permission,
                    },
```

- [ ] **Step 3: Check Django**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 4: Commit**

```bash
git add Administration/admin/dashboard.py
git commit -m "feat(Administration): add Cards + Card lots in Fedow sidebar section"
```

---

## Task 9: Cleanup `admin_root.py`

**Files:**
- Modify: `Administration/admin_root.py`

- [ ] **Step 1: Vérifier les lignes encore actives**

```bash
grep -n "^[^#]" /home/jonas/TiBillet/dev/Lespass/Administration/admin_root.py
```

Expected: lignes 1-19 (imports + logger), 205-207 (3 root_admin_site.register).

- [ ] **Step 2: Réécrire le fichier**

Réécrire `Administration/admin_root.py` :

```python
"""
Site admin root historique — DESACTIVE.
Historic root admin site — DISABLED.

Tout l'admin transite par staff_admin_site (Unfold) defini dans
Administration/admin/site.py et enregistre dans Administration/admin/*.py.

Ce fichier est conserve pour reference pendant la migration V1 -> V2.
Toutes les declarations sont commentees ; les imports restent pour
ne pas casser un eventuel import side-effect ailleurs dans le code.

This file is kept for reference during V1 -> V2 migration.
All declarations are commented out; imports stay to avoid breaking
any side-effect import elsewhere in the code.
"""
import logging

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth import login
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
from django.db import connection
from django.utils.translation import gettext_lazy as _
from solo.admin import SingletonModelAdmin

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_client_ip
from Customers.models import Client, Domain
from MetaBillet.models import EventDirectory, ProductDirectory
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tout le code historique de ce fichier est commente.
# Voir Administration/admin/*.py pour l'admin actuel.
# All historical code in this file is commented out.
# See Administration/admin/*.py for the current admin.
# ---------------------------------------------------------------------------

#
# class PublicAdminSite(AdminSite):
#     site_header = "TiBillet Public Admin"
#     site_title = "TiBillet Public Admin"
#     site_url = '/'
#
#     def has_permission(self, request):
#         logger.warning(
#             f"Tenant AdminSite.has_permission : {request.user} - {request.user.client_source if request.user.is_authenticated else 'No client source'} - ip : {get_client_ip(request)}")
#
#         try:
#             if request.user.client_source.categorie == Client.ROOT:
#                 return request.user.is_superuser
#         except AttributeError as e:
#             logger.warning(f"{e} : AnonymousUser for admin ?")
#             return False
#         except Exception as e:
#             raise e
#         return False
#
# root_admin_site = PublicAdminSite(name='public_admin')
#
# # USER
# class UserAdminTibillet(UserAdmin):
#     ...
# root_admin_site.register(TibilletUser, UserAdminTibillet)
#
# class CustomGroupAdmin(GroupAdmin):
#     pass
# root_admin_site.register(Group, CustomGroupAdmin)
#
# # CLIENT / DOMAIN
# class DomainInline(admin.TabularInline):
#     model = Domain
#
# class ClientAdmin(admin.ModelAdmin):
#     inlines = [DomainInline]
#     list_display = ('schema_name', 'name', 'categorie', 'created_on')
# root_admin_site.register(Client, ClientAdmin)
# root_admin_site.register(Domain, admin.ModelAdmin)
#
# # CARTE CASHLESS (deplace vers Administration/admin/cards.py)
# # CARTE CASHLESS (moved to Administration/admin/cards.py)
# # class CarteCashlessAdmin(admin.ModelAdmin):
# #     list_display = ('user', 'tag_id', 'wallets', 'number', 'uuid', 'get_origin')
# # root_admin_site.register(CarteCashless, CarteCashlessAdmin)
#
# # AUTRES
# root_admin_site.register(ProductDirectory, admin.ModelAdmin)
# root_admin_site.register(EventDirectory, admin.ModelAdmin)
# root_admin_site.register(RootConfiguration, SingletonModelAdmin)
```

- [ ] **Step 3: Vérifier que rien n'utilisait `root_admin_site`**

```bash
grep -rn "root_admin_site\b" /home/jonas/TiBillet/dev/Lespass/ --include="*.py" 2>/dev/null | grep -v "__pycache__\|admin_root.py"
```

Expected: 0 résultats. Si résultats, investiguer avant de continuer.

- [ ] **Step 4: Check Django**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 5: Commit**

```bash
git add Administration/admin_root.py
git commit -m "chore(Administration): comment out remaining dead code in admin_root.py"
```

---

## Task 10: Tests permissions admin

**Files:**
- Create: `tests/pytest/test_admin_cards.py`

- [ ] **Step 1: Créer le fichier de test**

```python
"""
tests/pytest/test_admin_cards.py — Tests permissions et filtres CarteCashlessAdmin (Phase 1).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_cards.py -v --api-key dummy
"""
import uuid as uuid_module

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django_tenants.utils import schema_context

from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail


CARDS_TEST_PREFIX = "ADMTEST"


@pytest.fixture(scope="module")
def tenant_lespass():
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="module")
def tenant_other():
    """Un autre tenant pour tester l'isolation."""
    return Client.objects.exclude(schema_name__in=["public", "lespass"]).first()


@pytest.fixture
def carte_lespass(tenant_lespass):
    """Carte rattachee au tenant lespass."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_LESP',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte = CarteCashless.objects.create(
            tag_id='ADM00001',
            number='ADM00001',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
        yield carte
        carte.delete()
        Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_LESP').delete()


@pytest.fixture
def carte_autre_tenant(tenant_other):
    """Carte rattachee a un autre tenant (test isolation)."""
    if tenant_other is None:
        pytest.skip("Pas de second tenant disponible pour le test d'isolation")
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_OTHR',
            origine=tenant_other,
            defaults={"generation": 0},
        )
        carte = CarteCashless.objects.create(
            tag_id='ADM00002',
            number='ADM00002',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
        yield carte
        carte.delete()
        Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_OTHR').delete()


def _login_admin_lespass():
    """Cree un client de test login en tant qu'admin du tenant lespass."""
    client = TestClient(HTTP_HOST='lespass.tibillet.localhost')
    User = get_user_model()
    user = User.objects.filter(email='admin@admin.com').first()
    if user is None:
        pytest.skip("User admin@admin.com introuvable (cf. memoire utilisateur)")
    client.force_login(user)
    return client, user


def test_card_admin_filter_by_tenant(carte_lespass, carte_autre_tenant):
    """
    Admin tenant ne voit que les cartes dont detail.origine == son tenant.
    Tenant admin only sees cards whose detail.origine matches their tenant.
    """
    from Administration.admin.cards import CarteCashlessAdmin
    from Administration.admin.site import staff_admin_site

    client, user = _login_admin_lespass()
    if user.is_superuser:
        pytest.skip("L'utilisateur de test est superuser, on teste l'autre cas dans test_card_admin_superuser_voit_tout")

    admin_instance = CarteCashlessAdmin(CarteCashless, staff_admin_site)

    # Simule une request avec connection.tenant = lespass
    response = client.get('/admin/QrcodeCashless/cartecashless/')
    assert response.status_code == 200
    contenu = response.content.decode()
    assert 'ADM00001' in contenu  # Carte du tenant lespass : visible
    assert 'ADM00002' not in contenu  # Carte d'un autre tenant : invisible


def test_card_admin_add_forbidden_for_tenant_admin(tenant_lespass):
    """
    POST sur add_view -> 403 si l'utilisateur n'est pas superuser.
    POST on add_view -> 403 if user is not superuser.
    """
    client, user = _login_admin_lespass()
    if user.is_superuser:
        pytest.skip("Test specifique aux non-superusers")

    response = client.get('/admin/QrcodeCashless/cartecashless/add/')
    # Django admin renvoie 403 ou redirige vers index si pas la permission
    assert response.status_code in (403, 302)


def test_refund_view_carte_vierge_no_button(tenant_lespass):
    """
    GET sur refund/ d'une carte sans wallet : message 'carte vierge', pas de bouton confirmer.
    GET on refund/ for a card without wallet: 'empty card' message, no confirm button.
    """
    client, user = _login_admin_lespass()
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_VIDE',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte_vide = CarteCashless.objects.create(
            tag_id='ADM00099',
            number='ADM00099',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
    try:
        response = client.get(f'/admin/QrcodeCashless/cartecashless/{carte_vide.uuid}/refund/')
        assert response.status_code == 200
        contenu = response.content.decode()
        assert 'card-refund-empty' in contenu  # data-testid du div info
        assert 'btn-refund-confirm' not in contenu  # Pas de bouton confirmer
    finally:
        carte_vide.delete()
        Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_VIDE').delete()


@pytest.fixture(scope="module", autouse=True)
def cleanup_admin_test_data():
    """Nettoyage en fin de module."""
    yield
    try:
        with schema_context('lespass'):
            CarteCashless.objects.filter(tag_id__startswith='ADM').delete()
            Detail.objects.filter(base_url__startswith=CARDS_TEST_PREFIX).delete()
    except Exception:
        pass
```

- [ ] **Step 2: Lancer les tests admin**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_cards.py -v --api-key dummy
```

Expected: tous les tests PASS (ou SKIP si pas de second tenant / user admin).

- [ ] **Step 3: Commit**

```bash
git add tests/pytest/test_admin_cards.py
git commit -m "test(Administration): permission and tenant filter tests for CarteCashlessAdmin"
```

---

## Task 11: Test E2E Playwright (flow complet)

**Files:**
- Create: `tests/e2e/test_admin_card_refund.py`

- [ ] **Step 1: Inspecter un test E2E existant pour suivre les conventions**

```bash
ls /home/jonas/TiBillet/dev/Lespass/tests/e2e/ | head -10
```

Choisir un fichier comme modèle (ex: `test_pos_*.py`) :

```bash
head -80 /home/jonas/TiBillet/dev/Lespass/tests/e2e/conftest.py
```

- [ ] **Step 2: Créer `tests/e2e/test_admin_card_refund.py`**

```python
"""
tests/e2e/test_admin_card_refund.py — Test E2E flow remboursement carte (Phase 1).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/e2e/test_admin_card_refund.py -v -s
"""
import uuid as uuid_module

import pytest
from django.db import transaction as db_transaction
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import Wallet
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, WalletService


E2E_PREFIX = "E2EREF"


@pytest.fixture
def carte_avec_solde_e2e():
    """
    Cree une carte avec un wallet contenant 1000c TLF + 500c FED, rattachee a lespass.
    Cleanup automatique en fin de test.
    """
    tenant = Client.objects.get(schema_name='lespass')
    with schema_context('lespass'):
        # Wallet recepteur (lieu)
        wallet_lieu = Wallet.objects.create(name=f'{E2E_PREFIX} Lieu')
        # Asset TLF du tenant
        asset_tlf = AssetService.creer_asset(
            tenant=tenant, name=f'{E2E_PREFIX} TLF',
            category=Asset.TLF, currency_code='EUR',
            wallet_origin=wallet_lieu,
        )
        # Asset FED (existant ou cree)
        asset_fed = Asset.objects.filter(category=Asset.FED).first()
        if asset_fed is None:
            asset_fed = AssetService.creer_asset(
                tenant=tenant, name=f'{E2E_PREFIX} FED',
                category=Asset.FED, currency_code='EUR',
                wallet_origin=wallet_lieu,
            )

        # Detail + Carte
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{E2E_PREFIX}_DETAIL',
            origine=tenant,
            defaults={"generation": 0},
        )
        wallet_user = Wallet.objects.create(name=f'{E2E_PREFIX} Wallet user')
        carte = CarteCashless.objects.create(
            tag_id='E2E00001',
            number='E2E00001',
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_user,
        )
        # Crediter
        with db_transaction.atomic():
            WalletService.crediter(wallet=wallet_user, asset=asset_tlf, montant_en_centimes=1000)
            WalletService.crediter(wallet=wallet_user, asset=asset_fed, montant_en_centimes=500)

    yield carte

    # Cleanup
    with schema_context('lespass'):
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet__in=[wallet_user, wallet_lieu]).delete()
        carte.delete()
        wallet_user.delete()
        Asset.objects.filter(name__startswith=E2E_PREFIX).delete()
        wallet_lieu.delete()
        Detail.objects.filter(base_url=f'{E2E_PREFIX}_DETAIL').delete()


def test_e2e_admin_refund_flow_complet(page, base_url, carte_avec_solde_e2e):
    """
    Flow complet : login admin -> liste cartes -> fiche carte -> page refund ->
    vérifier les montants -> confirmer -> vérifier le toast et le solde a 0.

    Complete flow: admin login -> cards list -> card detail -> refund page ->
    verify amounts -> confirm -> verify toast and zero balance.
    """
    # 1. Login admin (utilise la fixture admin_login si disponible, sinon manuel)
    page.goto(f'{base_url}/admin/login/')
    page.fill('input[name="username"]', 'admin@admin.com')
    page.fill('input[name="password"]', 'admin')
    page.click('button[type="submit"]')
    page.wait_for_url(f'{base_url}/admin/', timeout=5000)

    # 2. Naviguer vers la fiche carte directement
    refund_url = f'{base_url}/admin/QrcodeCashless/cartecashless/{carte_avec_solde_e2e.uuid}/refund/'
    page.goto(refund_url)

    # 3. Verifier l'affichage des tokens et du total
    page.wait_for_selector('[data-testid="refund-tokens-table"]', timeout=5000)
    contenu = page.content()
    assert '1000' in contenu  # Solde TLF
    assert '500' in contenu   # Solde FED
    assert '1500' in contenu  # Total

    # 4. Cliquer "Confirmer le remboursement"
    page.click('[data-testid="btn-refund-confirm"]')

    # 5. Vérifier la redirection vers la fiche carte + le message succes
    page.wait_for_url(
        lambda url: f'{carte_avec_solde_e2e.uuid}' in url and '/refund' not in url,
        timeout=5000,
    )
    contenu_apres = page.content()
    assert 'Remboursement effectue' in contenu_apres or 'Remboursement effectué' in contenu_apres

    # 6. Vérifier en DB : 2 Transactions REFUND, 2 LigneArticles
    with schema_context('lespass'):
        transactions_refund = Transaction.objects.filter(
            card=carte_avec_solde_e2e, action=Transaction.REFUND,
        )
        assert transactions_refund.count() == 2  # 1 TLF + 1 FED

        from BaseBillet.models import LigneArticle, PaymentMethod
        ligne_cash = LigneArticle.objects.filter(
            carte=carte_avec_solde_e2e, payment_method=PaymentMethod.CASH,
        )
        assert ligne_cash.count() == 1
        assert ligne_cash.first().amount == -1500

        ligne_fed = LigneArticle.objects.filter(
            carte=carte_avec_solde_e2e, payment_method=PaymentMethod.STRIPE_FED,
        )
        assert ligne_fed.count() == 1
        assert ligne_fed.first().amount == 500
```

- [ ] **Step 3: Vérifier que le serveur tourne**

```bash
curl -k -s -o /dev/null -w "%{http_code}" https://lespass.tibillet.localhost/admin/login/
```

Expected: `200` (ou `302` si redirect).

Si pas de réponse :
```bash
docker exec -d lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

- [ ] **Step 4: Lancer le test E2E**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_admin_card_refund.py::test_e2e_admin_refund_flow_complet -v -s
```

Expected: PASS. Si échec sur sélecteurs, ajuster `data-testid` dans le template.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_admin_card_refund.py
git commit -m "test(e2e): admin card refund full flow with TLF + FED"
```

---

## Task 12: i18n + commit final

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`

- [ ] **Step 1: Extraire les nouvelles chaînes**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

- [ ] **Step 2: Vérifier les fuzzy et les msgstr vides**

```bash
grep -B1 "^#, fuzzy" /home/jonas/TiBillet/dev/Lespass/locale/fr/LC_MESSAGES/django.po | head -30
grep -A1 'msgid "Remboursement carte"\|msgid "Cartes NFC"\|msgid "Lots de cartes"' /home/jonas/TiBillet/dev/Lespass/locale/fr/LC_MESSAGES/django.po
```

Si fuzzy ou vides : éditer manuellement les `.po` :
- `locale/fr/LC_MESSAGES/django.po` : msgstr en français (ex: "Remboursement carte" → "Remboursement carte")
- `locale/en/LC_MESSAGES/django.po` : msgstr en anglais (ex: "Remboursement carte" → "Card refund")

- [ ] **Step 3: Compiler**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

Expected: pas d'erreur.

- [ ] **Step 4: Lancer la suite complète des tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py tests/pytest/test_admin_cards.py tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected: tous PASS.

- [ ] **Step 5: Vérifier que `manage.py check` est propre**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

- [ ] **Step 6: Commit i18n**

```bash
git add locale/
git commit -m "i18n(Phase1): translate refund admin strings (FR/EN)"
```

---

## Récapitulatif

À la fin du plan, l'arbre des fichiers ressemble à :

```
fedow_core/
├── exceptions.py        (PATCH +NoEligibleTokens)
├── services.py          (PATCH +rembourser_en_especes)
└── REFUND.md            (NEW)

BaseBillet/
└── services_refund.py   (NEW)

Administration/
├── admin/
│   ├── cards.py         (NEW)
│   └── dashboard.py     (PATCH +sidebar)
├── admin_root.py        (PATCH cleanup)
├── admin_tenant.py      (PATCH +import cards)
├── serializers.py       (NEW)
├── views_cards.py       (NEW)
└── templates/admin/cards/refund.html (NEW)

tests/
├── pytest/
│   ├── test_card_refund_service.py  (NEW)
│   └── test_admin_cards.py          (NEW)
└── e2e/
    └── test_admin_card_refund.py    (NEW)

locale/{fr,en}/LC_MESSAGES/django.po (PATCH)
```

---

## Spec self-review (post-écriture)

**1. Spec coverage** :
- Admin Unfold cartes + lots → Tasks 7, 8 ✅
- Page dédiée remboursement → Tasks 5, 6 ✅
- Service `rembourser_en_especes()` → Task 3 ✅
- Helper Product/PriceSold partagé → Task 2 ✅
- Filtre par `detail.origine` sauf superuser → Task 7 (CarteCashlessAdmin.get_queryset) ✅
- Création/suppression superuser only → Task 7 (has_add_permission/has_delete_permission) ✅
- Checkbox VV unifié → Task 6 (template), Task 5 (serializer) ✅
- Cleanup admin_root.py → Task 9 ✅
- README REFUND.md → Task 4 ✅
- i18n → Task 12 ✅

**2. Placeholder scan** : aucun « TBD » / « TODO ». Toutes les tasks contiennent du code complet.

**3. Type consistency** :
- `WalletService.rembourser_en_especes(carte, tenant, receiver_wallet, ip, vider_carte)` : signature identique entre Task 3 (test), Task 3 (impl), Task 5 (appel ViewSet).
- `CardRefundConfirmSerializer` : champ `vider_carte: bool`, idem partout.
- URL names : `staff_admin:QrcodeCashless_cartecashless_refund` et `_refund_confirm` cohérents entre Task 7 (get_urls) et Task 6 (template form action).
- `data-testid` du template (Task 6) repris dans Task 11 (E2E).

**4. Notes restantes pour l'implémenteur** :
- Si le helper `_get_or_create_wallet_lieu()` ne convient pas, formaliser `tenant.wallet` avant Phase 2.
- Si `Configuration.module_monnaie_locale` doit être vérifié dans la vue (404 si désactivé), ajouter un decorator/middleware. Aujourd'hui l'isolation passe par la sidebar masquée.
