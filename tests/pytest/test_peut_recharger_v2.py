"""
Tests du helper peut_recharger_v2(user) dans BaseBillet/views.py.
Tests for the peut_recharger_v2(user) helper in BaseBillet/views.py.

LOCALISATION : tests/pytest/test_peut_recharger_v2.py

Les 4 branches critiques du helper :
1. feature_desactivee : Configuration.module_monnaie_locale=False
2. v1_legacy : Configuration.server_cashless renseigne (LaBoutik externe)
3. wallet_legacy : user.wallet.origin pointe vers un tenant V1 (server_cashless set)
4. v2 : tenant courant OK + wallet user OK

/ Four critical branches of the helper.

Approche : on ne modifie PAS la Configuration du tenant courant "lespass"
(risque de casser d'autres tests). On bascule dans un tenant dedie via
tenant_context, on force les valeurs, on teste, on restaure.

/ Approach: we do NOT modify the current tenant's Configuration (risk of
breaking other tests). We switch to a dedicated tenant via tenant_context,
force values, test, restore.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_peut_recharger_v2.py -v --api-key dummy
"""

import sys
import uuid

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from django.core.management import call_command
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from BaseBillet.models import Configuration
from BaseBillet.views import peut_recharger_v2


TEST_PREFIX = "[test_peut_recharger_v2]"


@pytest.fixture(scope="module")
def tenant_federation_fed():
    """Bootstrape federation_fed (idempotent)."""
    call_command("bootstrap_fed_asset")
    return Client.objects.get(schema_name="federation_fed")


@pytest.fixture(scope="module")
def tenant_lespass():
    """Tenant de test principal du projet (schema 'lespass')."""
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def user_avec_wallet_v2(tenant_federation_fed):
    """
    User dont le wallet est origine=federation_fed (cas nominal V2).
    / User whose wallet is origin=federation_fed (nominal V2 case).
    """
    email = f"{TEST_PREFIX} v2 {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    user.wallet = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet {email}",
    )
    user.save(update_fields=["wallet"])
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_peut_recharger_v2_module_off(tenant_lespass, user_avec_wallet_v2):
    """
    Si Configuration.module_monnaie_locale=False, la fonction retourne
    (False, 'feature_desactivee').
    / If module_monnaie_locale is False, returns (False, 'feature_desactivee').
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        # Sauvegarde de la valeur initiale pour restauration.
        # / Save initial value for restore.
        module_initial = config.module_monnaie_locale
        config.module_monnaie_locale = False
        config.save(update_fields=["module_monnaie_locale"])

        try:
            ok, verdict = peut_recharger_v2(user_avec_wallet_v2)
            assert ok is False
            assert verdict == "feature_desactivee"
        finally:
            # Restauration, meme si le test echoue.
            # / Restore even if the test fails.
            config.module_monnaie_locale = module_initial
            config.save(update_fields=["module_monnaie_locale"])


def test_peut_recharger_v2_tenant_v1(tenant_lespass, user_avec_wallet_v2):
    """
    Si Configuration.server_cashless est renseigne (LaBoutik externe connecte),
    la fonction retourne (False, 'v1_legacy').
    / If server_cashless is set (external LaBoutik), returns (False, 'v1_legacy').
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_cashless_initial = config.server_cashless

        config.module_monnaie_locale = True
        config.server_cashless = "https://laboutik.example.com"
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])

        try:
            ok, verdict = peut_recharger_v2(user_avec_wallet_v2)
            assert ok is False
            assert verdict == "v1_legacy"
        finally:
            config.module_monnaie_locale = module_initial
            config.server_cashless = server_cashless_initial
            config.save(update_fields=["module_monnaie_locale", "server_cashless"])


def test_peut_recharger_v2_wallet_legacy(tenant_lespass, tenant_federation_fed):
    """
    Si le wallet de l'user a origin=tenant avec server_cashless renseigne,
    la fonction retourne (False, 'wallet_legacy').
    Le tenant courant est OK (V2), mais le wallet est legacy.
    / If the user's wallet has origin=tenant with server_cashless set,
    returns (False, 'wallet_legacy').
    """
    # 1. Rendre le tenant courant compatible V2 (module on, no server_cashless).
    # / 1. Make current tenant V2-compatible.
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_cashless_initial = config.server_cashless
        config.module_monnaie_locale = True
        config.server_cashless = None
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])

    # 2. Utiliser un tenant existant avec schema migre (chantefrein est le
    # second tenant de fixture du projet, cf. test_fedow_core.py:50).
    # On force son server_cashless pour simuler un tenant V1 legacy, puis
    # on le restaure a la fin du test.
    # / 2. Use an existing tenant with migrated schema (chantefrein is the
    # project's second fixture tenant). Force its server_cashless to simulate
    # a legacy V1 tenant, then restore it at the end.
    try:
        tenant_legacy = Client.objects.get(schema_name="chantefrein")
    except Client.DoesNotExist:
        pytest.skip("Tenant 'chantefrein' introuvable pour simuler un tenant legacy")

    with tenant_context(tenant_legacy):
        config_legacy = Configuration.get_solo()
        server_cashless_legacy_initial = config_legacy.server_cashless
        config_legacy.server_cashless = "https://laboutik.example.com"
        config_legacy.save(update_fields=["server_cashless"])

    # 3. Creer un user avec wallet origin=tenant_legacy.
    # / 3. Create a user with wallet origin=tenant_legacy.
    email = f"{TEST_PREFIX} legacy {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    user.wallet = Wallet.objects.create(
        origin=tenant_legacy,
        name=f"Wallet {email}",
    )
    user.save(update_fields=["wallet"])

    # 4. Tester dans le contexte du tenant V2 (lespass).
    # / 4. Test in the V2 tenant (lespass) context.
    try:
        with tenant_context(tenant_lespass):
            ok, verdict = peut_recharger_v2(user)
            assert ok is False
            assert verdict == "wallet_legacy"
    finally:
        # Restauration du tenant legacy et du tenant courant.
        # / Restore legacy tenant and current tenant.
        with tenant_context(tenant_legacy):
            config_legacy = Configuration.get_solo()
            config_legacy.server_cashless = server_cashless_legacy_initial
            config_legacy.save(update_fields=["server_cashless"])
        with tenant_context(tenant_lespass):
            config = Configuration.get_solo()
            config.module_monnaie_locale = module_initial
            config.server_cashless = server_cashless_initial
            config.save(update_fields=["module_monnaie_locale", "server_cashless"])


def test_peut_recharger_v2_ok(tenant_lespass, user_avec_wallet_v2):
    """
    Tenant courant V2 + wallet user avec origin=federation_fed
    -> retourne (True, 'v2').
    / Current tenant V2 + user wallet origin=federation_fed -> (True, 'v2').
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_cashless_initial = config.server_cashless
        config.module_monnaie_locale = True
        config.server_cashless = None
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])

        try:
            ok, verdict = peut_recharger_v2(user_avec_wallet_v2)
            assert ok is True
            assert verdict == "v2"
        finally:
            config.module_monnaie_locale = module_initial
            config.server_cashless = server_cashless_initial
            config.save(update_fields=["module_monnaie_locale", "server_cashless"])
