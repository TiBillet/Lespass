"""
tests/pytest/test_commandes_tables.py — Tests Phase 4 : commandes de restaurant.
tests/pytest/test_commandes_tables.py — Tests Phase 4: restaurant orders.

Couvre : CommandeSauvegarde, ArticleCommandeSauvegarde, Table statut,
         ouvrir/ajouter/servir/payer/annuler une commande.
Covers: CommandeSauvegarde, ArticleCommandeSauvegarde, Table status,
        open/add/serve/pay/cancel an order.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_commandes_tables.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, Product,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, Table, CategorieTable,
    CommandeSauvegarde, ArticleCommandeSauvegarde,
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
        email = 'admin-test-commandes@tibillet.localhost'
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
def pv_restaurant(test_data):
    """Un point de vente avec accepte_commandes=True.
    / A point of sale with accepte_commandes=True."""
    with schema_context(TENANT_SCHEMA):
        pv = PointDeVente.objects.filter(
            accepte_commandes=True, hidden=False,
        ).first()
        assert pv is not None, "Aucun PV restaurant trouve — verifier create_test_pos_data"
        return pv


@pytest.fixture(scope="module")
def table_test(test_data):
    """Une table de test (creee si elle n'existe pas).
    / A test table (created if it doesn't exist)."""
    with schema_context(TENANT_SCHEMA):
        categorie, _ = CategorieTable.objects.get_or_create(
            name='Salle test',
        )
        table, _ = Table.objects.get_or_create(
            name='Table Test P4',
            defaults={
                'categorie': categorie,
                'statut': Table.LIBRE,
            },
        )
        # Remettre la table en libre avant chaque module de tests
        # / Reset table to free before each test module
        table.statut = Table.LIBRE
        table.save(update_fields=['statut'])
        return table


@pytest.fixture(scope="module")
def produit_et_prix(pv_restaurant):
    """Premier produit du PV restaurant avec son prix EUR.
    / First product of the restaurant PV with its EUR price."""
    with schema_context(TENANT_SCHEMA):
        produit = pv_restaurant.products.filter(
            methode_caisse__isnull=False,
        ).first()
        assert produit is not None, "Aucun produit trouve dans le PV restaurant"
        prix = Price.objects.filter(
            product=produit,
            publish=True,
            asset__isnull=True,
        ).order_by('order').first()
        assert prix is not None, f"Aucun prix EUR pour le produit {produit.name}"
        return produit, prix


def _make_client(admin_user, tenant):
    """Cree un client DRF authentifie comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestOuvrirCommande:
    """Tests pour l'ouverture d'une commande.
    / Tests for opening an order."""

    def test_ouvrir_commande(
        self, admin_user, tenant, pv_restaurant, table_test, produit_et_prix,
    ):
        """Ouvrir une commande : Table L→O, CommandeSauvegarde creee, articles crees.
        / Open an order: Table L→O, CommandeSauvegarde created, articles created."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_et_prix
            client = _make_client(admin_user, tenant)

            # Remettre la table en libre
            # / Reset table to free
            table_test.statut = Table.LIBRE
            table_test.save(update_fields=['statut'])

            post_data = {
                "table_uuid": str(table_test.uuid),
                "uuid_pv": str(pv_restaurant.uuid),
                "articles": [
                    {
                        "product_uuid": str(produit.uuid),
                        "price_uuid": str(prix.uuid),
                        "qty": 2,
                    },
                ],
            }

            response = client.post(
                '/laboutik/commande/ouvrir/',
                data=post_data,
                format='json',
            )
            assert response.status_code == 201

            # Verifier la table
            # / Check the table
            table_test.refresh_from_db()
            assert table_test.statut == Table.OCCUPEE

            # Verifier la commande
            # / Check the order
            commande = CommandeSauvegarde.objects.filter(
                table=table_test,
                statut=CommandeSauvegarde.OPEN,
            ).latest('datetime')
            assert commande is not None

            # Verifier les articles
            # / Check the articles
            articles = commande.articles.all()
            assert articles.count() == 1
            article = articles.first()
            assert article.product == produit
            assert article.price == prix
            assert article.qty == 2
            assert article.statut == ArticleCommandeSauvegarde.EN_ATTENTE
            assert article.reste_a_servir == 2

    def test_serializer_validation_articles_vide(
        self, admin_user, tenant, pv_restaurant, table_test,
    ):
        """Articles vide → erreur 400.
        / Empty articles → 400 error."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)

            post_data = {
                "table_uuid": str(table_test.uuid),
                "uuid_pv": str(pv_restaurant.uuid),
                "articles": [],
            }

            response = client.post(
                '/laboutik/commande/ouvrir/',
                data=post_data,
                format='json',
            )
            assert response.status_code == 400


@pytest.mark.usefixtures("test_data")
class TestAjouterArticles:
    """Tests pour l'ajout d'articles a une commande existante.
    / Tests for adding articles to an existing order."""

    def test_ajouter_articles(
        self, admin_user, tenant, pv_restaurant, table_test, produit_et_prix,
    ):
        """Ajouter 2 articles a une commande OPEN.
        / Add 2 articles to an OPEN order."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_et_prix
            client = _make_client(admin_user, tenant)

            # Creer une commande ouverte
            # / Create an open order
            commande = CommandeSauvegarde.objects.create(
                table=table_test,
                statut=CommandeSauvegarde.OPEN,
            )
            ArticleCommandeSauvegarde.objects.create(
                commande=commande,
                product=produit,
                price=prix,
                qty=1,
                reste_a_payer=int(round(prix.prix * 100)),
                reste_a_servir=1,
            )

            nb_articles_avant = commande.articles.count()

            post_data = [
                {
                    "product_uuid": str(produit.uuid),
                    "price_uuid": str(prix.uuid),
                    "qty": 3,
                },
            ]

            response = client.post(
                f'/laboutik/commande/ajouter/{commande.uuid}/',
                data=post_data,
                format='json',
            )
            assert response.status_code == 200

            nb_articles_apres = commande.articles.count()
            assert nb_articles_apres == nb_articles_avant + 1

    def test_ajouter_a_commande_fermee(
        self, admin_user, tenant, pv_restaurant, table_test, produit_et_prix,
    ):
        """Ajouter a une commande PAID → erreur 400.
        / Adding to a PAID order → 400 error."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_et_prix
            client = _make_client(admin_user, tenant)

            commande = CommandeSauvegarde.objects.create(
                table=table_test,
                statut=CommandeSauvegarde.PAID,
            )

            post_data = [
                {
                    "product_uuid": str(produit.uuid),
                    "price_uuid": str(prix.uuid),
                    "qty": 1,
                },
            ]

            response = client.post(
                f'/laboutik/commande/ajouter/{commande.uuid}/',
                data=post_data,
                format='json',
            )
            assert response.status_code == 400


@pytest.mark.usefixtures("test_data")
class TestMarquerServie:
    """Tests pour marquer une commande comme servie.
    / Tests for marking an order as served."""

    def test_marquer_servie(
        self, admin_user, tenant, pv_restaurant, table_test, produit_et_prix,
    ):
        """Marquer comme servie : articles → SERVI, commande → SERVED.
        / Mark as served: articles → SERVED, order → SERVED."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_et_prix
            client = _make_client(admin_user, tenant)

            commande = CommandeSauvegarde.objects.create(
                table=table_test,
                statut=CommandeSauvegarde.OPEN,
            )
            ArticleCommandeSauvegarde.objects.create(
                commande=commande,
                product=produit,
                price=prix,
                qty=1,
                reste_a_servir=1,
                statut=ArticleCommandeSauvegarde.EN_ATTENTE,
            )

            response = client.post(
                f'/laboutik/commande/servir/{commande.uuid}/',
            )
            assert response.status_code == 200

            commande.refresh_from_db()
            assert commande.statut == CommandeSauvegarde.SERVED

            article = commande.articles.first()
            assert article.statut == ArticleCommandeSauvegarde.SERVI
            assert article.reste_a_servir == 0


@pytest.mark.usefixtures("test_data")
class TestPayerCommande:
    """Tests pour le paiement d'une commande.
    / Tests for paying an order."""

    def test_payer_commande_especes(
        self, admin_user, tenant, pv_restaurant, table_test, produit_et_prix,
    ):
        """Payer en especes : CommandeSauvegarde → PAID, Table → L, LigneArticle crees.
        / Cash payment: CommandeSauvegarde → PAID, Table → L, LigneArticle created."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_et_prix
            client = _make_client(admin_user, tenant)

            # Nettoyer les commandes ouvertes des tests precedents sur cette table
            # / Clean up open orders from previous tests on this table
            CommandeSauvegarde.objects.filter(
                table=table_test,
                statut__in=[CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED],
            ).update(statut=CommandeSauvegarde.CANCEL)

            # Remettre la table en occupee
            # / Reset table to occupied
            table_test.statut = Table.OCCUPEE
            table_test.save(update_fields=['statut'])

            commande = CommandeSauvegarde.objects.create(
                table=table_test,
                statut=CommandeSauvegarde.OPEN,
            )
            prix_centimes = int(round(prix.prix * 100))
            ArticleCommandeSauvegarde.objects.create(
                commande=commande,
                product=produit,
                price=prix,
                qty=1,
                reste_a_payer=prix_centimes,
                reste_a_servir=1,
            )

            nb_lignes_avant = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).count()

            post_data = {
                'uuid_pv': str(pv_restaurant.uuid),
                'moyen_paiement': 'espece',
                'given_sum': '0',
            }

            response = client.post(
                f'/laboutik/commande/payer/{commande.uuid}/',
                data=post_data,
            )
            assert response.status_code == 200

            # Verifier la commande
            # / Check the order
            commande.refresh_from_db()
            assert commande.statut == CommandeSauvegarde.PAID

            # Verifier la table
            # / Check the table
            table_test.refresh_from_db()
            assert table_test.statut == Table.LIBRE

            # Verifier les LigneArticle
            # / Check LigneArticle
            nb_lignes_apres = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).count()
            assert nb_lignes_apres == nb_lignes_avant + 1

            # Verifier le moyen de paiement
            # / Check payment method
            derniere_ligne = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).latest('datetime')
            assert derniere_ligne.payment_method == PaymentMethod.CASH


@pytest.mark.usefixtures("test_data")
class TestAnnulerCommande:
    """Tests pour l'annulation d'une commande.
    / Tests for cancelling an order."""

    def test_annuler_commande(
        self, admin_user, tenant, pv_restaurant, table_test, produit_et_prix,
    ):
        """Annuler une commande : statut → CANCEL, Table → L.
        / Cancel an order: status → CANCEL, Table → L."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_et_prix
            client = _make_client(admin_user, tenant)

            # Nettoyer les commandes ouvertes des tests precedents sur cette table
            # / Clean up open orders from previous tests on this table
            CommandeSauvegarde.objects.filter(
                table=table_test,
                statut__in=[CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED],
            ).update(statut=CommandeSauvegarde.CANCEL)

            # Remettre la table en occupee
            # / Reset table to occupied
            table_test.statut = Table.OCCUPEE
            table_test.save(update_fields=['statut'])

            commande = CommandeSauvegarde.objects.create(
                table=table_test,
                statut=CommandeSauvegarde.OPEN,
            )
            ArticleCommandeSauvegarde.objects.create(
                commande=commande,
                product=produit,
                price=prix,
                qty=1,
                reste_a_servir=1,
            )

            response = client.post(
                f'/laboutik/commande/annuler/{commande.uuid}/',
            )
            assert response.status_code == 200

            commande.refresh_from_db()
            assert commande.statut == CommandeSauvegarde.CANCEL

            table_test.refresh_from_db()
            assert table_test.statut == Table.LIBRE

            article = commande.articles.first()
            assert article.statut == ArticleCommandeSauvegarde.ANNULE

    def test_table_occupee_si_autre_commande(
        self, admin_user, tenant, pv_restaurant, table_test, produit_et_prix,
    ):
        """Annuler 1 commande mais table reste O si autre commande OPEN.
        / Cancel 1 order but table stays O if another OPEN order exists."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_et_prix
            client = _make_client(admin_user, tenant)

            # Remettre la table en occupee
            # / Reset table to occupied
            table_test.statut = Table.OCCUPEE
            table_test.save(update_fields=['statut'])

            # Creer 2 commandes sur la meme table
            # / Create 2 orders on the same table
            commande_1 = CommandeSauvegarde.objects.create(
                table=table_test,
                statut=CommandeSauvegarde.OPEN,
            )
            ArticleCommandeSauvegarde.objects.create(
                commande=commande_1,
                product=produit,
                price=prix,
                qty=1,
            )

            commande_2 = CommandeSauvegarde.objects.create(
                table=table_test,
                statut=CommandeSauvegarde.OPEN,
            )
            ArticleCommandeSauvegarde.objects.create(
                commande=commande_2,
                product=produit,
                price=prix,
                qty=1,
            )

            # Annuler la premiere commande
            # / Cancel the first order
            response = client.post(
                f'/laboutik/commande/annuler/{commande_1.uuid}/',
            )
            assert response.status_code == 200

            commande_1.refresh_from_db()
            assert commande_1.statut == CommandeSauvegarde.CANCEL

            # La table doit rester occupee (commande_2 est encore OPEN)
            # / Table must stay occupied (commande_2 is still OPEN)
            table_test.refresh_from_db()
            assert table_test.statut == Table.OCCUPEE

    def test_annuler_commande_payee_interdit(
        self, admin_user, tenant, pv_restaurant, table_test, produit_et_prix,
    ):
        """Annuler une commande payee → erreur 400.
        / Cancelling a paid order → 400 error."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_et_prix
            client = _make_client(admin_user, tenant)

            commande = CommandeSauvegarde.objects.create(
                table=table_test,
                statut=CommandeSauvegarde.PAID,
            )

            response = client.post(
                f'/laboutik/commande/annuler/{commande.uuid}/',
            )
            assert response.status_code == 400
