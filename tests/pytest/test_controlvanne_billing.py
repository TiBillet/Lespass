"""
Tests pytest pour la facturation tireuse (controlvanne/billing.py + viewsets.py).
/ Pytest tests for tap billing (controlvanne/billing.py + viewsets.py).

LOCALISATION : tests/pytest/test_controlvanne_billing.py

Couvre :
- TestCalculVolume : tests unitaires de calculer_volume_autorise_ml
- TestBillingIntegration : tests integration authorize + pour_end via API
"""

import uuid
from decimal import Decimal

import pytest
from django.test import Client as DjangoClient
from django_tenants.utils import schema_context


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tireuse_api_key_billing(tenant):
    """Cree une TireuseAPIKey pour les tests billing. Nettoie apres.
    / Creates a TireuseAPIKey for billing tests. Cleans up after."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseAPIKey
        api_key_obj, key_string = TireuseAPIKey.objects.create_key(
            name="test-billing-key"
        )
        yield key_string
        api_key_obj.delete()


@pytest.fixture(scope="session")
def billing_headers(tireuse_api_key_billing):
    """En-tetes HTTP auth pour les tests billing.
    / HTTP auth headers for billing tests."""
    return {"HTTP_AUTHORIZATION": f"Api-Key {tireuse_api_key_billing}"}


@pytest.fixture(scope="session")
def billing_client():
    """Client Django avec HTTP_HOST pour le tenant lespass.
    / Django client with HTTP_HOST for lespass tenant."""
    return DjangoClient(HTTP_HOST="lespass.tibillet.localhost")


@pytest.fixture(scope="session")
def asset_tlf(tenant):
    """Asset TLF actif pour le tenant lespass.
    / Active TLF asset for lespass tenant."""
    with schema_context(tenant.schema_name):
        from fedow_core.models import Asset
        from AuthBillet.models import Wallet

        # Wallet du lieu (wallet_origin de l'asset)
        wallet_lieu, _ = Wallet.objects.get_or_create(
            origin=tenant,
            name="Wallet lieu billing-test",
        )

        asset, _ = Asset.objects.get_or_create(
            tenant_origin=tenant,
            category=Asset.TLF,
            active=True,
            defaults={
                "name": "Monnaie locale test billing",
                "currency_code": "EUR",
                "wallet_origin": wallet_lieu,
            },
        )
        return asset


@pytest.fixture(scope="session")
def carte_avec_solde(tenant, asset_tlf):
    """CarteCashless avec wallet ephemere et 1000 centimes de solde TLF.
    / CarteCashless with ephemeral wallet and 1000 cents TLF balance."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        # Tag unique par session pour eviter les conflits entre runs
        # tag_id et number : max 8 chars dans CarteCashless
        tag_id = uuid.uuid4().hex[:8].upper()
        number = uuid.uuid4().hex[:8].upper()

        wallet_client = Wallet.objects.create(
            origin=tenant,
            name=f"Wallet test billing {tag_id}",
        )

        carte = CarteCashless.objects.create(
            tag_id=tag_id,
            number=number,
            wallet_ephemere=wallet_client,
        )

        token, _ = Token.objects.get_or_create(
            wallet=wallet_client,
            asset=asset_tlf,
            defaults={"value": 1000},  # 10.00 EUR en centimes
        )
        # S'assurer que le solde est bien a 1000 (idempotent)
        if token.value != 1000:
            token.value = 1000
            token.save(update_fields=["value"])

        return carte


@pytest.fixture(scope="session")
def tireuse_billing(tenant):
    """TireuseBec avec Debimetre, Product(FUT), Price(5EUR/L, poids_mesure=True).
    / TireuseBec with Debimetre, Product(FUT), Price(5EUR/L, poids_mesure=True)."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec, Debimetre
        from BaseBillet.models import Product, Price
        from laboutik.models import PointDeVente

        # Nettoyer les doublons de runs precedents
        Debimetre.objects.filter(name="Test billing debimetre").delete()
        TireuseBec.objects.filter(nom_tireuse="Tireuse billing test").delete()
        PointDeVente.objects.filter(name="POS tireuse billing test").delete()

        debimetre = Debimetre.objects.create(
            name="Test billing debimetre",
            flow_calibration_factor=6.5,
        )

        produit_fut, _ = Product.objects.get_or_create(
            name="Fut test billing",
            categorie_article="U",
            defaults={"publish": True},
        )

        # S'assurer qu'un Price poids_mesure existe pour ce produit
        if not produit_fut.prices.filter(poids_mesure=True).exists():
            Price.objects.create(
                product=produit_fut,
                name="Litre",
                prix=Decimal("5.00"),
                poids_mesure=True,
            )

        pdv = PointDeVente.objects.create(
            name="POS tireuse billing test",
            hidden=True,  # Caché pour ne pas polluer les tests menu_ventes / Hidden to not pollute menu_ventes tests
        )

        tireuse = TireuseBec.objects.create(
            nom_tireuse="Tireuse billing test",
            enabled=True,
            fut_actif=produit_fut,
            debimetre=debimetre,
            point_de_vente=pdv,
            reservoir_ml=Decimal("30000.00"),
            seuil_mini_ml=Decimal("0.00"),
            appliquer_reserve=False,
        )

        return tireuse


# ─────────────────────────────────────────────────────────────────────
# TestCalculVolume — tests unitaires
# ─────────────────────────────────────────────────────────────────────

class TestCalculVolume:
    """Tests unitaires de calculer_volume_autorise_ml."""

    def test_01_formule_basique(self):
        """1000 centimes / 5 EUR/L = 200ml? Non: 1000cts / 500cts/L * 1000 = 2000ml."""
        from controlvanne.billing import calculer_volume_autorise_ml

        resultat = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=99999,
        )
        assert resultat == Decimal("2000.00"), f"Attendu 2000.00, obtenu {resultat}"

    def test_02_limite_par_reservoir(self):
        """Le solde permet 2000ml mais le reservoir n'a que 500ml."""
        from controlvanne.billing import calculer_volume_autorise_ml

        resultat = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=500,
        )
        assert resultat == Decimal("500.00"), f"Attendu 500.00, obtenu {resultat}"

    def test_03_solde_zero(self):
        """Solde 0 → volume 0."""
        from controlvanne.billing import calculer_volume_autorise_ml

        resultat = calculer_volume_autorise_ml(
            solde_centimes=0,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=99999,
        )
        assert resultat == Decimal("0.00"), f"Attendu 0.00, obtenu {resultat}"

    def test_04_prix_zero(self):
        """Prix 0 → protection division par zero → volume 0."""
        from controlvanne.billing import calculer_volume_autorise_ml

        resultat = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("0.00"),
            reservoir_disponible_ml=99999,
        )
        assert resultat == Decimal("0.00"), f"Attendu 0.00, obtenu {resultat}"


# ─────────────────────────────────────────────────────────────────────
# TestBillingIntegration — tests via API
# ─────────────────────────────────────────────────────────────────────

class TestBillingIntegration:
    """Tests integration : authorize + pour_end via les endpoints API."""

    def test_05_authorize_avec_solde(
        self, billing_client, billing_headers, tireuse_billing, carte_avec_solde, tenant, asset_tlf
    ):
        """Authorize retourne authorized=True, solde_centimes et allowed_ml calcule."""
        response = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            data={
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
            },
            content_type="application/json",
            **billing_headers,
        )
        assert response.status_code == 200, f"Status {response.status_code}: {response.json()}"
        data = response.json()

        assert data["authorized"] is True, f"authorized devrait etre True: {data}"
        assert data["solde_centimes"] == 1000, f"solde attendu 1000, obtenu {data.get('solde_centimes')}"
        # 1000cts / 5EUR/L → 2000ml (reservoir 30L ne limite pas)
        assert data["allowed_ml"] == 2000.0, f"allowed_ml attendu 2000.0, obtenu {data.get('allowed_ml')}"

    def test_06_pour_end_cree_transaction(
        self, billing_client, billing_headers, tireuse_billing, carte_avec_solde, tenant, asset_tlf
    ):
        """pour_end avec 500ml cree une Transaction, debite le wallet de 250cts."""
        # D'abord authorize pour creer une session ouverte
        resp_auth = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            data={
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
            },
            content_type="application/json",
            **billing_headers,
        )
        assert resp_auth.status_code == 200
        assert resp_auth.json()["authorized"] is True

        # Ensuite pour_end avec 500ml
        resp_event = billing_client.post(
            "/controlvanne/api/tireuse/event/",
            data={
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
                "event_type": "pour_end",
                "volume_ml": "500.00",
            },
            content_type="application/json",
            **billing_headers,
        )
        assert resp_event.status_code == 200, f"Status {resp_event.status_code}: {resp_event.json()}"
        data = resp_event.json()

        # 500ml a 5EUR/L = 0.5L * 5EUR = 2.50 EUR = 250 centimes
        assert data.get("montant_centimes") == 250, (
            f"montant_centimes attendu 250, obtenu {data.get('montant_centimes')}"
        )
        assert "transaction_id" in data, f"transaction_id manquant dans {data}"

        # Verifier que le wallet a ete debite : 1000 - 250 = 750
        with schema_context(tenant.schema_name):
            from fedow_core.services import WalletService

            wallet_client = carte_avec_solde.wallet_ephemere
            solde = WalletService.obtenir_solde(wallet_client, asset_tlf)
            assert solde == 750, f"Solde attendu 750, obtenu {solde}"

    def test_07_authorize_fonds_insuffisants(
        self, billing_client, billing_headers, tireuse_billing, tenant, asset_tlf
    ):
        """Carte avec 0 centimes → authorized=False, message 'Insufficient funds'."""
        with schema_context(tenant.schema_name):
            from QrcodeCashless.models import CarteCashless
            from AuthBillet.models import Wallet
            from fedow_core.models import Token

            tag_id = uuid.uuid4().hex[:8].upper()
            number = uuid.uuid4().hex[:8].upper()

            wallet_zero = Wallet.objects.create(
                origin=tenant,
                name=f"Wallet zero {tag_id}",
            )
            carte_zero = CarteCashless.objects.create(
                tag_id=tag_id,
                number=number,
                wallet_ephemere=wallet_zero,
            )
            # Token a 0 centimes
            Token.objects.create(
                wallet=wallet_zero,
                asset=asset_tlf,
                value=0,
            )

        response = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            data={
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": tag_id,
            },
            content_type="application/json",
            **billing_headers,
        )
        assert response.status_code == 200, f"Status {response.status_code}: {response.json()}"
        data = response.json()

        assert data["authorized"] is False, f"authorized devrait etre False: {data}"
        assert data["solde_centimes"] == 0, f"solde attendu 0, obtenu {data.get('solde_centimes')}"

        # Nettoyage
        with schema_context(tenant.schema_name):
            carte_zero.delete()
            Token.objects.filter(wallet=wallet_zero).delete()
            wallet_zero.delete()
