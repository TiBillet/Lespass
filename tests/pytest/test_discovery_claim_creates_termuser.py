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
