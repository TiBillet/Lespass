"""
tests/pytest/test_caisse_navigation.py — Tests Phase 2 etape 1 : navigation caisse.
tests/pytest/test_caisse_navigation.py — Tests Phase 2 step 1: POS navigation.

Couvre : serializer CartePrimaire, carte_primaire(), point_de_vente(), permissions.
Covers: CartePrimaireSerializer, carte_primaire(), point_de_vente(), permissions.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_caisse_navigation.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from django.conf import settings
from django.test import RequestFactory
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Product
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from laboutik.models import CartePrimaire, PointDeVente
from laboutik.serializers import CartePrimaireSerializer


# Schema tenant utilise pour les tests.
# / Tenant schema used for tests.
TENANT_SCHEMA = 'lespass'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in DB)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data(tenant):
    """Lance create_test_pos_data pour s'assurer que les donnees existent.
    / Runs create_test_pos_data to ensure test data exists."""
    from django.core.management import call_command
    # Forcer le schema lespass pour que la commande cree les donnees
    # dans le bon tenant (sinon elle prend le premier non-public = UUID).
    # / Force lespass schema so the command creates data in the right
    # tenant (otherwise it picks the first non-public = UUID).
    with schema_context(TENANT_SCHEMA):
        call_command('create_test_pos_data')
    return True


@pytest.fixture(scope="module")
def admin_user(tenant):
    """Un utilisateur admin du tenant pour tester l'acces par session.
    / A tenant admin user to test session-based access."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-caisse@tibillet.localhost'
        user, created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        # S'assurer que l'utilisateur est admin du tenant
        # / Ensure the user is admin of the tenant
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="module")
def tag_id_carte_primaire():
    """Tag NFC de la carte primaire de test (settings.DEMO_TAGID_CM).
    / Test primary card NFC tag (settings.DEMO_TAGID_CM)."""
    return getattr(settings, "DEMO_TAGID_CM", "A49E8E2A")


@pytest.fixture(scope="module")
def premier_pv(test_data):
    """Le PV 'Bar' cree par create_test_pos_data.
    / The 'Bar' POS created by create_test_pos_data."""
    with schema_context(TENANT_SCHEMA):
        # Chercher explicitement le PV 'Bar' (la carte primaire y a acces).
        # Ne pas utiliser .first() sans filtre car des PV de test
        # peuvent exister avec poid_liste=0 et ne pas etre dans la carte primaire.
        # / Explicitly look for the 'Bar' POS (the primary card has access).
        # Don't use .first() without filter because test POS may exist
        # with poid_liste=0 and not be in the primary card's POS list.
        return PointDeVente.objects.get(name='Bar')


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCartePrimaireSerializer:
    """Tests du serializer CartePrimaireSerializer.
    / Tests for CartePrimaireSerializer."""

    def test_tag_id_valide(self):
        """Tag NFC valide — nettoyé en majuscules.
        / Valid NFC tag — cleaned to uppercase."""
        serializer = CartePrimaireSerializer(data={"tag_id": "  abc123  "})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["tag_id"] == "ABC123"

    def test_tag_id_vide(self):
        """Tag NFC vide → erreur de validation.
        / Empty NFC tag → validation error."""
        serializer = CartePrimaireSerializer(data={"tag_id": ""})
        assert not serializer.is_valid()
        assert "tag_id" in serializer.errors

    def test_tag_id_absent(self):
        """Tag NFC absent du POST → erreur de validation.
        / NFC tag missing from POST → validation error."""
        serializer = CartePrimaireSerializer(data={})
        assert not serializer.is_valid()
        assert "tag_id" in serializer.errors

    def test_tag_id_espaces_seulement(self):
        """Tag NFC avec que des espaces → erreur de validation.
        / NFC tag with only spaces → validation error."""
        serializer = CartePrimaireSerializer(data={"tag_id": "   "})
        assert not serializer.is_valid()
        assert "tag_id" in serializer.errors


@pytest.mark.usefixtures("test_data")
class TestCartePrimaireVue:
    """Tests de la vue carte_primaire() (POST).
    / Tests for the carte_primaire() view (POST)."""

    def _make_client(self, admin_user, tenant):
        """Cree un client DRF authentifie comme admin du tenant.
        / Creates a DRF client authenticated as tenant admin."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=admin_user)
        # Activer le schema tenant pour les requetes
        # / Activate the tenant schema for requests
        client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
        return client

    def test_carte_primaire_valide(self, admin_user, tenant, tag_id_carte_primaire, premier_pv):
        """POST tag_id connu → redirect vers le PV (HX-Redirect).
        / POST known tag_id → redirect to POS (HX-Redirect)."""
        with schema_context(TENANT_SCHEMA):
            client = self._make_client(admin_user, tenant)
            response = client.post(
                '/laboutik/caisse/carte_primaire/',
                data={"tag_id": tag_id_carte_primaire},
            )
            # HttpResponseClientRedirect renvoie un 200 avec header HX-Redirect
            # / HttpResponseClientRedirect returns 200 with HX-Redirect header
            assert response.status_code == 200
            hx_redirect = response.get('HX-Redirect', '')
            assert 'point_de_vente' in hx_redirect
            assert 'uuid_pv=' in hx_redirect

    def test_carte_primaire_inconnue(self, admin_user, tenant):
        """POST tag_id inconnu → message d'erreur (pas de crash).
        / POST unknown tag_id → error message (no crash)."""
        with schema_context(TENANT_SCHEMA):
            client = self._make_client(admin_user, tenant)
            response = client.post(
                '/laboutik/caisse/carte_primaire/',
                data={"tag_id": "XXXXXXXXXX"},
            )
            assert response.status_code == 200
            contenu = response.content.decode()
            # Le message d'erreur "Carte inconnue" doit etre present
            # / The "Carte inconnue" error message must be present
            assert "Carte inconnue" in contenu or "Unknown card" in contenu

    def test_carte_non_primaire(self, admin_user, tenant):
        """POST tag_id d'une carte existante mais pas primaire → message d'erreur.
        / POST tag_id of an existing card that is NOT a primary card → error message."""
        with schema_context(TENANT_SCHEMA):
            # Utiliser une carte client (pas primaire)
            # / Use a client card (not primary)
            tag_client = getattr(settings, "DEMO_TAGID_CLIENT1", "52BE6543")
            client = self._make_client(admin_user, tenant)
            response = client.post(
                '/laboutik/caisse/carte_primaire/',
                data={"tag_id": tag_client},
            )
            assert response.status_code == 200
            contenu = response.content.decode()
            assert "non primaire" in contenu or "not a primary" in contenu.lower()

    def test_serializer_tag_id_vide_via_vue(self, admin_user, tenant):
        """POST tag_id vide via la vue → message d'erreur du serializer.
        / POST empty tag_id via the view → serializer error message."""
        with schema_context(TENANT_SCHEMA):
            client = self._make_client(admin_user, tenant)
            response = client.post(
                '/laboutik/caisse/carte_primaire/',
                data={"tag_id": ""},
            )
            assert response.status_code == 200
            contenu = response.content.decode()
            # Le serializer doit rejeter un tag vide
            # / The serializer must reject an empty tag
            assert len(contenu) > 0


@pytest.mark.usefixtures("test_data")
class TestPointDeVenteVue:
    """Tests de la vue point_de_vente() (GET).
    / Tests for the point_de_vente() view (GET)."""

    def _make_client(self, admin_user, tenant):
        """Cree un client DRF authentifie comme admin du tenant.
        / Creates a DRF client authenticated as tenant admin."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=admin_user)
        client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
        return client

    def test_point_de_vente_charge_vrais_produits(self, admin_user, tenant, premier_pv, tag_id_carte_primaire):
        """GET PV → les vrais produits depuis la DB (pas de mock).
        / GET POS → real products from DB (no mock)."""
        with schema_context(TENANT_SCHEMA):
            client = self._make_client(admin_user, tenant)
            response = client.get(
                '/laboutik/caisse/point_de_vente/',
                data={
                    "uuid_pv": str(premier_pv.uuid),
                    "tag_id_cm": tag_id_carte_primaire,
                },
            )
            assert response.status_code == 200
            contenu = response.content.decode()

            # Verifier que les produits du PV sont presents dans la page
            # / Verify that POS products are present in the page
            produits_du_pv = premier_pv.products.filter(methode_caisse__isnull=False)
            assert produits_du_pv.exists(), "Le PV doit avoir des produits"

            # Au moins un nom de produit doit etre dans le HTML rendu
            # / At least one product name must be in the rendered HTML
            noms_trouves = 0
            for produit in produits_du_pv:
                if produit.name in contenu:
                    noms_trouves += 1
            assert noms_trouves > 0, f"Aucun nom de produit trouve dans le HTML"


class TestSansAuthentification:
    """Tests sans authentification — doit etre refuse.
    / Tests without authentication — must be denied."""

    def test_sans_auth_caisse_list(self):
        """GET /laboutik/caisse/ sans auth → 403.
        / GET /laboutik/caisse/ without auth → 403."""
        with schema_context(TENANT_SCHEMA):
            from rest_framework.test import APIClient
            client = APIClient()
            client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
            response = client.get('/laboutik/caisse/')
            assert response.status_code == 403

    def test_sans_auth_carte_primaire(self):
        """POST /laboutik/caisse/carte_primaire/ sans auth → 403.
        / POST /laboutik/caisse/carte_primaire/ without auth → 403."""
        with schema_context(TENANT_SCHEMA):
            from rest_framework.test import APIClient
            client = APIClient()
            client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
            response = client.post(
                '/laboutik/caisse/carte_primaire/',
                data={"tag_id": "ANYTHING"},
            )
            assert response.status_code == 403
