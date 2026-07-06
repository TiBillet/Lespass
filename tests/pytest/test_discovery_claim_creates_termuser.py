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


@pytest.fixture
def pairing_device_laboutik(tenant_lespass):
    """Crée un PairingDevice role LB (Laboutik POS) / Creates a LB-role PairingDevice."""
    device = PairingDevice.objects.create(
        name=f'Test POS {uuid.uuid4().hex[:6]}',
        tenant=tenant_lespass,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='LB',
    )
    yield device
    # Cleanup : supprimer le TermUser créé s'il existe.
    # On NE supprime PAS le PairingDevice car son delete cascaderait vers
    # la table tenant controlvanne_tireusebec (qui n'existe pas en public
    # schema lors du teardown). Le test_discovery_pin_pairing.py existant
    # ne nettoie pas non plus ses devices.
    # / Cleanup: delete the created TermUser if any. We do NOT delete the
    # PairingDevice because cascade would hit the tenant-only table
    # controlvanne_tireusebec (not visible from public schema during
    # teardown). The existing test_discovery_pin_pairing.py does not
    # cleanup its devices either.
    with tenant_context(tenant_lespass):
        TermUser.objects.filter(email__contains=str(device.uuid)).delete()


@pytest.fixture
def pairing_device_kiosque(tenant_lespass):
    """Crée un PairingDevice role KI (Kiosque) / Creates a KI-role PairingDevice."""
    device = PairingDevice.objects.create(
        name=f'Test Kiosque {uuid.uuid4().hex[:6]}',
        tenant=tenant_lespass,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='KI',
    )
    yield device
    # Même remarque que plus haut : pas de device.delete() (cascade tenant).
    # / Same note as above: no device.delete() (tenant cascade).
    with tenant_context(tenant_lespass):
        TermUser.objects.filter(email__contains=str(device.uuid)).delete()


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
    """Crée un PairingDevice role TI + une TireuseBec liée dans le tenant.
    / Creates a TI-role PairingDevice + a linked TireuseBec in the tenant."""
    device = PairingDevice.objects.create(
        name=f'Test Tireuse {uuid.uuid4().hex[:6]}',
        tenant=tenant_lespass,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='TI',
    )
    with tenant_context(tenant_lespass):
        from controlvanne.models import TireuseBec
        from laboutik.models import PointDeVente

        tireuse = TireuseBec.objects.create(
            nom_tireuse=f'Test Tap Discovery {uuid.uuid4().hex[:6]}',
            pairing_device=device,
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
    """Flow d'appairage TI : le claim cree une TireuseAPIKey (pas de TermUser).
    / TI pairing flow: the claim creates a TireuseAPIKey (no TermUser)."""

    def test_claim_role_TI_retourne_cle_api_et_tireuse_uuid(self, pairing_device_tireuse, tenant_lespass):
        """PairingDevice(role=TI) + TireuseBec liée → 200 avec api_key + tireuse_uuid."""
        device, tireuse = pairing_device_tireuse
        response = _call_claim(device.pin_code)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        # La reponse contient la cle API et l'UUID de la tireuse liee.
        # / The response carries the API key and the linked tap UUID.
        assert data['api_key']
        assert data['tireuse_uuid'] == str(tireuse.uuid)

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
