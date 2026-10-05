"""
tests/pytest/test_remboursement_especes_trace_comptable.py
La trace comptable d'un remboursement en especes, monnaie locale ET federee.
/ The accounting trail of a cash refund, local AND federated currency.

LOCALISATION : tests/pytest/test_remboursement_especes_trace_comptable.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Vider une carte a la caisse rend de l'argent liquide a un adherent. L'operation
doit laisser une trace comptable complete, sinon la caisse ne tombe plus juste
et le solde du lieu derive sans qu'on sache pourquoi.

`WalletService.rembourser_en_especes` produit une `Transaction` REFUND par monnaie
remboursee (le mouvement de portefeuille), et aucune `LigneArticle`. La caisse
ecrit ensuite la vente VIDAGE_CARTE (D12) : un reglement par monnaie rendue (le
lieu encaisse la monnaie du reseau), puis un reglement especes NEGATIF du total
rendu (la sortie du tiroir).

Ce fichier couvre le cas ou les DEUX monnaies sont presentes en meme temps : le
total rendu est verifie comme une vraie somme (1000 + 500), et non une recopie.

/ Emptying a card at the register hands real cash to a member. The service writes
one REFUND transaction per currency and no line; the register writes the
VIDAGE_CARTE sale (D12). This file covers BOTH currencies at once.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_remboursement_especes_trace_comptable.py -v
"""

import uuid as uuid_module
from unittest.mock import patch

import pytest
from django.db import transaction as db_transaction
from django.test import override_settings
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import LigneArticle, PaymentMethod
from BaseBillet.models_vente import Vente
from Customers.models import Client as TenantClient
from QrcodeCashless.models import CarteCashless, Detail
from fedow_connect.models import FedowConfig
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import WalletService

# Prefixe des objets de ce fichier. La base de dev est partagee et sans
# rollback : tout ce qui est cree ici doit etre reconnaissable et nettoye.
# / Prefix for this file's objects. Shared dev DB with no rollback.
PREFIXE_DE_TEST = '[rbt_trace]'

# Les tag_id de CarteCashless font 8 caracteres au maximum (PIEGES 9.31).
# / CarteCashless tag_id is 8 characters max.
TAG_CARTE_CLIENT = 'RBT00001'
TAG_CARTE_CAISSIER = 'RBT00002'

# Montants du scenario mixte, volontairement differents l'un de l'autre pour
# qu'une confusion entre les deux soit visible dans les assertions.
# / Deliberately different amounts so any mix-up shows in the assertions.
SOLDE_MONNAIE_LOCALE = 1000
SOLDE_MONNAIE_FEDEREE = 500
TOTAL_ATTENDU = SOLDE_MONNAIE_LOCALE + SOLDE_MONNAIE_FEDEREE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tenant():
    """Le tenant de developpement, cible explicitement.
    / The development tenant, targeted explicitly."""
    return TenantClient.objects.get(schema_name="lespass")


@pytest.fixture(scope="module")
def wallet_du_lieu(tenant):
    """Le portefeuille du lieu, qui recoit les REFUND.
    / The venue's wallet, receiving the REFUND transactions."""
    return Wallet.objects.create(name=f'{PREFIXE_DE_TEST} Lieu')


@pytest.fixture(scope="module")
def asset_monnaie_locale(tenant, wallet_du_lieu):
    """La monnaie locale du lieu, remboursable en especes.
    / The venue's local currency, refundable in cash."""
    asset, _cree = Asset.objects.get_or_create(
        name=f'{PREFIXE_DE_TEST} Monnaie locale',
        category=Asset.TLF,
        defaults={
            "currency_code": "EUR",
            "wallet_origin": wallet_du_lieu,
            "tenant_origin": tenant,
        },
    )
    return asset


@pytest.fixture(scope="module")
def asset_monnaie_federee(tenant, wallet_du_lieu):
    """La monnaie federee du reseau, cote moteur local.

    `Asset.save()` interdit de creer un asset FED local
    (`AssetFedLocalInterdit`) : aujourd'hui cette monnaie vient du Fedow
    distant. Ce fichier couvre le comportement du remboursement pour le jour ou
    elle sera locale, il leve donc la garde le temps de fabriquer l'asset — et
    seulement pour ca : les remboursements testes plus bas s'executent avec la
    garde active, comme en production.
    / Asset.save() forbids creating a local FED asset. This file covers the
    refund's behaviour for the post-migration world, so it lifts the guard just
    long enough to build the asset. The refunds themselves run with the guard on.

    Un seul asset FED peut exister dans tout le systeme (contrainte
    `unique_fed_asset`) : on reutilise celui qui serait deja la.
    / Only one FED asset may exist system-wide: reuse an existing one.
    """
    asset_existant = Asset.objects.filter(category=Asset.FED).first()
    if asset_existant is not None:
        return asset_existant

    with override_settings(FEDOW_AUTORISER_ASSET_FED_LOCAL=True):
        return Asset.objects.create(
            name=f'{PREFIXE_DE_TEST} Monnaie federee',
            category=Asset.FED,
            currency_code='EUR',
            wallet_origin=wallet_du_lieu,
            tenant_origin=tenant,
        )


@pytest.fixture
def carte_client_mixte(request, tenant, asset_monnaie_locale, asset_monnaie_federee):
    """Une carte anonyme portant les DEUX monnaies a la fois.

    C'est la situation courante d'un festivalier : il a recharge en ligne (du
    federe) et au bar (de la monnaie locale).
    / The common festival-goer case: topped up online (federated) and at the bar
    (local currency).
    """
    with schema_context('lespass'):
        detail, _cree = Detail.objects.get_or_create(
            base_url=f'{PREFIXE_DE_TEST}_DETAIL',
            origine=tenant,
            defaults={"generation": 0},
        )
        wallet_du_client = Wallet.objects.create(
            name=f'{PREFIXE_DE_TEST} Wallet client',
        )
        carte = CarteCashless.objects.create(
            tag_id=TAG_CARTE_CLIENT,
            number=TAG_CARTE_CLIENT,
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_du_client,
        )
        # `crediter()` pose un select_for_update : il lui faut une transaction.
        # / crediter() takes a select_for_update: it needs a transaction.
        with db_transaction.atomic():
            WalletService.crediter(
                wallet=wallet_du_client,
                asset=asset_monnaie_locale,
                montant_en_centimes=SOLDE_MONNAIE_LOCALE,
            )
            WalletService.crediter(
                wallet=wallet_du_client,
                asset=asset_monnaie_federee,
                montant_en_centimes=SOLDE_MONNAIE_FEDEREE,
            )

        yield carte

        # Test marque django_db : le rollback de fin de test efface tout. Un nettoyage a
        # la main echouerait : la vente du vidage, scellee, protege la carte et le PV.
        # / django_db test: the end-of-test rollback erases everything. A manual cleanup
        # would fail: the sealed card-emptying sale protects the card and the POS.
        if request.node.get_closest_marker("django_db") is not None:
            return
        # Ordre impose par les FK PROTECT : lignes et transactions avant la
        # carte, tokens avant le wallet.
        # / Order imposed by PROTECT FKs.
        LigneArticle.objects.filter(carte=carte).delete()
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet=wallet_du_client).delete()
        carte.delete()
        wallet_du_client.delete()


@pytest.fixture
def carte_du_caissier(request, tenant):
    """La carte primaire qui autorise l'operation au point de vente.
    / The primary card authorizing the operation at the point of sale."""
    with schema_context('lespass'):
        detail, _cree = Detail.objects.get_or_create(
            base_url=f'{PREFIXE_DE_TEST}_DETAIL',
            origine=tenant,
            defaults={"generation": 0},
        )
        carte, _creee = CarteCashless.objects.get_or_create(
            tag_id=TAG_CARTE_CAISSIER,
            defaults={
                "number": TAG_CARTE_CAISSIER,
                "uuid": uuid_module.uuid4(),
                "detail": detail,
            },
        )

        yield carte

        # Test marque django_db : le rollback de fin de test efface tout. Un nettoyage a
        # la main echouerait : la vente du vidage, scellee, protege la carte et le PV.
        # / django_db test: the end-of-test rollback erases everything. A manual cleanup
        # would fail: the sealed card-emptying sale protects the card and the POS.
        if request.node.get_closest_marker("django_db") is not None:
            return
        Transaction.objects.filter(primary_card=carte).delete()
        carte.delete()


@pytest.fixture
def point_de_vente(request, carte_du_caissier):
    """Un point de vente qui accepte la carte du caissier et le produit de
    remboursement.
    / A point of sale accepting the cashier's card and the refund product."""
    from BaseBillet.services_refund import get_or_create_product_remboursement
    from laboutik.models import CartePrimaire, PointDeVente

    with schema_context('lespass'):
        pv, _cree = PointDeVente.objects.get_or_create(
            name=f'{PREFIXE_DE_TEST} PV',
            # `hidden=True` : un PV de test visible se glisserait en tete de la
            # liste des autres tests et les ferait echouer (PIEGES 9.41).
            # / hidden=True: a visible test PV would slip to the top of other
            # tests' lists and break them.
            defaults={"comportement": "V", "hidden": True, "poid_liste": 9999},
        )
        carte_primaire, _creee = CartePrimaire.objects.get_or_create(
            carte=carte_du_caissier,
            defaults={"edit_mode": False},
        )
        carte_primaire.points_de_vente.add(pv)
        produit_de_remboursement = get_or_create_product_remboursement()
        pv.products.add(produit_de_remboursement)

        yield pv

        # Test marque django_db : le rollback de fin de test efface tout. Un nettoyage a
        # la main echouerait : la vente du vidage, scellee, protege la carte et le PV.
        # / django_db test: the end-of-test rollback erases everything. A manual cleanup
        # would fail: the sealed card-emptying sale protects the card and the POS.
        if request.node.get_closest_marker("django_db") is not None:
            return
        pv.products.remove(produit_de_remboursement)
        carte_primaire.points_de_vente.remove(pv)
        carte_primaire.delete()
        pv.delete()


@pytest.fixture(scope="module", autouse=True)
def _nettoyage_en_fin_de_module(tenant):
    """Supprime ce que les fixtures de portee module ont laisse.
    / Deletes what the module-scoped fixtures left behind.

    Ordre impose par les FK PROTECT : Transactions et Tokens avant les Assets,
    Assets avant les Wallets. Les Products « Recharge X » nes du signal
    post_save d'`Asset` partent avec eux, sinon leur contrainte unique
    (categorie, nom) ferait echouer le run suivant (PIEGES 9.96).
    / Order imposed by PROTECT FKs. The "Recharge X" Products born from the
    Asset post_save signal go too, or their unique constraint would break the
    next run.
    """
    yield

    from BaseBillet.models import Price, Product

    with tenant_context(tenant):
        assets_de_test = Asset.objects.filter(name__startswith=PREFIXE_DE_TEST)
        wallets_de_test = Wallet.objects.filter(name__startswith=PREFIXE_DE_TEST)

        Transaction.objects.filter(asset__in=assets_de_test).delete()
        Token.objects.filter(asset__in=assets_de_test).delete()
        Detail.objects.filter(base_url=f'{PREFIXE_DE_TEST}_DETAIL').delete()

        for asset in assets_de_test:
            Price.objects.filter(product__name=f'Recharge {asset.name}').delete()
            Product.objects.filter(name=f'Recharge {asset.name}').delete()

        assets_de_test.delete()
        wallets_de_test.delete()


def _connexion_caisse():
    """Un client HTTP connecte comme administrateur du tenant.

    La vue de vidage exige `HasLaBoutikTerminalAccess`, qui retombe sur
    `HasLaBoutikAccess` : une session dont l'utilisateur administre le tenant
    suffit. Le test fabrique donc son propre administrateur plutot que de
    dependre d'un compte seede, qui varie selon l'etat de la base.
    / The view requires HasLaBoutikTerminalAccess, falling back to
    HasLaBoutikAccess: a session whose user administers the tenant is enough.
    The test builds its own admin rather than depending on a seeded account.
    """
    from django.test import Client as DjangoClient

    from AuthBillet.models import TibilletUser

    tenant = TenantClient.objects.get(schema_name="lespass")
    adresse = f'rbt_caisse_{uuid_module.uuid4().hex[:8]}@example.com'

    with tenant_context(tenant):
        administrateur = TibilletUser.objects.create(
            email=adresse,
            username=adresse,
            espece=TibilletUser.TYPE_HUM,
            is_active=True,
            email_valid=True,
        )
        administrateur.client_admin.add(tenant)
        administrateur.save()

    client = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")
    client.force_login(administrateur)
    return client, administrateur


# ---------------------------------------------------------------------------
# A. Le service : les deux monnaies remboursees ensemble
# ---------------------------------------------------------------------------


def test_rembourser_les_deux_monnaies_rend_la_somme_exacte(
    tenant, wallet_du_lieu, carte_client_mixte,
):
    """La sortie de caisse vaut la SOMME des deux monnaies, pas l'une des deux.

    C'est le calcul que les tests par monnaie unique ne peuvent pas verifier :
    avec une seule monnaie, `-(1000 + 0)` ne se distingue pas d'une recopie.
    Ici, rendre 1000 de monnaie locale et 500 de federee doit sortir 1500 du
    tiroir — ni 1000, ni 500.
    / The sum single-currency tests cannot verify: with one currency,
    -(1000 + 0) is indistinguishable from a copy.
    """
    with tenant_context(tenant):
        resultat = WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
            ip="127.0.0.1",
        )

        assert resultat["total_tlf_centimes"] == SOLDE_MONNAIE_LOCALE
        assert resultat["total_fed_centimes"] == SOLDE_MONNAIE_FEDEREE
        assert resultat["total_centimes"] == TOTAL_ATTENDU

        # Le service n'écrit aucune ligne : la caisse écrit la vente VIDAGE_CARTE
        # (D12, test_caisse_vider_carte_deux_fedow.py).
        # / The service writes no line: the register writes the VIDAGE_CARTE sale.
        assert not LigneArticle.objects.filter(carte=carte_client_mixte).exists()


def test_chaque_monnaie_rendue_laisse_sa_transaction(
    tenant, wallet_du_lieu, carte_client_mixte,
):
    """Deux monnaies rendues, deux mouvements de portefeuille, et les comptes
    tombent juste.

    Les `Transaction` tracent le portefeuille ; leur total vaut l'argent rendu
    annoncé par le service (c'est lui que la caisse écrit en règlement espèces).
    / Transactions track the wallet; their total equals the money given back.
    """
    with tenant_context(tenant):
        resultat = WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
        )

        transactions = Transaction.objects.filter(
            card=carte_client_mixte,
            action=Transaction.REFUND,
        )
        assert transactions.count() == 2
        assert len(resultat["transactions"]) == 2

        total_des_transactions = 0
        for transaction_de_remboursement in transactions:
            total_des_transactions += transaction_de_remboursement.amount
        assert total_des_transactions == resultat["total_centimes"] == TOTAL_ATTENDU


def test_les_soldes_de_la_carte_retombent_a_zero(
    tenant, wallet_du_lieu, carte_client_mixte,
    asset_monnaie_locale, asset_monnaie_federee,
):
    """Apres remboursement, la carte ne porte plus rien.

    L'argent a ete rendu en billets : le laisser sur la carte le rendrait deux
    fois.
    / The money was handed over in cash: leaving it on the card would give it
    away twice.
    """
    with tenant_context(tenant):
        WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
        )

        wallet_du_client = carte_client_mixte.wallet_ephemere
        assert WalletService.obtenir_solde(wallet_du_client, asset_monnaie_locale) == 0
        assert WalletService.obtenir_solde(wallet_du_client, asset_monnaie_federee) == 0


# ---------------------------------------------------------------------------
# B. Le flux complet depuis la caisse
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vider_une_carte_depuis_la_caisse_ecrit_la_vente_du_vidage(
    tenant, carte_client_mixte, carte_du_caissier, point_de_vente,
):
    """Le parcours reel : un caissier vide une carte, la trace est complete.

    La trace est la vente VIDAGE_CARTE (D12) : un règlement par monnaie rendue
    (monnaie locale +1000, monnaie fédérée +500), puis un règlement espèces −1500
    (ce qui sort du tiroir). Aucune ligne « Refund ».
    / The trail is the VIDAGE_CARTE sale: one payment per currency, then cash −1500.

    Ce test remplace la verification manuelle « vider une carte au point de
    vente » : il passe par la vraie route HTTP, avec la carte primaire, le
    controle d'acces au point de vente, et la garde anti-FED-local active — donc
    dans les conditions de production.
    / This replaces the manual "empty a card at the POS" check: it goes through
    the real HTTP route, with the primary card, the POS access control, and the
    local-FED guard ON — production conditions.
    """
    client, _administrateur = _connexion_caisse()

    # Lieu non relie a l'ancien Fedow (simule) : vidage local seul, aucun appel reseau.
    # / Venue not linked to the old Fedow (faked): local emptying only, no network call.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        response = client.post(
            "/laboutik/paiement/vider_carte/",
            data={
                "tag_id": carte_client_mixte.tag_id,
                "tag_id_cm": carte_du_caissier.tag_id,
                "uuid_pv": str(point_de_vente.uuid),
                "vider_carte": "false",
            },
        )

    assert response.status_code == 200, response.content.decode()[:500]

    with tenant_context(tenant):
        vente_du_vidage = Vente.objects.get(
            nature=Vente.Nature.VIDAGE_CARTE, carte=carte_client_mixte
        )
        montants_par_moyen = {}
        for reglement in vente_du_vidage.reglements.all():
            montants_par_moyen[reglement.moyen] = reglement.montant
        assert montants_par_moyen == {
            PaymentMethod.LOCAL_EURO: SOLDE_MONNAIE_LOCALE,
            PaymentMethod.STRIPE_FED: SOLDE_MONNAIE_FEDEREE,
            PaymentMethod.CASH: -TOTAL_ATTENDU,
        }
        assert not LigneArticle.objects.filter(
            carte=carte_client_mixte, vente__isnull=True
        ).exists()

        # La carte du caissier est tracee sur chaque mouvement : c'est ce qui
        # permet de savoir QUI a rendu l'argent.
        # / The cashier's card is recorded on every movement: it tells WHO
        # handed the money over.
        transactions = Transaction.objects.filter(
            card=carte_client_mixte,
            action=Transaction.REFUND,
        )
        assert transactions.count() == 2
        for transaction_de_remboursement in transactions:
            assert transaction_de_remboursement.primary_card_id == carte_du_caissier.pk


# ---------------------------------------------------------------------------
# C. La remontee dans les rapports de caisse : lue sur la vente VIDAGE_CARTE par le
# rapport unique (tests/pytest/test_rapport_unique.py, « cartes vidées »).
# / C. Report: read from the VIDAGE_CARTE sale by the single report.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# D. Non-regression de la garde
# ---------------------------------------------------------------------------


def test_la_garde_anti_fed_local_n_empeche_pas_de_vider_une_carte(
    tenant, wallet_du_lieu, carte_client_mixte,
):
    """La garde bloque la creation d'un asset federe, jamais son remboursement.

    C'est la verification de non-regression du chantier : `Asset.save()` refuse
    desormais la categorie FED, et `rembourser_en_especes` lit precisement des
    tokens de cette categorie. Une garde mal placee arreterait le vidage de
    carte a la caisse.
    / The guard blocks creating a federated asset, never refunding it. A guard
    placed wrong would stop card emptying at the register.
    """
    from django.conf import settings

    # On verifie d'abord que la garde est bien active, sinon le test ne prouve
    # rien : il tournerait dans le meme etat que les fixtures.
    # / First check the guard is actually on, or the test proves nothing.
    assert settings.FEDOW_AUTORISER_ASSET_FED_LOCAL is False

    with tenant_context(tenant):
        resultat = WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
        )

    assert resultat["total_centimes"] == TOTAL_ATTENDU
    assert resultat["total_fed_centimes"] == SOLDE_MONNAIE_FEDEREE
