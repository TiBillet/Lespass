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

`WalletService.rembourser_en_especes` produit :

- une `Transaction` REFUND par monnaie remboursee (le mouvement de portefeuille) ;
- une `LigneArticle` POSITIVE en STRIPE_FED si un solde federe est rendu — c'est
  l'encaissement, par le lieu, de monnaie qui appartenait au reseau ;
- une `LigneArticle` NEGATIVE en CASH du total rendu — c'est la sortie du tiroir.

Ce fichier couvre ce que les tests voisins laissent de cote : le cas ou les DEUX
monnaies sont presentes en meme temps, et le detail des champs de tracabilite.
`test_card_refund_service.py` et `test_pos_vider_carte.py` ne testent chaque
monnaie que SEULE : la ligne CASH y vaut `-(1000 + 0)` ou `-(0 + 500)`, ce qui ne
distingue pas une somme d'une simple recopie du plus grand des deux.

/ Emptying a card at the register hands real cash to a member: the accounting
trail must be complete. This file covers what the neighbouring tests leave out:
BOTH currencies at once (so the CASH line is verified as a true sum), and the
traceability fields.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_remboursement_especes_trace_comptable.py -v
"""

import uuid as uuid_module

import pytest
from django.db import transaction as db_transaction
from django.test import override_settings
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
from Customers.models import Client as TenantClient
from QrcodeCashless.models import CarteCashless, Detail
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
def carte_client_mixte(tenant, asset_monnaie_locale, asset_monnaie_federee):
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

        # Ordre impose par les FK PROTECT : lignes et transactions avant la
        # carte, tokens avant le wallet.
        # / Order imposed by PROTECT FKs.
        LigneArticle.objects.filter(carte=carte).delete()
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet=wallet_du_client).delete()
        carte.delete()
        wallet_du_client.delete()


@pytest.fixture
def carte_du_caissier(tenant):
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

        Transaction.objects.filter(primary_card=carte).delete()
        carte.delete()


@pytest.fixture
def point_de_vente(carte_du_caissier):
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

        ligne_de_sortie_de_caisse = LigneArticle.objects.get(
            carte=carte_client_mixte,
            payment_method=PaymentMethod.CASH,
        )
        assert ligne_de_sortie_de_caisse.amount == -TOTAL_ATTENDU


def test_le_solde_federe_rembourse_est_encaisse_par_le_lieu(
    tenant, wallet_du_lieu, carte_client_mixte, asset_monnaie_federee,
):
    """Une ligne positive en monnaie federee accompagne la sortie de caisse.

    Rendre du federe en billets, c'est deux mouvements comptables : le lieu
    encaisse de la monnaie du reseau (ligne positive), et sort du liquide
    (ligne negative). Sans la ligne positive, la caisse afficherait une sortie
    sans contrepartie.
    / Refunding federated money in cash is two accounting movements: the venue
    takes in network currency, and pays out cash. Without the positive line, the
    register would show an outflow with no counterpart.
    """
    with tenant_context(tenant):
        WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
        )

        ligne_federee = LigneArticle.objects.get(
            carte=carte_client_mixte,
            payment_method=PaymentMethod.STRIPE_FED,
        )
        assert ligne_federee.amount == SOLDE_MONNAIE_FEDEREE
        # L'asset est trace sur la ligne : c'est ce qui permet de savoir QUELLE
        # monnaie du reseau a ete encaissee.
        # / The asset is recorded on the line: it tells WHICH network currency
        # was taken in.
        assert ligne_federee.asset == asset_monnaie_federee.uuid


def test_les_lignes_portent_une_trace_comptable_complete(
    tenant, wallet_du_lieu, carte_client_mixte,
):
    """Chaque ligne sait d'ou elle vient : carte, portefeuille, origine, etat.

    Une ligne sans `carte` ni `wallet` serait un montant orphelin dans le
    journal : impossible de rattacher la sortie de caisse a la personne
    remboursee lors d'un controle.
    / A line without carte or wallet would be an orphan amount in the journal:
    impossible to tie the cash outflow to the refunded person during an audit.
    """
    with tenant_context(tenant):
        WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
        )

        lignes = LigneArticle.objects.filter(carte=carte_client_mixte)
        assert lignes.count() == 2

        for ligne in lignes:
            assert ligne.carte_id == carte_client_mixte.pk
            assert ligne.wallet_id == carte_client_mixte.wallet_ephemere_id
            assert ligne.status == LigneArticle.VALID
            assert ligne.sale_origin == SaleOrigin.LABOUTIK
            assert ligne.qty == 1
            # Le tarif rattache la ligne au produit systeme « Remboursement »,
            # sans lequel elle n'apparaitrait dans aucun export comptable.
            # / The price ties the line to the system "Refund" product, without
            # which it would appear in no accounting export.
            assert ligne.pricesold is not None


def test_chaque_monnaie_rendue_laisse_sa_transaction(
    tenant, wallet_du_lieu, carte_client_mixte,
):
    """Deux monnaies rendues, deux mouvements de portefeuille, et les comptes
    tombent juste.

    Les `Transaction` tracent le portefeuille, les `LigneArticle` tracent la
    caisse. Les deux doivent raconter la meme histoire : si leurs totaux
    divergent, l'un des deux journaux ment.
    / Transactions track the wallet, LigneArticle track the register. Both must
    tell the same story: diverging totals mean one of the journals lies.
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

        total_des_transactions = sum(tx.amount for tx in transactions)
        ligne_de_sortie_de_caisse = LigneArticle.objects.get(
            carte=carte_client_mixte,
            payment_method=PaymentMethod.CASH,
        )
        assert total_des_transactions == abs(ligne_de_sortie_de_caisse.amount)


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


def test_vider_une_carte_depuis_la_caisse_ecrit_les_deux_lignes(
    tenant, carte_client_mixte, carte_du_caissier, point_de_vente,
):
    """Le parcours reel : un caissier vide une carte, la trace est complete.

    Ce test remplace la verification manuelle « vider une carte au point de
    vente » : il passe par la vraie route HTTP, avec la carte primaire, le
    controle d'acces au point de vente, et la garde anti-FED-local active — donc
    dans les conditions de production.
    / This replaces the manual "empty a card at the POS" check: it goes through
    the real HTTP route, with the primary card, the POS access control, and the
    local-FED guard ON — production conditions.
    """
    client, _administrateur = _connexion_caisse()

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
        ligne_de_sortie_de_caisse = LigneArticle.objects.get(
            carte=carte_client_mixte,
            payment_method=PaymentMethod.CASH,
            sale_origin=SaleOrigin.LABOUTIK,
        )
        assert ligne_de_sortie_de_caisse.amount == -TOTAL_ATTENDU

        ligne_federee = LigneArticle.objects.get(
            carte=carte_client_mixte,
            payment_method=PaymentMethod.STRIPE_FED,
        )
        assert ligne_federee.amount == SOLDE_MONNAIE_FEDEREE

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
# C. La remontee dans les rapports de caisse (ticket X et ticket Z)
# ---------------------------------------------------------------------------
#
# Un remboursement sort de l'argent du tiroir. Le rapport de caisse doit donc le
# voir, sans quoi la caisse ne tombe plus juste : le tiroir contient moins que ce
# que le ticket annonce, et l'ecart n'est explique nulle part.
#
# Le rapport ne lit que les lignes dont l'origine figure dans
# `ORIGINES_ENCAISSEES_PAR_LE_LIEU` (laboutik/reports.py). Le vidage de carte se
# declenchant depuis le point de vente, ses lignes portent l'origine caisse et y
# entrent — c'est ce que verifient les tests ci-dessous.
#
# / A refund takes cash out of the drawer, so the register report must see it.
# The report only reads lines whose origin is in ORIGINES_ENCAISSEES_PAR_LE_LIEU;
# card emptying happens at the point of sale, so its lines belong there.


def _rapport_de_la_periode(point_de_vente):
    """Le service de rapport sur une fenetre encadrant l'instant present.

    C'est le meme service qui alimente le ticket X (rapport temps reel) et le
    ticket Z (cloture) : les deux lisent `RapportComptableService`.
    / The same service feeds both the X report (real time) and the Z report
    (closure).
    """
    from datetime import timedelta

    from django.utils import timezone

    from laboutik.reports import RapportComptableService

    maintenant = timezone.now()
    return RapportComptableService(
        point_de_vente=point_de_vente,
        datetime_debut=maintenant - timedelta(minutes=5),
        datetime_fin=maintenant + timedelta(minutes=5),
    )


def test_la_ligne_de_remboursement_porte_l_origine_caisse(
    tenant, wallet_du_lieu, carte_client_mixte,
):
    """L'origine decide de tout : c'est elle qui fait entrer la ligne au rapport.

    Etiqueter ces lignes en ADMIN les ferait disparaitre des tickets X et Z, sans
    aucune erreur visible — le rapport afficherait simplement un montant faux.
    / The origin is what lets the line into the report. Tagging these lines ADMIN
    would silently drop them from the X and Z tickets.
    """
    with tenant_context(tenant):
        WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
        )

        ligne_de_sortie_de_caisse = LigneArticle.objects.get(
            carte=carte_client_mixte,
            payment_method=PaymentMethod.CASH,
        )

        assert ligne_de_sortie_de_caisse.sale_origin == SaleOrigin.LABOUTIK


def test_le_remboursement_apparait_dans_les_totaux_du_rapport(
    tenant, wallet_du_lieu, carte_client_mixte, point_de_vente,
):
    """La sortie d'especes doit peser sur le total especes du rapport.

    Rendre 1500 centimes en billets diminue d'autant les especes de la periode.
    Sans cela, le ticket X affiche un total d'especes superieur a ce que
    contient reellement le tiroir.
    / Handing 1500 cents back lowers the period's cash total by as much.

    On mesure un DELTA, jamais un total absolu : la fenetre de cinq minutes est
    partagee avec tous les autres tests de la suite, qui encaissent eux aussi
    des especes. Un total absolu passerait en isolation et echouerait en suite
    complete (PIEGES 9.60).
    / We measure a DELTA, never an absolute total: the five-minute window is
    shared with every other test in the suite. An absolute total would pass in
    isolation and fail in the full suite.
    """
    with tenant_context(tenant):
        especes_avant = _rapport_de_la_periode(point_de_vente).calculer_totaux_par_moyen()["especes"]

        WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
        )

        especes_apres = _rapport_de_la_periode(point_de_vente).calculer_totaux_par_moyen()["especes"]

        assert especes_apres - especes_avant == -TOTAL_ATTENDU


def test_le_remboursement_diminue_le_solde_de_caisse_du_rapport(
    tenant, wallet_du_lieu, carte_client_mixte, point_de_vente,
):
    """Le solde annonce doit correspondre a ce qu'il y a dans le tiroir.

    C'est la raison d'etre du solde de caisse : le comparer au comptage physique
    en fin de service. Un remboursement non compte cree un ecart que le caissier
    ne peut pas expliquer.
    / The register balance exists to be compared with the physical count at
    closing. An uncounted refund creates an unexplainable discrepancy.
    """
    with tenant_context(tenant):
        solde_avant = _rapport_de_la_periode(point_de_vente).calculer_solde_caisse()["solde"]

        WalletService.rembourser_en_especes(
            carte=carte_client_mixte,
            tenant=tenant,
            receiver_wallet=wallet_du_lieu,
        )

        solde_apres = _rapport_de_la_periode(point_de_vente).calculer_solde_caisse()["solde"]

        assert solde_apres == solde_avant - TOTAL_ATTENDU


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
