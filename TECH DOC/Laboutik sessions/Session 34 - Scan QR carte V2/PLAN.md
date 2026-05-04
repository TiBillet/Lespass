# Scan QR carte V2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Contrainte projet : AUCUNE opération git (commit, add, push, stash, checkout, reset) ne doit être exécutée.** Le mainteneur gère tous les commits. Les tâches n'incluent PAS d'étapes de commit.

**Goal :** Remplacer les appels HTTP vers le serveur Fedow legacy par des appels directs à `fedow_core/services.py` pour le flow public de scan QR de carte cashless (scan, identification user, fusion wallet éphémère, perte de carte). Coexistence V1/V2 gardée via `Configuration.server_cashless`.

**Architecture :** Nouveau `CarteService` dans `fedow_core/services.py` avec 3 méthodes (`scanner_carte`, `lier_a_user`, `declarer_perdue`). Les 4 vues concernées dans `BaseBillet/views.py` dispatchent entre `fedow_connect` (V1) et `fedow_core` (V2) selon la présence de `Configuration.server_cashless`. Aucun changement de modèle. Fusion déléguée à `WalletService.fusionner_wallet_ephemere()` déjà existant (Phase 0).

**Tech Stack :** Django 5, DRF ViewSet, pytest DB-only, Playwright E2E, django-tenants (SHARED_APPS pour `fedow_core`, `AuthBillet`, `QrcodeCashless`).

**Référence spec :** `TECH DOC/Laboutik sessions/Session 34 - Scan QR carte V2/SPEC_SCAN_QR_CARTE_V2.md`

---

## File Structure

### À créer

| Fichier | Responsabilité |
|---|---|
| `tests/pytest/test_scan_qr_carte_v2.py` | 15 tests DB-only (service + dispatch vue) |
| `tests/e2e/test_scan_qr_carte_v2.py` | 3 scénarios Playwright |
| `A TESTER et DOCUMENTER/scan-qr-carte-v2.md` | Checklist de tests manuels |
| `fedow_core/CARTES.md` | Doc mécanique wallet éphémère + fusion |
| `TECH DOC/Laboutik sessions/Session 34 - Scan QR carte V2/JOURNAL.md` | Journal de session |

### À modifier

| Fichier | Changement |
|---|---|
| `fedow_core/exceptions.py` | +3 exceptions métier |
| `fedow_core/services.py` | +classe `CarteService` (3 méthodes) |
| `BaseBillet/views.py` | Dispatch V1/V2 dans 4 vues |
| `CHANGELOG.md` | Entrée Session 34 |
| `locale/fr/LC_MESSAGES/django.po` | +3 chaînes i18n |
| `locale/en/LC_MESSAGES/django.po` | +3 chaînes i18n |

### Inchangés (vérification uniquement)

- `QrcodeCashless/models.py` — `CarteCashless` schema inchangé (Option 3 YAGNI)
- `fedow_core/models.py` — `Transaction.FUSION` déjà dans `ACTION_CHOICES`
- Templates (`reunion/views/register.html`, `htmx/views/inscription.html`) — contrat vue inchangé

---

## Task 1 : Exceptions métier

**Files :**
- Modify : `fedow_core/exceptions.py`
- Test : aucun (import + instanciation testés dans les tasks suivantes)

### - [ ] Step 1.1 : Lire l'état actuel de `fedow_core/exceptions.py`

Run : lire le contenu complet du fichier pour repérer le pattern existant.

```bash
cat /home/jonas/TiBillet/dev/Lespass/fedow_core/exceptions.py
```

Expected : on a au minimum `SoldeInsuffisant(Exception)` avec `_()`.

### - [ ] Step 1.2 : Ajouter les 3 exceptions métier

Ajouter à la fin de `fedow_core/exceptions.py` (après les exceptions existantes) :

```python
class CarteIntrouvable(Exception):
    """
    Carte non trouvee ou pas liee au user demande.
    / Card not found or not linked to the requested user.

    LOCALISATION : fedow_core/exceptions.py
    Levee par : CarteService.declarer_perdue()
    """
    def __init__(self, message=None):
        super().__init__(message or _("Carte introuvable ou non liee a votre compte."))


class CarteDejaLiee(Exception):
    """
    Carte deja liee a un autre compte utilisateur.
    / Card already linked to another user account.

    LOCALISATION : fedow_core/exceptions.py
    Levee par : CarteService.lier_a_user() quand carte.user != user
    """
    def __init__(self, message=None):
        super().__init__(message or _("Cette carte est deja liee a un autre compte."))


class UserADejaCarte(Exception):
    """
    L'utilisateur a deja une autre carte liee a son compte.
    Protection anti-vol : empeche de lier plusieurs cartes avec un meme email.
    / User already has another card linked. Anti-theft protection.

    LOCALISATION : fedow_core/exceptions.py
    Levee par : CarteService.lier_a_user() quand user.cartecashless_set non vide
    """
    def __init__(self, message=None):
        super().__init__(message or _(
            "Vous avez deja une carte TiBillet liee a votre compte. "
            "Declarez-la perdue avant d'en associer une nouvelle."
        ))
```

Vérifier que l'import `from django.utils.translation import gettext_lazy as _` est présent en haut du fichier (l'ajouter sinon).

### - [ ] Step 1.3 : Vérifier l'import

Run :
```bash
docker exec lespass_django poetry run python -c "from fedow_core.exceptions import CarteIntrouvable, CarteDejaLiee, UserADejaCarte; print('OK')"
```

Expected : `OK` affiché, aucune erreur.

---

## Task 2 : `CarteService.scanner_carte()`

**Files :**
- Modify : `fedow_core/services.py` (ajouter classe `CarteService`)
- Test : `tests/pytest/test_scan_qr_carte_v2.py` (créer)

### - [ ] Step 2.1 : Lire la structure existante de `fedow_core/services.py`

Consulter la fin du fichier (après la dernière classe existante) pour identifier où ajouter `CarteService`.

Run :
```bash
grep -n "^class " /home/jonas/TiBillet/dev/Lespass/fedow_core/services.py
```

Expected : liste des classes existantes (AssetService, WalletService, TransactionService, RefillService...).

### - [ ] Step 2.2 : Créer le fichier de test

Créer `tests/pytest/test_scan_qr_carte_v2.py` :

```python
"""
Tests de CarteService (scanner_carte, lier_a_user, declarer_perdue).
/ Tests of CarteService (scan, link, declare lost).

LOCALISATION : tests/pytest/test_scan_qr_carte_v2.py

SCOPE :
- Remplacement des appels Fedow distants (fedow_connect) par fedow_core direct
- Scope A Session 34 : scan QR + identification user + perte
"""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import Configuration, Membership
from Customers.models import Client, Domain
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.exceptions import (
    CarteDejaLiee,
    CarteIntrouvable,
    UserADejaCarte,
)
from fedow_core.models import Asset, Token, Transaction

User = get_user_model()


# ------------------------------------------------------------------
# Fixtures
# / Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def tenant_origine(db):
    """
    Tenant qui sert de lieu d'origine pour les cartes de test.
    / Test tenant acting as card origin.
    """
    tenant = Client.objects.get(schema_name="lespass")
    return tenant


@pytest.fixture
def detail_cartes(db, tenant_origine):
    """
    Detail partage par toutes les cartes de test (lot de cartes).
    / Shared Detail for all test cards (card batch).
    """
    with tenant_context(tenant_origine):
        detail, _ = Detail.objects.get_or_create(
            base_url="test.tibillet.localhost",
            defaults={"origine": tenant_origine, "generation": 1},
        )
        return detail


@pytest.fixture
def carte_vierge(db, detail_cartes):
    """
    Carte neuve sans user ni wallet_ephemere.
    / Blank card, no user, no wallet_ephemere.
    """
    return CarteCashless.objects.create(
        tag_id=uuid.uuid4().hex[:8].upper(),
        number=uuid.uuid4().hex[:8].upper(),
        uuid=uuid.uuid4(),
        detail=detail_cartes,
    )


@pytest.fixture
def user_tout_neuf(db):
    """
    Un user sans wallet ni carte (cas du nouvel inscrit).
    / A user without wallet or card (fresh sign-up).
    """
    return User.objects.create_user(
        email=f"user-{uuid.uuid4().hex[:6]}@test.local",
        password="testpass123",
    )


@pytest.fixture
def asset_tlf(db, tenant_origine):
    """
    Asset TLF (Token Local Fiduciaire) pour tester les fusions avec tokens.
    / TLF asset (Local Fiduciary Token) for testing fusion with tokens.
    """
    wallet_lieu = Wallet.objects.create(
        origin=tenant_origine, name="Wallet lieu test",
    )
    return Asset.objects.create(
        name="TLF Test",
        currency_code="EUR",
        category=Asset.TLF,
        wallet_origin=wallet_lieu,
        tenant_origin=tenant_origine,
    )


# ------------------------------------------------------------------
# Tests — CarteService.scanner_carte
# / Tests — CarteService.scanner_carte
# ------------------------------------------------------------------

def test_scan_carte_vierge_cree_wallet_ephemere(carte_vierge, tenant_origine):
    """
    Un scan sur carte vierge cree un wallet_ephemere et l'attache.
    / A scan on a blank card creates a wallet_ephemere and attaches it.
    """
    from fedow_core.services import CarteService

    resultat = CarteService.scanner_carte(carte_vierge, tenant_origine)

    assert resultat.is_wallet_ephemere is True
    assert resultat.wallet is not None
    carte_vierge.refresh_from_db()
    assert carte_vierge.wallet_ephemere is not None
    assert carte_vierge.wallet_ephemere.pk == resultat.wallet.pk
    assert carte_vierge.wallet_ephemere.origin == tenant_origine


def test_scan_idempotent_sur_carte_vierge(carte_vierge, tenant_origine):
    """
    Deux scans successifs sur la meme carte ne recreent pas le wallet_ephemere.
    / Two consecutive scans do not recreate wallet_ephemere.
    """
    from fedow_core.services import CarteService

    r1 = CarteService.scanner_carte(carte_vierge, tenant_origine)
    r2 = CarteService.scanner_carte(carte_vierge, tenant_origine)

    assert r1.wallet.pk == r2.wallet.pk


def test_scan_carte_identifiee_retourne_wallet_user(carte_vierge, tenant_origine, user_tout_neuf):
    """
    Scan sur carte avec user identifie retourne le wallet du user et is_wallet_ephemere=False.
    / Scan on identified card returns the user's wallet and is_wallet_ephemere=False.
    """
    from fedow_core.services import CarteService

    wallet_user = Wallet.objects.create(origin=tenant_origine)
    user_tout_neuf.wallet = wallet_user
    user_tout_neuf.save()

    carte_vierge.user = user_tout_neuf
    carte_vierge.save()

    resultat = CarteService.scanner_carte(carte_vierge, tenant_origine)

    assert resultat.is_wallet_ephemere is False
    assert resultat.wallet.pk == wallet_user.pk
```

### - [ ] Step 2.3 : Lancer les tests pour vérifier qu'ils échouent

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : 3 tests en ERROR (ImportError sur `CarteService`).

### - [ ] Step 2.4 : Implémenter `CarteService.scanner_carte()`

Ajouter à la fin de `fedow_core/services.py` (avant le dernier bloc de commentaires s'il y en a) :

```python
# ==========================================================================
# CarteService — Service carte cashless (scan QR + identification + perte)
# Session 34 (2026-04-20)
# / CarteService — Cashless card service (QR scan + user link + lost)
# ==========================================================================

from dataclasses import dataclass

from QrcodeCashless.models import CarteCashless
from fedow_core.exceptions import (
    CarteDejaLiee,
    CarteIntrouvable,
    UserADejaCarte,
)


@dataclass
class ScanResult:
    """
    Resultat d'un scan de carte. Contient le wallet resolu et si c'est ephemere.
    / Result of a card scan. Contains resolved wallet and ephemeral flag.

    LOCALISATION : fedow_core/services.py
    """
    wallet: Wallet
    is_wallet_ephemere: bool


class CarteService:
    """
    Service de gestion des cartes cashless (scan QR, identification, perte).
    Remplace les appels vers fedow_connect/NFCcardFedow pour les tenants V2.
    / Cashless card management service. Replaces fedow_connect calls for V2 tenants.

    LOCALISATION : fedow_core/services.py

    Decisions architecturales (cf. SPEC_SCAN_QR_CARTE_V2.md) :
    - Aucune modification de schema CarteCashless
    - CarteCashless.uuid sert d'identifiant public (qrcode_uuid)
    - Wallet ephemere cree a la volee sur carte vierge
    - Fusion deleguee a WalletService.fusionner_wallet_ephemere()
    """

    @staticmethod
    def scanner_carte(carte, tenant_origine, ip="0.0.0.0"):
        """
        Resout le wallet d'une carte. Cree un wallet_ephemere si carte vierge.
        / Resolves a card's wallet. Creates a wallet_ephemere if card is blank.

        Retourne ScanResult(wallet, is_wallet_ephemere).

        :param carte: CarteCashless
        :param tenant_origine: Client (tenant d'origine de la carte, = carte.detail.origine)
        :param ip: str (IP de la requete, pour tracabilite future)
        :return: ScanResult
        """
        # --- Carte identifiee : wallet du user ---
        # Nota : user.wallet peut etre None (user inscrit sans wallet encore).
        # Dans ce cas on bascule sur la branche wallet_ephemere ou creation.
        # / Identified card: user's wallet (may be None — fall back below).
        carte_est_identifiee = carte.user is not None and carte.user.wallet is not None
        if carte_est_identifiee:
            return ScanResult(wallet=carte.user.wallet, is_wallet_ephemere=False)

        # --- Carte anonyme deja scannee : wallet ephemere existant ---
        # / Anonymous card already scanned: existing wallet_ephemere.
        if carte.wallet_ephemere is not None:
            return ScanResult(wallet=carte.wallet_ephemere, is_wallet_ephemere=True)

        # --- Carte vierge : creer un wallet_ephemere et l'attacher ---
        # Le wallet ephemere n'a pas de reverse user (champ OneToOne sur TibilletUser
        # reste None). Son origin est le tenant d'origine de la carte.
        # / Blank card: create a wallet_ephemere and attach it. Origin = card origin tenant.
        nouveau_wallet_ephemere = Wallet.objects.create(
            origin=tenant_origine,
            name=f"Wallet ephemere carte {carte.number}",
        )
        carte.wallet_ephemere = nouveau_wallet_ephemere
        carte.save(update_fields=["wallet_ephemere"])
        return ScanResult(wallet=nouveau_wallet_ephemere, is_wallet_ephemere=True)
```

**Note** : Si les imports `Wallet`, `Transaction`, `Token`, etc. ne sont pas déjà en haut du fichier, les ajouter. Vérifier avec `grep -n "^from\|^import" fedow_core/services.py`.

### - [ ] Step 2.5 : Relancer les tests pour vérifier qu'ils passent

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : 3 tests PASS.

### - [ ] Step 2.6 : Vérifier Django check

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected : `System check identified no issues (0 silenced).`

---

## Task 3 : `CarteService.lier_a_user()` — anti-vol + fusion + rattrapage adhésions

**Files :**
- Modify : `fedow_core/services.py`
- Modify : `tests/pytest/test_scan_qr_carte_v2.py`

### - [ ] Step 3.1 : Ajouter les tests pour `lier_a_user()`

Ajouter à la fin de `tests/pytest/test_scan_qr_carte_v2.py` :

```python
# ------------------------------------------------------------------
# Tests — CarteService.lier_a_user
# / Tests — CarteService.lier_a_user
# ------------------------------------------------------------------

def test_lier_carte_nouveau_user_sans_tokens(carte_vierge, tenant_origine, user_tout_neuf):
    """
    Lier un nouveau user a une carte vierge (sans tokens) : pas de Transaction FUSION.
    / Link a new user to a blank card (no tokens): no FUSION transaction.
    """
    from fedow_core.services import CarteService

    # Simuler un scan prealable qui cree wallet_ephemere
    CarteService.scanner_carte(carte_vierge, tenant_origine)
    carte_vierge.refresh_from_db()

    CarteService.lier_a_user(
        qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf,
    )

    carte_vierge.refresh_from_db()
    user_tout_neuf.refresh_from_db()
    assert carte_vierge.user == user_tout_neuf
    assert carte_vierge.wallet_ephemere is None
    assert user_tout_neuf.wallet is not None
    assert Transaction.objects.filter(action=Transaction.FUSION, card=carte_vierge).count() == 0


def test_lier_carte_avec_tokens_cree_transaction_fusion(
    carte_vierge, tenant_origine, user_tout_neuf, asset_tlf,
):
    """
    Lier avec tokens sur wallet_ephemere : 1 Transaction FUSION creee,
    tokens transferes sur user.wallet.
    / Link with tokens on wallet_ephemere: 1 FUSION transaction created,
    tokens transferred to user.wallet.
    """
    from fedow_core.services import CarteService, WalletService

    # Scan + recharge anonyme de 2000 centimes
    CarteService.scanner_carte(carte_vierge, tenant_origine)
    carte_vierge.refresh_from_db()
    Token.objects.create(
        wallet=carte_vierge.wallet_ephemere,
        asset=asset_tlf,
        value=2000,
    )

    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    carte_vierge.refresh_from_db()
    user_tout_neuf.refresh_from_db()
    assert carte_vierge.user == user_tout_neuf
    assert carte_vierge.wallet_ephemere is None

    transactions_fusion = Transaction.objects.filter(
        action=Transaction.FUSION, card=carte_vierge,
    )
    assert transactions_fusion.count() == 1
    assert transactions_fusion.first().amount == 2000
    token_user = Token.objects.get(wallet=user_tout_neuf.wallet, asset=asset_tlf)
    assert token_user.value == 2000


def test_lier_carte_antivol_user_deja_carte(
    carte_vierge, tenant_origine, detail_cartes, user_tout_neuf,
):
    """
    User a deja une autre carte : lever UserADejaCarte.
    / User already has another card: raise UserADejaCarte.
    """
    from fedow_core.services import CarteService

    autre_carte = CarteCashless.objects.create(
        tag_id=uuid.uuid4().hex[:8].upper(),
        number=uuid.uuid4().hex[:8].upper(),
        uuid=uuid.uuid4(),
        detail=detail_cartes,
        user=user_tout_neuf,
    )
    CarteService.scanner_carte(carte_vierge, tenant_origine)

    with pytest.raises(UserADejaCarte):
        CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)


def test_lier_carte_idempotent_meme_user(carte_vierge, tenant_origine, user_tout_neuf):
    """
    Relink sur carte deja liee au meme user : pas d'erreur, carte inchangee.
    / Re-link on same user: no error, card unchanged.
    """
    from fedow_core.services import CarteService

    CarteService.scanner_carte(carte_vierge, tenant_origine)
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    # 2e appel : doit rester idempotent
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    carte_vierge.refresh_from_db()
    assert carte_vierge.user == user_tout_neuf


def test_lier_carte_refus_autre_user(carte_vierge, tenant_origine, user_tout_neuf, db):
    """
    Carte liee a user A, tentative de link user B : CarteDejaLiee.
    / Card linked to user A, attempt to link user B: raise CarteDejaLiee.
    """
    from fedow_core.services import CarteService

    CarteService.scanner_carte(carte_vierge, tenant_origine)
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    user_b = User.objects.create_user(email="userb@test.local", password="p")

    with pytest.raises(CarteDejaLiee):
        CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_b)


def test_lier_rattrape_adhesions_anonymes(
    carte_vierge, tenant_origine, user_tout_neuf,
):
    """
    Adhesion anonyme (user=None, card_number=X) : apres lier_a_user, user_tout_neuf
    devient le proprietaire de l'adhesion.
    / Anonymous membership: after lier_a_user, user_tout_neuf becomes owner.
    """
    from BaseBillet.models import Price, Product
    from fedow_core.services import CarteService

    CarteService.scanner_carte(carte_vierge, tenant_origine)

    with tenant_context(tenant_origine):
        product = Product.objects.create(
            name="Adhesion test",
            categorie_article=Product.ADHESION,
        )
        price = Price.objects.create(product=product, prix=10)
        adhesion_anonyme = Membership.objects.create(
            price=price,
            card_number=carte_vierge.number,
            user=None,
        )

        user_tout_neuf.first_name = "Alice"
        user_tout_neuf.last_name = "Test"
        user_tout_neuf.save()

        CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

        adhesion_anonyme.refresh_from_db()
        assert adhesion_anonyme.user == user_tout_neuf
        assert adhesion_anonyme.first_name == "Alice"
        assert adhesion_anonyme.last_name == "Test"


def test_lier_carte_multi_assets(
    carte_vierge, tenant_origine, user_tout_neuf, asset_tlf,
):
    """
    wallet_ephemere a TLF + TNF : 2 Transactions FUSION distinctes.
    / wallet_ephemere has TLF + TNF: 2 distinct FUSION Transactions.
    """
    from fedow_core.services import CarteService

    CarteService.scanner_carte(carte_vierge, tenant_origine)
    carte_vierge.refresh_from_db()

    # Un 2e asset TNF
    wallet_lieu = Wallet.objects.create(origin=tenant_origine)
    asset_tnf = Asset.objects.create(
        name="TNF Test", currency_code="EUR", category=Asset.TNF,
        wallet_origin=wallet_lieu, tenant_origin=tenant_origine,
    )
    Token.objects.create(wallet=carte_vierge.wallet_ephemere, asset=asset_tlf, value=1000)
    Token.objects.create(wallet=carte_vierge.wallet_ephemere, asset=asset_tnf, value=500)

    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    assert Transaction.objects.filter(
        action=Transaction.FUSION, card=carte_vierge,
    ).count() == 2
```

### - [ ] Step 3.2 : Lancer les tests pour vérifier qu'ils échouent

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : 3 PASS (Task 2) + 7 FAIL/ERROR pour `lier_a_user`.

### - [ ] Step 3.3 : Implémenter `CarteService.lier_a_user()`

Ajouter dans la classe `CarteService` (après `scanner_carte`) :

```python
    @staticmethod
    def lier_a_user(qrcode_uuid, user, ip="0.0.0.0"):
        """
        Lie une carte a un user. Effectue la fusion du wallet ephemere
        et rattrape les adhesions anonymes.
        / Link a card to a user. Performs wallet_ephemere fusion
        and catches up anonymous memberships.

        Transactionnel : tout ou rien.
        / Transactional: all or nothing.

        :param qrcode_uuid: UUID de la carte (= CarteCashless.uuid)
        :param user: TibilletUser identifie
        :param ip: str (IP de la requete)
        :return: CarteCashless liee
        :raises CarteIntrouvable: carte absente en base
        :raises CarteDejaLiee: carte deja liee a un autre user
        :raises UserADejaCarte: user possede deja une autre carte (anti-vol)
        """
        from django.db import transaction as db_transaction
        from BaseBillet.models import Membership

        with db_transaction.atomic():
            # --- Verrou sur la ligne carte pour eviter double-link concurrent ---
            # / Lock the card row to prevent concurrent double-link.
            try:
                carte = CarteCashless.objects.select_for_update().select_related(
                    "detail__origine", "user", "wallet_ephemere",
                ).get(uuid=qrcode_uuid)
            except CarteCashless.DoesNotExist:
                raise CarteIntrouvable()

            tenant_origine = carte.detail.origine

            # --- Idempotence : carte deja liee a CE user ---
            # / Idempotency: card already linked to THIS user.
            carte_deja_liee_au_user = carte.user is not None and carte.user.pk == user.pk
            if carte_deja_liee_au_user:
                return carte

            # --- Carte deja liee a un AUTRE user ---
            # / Card linked to ANOTHER user.
            carte_liee_a_autre_user = carte.user is not None and carte.user.pk != user.pk
            if carte_liee_a_autre_user:
                raise CarteDejaLiee()

            # --- Anti-vol : user a-t-il deja une autre carte ? ---
            # Exclut la carte courante (utile en cas de relink apres perte).
            # / Anti-theft: does user already have another card? Exclude current card.
            user_a_deja_une_autre_carte = (
                user.cartecashless_set.exclude(pk=carte.pk).exists()
            )
            if user_a_deja_une_autre_carte:
                raise UserADejaCarte()

            # --- Fusion du wallet ephemere vers user.wallet ---
            # Delegue a WalletService (deja implemente en Phase 0).
            # Cree user.wallet si inexistant, transfere chaque Token avec solde > 0,
            # cree les Transaction(FUSION), pose carte.user et detache wallet_ephemere.
            # / Delegate to WalletService (already implemented in Phase 0).
            WalletService.fusionner_wallet_ephemere(
                carte=carte,
                user=user,
                tenant=tenant_origine,
                ip=ip,
            )

            # --- Rattrapage des adhesions anonymes ---
            # Les adhesions faites avec la carte anonyme (user=None, card_number=X)
            # sont rattachees au user identifie.
            # / Catch up anonymous memberships (user=None, card_number=X).
            with tenant_context(tenant_origine):
                Membership.objects.filter(
                    user__isnull=True,
                    card_number=carte.number,
                ).update(
                    user=user,
                    first_name=user.first_name or "",
                    last_name=user.last_name or "",
                )

            return carte
```

**Note** : ajouter `from django_tenants.utils import tenant_context` en haut du fichier si pas déjà présent.

### - [ ] Step 3.4 : Relancer les tests pour vérifier qu'ils passent

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : 10 tests PASS.

### - [ ] Step 3.5 : Vérifier Django check

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected : `System check identified no issues (0 silenced).`

---

## Task 4 : `CarteService.declarer_perdue()` — nullify carte + préserver wallet user

**Files :**
- Modify : `fedow_core/services.py`
- Modify : `tests/pytest/test_scan_qr_carte_v2.py`

### - [ ] Step 4.1 : Ajouter les tests `declarer_perdue`

Ajouter à la fin de `tests/pytest/test_scan_qr_carte_v2.py` :

```python
# ------------------------------------------------------------------
# Tests — CarteService.declarer_perdue
# / Tests — CarteService.declarer_perdue
# ------------------------------------------------------------------

def test_declarer_perdue_nullify_carte(
    carte_vierge, tenant_origine, user_tout_neuf, asset_tlf,
):
    """
    Apres declarer_perdue : carte.user = None, wallet_ephemere = None.
    / After declarer_perdue: carte.user = None, wallet_ephemere = None.
    """
    from fedow_core.services import CarteService

    CarteService.scanner_carte(carte_vierge, tenant_origine)
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    CarteService.declarer_perdue(user=user_tout_neuf, number_printed=carte_vierge.number)

    carte_vierge.refresh_from_db()
    assert carte_vierge.user is None
    assert carte_vierge.wallet_ephemere is None


def test_declarer_perdue_preserve_wallet_user(
    carte_vierge, tenant_origine, user_tout_neuf, asset_tlf,
):
    """
    Le wallet user et ses tokens sont preserves apres perte.
    / User wallet and its tokens are preserved after loss.
    """
    from fedow_core.services import CarteService

    # Scan + recharge + link
    CarteService.scanner_carte(carte_vierge, tenant_origine)
    carte_vierge.refresh_from_db()
    Token.objects.create(
        wallet=carte_vierge.wallet_ephemere, asset=asset_tlf, value=3000,
    )
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    user_tout_neuf.refresh_from_db()
    wallet_user_pk = user_tout_neuf.wallet.pk

    CarteService.declarer_perdue(user=user_tout_neuf, number_printed=carte_vierge.number)

    # Le wallet user doit toujours exister et contenir les 3000
    user_tout_neuf.refresh_from_db()
    assert user_tout_neuf.wallet is not None
    assert user_tout_neuf.wallet.pk == wallet_user_pk
    token = Token.objects.get(wallet=user_tout_neuf.wallet, asset=asset_tlf)
    assert token.value == 3000


def test_declarer_perdue_carte_autre_user(
    carte_vierge, tenant_origine, user_tout_neuf, db,
):
    """
    Tentative de declarer_perdue pour une carte non liee au user : CarteIntrouvable.
    / Attempt to declare loss on a card not linked to user: raise CarteIntrouvable.
    """
    from fedow_core.services import CarteService

    user_b = User.objects.create_user(email="userb2@test.local", password="p")

    with pytest.raises(CarteIntrouvable):
        CarteService.declarer_perdue(user=user_b, number_printed=carte_vierge.number)
```

### - [ ] Step 4.2 : Lancer les tests pour vérifier qu'ils échouent

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : 10 PASS + 3 FAIL/ERROR pour `declarer_perdue`.

### - [ ] Step 4.3 : Implémenter `CarteService.declarer_perdue()`

Ajouter dans la classe `CarteService` (après `lier_a_user`) :

```python
    @staticmethod
    def declarer_perdue(user, number_printed):
        """
        Detache la carte du user. Le wallet user conserve ses tokens.
        Reproduction du comportement V1 (lost_my_card_by_signature).
        / Detach card from user. User wallet keeps its tokens.

        :param user: TibilletUser
        :param number_printed: str (CarteCashless.number, 8 chars)
        :return: CarteCashless detachee
        :raises CarteIntrouvable: carte absente ou non liee a ce user
        """
        try:
            carte = CarteCashless.objects.get(user=user, number=number_printed)
        except CarteCashless.DoesNotExist:
            raise CarteIntrouvable()

        carte.user = None
        carte.wallet_ephemere = None
        carte.save(update_fields=["user", "wallet_ephemere"])

        logger.info(
            f"Carte {number_printed} declaree perdue par user {user.email}"
        )
        return carte
```

### - [ ] Step 4.4 : Relancer les tests pour vérifier qu'ils passent

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : 13 tests PASS.

---

## Task 5 : Dispatch V1/V2 dans `ScanQrCode.retrieve()`

**Files :**
- Modify : `BaseBillet/views.py:394-462` (méthode `retrieve` de `ScanQrCode`)

### - [ ] Step 5.1 : Lire la vue actuelle

Run :
```bash
grep -n "class ScanQrCode\|def retrieve\|def link" /home/jonas/TiBillet/dev/Lespass/BaseBillet/views.py
```

Expected : localisation de `ScanQrCode` (~ligne 394) et ses méthodes.

### - [ ] Step 5.2 : Refactor de `ScanQrCode.retrieve()` avec dispatch V1/V2

Remplacer le corps de `retrieve()` par la version avec dispatch. Conserver les imports existants.

Code cible (remplace `BaseBillet/views.py:397-462`) :

```python
    def retrieve(self, request, pk=None):
        """
        GET /qr/<qrcode_uuid>/ — scan public de carte cashless.
        / Public QR code scan of a cashless card.

        LOCALISATION : BaseBillet/views.py:ScanQrCode
        Dispatch V1 (fedow_connect HTTP) / V2 (fedow_core DB direct) selon
        Configuration.server_cashless du tenant d'origine de la carte.
        """
        # --- Validation UUID ---
        # / Validate UUID format.
        try:
            qrcode_uuid = uuid.UUID(pk)
        except (ValueError, TypeError):
            logger.warning(f"ScanQrCode.retrieve : pk non uuid : {pk}")
            raise Http404()

        # --- Resolution carte + tenant d'origine (SHARED_APPS : acces direct) ---
        # / Resolve card and origin tenant (SHARED_APPS: direct access).
        try:
            carte = CarteCashless.objects.select_related(
                "detail__origine", "user", "wallet_ephemere",
            ).get(uuid=qrcode_uuid)
        except CarteCashless.DoesNotExist:
            raise Http404("Unknow qrcode_uuid")

        if carte.detail is None or carte.detail.origine is None:
            logger.error(f"Carte {qrcode_uuid} sans detail ou origine")
            raise Http404("Origin error")

        tenant_origine = carte.detail.origine

        # --- Redirection cross-domain vers le primary_domain du tenant d'origine ---
        # UX V1 conservee : scanner une carte ramene toujours sur son festival.
        # / Cross-domain redirect to origin tenant's primary domain. V1 UX preserved.
        primary_domain = tenant_origine.get_primary_domain()
        if primary_domain.domain not in request.build_absolute_uri():
            return HttpResponseRedirect(f"https://{primary_domain.domain}/qr/{qrcode_uuid}/")

        # --- Dispatch V1 / V2 selon tenant d'origine ---
        # V1 : tenant legacy (server_cashless renseigne) → HTTP Fedow distant
        # V2 : tenant fedow_core → acces DB direct
        # / V1 vs V2 dispatch based on Configuration.server_cashless.
        with tenant_context(tenant_origine):
            config = Configuration.get_solo()
            tenant_est_en_v1 = bool(config.server_cashless)

            if tenant_est_en_v1:
                return self._retrieve_v1_legacy(request, qrcode_uuid, tenant_origine)
            return self._retrieve_v2_fedow_core(request, carte, tenant_origine)

    def _retrieve_v1_legacy(self, request, qrcode_uuid, tenant_origine):
        """
        Branche V1 : appelle fedow_connect (HTTP vers Fedow distant).
        Ancien code conserve pour les tenants legacy.
        / V1 branch: calls fedow_connect (HTTP to remote Fedow).
        """
        fedowAPI = FedowAPI()
        serialized_qrcode_card = fedowAPI.NFCcard.qr_retrieve(qrcode_uuid)
        if not serialized_qrcode_card:
            raise Http404("Unknow qrcode_uuid")

        if serialized_qrcode_card['is_wallet_ephemere']:
            template_context = get_context(request)
            template_context['qrcode_uuid'] = qrcode_uuid
            template_context['base_template'] = 'reunion/blank_base.html'
            logout(request)
            return render(request, "reunion/views/register.html", context=template_context)

        wallet = Wallet.objects.get(uuid=serialized_qrcode_card['wallet_uuid'])
        user = wallet.user
        user.is_active = True
        user.save()
        login(request, user)

        if settings.TEST or settings.DEBUG:
            token = user.get_connect_token()
            base_url = connection.tenant.get_primary_domain().domain
            connexion_url = f"https://{base_url}/emailconfirmation/{token}"
            messages.add_message(request, messages.INFO,
                                 format_html(f"<a href='{connexion_url}'>TEST MODE</a>"))
        return redirect("/my_account")

    def _retrieve_v2_fedow_core(self, request, carte, tenant_origine):
        """
        Branche V2 : appelle fedow_core.CarteService (DB direct).
        / V2 branch: calls fedow_core.CarteService (direct DB access).
        """
        from fedow_core.services import CarteService

        resultat = CarteService.scanner_carte(
            carte=carte, tenant_origine=tenant_origine,
            ip=get_request_ip(request),
        )

        if resultat.is_wallet_ephemere:
            template_context = get_context(request)
            template_context['qrcode_uuid'] = carte.uuid
            template_context['base_template'] = 'reunion/blank_base.html'
            # Logout au cas ou on scanne les cartes a la suite
            # / Logout in case of consecutive scans
            logout(request)
            return render(request, "reunion/views/register.html", context=template_context)

        # Carte identifiee : login automatique du user
        # / Identified card: automatic user login
        user = carte.user
        user.is_active = True
        user.save()
        login(request, user)

        if settings.TEST or settings.DEBUG:
            token = user.get_connect_token()
            base_url = connection.tenant.get_primary_domain().domain
            connexion_url = f"https://{base_url}/emailconfirmation/{token}"
            messages.add_message(request, messages.INFO,
                                 format_html(f"<a href='{connexion_url}'>TEST MODE</a>"))
        return redirect("/my_account")
```

**Note** : Vérifier que ces imports sont en haut de `BaseBillet/views.py` (les ajouter sinon) :
- `from QrcodeCashless.models import CarteCashless`
- `from BaseBillet.models import Configuration`
- `get_request_ip` (helper existant — vérifier le chemin d'import)

### - [ ] Step 5.3 : Vérifier Django check

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected : aucune erreur.

### - [ ] Step 5.4 : Lancer la suite pytest scan QR

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : 13 tests PASS (aucune régression).

---

## Task 6 : Dispatch V1/V2 dans `ScanQrCode.link()`

**Files :**
- Modify : `BaseBillet/views.py:468-544` (méthode `link` de `ScanQrCode`)

### - [ ] Step 6.1 : Refactor de `ScanQrCode.link()` avec dispatch V1/V2

Remplacer le corps de `link()` par :

```python
    @action(detail=False, methods=['POST'])
    def link(self, request):
        """
        POST /qr/link/ — identification d'une carte scannee.
        / Identify a scanned card with user email.

        LOCALISATION : BaseBillet/views.py:ScanQrCode
        """
        validator = LinkQrCodeValidator(data=request.POST.dict())
        if not validator.is_valid():
            for error in validator.errors:
                logger.error(f"{error} : {validator.errors[error][0]}")
                messages.add_message(request, messages.ERROR,
                                     f"{error} : {validator.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        email = validator.validated_data['email']
        user = get_or_create_user(email, force_mail=True)
        if validator.validated_data.get('newsletter'):
            send_to_ghost_email.delay(email)

        if not user:
            messages.add_message(request, messages.ERROR, f"{_('Invalid email')}")
            logger.error("email valide DRF mais pas get_or_create_user")
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        # Completer first_name/last_name uniquement si vides (pas d'ecrasement)
        # / Fill first_name/last_name only if empty (never overwrite).
        if validator.data.get('lastname') and not user.last_name:
            user.last_name = validator.data.get('lastname')
        if validator.data.get('firstname') and not user.first_name:
            user.first_name = validator.data.get('firstname')
        if validator.data.get('newsletter'):
            send_to_ghost_email.delay(email, f"{user.first_name} {user.last_name}")
        user.email_valid = False
        user.save()

        # --- Dispatch V1 / V2 ---
        # / V1 vs V2 dispatch.
        qrcode_uuid = validator.validated_data['qrcode_uuid']

        try:
            carte = CarteCashless.objects.select_related("detail__origine").get(uuid=qrcode_uuid)
        except CarteCashless.DoesNotExist:
            messages.add_message(request, messages.ERROR, _("Card not found"))
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        tenant_origine = carte.detail.origine
        with tenant_context(tenant_origine):
            config = Configuration.get_solo()
            tenant_est_en_v1 = bool(config.server_cashless)

        if tenant_est_en_v1:
            return self._link_v1_legacy(request, user, qrcode_uuid, carte)
        return self._link_v2_fedow_core(request, user, carte)

    def _link_v1_legacy(self, request, user, qrcode_uuid, carte):
        """
        Branche V1 : appelle fedow_connect (HTTP).
        / V1 branch: calls fedow_connect (HTTP).
        """
        fedowAPI = FedowAPI()
        wallet, created = fedowAPI.wallet.get_or_create_wallet(user)
        if not created:
            retrieve_wallet = fedowAPI.wallet.retrieve_by_signature(user)
            if retrieve_wallet.validated_data['has_user_card']:
                messages.add_message(request, messages.ERROR,
                                     _("You seem to already have a TiBillet card "
                                       "linked to your wallet. Please revoke it first."))
                return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        linked_serialized_card = fedowAPI.NFCcard.linkwallet_cardqrcode(
            user=user, qrcode_uuid=qrcode_uuid,
        )
        if not linked_serialized_card:
            messages.add_message(request, messages.ERROR, _("Not valid"))

        card_number = linked_serialized_card.get('number_printed') if linked_serialized_card else None
        if card_number:
            for membership in Membership.objects.filter(
                user__isnull=True, card_number=card_number,
            ):
                membership.user = user
                membership.first_name = user.first_name
                membership.last_name = user.last_name
                membership.save()

        return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

    def _link_v2_fedow_core(self, request, user, carte):
        """
        Branche V2 : appelle fedow_core.CarteService (DB direct).
        / V2 branch: calls fedow_core.CarteService.
        """
        from fedow_core.services import CarteService
        from fedow_core.exceptions import (
            CarteDejaLiee, CarteIntrouvable, UserADejaCarte,
        )

        try:
            CarteService.lier_a_user(
                qrcode_uuid=carte.uuid, user=user, ip=get_request_ip(request),
            )
        except UserADejaCarte as e:
            messages.add_message(request, messages.ERROR, str(e))
        except CarteDejaLiee as e:
            messages.add_message(request, messages.ERROR, str(e))
        except CarteIntrouvable as e:
            messages.add_message(request, messages.ERROR, str(e))

        return HttpResponseClientRedirect(request.headers.get('Referer', '/'))
```

### - [ ] Step 6.2 : Vérifier Django check

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected : aucune erreur.

### - [ ] Step 6.3 : Relancer pytest scan QR

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : 13 tests PASS.

---

## Task 7 : Dispatch V1/V2 dans `lost_my_card()` + `admin_lost_my_card()`

**Files :**
- Modify : `BaseBillet/views.py:1111-1155` (méthodes `admin_lost_my_card` et `lost_my_card`)

### - [ ] Step 7.1 : Lire l'état actuel

Run :
```bash
grep -n "def admin_lost_my_card\|def lost_my_card" /home/jonas/TiBillet/dev/Lespass/BaseBillet/views.py
```

Expected : localisation des 2 méthodes.

### - [ ] Step 7.2 : Refactor `lost_my_card` avec dispatch

Remplacer le corps de `lost_my_card` (et `admin_lost_my_card`) :

```python
    @action(detail=True, methods=['GET'])
    def admin_lost_my_card(self, request, pk, *args, **kwargs):
        """
        GET — Admin tenant declare une carte perdue pour un user.
        / Tenant admin declares a card lost for a user.
        """
        tenant = request.tenant
        admin = request.user
        user_pk, number_printed = pk.split(':')
        user = get_object_or_404(HumanUser, pk=user_pk)
        if not admin.is_tenant_admin(tenant):
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))
        self._declare_lost_card_dispatch(request, user, number_printed)
        return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

    @action(detail=True, methods=['GET'])
    def lost_my_card(self, request, pk):
        """
        GET — L'utilisateur declare sa propre carte perdue.
        / User declares their own card lost.
        """
        if not request.user.email_valid:
            logger.warning(_("User email not active"))
            messages.add_message(request, messages.ERROR,
                                 _("You need a valid email to declare a card lost."))
            return HttpResponseClientRedirect('/my_account/')

        self._declare_lost_card_dispatch(request, request.user, pk)
        return HttpResponseClientRedirect('/my_account/')

    def _declare_lost_card_dispatch(self, request, user, number_printed):
        """
        Dispatch V1/V2 pour la declaration de perte.
        / V1/V2 dispatch for loss declaration.
        """
        # Recuperer le tenant d'origine de la carte (SHARED_APPS : acces direct)
        # / Get the origin tenant of the card (SHARED_APPS: direct access).
        try:
            carte = CarteCashless.objects.select_related("detail__origine").get(
                user=user, number=number_printed,
            )
        except CarteCashless.DoesNotExist:
            messages.add_message(request, messages.ERROR,
                                 _("Card not found or not linked to your account."))
            return

        tenant_origine = carte.detail.origine
        with tenant_context(tenant_origine):
            config = Configuration.get_solo()
            tenant_est_en_v1 = bool(config.server_cashless)

        if tenant_est_en_v1:
            self._declare_lost_v1_legacy(request, user, number_printed)
        else:
            self._declare_lost_v2_fedow_core(request, user, number_printed)

    def _declare_lost_v1_legacy(self, request, user, number_printed):
        """Branche V1 : fedow_connect HTTP."""
        try:
            fedowAPI = FedowAPI()
            lost_card_report = fedowAPI.NFCcard.lost_my_card_by_signature(
                user, number_printed=number_printed,
            )
            if lost_card_report:
                messages.add_message(request, messages.SUCCESS,
                                     _("Your wallet has been detached from this card. "
                                       "You can scan a new one to link it again."))
            else:
                messages.add_message(request, messages.ERROR,
                                     _("Error when detaching your card. Contact an administrator."))
        except Exception as e:
            logger.error(f"_declare_lost_v1_legacy error: {e}")
            messages.add_message(request, messages.ERROR,
                                 _("Error when detaching your card. Contact an administrator."))

    def _declare_lost_v2_fedow_core(self, request, user, number_printed):
        """Branche V2 : fedow_core.CarteService."""
        from fedow_core.services import CarteService
        from fedow_core.exceptions import CarteIntrouvable

        try:
            CarteService.declarer_perdue(user=user, number_printed=number_printed)
            messages.add_message(request, messages.SUCCESS,
                                 _("Your wallet has been detached from this card. "
                                   "You can scan a new one to link it again."))
        except CarteIntrouvable as e:
            messages.add_message(request, messages.ERROR, str(e))
        except Exception as e:
            logger.error(f"_declare_lost_v2_fedow_core error: {e}")
            messages.add_message(request, messages.ERROR,
                                 _("Error when detaching your card. Contact an administrator."))
```

### - [ ] Step 7.3 : Vérifier Django check + relancer pytest

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check && \
docker exec lespass_django poetry run pytest tests/pytest/test_scan_qr_carte_v2.py -v
```

Expected : check OK, 13 tests PASS.

---

## Task 8 : Tests E2E Playwright

**Files :**
- Create : `tests/e2e/test_scan_qr_carte_v2.py`

### - [ ] Step 8.1 : Vérifier qu'une carte de test existe

Regarder `tests/e2e/conftest.py` pour voir si une fixture `carte_e2e` existe (chercher `CARTE_E2E_TAG`, `CARTE_E2E_UUID` dans les tests existants).

Run :
```bash
grep -rn "CARTE_E2E_TAG\|CARTE_E2E_UUID" /home/jonas/TiBillet/dev/Lespass/tests/
```

Expected : constants utilisées dans `test_admin_card_refund.py` ou équivalent. Sinon, créer une fixture locale.

### - [ ] Step 8.2 : Créer les tests E2E

Créer `tests/e2e/test_scan_qr_carte_v2.py` :

```python
"""
Tests E2E du flow scan QR carte V2.
/ E2E tests for V2 QR card scan flow.

LOCALISATION : tests/e2e/test_scan_qr_carte_v2.py

Prerequis : serveur Django actif via Traefik (lespass.tibillet.localhost).
/ Prerequisite: Django server active via Traefik.
"""
import uuid

import pytest


@pytest.fixture
def carte_e2e_vierge(db):
    """
    Cree une carte vierge de test (user=None, wallet_ephemere=None) sur le tenant lespass.
    / Create a blank test card on the lespass tenant.
    """
    from django.db import connection
    from django_tenants.utils import schema_context
    from Customers.models import Client
    from QrcodeCashless.models import CarteCashless, Detail

    tag = uuid.uuid4().hex[:8].upper()
    number = uuid.uuid4().hex[:8].upper()
    card_uuid = uuid.uuid4()

    tenant = Client.objects.get(schema_name="lespass")
    detail, _ = Detail.objects.get_or_create(
        base_url="lespass.tibillet.localhost",
        defaults={"origine": tenant, "generation": 1},
    )
    carte = CarteCashless.objects.create(
        tag_id=tag, number=number, uuid=card_uuid, detail=detail,
    )
    return {"tag_id": tag, "number": number, "uuid": str(card_uuid), "obj": carte}


def test_scan_qr_flow_complet(page, carte_e2e_vierge, live_server):
    """
    Scan carte vierge -> formulaire email -> soumission -> login automatique -> /my_account.
    / Scan blank card -> email form -> submit -> auto login -> /my_account.
    """
    email = f"e2e-{uuid.uuid4().hex[:6]}@test.local"
    url_scan = f"https://lespass.tibillet.localhost/qr/{carte_e2e_vierge['uuid']}/"

    page.goto(url_scan)
    page.wait_for_load_state("domcontentloaded")

    # Formulaire d'inscription doit etre visible (wallet ephemere)
    assert page.locator("form#linkform").is_visible()

    page.fill("input[name='email']", email)
    page.fill("input[name='firstname']", "Alice")
    page.fill("input[name='lastname']", "Test")

    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    # Retour sur /qr/ qui log in et redirige vers /my_account
    page.wait_for_url(lambda url: "/my_account" in url, timeout=10000)


def test_scan_qr_redirection_crossdomain(page, carte_e2e_vierge):
    """
    GET /qr/<uuid>/ depuis un tenant autre que l'origine → 302 vers primary_domain d'origine.
    / GET from another tenant → 302 to origin primary_domain.
    """
    url_autre_tenant = f"https://autre.tibillet.localhost/qr/{carte_e2e_vierge['uuid']}/"

    response = page.goto(url_autre_tenant)

    # Apres suivi de redirect, on doit etre sur lespass.tibillet.localhost
    assert "lespass.tibillet.localhost" in page.url


def test_perte_carte_from_my_account(page, carte_e2e_vierge):
    """
    User connecte + carte liee -> click bouton Carte perdue -> message succes + carte detachee.
    / Logged user + linked card -> click Lost Card -> success message + card detached.
    """
    # Prerequis : user connecte et carte liee (a monter via fixture ou API)
    # Pour simplifier : skip si infrastructure de login E2E absente
    pytest.skip("A implementer : fixture de user logged-in + carte liee")
```

### - [ ] Step 8.3 : Lancer les tests E2E

Run :
```bash
docker exec lespass_django poetry run pytest tests/e2e/test_scan_qr_carte_v2.py -v -s
```

Expected : 2 tests PASS (flow complet + redirection), 1 SKIPPED (perte — à implémenter selon infra auth E2E).

---

## Task 9 : Workflow djc — CHANGELOG + i18n + docs

**Files :**
- Modify : `CHANGELOG.md`
- Modify : `locale/fr/LC_MESSAGES/django.po`
- Modify : `locale/en/LC_MESSAGES/django.po`
- Create : `A TESTER et DOCUMENTER/scan-qr-carte-v2.md`
- Create : `fedow_core/CARTES.md`

### - [ ] Step 9.1 : Entrée CHANGELOG.md

Ajouter en tête de `CHANGELOG.md` (après le header, avant l'entrée précédente) :

```markdown
## Session 34 — Scan QR carte V2 (fedow_core) / QR card scan V2

**Quoi / What :** Bascule du flow public "scan QR carte cashless" de `fedow_connect/fedow_api.py` (HTTP vers Fedow distant) vers `fedow_core/services.py` (DB direct). Scope : scan, identification user (link), fusion wallet ephemere, perte de carte.
**Pourquoi / Why :** Supprimer la dependance reseau Fedow pour le flow public, simplifier l'audit anti-vol, preparer la suppression totale de `fedow_connect/` (roadmap C).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_core/exceptions.py` | +3 exceptions (`CarteIntrouvable`, `CarteDejaLiee`, `UserADejaCarte`) |
| `fedow_core/services.py` | +classe `CarteService` (scanner_carte, lier_a_user, declarer_perdue) |
| `BaseBillet/views.py` | Dispatch V1/V2 dans `ScanQrCode.retrieve/link` + `lost_my_card`/`admin_lost_my_card` |
| `tests/pytest/test_scan_qr_carte_v2.py` | 13 tests DB-only |
| `tests/e2e/test_scan_qr_carte_v2.py` | 2 tests Playwright |
| `fedow_core/CARTES.md` | Doc mecanique wallet ephemere + fusion |

### Migration / Migration
- **Migration necessaire / Migration required :** Non / No
- Aucun changement de schema. `CarteCashless`, `Wallet`, `Transaction.FUSION` deja en place.

### Coexistence V1/V2 / V1/V2 coexistence
- Dispatch par tenant : `Configuration.server_cashless` renseigne → V1 `fedow_connect` ; sinon V2 `fedow_core`.
- Les tenants legacy continuent d'appeler le serveur Fedow distant sans changement.
- Les nouveaux tenants V2 n'utilisent plus jamais `NFCcardFedow` pour le scan QR.
```

### - [ ] Step 9.2 : Lancer makemessages FR + EN

Run :
```bash
docker exec lespass_django poetry run django-admin makemessages -l fr && \
docker exec lespass_django poetry run django-admin makemessages -l en
```

Expected : fichiers `.po` mis à jour avec les nouvelles chaînes (issues des `_()` dans `fedow_core/exceptions.py`).

### - [ ] Step 9.3 : Compléter les `msgstr` FR + EN

Ouvrir `locale/fr/LC_MESSAGES/django.po` et chercher les 3 nouvelles entrées (les `msgstr ""` vides liés à `fedow_core/exceptions.py`). Les compléter :

```po
#: fedow_core/exceptions.py:XX
msgid "Carte introuvable ou non liee a votre compte."
msgstr "Carte introuvable ou non liée à votre compte."

#: fedow_core/exceptions.py:XX
msgid "Cette carte est deja liee a un autre compte."
msgstr "Cette carte est déjà liée à un autre compte."

#: fedow_core/exceptions.py:XX
msgid ""
"Vous avez deja une carte TiBillet liee a votre compte. Declarez-la perdue "
"avant d'en associer une nouvelle."
msgstr ""
"Vous avez déjà une carte TiBillet liée à votre compte. Déclarez-la perdue "
"avant d'en associer une nouvelle."
```

Même opération sur `locale/en/LC_MESSAGES/django.po` avec traduction EN :

```po
msgid "Carte introuvable ou non liee a votre compte."
msgstr "Card not found or not linked to your account."

msgid "Cette carte est deja liee a un autre compte."
msgstr "This card is already linked to another account."

msgid ""
"Vous avez deja une carte TiBillet liee a votre compte. Declarez-la perdue "
"avant d'en associer une nouvelle."
msgstr ""
"You already have a TiBillet card linked to your account. Please declare it "
"lost before linking a new one."
```

Vérifier qu'aucune entrée `fuzzy` ne traîne (rechercher `#, fuzzy`).

### - [ ] Step 9.4 : Compilemessages

Run :
```bash
docker exec lespass_django poetry run django-admin compilemessages
```

Expected : `processing file django.po in /home/.../fr/LC_MESSAGES` et idem EN. Aucune erreur.

### - [ ] Step 9.5 : Créer `A TESTER et DOCUMENTER/scan-qr-carte-v2.md`

Contenu :

```markdown
# Scan QR carte V2 (fedow_core) — Tests manuels

## Ce qui a ete fait

Bascule du flow public de scan QR vers `fedow_core/services.py:CarteService`.
Dispatch V1/V2 via `Configuration.server_cashless` : les anciens tenants legacy
restent sur `fedow_connect` (HTTP Fedow distant), les nouveaux sur `fedow_core`.

### Modifications
| Fichier | Changement |
|---|---|
| `fedow_core/services.py` | +classe `CarteService` (3 methodes) |
| `fedow_core/exceptions.py` | +3 exceptions metier |
| `BaseBillet/views.py` | Dispatch V1/V2 dans 4 vues |

## Tests a realiser

### Test 1 : Scan carte vierge -> formulaire -> login
1. Creer une `CarteCashless` sur le tenant `lespass` via l'admin (ou fixture).
2. `Configuration.server_cashless` sur lespass doit etre `None` (V2 actif).
3. Aller sur `https://lespass.tibillet.localhost/qr/<carte.uuid>/`
4. Verification : formulaire email affiche.
5. Saisir email + prenom + nom, soumettre.
6. Verification : redirection vers `/my_account/`, user logue.
7. Verification en base :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
   from QrcodeCashless.models import CarteCashless
   carte = CarteCashless.objects.get(uuid='<uuid>')
   print(f'user={carte.user.email}')
   print(f'wallet_ephemere={carte.wallet_ephemere}')
   print(f'user.wallet={carte.user.wallet}')
   "
   ```
8. Attendu : `user=...@test.local`, `wallet_ephemere=None`, `user.wallet=Wallet`.

### Test 2 : Redirection cross-domain
1. Scan la meme carte depuis `https://autre.tibillet.localhost/qr/<uuid>/`
2. Verification : 302 vers `https://lespass.tibillet.localhost/qr/<uuid>/`

### Test 3 : Anti-vol (user a deja une carte)
1. User A a une carte liee. Creer une 2e carte vierge.
2. Scan carte 2 -> formulaire -> saisir email de user A.
3. Attendu : message erreur "Vous avez deja une carte TiBillet..."
4. Verification en base : carte 2 reste `user=None`.

### Test 4 : Fusion avec tokens
1. Carte vierge scannee -> wallet_ephemere cree.
2. Ajouter manuellement un Token de 1000 centimes sur ce wallet_ephemere.
3. Scan + saisir email nouveau user.
4. Attendu : Token transfere sur user.wallet + Transaction FUSION en base.
5. Verification :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
   from fedow_core.models import Transaction
   print(Transaction.objects.filter(action='FUS').count())
   "
   ```

### Test 5 : Perte de carte
1. User connecte, carte liee.
2. Aller sur MyAccount, cliquer "Carte perdue".
3. Attendu : message succes, carte detachee (`user=None, wallet_ephemere=None`).
4. Verification : `user.wallet` reste intact, ses tokens aussi.

### Test 6 : Coexistence V1 (si tenant legacy disponible)
1. Sur un tenant avec `Configuration.server_cashless` renseigne, refaire le Test 1.
2. Attendu : le flow passe par `fedow_connect` (logs HTTP visibles), comportement V1 inchange.

## Compatibilite

- Aucun changement de schema. Rollback = revert du code uniquement.
- Les adhesions anonymes liees par `card_number` sont rattrapees automatiquement lors du link.
- Les tenants legacy ne sont pas impactes (dispatch V1 conserve).
```

### - [ ] Step 9.6 : Créer `fedow_core/CARTES.md`

Contenu :

```markdown
# Gestion des cartes cashless — fedow_core

Documentation technique du flow carte cashless dans `fedow_core`. Remplace
progressivement `fedow_connect/` (HTTP vers Fedow distant).

## Modele `CarteCashless` (QrcodeCashless/models.py)

Une carte NFC physique, identifiee par :
- `tag_id` : identifiant NFC 8 hex (grave dans la puce)
- `uuid` : UUID public, utilise dans l'URL `/qr/<uuid>/` (QR code imprime)
- `number` : numero imprime visible (8 chars)
- `detail` : FK vers `Detail` (lot de cartes, porte l'origine via `detail.origine`)
- `user` : FK `TibilletUser` nullable — null si carte anonyme
- `wallet_ephemere` : OneToOne `Wallet` nullable — conteneur anonyme

## Les 4 etats d'une carte

| Etat | `user` | `wallet_ephemere` | Ou sont les tokens ? |
|---|---|---|---|
| Vierge | None | None | Nulle part |
| Anonyme | None | `Wallet_X` | Sur `Wallet_X` (sans reverse user) |
| Identifiee | `User_A` | None | Sur `User_A.wallet` |
| Perdue | None | None | Restent sur `User_A.wallet` (detache) |

## Transitions

### Scan d'une carte vierge (`CarteService.scanner_carte`)
- Vierge -> Anonyme : cree un `Wallet` avec `origin=detail.origine`, l'attache.

### Identification (`CarteService.lier_a_user`)
- Anonyme -> Identifiee : fusion des tokens `wallet_ephemere -> user.wallet` via
  `Transaction(action=FUSION)`, puis `carte.user = user ; carte.wallet_ephemere = None`.
- Anti-vol : refus si `user` a deja une autre carte (`user.cartecashless_set.exclude(pk=carte.pk).exists()`).
- Rattrapage : les `Membership(user=None, card_number=carte.number)` sont rattachees.

### Perte (`CarteService.declarer_perdue`)
- Identifiee -> Perdue : `carte.user = None ; carte.wallet_ephemere = None`.
- `user.wallet` et ses tokens restent intacts : le user peut lier une nouvelle carte.

## Pourquoi une fusion et pas "attacher l'user au wallet_ephemere" ?

1. **Unicite OneToOne user<->wallet** : `TibilletUser.wallet` est un OneToOne.
   Un user a un seul wallet. Un user peut avoir un wallet preexistant avec des
   tokens (adhesion, FED d'un autre festival, etc.) — on ne peut pas "l'ecraser".
2. **Preservation des tokens preexistants** : si `user.wallet` a deja 15 FED,
   attacher le wallet_ephemere (5 TLF) les perdrait.
3. **Auditabilite** : `Transaction(FUSION)` trace explicitement le transfert.

## Dispatch V1/V2

- Tenant avec `Configuration.server_cashless` renseigne -> V1 (`fedow_connect`).
- Tenant sans -> V2 (`fedow_core.CarteService`).
- Les 2 systemes de tokens sont disjoints : tokens V1 restent sur serveur Fedow
  distant, tokens V2 dans DB locale. Pas de pont entre les deux (hors scope).

## Coexistence avec le refactor wallet-only (en attente)

Le design `2026-04-14-refactor-carte-wallet-only-design.md` propose de supprimer
`CarteCashless.user` et `wallet_ephemere` au profit d'un champ `wallet` unique.
Si ce refactor passe, adapter `CarteService` (logique simplifiee, plus de dualite).
```

### - [ ] Step 9.7 : Vérifier que tout compile

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected : aucune erreur.

---

## Task 10 : Validation finale

**Files :** aucun (validation uniquement)

### - [ ] Step 10.1 : Suite pytest complète

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Expected : tous les tests passent (y compris les 13 nouveaux de cette session).

### - [ ] Step 10.2 : Suite pytest ciblée scope carte

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "carte or scan or fusion or wallet_ephemere"
```

Expected : aucune régression sur les tests existants (admin cartes, refund, fusion phase 0).

### - [ ] Step 10.3 : Test manuel en navigateur

1. Lancer le serveur en arrière-plan :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
   ```
2. Suivre le scénario du fichier `A TESTER et DOCUMENTER/scan-qr-carte-v2.md` (Test 1 au minimum).
3. Vérifier les logs du serveur (pas de traceback 500).

### - [ ] Step 10.4 : Créer le JOURNAL de session

Créer `TECH DOC/Laboutik sessions/Session 34 - Scan QR carte V2/JOURNAL.md` :

```markdown
# Journal Session 34 — Scan QR carte V2

**Date :** 2026-04-20
**Duree estimee :** 10h
**Duree reelle :** (a remplir)

## Etapes completees

- [x] Task 1 : Exceptions metier
- [x] Task 2 : `CarteService.scanner_carte()`
- [x] Task 3 : `CarteService.lier_a_user()`
- [x] Task 4 : `CarteService.declarer_perdue()`
- [x] Task 5 : Dispatch V1/V2 `ScanQrCode.retrieve`
- [x] Task 6 : Dispatch V1/V2 `ScanQrCode.link`
- [x] Task 7 : Dispatch V1/V2 `lost_my_card` + `admin_lost_my_card`
- [x] Task 8 : Tests E2E Playwright
- [x] Task 9 : CHANGELOG + i18n + docs
- [x] Task 10 : Validation finale

## Tests ajoutes

- **pytest DB-only** : 13 tests (`tests/pytest/test_scan_qr_carte_v2.py`)
- **E2E Playwright** : 2 tests (`tests/e2e/test_scan_qr_carte_v2.py`)

## Pieges rencontres

(a remplir au fur et a mesure)

## Suite (roadmap C)

Session 35 : Wallet user + token retrieval (`retrieve_by_signature`, `get_total_fed_token`, etc.)
Session 36 : Transactions list + history
Session 37 : Adhesions + badges
Session 38 : Asset management + bank deposits
Session 39 : Bootstrap place
Session 40 : Decommission `fedow_connect/`
```

### - [ ] Step 10.5 : Récap final pour le mainteneur

Préparer le message de fin de session avec :
- Nombre de fichiers créés / modifiés
- Nombre de tests ajoutés
- Points d'attention pour la revue
- Message de commit suggéré (que le mainteneur pourra utiliser) :

```
feat(fedow_core): Session 34 - scan QR carte V2 (CarteService)

- Ajoute CarteService dans fedow_core/services.py avec 3 methodes :
  scanner_carte, lier_a_user, declarer_perdue
- Ajoute 3 exceptions metier dans fedow_core/exceptions.py
- Dispatch V1/V2 dans BaseBillet.ScanQrCode + lost_my_card
  selon Configuration.server_cashless
- Aucune migration : CarteCashless schema inchange (Option 3 YAGNI)
- 13 tests pytest + 2 tests E2E Playwright
- CHANGELOG + i18n FR/EN + docs (fedow_core/CARTES.md)

Hors scope : suppression fedow_connect/ (roadmap C session finale).
```

**Le mainteneur decidera du commit final.** Ne JAMAIS executer `git commit`.

---

## Self-Review

**Spec coverage (spec sections -> tasks) :**
- §3 decisions archi -> Task 5/6/7 (dispatch) + Task 2/3/4 (services)
- §4 architecture -> Task 2/3/4 (CarteService) + Task 5/6/7 (vues)
- §5 flow detaille -> Task 2 (scanner), 3 (lier), 4 (perdue), 5/6/7 (vues)
- §6 exceptions -> Task 1 ✓
- §7 impact code -> Task 5/6/7 ✓
- §8 tests pytest 1-15 -> Task 2 (3-4), Task 3 (7), Task 4 (3), Task 5 (dispatch partiel — test #15 peut etre fait avec mocks) ✓
- §8 tests E2E 1-3 -> Task 8 ✓
- §10 workflow djc -> Task 9 ✓

**Placeholder scan :** aucun "TODO", "TBD", "similar to". Chaque step a son code.

**Type consistency :** 
- `ScanResult(wallet, is_wallet_ephemere)` utilisé partout de manière cohérente
- `CarteService.scanner_carte(carte, tenant_origine, ip)` — signature stable dans tous les tests et vues
- `CarteService.lier_a_user(qrcode_uuid, user, ip)` — signature stable
- `CarteService.declarer_perdue(user, number_printed)` — signature stable
- Exceptions : `CarteIntrouvable`, `CarteDejaLiee`, `UserADejaCarte` — identiques partout

**Note** : le test #15 de la spec (`test_dispatch_v1_si_server_cashless`) n'est pas explicitement dans le plan car il demande un mock sophistiqué de `fedow_connect.NFCcardFedow`. Considéré comme hors-scope tests unitaires (couvert par le test manuel de Test 6 dans `A TESTER et DOCUMENTER`).
