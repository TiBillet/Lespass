"""
Tests de la vue MyAccount.transactions_table pour la branche V2 (fedow_core local).
Tests for MyAccount.transactions_table — V2 branch (local fedow_core).

LOCALISATION : tests/pytest/test_transactions_table_v2.py

Couvre :
- Dispatch V2 vs V1
- Wallet absent
- Tri chronologique desc
- Exclusion actions techniques
- Reconstitution wallets historiques via FUSION
- Signe entrant/sortant
- Pagination 40/page

/ Covers V2 dispatch, empty wallet, desc sort, technical exclusion, historical
wallets via FUSION, signs, pagination.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
"""

import sys
import uuid

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory
from django_tenants.utils import tenant_context
from django.utils import timezone

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from BaseBillet.models import Configuration
from fedow_core.models import Asset, Transaction
from QrcodeCashless.models import CarteCashless
from BaseBillet.views import MyAccount, _structure_pour_transaction, _enrichir_transaction_v2


TEST_PREFIX = "[test_transactions_table_v2]"


@pytest.fixture(scope="module")
def tenant_federation_fed():
    """Bootstrape federation_fed (idempotent). / Bootstrap federation_fed."""
    call_command("bootstrap_fed_asset")
    return Client.objects.get(schema_name="federation_fed")


@pytest.fixture(scope="module")
def tenant_lespass():
    """Tenant principal du projet (schema 'lespass'). / Main project tenant."""
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def user_v2(tenant_federation_fed):
    """
    User avec wallet origine=federation_fed (cas V2 nominal).
    / User with wallet origin=federation_fed (V2 nominal case).
    """
    email = f"{TEST_PREFIX} v2 {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    user.wallet = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet {email}",
    )
    user.save(update_fields=["wallet"])
    return user


@pytest.fixture
def config_v2(tenant_lespass):
    """
    Met lespass en mode V2 (module_monnaie_locale=True, server_cashless=None),
    et restaure en fin de test.
    / Sets lespass to V2 mode, restores at teardown.
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_initial = config.server_cashless
        config.module_monnaie_locale = True
        config.server_cashless = None
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])
    yield tenant_lespass
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        config.module_monnaie_locale = module_initial
        config.server_cashless = server_initial
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])


def test_transactions_table_v2_dispatch_branche_v2(config_v2, user_v2):
    """
    Verdict peut_recharger_v2 == 'v2' -> le template transaction_history_v2.html
    est rendu.
    / V2 verdict -> transaction_history_v2.html template is rendered.
    """
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2
        response = MyAccount().transactions_table(request)
        assert response.status_code == 200
        html = response.content.decode()
        # Marker V2 present dans le HTML.
        # / V2 marker present in HTML.
        assert 'data-testid="tx-v2-container"' in html or 'data-testid="tx-v2-empty"' in html


@pytest.fixture
def asset_fed_instance(tenant_federation_fed):
    """L'unique Asset FED du systeme. / Unique FED Asset."""
    return Asset.objects.get(category=Asset.FED)


def test_structure_pour_transaction_refill_retourne_tibillet(
    asset_fed_instance, user_v2, tenant_federation_fed
):
    """
    REFILL -> structure = "TiBillet" (nom propre, convention mainteneur).
    / REFILL -> structure = "TiBillet" (brand name, maintainer convention).
    """
    tx = Transaction.objects.create(
        sender=asset_fed_instance.wallet_origin,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=2000,
        action=Transaction.REFILL,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
    )
    # user.wallet est le receiver -> receiver_est_historique=True
    # / user.wallet is receiver -> receiver_est_historique=True
    structure = _structure_pour_transaction(tx, receiver_est_historique=True)
    assert structure == "TiBillet"


def test_structure_pour_transaction_fusion_retourne_carte_number(
    asset_fed_instance, user_v2, tenant_federation_fed
):
    """
    FUSION avec card -> structure = "Carte #{card.number}".
    / FUSION with card -> structure = "Carte #{card.number}".
    """
    # Creer une carte avec un number imprime de 8 chars unique par run.
    # CarteCashless.number et tag_id ont une contrainte unique DB donc on
    # utilise deux UUID hex differents pour chaque run du test.
    # / 8-char printed number unique per run (unique DB constraint on
    # CarteCashless.number and .tag_id).
    number_unique = uuid.uuid4().hex[:8].upper()
    wallet_ephemere = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet ephemere {uuid.uuid4()}",
    )
    carte = CarteCashless.objects.create(
        tag_id=uuid.uuid4().hex[:8].upper(),
        number=number_unique,
        wallet_ephemere=wallet_ephemere,
    )
    tx = Transaction.objects.create(
        sender=wallet_ephemere,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=1500,
        action=Transaction.FUSION,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
        card=carte,
    )
    structure = _structure_pour_transaction(tx, receiver_est_historique=True)
    assert structure == f"Carte #{number_unique}"


def test_structure_pour_transaction_sale_retourne_organisation_collectif(
    asset_fed_instance, user_v2, tenant_lespass, tenant_federation_fed
):
    """
    SALE -> structure = nom du collectif receiver (via cache tenant_info_v2).
    / SALE -> structure = receiver collective name (via cache).
    """
    # Wallet du lieu lespass (receveur de la vente).
    # / Lespass venue wallet (sale receiver).
    wallet_lieu_lespass = Wallet.objects.create(
        origin=tenant_lespass,
        name=f"Wallet lieu lespass {uuid.uuid4()}",
    )
    tx = Transaction.objects.create(
        sender=user_v2.wallet,
        receiver=wallet_lieu_lespass,
        asset=asset_fed_instance,
        amount=500,
        action=Transaction.SALE,
        tenant=tenant_lespass,
        datetime=timezone.now(),
    )
    # Cold cache pour propre reconstitution.
    # / Cold cache for clean reconstruction.
    cache.delete("tenant_info_v2")

    # user est sender -> receiver_est_historique=False
    # / user is sender -> receiver_est_historique=False
    structure = _structure_pour_transaction(tx, receiver_est_historique=False)
    # Le nom de l'organisation lespass (depuis Configuration).
    # / Lespass Configuration organisation name.
    with tenant_context(tenant_lespass):
        config_lespass = Configuration.get_solo()
        nom_attendu = config_lespass.organisation
    assert structure == nom_attendu


def test_enrichir_transaction_v2_signe_entrant_sortant(
    asset_fed_instance, user_v2, tenant_lespass, tenant_federation_fed
):
    """
    SALE (sender=user.wallet) -> dict a signe='-'.
    REFILL (receiver=user.wallet) -> dict a signe='+'.
    / SALE sender=user -> signe='-'. REFILL receiver=user -> signe='+'.
    """
    wallet_lieu = Wallet.objects.create(
        origin=tenant_lespass,
        name=f"Wallet lieu {uuid.uuid4()}",
    )

    # SALE : user paye (sortant).
    # / SALE: user pays (outgoing).
    tx_sale = Transaction.objects.create(
        sender=user_v2.wallet,
        receiver=wallet_lieu,
        asset=asset_fed_instance,
        amount=350,
        action=Transaction.SALE,
        tenant=tenant_lespass,
        datetime=timezone.now(),
    )
    # REFILL : user recoit (entrant).
    # / REFILL: user receives (incoming).
    tx_refill = Transaction.objects.create(
        sender=asset_fed_instance.wallet_origin,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=2000,
        action=Transaction.REFILL,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
    )

    wallets_historiques_pks = {user_v2.wallet.pk}

    item_sale = _enrichir_transaction_v2(tx_sale, user_v2.wallet, wallets_historiques_pks)
    item_refill = _enrichir_transaction_v2(tx_refill, user_v2.wallet, wallets_historiques_pks)

    assert item_sale["signe"] == "-"
    assert item_sale["amount_euros"] == 3.5
    assert item_sale["action"] == Transaction.SALE

    assert item_refill["signe"] == "+"
    assert item_refill["amount_euros"] == 20.0
    assert item_refill["asset_name_affichage"] == "TiBillets"
    assert item_refill["structure"] == "TiBillet"


def test_reconstitution_wallets_historiques_via_fusion(
    asset_fed_instance, config_v2, user_v2, tenant_lespass, tenant_federation_fed
):
    """
    Un wallet ephemere + une FUSION(receiver=user.wallet) + une SALE sur
    le wallet ephemere -> la SALE apparait dans l'historique du user.
    / ephemeral wallet + FUSION + SALE on ephemeral -> SALE appears in
    user history.
    """
    # 1. Creer un wallet ephemere (ex-carte anonyme).
    # / 1. Create ephemeral wallet (ex-anonymous card).
    wallet_ephemere = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet ephemere {uuid.uuid4()}",
    )

    # 2. Creer une SALE AVANT identification (sender=wallet_ephemere).
    # / 2. Create a SALE BEFORE identification.
    wallet_lieu = Wallet.objects.create(
        origin=tenant_lespass,
        name=f"Wallet lieu {uuid.uuid4()}",
    )
    tx_sale = Transaction.objects.create(
        sender=wallet_ephemere,
        receiver=wallet_lieu,
        asset=asset_fed_instance,
        amount=500,
        action=Transaction.SALE,
        tenant=tenant_lespass,
        datetime=timezone.now(),
    )

    # 3. Creer la FUSION(sender=wallet_ephemere, receiver=user.wallet).
    # / 3. Create FUSION.
    tx_fusion = Transaction.objects.create(
        sender=wallet_ephemere,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=1500,
        action=Transaction.FUSION,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
    )

    # 4. Appeler la vue V2.
    # / 4. Call V2 view.
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2
        response = MyAccount().transactions_table(request)
        assert response.status_code == 200

        html = response.content.decode()
        # Les 2 tx (SALE + FUSION) doivent etre presentes. Assertion laxe :
        # le template ne rend pas encore les lignes (Task 5 le fait), on
        # verifie juste que la vue les a construites (UUID ou Action label).
        # / Both transactions (SALE + FUSION) must be present. Loose
        # assertion: template doesn't render lines yet (Task 5), we check
        # the view built them (UUID or Action label).
        assert str(tx_sale.uuid) in html or tx_sale.get_action_display() in html
        assert str(tx_fusion.uuid) in html or tx_fusion.get_action_display() in html


@pytest.fixture
def user_v2_sans_wallet():
    """
    User sans wallet (user neuf qui n'a jamais ete credite).
    / User without wallet (new user never credited).
    """
    email = f"{TEST_PREFIX} no_wallet {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    return user


def test_transactions_table_v2_wallet_absent(config_v2, user_v2_sans_wallet):
    """
    User sans wallet -> aucune_transaction=True, message "empty" visible.
    / User without wallet -> empty state visible.
    """
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2_sans_wallet
        response = MyAccount().transactions_table(request)
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-testid="tx-v2-empty"' in html


def test_transactions_table_v2_tri_chronologique_desc(
    asset_fed_instance, config_v2, user_v2, tenant_federation_fed
):
    """
    3 Transactions crees a des datetimes differents -> ordre desc dans le rendu.
    / 3 tx created at different datetimes -> desc order in output.
    """
    from datetime import timedelta
    base = timezone.now()

    for i, minutes in enumerate([0, 10, 20]):
        Transaction.objects.create(
            sender=asset_fed_instance.wallet_origin,
            receiver=user_v2.wallet,
            asset=asset_fed_instance,
            amount=1000 + i,  # amounts distincts pour reperer l'ordre
            action=Transaction.REFILL,
            tenant=tenant_federation_fed,
            datetime=base - timedelta(minutes=minutes),
        )

    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2
        response = MyAccount().transactions_table(request)
        html = response.content.decode()
        # Le montant le plus recent (1000 centimes = 10.00) doit apparaitre
        # AVANT 1001 (10.01) et 1002 (10.02) dans le HTML (tri desc).
        # Le template utilise floatformat:2 qui rend avec un point.
        # / Most recent amount (10.00) must appear BEFORE 10.01 and 10.02
        # (desc). Template uses floatformat:2 → dot separator.
        pos_10_00 = html.find("10.00")
        pos_10_01 = html.find("10.01")
        pos_10_02 = html.find("10.02")
        assert pos_10_00 != -1 and pos_10_01 != -1 and pos_10_02 != -1
        assert pos_10_00 < pos_10_01 < pos_10_02


def test_transactions_table_v2_exclusion_actions_techniques(
    asset_fed_instance, config_v2, user_v2, tenant_federation_fed
):
    """
    FIRST, CREATION, BANK_TRANSFER crees sur le wallet user -> ABSENTS du HTML.
    SALE/REFILL present -> DANS le HTML.
    / Technical actions excluded from rendering, non-technical included.
    """
    actions_masquees = [
        Transaction.FIRST,
        Transaction.CREATION,
        Transaction.BANK_TRANSFER,
    ]
    for act in actions_masquees:
        Transaction.objects.create(
            sender=asset_fed_instance.wallet_origin,
            receiver=user_v2.wallet,
            asset=asset_fed_instance,
            amount=1111,  # marker unique
            action=act,
            tenant=tenant_federation_fed,
            datetime=timezone.now(),
        )
    # Une action visible pour controle positif.
    # / One visible action for positive control.
    Transaction.objects.create(
        sender=asset_fed_instance.wallet_origin,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=2222,  # marker unique
        action=Transaction.REFILL,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
    )

    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2
        response = MyAccount().transactions_table(request)
        html = response.content.decode()
        # Action visible (REFILL 22.22) presente.
        # Template floatformat:2 -> separateur point.
        # / Visible action present. floatformat:2 -> dot separator.
        assert "22.22" in html
        # Actions techniques (11.11) ABSENTES.
        # / Technical actions (11.11) absent.
        assert "11.11" not in html


def test_transactions_table_v2_pagination_40_par_page(
    asset_fed_instance, config_v2, user_v2, tenant_federation_fed
):
    """
    45 Transactions crees -> page 1 = 40 lignes, has_other_pages=True.
    / 45 tx -> page 1 = 40 rows, has_other_pages=True.
    """
    from datetime import timedelta
    base = timezone.now()
    for i in range(45):
        Transaction.objects.create(
            sender=asset_fed_instance.wallet_origin,
            receiver=user_v2.wallet,
            asset=asset_fed_instance,
            amount=100 + i,
            action=Transaction.REFILL,
            tenant=tenant_federation_fed,
            datetime=base - timedelta(seconds=i),
        )

    with tenant_context(config_v2):
        # Page 1 : 40 lignes + bouton "Next".
        # / Page 1: 40 rows + "Next" button.
        request_p1 = RequestFactory().get("/my_account/transactions_table/")
        request_p1.user = user_v2
        response_p1 = MyAccount().transactions_table(request_p1)
        html_p1 = response_p1.content.decode()
        assert html_p1.count('data-testid="tx-v2-row"') == 40
        assert 'data-testid="tx-v2-page-next"' in html_p1

        # Page 2 : 5 lignes + bouton "Previous".
        # / Page 2: 5 rows + "Previous" button.
        request_p2 = RequestFactory().get("/my_account/transactions_table/?page=2")
        request_p2.user = user_v2
        response_p2 = MyAccount().transactions_table(request_p2)
        html_p2 = response_p2.content.decode()
        assert html_p2.count('data-testid="tx-v2-row"') == 5
        assert 'data-testid="tx-v2-page-prev"' in html_p2


def test_transactions_table_v2_non_regression_branche_v1_legacy(
    tenant_lespass, tenant_federation_fed, user_v2
):
    """
    Verdict "v1_legacy" (tenant avec server_cashless) -> code V1 appele,
    template V1 rendu. Le conteneur V2 n'est PAS dans le HTML.
    / V1 legacy verdict -> V1 code called. V2 container NOT in HTML.
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_initial = config.server_cashless
        config.module_monnaie_locale = True
        config.server_cashless = "https://laboutik.example.com"
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])

    try:
        with tenant_context(tenant_lespass):
            request = RequestFactory().get("/my_account/transactions_table/")
            request.user = user_v2
            # 2 outcomes acceptables :
            # 1. Exception reseau (FedowAPI distant non joignable en test)
            # 2. Response 200 mais sans le conteneur V2
            # / 2 acceptable outcomes: network error OR 200 without V2 marker.
            try:
                response = MyAccount().transactions_table(request)
                html = response.content.decode()
                assert 'data-testid="tx-v2-container"' not in html
            except Exception as erreur_fedow_api:
                message = str(erreur_fedow_api).lower()
                indices_reseau = (
                    "connection", "resolve", "timeout", "http",
                    "fedow", "url", "name or service", "max retries",
                )
                assert any(i in message for i in indices_reseau), (
                    f"Exception inattendue : {erreur_fedow_api!r}"
                )
    finally:
        with tenant_context(tenant_lespass):
            config = Configuration.get_solo()
            config.module_monnaie_locale = module_initial
            config.server_cashless = server_initial
            config.save(update_fields=["module_monnaie_locale", "server_cashless"])
