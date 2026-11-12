"""
Le scan du QR code d'une carte passe par le guichet, et lier une carte demande un clic.
/ Scanning a card's QR code goes through the login desk; linking a card needs a click.

LOCALISATION : tests/pytest/test_scan_qrcode_par_le_guichet.py
Spec : TECH_DOC/SESSIONS/OTP/CHANTIER-07-qrcode-par-le-guichet.md

Code testé : BaseBillet/views.py, ScanQrCode.retrieve et ScanQrCode.lier ;
MyAccount.lost_my_card (POST seulement).
/ Tested code: ScanQrCode.retrieve, ScanQrCode.lier, MyAccount.lost_my_card.

RÈGLES TESTÉES :
- le scan ne connecte jamais personne : un anonyme part au guichet ;
- un GET ne lie jamais une carte : seul le bouton (POST) le fait ;
- une carte liée à un autre compte reste à son propriétaire ;
- l'ancienne route POST /qr/link/ (email tapé par un anonyme) n'existe plus.
/ Scanning never logs in; a GET never links; another account's card is refused.

Fedow est simulé : on vérifie ce que la vue lui DEMANDE (ou ne lui demande pas).
/ Fedow is faked: we check what the view ASKS it (or does not ask).

Lancer / Run :
docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest /DjangoFiles/tests/pytest/test_scan_qrcode_par_le_guichet.py -v"
"""

import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import client_connecte, creer_utilisateur

pytestmark = pytest.mark.django_db

DOMAINE_DU_LIEU = "lespass.tibillet.localhost"


def fedow_simule(carte_vierge=True, uuid_du_portefeuille_de_la_carte=None,
                 uuid_du_portefeuille_de_la_personne=None, la_personne_a_deja_une_carte=False):
    """
    Un faux client Fedow : la carte scannée vient du lieu `lespass`.
    / A fake Fedow client: the scanned card comes from the `lespass` venue.
    """
    uuid_du_portefeuille_de_la_personne = uuid_du_portefeuille_de_la_personne or uuid.uuid4()
    api = mock.MagicMock()
    api.NFCcard.qr_retrieve.return_value = {
        "wallet_uuid": str(uuid_du_portefeuille_de_la_carte or uuid.uuid4()),
        "is_wallet_ephemere": carte_vierge,
        "origin": {"place": {"lespass_domain": DOMAINE_DU_LIEU}},
    }
    api.wallet.get_or_create_wallet.return_value = (
        SimpleNamespace(uuid=uuid_du_portefeuille_de_la_personne),
        False,
    )
    api.wallet.retrieve_by_signature.return_value = SimpleNamespace(
        validated_data={"has_user_card": la_personne_a_deja_une_carte},
    )
    return api


def scanner(client, qrcode_uuid, api, **en_tetes):
    """GET /qr/<uuid>/ avec Fedow simulé. / GET /qr/<uuid>/ with a fake Fedow."""
    with mock.patch("BaseBillet.views.FedowAPI", return_value=api):
        return client.get(f"/qr/{qrcode_uuid}/", **en_tetes)


def test_un_anonyme_qui_scanne_une_carte_part_au_guichet(tenant):
    with tenant_context(tenant):
        qrcode_uuid = uuid.uuid4()
        api = fedow_simule()

        reponse = scanner(client_connecte(), qrcode_uuid, api)

        assert reponse.status_code == 302
        assert reponse["Location"] == f"/connexion/?next=%2Fqr%2F{qrcode_uuid}%2F"
        assert not api.NFCcard.linkwallet_cardqrcode.called


def test_scanner_la_carte_d_un_autre_ne_connecte_pas_a_son_compte(tenant):
    """Avant, scanner une carte liée connectait au compte de son propriétaire.
    / Scanning a linked card used to log in as its owner."""
    with tenant_context(tenant):
        api = fedow_simule(carte_vierge=False)

        client = client_connecte()
        scanner(client, uuid.uuid4(), api)

        assert "_auth_user_id" not in client.session


def test_scanner_sa_propre_carte_mene_a_son_compte(tenant):
    with tenant_context(tenant):
        portefeuille = uuid.uuid4()
        api = fedow_simule(
            carte_vierge=False,
            uuid_du_portefeuille_de_la_carte=portefeuille,
            uuid_du_portefeuille_de_la_personne=portefeuille,
        )

        reponse = scanner(client_connecte(creer_utilisateur()), uuid.uuid4(), api)

        assert reponse.status_code == 302
        assert reponse["Location"] == "/my_account/"


def test_la_carte_d_un_autre_compte_n_est_jamais_liee(tenant):
    with tenant_context(tenant):
        api = fedow_simule(carte_vierge=False)

        reponse = scanner(client_connecte(creer_utilisateur()), uuid.uuid4(), api)

        assert reponse.status_code == 302
        assert reponse["Location"] == "/my_account/"
        assert not api.NFCcard.linkwallet_cardqrcode.called


def test_une_carte_vierge_affiche_le_bouton_lier_sans_rien_lier(tenant):
    """Un GET (lien, image, aperçu) ne doit jamais lier une carte.
    / A GET (link, image, preview) must never link a card."""
    with tenant_context(tenant):
        qrcode_uuid = uuid.uuid4()
        api = fedow_simule(carte_vierge=True)

        reponse = scanner(client_connecte(creer_utilisateur()), qrcode_uuid, api)

        assert reponse.status_code == 200
        html = reponse.content.decode()
        assert 'data-testid="qrcode-bouton-lier"' in html
        assert f'action="/qr/{qrcode_uuid}/lier/"' in html
        assert not api.NFCcard.linkwallet_cardqrcode.called


def test_une_personne_qui_a_deja_une_carte_n_en_lie_pas_une_seconde(tenant):
    with tenant_context(tenant):
        api = fedow_simule(carte_vierge=True, la_personne_a_deja_une_carte=True)

        reponse = scanner(client_connecte(creer_utilisateur()), uuid.uuid4(), api)

        assert reponse.status_code == 302
        assert reponse["Location"] == "/my_account/"
        assert not api.NFCcard.linkwallet_cardqrcode.called


def test_le_bouton_lier_refuse_un_anonyme(tenant):
    with tenant_context(tenant):
        api = fedow_simule(carte_vierge=True)

        with mock.patch("BaseBillet.views.FedowAPI", return_value=api):
            reponse = client_connecte().post(f"/qr/{uuid.uuid4()}/lier/")

        assert reponse.status_code == 403
        assert not api.NFCcard.linkwallet_cardqrcode.called


def test_le_bouton_lier_refuse_une_carte_devenue_liee_entre_temps(tenant):
    """La carte est relue chez Fedow au clic : quelqu'un a pu la lier entre-temps.
    / The card is read again on click: someone may have linked it meanwhile."""
    with tenant_context(tenant):
        api = fedow_simule(carte_vierge=False)

        with mock.patch("BaseBillet.views.FedowAPI", return_value=api):
            reponse = client_connecte(creer_utilisateur()).post(f"/qr/{uuid.uuid4()}/lier/")

        assert reponse.status_code == 302
        assert not api.NFCcard.linkwallet_cardqrcode.called


def test_un_autre_domaine_avec_le_domaine_du_lieu_dans_l_adresse_est_redirige(tenant):
    """On compare l'hôte, pas une sous-chaîne : `?x=<domaine>` n'évite pas la redirection.
    / Compare the host, not a substring."""
    from django.test import Client

    with tenant_context(tenant):
        qrcode_uuid = uuid.uuid4()
        api = fedow_simule()
        client_sur_un_autre_lieu = Client(HTTP_HOST="festival.tibillet.localhost")

        with mock.patch("BaseBillet.views.FedowAPI", return_value=api):
            reponse = client_sur_un_autre_lieu.get(f"/qr/{qrcode_uuid}/?x={DOMAINE_DU_LIEU}")

        assert reponse.status_code == 302
        assert reponse["Location"] == f"https://{DOMAINE_DU_LIEU}/qr/{qrcode_uuid}/"


def test_l_ancienne_liaison_par_email_n_existe_plus(tenant):
    with tenant_context(tenant):
        reponse = client_connecte().post("/qr/link/", {"email": "victime@mock.test"})

        assert reponse.status_code in (404, 405)


def test_declarer_sa_carte_perdue_refuse_un_get(tenant):
    """Un GET à effet de bord se déclenche par un simple lien ou une image.
    / A GET with side effects fires from a plain link or image."""
    # MyAccount.dispatch parle à Fedow avant de regarder la méthode : on le simule.
    # / MyAccount.dispatch talks to Fedow before checking the method: fake it.
    with tenant_context(tenant), mock.patch("BaseBillet.views.FedowAPI", return_value=fedow_simule()):
        reponse = client_connecte(creer_utilisateur()).get("/my_account/ABCDEF12/lost_my_card/")

        assert reponse.status_code == 405
