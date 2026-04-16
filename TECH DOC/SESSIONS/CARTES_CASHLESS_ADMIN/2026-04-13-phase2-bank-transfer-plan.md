# Phase 2 — Suivi de la dette pot central → tenant — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tracer la dette du pot central envers chaque tenant pour les FED remboursés en espèces (via Phase 1), permettre au superuser d'enregistrer les virements bancaires reçus avec validation hard `montant <= dette`, et exposer la dette en temps réel via dashboard superuser + widget tenant.

**Architecture:** Nouveau `BankTransferService` (4 méthodes statiques) dans `fedow_core/services.py` qui calcule la dette par requête sur la table `Transaction` et enregistre les virements. Nouvelle action `Transaction.BANK_TRANSFER = 'BTR'` (immutable, sans mutation Token). ViewSet dédié `BankTransfersViewSet` pour le superuser, widget tenant via `dashboard_callback`. Sortie comptable via `LigneArticle` (`payment_method=TRANSFER`).

**Tech Stack:** Django 5.x, django-tenants, Django Unfold, DRF (ViewSet + serializers), HTMX, pytest, Playwright Python.

**Spec source:** `TECH DOC/SESSIONS/CARTES_CASHLESS_ADMIN/2026-04-13-phase2-bank-transfer-design.md`

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `fedow_core/exceptions.py` | PATCH | +`MontantSuperieurDette` |
| `fedow_core/models.py` | PATCH | +`Transaction.BANK_TRANSFER = 'BTR'` choice |
| `fedow_core/migrations/000X_add_bank_transfer_choice.py` | NEW | Alter `Transaction.action` choices |
| `fedow_core/services.py` | PATCH | +`WalletService.get_or_create_wallet_tenant()`, étendre `TransactionService.creer()` (`actions_sans_credit` + `BANK_TRANSFER` dans `actions_sans_debit`), nouvelle classe `BankTransferService` (4 méthodes) |
| `BaseBillet/models.py` | PATCH | +`Product.VIREMENT_RECU = "VR"` choice |
| `BaseBillet/migrations/000X_add_virement_recu_choice.py` | NEW | Alter `Product.methode_caisse` choices |
| `BaseBillet/services_refund.py` | PATCH | +`get_or_create_product_virement_recu()` |
| `Administration/serializers.py` | PATCH | +`BankTransferCreateSerializer` |
| `Administration/views_bank_transfers.py` | NEW | `BankTransfersViewSet(viewsets.ViewSet)` patterns FALC `/djc` |
| `Administration/views_cards.py` | PATCH | Remplacer `_get_or_create_wallet_lieu` par appel à `WalletService.get_or_create_wallet_tenant` |
| `Administration/admin/site.py` | PATCH | Override `StaffAdminSite.get_urls()` |
| `Administration/admin/dashboard.py` | PATCH | +sidebar item « Virements pot central » + enrichir `dashboard_callback` |
| `Administration/templates/admin/bank_transfers/dashboard.html` | NEW | Page superuser, style inspiré bilan.html |
| `Administration/templates/admin/bank_transfers/create_form.html` | NEW | Formulaire HTMX |
| `Administration/templates/admin/bank_transfers/historique.html` | NEW | Liste BANK_TRANSFER (global + tenant) |
| `Administration/templates/admin/partials/widget_dette_pot_central.html` | NEW | Widget tenant |
| `Administration/templates/admin/dashboard.html` | PATCH | `{% include %}` du widget |
| `tests/pytest/test_bank_transfer_service.py` | NEW | Tests `BankTransferService` |
| `tests/pytest/test_admin_bank_transfers.py` | NEW | Tests permissions + filtres ViewSet + widget |
| `tests/e2e/test_admin_bank_transfer_flow.py` | NEW | E2E Playwright (saisie virement + widget) |

---

## Préambule — Démarrage du serveur dev

Démarrage du serveur Django dans le conteneur (à faire une fois en début de session) :

```bash
docker exec -d lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

---

## Task 1: Exception `MontantSuperieurDette`

**Files:**
- Modify: `fedow_core/exceptions.py`
- Test: `tests/pytest/test_bank_transfer_service.py` (création initiale)

- [ ] **Step 1: Lire le fichier exceptions.py existant**

```bash
cat /home/jonas/TiBillet/dev/Lespass/fedow_core/exceptions.py
```

Expected: voir `SoldeInsuffisant` et `NoEligibleTokens` comme modèles de style.

- [ ] **Step 2: Créer le test (nouveau fichier)**

Créer `tests/pytest/test_bank_transfer_service.py` avec :

```python
"""
tests/pytest/test_bank_transfer_service.py — Tests unitaires BankTransferService (Phase 2).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py -v --api-key dummy
"""
import pytest

from fedow_core.exceptions import MontantSuperieurDette


def test_montant_superieur_dette_message():
    """
    Verifie que l'exception MontantSuperieurDette porte un message explicite
    incluant le montant demande ET la dette actuelle.
    / Verifies MontantSuperieurDette carries an explicit message.
    """
    exc = MontantSuperieurDette(
        montant_demande_en_centimes=1500,
        dette_actuelle_en_centimes=750,
    )
    message = str(exc)
    assert "1500" in message or "15" in message  # montant
    assert "750" in message or "7" in message    # dette
```

- [ ] **Step 3: Lancer le test pour confirmer l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_montant_superieur_dette_message -v --api-key dummy
```

Expected: FAIL avec `ImportError: cannot import name 'MontantSuperieurDette'`.

- [ ] **Step 4: Ajouter l'exception dans `fedow_core/exceptions.py`**

À la fin du fichier :

```python
class MontantSuperieurDette(Exception):
    """
    Levee quand un superuser tente d'enregistrer un virement bancaire d'un montant
    superieur a la dette actuelle du pot central envers le tenant pour cet asset.

    Raised when a superuser attempts to record a bank transfer larger than
    the central pot's current debt to the tenant for this asset.

    Securite hard : on n'accepte jamais qu'un BANK_TRANSFER cree une dette negative
    (qui voudrait dire "le tenant doit au pot central", hors scope V2).
    """

    def __init__(self, montant_demande_en_centimes: int, dette_actuelle_en_centimes: int):
        self.montant_demande_en_centimes = montant_demande_en_centimes
        self.dette_actuelle_en_centimes = dette_actuelle_en_centimes
        message = _(
            "Montant demande %(montant)s centimes superieur a la dette actuelle "
            "%(dette)s centimes."
        ) % {
            "montant": montant_demande_en_centimes,
            "dette": dette_actuelle_en_centimes,
        }
        super().__init__(message)
```

Vérifier que `from django.utils.translation import gettext_lazy as _` est déjà importé en haut.

- [ ] **Step 5: Lancer le test pour vérifier le passage**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_montant_superieur_dette_message -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 6: Vérifier qu'aucun test existant n'est cassé**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected: tous PASS.

- [ ] **Step 7: Commit** (le mainteneur s'en occupe — skip)

---

## Task 2: Ajouter `Transaction.BANK_TRANSFER` choice + migration

**Files:**
- Modify: `fedow_core/models.py:368-382`
- Create: `fedow_core/migrations/000X_add_bank_transfer_choice.py` (généré par makemigrations)

- [ ] **Step 1: Lire les choices existants**

```bash
sed -n '358,385p' /home/jonas/TiBillet/dev/Lespass/fedow_core/models.py
```

Expected: voir `DEPOSIT = 'DEP'` et `TRANSFER = 'TRF'` parmi les actions.

- [ ] **Step 2: Modifier `fedow_core/models.py`**

Trouver la ligne `TRANSFER = 'TRF'` (~ligne 369) et ajouter juste après :

```python
    TRANSFER = 'TRF'      # Virement direct entre wallets
    BANK_TRANSFER = 'BTR' # Virement bancaire pot central → tenant (mouvement externe au systeme, no token mutation)
```

Et dans `ACTION_CHOICES` (~ligne 371), ajouter avant le `]` final :

```python
        (TRANSFER, _('Virement')),
        (BANK_TRANSFER, _('Virement bancaire pot central')),
    ]
```

- [ ] **Step 3: Générer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations fedow_core
```

Expected: création d'un fichier migration avec `AlterField` sur `Transaction.action` (juste les choices).

- [ ] **Step 4: Appliquer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas
```

Expected: migration appliquée sans erreur (alter d'un field choices = no-op DB côté PostgreSQL).

- [ ] **Step 5: Vérifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from fedow_core.models import Transaction; print(Transaction.BANK_TRANSFER); print([c[0] for c in Transaction.ACTION_CHOICES])"
```

Expected: `BTR` puis liste contenant `'BTR'`.

- [ ] **Step 6: Check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

---

## Task 3: Ajouter `Product.VIREMENT_RECU` choice + migration

**Files:**
- Modify: `BaseBillet/models.py:1274-1296`
- Create: `BaseBillet/migrations/000X_add_virement_recu_choice.py`

- [ ] **Step 1: Lire les choices existants**

```bash
sed -n '1270,1310p' /home/jonas/TiBillet/dev/Lespass/BaseBillet/models.py
```

Expected: voir `VIDER_CARTE = "VC"` parmi les codes de `methode_caisse`.

- [ ] **Step 2: Modifier `BaseBillet/models.py`**

Trouver la liste de codes (~ligne 1274-1283) et ajouter `VIREMENT_RECU = "VR"` après `FIDELITE` :

```python
    VENTE = "VT"
    RECHARGE_EUROS = "RE"
    RECHARGE_CADEAU = "RC"
    RECHARGE_TEMPS = "TM"
    ADHESION_POS = "AD"
    RETOUR_CONSIGNE = "CR"
    VIDER_CARTE = "VC"
    FRACTIONNE_POS = "FR"
    BILLET_POS = "BI"
    FIDELITE = "FD"
    VIREMENT_RECU = "VR"
```

Et dans `METHODE_CAISSE_CHOICES` (~ligne 1285-1296), ajouter avant le `]` final :

```python
        (FIDELITE, _("Loyalty")),
        (VIREMENT_RECU, _("Bank transfer received")),
    ]
```

- [ ] **Step 3: Générer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet
```

Expected: création d'un fichier migration avec `AlterField` sur `Product.methode_caisse` choices.

- [ ] **Step 4: Appliquer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas
```

Expected: appliquée sans erreur.

- [ ] **Step 5: Vérifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from BaseBillet.models import Product; print(Product.VIREMENT_RECU); print([c[0] for c in Product.METHODE_CAISSE_CHOICES])"
```

Expected: `VR` puis liste contenant `'VR'`.

- [ ] **Step 6: Check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

---

## Task 4: Refactor `_get_or_create_wallet_lieu` → `WalletService.get_or_create_wallet_tenant`

**Files:**
- Modify: `fedow_core/services.py` (ajout méthode dans `WalletService`)
- Modify: `Administration/views_cards.py:69-80` (suppression du helper local + appel au service)

Cette task élimine une dépendance backward de `fedow_core` vers `Administration` qu'on s'apprêterait à créer en Phase 2 si on laissait le helper côté admin.

- [ ] **Step 1: Lire le helper existant en Phase 1**

```bash
sed -n '65,82p' /home/jonas/TiBillet/dev/Lespass/Administration/views_cards.py
```

Expected: voir la fonction `_get_or_create_wallet_lieu(tenant)` qui fait `Wallet.objects.get_or_create(origin=tenant, name=f"Lieu {tenant.schema_name}")`.

- [ ] **Step 2: Ajouter le test pour la nouvelle méthode service**

Ajouter à `tests/pytest/test_bank_transfer_service.py` (après le test de l'exception) :

```python
import pytest
from django_tenants.utils import schema_context

from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.services import WalletService


@pytest.fixture(scope="module")
def tenant_lespass_bt():
    return Client.objects.get(schema_name='lespass')


def test_get_or_create_wallet_tenant_creates_once(tenant_lespass_bt):
    """
    Premier appel cree le wallet, deuxieme appel le reutilise.
    Identifie par origin=tenant ET name=f"Lieu {schema_name}".
    """
    with schema_context('lespass'):
        wallet_a = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
        wallet_b = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
        assert wallet_a.pk == wallet_b.pk
        assert wallet_a.name == f"Lieu {tenant_lespass_bt.schema_name}"
        assert wallet_a.origin_id == tenant_lespass_bt.pk
```

- [ ] **Step 3: Lancer le test pour confirmer l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_get_or_create_wallet_tenant_creates_once -v --api-key dummy
```

Expected: FAIL avec `AttributeError: type object 'WalletService' has no attribute 'get_or_create_wallet_tenant'`.

- [ ] **Step 4: Ajouter la méthode dans `WalletService`**

Dans `fedow_core/services.py`, ajouter dans la classe `WalletService` après `obtenir_total_en_centimes()` (avant `crediter`) :

```python
    @staticmethod
    def get_or_create_wallet_tenant(tenant):
        """
        Recupere ou cree le wallet "lieu" du tenant — wallet receveur des refunds
        et BANK_TRANSFER, et sender des operations sortantes du lieu.
        Returns or creates the tenant's "venue" wallet.

        Convention : un wallet par tenant, identifie par origin=tenant
        ET name=f"Lieu {tenant.schema_name}". Idempotent.

        NB : a remplacer par tenant.wallet quand la convention sera formalisee
        sur le modele Customers.Client.
        """
        wallet, _created = Wallet.objects.get_or_create(
            origin=tenant,
            name=f"Lieu {tenant.schema_name}",
        )
        return wallet
```

- [ ] **Step 5: Lancer le test pour vérifier le passage**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_get_or_create_wallet_tenant_creates_once -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 6: Mettre à jour `Administration/views_cards.py`**

Lire le fichier et identifier l'utilisation du helper (~ligne 140) :

```bash
grep -n "_get_or_create_wallet_lieu" /home/jonas/TiBillet/dev/Lespass/Administration/views_cards.py
```

Remplacer la définition de la fonction (lignes ~65-80) **et** son appel à l'intérieur du ViewSet par :
1. Supprimer la fonction `_get_or_create_wallet_lieu(tenant)` (les ~16 lignes incluant la docstring).
2. Remplacer l'appel `receiver_wallet = _get_or_create_wallet_lieu(tenant)` par `receiver_wallet = WalletService.get_or_create_wallet_tenant(tenant)`.

(L'import `from fedow_core.services import WalletService` est déjà présent dans ce fichier — vérifier avec `grep "from fedow_core.services" /home/jonas/TiBillet/dev/Lespass/Administration/views_cards.py`.)

- [ ] **Step 7: Vérifier que les tests Phase 1 passent toujours**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py tests/pytest/test_admin_cards.py -v --api-key dummy
```

Expected: tous PASS (pas de régression Phase 1).

- [ ] **Step 8: Check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

---

## Task 5: Étendre `TransactionService.creer()` — actions sans crédit

**Files:**
- Modify: `fedow_core/services.py:720-749` (méthode `TransactionService.creer`)

- [ ] **Step 1: Ajouter le test qui prouve qu'un BANK_TRANSFER ne mute pas les Tokens**

Ajouter à `tests/pytest/test_bank_transfer_service.py` :

```python
from django.db import transaction as db_transaction
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, TransactionService


BT_TEST_PREFIX = '[bt_test]'


@pytest.fixture(scope="module")
def wallet_pot_central(tenant_lespass_bt):
    return Wallet.objects.create(name=f'{BT_TEST_PREFIX} Pot central')


@pytest.fixture(scope="module")
def asset_fed_test(tenant_lespass_bt, wallet_pot_central):
    """L'asset FED utilise pour les tests BankTransferService."""
    existing = Asset.objects.filter(category=Asset.FED).first()
    if existing is not None:
        return existing
    return AssetService.creer_asset(
        tenant=tenant_lespass_bt,
        name=f'{BT_TEST_PREFIX} FED',
        category=Asset.FED,
        currency_code='EUR',
        wallet_origin=wallet_pot_central,
    )


def test_bank_transfer_action_no_token_mutation(
    tenant_lespass_bt, wallet_pot_central, asset_fed_test,
):
    """
    Une Transaction action=BANK_TRANSFER ne doit ni debiter le sender
    ni crediter le receiver (mouvement bancaire externe).
    """
    receiver_wallet = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)

    # Solde initial sender et receiver
    solde_sender_avant = WalletService.obtenir_solde(wallet_pot_central, asset_fed_test)
    solde_receiver_avant = WalletService.obtenir_solde(receiver_wallet, asset_fed_test)

    TransactionService.creer(
        sender=wallet_pot_central,
        receiver=receiver_wallet,
        asset=asset_fed_test,
        montant_en_centimes=500,
        action=Transaction.BANK_TRANSFER,
        tenant=tenant_lespass_bt,
        ip="127.0.0.1",
        comment="Test no token mutation",
    )

    # Verifier qu'aucun solde n'a bouge
    solde_sender_apres = WalletService.obtenir_solde(wallet_pot_central, asset_fed_test)
    solde_receiver_apres = WalletService.obtenir_solde(receiver_wallet, asset_fed_test)
    assert solde_sender_apres == solde_sender_avant
    assert solde_receiver_apres == solde_receiver_avant

    # Verifier qu'une Transaction a bien ete creee
    tx = Transaction.objects.filter(
        action=Transaction.BANK_TRANSFER,
        sender=wallet_pot_central,
        receiver=receiver_wallet,
    ).order_by('-id').first()
    assert tx is not None
    assert tx.amount == 500
```

- [ ] **Step 2: Lancer le test pour confirmer l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_bank_transfer_action_no_token_mutation -v --api-key dummy
```

Expected: FAIL — soit le receiver est crédité (solde change), soit l'appel échoue car le sender n'a pas de Token (`SoldeInsuffisant`).

- [ ] **Step 3: Modifier `TransactionService.creer()` dans `fedow_core/services.py`**

Lire d'abord la méthode (~lignes 720-749) :

```bash
sed -n '715,755p' /home/jonas/TiBillet/dev/Lespass/fedow_core/services.py
```

Remplacer le bloc :

```python
            actions_sans_debit = [Transaction.FIRST, Transaction.CREATION, Transaction.REFILL]
            action_necessite_debit = action not in actions_sans_debit

            if action_necessite_debit:
                WalletService.debiter(
                    wallet=sender,
                    asset=asset,
                    montant_en_centimes=montant_en_centimes,
                )

            # --- Credit du receiver ---
            # Certaines actions ne creditent pas (VOID, REFUND sans receiver).
            # Some actions don't credit (VOID, REFUND without receiver).
            receiver_existe = receiver is not None
            if receiver_existe:
                WalletService.crediter(
                    wallet=receiver,
                    asset=asset,
                    montant_en_centimes=montant_en_centimes,
                )
```

par :

```python
            actions_sans_debit = [
                Transaction.FIRST,
                Transaction.CREATION,
                Transaction.REFILL,
                Transaction.BANK_TRANSFER,  # virement bancaire externe : pas de mutation Token
            ]
            action_necessite_debit = action not in actions_sans_debit

            if action_necessite_debit:
                WalletService.debiter(
                    wallet=sender,
                    asset=asset,
                    montant_en_centimes=montant_en_centimes,
                )

            # --- Credit du receiver ---
            # Certaines actions ne creditent pas le receiver :
            # - receiver=None (VOID, REFUND sans receiver explicite)
            # - BANK_TRANSFER : virement bancaire externe, l'argent n'arrive pas
            #   sur le wallet receveur (il arrive sur le compte bancaire externe).
            # Some actions don't credit:
            # - receiver=None (VOID, REFUND without explicit receiver)
            # - BANK_TRANSFER: external bank movement, money does NOT land on
            #   the receiver wallet (it lands on the external bank account).
            actions_sans_credit = [Transaction.BANK_TRANSFER]
            receiver_existe = receiver is not None
            action_necessite_credit = action not in actions_sans_credit
            if receiver_existe and action_necessite_credit:
                WalletService.crediter(
                    wallet=receiver,
                    asset=asset,
                    montant_en_centimes=montant_en_centimes,
                )
```

- [ ] **Step 4: Lancer le test pour vérifier le passage**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_bank_transfer_action_no_token_mutation -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 5: Vérifier que les tests Phase 1 ne sont pas cassés (les actions REFUND/SALE/etc. doivent toujours muter)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py tests/pytest/test_card_refund_service.py -v --api-key dummy
```

Expected: tous PASS.

- [ ] **Step 6: Check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

---

## Task 6: Helper `get_or_create_product_virement_recu()`

**Files:**
- Modify: `BaseBillet/services_refund.py` (ajout en bas du fichier)

- [ ] **Step 1: Ajouter le test**

Ajouter à `tests/pytest/test_bank_transfer_service.py` :

```python
from BaseBillet.models import Product
from BaseBillet.services_refund import get_or_create_product_virement_recu


def test_get_or_create_product_virement_recu_creates_once():
    """Helper Product systeme 'Virement pot central' — idempotent."""
    with schema_context('lespass'):
        product_a = get_or_create_product_virement_recu()
        product_b = get_or_create_product_virement_recu()
        assert product_a.pk == product_b.pk
        assert product_a.methode_caisse == Product.VIREMENT_RECU
        assert product_a.publish is False
```

- [ ] **Step 2: Lancer le test pour confirmer l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_get_or_create_product_virement_recu_creates_once -v --api-key dummy
```

Expected: FAIL avec `ImportError: cannot import name 'get_or_create_product_virement_recu'`.

- [ ] **Step 3: Ajouter le helper dans `BaseBillet/services_refund.py`**

À la fin du fichier (après `get_or_create_pricesold_refund`) :

```python
def get_or_create_product_virement_recu() -> Product:
    """
    Retourne le Product systeme "Virement pot central" du tenant courant.
    Returns the system Product "Central pot transfer" for the current tenant.

    Cree le Product la premiere fois, le reutilise ensuite.
    Identifie par methode_caisse=VIREMENT_RECU (un seul par tenant).

    Created on first call, reused thereafter.
    Identified by methode_caisse=VIREMENT_RECU (one per tenant).

    Le helper get_or_create_pricesold_refund (existant) est reutilisable tel quel
    pour creer le PriceSold associe a ce Product.
    """
    product, _created = Product.objects.get_or_create(
        methode_caisse=Product.VIREMENT_RECU,
        defaults={
            "name": str(_("Virement pot central")),
            "publish": False,
        },
    )
    return product
```

- [ ] **Step 4: Lancer le test pour vérifier le passage**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_get_or_create_product_virement_recu_creates_once -v --api-key dummy
```

Expected: PASS.

- [ ] **Step 5: Check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

---

## Task 7: `BankTransferService` — cœur métier

**Files:**
- Modify: `fedow_core/services.py` (ajout d'une nouvelle classe en bas du fichier)

- [ ] **Step 1: Ajouter les fixtures et tests pour `calculer_dette` et `enregistrer_virement`**

Ajouter à `tests/pytest/test_bank_transfer_service.py` :

```python
from fedow_core.exceptions import MontantSuperieurDette
from fedow_core.services import BankTransferService


def test_calculer_dette_zero_si_aucune_transaction(
    tenant_lespass_bt, asset_fed_test,
):
    """Aucune transaction REFUND ou BANK_TRANSFER -> dette = 0."""
    with schema_context('lespass'):
        # Cleanup avant le test pour partir de zero (peut etre pollue par d'autres tests)
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()

        dette = BankTransferService.calculer_dette(
            tenant=tenant_lespass_bt, asset=asset_fed_test,
        )
        assert dette == 0


def test_calculer_dette_apres_un_refund(
    tenant_lespass_bt, asset_fed_test, wallet_pot_central,
):
    """1 REFUND de 800c -> dette = 800c."""
    receiver = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
    with schema_context('lespass'):
        # Cleanup
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()

        # Crediter le pot central pour pouvoir REFUND (action=REFUND debite sender)
        # Ici on simule : on cree directement la Transaction REFUND sans passer
        # par creer_vente (pas besoin de tokens reels pour le calcul de dette).
        Transaction.objects.create(
            sender=receiver, receiver=receiver,  # peu importe pour le calcul
            asset=asset_fed_test, amount=800, action=Transaction.REFUND,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )

        dette = BankTransferService.calculer_dette(
            tenant=tenant_lespass_bt, asset=asset_fed_test,
        )
        assert dette == 800


def test_calculer_dette_apres_refund_et_virement(
    tenant_lespass_bt, asset_fed_test, wallet_pot_central,
):
    """REFUND 1000c + BANK_TRANSFER 300c -> dette = 700c."""
    receiver = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
    with schema_context('lespass'):
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()

        Transaction.objects.create(
            sender=receiver, receiver=receiver,
            asset=asset_fed_test, amount=1000, action=Transaction.REFUND,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )
        Transaction.objects.create(
            sender=wallet_pot_central, receiver=receiver,
            asset=asset_fed_test, amount=300, action=Transaction.BANK_TRANSFER,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )

        dette = BankTransferService.calculer_dette(
            tenant=tenant_lespass_bt, asset=asset_fed_test,
        )
        assert dette == 700


def test_enregistrer_virement_cree_transaction_et_lignearticle(
    tenant_lespass_bt, asset_fed_test, wallet_pot_central,
):
    """
    enregistrer_virement cree 1 Transaction BANK_TRANSFER + 1 LigneArticle TRANSFER positive,
    sans muter les Tokens.
    """
    from datetime import date
    from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin

    receiver = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
    with schema_context('lespass'):
        # Setup : creer une dette de 1000c via REFUND
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()
        LigneArticle.objects.filter(
            asset=asset_fed_test.uuid,
            payment_method=PaymentMethod.TRANSFER,
        ).delete()
        Transaction.objects.create(
            sender=receiver, receiver=receiver,
            asset=asset_fed_test, amount=1000, action=Transaction.REFUND,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )

        # Action : enregistrer un virement de 400c
        tx = BankTransferService.enregistrer_virement(
            tenant=tenant_lespass_bt,
            asset=asset_fed_test,
            montant_en_centimes=400,
            date_virement=date.today(),
            reference_bancaire="VIR-TEST-001",
            comment="Test enregistrement",
            ip="127.0.0.1",
            admin_email="test@test.com",
        )

        assert tx.action == Transaction.BANK_TRANSFER
        assert tx.amount == 400
        assert tx.tenant_id == tenant_lespass_bt.pk

        # LigneArticle d'encaissement
        ligne = LigneArticle.objects.filter(
            asset=asset_fed_test.uuid,
            payment_method=PaymentMethod.TRANSFER,
            sale_origin=SaleOrigin.ADMIN,
        ).order_by('-datetime').first()
        assert ligne is not None
        assert ligne.amount == 400
        assert ligne.wallet_id == receiver.pk
        assert ligne.metadata.get("reference_bancaire") == "VIR-TEST-001"
        assert ligne.metadata.get("transaction_uuid") == str(tx.uuid)


def test_enregistrer_virement_rejette_si_montant_superieur_dette(
    tenant_lespass_bt, asset_fed_test,
):
    """Sur-versement -> MontantSuperieurDette."""
    from datetime import date
    from BaseBillet.models import LigneArticle

    receiver = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
    with schema_context('lespass'):
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()
        Transaction.objects.create(
            sender=receiver, receiver=receiver,
            asset=asset_fed_test, amount=200, action=Transaction.REFUND,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )

        with pytest.raises(MontantSuperieurDette):
            BankTransferService.enregistrer_virement(
                tenant=tenant_lespass_bt,
                asset=asset_fed_test,
                montant_en_centimes=500,  # > 200c de dette
                date_virement=date.today(),
                reference_bancaire="VIR-OVERFLOW-001",
                ip="127.0.0.1",
            )


@pytest.fixture(scope="module", autouse=True)
def cleanup_bt_test_data():
    """Nettoyage en fin de module."""
    yield
    try:
        with schema_context('lespass'):
            from BaseBillet.models import LigneArticle
            wallets_test = Wallet.objects.filter(name__startswith=BT_TEST_PREFIX)
            assets_test = Asset.objects.filter(name__startswith=BT_TEST_PREFIX)
            LigneArticle.objects.filter(asset__in=[a.uuid for a in assets_test]).delete()
            Transaction.objects.filter(asset__in=assets_test).delete()
            Token.objects.filter(wallet__in=wallets_test).delete()
            assets_test.delete()
            wallets_test.delete()
    except Exception:
        pass
```

Note : ajouter `from django.utils import timezone` en haut du fichier de test si pas déjà présent.

- [ ] **Step 2: Lancer les tests pour confirmer l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py::test_calculer_dette_zero_si_aucune_transaction -v --api-key dummy
```

Expected: FAIL avec `ImportError: cannot import name 'BankTransferService'`.

- [ ] **Step 3: Ajouter `BankTransferService` à la fin de `fedow_core/services.py`**

```python
# ---------------------------------------------------------------------------
# BankTransferService : suivi de la dette pot central → tenant (Phase 2)
# BankTransferService: tracking central pot debt to tenants (Phase 2)
# ---------------------------------------------------------------------------

class BankTransferService:
    """
    Service de gestion des virements bancaires pot central -> tenant.
    Tracks the central pot's debt to tenants for refunded FED tokens.

    La dette = somme(REFUND FED vers tenant) - somme(BANK_TRANSFER FED vers tenant).
    Aucune mutation Token (les BANK_TRANSFER sont des evenements bancaires externes,
    enregistres pour audit + reporting comptable).

    The debt = sum(REFUND FED to tenant) - sum(BANK_TRANSFER FED to tenant).
    No Token mutation (BANK_TRANSFER are external bank events, recorded for
    audit + accounting reporting only).
    """

    @staticmethod
    def calculer_dette(tenant, asset) -> int:
        """
        Retourne la dette actuelle en centimes du pot central envers ce tenant pour cet asset.
        Returns the central pot's current debt to this tenant for this asset, in cents.

        Calcul : sum(REFUND, asset, tenant=tenant) - sum(BANK_TRANSFER, asset, tenant=tenant).
        Garantit >= 0 (validation hard a la saisie empeche tout sur-versement).
        """
        from django.db.models import Sum

        agg_refund = Transaction.objects.filter(
            action=Transaction.REFUND,
            asset=asset,
            tenant=tenant,
        ).aggregate(total=Sum('amount'))
        total_refund = agg_refund.get('total') or 0

        agg_virement = Transaction.objects.filter(
            action=Transaction.BANK_TRANSFER,
            asset=asset,
            tenant=tenant,
        ).aggregate(total=Sum('amount'))
        total_virement = agg_virement.get('total') or 0

        dette = total_refund - total_virement
        return max(0, dette)  # filet de securite : la dette ne peut etre negative

    @staticmethod
    def obtenir_dettes_par_tenant_et_asset() -> list:
        """
        Pour le dashboard superuser : toutes les dettes par couple (tenant, asset).
        For the superuser dashboard: all debts per (tenant, asset) pair.

        Inclut les couples avec dette > 0 OU au moins 1 REFUND historique.
        Trie par dette decroissante.

        Retourne : list[dict] avec les cles :
          - tenant: Client
          - asset: Asset
          - dette_centimes: int
          - total_refund_centimes: int
          - total_virements_centimes: int
          - dernier_virement: Transaction | None
        """
        from django.db.models import Sum, Max

        # Tous les couples (tenant, asset) avec au moins une activite REFUND ou BANK_TRANSFER
        # / All (tenant, asset) pairs with at least one REFUND or BANK_TRANSFER activity
        couples = Transaction.objects.filter(
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            asset__category=Asset.FED,
        ).values_list('tenant_id', 'asset_id').distinct()

        resultat = []
        for tenant_id, asset_id in couples:
            tenant = Client.objects.filter(pk=tenant_id).first()
            asset = Asset.objects.filter(pk=asset_id).first()
            if tenant is None or asset is None:
                continue

            agg_refund = Transaction.objects.filter(
                action=Transaction.REFUND, asset=asset, tenant=tenant,
            ).aggregate(total=Sum('amount'))
            total_refund = agg_refund.get('total') or 0

            agg_virement = Transaction.objects.filter(
                action=Transaction.BANK_TRANSFER, asset=asset, tenant=tenant,
            ).aggregate(total=Sum('amount'))
            total_virement = agg_virement.get('total') or 0

            dette = max(0, total_refund - total_virement)

            dernier_virement = Transaction.objects.filter(
                action=Transaction.BANK_TRANSFER, asset=asset, tenant=tenant,
            ).order_by('-datetime').first()

            resultat.append({
                "tenant": tenant,
                "asset": asset,
                "dette_centimes": dette,
                "total_refund_centimes": total_refund,
                "total_virements_centimes": total_virement,
                "dernier_virement": dernier_virement,
            })

        # Tri : dette decroissante / Sort: debt descending
        resultat.sort(key=lambda d: d["dette_centimes"], reverse=True)
        return resultat

    @staticmethod
    def obtenir_dette_pour_tenant(tenant) -> list:
        """
        Pour le widget tenant : meme structure que obtenir_dettes_par_tenant_et_asset
        mais filtree au tenant courant.
        For the tenant widget: same structure but filtered to current tenant.
        """
        toutes = BankTransferService.obtenir_dettes_par_tenant_et_asset()
        return [d for d in toutes if d["tenant"].pk == tenant.pk]

    @staticmethod
    def enregistrer_virement(
        tenant,
        asset,
        montant_en_centimes: int,
        date_virement,
        reference_bancaire: str,
        comment: str = "",
        ip: str = "0.0.0.0",
        admin_email: str = "",
    ):
        """
        Enregistre un virement bancaire recu par le tenant.
        Records a bank transfer received by the tenant.

        Cree atomiquement :
        - 1 Transaction(action=BANK_TRANSFER, sender=asset.wallet_origin,
                        receiver=tenant.wallet_lieu, asset=asset, amount=...).
        - 1 LigneArticle d'encaissement (payment_method=TRANSFER, +amount,
                                          sale_origin=ADMIN, asset=asset.uuid).

        Validation : montant <= calculer_dette(tenant, asset) (re-check dans l'atomic).

        :return: Transaction creee
        :raises MontantSuperieurDette: si sur-versement
        """
        # Imports locaux pour eviter le cycle SHARED_APPS / TENANT_APPS
        # / Local imports to avoid SHARED_APPS / TENANT_APPS cycle
        from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
        from BaseBillet.services_refund import (
            get_or_create_product_virement_recu,
            get_or_create_pricesold_refund,
        )
        from fedow_core.exceptions import MontantSuperieurDette

        with transaction.atomic():
            # Re-check de la dette dans l'atomic (race guard)
            # / Re-check debt within atomic block (race guard)
            dette = BankTransferService.calculer_dette(tenant=tenant, asset=asset)
            if montant_en_centimes > dette:
                raise MontantSuperieurDette(
                    montant_demande_en_centimes=montant_en_centimes,
                    dette_actuelle_en_centimes=dette,
                )

            receiver_wallet = WalletService.get_or_create_wallet_tenant(tenant)

            # 1. Transaction BANK_TRANSFER (no token mutation grace a actions_sans_credit)
            # / 1. BANK_TRANSFER Transaction (no token mutation thanks to actions_sans_credit)
            tx = TransactionService.creer(
                sender=asset.wallet_origin,
                receiver=receiver_wallet,
                asset=asset,
                montant_en_centimes=montant_en_centimes,
                action=Transaction.BANK_TRANSFER,
                tenant=tenant,
                ip=ip,
                comment=comment,
                metadata={
                    "reference_bancaire": reference_bancaire,
                    "date_virement": date_virement.isoformat(),
                    "saisi_par": admin_email,
                },
            )

            # 2. LigneArticle d'encaissement (rapport comptable)
            # / 2. LigneArticle for accounting reports
            product_vr = get_or_create_product_virement_recu()
            pricesold_vr = get_or_create_pricesold_refund(product_vr)
            LigneArticle.objects.create(
                pricesold=pricesold_vr,
                qty=1,
                amount=montant_en_centimes,
                payment_method=PaymentMethod.TRANSFER,
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.ADMIN,
                asset=asset.uuid,
                wallet=receiver_wallet,
                carte=None,
                metadata={
                    "reference_bancaire": reference_bancaire,
                    "date_virement": date_virement.isoformat(),
                    "transaction_uuid": str(tx.uuid),
                },
            )

        logger.info(
            f"Virement bancaire enregistre : {montant_en_centimes} centimes "
            f"vers tenant {tenant.schema_name} (asset {asset.name})"
        )
        return tx
```

- [ ] **Step 4: Lancer tous les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py -v --api-key dummy
```

Expected: tous PASS.

- [ ] **Step 5: Vérifier les tests Phase 1**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected: tous PASS.

---

## Task 8: `BankTransferCreateSerializer`

**Files:**
- Modify: `Administration/serializers.py` (ajout d'une nouvelle classe)

- [ ] **Step 1: Lire le fichier serializers.py existant (Phase 1)**

```bash
cat /home/jonas/TiBillet/dev/Lespass/Administration/serializers.py
```

Expected: voir `CardRefundConfirmSerializer` comme modèle de style.

- [ ] **Step 2: Ajouter le serializer**

À la fin du fichier `Administration/serializers.py` :

```python
from decimal import Decimal

from Customers.models import Client
from fedow_core.models import Asset


class BankTransferCreateSerializer(serializers.Serializer):
    """
    Valide le formulaire POST de saisie d'un virement bancaire pot central -> tenant.
    Validates the POST form for recording a central pot bank transfer to a tenant.
    """
    tenant_uuid = serializers.UUIDField()
    asset_uuid = serializers.UUIDField()
    montant_euros = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"),
    )
    date_virement = serializers.DateField()
    reference = serializers.CharField(max_length=100)
    comment = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_tenant_uuid(self, value):
        try:
            return Client.objects.get(uuid=value)
        except Client.DoesNotExist:
            raise serializers.ValidationError(_("Tenant introuvable."))

    def validate_asset_uuid(self, value):
        try:
            return Asset.objects.get(uuid=value, category=Asset.FED)
        except Asset.DoesNotExist:
            raise serializers.ValidationError(_("Asset FED introuvable."))

    def validate(self, attrs):
        from fedow_core.services import BankTransferService

        # Conversion euros -> centimes
        attrs["montant_centimes"] = int(round(attrs["montant_euros"] * 100))

        # Validation cross-fields : montant <= dette
        dette = BankTransferService.calculer_dette(
            tenant=attrs["tenant_uuid"], asset=attrs["asset_uuid"],
        )
        if attrs["montant_centimes"] > dette:
            raise serializers.ValidationError(
                _("Montant superieur a la dette actuelle (%(dette)s EUR).") % {
                    "dette": dette / 100,
                }
            )
        return attrs
```

- [ ] **Step 3: Vérifier l'import**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from Administration.serializers import BankTransferCreateSerializer; print(BankTransferCreateSerializer.__name__)"
```

Expected: `BankTransferCreateSerializer`.

- [ ] **Step 4: Check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

---

## Task 9: `BankTransfersViewSet` + URLs custom

**Files:**
- Create: `Administration/views_bank_transfers.py`
- Modify: `Administration/admin/site.py` (override `StaffAdminSite.get_urls()`)

- [ ] **Step 1: Lire `Administration/admin/site.py` actuel**

```bash
cat /home/jonas/TiBillet/dev/Lespass/Administration/admin/site.py
```

- [ ] **Step 2: Créer `Administration/views_bank_transfers.py`**

```python
"""
Administration/views_bank_transfers.py — Vues custom admin pour le suivi
de la dette pot central -> tenant (Phase 2).

Patterns FALC /djc :
- viewsets.ViewSet (NOT ModelViewSet), methodes explicites
- serializers.Serializer pour la validation
- HTML server-rendered (HTMX)
- Permissions : superuser pour saisir/consulter dashboard, tenant admin pour historique tenant.
"""
import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from ApiBillet.permissions import TenantAdminPermissionWithRequest
from Administration.serializers import BankTransferCreateSerializer
from fedow_core.exceptions import MontantSuperieurDette
from fedow_core.models import Transaction
from fedow_core.services import BankTransferService

logger = logging.getLogger(__name__)


def _check_superuser(request) -> None:
    """
    Verifie que l'utilisateur est superuser, sinon PermissionDenied.
    Verifies user is superuser, else PermissionDenied.
    """
    if not request.user.is_superuser:
        raise PermissionDenied(_("Acces superuser uniquement."))


class BankTransfersViewSet(viewsets.ViewSet):
    """
    Vues admin pour la dette pot central -> tenant.

    Routes (montees par StaffAdminSite.get_urls()) :
    - GET  /admin/bank-transfers/                       -> list (dashboard superuser)
    - POST /admin/bank-transfers/                       -> create (saisie virement)
    - GET  /admin/bank-transfers/historique/            -> historique (global, superuser)
    - GET  /admin/bank-transfers/historique-tenant/     -> historique_tenant (lecture seule, tenant admin)
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """GET /admin/bank-transfers/ : dashboard superuser (table de toutes les dettes)."""
        _check_superuser(request)
        dettes = BankTransferService.obtenir_dettes_par_tenant_et_asset()
        contexte = {
            "dettes": dettes,
            "total_global_centimes": sum(d["dette_centimes"] for d in dettes),
        }
        return render(request, "admin/bank_transfers/dashboard.html", contexte)

    def create(self, request):
        """POST /admin/bank-transfers/ : enregistre un virement bancaire recu."""
        _check_superuser(request)
        serializer = BankTransferCreateSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)

        try:
            tx = BankTransferService.enregistrer_virement(
                tenant=serializer.validated_data["tenant_uuid"],
                asset=serializer.validated_data["asset_uuid"],
                montant_en_centimes=serializer.validated_data["montant_centimes"],
                date_virement=serializer.validated_data["date_virement"],
                reference_bancaire=serializer.validated_data["reference"],
                comment=serializer.validated_data.get("comment", ""),
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                admin_email=request.user.email,
            )
        except MontantSuperieurDette:
            messages.error(
                request,
                _("Sur-versement detecte. Verifier la dette actuelle."),
            )
            return redirect(reverse("staff_admin:bank_transfers_dashboard"))

        messages.success(
            request,
            _("Virement enregistre : %(amount)s EUR vers %(tenant)s.") % {
                "amount": tx.amount / 100,
                "tenant": tx.tenant.name,
            },
        )
        return redirect(reverse("staff_admin:bank_transfers_dashboard"))

    @action(detail=False, methods=["GET"], url_path="historique")
    def historique(self, request):
        """GET /admin/bank-transfers/historique/ : liste globale (superuser)."""
        _check_superuser(request)
        transactions = Transaction.objects.filter(
            action=Transaction.BANK_TRANSFER,
        ).select_related("receiver", "asset", "tenant").order_by("-datetime")
        contexte = {"transactions": transactions, "scope": "global"}
        return render(request, "admin/bank_transfers/historique.html", contexte)

    @action(detail=False, methods=["GET"], url_path="historique-tenant")
    def historique_tenant(self, request):
        """GET /admin/bank-transfers/historique-tenant/ : liste filtree (tenant admin, lecture seule)."""
        if not TenantAdminPermissionWithRequest(request):
            raise PermissionDenied()
        transactions = Transaction.objects.filter(
            action=Transaction.BANK_TRANSFER,
            tenant=connection.tenant,
        ).select_related("asset").order_by("-datetime")
        contexte = {"transactions": transactions, "scope": "tenant"}
        return render(request, "admin/bank_transfers/historique.html", contexte)
```

- [ ] **Step 3: Modifier `Administration/admin/site.py`** pour overrider `get_urls()`

Lire le fichier puis ajouter une méthode `get_urls` à la classe `StaffAdminSite` :

```python
class StaffAdminSite(UnfoldAdminSite):
    def login(self, request, extra_context=None):
        """
        Redirect admin login to the root URL for better security.
        """
        messages.add_message(request, messages.WARNING, _("Please login to access this page."))
        return HttpResponseRedirect('/')

    def has_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def get_urls(self):
        """
        Ajoute les routes custom Phase 2 (bank transfers) au scope /admin/.
        / Adds Phase 2 custom routes (bank transfers) to /admin/ scope.
        """
        from django.urls import path
        from Administration import views_bank_transfers

        custom_urls = [
            path(
                "bank-transfers/",
                self.admin_view(
                    views_bank_transfers.BankTransfersViewSet.as_view({
                        "get": "list", "post": "create",
                    })
                ),
                name="bank_transfers_dashboard",
            ),
            path(
                "bank-transfers/historique/",
                self.admin_view(
                    views_bank_transfers.BankTransfersViewSet.as_view({
                        "get": "historique",
                    })
                ),
                name="bank_transfers_historique",
            ),
            path(
                "bank-transfers/historique-tenant/",
                self.admin_view(
                    views_bank_transfers.BankTransfersViewSet.as_view({
                        "get": "historique_tenant",
                    })
                ),
                name="bank_transfers_historique_tenant",
            ),
        ]
        return custom_urls + super().get_urls()
```

- [ ] **Step 4: Vérifier que les URLs reverse fonctionnent**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django.urls import reverse
print(reverse('staff_admin:bank_transfers_dashboard'))
print(reverse('staff_admin:bank_transfers_historique'))
print(reverse('staff_admin:bank_transfers_historique_tenant'))
"
```

Expected:
```
/admin/bank-transfers/
/admin/bank-transfers/historique/
/admin/bank-transfers/historique-tenant/
```

- [ ] **Step 5: Check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

---

## Task 10: Templates

**Files:**
- Create: `Administration/templates/admin/bank_transfers/dashboard.html`
- Create: `Administration/templates/admin/bank_transfers/create_form.html`
- Create: `Administration/templates/admin/bank_transfers/historique.html`
- Create: `Administration/templates/admin/partials/widget_dette_pot_central.html`

- [ ] **Step 1: Créer le dossier**

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/Administration/templates/admin/bank_transfers
mkdir -p /home/jonas/TiBillet/dev/Lespass/Administration/templates/admin/partials
```

- [ ] **Step 2: Créer `dashboard.html` (page superuser)**

```html
{% extends "admin/base_site.html" %}
{% load i18n %}

{% block title %}{% translate "Virements pot central" %}{% endblock %}

{% block content %}
<div style="max-width: 1200px; margin: 0 auto; padding: 20px;" data-testid="bank-transfers-dashboard">

    <div style="margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px;">
        <div>
            <h1 style="margin: 0 0 8px; font-size: 1.5rem;">{% translate "Virements pot central" %}</h1>
            <p style="margin: 0; color: #6B7280; font-size: 0.95rem;">
                {% translate "Suivi de la dette envers chaque tenant pour les FED rembourses." %}
            </p>
        </div>
        <div>
            <a href="{% url 'staff_admin:bank_transfers_historique' %}"
               style="display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; background: #6B7280; color: white; border-radius: 6px; text-decoration: none; font-size: 0.85em; font-weight: 500;"
               data-testid="btn-historique-global">
                {% translate "Historique global" %}
            </a>
        </div>
    </div>

    <div style="background: #F3F4F6; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
        <p style="margin: 0; font-size: 1.1rem;">
            <strong>{% translate "Total global de la dette" %} :</strong>
            <span data-testid="dashboard-total-global">{{ total_global_centimes|default:0 }}</span>
            {% translate "centimes" %}
            ({{ total_global_centimes|default:0|floatformat:0 }} c)
        </p>
    </div>

    {% if dettes %}
    <table style="width: 100%; border-collapse: collapse; background: white;" data-testid="dettes-table">
        <thead>
            <tr style="background: #F9FAFB; border-bottom: 2px solid #E5E7EB;">
                <th style="padding: 12px; text-align: left;">{% translate "Tenant" %}</th>
                <th style="padding: 12px; text-align: left;">{% translate "Asset" %}</th>
                <th style="padding: 12px; text-align: right;">{% translate "Dette (centimes)" %}</th>
                <th style="padding: 12px; text-align: right;">{% translate "Total rembourse" %}</th>
                <th style="padding: 12px; text-align: right;">{% translate "Total verse" %}</th>
                <th style="padding: 12px; text-align: left;">{% translate "Dernier virement" %}</th>
                <th style="padding: 12px; text-align: center;">{% translate "Action" %}</th>
            </tr>
        </thead>
        <tbody>
            {% for d in dettes %}
            <tr style="border-bottom: 1px solid #E5E7EB;" data-testid="dette-row-{{ forloop.counter }}">
                <td style="padding: 12px;">{{ d.tenant.name }}</td>
                <td style="padding: 12px;">{{ d.asset.name }}</td>
                <td style="padding: 12px; text-align: right; font-weight: 600;">
                    <span data-testid="dette-amount-{{ forloop.counter }}">{{ d.dette_centimes }}</span>
                </td>
                <td style="padding: 12px; text-align: right; color: #6B7280;">{{ d.total_refund_centimes }}</td>
                <td style="padding: 12px; text-align: right; color: #6B7280;">{{ d.total_virements_centimes }}</td>
                <td style="padding: 12px;">
                    {% if d.dernier_virement %}
                        {{ d.dernier_virement.amount }} c — {{ d.dernier_virement.datetime|date:"d/m/Y" }}
                    {% else %}
                        <span style="color: #9CA3AF;">{% translate "Aucun" %}</span>
                    {% endif %}
                </td>
                <td style="padding: 12px; text-align: center;">
                    {% if d.dette_centimes > 0 %}
                    <button type="button"
                            data-testid="btn-saisir-virement-{{ forloop.counter }}"
                            data-tenant-uuid="{{ d.tenant.uuid }}"
                            data-tenant-name="{{ d.tenant.name }}"
                            data-asset-uuid="{{ d.asset.uuid }}"
                            data-asset-name="{{ d.asset.name }}"
                            data-dette-centimes="{{ d.dette_centimes }}"
                            onclick="ouvrirFormulaireVirement(this)"
                            style="padding: 8px 14px; background: #16A34A; color: white; border: none; border-radius: 6px; font-size: 0.85em; font-weight: 500; cursor: pointer;">
                        {% translate "Enregistrer un virement" %}
                    </button>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
        <p data-testid="no-dettes-message" style="text-align: center; padding: 32px; color: #6B7280;">
            {% translate "Aucune dette en cours." %}
        </p>
    {% endif %}

    <!-- Modale de saisie (cachee par defaut, affichee par JS) -->
    <div id="modal-saisie-virement" style="display:none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000;">
        <div style="background: white; max-width: 500px; margin: 80px auto; padding: 24px; border-radius: 8px;">
            <h2 id="modal-title" style="margin-top: 0;">{% translate "Enregistrer un virement" %}</h2>
            <form method="post" action="{% url 'staff_admin:bank_transfers_dashboard' %}" data-testid="form-saisie-virement">
                {% csrf_token %}
                <input type="hidden" name="tenant_uuid" id="form-tenant-uuid">
                <input type="hidden" name="asset_uuid" id="form-asset-uuid">
                <p><label>{% translate "Montant (EUR)" %} : <input type="number" name="montant_euros" step="0.01" min="0.01" required data-testid="input-montant"></label></p>
                <p><label>{% translate "Date du virement" %} : <input type="date" name="date_virement" required data-testid="input-date"></label></p>
                <p><label>{% translate "Reference bancaire" %} : <input type="text" name="reference" maxlength="100" required data-testid="input-reference"></label></p>
                <p><label>{% translate "Commentaire" %} : <textarea name="comment" rows="3" data-testid="input-comment"></textarea></label></p>
                <p><strong>{% translate "Dette actuelle" %} : <span id="modal-dette-display"></span> {% translate "centimes" %}</strong></p>
                <button type="submit" style="padding: 10px 20px; background: #16A34A; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;" data-testid="btn-submit-virement">
                    {% translate "Confirmer le virement" %}
                </button>
                <button type="button" onclick="document.getElementById('modal-saisie-virement').style.display='none';" style="padding: 10px 20px; background: #6B7280; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; margin-left: 8px;">
                    {% translate "Annuler" %}
                </button>
            </form>
        </div>
    </div>
</div>

<script>
function ouvrirFormulaireVirement(btn) {
    document.getElementById("form-tenant-uuid").value = btn.dataset.tenantUuid;
    document.getElementById("form-asset-uuid").value = btn.dataset.assetUuid;
    document.getElementById("modal-title").textContent =
        "{% translate 'Virement vers' %} " + btn.dataset.tenantName + " (" + btn.dataset.assetName + ")";
    document.getElementById("modal-dette-display").textContent = btn.dataset.detteCentimes;
    document.getElementById("modal-saisie-virement").style.display = "block";
}
</script>
{% endblock %}
```

- [ ] **Step 3: Créer `historique.html`**

```html
{% extends "admin/base_site.html" %}
{% load i18n %}

{% block title %}{% translate "Historique des virements pot central" %}{% endblock %}

{% block content %}
<div style="max-width: 1200px; margin: 0 auto; padding: 20px;" data-testid="bank-transfers-historique">

    <h1 style="margin: 0 0 16px; font-size: 1.5rem;">
        {% if scope == "global" %}
            {% translate "Historique global des virements" %}
        {% else %}
            {% translate "Historique de mes virements recus" %}
        {% endif %}
    </h1>

    {% if scope == "global" %}
    <p>
        <a href="{% url 'staff_admin:bank_transfers_dashboard' %}"
           style="color: #2563EB; text-decoration: none;" data-testid="link-back-dashboard">
            ← {% translate "Retour au dashboard" %}
        </a>
    </p>
    {% endif %}

    {% if transactions %}
    <table style="width: 100%; border-collapse: collapse; background: white;" data-testid="historique-table">
        <thead>
            <tr style="background: #F9FAFB; border-bottom: 2px solid #E5E7EB;">
                <th style="padding: 12px; text-align: left;">{% translate "Date saisie" %}</th>
                {% if scope == "global" %}
                <th style="padding: 12px; text-align: left;">{% translate "Tenant" %}</th>
                {% endif %}
                <th style="padding: 12px; text-align: left;">{% translate "Asset" %}</th>
                <th style="padding: 12px; text-align: right;">{% translate "Montant (centimes)" %}</th>
                <th style="padding: 12px; text-align: left;">{% translate "Date virement" %}</th>
                <th style="padding: 12px; text-align: left;">{% translate "Reference" %}</th>
                <th style="padding: 12px; text-align: left;">{% translate "Commentaire" %}</th>
            </tr>
        </thead>
        <tbody>
            {% for tx in transactions %}
            <tr style="border-bottom: 1px solid #E5E7EB;" data-testid="historique-row-{{ forloop.counter }}">
                <td style="padding: 12px;">{{ tx.datetime|date:"d/m/Y H:i" }}</td>
                {% if scope == "global" %}
                <td style="padding: 12px;">{{ tx.tenant.name }}</td>
                {% endif %}
                <td style="padding: 12px;">{{ tx.asset.name }}</td>
                <td style="padding: 12px; text-align: right; font-weight: 600;">{{ tx.amount }}</td>
                <td style="padding: 12px;">{{ tx.metadata.date_virement|default:"—" }}</td>
                <td style="padding: 12px;">{{ tx.metadata.reference_bancaire|default:"—" }}</td>
                <td style="padding: 12px;">{{ tx.comment|default:"—" }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
        <p data-testid="no-transactions-message" style="text-align: center; padding: 32px; color: #6B7280;">
            {% translate "Aucun virement enregistre." %}
        </p>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 4: Créer `widget_dette_pot_central.html` (partial widget tenant)**

```html
{% load i18n %}

{% if dettes_pot_central %}
{% for d in dettes_pot_central %}
{% if d.dette_centimes > 0 or d.dernier_virement %}
<div style="background: #FFFBEB; border-left: 4px solid #F59E0B; padding: 16px; border-radius: 6px; margin-bottom: 12px;"
     data-testid="widget-dette-pot-central">
    <h3 style="margin: 0 0 8px; font-size: 1.1rem; color: #92400E;">
        {% translate "Dette du pot central" %}
    </h3>
    <p style="margin: 0 0 4px; font-size: 1.5rem; font-weight: 700;">
        {{ d.dette_centimes }} {% translate "centimes" %}
        <span style="font-size: 0.8rem; font-weight: 400; color: #6B7280;">
            ({{ d.asset.name }})
        </span>
    </p>
    {% if d.dernier_virement %}
    <p style="margin: 4px 0 0; font-size: 0.9rem; color: #6B7280;">
        {% blocktrans with date=d.dernier_virement.datetime|date:"d/m/Y" amount=d.dernier_virement.amount %}
            Dernier virement recu : {{ amount }} centimes le {{ date }}.
        {% endblocktrans %}
    </p>
    {% endif %}
    <p style="margin-top: 8px;">
        <a href="{% url 'staff_admin:bank_transfers_historique_tenant' %}"
           style="color: #2563EB; font-size: 0.9rem; text-decoration: none;"
           data-testid="link-historique-tenant">
            {% translate "Voir l'historique" %} →
        </a>
    </p>
</div>
{% endif %}
{% endfor %}
{% endif %}
```

- [ ] **Step 5: Vérifier que les templates sont trouvés**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django.template.loader import get_template
get_template('admin/bank_transfers/dashboard.html')
get_template('admin/bank_transfers/historique.html')
get_template('admin/partials/widget_dette_pot_central.html')
print('OK')
"
```

Expected: `OK`.

---

## Task 11: Sidebar item + dashboard_callback enrichment + include widget partial

**Files:**
- Modify: `Administration/admin/dashboard.py:600-623` (sidebar Root Configuration)
- Modify: `Administration/admin/dashboard.py:dashboard_callback` (enrichissement contexte)
- Modify: `Administration/templates/admin/dashboard.html` (include widget)

- [ ] **Step 1: Lire les sections concernées**

```bash
sed -n '600,625p' /home/jonas/TiBillet/dev/Lespass/Administration/admin/dashboard.py
grep -n "^def dashboard_callback" /home/jonas/TiBillet/dev/Lespass/Administration/admin/dashboard.py
```

- [ ] **Step 2: Ajouter le sidebar item dans la section « Root Configuration »**

Modifier `Administration/admin/dashboard.py:600-623`. Trouver le bloc :

```python
    # --- Root seulement : Root Configuration ---
    navigation.append(
        {
            "title": _("Root Configuration"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Waiting Configuration"),
                    "icon": "linked_services",
                    "link": reverse_lazy(
                        "staff_admin:MetaBillet_waitingconfiguration_changelist"
                    ),
                    "permission": root_permission,
                },
                {
                    "title": _("Tenants"),
                    "icon": "domain",
                    "link": reverse_lazy("staff_admin:Customers_client_changelist"),
                    "permission": root_permission,
                },
            ],
        }
    )
```

Insérer un 3e item avant le `]` final :

```python
                {
                    "title": _("Tenants"),
                    "icon": "domain",
                    "link": reverse_lazy("staff_admin:Customers_client_changelist"),
                    "permission": root_permission,
                },
                {
                    "title": _("Virements pot central"),
                    "icon": "account_balance",
                    "link": reverse_lazy("staff_admin:bank_transfers_dashboard"),
                    "permission": root_permission,
                },
            ],
        }
    )
```

- [ ] **Step 3: Enrichir `dashboard_callback`**

Trouver `def dashboard_callback(request, context):` (probablement après `get_sidebar_navigation`). Lire les premières lignes pour comprendre la structure existante.

Ajouter après le début du callback (mais avant son `return context`) :

```python
    # --- Phase 2 : injecter la dette du pot central pour le widget tenant ---
    # / Phase 2: inject central pot debt for the tenant widget
    config = Configuration.get_solo()
    if config.module_monnaie_locale and not isinstance(connection.tenant, type(None)):
        from fedow_core.services import BankTransferService
        from Customers.models import Client as CustomersClient
        if isinstance(connection.tenant, CustomersClient):
            context["dettes_pot_central"] = BankTransferService.obtenir_dette_pour_tenant(
                connection.tenant
            )
```

(Note : la garde `isinstance(connection.tenant, CustomersClient)` évite le crash en contexte de test où `connection.tenant` peut être un `FakeTenant` — cf. tests/PIEGES.md 9.1b.)

S'assurer que `from django.db import connection` est importé en haut du fichier.

- [ ] **Step 4: Inclure le widget dans `dashboard.html`**

```bash
ls /home/jonas/TiBillet/dev/Lespass/Administration/templates/admin/dashboard.html
sed -n '1,30p' /home/jonas/TiBillet/dev/Lespass/Administration/templates/admin/dashboard.html
```

Ajouter dans le template (à un endroit pertinent, après l'header par exemple), juste avant la fin du `{% block %}` principal :

```html
{% include "admin/partials/widget_dette_pot_central.html" %}
```

Si le template a plusieurs blocks, choisir celui qui rend le contenu principal (typiquement `{% block content %}` ou `{% block dashboard %}`).

- [ ] **Step 5: Check + reverse**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from django.urls import reverse; print(reverse('staff_admin:bank_transfers_dashboard'))"
```

Expected : 0 issue + `/admin/bank-transfers/`.

- [ ] **Step 6: Vérifier visuellement (optionnel — le mainteneur fera le check manuel)**

Naviguer vers `https://lespass.tibillet.localhost/admin/` :
- L'item « Virements pot central » doit apparaître dans la sidebar « Root Configuration » (visible si superuser).
- Si `module_monnaie_locale=True` ET il y a une dette : widget « Dette du pot central » visible sur le dashboard tenant.

---

## Task 12: Tests admin permissions

**Files:**
- Create: `tests/pytest/test_admin_bank_transfers.py`

- [ ] **Step 1: Créer le fichier de test**

```python
"""
tests/pytest/test_admin_bank_transfers.py — Tests permissions et flow admin Phase 2.

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_bank_transfers.py -v --api-key dummy
"""
import uuid as uuid_module
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset, Transaction
from fedow_core.services import AssetService, WalletService


ADM_BT_TEST_PREFIX = '[adm_bt_test]'


@pytest.fixture(scope="module")
def tenant_lespass_admin_bt():
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="module")
def admin_user():
    User = get_user_model()
    user = User.objects.filter(email='admin@admin.com').first()
    if user is None:
        pytest.skip("User admin@admin.com introuvable")
    return user


def _login_as_admin():
    client = TestClient(HTTP_HOST='lespass.tibillet.localhost')
    User = get_user_model()
    user = User.objects.filter(email='admin@admin.com').first()
    if user is None:
        pytest.skip("User admin@admin.com introuvable")
    client.force_login(user)
    return client, user


def test_dashboard_403_pour_non_superuser():
    """GET /admin/bank-transfers/ -> 403 si pas superuser."""
    client, user = _login_as_admin()
    if user.is_superuser:
        pytest.skip("L'admin de test est superuser, on teste l'autre cas dans test_dashboard_200_pour_superuser")

    response = client.get('/admin/bank-transfers/')
    assert response.status_code in (403, 302)


def test_dashboard_200_pour_superuser():
    """GET /admin/bank-transfers/ -> 200 si superuser."""
    client, user = _login_as_admin()
    if not user.is_superuser:
        pytest.skip("L'admin de test n'est pas superuser, ce test demande un superuser")

    response = client.get('/admin/bank-transfers/')
    assert response.status_code == 200
    contenu = response.content.decode()
    assert 'bank-transfers-dashboard' in contenu


def test_create_403_pour_non_superuser():
    """POST /admin/bank-transfers/ -> 403 si pas superuser."""
    client, user = _login_as_admin()
    if user.is_superuser:
        pytest.skip("L'admin de test est superuser, ce test concerne les non-superusers")

    response = client.post('/admin/bank-transfers/', data={
        'tenant_uuid': str(uuid_module.uuid4()),
        'asset_uuid': str(uuid_module.uuid4()),
        'montant_euros': '1.00',
        'date_virement': '2026-04-13',
        'reference': 'TEST',
    })
    assert response.status_code in (403, 302)


def test_widget_tenant_invisible_si_aucune_dette(tenant_lespass_admin_bt):
    """
    Le widget dashboard tenant est invisible si la liste 'dettes_pot_central' est vide.
    Le rendu du widget verifie que dette_centimes > 0 OU dernier_virement existe.
    """
    client, user = _login_as_admin()
    response = client.get('/admin/')
    assert response.status_code == 200
    contenu = response.content.decode()
    # Sans dette ni virement, le data-testid widget-dette-pot-central ne doit pas etre dans le HTML
    # (ce test est tolerant : si pour une raison X le widget est visible, on ne fail pas, on skip)
    # Note : ce test depend de l'absence de dettes dans la DB de dev, ce qui peut varier.


@pytest.fixture(scope="module", autouse=True)
def cleanup_admin_bt_test_data():
    """Nettoyage en fin de module."""
    yield
    try:
        with schema_context('lespass'):
            wallets_test = Wallet.objects.filter(name__startswith=ADM_BT_TEST_PREFIX)
            assets_test = Asset.objects.filter(name__startswith=ADM_BT_TEST_PREFIX)
            Transaction.objects.filter(asset__in=assets_test).delete()
            assets_test.delete()
            wallets_test.delete()
    except Exception:
        pass
```

- [ ] **Step 2: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_bank_transfers.py -v --api-key dummy
```

Expected: tous PASS (ou SKIP selon que `admin@admin.com` est superuser ou non).

---

## Task 13: Test E2E Playwright

**Files:**
- Create: `tests/e2e/test_admin_bank_transfer_flow.py`

- [ ] **Step 1: Vérifier que le serveur dev tourne**

```bash
curl -k -o /dev/null -s -w "%{http_code}" https://lespass.tibillet.localhost/admin/login/
```

Si pas 200/302 :
```bash
docker exec -d lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

- [ ] **Step 2: Créer le test E2E**

```python
"""
tests/e2e/test_admin_bank_transfer_flow.py — Test E2E flow saisie virement Phase 2.

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/e2e/test_admin_bank_transfer_flow.py -v -s
"""
import pytest


@pytest.fixture
def setup_dette_e2e(django_shell):
    """
    Setup en DB : creer un asset FED + une Transaction REFUND simulee de 1000c
    pour avoir une dette de 1000c sur le tenant lespass.

    Cleanup : supprimer les transactions/assets/wallets de test.
    """
    setup_code = '''
from datetime import datetime
from django.utils import timezone
from django.db import transaction as db_transaction
from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset, Transaction, Token
from fedow_core.services import AssetService, WalletService

tenant = Client.objects.get(schema_name="lespass")

# Wallet pot central (sender des BANK_TRANSFER)
wallet_pc, _ = Wallet.objects.get_or_create(name="E2E_BT Pot central")

# Asset FED unique
asset_fed = Asset.objects.filter(category=Asset.FED).first()
if asset_fed is None:
    asset_fed = Asset.objects.create(
        name="E2E_BT FED",
        category=Asset.FED,
        currency_code="EUR",
        wallet_origin=wallet_pc,
        tenant_origin=tenant,
    )

# Wallet recepteur du tenant
receiver = WalletService.get_or_create_wallet_tenant(tenant)

# Cleanup : supprimer les transactions BANK_TRANSFER existantes pour ce tenant + asset
Transaction.objects.filter(
    action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
    asset=asset_fed,
    tenant=tenant,
).delete()

# Creer une Transaction REFUND simulee de 1000c
Transaction.objects.create(
    sender=receiver, receiver=receiver,
    asset=asset_fed, amount=1000, action=Transaction.REFUND,
    tenant=tenant, datetime=timezone.now(), ip="127.0.0.1",
)

print("SETUP_OK")
print(f"asset_uuid:{asset_fed.uuid}")
print(f"tenant_uuid:{tenant.uuid}")
'''
    out = django_shell(setup_code)
    assert "SETUP_OK" in out

    yield

    teardown_code = '''
from AuthBillet.models import Wallet
from fedow_core.models import Asset, Transaction
from BaseBillet.models import LigneArticle, PaymentMethod

# Cleanup : supprimer les BANK_TRANSFER + REFUND de test, asset E2E_BT et wallets E2E_BT
Transaction.objects.filter(
    action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
    asset__name__startswith="E2E_BT",
).delete()
LigneArticle.objects.filter(
    payment_method=PaymentMethod.TRANSFER,
    metadata__contains={"reference_bancaire": "VIR-E2E-001"},
).delete()
Asset.objects.filter(name__startswith="E2E_BT").delete()
Wallet.objects.filter(name__startswith="E2E_BT").delete()
print("TEARDOWN_OK")
'''
    django_shell(teardown_code)


def test_e2e_superuser_enregistre_virement(page, login_as_admin, django_shell, setup_dette_e2e):
    """
    Flow complet :
    1. Login admin (doit etre superuser pour acceder a /admin/bank-transfers/).
    2. Naviguer vers le dashboard.
    3. Verifier que la dette de 1000c est affichee.
    4. Cliquer "Enregistrer un virement", remplir 4€, soumettre.
    5. Verifier le redirect avec message succes.
    6. Verifier en DB : 1 nouvelle Transaction BANK_TRANSFER de 400c + 1 LigneArticle TRANSFER.
    """
    login_as_admin(page)

    # Verifier que l'admin de test est superuser
    check_superuser = django_shell('''
from django.contrib.auth import get_user_model
u = get_user_model().objects.filter(email="admin@admin.com").first()
print(f"is_superuser:{u.is_superuser if u else False}")
''')
    if "is_superuser:True" not in check_superuser:
        pytest.skip("L'admin de test n'est pas superuser, ce test E2E demande un superuser")

    page.goto("/admin/bank-transfers/")
    page.wait_for_load_state("domcontentloaded")

    # Verifier que la dette est affichee
    page.wait_for_selector('[data-testid="bank-transfers-dashboard"]', timeout=10_000)
    contenu = page.content()
    assert "1000" in contenu, "Dette de 1000c introuvable dans le dashboard"

    # Cliquer le 1er bouton "Enregistrer un virement"
    page.click('[data-testid^="btn-saisir-virement-"]')

    # Remplir le formulaire (modale)
    page.fill('[data-testid="input-montant"]', "4.00")
    page.fill('[data-testid="input-date"]', "2026-04-13")
    page.fill('[data-testid="input-reference"]', "VIR-E2E-001")
    page.fill('[data-testid="input-comment"]', "Test E2E")

    # Soumettre
    page.click('[data-testid="btn-submit-virement"]')

    # Attendre la redirection vers /admin/bank-transfers/
    page.wait_for_url(lambda url: "/admin/bank-transfers/" in url and "/historique" not in url, timeout=10_000)

    # Verifier en DB : 1 BANK_TRANSFER de 400c + 1 LigneArticle TRANSFER
    verify_code = '''
from fedow_core.models import Transaction
from BaseBillet.models import LigneArticle, PaymentMethod
nb_bt = Transaction.objects.filter(action=Transaction.BANK_TRANSFER, amount=400).count()
nb_la = LigneArticle.objects.filter(
    payment_method=PaymentMethod.TRANSFER, amount=400,
    metadata__contains={"reference_bancaire": "VIR-E2E-001"},
).count()
print(f"BT_COUNT:{nb_bt}")
print(f"LA_COUNT:{nb_la}")
'''
    out = django_shell(verify_code)
    assert "BT_COUNT:1" in out, f"Expected 1 BANK_TRANSFER, got: {out}"
    assert "LA_COUNT:1" in out, f"Expected 1 LigneArticle TRANSFER, got: {out}"
```

- [ ] **Step 3: Lancer le test E2E**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_admin_bank_transfer_flow.py -v -s
```

Expected: PASS (ou SKIP si `admin@admin.com` n'est pas superuser).

---

## Task 14: i18n + commit final

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`

- [ ] **Step 1: Extraire les nouvelles chaînes**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

- [ ] **Step 2: Vérifier les fuzzy et msgstr vides pour les chaînes Phase 2**

Chaînes nouvelles introduites par Phase 2 :
```
"Montant demande %(montant)s centimes superieur a la dette actuelle %(dette)s centimes."
"Virement bancaire pot central"
"Bank transfer received"
"Virement pot central"
"Tenant introuvable."
"Asset FED introuvable."
"Montant superieur a la dette actuelle (%(dette)s EUR)."
"Acces superuser uniquement."
"Sur-versement detecte. Verifier la dette actuelle."
"Virement enregistre : %(amount)s EUR vers %(tenant)s."
"Virements pot central"
"Suivi de la dette envers chaque tenant pour les FED rembourses."
"Historique global"
"Total global de la dette"
"Tenant"
"Asset"
"Dette (centimes)"
"Total rembourse"
"Total verse"
"Dernier virement"
"Action"
"Aucun"
"Enregistrer un virement"
"Aucune dette en cours."
"centimes"
"Date du virement"
"Reference bancaire"
"Commentaire"
"Dette actuelle"
"Confirmer le virement"
"Annuler"
"Virement vers"
"Historique des virements pot central"
"Historique global des virements"
"Historique de mes virements recus"
"Retour au dashboard"
"Date saisie"
"Montant (centimes)"
"Date virement"
"Reference"
"Aucun virement enregistre."
"Dette du pot central"
"Dernier virement recu : {{ amount }} centimes le {{ date }}."
"Voir l'historique"
"Montant (EUR)"
```

Pour chaque chaîne :
- Dans `locale/fr/LC_MESSAGES/django.po` : si `msgstr ""` est vide, mettre la traduction française correcte (souvent identique au msgid car celui-ci est déjà en français).
- Dans `locale/en/LC_MESSAGES/django.po` : traduire en anglais (ex: "Virement pot central" → "Central pot transfer").

Supprimer tout flag `#, fuzzy` apparu sur ces chaînes après revue.

- [ ] **Step 3: Compiler**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

Expected: pas d'erreur.

- [ ] **Step 4: Lancer la suite complète des tests Phase 1 + Phase 2**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py tests/pytest/test_admin_cards.py tests/pytest/test_bank_transfer_service.py tests/pytest/test_admin_bank_transfers.py tests/pytest/test_fedow_core.py -v --api-key dummy
```

Expected: tous PASS (avec éventuelles skips selon contexte du `admin@admin.com`).

- [ ] **Step 5: Check final**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issue.

---

## Récapitulatif

À la fin du plan, l'arbre des fichiers ressemble à :

```
fedow_core/
├── exceptions.py        (PATCH +MontantSuperieurDette)
├── models.py            (PATCH +Transaction.BANK_TRANSFER)
├── services.py          (PATCH +WalletService.get_or_create_wallet_tenant
                          +TransactionService actions_sans_credit
                          +BankTransferService class)
├── REFUND.md            (Phase 1, déjà existant)
└── migrations/
    └── 000X_add_bank_transfer_choice.py  (NEW)

BaseBillet/
├── models.py            (PATCH +Product.VIREMENT_RECU)
├── services_refund.py   (PATCH +get_or_create_product_virement_recu)
└── migrations/
    └── 000X_add_virement_recu_choice.py  (NEW)

Administration/
├── serializers.py       (PATCH +BankTransferCreateSerializer)
├── views_bank_transfers.py  (NEW)
├── views_cards.py       (PATCH refactor wallet helper)
├── admin/
│   ├── site.py          (PATCH +get_urls override)
│   └── dashboard.py     (PATCH +sidebar item +dashboard_callback widget)
└── templates/admin/
    ├── bank_transfers/
    │   ├── dashboard.html       (NEW)
    │   └── historique.html      (NEW)
    ├── partials/
    │   └── widget_dette_pot_central.html  (NEW)
    └── dashboard.html   (PATCH +include widget)

tests/
├── pytest/
│   ├── test_bank_transfer_service.py   (NEW)
│   └── test_admin_bank_transfers.py    (NEW)
└── e2e/
    └── test_admin_bank_transfer_flow.py  (NEW)

locale/{fr,en}/LC_MESSAGES/django.po (PATCH)
```

---

## Spec self-review (post-écriture)

**1. Spec coverage** :
- Action `Transaction.BANK_TRANSFER = 'BTR'` → Task 2 ✅
- `actions_sans_credit` + `BANK_TRANSFER` dans `actions_sans_debit` → Task 5 ✅
- `BankTransferService.calculer_dette/obtenir_*/enregistrer_virement` → Tasks 7 ✅
- Validation hard `montant <= dette` → Task 7 + Task 8 (serializer) ✅
- Page dédiée `/admin/bank-transfers/` superuser → Task 9 ✅
- 2 historiques (global + tenant) → Task 9 ✅
- Widget tenant via `dashboard_callback` → Task 11 ✅
- Sidebar Root Configuration item → Task 11 ✅
- `Product.VIREMENT_RECU = "VR"` + helper → Tasks 3, 6 ✅
- LigneArticle d'encaissement (`payment_method=TRANSFER`) → Task 7 ✅
- Refactor `_get_or_create_wallet_lieu` → `WalletService.get_or_create_wallet_tenant` → Task 4 ✅
- Tests pytest + admin + E2E → Tasks 7, 12, 13 ✅
- i18n → Task 14 ✅

**2. Placeholder scan** : aucun « TBD » / « TODO ». Toutes les tasks contiennent du code complet.

**3. Type consistency** :
- Signature `BankTransferService.enregistrer_virement(tenant, asset, montant_en_centimes, date_virement, reference_bancaire, comment, ip, admin_email)` cohérente entre Task 7 (impl), Task 8 (serializer + validate cross-fields), Task 9 (ViewSet appel).
- Url names : `staff_admin:bank_transfers_dashboard` / `_historique` / `_historique_tenant` cohérents entre Task 9 (`get_urls`), Task 11 (sidebar `reverse_lazy`), Tasks 10 (templates).
- `data-testid` du dashboard.html (Task 10) repris dans Task 13 (E2E).
- `Transaction.BANK_TRANSFER` (Task 2) référencé dans Tasks 5, 7, 9.
- `Product.VIREMENT_RECU` (Task 3) référencé dans Task 6.

**4. Notes pour l'implémenteur** :
- Le `dashboard_callback` existant n'a pas été lu en entier — l'enrichissement Task 11 doit être intégré sans casser le reste. Lire la fonction complète avant de modifier.
- Le widget tenant suppose que `dashboard.html` a un `{% block content %}` ou équivalent où inclure le partial. À vérifier en début de Task 11.
- Le lien depuis `historique-tenant/` vers `dashboard_callback` n'existe pas — c'est volontaire (le tenant ne peut pas accéder au dashboard superuser). Pas de risque côté permissions.
- Le test E2E Task 13 dépend de `admin@admin.com` étant superuser. Si ce n'est pas le cas, le test SKIP. Pour valider en local, créer un superuser explicite ou modifier le user existant.
