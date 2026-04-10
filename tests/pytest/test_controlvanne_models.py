"""
Tests complémentaires controlvanne — modèles, maintenance, events.
/ Complementary controlvanne tests — models, maintenance, events.

LOCALISATION : tests/pytest/test_controlvanne_models.py
"""

import json
import uuid
from decimal import Decimal

import pytest
from django.test import Client as DjangoClient
from django_tenants.utils import schema_context


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def cv_api_key(tenant):
    """TireuseAPIKey pour ces tests."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseAPIKey

        _obj, key = TireuseAPIKey.objects.create_key(name="test-cv-models")
        yield key
        TireuseAPIKey.objects.filter(name="test-cv-models").delete()


@pytest.fixture(scope="session")
def cv_headers(cv_api_key):
    return {"HTTP_AUTHORIZATION": f"Api-Key {cv_api_key}"}


@pytest.fixture(scope="session")
def cv_client():
    return DjangoClient(HTTP_HOST="lespass.tibillet.localhost")


@pytest.fixture(scope="session")
def cv_tireuse_sans_fut(tenant):
    """TireuseBec sans fut_actif (propriétés retournent les valeurs par défaut)."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec

        t, _created = TireuseBec.objects.get_or_create(
            nom_tireuse="Tap No Keg",
            defaults={
                "enabled": True,
                "reservoir_ml": Decimal("3000.00"),
            },
        )
        yield t


@pytest.fixture(scope="session")
def cv_tireuse_avec_fut(tenant):
    """TireuseBec avec fut_actif + prix au litre."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec
        from BaseBillet.models import Product, Price

        fut, _ = Product.objects.get_or_create(
            name="Test Stout Models",
            categorie_article=Product.FUT,
            defaults={"publish": True},
        )
        Price.objects.get_or_create(
            product=fut,
            name="Litre models",
            defaults={"prix": Decimal("4.00"), "poids_mesure": True},
        )
        t, _created = TireuseBec.objects.get_or_create(
            nom_tireuse="Tap With Keg",
            defaults={
                "enabled": True,
                "fut_actif": fut,
                "reservoir_ml": Decimal("10000.00"),
            },
        )
        yield t


@pytest.fixture(scope="session")
def cv_asset_tlf(tenant):
    """Asset TLF actif — le récupère ou le crée si nécessaire.
    / Active TLF asset — fetches or creates if needed."""
    with schema_context(tenant.schema_name):
        from fedow_core.models import Asset
        from AuthBillet.models import Wallet

        asset = Asset.objects.filter(
            tenant_origin=tenant,
            category=Asset.TLF,
            active=True,
        ).first()
        if not asset:
            wallet_lieu, _ = Wallet.objects.get_or_create(
                origin=tenant,
                name="Wallet lieu cv-models-test",
            )
            asset = Asset.objects.create(
                tenant_origin=tenant,
                category=Asset.TLF,
                active=True,
                name="Monnaie locale test cv-models",
                currency_code="EUR",
                wallet_origin=wallet_lieu,
            )
        yield asset


@pytest.fixture(scope="session")
def cv_carte_client(tenant, cv_asset_tlf):
    """CarteCashless avec wallet crédité 2000 centimes (20 EUR)."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        carte = CarteCashless.objects.filter(tag_id="TSTMD01").first()
        if not carte:
            carte = CarteCashless(tag_id="TSTMD01", number="TSTMD01", uuid=uuid.uuid4())
            carte.save()
        if not carte.wallet_ephemere:
            w = Wallet.objects.create(origin=tenant, name="Wallet TSTMD01")
            carte.wallet_ephemere = w
            carte.save(update_fields=["wallet_ephemere"])
        Token.objects.update_or_create(
            wallet=carte.wallet_ephemere,
            asset=cv_asset_tlf,
            defaults={"value": 2000},
        )
        yield carte


@pytest.fixture(scope="session")
def cv_carte_maintenance(tenant, cv_tireuse_avec_fut):
    """CarteCashless avec CarteMaintenance associée."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from controlvanne.models import CarteMaintenance

        carte = CarteCashless.objects.filter(tag_id="TSTMT01").first()
        if not carte:
            carte = CarteCashless(tag_id="TSTMT01", number="TSTMT01", uuid=uuid.uuid4())
            carte.save()
        CarteMaintenance.objects.get_or_create(
            carte=carte,
            defaults={"produit": "Eau claire", "notes": "Test maintenance"},
        )
        yield carte


# ──────────────────────────────────────────────────────────────────────
# Tests modèles
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTireuseBecProperties:
    def test_01_liquid_label_sans_fut(self, cv_tireuse_sans_fut):
        """Sans fut → 'Liquide'."""
        assert cv_tireuse_sans_fut.liquid_label == "Liquide"

    def test_02_liquid_label_avec_fut(self, cv_tireuse_avec_fut):
        """Avec fut → nom du produit."""
        assert cv_tireuse_avec_fut.liquid_label == "Test Stout Models"

    def test_03_prix_litre_sans_fut(self, cv_tireuse_sans_fut):
        """Sans fut → Decimal('0.00')."""
        assert cv_tireuse_sans_fut.prix_litre == Decimal("0.00")

    def test_04_prix_litre_avec_fut(self, cv_tireuse_avec_fut):
        """Avec fut + Price poids_mesure → 4.00."""
        assert cv_tireuse_avec_fut.prix_litre == Decimal("4.00")


@pytest.mark.django_db
class TestRfidSession:
    def test_05_close_with_volume(self, tenant, cv_tireuse_avec_fut):
        """close_with_volume ferme la session avec le bon volume."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import RfidSession

            session = RfidSession.objects.create(
                uid="CLOSEVOL",
                tireuse_bec=cv_tireuse_avec_fut,
            )
            assert session.ended_at is None
            session.close_with_volume(333.5)
            session.refresh_from_db()
            assert session.ended_at is not None
            assert session.volume_delta_ml == Decimal("333.50")

    def test_06_duration_seconds_open(self, tenant, cv_tireuse_avec_fut):
        """Session ouverte → duration_seconds = None."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import RfidSession

            session = RfidSession.objects.create(
                uid="DUROPEN",
                tireuse_bec=cv_tireuse_avec_fut,
            )
            assert session.duration_seconds is None

    def test_07_duration_seconds_closed(self, tenant, cv_tireuse_avec_fut):
        """Session fermée → duration_seconds > 0."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import RfidSession
            from django.utils import timezone
            from datetime import timedelta

            now = timezone.now()
            session = RfidSession.objects.create(
                uid="DURCLOS",
                tireuse_bec=cv_tireuse_avec_fut,
                started_at=now - timedelta(seconds=42),
                ended_at=now,
            )
            assert abs(session.duration_seconds - 42) < 1


# ──────────────────────────────────────────────────────────────────────
# Tests authorize maintenance
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAuthorizeMaintenance:
    def test_08_authorize_carte_maintenance(
        self, cv_client, cv_headers, cv_tireuse_avec_fut, cv_carte_maintenance
    ):
        """Carte maintenance → is_maintenance=True, allowed_ml=reservoir."""
        response = cv_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                    "uid": cv_carte_maintenance.tag_id,
                }
            ),
            **cv_headers,
        )
        data = response.json()
        assert data["authorized"] is True
        assert data["is_maintenance"] is True
        assert data["allowed_ml"] == float(cv_tireuse_avec_fut.reservoir_ml)


# ──────────────────────────────────────────────────────────────────────
# Tests events complémentaires
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEventsComplementaires:
    def test_09_pour_update(
        self, cv_client, cv_headers, cv_tireuse_avec_fut, cv_carte_client
    ):
        """pour_update met à jour le volume sans fermer la session."""
        # Authorize d'abord
        cv_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                    "uid": cv_carte_client.tag_id,
                }
            ),
            **cv_headers,
        )
        # pour_update
        response = cv_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                    "uid": cv_carte_client.tag_id,
                    "event_type": "pour_update",
                    "volume_ml": "150.00",
                }
            ),
            **cv_headers,
        )
        data = response.json()
        assert data["status"] == "ok"
        assert data["event_type"] == "pour_update"
        # Pas de montant_centimes (pas de facturation au pour_update)
        assert "montant_centimes" not in data

        # Session toujours ouverte
        with schema_context("lespass"):
            from controlvanne.models import RfidSession

            session = (
                RfidSession.objects.filter(
                    tireuse_bec=cv_tireuse_avec_fut,
                    uid=cv_carte_client.tag_id,
                    ended_at__isnull=True,
                )
                .order_by("-started_at")
                .first()
            )
            assert session is not None
            assert session.volume_delta_ml == Decimal("150.00")

        # Nettoyer : fermer la session
        cv_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                    "uid": cv_carte_client.tag_id,
                    "event_type": "card_removed",
                    "volume_ml": "150.00",
                }
            ),
            **cv_headers,
        )

    def test_10_card_removed(
        self, cv_client, cv_headers, cv_tireuse_avec_fut, cv_carte_client
    ):
        """card_removed ferme la session (comme pour_end)."""
        # Re-créditer le wallet avant authorize (les tests précédents ont pu débiter)
        with schema_context("lespass"):
            from fedow_core.models import Token, Asset
            from Customers.models import Client

            tenant = Client.objects.get(schema_name="lespass")
            asset_tlf = Asset.objects.filter(
                tenant_origin=tenant,
                category=Asset.TLF,
                active=True,
            ).first()
            if asset_tlf and cv_carte_client.wallet_ephemere:
                Token.objects.update_or_create(
                    wallet=cv_carte_client.wallet_ephemere,
                    asset=asset_tlf,
                    defaults={"value": 2000},
                )

        # Authorize
        cv_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                    "uid": cv_carte_client.tag_id,
                }
            ),
            **cv_headers,
        )
        # card_removed avec volume
        response = cv_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                    "uid": cv_carte_client.tag_id,
                    "event_type": "card_removed",
                    "volume_ml": "200.00",
                }
            ),
            **cv_headers,
        )
        data = response.json()
        assert data["status"] == "ok"
        assert data["event_type"] == "card_removed"

        # Session fermée
        with schema_context("lespass"):
            from controlvanne.models import RfidSession

            session = (
                RfidSession.objects.filter(
                    tireuse_bec=cv_tireuse_avec_fut,
                    uid=cv_carte_client.tag_id,
                )
                .order_by("-started_at")
                .first()
            )
            assert session.ended_at is not None

    def test_11_event_no_open_session(self, cv_client, cv_headers, cv_tireuse_avec_fut):
        """Event sans session ouverte → 404."""
        response = cv_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                    "uid": "NOSESSION",
                    "event_type": "pour_end",
                    "volume_ml": "100.00",
                }
            ),
            **cv_headers,
        )
        assert response.status_code == 404

    def test_12_authorize_tireuse_disabled(
        self, cv_client, cv_headers, cv_tireuse_sans_fut, cv_carte_client
    ):
        """Tireuse désactivée → authorized=False."""
        with schema_context("lespass"):
            cv_tireuse_sans_fut.enabled = False
            cv_tireuse_sans_fut.save(update_fields=["enabled"])

        response = cv_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps(
                {
                    "tireuse_uuid": str(cv_tireuse_sans_fut.uuid),
                    "uid": cv_carte_client.tag_id,
                }
            ),
            **cv_headers,
        )
        data = response.json()
        assert data["authorized"] is False
        assert "disabled" in data["message"].lower()

        # Remettre enabled
        with schema_context("lespass"):
            cv_tireuse_sans_fut.enabled = True
            cv_tireuse_sans_fut.save(update_fields=["enabled"])
