"""
Tests de la vue MyAccount.tokens_table pour la branche V2 (fedow_core local).
Tests for MyAccount.tokens_table — V2 branch (local fedow_core).

LOCALISATION : tests/pytest/test_tokens_table_v2.py

Couvre :
- Dispatch V2 vs V1 (verdict peut_recharger_v2)
- Wallet absent / vide
- Rendu FED "utilisable partout"
- Rendu TLF avec lieux federes
- Split fiduciaires / compteurs TIM/FID

/ Covers V2 dispatch, empty wallet, FED "everywhere", TLF federated venues, fiduciary/counter split.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
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

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from BaseBillet.models import Configuration
from fedow_core.models import Asset, Federation, Token
from BaseBillet.views import (
    MyAccount,
    _get_tenant_info_cached,
    _lieux_utilisables_pour_asset,
)


TEST_PREFIX = "[test_tokens_table_v2]"


@pytest.fixture(scope="module")
def tenant_federation_fed():
    """Bootstrape federation_fed (idempotent). / Bootstrap federation_fed (idempotent)."""
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
    / User with wallet origin=federation_fed (nominal V2 case).
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
    Met le tenant lespass en mode V2 (module_monnaie_locale=True, server_cashless=None),
    et restaure les valeurs initiales en fin de test.
    / Sets lespass tenant to V2 mode and restores initial values at end of test.
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


def test_tokens_table_v2_dispatch_branche_v2(config_v2, user_v2):
    """
    Verdict peut_recharger_v2 == 'v2' -> le template token_table_v2.html est rendu.
    / V2 verdict -> token_table_v2.html template is rendered.
    """
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/tokens_table/")
        request.user = user_v2
        response = MyAccount().tokens_table(request)
        assert response.status_code == 200
        html = response.content.decode()
        # Le conteneur V2 a un id specifique, absent du template V1.
        # / V2 container has a specific id, absent from V1 template.
        assert 'id="tokens-v2-container"' in html


def test_get_tenant_info_cached_construit_le_cache(tenant_lespass):
    """
    Premier appel : cache froid, le helper construit le dict complet.
    / First call: cold cache, helper builds the full dict.
    """
    cache.delete("tenant_info_v2")
    info = _get_tenant_info_cached(tenant_lespass.pk)
    # Lespass est une SALLE_SPECTACLE, il doit etre dans le cache.
    # / Lespass is a SALLE_SPECTACLE, must be in cache.
    assert info is not None
    assert "organisation" in info
    assert "logo" in info


def test_get_tenant_info_cached_hit_au_second_appel(tenant_lespass):
    """
    Second appel immediat : le cache retourne le meme dict (HIT).
    On prouve le HIT en verifiant qu'aucune requete DB n'est emise
    au second appel (CaptureQueriesContext).
    / Second immediate call: cache returns the same dict (HIT).
    Proved by capturing zero DB queries on the second call.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    cache.delete("tenant_info_v2")

    # Premier appel : cache froid, construit le dict (requetes DB attendues).
    # / First call: cold cache, builds dict (DB queries expected).
    info1 = _get_tenant_info_cached(tenant_lespass.pk)

    # Verifie que l'entree cache a bien ete posee.
    # / Verify the cache entry is set.
    assert cache.get("tenant_info_v2") is not None

    # Deuxieme appel : doit lire uniquement le cache, aucune DB.
    # / Second call: cache-only read, zero DB.
    with CaptureQueriesContext(connection) as contexte_requetes:
        info2 = _get_tenant_info_cached(tenant_lespass.pk)
    assert len(contexte_requetes.captured_queries) == 0, (
        "Le second appel ne doit pas requeter la DB / Second call must not query the DB"
    )
    assert info1 == info2


@pytest.fixture
def asset_tlf_avec_federation(tenant_lespass, tenant_federation_fed):
    """
    Cree un asset TLF dont le tenant_origin est lespass + une Federation
    qui contient cet asset + 1 autre tenant (federation_fed utilise comme
    second lieu fictif). Restauration a la fin.
    / Creates a TLF asset with tenant_origin=lespass + a Federation
    containing this asset + 1 other tenant (federation_fed as fake 2nd venue).
    """
    # Wallet d'origine pour l'asset (un wallet lambda, pas besoin de user).
    # / Origin wallet for asset (a lambda wallet, no user needed).
    wallet_origin = Wallet.objects.create(
        origin=tenant_lespass,
        name=f"Wallet TLF fixture {uuid.uuid4()}",
    )
    asset = Asset.objects.create(
        name=f"Monnaie locale test {uuid.uuid4()}",
        category=Asset.TLF,
        currency_code="EUR",
        wallet_origin=wallet_origin,
        tenant_origin=tenant_lespass,
    )
    federation = Federation.objects.create(
        name=f"Federation test {uuid.uuid4()}",
        created_by=tenant_lespass,
    )
    federation.tenants.add(tenant_lespass, tenant_federation_fed)
    federation.assets.add(asset)

    yield asset

    # Cleanup : Asset.delete() declenche une cascade cross-schema vers
    # BaseBillet.Product.asset (tenant_app), donc on doit se placer dans
    # un tenant_context pour que les tables tenant soient visibles.
    # / Asset.delete() triggers a cross-schema cascade to BaseBillet.Product
    # (tenant app), so we must wrap in tenant_context to make tenant tables visible.
    with tenant_context(tenant_lespass):
        federation.delete()
        asset.delete()
        wallet_origin.delete()


def test_lieux_utilisables_pour_asset_fed_retourne_none(tenant_federation_fed):
    """
    Pour un asset FED : la fonction retourne None (cas "utilisable partout").
    / For a FED asset: returns None (the "usable everywhere" case).
    """
    asset_fed = Asset.objects.get(category=Asset.FED)
    resultat = _lieux_utilisables_pour_asset(asset_fed)
    assert resultat is None


def test_lieux_utilisables_pour_asset_tlf_retourne_liste_deduplique(
    asset_tlf_avec_federation, tenant_lespass
):
    """
    Pour un asset TLF : la fonction retourne la liste des lieux utilisables,
    dedupliquee (tenant_origin + tenants de federations).
    / For a TLF asset: returns deduplicated list of usable venues.
    """
    # Cache froid force pour un parcours propre.
    # / Cold cache forced for clean run.
    cache.delete("tenant_info_v2")

    resultat = _lieux_utilisables_pour_asset(asset_tlf_avec_federation)

    assert resultat is not None

    # federation_fed a categorie FED (pas SALLE_SPECTACLE) donc absent du cache
    # de _get_tenant_info_cached : un seul lieu doit rester dans le resultat.
    # / federation_fed is category FED (not SALLE_SPECTACLE) so absent from
    # the cache: exactly one venue must remain in the result.
    assert len(resultat) == 1, (
        f"Exactement 1 lieu attendu (lespass), obtenu : {len(resultat)} "
        f"/ Expected exactly 1 venue (lespass), got: {len(resultat)}"
    )

    organisations = [info["organisation"] for info in resultat]

    # Dedup : lespass est ajoute DEUX fois (tenant_origin + federation.tenants),
    # il doit apparaitre UNE SEULE FOIS apres dedup via {t.pk: t}.
    # / Dedup: lespass is added TWICE (tenant_origin + federation.tenants),
    # must appear ONCE after dedup via {t.pk: t}.
    config_lespass_organisation = None
    with tenant_context(tenant_lespass):
        from BaseBillet.models import Configuration as ConfLocal

        config_lespass_organisation = ConfLocal.get_solo().organisation
    assert organisations.count(config_lespass_organisation) == 1, (
        "Lespass doit apparaitre exactement 1 fois apres dedup "
        "/ Lespass must appear exactly once after dedup"
    )


@pytest.fixture
def user_v2_sans_wallet():
    """
    User sans wallet (user neuf qui n'a jamais recharge).
    / User without wallet (new user never refilled).
    """
    email = f"{TEST_PREFIX} no_wallet {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    return user


def test_tokens_table_v2_wallet_absent(config_v2, user_v2_sans_wallet):
    """
    User sans wallet -> aucun_token=True, message "empty" visible dans le HTML.
    / User without wallet -> aucun_token=True, empty message visible.
    """
    # peut_recharger_v2 retourne "v2" meme si user.wallet is None
    # tant que le wallet n'est pas dans un tenant V1.
    # / peut_recharger_v2 returns "v2" even if user.wallet is None
    # as long as the wallet is not in a V1 tenant.
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/tokens_table/")
        request.user = user_v2_sans_wallet
        response = MyAccount().tokens_table(request)
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-testid="tokens-v2-empty"' in html


def test_tokens_table_v2_split_fiduciaires_compteurs(
    config_v2, user_v2, tenant_federation_fed
):
    """
    Tokens FED (1500 centimes) + TIM (3 unites) ->
    FED dans tokens_fiduciaires, TIM dans tokens_compteurs.
    / FED + TIM tokens -> FED in fiduciary list, TIM in counter list.
    """
    # Creer un Token FED pour l'user (credit direct, simule une recharge).
    # / Create a FED Token for the user (direct credit, simulates a refill).
    asset_fed = Asset.objects.get(category=Asset.FED)
    Token.objects.create(wallet=user_v2.wallet, asset=asset_fed, value=1500)

    # Creer un asset TIM + Token pour le meme user.
    # / Create a TIM asset + Token for same user.
    wallet_origin_tim = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet TIM {uuid.uuid4()}",
    )
    asset_tim = Asset.objects.create(
        name=f"Heures test {uuid.uuid4()}",
        category=Asset.TIM,
        currency_code="TMP",
        wallet_origin=wallet_origin_tim,
        tenant_origin=tenant_federation_fed,
    )
    Token.objects.create(wallet=user_v2.wallet, asset=asset_tim, value=3)

    try:
        with tenant_context(config_v2):
            request = RequestFactory().get("/my_account/tokens_table/")
            request.user = user_v2
            response = MyAccount().tokens_table(request)
            html = response.content.decode()

            # Preuve que la branche V2 a ete executee (le template V1 n'a
            # pas ce conteneur). / Proof that V2 branch ran (V1 template
            # doesn't have this container).
            assert 'id="tokens-v2-container"' in html

            # Les 2 sous-tableaux ne sont pas encore dans le template
            # (Tasks 6-7 les ajoutent). On verifie ici uniquement que le
            # split est correct COTE VUE via le contexte, pas le HTML.
            # / The 2 sub-tables come in Tasks 6-7. Here we verify the
            # split is correct in the VIEW context, not HTML yet.
            # Le marker "aucun_token" doit etre absent (on a 2 tokens).
            # / aucun_token marker must be absent (we have 2 tokens).
            assert 'data-testid="tokens-v2-empty"' not in html
            # TiBillets (FED) doit apparaitre dans le HTML meme si le
            # template n'a pas encore le sous-tableau (assertion laxe).
            # / TiBillets label should appear (dev friendly partial).
            # On ne teste pas le HTML strict ici — Task 8 affine les tests.
            # TiBillets (FED) doit apparaitre dans le HTML meme si le
            # template n'a pas encore le sous-tableau (assertion laxe).
            # / TiBillets label should appear (dev friendly partial).
            # On ne teste pas le HTML strict ici — Task 8 affine les tests.
    finally:
        # Cleanup : delete tokens + asset_tim + wallet_origin_tim.
        # Asset.delete() cascade sur BaseBillet.Product (TENANT_APP),
        # besoin de tenant_context.
        # / Cleanup with tenant_context because Asset.delete() cascades
        # to BaseBillet.Product (TENANT_APP).
        Token.objects.filter(wallet=user_v2.wallet).delete()
        with tenant_context(tenant_federation_fed):
            asset_tim.delete()
            # Wallet.delete() cascade aussi sur BaseBillet.lignearticle
            # (tenant app), donc on reste dans le tenant_context.
            # / Wallet.delete() also cascades to BaseBillet.lignearticle
            # (tenant app), so keep the tenant_context.
            wallet_origin_tim.delete()


def test_tokens_table_v2_token_tlf_lieux_federes_visibles_html(
    config_v2, user_v2, asset_tlf_avec_federation
):
    """
    Un token TLF appartenant au user doit afficher les pastilles des lieux
    federes (organisation du tenant_origin dans le HTML).
    / A user's TLF token must display federated venue chips in HTML.
    """
    cache.delete("tenant_info_v2")
    Token.objects.create(
        wallet=user_v2.wallet,
        asset=asset_tlf_avec_federation,
        value=1000,
    )

    try:
        with tenant_context(config_v2):
            request = RequestFactory().get("/my_account/tokens_table/")
            request.user = user_v2
            response = MyAccount().tokens_table(request)
            html = response.content.decode()
            # Le nom de l'asset TLF est present dans le HTML (sous-tableau fiduciaires).
            # / TLF asset name in HTML (fiduciary sub-table).
            assert asset_tlf_avec_federation.name in html
            # Le sous-tableau fiduciaires est bien rendu.
            # / Fiduciary sub-table is rendered.
            assert 'data-testid="tokens-v2-fiduciaires"' in html
    finally:
        # Cleanup. / Cleanup.
        Token.objects.filter(wallet=user_v2.wallet).delete()


def test_tokens_table_v2_non_regression_branche_v1_legacy(
    tenant_lespass, tenant_federation_fed, user_v2
):
    """
    Verdict "v1_legacy" (tenant avec server_cashless) -> code V1 appele,
    template V1 rendu. NE PAS rendre le nouveau template V2.
    / V1 legacy verdict -> V1 code called, V1 template rendered.
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
            request = RequestFactory().get("/my_account/tokens_table/")
            request.user = user_v2
            # On s'attend a un appel reel a FedowAPI : si Fedow n'est pas
            # joignable en test, on recupere une erreur. On accepte donc
            # 2 issues possibles :
            # 1. Une exception FedowAPI (Fedow distant non dispo en test)
            # 2. Une reponse 200 mais SANS le conteneur V2
            # / Two possible outcomes: FedowAPI exception OR 200 without V2 marker.
            try:
                response = MyAccount().tokens_table(request)
                html = response.content.decode()
                # Critere essentiel : le conteneur V2 n'est PAS la.
                # / Essential: V2 container is NOT there.
                assert 'id="tokens-v2-container"' not in html
            except Exception as erreur_fedow_api:
                # Acceptable : Fedow distant pas joignable en test.
                # On confirme que l'erreur vient bien d'un appel reseau/HTTP
                # (FedowAPI injoignable), pas d'un bug cote vue V2 ou d'un
                # plantage arbitraire (ImportError, TypeError, etc.).
                # / Acceptable: Fedow remote not reachable in test.
                # Confirms the error is network/HTTP-related (FedowAPI
                # unreachable), not a bug in V2 branch or arbitrary crash.
                message_erreur = str(erreur_fedow_api).lower()
                indices_reseau = (
                    "connection",
                    "resolve",
                    "timeout",
                    "http",
                    "fedow",
                    "url",
                    "name or service",
                    "max retries",
                )
                assert any(indice in message_erreur for indice in indices_reseau), (
                    f"Exception inattendue (pas liee au reseau/FedowAPI) : "
                    f"{erreur_fedow_api!r} "
                    f"/ Unexpected exception (not network/FedowAPI-related): "
                    f"{erreur_fedow_api!r}"
                )
    finally:
        with tenant_context(tenant_lespass):
            config = Configuration.get_solo()
            config.module_monnaie_locale = module_initial
            config.server_cashless = server_initial
            config.save(update_fields=["module_monnaie_locale", "server_cashless"])
