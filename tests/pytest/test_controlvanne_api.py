"""
Tests de l'API tireuse connectée (controlvanne) — Phase 2.
/ Tests for the connected tap API (controlvanne) — Phase 2.

LOCALISATION : tests/pytest/test_controlvanne_api.py

Couvre :
- TireuseAPIKey : création et validation de clé
- HasTireuseAccess : permission clé API + session admin
- TireuseViewSet : ping, authorize, event
- AuthKioskView : POST token → session cookie

Utilise la base dev existante (django-tenants, pas de test DB).
/ Uses existing dev database (django-tenants, no test DB).
"""

import pytest
import json
import uuid
from decimal import Decimal

from django.test import Client as DjangoClient
from django_tenants.utils import schema_context


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def tireuse_api_key(tenant):
    """Crée une TireuseAPIKey pour les tests.
    / Creates a TireuseAPIKey for tests."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseAPIKey

        _key_obj, key_string = TireuseAPIKey.objects.create_key(name="test-tireuse-key")
        yield key_string
        # Nettoyage / Cleanup
        TireuseAPIKey.objects.filter(name="test-tireuse-key").delete()


@pytest.fixture(scope="session")
def tireuse_headers(tireuse_api_key):
    """En-têtes d'auth avec clé TireuseAPIKey.
    / Auth headers with TireuseAPIKey."""
    return {"HTTP_AUTHORIZATION": f"Api-Key {tireuse_api_key}"}


@pytest.fixture(scope="session")
def tireuse_client():
    """Client Django pour le tenant lespass.
    / Django client for the lespass tenant."""
    return DjangoClient(HTTP_HOST="lespass.tibillet.localhost")


@pytest.fixture(scope="session")
def test_asset_tlf_api(tenant):
    """Asset TLF actif pour les tests API Phase 2.
    / Active TLF asset for Phase 2 API tests."""
    with schema_context(tenant.schema_name):
        from fedow_core.models import Asset
        from AuthBillet.models import Wallet

        asset = Asset.objects.filter(
            tenant_origin=tenant,
            category=Asset.TLF,
            active=True,
        ).first()
        if not asset:
            wallet_lieu = Wallet.objects.create(
                origin=tenant, name="Wallet lieu test API"
            )
            asset = Asset.objects.create(
                name="Monnaie locale test API",
                category=Asset.TLF,
                currency_code="EUR",
                wallet_origin=wallet_lieu,
                tenant_origin=tenant,
                active=True,
            )
        yield asset


@pytest.fixture(scope="session")
def test_tireuse(tenant, test_asset_tlf_api):
    """Crée une TireuseBec de test avec un débitmètre et un fut actif.
    / Creates a test TireuseBec with a flow meter and active keg."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec, Debimetre
        from BaseBillet.models import Product, Price

        # get_or_create avec first() pour éviter les doublons de runs précédents
        # / get_or_create with first() to avoid duplicates from previous runs
        debimetre = Debimetre.objects.filter(name="Test YF-S201").first()
        if not debimetre:
            debimetre = Debimetre.objects.create(
                name="Test YF-S201", flow_calibration_factor=6.5
            )

        # Fut avec prix au litre / Keg with per-liter price
        fut, _ = Product.objects.get_or_create(
            name="Test Fut API",
            categorie_article=Product.FUT,
            defaults={"publish": True},
        )
        Price.objects.get_or_create(
            product=fut,
            name="Litre",
            defaults={"prix": Decimal("5.00"), "poids_mesure": True},
        )
        tireuse, _created = TireuseBec.objects.get_or_create(
            nom_tireuse="Test Tap Phase2",
            defaults={
                "enabled": True,
                "debimetre": debimetre,
                "fut_actif": fut,
                "reservoir_ml": Decimal("5000.00"),
            },
        )
        yield tireuse
        # Pas de nettoyage — les fixtures utilisent get_or_create sur dev DB
        # / No cleanup — fixtures use get_or_create on dev DB


@pytest.fixture(scope="session")
def test_carte(tenant, test_asset_tlf_api):
    """CarteCashless de test avec wallet crédité (500 centimes = 5 EUR).
    / Test CarteCashless with credited wallet (500 cents = 5 EUR).

    CarteCashless.tag_id et number sont editable=False,
    on passe par le ORM directement (pas de formulaire).
    / CarteCashless.tag_id and number are editable=False,
    we go through the ORM directly (no form).
    """
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        carte = CarteCashless.objects.filter(tag_id="TSTCV01").first()
        if not carte:
            carte = CarteCashless(
                tag_id="TSTCV01",
                number="TSTCV01",
                uuid=uuid.uuid4(),
            )
            carte.save()

        # Ajouter un wallet avec du solde / Add a wallet with balance
        if not carte.wallet_ephemere:
            wallet = Wallet.objects.create(
                origin=tenant, name="Wallet test API TSTCV01"
            )
            carte.wallet_ephemere = wallet
            carte.save(update_fields=["wallet_ephemere"])

        Token.objects.update_or_create(
            wallet=carte.wallet_ephemere,
            asset=test_asset_tlf_api,
            defaults={"value": 500},
        )

        yield carte


# ──────────────────────────────────────────────────────────────────────
# Tests : TireuseAPIKey
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTireuseAPIKey:
    """Tests de création et validation de TireuseAPIKey.
    / Tests for TireuseAPIKey creation and validation."""

    def test_01_create_key(self, tenant):
        """On peut créer une clé et la valider.
        / Can create a key and validate it."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import TireuseAPIKey

            _obj, key_string = TireuseAPIKey.objects.create_key(name="test-create")
            assert key_string is not None
            assert len(key_string) > 0
            # Vérifier que la clé est valide / Check the key is valid
            assert TireuseAPIKey.objects.is_valid(key_string)
            # Nettoyage / Cleanup
            TireuseAPIKey.objects.filter(name="test-create").delete()


# ──────────────────────────────────────────────────────────────────────
# Tests : Permission HasTireuseAccess
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPermission:
    """Tests de la permission HasTireuseAccess.
    / Tests for HasTireuseAccess permission."""

    def test_02_ping_sans_auth_refuse(self, tireuse_client):
        """Requête sans auth → 403.
        / Request without auth → 403."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
        )
        assert response.status_code == 403

    def test_03_ping_avec_cle_tireuse(self, tireuse_client, tireuse_headers):
        """Requête avec TireuseAPIKey → 200.
        / Request with TireuseAPIKey → 200."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
            **tireuse_headers,
        )
        assert response.status_code == 200

    def test_04_ping_avec_laboutik_key_refuse(self, tireuse_client, auth_headers):
        """LaBoutikAPIKey ne doit PAS marcher sur l'endpoint tireuse → 403.
        / LaBoutikAPIKey must NOT work on the tap endpoint → 403."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
            **auth_headers,
        )
        assert response.status_code == 403

    def test_05_ping_avec_admin_session(self, admin_client):
        """Admin tenant connecté via session → 200.
        / Tenant admin logged in via session → 200."""
        response = admin_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
        )
        assert response.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# Tests : TireuseViewSet
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTireuseViewSet:
    """Tests du ViewSet tireuse.
    / Tests for the tap ViewSet."""

    def test_06_ping_simple(self, tireuse_client, tireuse_headers):
        """Ping sans UUID → pong.
        / Ping without UUID → pong."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
            **tireuse_headers,
        )
        data = response.json()
        assert data["status"] == "pong"
        assert data["message"] == "Server online"

    def test_07_ping_avec_uuid(self, tireuse_client, tireuse_headers, test_tireuse):
        """Ping avec UUID → config de la tireuse.
        / Ping with UUID → tap config."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data=json.dumps({"tireuse_uuid": str(test_tireuse.uuid)}),
            **tireuse_headers,
        )
        data = response.json()
        assert data["status"] == "pong"
        assert data["tireuse"]["nom"] == "Test Tap Phase2"
        assert data["tireuse"]["enabled"] is True
        assert data["tireuse"]["calibration_factor"] == 6.5

    def test_08_ping_uuid_inexistant(self, tireuse_client, tireuse_headers):
        """Ping avec UUID invalide → 404.
        / Ping with invalid UUID → 404."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data=json.dumps({"tireuse_uuid": str(uuid.uuid4())}),
            **tireuse_headers,
        )
        assert response.status_code == 404

    def test_09_authorize_carte_inconnue(
        self, tireuse_client, tireuse_headers, test_tireuse
    ):
        """Authorize avec UID inconnu → non autorisé.
        / Authorize with unknown UID → not authorized."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(test_tireuse.uuid),
                    "uid": "XXXXXXXX",
                }
            ),
            **tireuse_headers,
        )
        data = response.json()
        assert data["authorized"] is False
        assert "Unknown card" in data["message"]

    def test_10_authorize_carte_valide(
        self, tireuse_client, tireuse_headers, test_tireuse, test_carte
    ):
        """Authorize avec carte valide → autorisé + session créée.
        / Authorize with valid card → authorized + session created."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(test_tireuse.uuid),
                    "uid": test_carte.tag_id,
                }
            ),
            **tireuse_headers,
        )
        data = response.json()
        assert data["authorized"] is True
        assert data["is_maintenance"] is False
        assert "session_id" in data

    def test_11_event_pour_end(
        self, tireuse_client, tireuse_headers, test_tireuse, test_carte, tenant
    ):
        """Event pour_end → session fermée.
        / Event pour_end → session closed."""
        # D'abord autoriser pour créer une session ouverte
        # / First authorize to create an open session
        tireuse_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(test_tireuse.uuid),
                    "uid": test_carte.tag_id,
                }
            ),
            **tireuse_headers,
        )

        # Envoyer pour_end / Send pour_end
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(test_tireuse.uuid),
                    "uid": test_carte.tag_id,
                    "event_type": "pour_end",
                    "volume_ml": "250.00",
                }
            ),
            **tireuse_headers,
        )
        data = response.json()
        assert data["status"] == "ok"
        assert data["event_type"] == "pour_end"

        # Vérifier que la session est fermée / Check session is closed
        with schema_context(tenant.schema_name):
            from controlvanne.models import RfidSession

            session = (
                RfidSession.objects.filter(
                    tireuse_bec=test_tireuse, uid=test_carte.tag_id
                )
                .order_by("-started_at")
                .first()
            )
            assert session.ended_at is not None
            assert session.volume_delta_ml == Decimal("250.00")


# ──────────────────────────────────────────────────────────────────────
# Tests : AuthKioskView
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAuthKiosk:
    """Tests de l'auth kiosk (POST token → session cookie).
    / Tests for kiosk auth (POST token → session cookie)."""

    def test_12_auth_kiosk_sans_auth(self, tireuse_client):
        """Auth kiosk sans clé → 403.
        / Auth kiosk without key → 403."""
        response = tireuse_client.post(
            "/controlvanne/auth-kiosk/",
            content_type="application/json",
            data="{}",
        )
        assert response.status_code == 403

    def test_13_auth_kiosk_avec_cle(self, tireuse_client, tireuse_headers):
        """Auth kiosk avec clé → 200 + session_key.
        / Auth kiosk with key → 200 + session_key."""
        response = tireuse_client.post(
            "/controlvanne/auth-kiosk/",
            content_type="application/json",
            data="{}",
            **tireuse_headers,
        )
        data = response.json()
        assert response.status_code == 200
        assert data["status"] == "ok"
        assert "session_key" in data
        assert len(data["session_key"]) > 0


# ──────────────────────────────────────────────────────────────────────
# Tests : Vue kiosk
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestKioskView:
    """Tests de la vue kiosk (GET /controlvanne/kiosk/<uuid>/).
    / Tests for the kiosk view."""

    def test_14_kiosk_sans_auth(self, tireuse_client, test_tireuse):
        """Kiosk sans session → 403.
        / Kiosk without session → 403."""
        response = tireuse_client.get(
            f"/controlvanne/kiosk/{test_tireuse.uuid}/",
        )
        assert response.status_code == 403

    def test_15_kiosk_avec_admin_session(self, admin_client, test_tireuse):
        """Kiosk avec admin session → 200.
        / Kiosk with admin session → 200."""
        response = admin_client.get(
            f"/controlvanne/kiosk/{test_tireuse.uuid}/",
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-testid="kiosk-cards-grid"' in content

    def test_16_kiosk_uuid_inexistant(self, admin_client):
        """Kiosk avec UUID inexistant → 404.
        / Kiosk with nonexistent UUID → 404."""
        import uuid as uuid_module

        response = admin_client.get(
            f"/controlvanne/kiosk/{uuid_module.uuid4()}/",
        )
        assert response.status_code == 404

    def test_17_kiosk_avec_session_auth_kiosk(
        self, tireuse_client, tireuse_headers, test_tireuse
    ):
        """Auth kiosk puis kiosk → 200.
        / Auth kiosk then kiosk → 200."""
        # D'abord auth-kiosk pour obtenir le cookie
        # / First auth-kiosk to get the cookie
        tireuse_client.post(
            "/controlvanne/auth-kiosk/",
            content_type="application/json",
            data="{}",
            **tireuse_headers,
        )
        # Puis kiosk (meme client = meme cookie)
        # / Then kiosk (same client = same cookie)
        response = tireuse_client.get(
            f"/controlvanne/kiosk/{test_tireuse.uuid}/",
        )
        assert response.status_code == 200
