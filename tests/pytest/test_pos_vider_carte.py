"""
tests/pytest/test_pos_vider_carte.py — Tests Phase 3 : bouton POS "Vider Carte".

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_pos_vider_carte.py -v --api-key dummy
"""

import uuid as uuid_module
from unittest.mock import patch

import pytest
from django.db import transaction as db_transaction
from django.utils import timezone
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import Wallet
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_connect.models import FedowConfig
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import WalletService


VC_TEST_PREFIX = "[vc_test]"


@pytest.fixture(scope="module")
def tenant_lespass_vc():
    return Client.objects.get(schema_name="lespass")


@pytest.fixture(scope="module")
def wallet_lieu_vc(tenant_lespass_vc):
    return Wallet.objects.create(name=f"{VC_TEST_PREFIX} Lieu")


@pytest.fixture(scope="module")
def asset_tlf_vc(tenant_lespass_vc, wallet_lieu_vc):
    # get_or_create pour eviter l'IntegrityError si un run precedent n'a pas nettoye
    # / get_or_create to avoid IntegrityError if a previous run did not clean up
    asset, _created = Asset.objects.get_or_create(
        name=f"{VC_TEST_PREFIX} TLF",
        category=Asset.TLF,
        defaults={
            "currency_code": "EUR",
            "wallet_origin": wallet_lieu_vc,
            "tenant_origin": tenant_lespass_vc,
        },
    )
    return asset


@pytest.fixture
def carte_caissier_vc(request, tenant_lespass_vc):
    """Carte NFC primaire du caissier pour les tests Phase 3.

    Resilience : get_or_create pour eviter IntegrityError si run precedent non nettoye.
    / Resilient: get_or_create avoids IntegrityError if a previous run did not clean up.
    """
    with schema_context("lespass"):
        detail, _ = Detail.objects.get_or_create(
            base_url=f"{VC_TEST_PREFIX}_DETAIL",
            origine=tenant_lespass_vc,
            defaults={"generation": 0},
        )
        carte, _created = CarteCashless.objects.get_or_create(
            tag_id="VCT00001",
            defaults={
                "number": "VCT00001",
                "uuid": uuid_module.uuid4(),
                "detail": detail,
            },
        )
        yield carte
        # Test marque django_db : le rollback de fin de test efface tout. Un nettoyage a
        # la main echouerait : la vente du vidage, scellee, protege la carte et le PV.
        # / django_db test: the end-of-test rollback erases everything. A manual cleanup
        # would fail: the sealed card-emptying sale protects the card and the POS.
        if request.node.get_closest_marker("django_db") is not None:
            return
        # Nettoyer les Transactions referencing cette carte avant suppression
        # / Clean up Transactions referencing this card before deletion
        Transaction.objects.filter(primary_card=carte).delete()
        carte.delete()


@pytest.fixture
def carte_client_vc_avec_tlf(request, tenant_lespass_vc, asset_tlf_vc):
    """Carte client avec wallet_ephemere credite 1000c TLF."""
    with schema_context("lespass"):
        detail, _ = Detail.objects.get_or_create(
            base_url=f"{VC_TEST_PREFIX}_DETAIL",
            origine=tenant_lespass_vc,
            defaults={"generation": 0},
        )
        wallet_user = Wallet.objects.create(name=f"{VC_TEST_PREFIX} Wallet client")
        carte = CarteCashless.objects.create(
            tag_id="VCT00002",
            number="VCT00002",
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_user,
        )
        with db_transaction.atomic():
            WalletService.crediter(
                wallet=wallet_user,
                asset=asset_tlf_vc,
                montant_en_centimes=1000,
            )
        yield carte
        # Test marque django_db : le rollback de fin de test efface tout. Un nettoyage a
        # la main echouerait : la vente du vidage, scellee, protege la carte et le PV.
        # / django_db test: the end-of-test rollback erases everything. A manual cleanup
        # would fail: the sealed card-emptying sale protects the card and the POS.
        if request.node.get_closest_marker("django_db") is not None:
            return
        from BaseBillet.models import LigneArticle

        LigneArticle.objects.filter(carte=carte).delete()
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet=wallet_user).delete()
        carte.delete()
        wallet_user.delete()


def test_rembourser_en_especes_accepte_primary_card(
    tenant_lespass_vc,
    wallet_lieu_vc,
    asset_tlf_vc,
    carte_client_vc_avec_tlf,
    carte_caissier_vc,
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
    """Cree (ou recupere) un utilisateur ADMIN DU TENANT 'lespass' et renvoie un
    client HTTP connecte. Le test est autonome : il ne depend PAS d'un user seede
    (le flush cree l'admin sous ADMIN_EMAIL, pas 'admin@admin.com').
    / Creates (or gets) a 'lespass' TENANT ADMIN user and returns a logged-in HTTP
    client. The test is self-contained: it does NOT depend on a seeded user.

    La vue vider_carte exige HasLaBoutikTerminalAccess → fallback HasLaBoutikAccess
    qui accepte une session dont l'user est admin du tenant (is_tenant_admin).
    On reutilise le pattern des autres tests : client_admin.add(tenant) +
    is_active=True + espece=TYPE_HUM (cf. test_caisse_navigation, test_paiement_especes_cb).
    / The vider_carte view requires HasLaBoutikTerminalAccess → HasLaBoutikAccess
    fallback that accepts a session whose user is tenant admin (is_tenant_admin).
    We reuse the pattern from other tests.
    """
    from django.test import Client as TestClient
    from AuthBillet.models import TibilletUser

    tenant = Client.objects.get(schema_name="lespass")

    client = TestClient(HTTP_HOST="lespass.tibillet.localhost")
    email = f"{VC_TEST_PREFIX.strip('[]')}-admin@tibillet.localhost".lower()
    user, _created = TibilletUser.objects.get_or_create(
        email=email,
        defaults={
            "username": email,
            "espece": TibilletUser.TYPE_HUM,
            "is_staff": True,
            "is_active": True,
        },
    )
    # Admin du tenant 'lespass' : indispensable pour is_tenant_admin(connection.tenant).
    # / Tenant admin of 'lespass': required for is_tenant_admin(connection.tenant).
    user.client_admin.add(tenant)
    # Le signal pre_save peut remettre is_active=False / espece (cf. PIEGES.md 9.88).
    # On reforce l'etat attendu pour que force_login et la permission passent.
    # / The pre_save signal may reset is_active/espece. Re-force the expected state.
    if not user.is_active or user.espece != TibilletUser.TYPE_HUM:
        user.is_active = True
        user.espece = TibilletUser.TYPE_HUM
        user.save(update_fields=["is_active", "espece"])
    client.force_login(user)
    return client, user


def test_vider_carte_preview_carte_inconnue_toast_erreur(carte_caissier_vc):
    """tag_id inexistant → toast erreur, aucune mutation DB."""
    client, user = _login_as_admin()
    response = client.post(
        "/laboutik/paiement/vider_carte/preview/",
        data={
            "tag_id": "XYZINCON",
            "tag_id_cm": carte_caissier_vc.tag_id,
            "uuid_pv": str(uuid_module.uuid4()),
        },
    )
    assert response.status_code == 200
    contenu = response.content.decode()
    assert "inconnue" in contenu.lower() or "unknown" in contenu.lower()


def test_vider_carte_preview_tag_identique_cm_rejette(carte_caissier_vc):
    """Protection self-refund : tag_id == tag_id_cm → toast erreur."""
    client, user = _login_as_admin()
    response = client.post(
        "/laboutik/paiement/vider_carte/preview/",
        data={
            "tag_id": carte_caissier_vc.tag_id,
            "tag_id_cm": carte_caissier_vc.tag_id,
            "uuid_pv": str(uuid_module.uuid4()),
        },
    )
    assert response.status_code == 200
    contenu = response.content.decode()
    assert "carte primaire" in contenu.lower() or "primary card" in contenu.lower()


def _poster_preview(carte_client, carte_caissier, action_carte=None):
    """
    POST vers vider_carte_preview, avec ou sans choix deja fait.
    / POST to vider_carte_preview, with or without a choice already made.
    """
    client, user = _login_as_admin()
    donnees = {
        "tag_id": carte_client.tag_id,
        "tag_id_cm": carte_caissier.tag_id,
        "uuid_pv": str(uuid_module.uuid4()),
    }
    if action_carte is not None:
        donnees["action_carte"] = action_carte
    # Lieu non relie a l'ancien Fedow (simule) : l'apercu ne lit que le Fedow local,
    # aucun appel reseau.
    # / Venue not linked to the old Fedow (faked): the preview reads the local Fedow only.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        response = client.post("/laboutik/paiement/vider_carte/preview/", data=donnees)
    assert response.status_code == 200
    return response.content.decode()


def test_vider_carte_preview_action_cloturer_affiche_un_seul_bouton_reinitialiser(
    carte_client_vc_avec_tlf, carte_caissier_vc
):
    """
    action_carte=cloturer (popup retour carte) : un seul bouton, vider_carte=true.
    / action_carte=cloturer: a single button posting vider_carte=true.
    """
    contenu = _poster_preview(carte_client_vc_avec_tlf, carte_caissier_vc, "cloturer")

    assert "Vous vous apprêtez à clôturer cette carte." in contenu
    assert "Cette action est irréversible" in contenu
    assert 'data-testid="vider-carte-btn-annuler"' in contenu
    # Annuler revient a la popup retour carte / Cancel goes back to the card popup
    assert 'hx-post="/laboutik/paiement/retour_carte/"' in contenu
    assert 'data-testid="vider-carte-btn-cloturer"' in contenu
    assert 'name="vider_carte" value="true"' in contenu
    assert 'name="action_carte" value="cloturer"' in contenu
    assert 'value="false"' not in contenu
    assert 'data-testid="vider-carte-btn-vider"' not in contenu


def test_vider_carte_preview_action_vider_affiche_un_seul_bouton_garder_la_carte(
    carte_client_vc_avec_tlf, carte_caissier_vc
):
    """
    action_carte=vider (popup retour carte) : un seul bouton, vider_carte=false.
    / action_carte=vider: a single button posting vider_carte=false.
    """
    contenu = _poster_preview(carte_client_vc_avec_tlf, carte_caissier_vc, "vider")

    assert "Vous vous apprêtez à vider cette carte." in contenu
    assert 'data-testid="vider-carte-btn-annuler"' in contenu
    assert 'data-testid="vider-carte-btn-vider"' in contenu
    assert 'name="vider_carte" value="false"' in contenu
    assert 'name="action_carte" value="vider"' in contenu
    assert 'value="true"' not in contenu
    assert 'data-testid="vider-carte-btn-cloturer"' not in contenu


def test_vider_carte_preview_action_inconnue_garde_le_choix_habituel(
    carte_client_vc_avec_tlf, carte_caissier_vc
):
    """
    Sans action_carte, ou avec une valeur inconnue (tuile « Vider carte ») :
    le bouton habituel « Rembourser et réinitialiser » s'affiche.
    / Without (or with an unknown) action_carte: the usual button is shown.
    """
    for action_carte in (None, "nimportequoi"):
        contenu = _poster_preview(
            carte_client_vc_avec_tlf, carte_caissier_vc, action_carte
        )
        assert 'data-testid="vider-carte-btn-confirm"' in contenu
        assert 'data-testid="vider-carte-btn-cloturer"' not in contenu
        assert 'data-testid="vider-carte-btn-vider"' not in contenu


from BaseBillet.models import LigneArticle, PaymentMethod
from BaseBillet.models_vente import Vente


@pytest.fixture
def pv_cashless_vc(request, carte_caissier_vc):
    """PointDeVente qui autorise carte_caissier_vc et contient le Product VIDER_CARTE."""
    from laboutik.models import CartePrimaire, PointDeVente
    from BaseBillet.services_refund import get_or_create_product_remboursement

    with schema_context("lespass"):
        pv, _ = PointDeVente.objects.get_or_create(
            name="VC Test PV",
            defaults={"comportement": "V", "hidden": False},
        )
        cp, _ = CartePrimaire.objects.get_or_create(
            carte=carte_caissier_vc,
            defaults={"edit_mode": False},
        )
        cp.points_de_vente.add(pv)
        product_vc = get_or_create_product_remboursement()
        pv.products.add(product_vc)
        yield pv
        # Test marque django_db : le rollback de fin de test efface tout. Un nettoyage a
        # la main echouerait : la vente du vidage, scellee, protege la carte et le PV.
        # / django_db test: the end-of-test rollback erases everything. A manual cleanup
        # would fail: the sealed card-emptying sale protects the card and the POS.
        if request.node.get_closest_marker("django_db") is not None:
            return
        pv.products.remove(product_vc)
        cp.points_de_vente.remove(pv)
        cp.delete()
        pv.delete()


@pytest.mark.django_db
def test_vider_carte_execute_remboursement_complet(
    carte_client_vc_avec_tlf,
    carte_caissier_vc,
    pv_cashless_vc,
):
    """
    POST /laboutik/paiement/vider_carte/ avec vider_carte=false :
    1 Transaction REFUND TLF ; la vente VIDAGE_CARTE porte un règlement espèces de
    −1000, et aucune LigneArticle « Refund » n'est écrite (D12).
    primary_card de la Transaction == carte_caissier.
    """
    client, user = _login_as_admin()
    # Lieu non relie a l'ancien Fedow (simule) : vidage local seul, aucun appel reseau.
    # / Venue not linked to the old Fedow (faked): local emptying only, no network call.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        response = client.post(
            "/laboutik/paiement/vider_carte/",
            data={
                "tag_id": carte_client_vc_avec_tlf.tag_id,
                "tag_id_cm": carte_caissier_vc.tag_id,
                "uuid_pv": str(pv_cashless_vc.uuid),
                "vider_carte": "false",
            },
        )
    assert response.status_code == 200, response.content.decode()[:500]

    tx_refund = Transaction.objects.filter(
        card=carte_client_vc_avec_tlf,
        action=Transaction.REFUND,
    )
    assert tx_refund.count() == 1
    assert tx_refund.first().primary_card_id == carte_caissier_vc.pk

    vente_du_vidage = Vente.objects.get(
        nature=Vente.Nature.VIDAGE_CARTE, carte=carte_client_vc_avec_tlf
    )
    reglement_especes = vente_du_vidage.reglements.get(moyen=PaymentMethod.CASH)
    assert reglement_especes.montant == -1000
    assert not LigneArticle.objects.filter(
        carte=carte_client_vc_avec_tlf, vente__isnull=True
    ).exists()


@pytest.mark.django_db
def test_vider_carte_execute_avec_vv(
    carte_client_vc_avec_tlf,
    carte_caissier_vc,
    pv_cashless_vc,
):
    """vider_carte=true → carte.user=None, carte.wallet_ephemere=None."""
    client, user = _login_as_admin()
    # Lieu non relie a l'ancien Fedow (simule) : vidage local seul, aucun appel reseau.
    # / Venue not linked to the old Fedow (faked): local emptying only, no network call.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        response = client.post(
            "/laboutik/paiement/vider_carte/",
            data={
                "tag_id": carte_client_vc_avec_tlf.tag_id,
                "tag_id_cm": carte_caissier_vc.tag_id,
                "uuid_pv": str(pv_cashless_vc.uuid),
                "vider_carte": "true",
            },
        )
    assert response.status_code == 200

    carte_client_vc_avec_tlf.refresh_from_db()
    assert carte_client_vc_avec_tlf.user is None
    assert carte_client_vc_avec_tlf.wallet_ephemere is None


@pytest.mark.django_db
def test_vider_carte_action_cloturer_reinitialise_et_affiche_l_ecran_cloture(
    carte_client_vc_avec_tlf,
    carte_caissier_vc,
    pv_cashless_vc,
):
    """
    action_carte=cloturer : la carte est reinitialisee, meme si le POST porte
    vider_carte=false. L'ecran final annonce la cloture.
    / action_carte=cloturer resets the card, whatever vider_carte says.
    """
    client, user = _login_as_admin()
    # Lieu non relie a l'ancien Fedow (simule) : vidage local seul, aucun appel reseau.
    # / Venue not linked to the old Fedow (faked): local emptying only, no network call.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        response = client.post(
            "/laboutik/paiement/vider_carte/",
            data={
                "tag_id": carte_client_vc_avec_tlf.tag_id,
                "tag_id_cm": carte_caissier_vc.tag_id,
                "uuid_pv": str(pv_cashless_vc.uuid),
                "vider_carte": "false",
                "action_carte": "cloturer",
            },
        )
    assert response.status_code == 200
    contenu = response.content.decode()

    carte_client_vc_avec_tlf.refresh_from_db()
    assert carte_client_vc_avec_tlf.wallet_ephemere is None

    assert "Carte n° VCT0 0002 clôturée avec succès" in contenu
    assert "Montant à rembourser au client" in contenu
    assert "10,00" in contenu
    assert 'data-testid="vider-carte-success-donnees"' in contenu
    assert "Rangez la carte avec les cartes vierges." in contenu
    assert 'data-testid="vider-carte-btn-retour-caisse"' in contenu
    assert 'data-testid="vider-carte-btn-imprimer"' not in contenu


@pytest.mark.django_db
def test_vider_carte_action_vider_garde_la_carte_et_affiche_le_nouveau_solde(
    carte_client_vc_avec_tlf,
    carte_caissier_vc,
    pv_cashless_vc,
):
    """
    action_carte=vider : la carte garde son wallet, meme si le POST porte
    vider_carte=true. L'ecran final affiche le nouveau solde : tout a ete rembourse,
    la carte est vide (« Carte vide », aucune ligne de solde).
    / action_carte=vider keeps the card wallet; final screen shows "Carte vide".
    """
    wallet_avant = carte_client_vc_avec_tlf.wallet_ephemere
    client, user = _login_as_admin()
    # Lieu non relie a l'ancien Fedow (simule) : vidage local seul, aucun appel reseau.
    # / Venue not linked to the old Fedow (faked): local emptying only, no network call.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        response = client.post(
            "/laboutik/paiement/vider_carte/",
            data={
                "tag_id": carte_client_vc_avec_tlf.tag_id,
                "tag_id_cm": carte_caissier_vc.tag_id,
                "uuid_pv": str(pv_cashless_vc.uuid),
                "vider_carte": "true",
                "action_carte": "vider",
            },
        )
    assert response.status_code == 200
    contenu = response.content.decode()

    carte_client_vc_avec_tlf.refresh_from_db()
    assert carte_client_vc_avec_tlf.wallet_ephemere == wallet_avant

    assert "Carte n° VCT0 0002 vidée avec succès" in contenu
    assert "Montant remboursé au client" in contenu
    assert "10,00" in contenu
    assert 'data-testid="vider-carte-success-nouveau-solde"' in contenu
    assert 'data-testid="vider-carte-success-carte-vide"' in contenu
    assert "Carte vide" in contenu
    assert 'data-testid="vider-carte-nouveau-solde-ligne"' not in contenu
    assert "Rendez sa carte au client" in contenu
    assert 'data-testid="vider-carte-btn-retour-caisse"' in contenu


@pytest.mark.django_db
def test_vider_carte_sans_action_garde_l_ecran_habituel(
    carte_client_vc_avec_tlf,
    carte_caissier_vc,
    pv_cashless_vc,
):
    """
    Sans action_carte (tuile « Vider carte ») : ecran habituel avec Imprimer + Terminé.
    / Without action_carte: the usual screen with Print + Done.
    """
    client, user = _login_as_admin()
    # Lieu non relie a l'ancien Fedow (simule) : vidage local seul, aucun appel reseau.
    # / Venue not linked to the old Fedow (faked): local emptying only, no network call.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        response = client.post(
            "/laboutik/paiement/vider_carte/",
            data={
                "tag_id": carte_client_vc_avec_tlf.tag_id,
                "tag_id_cm": carte_caissier_vc.tag_id,
                "uuid_pv": str(pv_cashless_vc.uuid),
                "vider_carte": "false",
            },
        )
    assert response.status_code == 200
    contenu = response.content.decode()

    assert 'data-testid="vider-carte-btn-imprimer"' in contenu
    assert 'data-testid="vider-carte-btn-termine"' in contenu
    assert 'data-testid="vider-carte-btn-retour-caisse"' not in contenu


def test_vider_carte_carte_primaire_pas_liee_pv_rejette(
    carte_client_vc_avec_tlf,
    carte_caissier_vc,
):
    """Si la carte caissier n'est pas dans pv.cartes_primaires → toast erreur."""
    from laboutik.models import PointDeVente

    client, user = _login_as_admin()
    with schema_context("lespass"):
        pv_orphan, _ = PointDeVente.objects.get_or_create(
            name="VC Orphan PV",
            defaults={"comportement": "V", "hidden": False},
        )

    try:
        response = client.post(
            "/laboutik/paiement/vider_carte/",
            data={
                "tag_id": carte_client_vc_avec_tlf.tag_id,
                "tag_id_cm": carte_caissier_vc.tag_id,
                "uuid_pv": str(pv_orphan.uuid),
                "vider_carte": "false",
            },
        )
        assert response.status_code == 200
        contenu = response.content.decode()
        assert (
            "acces" in contenu.lower()
            or "access" in contenu.lower()
            or "primaire" in contenu.lower()
        )
        assert (
            Transaction.objects.filter(
                card=carte_client_vc_avec_tlf,
                action=Transaction.REFUND,
            ).count()
            == 0
        )
    finally:
        with schema_context("lespass"):
            pv_orphan.delete()


def test_vider_carte_imprimer_recu_sans_imprimante_toast_info(pv_cashless_vc):
    """
    PV sans imprimante active → toast 'Pas d'imprimante configuree'.
    L'operation DB n'est pas affectee (deja enregistree avant cet endpoint).
    """
    client, user = _login_as_admin()
    response = client.post(
        "/laboutik/paiement/vider_carte/imprimer_recu/",
        data={
            "transaction_uuids": [str(uuid_module.uuid4())],
            "uuid_pv": str(pv_cashless_vc.uuid),
        },
    )
    assert response.status_code == 200
    contenu = response.content.decode()
    assert "imprimante" in contenu.lower() or "printer" in contenu.lower()


def test_formatter_recu_vider_carte_structure_dict(
    tenant_lespass_vc,
    asset_tlf_vc,
    wallet_lieu_vc,
):
    """Le formatter retourne un dict compatible avec imprimer_async."""
    from laboutik.printing.formatters import formatter_recu_vider_carte

    wallet_source = Wallet.objects.create(name=f"{VC_TEST_PREFIX} Source recu")
    with schema_context("lespass"):
        tx1 = Transaction.objects.create(
            sender=wallet_source,
            receiver=wallet_lieu_vc,
            asset=asset_tlf_vc,
            amount=800,
            action=Transaction.REFUND,
            tenant=tenant_lespass_vc,
            datetime=timezone.now(),
            ip="127.0.0.1",
        )
        tx2 = Transaction.objects.create(
            sender=wallet_source,
            receiver=wallet_lieu_vc,
            asset=asset_tlf_vc,
            amount=200,
            action=Transaction.REFUND,
            tenant=tenant_lespass_vc,
            datetime=timezone.now(),
            ip="127.0.0.1",
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
        with schema_context("lespass"):
            from BaseBillet.models import LigneArticle

            wallets_test = Wallet.objects.filter(name__startswith=VC_TEST_PREFIX)
            assets_test = Asset.objects.filter(name__startswith=VC_TEST_PREFIX)
            LigneArticle.objects.filter(carte__tag_id__startswith="VCT").delete()
            Transaction.objects.filter(asset__in=assets_test).delete()
            Token.objects.filter(wallet__in=wallets_test).delete()
            CarteCashless.objects.filter(tag_id__startswith="VCT").delete()
            Detail.objects.filter(base_url__startswith=VC_TEST_PREFIX).delete()
            assets_test.delete()
            wallets_test.delete()
    except Exception:
        pass
    # Cleanup de l'admin tenant cree par _login_as_admin, dans son PROPRE try/except :
    # si le bloc ci-dessus leve (ex: ProtectedError sur un wallet), l'user resterait
    # en base (DB partagee, pas de rollback) et polluerait les runs suivants.
    # / Tenant admin cleanup in its OWN try/except so an exception in the block above
    # (e.g. ProtectedError) never leaves the user behind (shared DB, no rollback).
    try:
        with schema_context("lespass"):
            from AuthBillet.models import TibilletUser

            admin_email = f"{VC_TEST_PREFIX.strip('[]')}-admin@tibillet.localhost".lower()
            TibilletUser.objects.filter(email=admin_email).delete()
    except Exception:
        pass
