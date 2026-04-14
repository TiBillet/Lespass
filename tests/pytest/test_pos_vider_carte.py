"""
tests/pytest/test_pos_vider_carte.py — Tests Phase 3 : bouton POS "Vider Carte".

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py -v --api-key dummy
"""
import uuid as uuid_module

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
    # get_or_create pour eviter l'IntegrityError si un run precedent n'a pas nettoye
    # / get_or_create to avoid IntegrityError if a previous run did not clean up
    asset, _created = Asset.objects.get_or_create(
        name=f'{VC_TEST_PREFIX} TLF',
        category=Asset.TLF,
        defaults={
            'currency_code': 'EUR',
            'wallet_origin': wallet_lieu_vc,
            'tenant_origin': tenant_lespass_vc,
        },
    )
    return asset


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
        # Nettoyer les Transactions referencing cette carte avant suppression
        # / Clean up Transactions referencing this card before deletion
        Transaction.objects.filter(primary_card=carte).delete()
        carte.delete()


@pytest.fixture
def carte_client_vc_avec_tlf(tenant_lespass_vc, asset_tlf_vc):
    """Carte client avec wallet_ephemere credite 1000c TLF."""
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


def _login_as_admin():
    from django.test import Client as TestClient
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
        'tag_id': 'XYZINCON',
        'tag_id_cm': carte_caissier_vc.tag_id,
        'uuid_pv': str(uuid_module.uuid4()),
    })
    assert response.status_code == 200
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


from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin


@pytest.fixture
def pv_cashless_vc(carte_caissier_vc):
    """PointDeVente qui autorise carte_caissier_vc et contient le Product VIDER_CARTE."""
    from laboutik.models import CartePrimaire, PointDeVente
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

    tx_refund = Transaction.objects.filter(
        card=carte_client_vc_avec_tlf, action=Transaction.REFUND,
    )
    assert tx_refund.count() == 1
    assert tx_refund.first().primary_card_id == carte_caissier_vc.pk

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
        assert (
            'acces' in contenu.lower()
            or 'access' in contenu.lower()
            or 'primaire' in contenu.lower()
        )
        assert Transaction.objects.filter(
            card=carte_client_vc_avec_tlf, action=Transaction.REFUND,
        ).count() == 0
    finally:
        with schema_context('lespass'):
            pv_orphan.delete()


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


def test_formatter_recu_vider_carte_structure_dict(
    tenant_lespass_vc, asset_tlf_vc, wallet_lieu_vc,
):
    """Le formatter retourne un dict compatible avec imprimer_async."""
    from laboutik.printing.formatters import formatter_recu_vider_carte

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
        assert recu["total"]["amount"] == 1000

        Transaction.objects.filter(sender=wallet_source).delete()
        wallet_source.delete()


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
