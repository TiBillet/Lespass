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
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import Membership
from Customers.models import Client
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


SCAN_QR_V2_TEST_PREFIX = "SCAN_QR_V2_TEST"


@pytest.fixture
def detail_cartes(db, tenant_origine):
    """
    Detail partage par toutes les cartes de test (lot de cartes).
    Le prefix est unique a ce fichier de test pour eviter les collisions
    avec d'autres suites qui creent aussi des Detail.
    / Shared Detail for all test cards. Unique prefix to avoid collisions
    with other test suites that also create Detail objects.

    Pas de teardown manuel : la fixture `db` de pytest-django utilise
    transaction.atomic + rollback a la fin du test, ce qui annule
    TOUTES les ecritures (CarteCashless, Wallet, Token, Transaction, Detail).
    / No manual teardown: pytest-django `db` fixture uses transaction.atomic
    + rollback, which undoes ALL writes automatically.
    """
    with tenant_context(tenant_origine):
        detail, _ = Detail.objects.get_or_create(
            base_url=SCAN_QR_V2_TEST_PREFIX,
            defaults={"origine": tenant_origine, "generation": 1},
        )
        yield detail


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
def user_tout_neuf(db, tenant_origine):
    """
    Un user sans wallet ni carte (cas du nouvel inscrit).
    create_user() lit connection.tenant pour client_source — il faut etre dans un tenant_context.
    / A user without wallet or card (fresh sign-up).
    create_user() reads connection.tenant for client_source — must be inside a tenant_context.
    """
    with tenant_context(tenant_origine):
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
        origin=tenant_origine,
        name="Wallet lieu test",
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


def test_scan_carte_identifiee_retourne_wallet_user(
    carte_vierge, tenant_origine, user_tout_neuf
):
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


# ------------------------------------------------------------------
# Tests — CarteService.lier_a_user
# / Tests — CarteService.lier_a_user
# ------------------------------------------------------------------


def test_lier_carte_nouveau_user_sans_tokens(
    carte_vierge, tenant_origine, user_tout_neuf
):
    """
    Lier un nouveau user a une carte vierge (sans tokens) : pas de Transaction FUSION.
    / Link a new user to a blank card (no tokens): no FUSION transaction.
    """
    from fedow_core.services import CarteService

    # Simuler un scan prealable qui cree wallet_ephemere
    CarteService.scanner_carte(carte_vierge, tenant_origine)
    carte_vierge.refresh_from_db()

    CarteService.lier_a_user(
        qrcode_uuid=carte_vierge.uuid,
        user=user_tout_neuf,
    )

    carte_vierge.refresh_from_db()
    user_tout_neuf.refresh_from_db()
    assert carte_vierge.user == user_tout_neuf
    assert carte_vierge.wallet_ephemere is None
    assert user_tout_neuf.wallet is not None
    assert (
        Transaction.objects.filter(action=Transaction.FUSION, card=carte_vierge).count()
        == 0
    )


def test_lier_carte_avec_tokens_cree_transaction_fusion(
    carte_vierge,
    tenant_origine,
    user_tout_neuf,
    asset_tlf,
):
    """
    Lier avec tokens sur wallet_ephemere : 1 Transaction FUSION creee,
    tokens transferes sur user.wallet.
    / Link with tokens on wallet_ephemere: 1 FUSION transaction created,
    tokens transferred to user.wallet.
    """
    from fedow_core.services import CarteService

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
        action=Transaction.FUSION,
        card=carte_vierge,
    )
    assert transactions_fusion.count() == 1
    assert transactions_fusion.first().amount == 2000
    token_user = Token.objects.get(wallet=user_tout_neuf.wallet, asset=asset_tlf)
    assert token_user.value == 2000


def test_lier_carte_antivol_user_deja_carte(
    carte_vierge,
    tenant_origine,
    detail_cartes,
    user_tout_neuf,
):
    """
    User a deja une autre carte : lever UserADejaCarte.
    / User already has another card: raise UserADejaCarte.
    """
    from fedow_core.services import CarteService

    # On cree une autre carte liee au user (sans assigner la var — la carte
    # existe en DB via objects.create, pas besoin de la reutiliser).
    # / Create another card linked to user (no var — exists in DB via create).
    CarteCashless.objects.create(
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

    # Creer user_b DANS le tenant_context comme user_tout_neuf
    with tenant_context(tenant_origine):
        user_b = User.objects.create_user(email="userb@test.local", password="p")

    with pytest.raises(CarteDejaLiee):
        CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_b)


def test_lier_rattrape_adhesions_anonymes(
    carte_vierge,
    tenant_origine,
    user_tout_neuf,
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
    carte_vierge,
    tenant_origine,
    user_tout_neuf,
    asset_tlf,
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
        name="TNF Test",
        currency_code="EUR",
        category=Asset.TNF,
        wallet_origin=wallet_lieu,
        tenant_origin=tenant_origine,
    )
    Token.objects.create(
        wallet=carte_vierge.wallet_ephemere, asset=asset_tlf, value=1000
    )
    Token.objects.create(
        wallet=carte_vierge.wallet_ephemere, asset=asset_tnf, value=500
    )

    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    assert (
        Transaction.objects.filter(
            action=Transaction.FUSION,
            card=carte_vierge,
        ).count()
        == 2
    )


# ------------------------------------------------------------------
# Tests — CarteService.declarer_perdue
# / Tests — CarteService.declarer_perdue
# ------------------------------------------------------------------


def test_declarer_perdue_nullify_carte(
    carte_vierge,
    tenant_origine,
    user_tout_neuf,
    asset_tlf,
):
    """
    Apres declarer_perdue : carte.user = None, wallet_ephemere = None.
    / After declarer_perdue: carte.user = None, wallet_ephemere = None.
    """
    from fedow_core.services import CarteService

    CarteService.scanner_carte(carte_vierge, tenant_origine)
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    CarteService.declarer_perdue(
        user=user_tout_neuf, number_printed=carte_vierge.number
    )

    carte_vierge.refresh_from_db()
    assert carte_vierge.user is None
    assert carte_vierge.wallet_ephemere is None


def test_declarer_perdue_preserve_wallet_user(
    carte_vierge,
    tenant_origine,
    user_tout_neuf,
    asset_tlf,
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
        wallet=carte_vierge.wallet_ephemere,
        asset=asset_tlf,
        value=3000,
    )
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    user_tout_neuf.refresh_from_db()
    wallet_user_pk = user_tout_neuf.wallet.pk

    CarteService.declarer_perdue(
        user=user_tout_neuf, number_printed=carte_vierge.number
    )

    # Le wallet user doit toujours exister et contenir les 3000
    user_tout_neuf.refresh_from_db()
    assert user_tout_neuf.wallet is not None
    assert user_tout_neuf.wallet.pk == wallet_user_pk
    token = Token.objects.get(wallet=user_tout_neuf.wallet, asset=asset_tlf)
    assert token.value == 3000


def test_declarer_perdue_carte_autre_user(
    carte_vierge,
    tenant_origine,
    user_tout_neuf,
    db,
):
    """
    Tentative de declarer_perdue pour une carte non liee au user : CarteIntrouvable.
    / Attempt to declare loss on a card not linked to user: raise CarteIntrouvable.
    """
    from fedow_core.services import CarteService

    with tenant_context(tenant_origine):
        user_b = User.objects.create_user(email="userb2@test.local", password="p")

    with pytest.raises(CarteIntrouvable):
        CarteService.declarer_perdue(user=user_b, number_printed=carte_vierge.number)


# ------------------------------------------------------------------
# Tests — CarteService.lister_cartes_du_user
# / Tests — CarteService.lister_cartes_du_user
# ------------------------------------------------------------------


def test_lister_cartes_user_sans_carte_retourne_liste_vide(
    user_tout_neuf,
    tenant_origine,
):
    """
    Un user sans carte liee retourne une liste vide.
    / A user with no linked card returns an empty list.
    """
    from fedow_core.services import CarteService

    cartes = CarteService.lister_cartes_du_user(user_tout_neuf)

    assert cartes == []


def test_lister_cartes_user_retourne_structure_template_compatible(
    carte_vierge,
    tenant_origine,
    user_tout_neuf,
):
    """
    Apres lier_a_user, lister retourne la carte avec number_printed + origin.place.name
    + origin.generation (structure attendue par card_table.html).
    / After lier_a_user, list returns card with template-compatible fields.
    """
    from fedow_core.services import CarteService

    CarteService.scanner_carte(carte_vierge, tenant_origine)
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    cartes = CarteService.lister_cartes_du_user(user_tout_neuf)

    assert len(cartes) == 1
    carte_info = cartes[0]
    # Structure attendue par card_table.html
    # / Structure expected by card_table.html
    assert carte_info.number_printed == carte_vierge.number
    assert carte_info.origin.place.name == tenant_origine.name
    assert carte_info.origin.generation == 1  # defini par detail_cartes fixture


def test_lister_cartes_user_filtre_autres_users(
    carte_vierge,
    tenant_origine,
    user_tout_neuf,
    detail_cartes,
):
    """
    La liste ne contient que les cartes du user, pas celles d'autres users.
    / List only contains the user's cards, not others.
    """
    from fedow_core.services import CarteService

    # Carte liee au user_tout_neuf
    CarteService.scanner_carte(carte_vierge, tenant_origine)
    CarteService.lier_a_user(qrcode_uuid=carte_vierge.uuid, user=user_tout_neuf)

    # Autre user avec autre carte
    with tenant_context(tenant_origine):
        user_b = User.objects.create_user(
            email=f"userb-{uuid.uuid4().hex[:6]}@test.local", password="p"
        )
    carte_b = CarteCashless.objects.create(
        tag_id=uuid.uuid4().hex[:8].upper(),
        number=uuid.uuid4().hex[:8].upper(),
        uuid=uuid.uuid4(),
        detail=detail_cartes,
        user=user_b,
    )

    cartes_a = CarteService.lister_cartes_du_user(user_tout_neuf)
    cartes_b = CarteService.lister_cartes_du_user(user_b)

    assert len(cartes_a) == 1
    assert len(cartes_b) == 1
    assert cartes_a[0].number_printed == carte_vierge.number
    assert cartes_b[0].number_printed == carte_b.number
