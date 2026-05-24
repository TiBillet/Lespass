"""
Test DB-only - API v2 : lecture des adhesions par wallet_uuid.
Run: docker exec lespass_django poetry run pytest tests/pytest/test_membership_by_wallet.py -q
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

HOST = "lespass.tibillet.localhost"


# ---------------------------------------------------------------------------
# Reutiliser la DB dev (pattern V2 onboard).
# / Reuse the dev DB (V2 onboard pattern).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


@pytest.fixture
def wallet_setup():
    from django.db import transaction
    from Customers.models import Client
    from AuthBillet.models import Wallet, TibilletUser
    from BaseBillet.models import ExternalApiKey, Product, Price, Membership
    from rest_framework_api_key.models import APIKey

    tenant = Client.objects.get(schema_name="lespass")
    suffix = uuid.uuid4().hex[:6]

    # On cree tout dans une transaction qu'on ANNULE a la fin : aucune donnee
    # ne reste dans la base dev, et aucun signal de suppression ne se declenche
    # (le signal de nettoyage d'image du projet plante sur un Product sans fichier).
    # / Create everything in a transaction rolled back at the end: nothing stays
    # in the dev DB and no delete signal fires.
    with tenant_context(tenant):
        with transaction.atomic():
            wallet = Wallet.objects.create(origin=tenant)
            user = TibilletUser.objects.create(
                email=f"adh-{suffix}@example.org",
                username=f"adh-{suffix}",
                wallet=wallet,
            )
            product = Product.objects.create(
                name=f"Adhesion {suffix}",
                categorie_article=Product.ADHESION,
            )
            price = Price.objects.create(
                product=product,
                name="Normal",
                prix=10,
                subscription_type=Price.YEAR,
            )
            Membership.objects.create(
                user=user,
                price=price,
                last_contribution=timezone.localtime(),
                deadline=timezone.localtime() + timedelta(days=30),  # valide
            )
            api_obj, key_str = APIKey.objects.create_key(name=f"laboutik-{suffix}")
            ExternalApiKey.objects.create(
                name=f"laboutik-{suffix}",
                key=api_obj,
                membership=True,
            )

            try:
                yield {"tenant": tenant, "wallet": wallet, "key": key_str}
            finally:
                # Annule tout ce qui a ete cree par ce fixture.
                # / Roll back everything created by this fixture.
                transaction.set_rollback(True)


def _get(wallet_uuid, key=None):
    client = APIClient()
    extra = {"SERVER_NAME": HOST}
    if key:
        extra["HTTP_AUTHORIZATION"] = f"Api-Key {key}"
    return client.get(
        f"/api/v2/memberships/by-wallet/?wallet_uuid={wallet_uuid}", **extra
    )


def test_by_wallet_sans_cle_est_refuse(wallet_setup):
    resp = _get(wallet_setup["wallet"].uuid)
    assert resp.status_code == 403


def test_by_wallet_wallet_inconnu_renvoie_liste_vide(wallet_setup):
    resp = _get(uuid.uuid4(), key=wallet_setup["key"])
    assert resp.status_code == 200
    assert resp.json()["memberships"] == []


def test_by_wallet_adhesion_valide(wallet_setup):
    resp = _get(wallet_setup["wallet"].uuid, key=wallet_setup["key"])
    assert resp.status_code == 200
    memberships = resp.json()["memberships"]
    assert len(memberships) == 1
    assert memberships[0]["is_valid"] is True
