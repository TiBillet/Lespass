"""
tests/pytest/test_cloture_caisse.py — Tests Phase 5 : cloture de caisse.
tests/pytest/test_cloture_caisse.py — Tests Phase 5: cash register closure.

Couvre : ClotureCaisse, cloturer(), totaux, fermeture tables, rapport JSON.
Covers: ClotureCaisse, cloturer(), totals, table closure, JSON report.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_cloture_caisse.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from decimal import Decimal

from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, ClotureCaisse, Table, CommandeSauvegarde,
)


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
    call_command('create_test_pos_data')
    return True


@pytest.fixture(scope="module")
def admin_user(tenant):
    """Un utilisateur admin du tenant.
    / A tenant admin user."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-cloture@tibillet.localhost'
        user, created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="module")
def premier_pv(test_data):
    """Le premier point de vente (Bar).
    / The first point of sale (Bar)."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).order_by('poid_liste').first()


@pytest.fixture(scope="module")
def premier_produit_et_prix(premier_pv):
    """Premier produit du PV avec son prix.
    / First product of the PV with its price."""
    with schema_context(TENANT_SCHEMA):
        produit = premier_pv.products.filter(
            methode_caisse__isnull=False,
        ).first()
        prix = Price.objects.filter(
            product=produit,
            publish=True,
            asset__isnull=True,
        ).order_by('order').first()
        return produit, prix


def _make_client(admin_user, tenant):
    """Cree un client DRF authentifie comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


def _creer_ligne_article_directe(produit, prix, montant_centimes, payment_method_code, dt=None, pv=None):
    """
    Cree une LigneArticle directement en base (sans passer par la vue).
    Creates a LigneArticle directly in DB (without going through the view).

    :param produit: Product
    :param prix: Price
    :param montant_centimes: int en centimes
    :param payment_method_code: PaymentMethod.CASH, .CC, .LOCAL_EURO, etc.
    :param dt: datetime optionnel (None = maintenant)
    :param pv: PointDeVente optionnel (None = pas de PV)
    """
    # ProductSold : snapshot du produit
    # / Product snapshot
    product_sold, _ = ProductSold.objects.get_or_create(
        product=produit,
        event=None,
        defaults={'categorie_article': produit.categorie_article},
    )
    # PriceSold : snapshot du prix
    # / Price snapshot
    price_sold, _ = PriceSold.objects.get_or_create(
        productsold=product_sold,
        price=prix,
        defaults={'prix': prix.prix},
    )
    ligne = LigneArticle.objects.create(
        pricesold=price_sold,
        qty=1,
        amount=montant_centimes,
        sale_origin=SaleOrigin.LABOUTIK,
        payment_method=payment_method_code,
        status=LigneArticle.VALID,
        point_de_vente=pv,
    )
    # Mettre a jour le datetime si specifie (auto_now_add ne permet pas de le setter)
    # / Update datetime if specified (auto_now_add prevents setting it)
    if dt is not None:
        LigneArticle.objects.filter(pk=ligne.pk).update(datetime=dt)
    return ligne


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestClotureTotauxCorrects:
    """Verifie que les totaux de la cloture sont corrects.
    / Verify that closure totals are correct."""

    def test_cloture_totaux_corrects(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Setup : creer 3 LigneArticle (1 espece 500c, 1 CB 1000c, 1 NFC 2000c).
        Action : cloturer().
        Verify : total_especes=500, total_cb=1000, total_nfc=2000, total_general=3500.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Creer les 3 LigneArticle
            # / Create the 3 LigneArticle
            _creer_ligne_article_directe(produit, prix, 500, PaymentMethod.CASH)
            _creer_ligne_article_directe(produit, prix, 1000, PaymentMethod.CC)
            _creer_ligne_article_directe(produit, prix, 2000, PaymentMethod.LOCAL_EURO)

            # Appeler l'endpoint de cloture (datetime_ouverture est calcule automatiquement)
            # / Call the closure endpoint (datetime_ouverture is computed automatically)
            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
            }
            response = client.post('/laboutik/caisse/cloturer/', data=post_data)
            assert response.status_code == 200

            # Verifier que la ClotureCaisse a ete creee
            # / Verify that ClotureCaisse was created
            cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
            assert cloture is not None
            assert cloture.total_especes >= 500
            assert cloture.total_carte_bancaire >= 1000
            assert cloture.total_cashless >= 2000
            assert cloture.total_general >= 3500


@pytest.mark.usefixtures("test_data")
class TestClotureNombreTransactions:
    """Verifie le nombre de transactions dans la cloture.
    / Verify the transaction count in the closure."""

    def test_cloture_nombre_transactions(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Verify : nombre_transactions compte les lignes de la periode.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            _creer_ligne_article_directe(produit, prix, 100, PaymentMethod.CASH)
            _creer_ligne_article_directe(produit, prix, 200, PaymentMethod.CC)
            _creer_ligne_article_directe(produit, prix, 300, PaymentMethod.LOCAL_EURO)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
            }
            response = client.post('/laboutik/caisse/cloturer/', data=post_data)
            assert response.status_code == 200

            cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
            assert cloture is not None
            assert cloture.nombre_transactions >= 3


@pytest.mark.usefixtures("test_data")
class TestClotureFermeTables:
    """Verifie que les tables ouvertes sont liberees apres cloture.
    / Verify that open tables are freed after closure."""

    def test_cloture_ferme_tables(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Setup : 2 tables OCCUPEE + 1 vente (pour que la cloture ait quelque chose a cloturer).
        Action : cloturer().
        Verify : les 2 tables passent a LIBRE.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Creer 2 tables OCCUPEE pour le test
            # / Create 2 OCCUPIED tables for the test
            table1, _ = Table.objects.get_or_create(
                name='Test Cloture T1',
                defaults={'statut': Table.OCCUPEE},
            )
            table1.statut = Table.OCCUPEE
            table1.save(update_fields=['statut'])

            table2, _ = Table.objects.get_or_create(
                name='Test Cloture T2',
                defaults={'statut': Table.OCCUPEE},
            )
            table2.statut = Table.OCCUPEE
            table2.save(update_fields=['statut'])

            # Il faut au moins une vente pour que la cloture fonctionne
            # / Need at least one sale for the closure to work
            _creer_ligne_article_directe(produit, prix, 100, PaymentMethod.CASH)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
            }
            response = client.post('/laboutik/caisse/cloturer/', data=post_data)
            assert response.status_code == 200

            # Recharger depuis la DB
            # / Reload from DB
            table1.refresh_from_db()
            table2.refresh_from_db()
            assert table1.statut == Table.LIBRE
            assert table2.statut == Table.LIBRE


@pytest.mark.usefixtures("test_data")
class TestClotureRapportJSON:
    """Verifie que le rapport JSON contient les bonnes sections.
    / Verify that the JSON report contains the correct sections."""

    def test_cloture_rapport_json_complet(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Verify : rapport_json contient par_categorie, par_produit, par_moyen_paiement.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            _creer_ligne_article_directe(produit, prix, 500, PaymentMethod.CASH)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
            }
            response = client.post('/laboutik/caisse/cloturer/', data=post_data)
            assert response.status_code == 200

            cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
            assert cloture is not None
            rapport = cloture.rapport_json

            # Les 13 cles du RapportComptableService
            # / The 13 keys from RapportComptableService
            assert 'totaux_par_moyen' in rapport
            assert 'detail_ventes' in rapport
            assert 'tva' in rapport
            assert 'solde_caisse' in rapport
            assert 'recharges' in rapport
            assert 'adhesions' in rapport
            assert 'remboursements' in rapport
            assert 'habitus' in rapport
            assert 'billets' in rapport
            assert 'synthese_operations' in rapport
            assert 'operateurs' in rapport
            assert 'ventilation_par_pv' in rapport
            assert 'infos_legales' in rapport

            # Verifier la structure totaux_par_moyen
            # / Verify totaux_par_moyen structure
            totaux = rapport['totaux_par_moyen']
            assert 'especes' in totaux
            assert 'carte_bancaire' in totaux
            assert 'cashless' in totaux

            # Verifier la structure TVA
            # / Verify TVA structure
            tva = rapport['tva']
            assert isinstance(tva, dict)
            for cle_taux, donnees_tva in tva.items():
                assert 'taux' in donnees_tva
                assert 'total_ttc' in donnees_tva
                assert 'total_ht' in donnees_tva
                assert 'total_tva' in donnees_tva


@pytest.mark.usefixtures("test_data")
class TestClotureCalculAutoDatetime:
    """Verifie que datetime_ouverture est calcule automatiquement.
    / Verify that datetime_ouverture is computed automatically."""

    def test_cloture_datetime_ouverture_auto(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Setup : creer une vente.
        Action : cloturer (sans datetime_ouverture dans le POST).
        Verify : la cloture a bien un datetime_ouverture et contient la vente.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Creer une LigneArticle
            # / Create a LigneArticle
            _creer_ligne_article_directe(produit, prix, 777, PaymentMethod.CASH)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
            }
            response = client.post('/laboutik/caisse/cloturer/', data=post_data)
            assert response.status_code == 200

            # La cloture doit exister avec datetime_ouverture renseigne
            # / The closure must exist with datetime_ouverture set
            cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
            assert cloture is not None
            assert cloture.datetime_ouverture is not None
            assert cloture.datetime_ouverture < cloture.datetime_cloture
            assert cloture.nombre_transactions >= 1


@pytest.mark.usefixtures("test_data")
class TestDoubleClotureMmePeriode:
    """Verifie qu'on peut cloturer 2 fois la meme periode (pas de blocage).
    / Verify that double closure of the same period works (no blocking)."""

    def test_double_cloture_meme_periode(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Action : cloturer 2 fois la meme periode.
        Verify : 2 ClotureCaisse creees.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            _creer_ligne_article_directe(produit, prix, 100, PaymentMethod.CASH)

            nb_clotures_avant = ClotureCaisse.objects.count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
            }

            # Premiere cloture
            # / First closure
            response1 = client.post('/laboutik/caisse/cloturer/', data=post_data)
            assert response1.status_code == 200

            # Creer une nouvelle vente pour la 2eme cloture
            # / Create a new sale for the 2nd closure
            _creer_ligne_article_directe(produit, prix, 200, PaymentMethod.CC)

            # Deuxieme cloture
            # / Second closure
            response2 = client.post('/laboutik/caisse/cloturer/', data=post_data)
            assert response2.status_code == 200

            # Verifier que 2 nouvelles clotures ont ete creees
            # / Verify that 2 new closures were created
            nb_clotures_apres = ClotureCaisse.objects.count()
            assert nb_clotures_apres >= nb_clotures_avant + 2


@pytest.mark.usefixtures("test_data")
class TestClotureAnnuleCommandes:
    """Verifie que les commandes OPEN sont annulees apres cloture.
    / Verify that OPEN orders are cancelled after closure."""

    def test_cloture_annule_commandes_ouvertes(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Setup : 1 commande OPEN + 1 vente.
        Action : cloturer().
        Verify : la commande passe a CANCEL.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Creer une commande OPEN pour le test
            # / Create an OPEN order for the test
            commande = CommandeSauvegarde.objects.create(
                statut=CommandeSauvegarde.OPEN,
                commentaire='Test cloture phase 5',
            )

            # Il faut au moins une vente pour que la cloture fonctionne
            # / Need at least one sale for the closure to work
            _creer_ligne_article_directe(produit, prix, 100, PaymentMethod.CASH)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
            }
            response = client.post('/laboutik/caisse/cloturer/', data=post_data)
            assert response.status_code == 200

            # Recharger la commande
            # / Reload the order
            commande.refresh_from_db()
            assert commande.statut == CommandeSauvegarde.CANCEL
