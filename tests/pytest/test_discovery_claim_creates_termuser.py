"""
Tests du flow discovery claim qui crée désormais un TermUser + LaBoutikAPIKey liée.
/ Tests of the discovery claim flow which now creates a TermUser + linked LaBoutikAPIKey.
"""
import uuid

import pytest
from django.test import Client
from django_tenants.utils import schema_context, tenant_context
from rest_framework import status

from AuthBillet.models import TermUser, TibilletUser
from BaseBillet.models import LaBoutikAPIKey
from Customers.models import Client as TenantClient
from discovery.models import PairingDevice


# Note : le conftest.py définit déjà une fixture `tenant` session-scoped qui
# retourne le tenant 'lespass'. Pour éviter un conflit de portée (les fixtures
# ci-dessous sont function-scoped car elles créent des objets en DB par test),
# on renomme la fixture locale en `tenant_lespass`.
# / Note: conftest.py already defines a session-scoped `tenant` fixture returning
# the 'lespass' tenant. To avoid a scope mismatch (the fixtures below are
# function-scoped because they create DB rows per test), we rename the local
# fixture to `tenant_lespass`.
@pytest.fixture
def tenant_lespass():
    """Récupère le tenant lespass pour les tests / Gets the lespass tenant."""
    return TenantClient.objects.get(schema_name='lespass')


def _creer_un_terminal_en_attente(tenant, role, nom):
    """
    Cree un terminal et son code PIN, comme le fait l'admin.
    / Creates a terminal and its PIN, the way the admin does.

    C'est le vrai flux : le gestionnaire declare l'appareil, l'enregistrement fabrique le
    code, et il ira le taper dessus. Le claim ne cree PAS le terminal — il le remplit.
    """
    from discovery.services import fabriquer_le_code_pin_d_appairage
    from laboutik.models import Terminal

    with tenant_context(tenant):
        terminal = Terminal.objects.create(name=nom, terminal_role=role)
        appairage = fabriquer_le_code_pin_d_appairage(terminal)

    return terminal, appairage


def _nettoyer_le_terminal(tenant, terminal, appairage):
    """Supprime le terminal, son compte et son code PIN. / Cleans up after a test."""
    from laboutik.models import Terminal

    with tenant_context(tenant):
        terminal_en_base = Terminal.objects.filter(pk=terminal.pk).first()
        compte = terminal_en_base.term_user if terminal_en_base else None

        if terminal_en_base:
            terminal_en_base.delete()
        if compte:
            TermUser.objects.filter(pk=compte.pk).delete()

    PairingDevice.objects.filter(pk=appairage.pk).delete()


@pytest.fixture
def pairing_device_laboutik(tenant_lespass):
    """Un terminal de caisse LaBoutik, en attente de son appareil.
    / A LaBoutik POS terminal, waiting for its device."""
    terminal, appairage = _creer_un_terminal_en_attente(
        tenant_lespass, 'LB', f'Test POS {uuid.uuid4().hex[:6]}',
    )
    yield appairage
    _nettoyer_le_terminal(tenant_lespass, terminal, appairage)


@pytest.fixture
def pairing_device_kiosque(tenant_lespass):
    """Un terminal de borne kiosque, en attente de son appareil.
    / A kiosk terminal, waiting for its device."""
    terminal, appairage = _creer_un_terminal_en_attente(
        tenant_lespass, 'KI', f'Test Kiosque {uuid.uuid4().hex[:6]}',
    )
    yield appairage
    _nettoyer_le_terminal(tenant_lespass, terminal, appairage)


def _call_claim(pin):
    """Appelle POST /api/discovery/claim/ avec un PIN.
    / Calls POST /api/discovery/claim/ with a PIN."""
    # Le throttle anonyme /api/discovery/claim/ limite à 10/min.
    # cache.clear() efface TOUTES les clés Django (pas seulement le throttle) :
    # acceptable uniquement parce que les tests tournent sur la dev DB sans
    # données de production. Ne pas porter ce pattern en prod.
    # / The anonymous throttle on /api/discovery/claim/ limits to 10/min.
    # cache.clear() wipes ALL Django cache keys (not just the throttle):
    # acceptable only because tests run on dev DB without production data.
    # Do not port this pattern to production.
    from django.core.cache import cache
    cache.clear()
    client = Client(HTTP_HOST='tibillet.localhost')
    return client.post(
        '/api/discovery/claim/',
        data={'pin_code': pin},
        content_type='application/json',
    )


# Pas de @pytest.mark.django_db : le projet utilise la base dev directement via
# conftest._enable_db_access_for_all (autouse session). Utiliser transaction=True
# ici provoque un FLUSH en teardown qui échoue à cause des FK cross-schema
# (BaseBillet_price → fedow_public_assetfedowpublic).
# / No @pytest.mark.django_db: project uses dev DB directly via conftest's
# _enable_db_access_for_all (autouse session). Using transaction=True here
# triggers a teardown FLUSH that fails due to cross-schema FKs.
class TestClaimCreatesTermUserLaboutik:
    def test_claim_role_LB_cree_termuser_espece_TE(self, pairing_device_laboutik, tenant_lespass):
        """PairingDevice(role=LB) → TermUser(espece=TE)."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant_lespass):
            term_user = TermUser.objects.get(email=f'{pairing_device_laboutik.uuid}@terminals.local')
            assert term_user.espece == TibilletUser.TYPE_TERM

    def test_claim_role_LB_cree_termuser_role_LB(self, pairing_device_laboutik, tenant_lespass):
        """PairingDevice(role=LB) → TermUser(terminal_role=LB)."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant_lespass):
            term_user = TermUser.objects.get(email=f'{pairing_device_laboutik.uuid}@terminals.local')
            assert term_user.terminal_role == 'LB'

    def test_claim_cle_api_liee_au_termuser(self, pairing_device_laboutik, tenant_lespass):
        """LaBoutikAPIKey.user == TermUser créé."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant_lespass):
            term_user = TermUser.objects.get(email=f'{pairing_device_laboutik.uuid}@terminals.local')
            assert hasattr(term_user, 'laboutik_api_key')
            assert term_user.laboutik_api_key is not None

    def test_claim_termuser_client_source_est_le_tenant(self, pairing_device_laboutik, tenant_lespass):
        """TermUser.client_source == tenant courant."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant_lespass):
            term_user = TermUser.objects.get(email=f'{pairing_device_laboutik.uuid}@terminals.local')
            assert term_user.client_source_id == tenant_lespass.pk

    def test_claim_termuser_email_synthetique(self, pairing_device_laboutik, tenant_lespass):
        """Email = '<pairing_uuid>@terminals.local'."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        expected_email = f'{pairing_device_laboutik.uuid}@terminals.local'
        with tenant_context(tenant_lespass):
            assert TermUser.objects.filter(email=expected_email).exists()

    def test_claim_role_KI_cree_termuser_role_KI(self, pairing_device_kiosque, tenant_lespass):
        """PairingDevice(role=KI) → TermUser(terminal_role=KI)."""
        response = _call_claim(pairing_device_kiosque.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant_lespass):
            term_user = TermUser.objects.get(email=f'{pairing_device_kiosque.uuid}@terminals.local')
            assert term_user.terminal_role == 'KI'


@pytest.fixture
def pairing_device_tireuse(tenant_lespass):
    """
    Cree une TireuseBec. Son signal post_save fabrique lui-meme le code PIN.
    / Creates a TireuseBec. Its post_save signal issues the PIN itself.

    C'est le flux reel : on cree la tireuse dans l'admin, et elle nait avec son code PIN.
    Le PairingDevice porte cible_uuid = l'identifiant de la tireuse — c'est ainsi que le
    claim la retrouvera.
    """
    with tenant_context(tenant_lespass):
        from controlvanne.models import TireuseBec
        from laboutik.models import PointDeVente

        tireuse = TireuseBec.objects.create(
            nom_tireuse=f'Test Tap Discovery {uuid.uuid4().hex[:6]}',
        )
        # Le signal post_save cree automatiquement un PointDeVente non masque.
        # On le masque pour ne pas polluer premier_pv (test_menu_ventes.py,
        # test_cloture_caisse.py) — meme pattern que test_controlvanne_api.py.
        # / post_save signal auto-creates a non-hidden PointDeVente. Hide it so
        # it doesn't pollute premier_pv — same pattern as test_controlvanne_api.py.
        if tireuse.point_de_vente:
            PointDeVente.objects.filter(pk=tireuse.point_de_vente_id).update(
                hidden=True
            )

    # Le code PIN appartient au TERMINAL de la tireuse — son Raspberry Pi — pas a la
    # tireuse elle-meme. C'est le materiel qu'on appaire, pas l'objet metier.
    # / The PIN belongs to the tap's TERMINAL (its Raspberry Pi), not to the tap itself.
    device = PairingDevice.objects.get(cible_uuid=tireuse.terminal_id)

    yield device, tireuse
    # Cleanup : la cle API creee par le claim + la tireuse de test.
    # Pas de device.delete() (cascade vers une table tenant, cf. note plus haut).
    # / Cleanup: the API key created by the claim + the test tap.
    # No device.delete() (cascades to a tenant-only table, see note above).
    with tenant_context(tenant_lespass):
        from controlvanne.models import TireuseAPIKey, TireuseBec

        TireuseAPIKey.objects.filter(name=f'discovery-{device.uuid}').delete()
        TireuseBec.objects.filter(pk=tireuse.pk).delete()


class TestClaimTireuse:
    """
    Appairage d'une tireuse : meme pipeline que les autres roles.
    Un compte (TermUser), un Terminal, et une cle — de classe TireuseAPIKey.
    / Tap pairing: same pipeline as the other roles. Only the key class differs.
    """

    def test_claim_role_TI_retourne_cle_api_et_tireuse_uuid(self, pairing_device_tireuse, tenant_lespass):
        """Le claim rend la cle API et l'identifiant de la tireuse au Raspberry Pi."""
        device, tireuse = pairing_device_tireuse
        response = _call_claim(device.pin_code)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data['api_key']
        assert data['tireuse_uuid'] == str(tireuse.uuid)

    def test_le_terminal_de_la_tireuse_existe_avant_l_appairage(
        self, pairing_device_tireuse, tenant_lespass,
    ):
        """
        Le Raspberry Pi de la tireuse existe DES SA CREATION, en attente d'appairage.
        Le claim ne le cree pas : il le remplit, en lui posant son compte.
        / The tap's Pi exists FROM CREATION, waiting. The claim fills it in.
        """
        _device, tireuse = pairing_device_tireuse

        with tenant_context(tenant_lespass):
            from controlvanne.models import TireuseBec

            tireuse_avant = TireuseBec.objects.get(pk=tireuse.pk)

            # Le terminal est la, mais aucun appareil ne l'a encore reclame.
            # / The terminal is there, but no device has claimed it yet.
            assert tireuse_avant.terminal is not None
            assert tireuse_avant.terminal.terminal_role == 'TI'
            assert tireuse_avant.terminal.est_appaire() is False
            assert tireuse_avant.terminal.code_pin_en_attente() is not None

    def test_claim_role_TI_pose_le_compte_sur_le_terminal(
        self, pairing_device_tireuse, tenant_lespass,
    ):
        """
        Le claim pose le compte sur le terminal deja la. C'est ce qui rend la tireuse
        revocable depuis l'admin, comme une caisse.
        / The claim puts the account on the already-existing terminal.
        """
        device, tireuse = pairing_device_tireuse
        response = _call_claim(device.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant_lespass):
            from controlvanne.models import TireuseBec

            tireuse_rechargee = TireuseBec.objects.get(pk=tireuse.pk)

            assert tireuse_rechargee.terminal.est_appaire() is True
            assert tireuse_rechargee.terminal.term_user.terminal_role == 'TI'

    def test_claim_role_TI_lie_la_cle_au_compte_du_terminal(
        self, pairing_device_tireuse, tenant_lespass,
    ):
        """
        La cle de la tireuse est liee a son compte. Sans ce lien, revoquer une tireuse
        etait impossible : on ne savait pas quelle cle appartenait a quel appareil.
        / The tap's key is linked to its account. Without it, revoking a tap was impossible.
        """
        device, tireuse = pairing_device_tireuse
        response = _call_claim(device.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant_lespass):
            from controlvanne.models import TireuseAPIKey, TireuseBec

            tireuse_rechargee = TireuseBec.objects.get(pk=tireuse.pk)
            compte_du_terminal = tireuse_rechargee.terminal.term_user

            cle = TireuseAPIKey.objects.get(user=compte_du_terminal)
            assert cle.revoked is False

    def test_le_pin_et_la_cible_sont_vides_apres_l_appairage(
        self, pairing_device_tireuse, tenant_lespass,
    ):
        """
        Une fois l'appairage fait, le PairingDevice ne sert plus a rien : son code PIN et
        sa cible sont vides. Le lien durable est la cle etrangere TireuseBec.terminal.
        / Once paired, the PairingDevice is spent: PIN and target are cleared.
        """
        device, _tireuse = pairing_device_tireuse
        response = _call_claim(device.pin_code)
        assert response.status_code == status.HTTP_200_OK

        device.refresh_from_db()
        assert device.pin_code is None
        assert device.cible_uuid is None
        assert device.is_claimed is True

        with tenant_context(tenant_lespass):
            from controlvanne.models import TireuseAPIKey
            assert TireuseAPIKey.objects.filter(
                name=f'discovery-{device.uuid}'
            ).exists()

    def test_claim_role_TI_sans_tireusebec_refuse_500(self, tenant_lespass):
        """PairingDevice(role=TI) SANS TireuseBec liée → 500 et PIN non consommé."""
        device = PairingDevice.objects.create(
            name=f'Test Tireuse orpheline {uuid.uuid4().hex[:6]}',
            tenant=tenant_lespass,
            pin_code=PairingDevice.generate_unique_pin(),
            terminal_role='TI',
        )
        # PIÈGE (bug préexistant, hors périmètre de ce test) : une réponse 500
        # sur le schéma public déclenche AdminEmailHandler, dont le rapport
        # debug évalue les reverse_lazy de la SIDEBAR Unfold (settings.py)
        # sous urls_public → KeyError 'staff_admin'. On neutralise l'envoi
        # d'email pour tester NOTRE contrat (500 + PIN non consommé).
        # / TRAP (preexisting bug, out of this test's scope): a 500 response
        # on the public schema triggers AdminEmailHandler, whose debug report
        # evaluates the Unfold SIDEBAR reverse_lazy under urls_public →
        # KeyError 'staff_admin'. Mock the email emit to test OUR contract.
        from unittest import mock
        with mock.patch('django.utils.log.AdminEmailHandler.emit'):
            response = _call_claim(device.pin_code)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # Le PIN ne doit PAS etre marque consomme : l'operateur peut lier la
        # tireuse puis rejouer le meme PIN.
        # / The PIN must NOT be marked claimed: the operator can link the tap
        # then retry the same PIN.
        device.refresh_from_db()
        assert device.claimed_at is None
