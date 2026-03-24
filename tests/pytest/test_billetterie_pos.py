"""
tests/pytest/test_billetterie_pos.py — Tests de la billetterie POS :
extraction d'articles billet, creation Reservation + Ticket, jauge atomique.
/ Tests for POS ticketing: ticket article extraction, Reservation + Ticket
creation, atomic gauge check.

LOCALISATION : tests/pytest/test_billetterie_pos.py

Couvre :
  - _extraire_articles_du_panier avec ID composite event__price
  - _creer_billets_depuis_panier : Reservation, Ticket, jauge
  - Panier mixte (biere + billet, adhesion + billet)
  - Ticket.status = NOT_SCANNED ('K')

Prerequis / Prerequisites:
  - Base de donnees avec le tenant 'lespass' existant
  - demo_data_v2 chargee (pour les events existants)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_billetterie_pos.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.utils import timezone
from django_tenants.utils import schema_context, tenant_context

from Customers.models import Client


# Prefixe pour identifier les donnees de ce module et les nettoyer.
# / Prefix to identify this module's data and clean it up.
TEST_PREFIX = 'zz_test_billetterie'

TENANT_SCHEMA = 'lespass'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass'. / The 'lespass' tenant."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def donnees_billetterie(tenant):
    """
    Cree un Event futur + Product BILLET + Price + PointDeVente BILLETTERIE.
    Nettoie apres tous les tests du module.
    / Creates a future Event + BILLET Product + Price + BILLETTERIE PointDeVente.
    Cleans up after all module tests.
    """
    from BaseBillet.models import Event, Product, Price, Ticket, Reservation
    from BaseBillet.models import ProductSold, PriceSold, LigneArticle
    from laboutik.models import PointDeVente

    with tenant_context(tenant):
        # --- Nettoyage des donnees residuelles d'un run precedent ---
        # / Cleanup residual data from a previous run
        Ticket.objects.filter(
            reservation__event__name__startswith=TEST_PREFIX,
        ).delete()
        LigneArticle.objects.filter(
            pricesold__productsold__product__name__startswith=TEST_PREFIX,
        ).delete()
        PriceSold.objects.filter(
            productsold__product__name__startswith=TEST_PREFIX,
        ).delete()
        ProductSold.objects.filter(
            product__name__startswith=TEST_PREFIX,
        ).delete()
        Reservation.objects.filter(
            event__name__startswith=TEST_PREFIX,
        ).delete()
        # Les PV de test ne sont pas supprimes (FK PROTECT depuis d'autres tables).
        # get_or_create les reutilisera au prochain run.
        # / Test PVs are not deleted (FK PROTECT from other tables).
        # get_or_create will reuse them on the next run.

        # Creer le Product billet (get_or_create pour eviter les doublons)
        # / Create the ticket Product (get_or_create to avoid duplicates)
        product_billet, _ = Product.objects.get_or_create(
            name=f"{TEST_PREFIX} Concert Rock",
            categorie_article=Product.BILLET,
            defaults={'publish': True},
        )

        # Creer la Price
        # / Create the Price
        price_billet, _ = Price.objects.get_or_create(
            product=product_billet,
            name=f"{TEST_PREFIX} Plein tarif",
            defaults={'prix': Decimal("15.00"), 'publish': True},
        )

        # Creer l'Event futur
        # / Create a future Event
        event_futur, _ = Event.objects.get_or_create(
            name=f"{TEST_PREFIX} Festival Rock",
            defaults={
                'datetime': timezone.now() + timedelta(days=7),
                'jauge_max': 10,
                'published': True,
            },
        )
        # S'assurer que la date est dans le futur et la jauge est a 10
        # / Ensure the date is in the future and the gauge is at 10
        event_futur.datetime = timezone.now() + timedelta(days=7)
        event_futur.jauge_max = 10
        event_futur.published = True
        event_futur.save(update_fields=['datetime', 'jauge_max', 'published'])
        event_futur.products.add(product_billet)

        # Creer un Product biere standard (pour les paniers mixtes)
        # / Create a standard beer Product (for mixed carts)
        product_biere, _ = Product.objects.get_or_create(
            name=f"{TEST_PREFIX} Biere",
            defaults={
                'categorie_article': Product.NONE,
                'methode_caisse': Product.VENTE,
                'publish': True,
            },
        )
        price_biere, _ = Price.objects.get_or_create(
            product=product_biere,
            name=f"{TEST_PREFIX} Biere prix",
            defaults={'prix': Decimal("5.00"), 'publish': True},
        )

        # Creer le PointDeVente BILLETTERIE
        # / Create the BILLETTERIE PointDeVente
        pv_billetterie, _ = PointDeVente.objects.get_or_create(
            name=f"{TEST_PREFIX} Accueil",
            defaults={
                'comportement': PointDeVente.BILLETTERIE,
                'accepte_especes': True,
                'accepte_carte_bancaire': True,
                'poid_liste': 9999,  # En fin de liste pour ne pas perturber premier_pv des autres tests
            },
        )
        pv_billetterie.products.add(product_biere)

        donnees = {
            'product_billet': product_billet,
            'price_billet': price_billet,
            'event': event_futur,
            'product_biere': product_biere,
            'price_biere': price_biere,
            'pv': pv_billetterie,
        }

        yield donnees

        # --- Nettoyage (ordre inverse des FK) ---
        # Les Products/Prices/Events ne sont pas supprimes ici
        # car stdimage leve TypeError sur post_delete si pas d'image.
        # Ils seront nettoyes au prochain run par le cleanup initial.
        # / Products/Prices/Events are not deleted here because stdimage
        # raises TypeError on post_delete if no image.
        # They will be cleaned up on the next run by the initial cleanup.
        Ticket.objects.filter(
            reservation__event=event_futur,
        ).delete()
        LigneArticle.objects.filter(
            pricesold__productsold__product__name__startswith=TEST_PREFIX,
        ).delete()
        Reservation.objects.filter(event=event_futur).delete()
        PriceSold.objects.filter(
            productsold__product__name__startswith=TEST_PREFIX,
        ).delete()
        ProductSold.objects.filter(
            product__name__startswith=TEST_PREFIX,
        ).delete()
        pv_billetterie.products.clear()


@pytest.fixture(scope="module")
def user_client(tenant):
    """
    Utilisateur client pour les tests de billetterie.
    / Client user for ticketing tests.
    """
    from AuthBillet.utils import get_or_create_user

    email = f"{TEST_PREFIX.lower()}@test.local"
    user = get_or_create_user(email, send_mail=False)
    if not user.first_name:
        user.first_name = 'Test'
        user.last_name = 'Billet'
        user.save(update_fields=['first_name', 'last_name'])
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtraireArticlesBilletterie:
    """Tests de _extraire_articles_du_panier pour les articles BILLETTERIE."""

    def test_extraire_article_billet_id_composite(self, tenant, donnees_billetterie):
        """
        POST avec repid-{event_uuid}__{price_uuid} → article trouve
        avec est_billet=True et event correct.
        / POST with repid-{event_uuid}__{price_uuid} → article found
        with est_billet=True and correct event.
        """
        from laboutik.views import _extraire_articles_du_panier

        pv = donnees_billetterie['pv']
        event = donnees_billetterie['event']
        price = donnees_billetterie['price_billet']

        # Simuler le POST avec l'ID composite
        # / Simulate POST with composite ID
        id_composite = f"{event.uuid}__{price.uuid}"
        post_data = {
            f"repid-{id_composite}": "2",
        }

        with tenant_context(tenant):
            articles = _extraire_articles_du_panier(post_data, pv)

        assert len(articles) == 1
        article = articles[0]
        assert article['est_billet'] is True
        assert article['event'] is not None
        assert str(article['event'].uuid) == str(event.uuid)
        assert article['product'] == donnees_billetterie['product_billet']
        assert article['price'] == price
        assert article['quantite'] == 2
        assert article['prix_centimes'] == 1500

    def test_extraire_article_standard_dans_pv_billetterie(self, tenant, donnees_billetterie):
        """
        Un article standard (biere) dans un PV BILLETTERIE est extrait normalement.
        / A standard article (beer) in a BILLETTERIE PV is extracted normally.
        """
        from laboutik.views import _extraire_articles_du_panier

        pv = donnees_billetterie['pv']
        product_biere = donnees_billetterie['product_biere']

        post_data = {
            f"repid-{product_biere.uuid}": "1",
        }

        with tenant_context(tenant):
            articles = _extraire_articles_du_panier(post_data, pv)

        assert len(articles) == 1
        article = articles[0]
        assert article['est_billet'] is False
        assert article['event'] is None
        assert article['product'] == product_biere


class TestCreerBilletDepuisPanier:
    """Tests de _creer_billets_depuis_panier."""

    def test_creer_billet_espece_sans_email(self, tenant, donnees_billetterie, user_client):
        """
        Paiement especes avec tag_id → Reservation VALID + Ticket NOT_SCANNED, to_mail=False.
        / Cash payment with tag_id → Reservation VALID + Ticket NOT_SCANNED, to_mail=False.
        """
        from BaseBillet.models import Reservation, Ticket, LigneArticle
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles
        from django.db import transaction as db_transaction
        from QrcodeCashless.models import CarteCashless

        event = donnees_billetterie['event']
        price = donnees_billetterie['price_billet']
        product = donnees_billetterie['product_billet']

        with tenant_context(tenant):
            # Creer/recuperer une carte NFC pour l'identification
            # / Create/get an NFC card for identification
            carte, _ = CarteCashless.objects.get_or_create(
                tag_id='BTST0001',
                defaults={'number': 'BTST0001', 'user': user_client},
            )
            if carte.user != user_client:
                carte.user = user_client
                carte.save(update_fields=['user'])

            articles_panier = [{
                'product': product,
                'price': price,
                'quantite': 1,
                'prix_centimes': 1500,
                'custom_amount_centimes': None,
                'est_billet': True,
                'event': event,
            }]

            # Simuler le request POST
            # / Simulate the POST request
            request = MagicMock()
            request.POST = {
                'tag_id': 'BTST0001',
                'moyen_paiement': 'espece',
            }
            request.META = {'REMOTE_ADDR': '127.0.0.1'}

            with db_transaction.atomic():
                lignes = _creer_lignes_articles(articles_panier, 'espece')
                reservations = _creer_billets_depuis_panier(
                    request, articles_panier, lignes_articles=lignes,
                )

            assert len(reservations) == 1
            reservation = reservations[0]
            assert reservation.status == Reservation.VALID
            assert reservation.to_mail is False
            assert reservation.user_commande == user_client
            assert reservation.event == event

            tickets = Ticket.objects.filter(reservation=reservation)
            assert tickets.count() == 1
            ticket = tickets.first()
            assert ticket.status == Ticket.NOT_SCANNED

            # Nettoyage (ordre FK : LigneArticle → Ticket → Reservation)
            # / Cleanup (FK order: LigneArticle → Ticket → Reservation)
            LigneArticle.objects.filter(reservation=reservation).delete()
            for ligne in lignes:
                ligne.delete()
            tickets.delete()
            reservation.delete()

    def test_creer_billet_avec_email(self, tenant, donnees_billetterie):
        """
        Paiement avec email → to_mail=True, user cree.
        / Payment with email → to_mail=True, user created.
        """
        from BaseBillet.models import Reservation, Ticket, LigneArticle
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles
        from django.db import transaction as db_transaction

        event = donnees_billetterie['event']
        price = donnees_billetterie['price_billet']
        product = donnees_billetterie['product_billet']

        with tenant_context(tenant):
            articles_panier = [{
                'product': product,
                'price': price,
                'quantite': 1,
                'prix_centimes': 1500,
                'custom_amount_centimes': None,
                'est_billet': True,
                'event': event,
            }]

            request = MagicMock()
            request.POST = {
                'email_adhesion': f'{TEST_PREFIX.lower()}email@test.local',
                'prenom_adhesion': 'Alice',
                'nom_adhesion': 'Dupont',
                'moyen_paiement': 'carte_bancaire',
            }
            request.META = {'REMOTE_ADDR': '127.0.0.1'}

            with db_transaction.atomic():
                lignes = _creer_lignes_articles(articles_panier, 'carte_bancaire')
                reservations = _creer_billets_depuis_panier(
                    request, articles_panier, lignes_articles=lignes,
                )

            assert len(reservations) == 1
            reservation = reservations[0]
            assert reservation.to_mail is True

            # Nettoyage (ordre FK : LigneArticle → Ticket → Reservation)
            LigneArticle.objects.filter(reservation=reservation).delete()
            for ligne in lignes:
                ligne.delete()
            Ticket.objects.filter(reservation=reservation).delete()
            reservation.delete()

    def test_jauge_bloque_vente(self, tenant, donnees_billetterie, user_client):
        """
        Jauge pleine → ValueError levee, aucun Ticket cree (rollback).
        / Full gauge → ValueError raised, no Ticket created (rollback).
        """
        from BaseBillet.models import Reservation, Ticket
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles
        from django.db import transaction as db_transaction
        from QrcodeCashless.models import CarteCashless

        event = donnees_billetterie['event']
        price = donnees_billetterie['price_billet']
        product = donnees_billetterie['product_billet']

        with tenant_context(tenant):
            # Remplir la jauge : creer 10 tickets (jauge_max=10)
            # / Fill the gauge: create 10 tickets (jauge_max=10)
            reservation_remplissage = Reservation.objects.create(
                user_commande=user_client,
                event=event,
                status=Reservation.VALID,
            )
            from BaseBillet.models import ProductSold, PriceSold
            ps, _ = ProductSold.objects.get_or_create(
                product=product, event=event,
                defaults={'categorie_article': product.categorie_article},
            )
            prs, _ = PriceSold.objects.get_or_create(
                productsold=ps, price=price,
                defaults={'prix': price.prix},
            )
            for _ in range(10):
                Ticket.objects.create(
                    reservation=reservation_remplissage,
                    pricesold=prs,
                    status=Ticket.NOT_SCANNED,
                )

            # Tenter d'acheter un billet de plus → ValueError
            # / Try to buy one more ticket → ValueError
            articles_panier = [{
                'product': product,
                'price': price,
                'quantite': 1,
                'prix_centimes': 1500,
                'custom_amount_centimes': None,
                'est_billet': True,
                'event': event,
            }]

            carte, _ = CarteCashless.objects.get_or_create(
                tag_id='BTST0001',
                defaults={'number': 'BTST0001', 'user': user_client},
            )

            request = MagicMock()
            request.POST = {
                'tag_id': 'BTST0001',
                'moyen_paiement': 'espece',
            }
            request.META = {'REMOTE_ADDR': '127.0.0.1'}

            with pytest.raises(ValueError, match="complet"):
                with db_transaction.atomic():
                    lignes = _creer_lignes_articles(articles_panier, 'espece')
                    _creer_billets_depuis_panier(
                        request, articles_panier, lignes_articles=lignes,
                    )

            # Verifier qu'aucun nouveau ticket n'a ete cree (rollback)
            # / Verify no new ticket was created (rollback)
            assert Ticket.objects.filter(
                reservation__event=event,
            ).count() == 10

            # Nettoyage
            Ticket.objects.filter(reservation=reservation_remplissage).delete()
            reservation_remplissage.delete()

    def test_ticket_status_not_scanned(self, tenant, donnees_billetterie, user_client):
        """
        Le Ticket cree a status='K' (NOT_SCANNED).
        / The created Ticket has status='K' (NOT_SCANNED).
        """
        from BaseBillet.models import Reservation, Ticket, LigneArticle
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles
        from django.db import transaction as db_transaction
        from QrcodeCashless.models import CarteCashless

        event = donnees_billetterie['event']
        price = donnees_billetterie['price_billet']
        product = donnees_billetterie['product_billet']

        with tenant_context(tenant):
            carte, _ = CarteCashless.objects.get_or_create(
                tag_id='BTST0001',
                defaults={'number': 'BTST0001', 'user': user_client},
            )

            articles_panier = [{
                'product': product,
                'price': price,
                'quantite': 3,
                'prix_centimes': 1500,
                'custom_amount_centimes': None,
                'est_billet': True,
                'event': event,
            }]

            request = MagicMock()
            request.POST = {
                'tag_id': 'BTST0001',
                'moyen_paiement': 'espece',
            }
            request.META = {'REMOTE_ADDR': '127.0.0.1'}

            with db_transaction.atomic():
                lignes = _creer_lignes_articles(articles_panier, 'espece')
                reservations = _creer_billets_depuis_panier(
                    request, articles_panier, lignes_articles=lignes,
                )

            tickets = Ticket.objects.filter(reservation=reservations[0])
            assert tickets.count() == 3
            for ticket in tickets:
                assert ticket.status == 'K'
                assert ticket.status == Ticket.NOT_SCANNED

            # Nettoyage (ordre FK : LigneArticle → Ticket → Reservation)
            LigneArticle.objects.filter(reservation=reservations[0]).delete()
            for ligne in lignes:
                ligne.delete()
            tickets.delete()
            reservations[0].delete()

    def test_panier_mixte_billet_et_vente(self, tenant, donnees_billetterie, user_client):
        """
        Biere + Billet → 2 LigneArticle, 1 Ticket pour le billet.
        / Beer + Ticket → 2 LigneArticle, 1 Ticket for the ticket.
        """
        from BaseBillet.models import Reservation, Ticket, LigneArticle
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles
        from django.db import transaction as db_transaction
        from QrcodeCashless.models import CarteCashless

        event = donnees_billetterie['event']
        price_billet = donnees_billetterie['price_billet']
        product_billet = donnees_billetterie['product_billet']
        product_biere = donnees_billetterie['product_biere']
        price_biere = donnees_billetterie['price_biere']

        with tenant_context(tenant):
            carte, _ = CarteCashless.objects.get_or_create(
                tag_id='BTST0001',
                defaults={'number': 'BTST0001', 'user': user_client},
            )

            articles_panier = [
                {
                    'product': product_biere,
                    'price': price_biere,
                    'quantite': 1,
                    'prix_centimes': 500,
                    'custom_amount_centimes': None,
                    'est_billet': False,
                    'event': None,
                },
                {
                    'product': product_billet,
                    'price': price_billet,
                    'quantite': 1,
                    'prix_centimes': 1500,
                    'custom_amount_centimes': None,
                    'est_billet': True,
                    'event': event,
                },
            ]

            request = MagicMock()
            request.POST = {
                'tag_id': 'BTST0001',
                'moyen_paiement': 'espece',
            }
            request.META = {'REMOTE_ADDR': '127.0.0.1'}

            with db_transaction.atomic():
                lignes = _creer_lignes_articles(articles_panier, 'espece')
                reservations = _creer_billets_depuis_panier(
                    request, articles_panier, lignes_articles=lignes,
                )

            # 2 LigneArticle creees (biere + billet)
            # / 2 LigneArticle created (beer + ticket)
            assert len(lignes) == 2

            # 1 Reservation + 1 Ticket pour le billet
            # / 1 Reservation + 1 Ticket for the ticket
            assert len(reservations) == 1
            tickets = Ticket.objects.filter(reservation=reservations[0])
            assert tickets.count() == 1

            # Nettoyage (ordre FK : LigneArticle → Ticket → Reservation)
            LigneArticle.objects.filter(reservation=reservations[0]).delete()
            for ligne in lignes:
                ligne.delete()
            tickets.delete()
            reservations[0].delete()

    def test_jauge_price_stock(self, tenant, donnees_billetterie, user_client):
        """
        Price.stock=2, 2 tickets existants → ValueError au 3e billet.
        / Price.stock=2, 2 existing tickets → ValueError on 3rd ticket.
        """
        from BaseBillet.models import Reservation, Ticket, ProductSold, PriceSold
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles
        from django.db import transaction as db_transaction
        from QrcodeCashless.models import CarteCashless

        event = donnees_billetterie['event']
        price = donnees_billetterie['price_billet']
        product = donnees_billetterie['product_billet']

        with tenant_context(tenant):
            # Mettre un stock de 2 sur la Price
            # / Set stock to 2 on the Price
            old_stock = price.stock
            price.stock = 2
            price.save(update_fields=['stock'])

            # Creer 2 tickets existants
            # / Create 2 existing tickets
            reservation_existante = Reservation.objects.create(
                user_commande=user_client,
                event=event,
                status=Reservation.VALID,
            )
            ps, _ = ProductSold.objects.get_or_create(
                product=product, event=event,
                defaults={'categorie_article': product.categorie_article},
            )
            prs, _ = PriceSold.objects.get_or_create(
                productsold=ps, price=price,
                defaults={'prix': price.prix},
            )
            for _ in range(2):
                Ticket.objects.create(
                    reservation=reservation_existante,
                    pricesold=prs,
                    status=Ticket.NOT_SCANNED,
                )

            carte, _ = CarteCashless.objects.get_or_create(
                tag_id='BTST0001',
                defaults={'number': 'BTST0001', 'user': user_client},
            )

            articles_panier = [{
                'product': product,
                'price': price,
                'quantite': 1,
                'prix_centimes': 1500,
                'custom_amount_centimes': None,
                'est_billet': True,
                'event': event,
            }]

            request = MagicMock()
            request.POST = {
                'tag_id': 'BTST0001',
                'moyen_paiement': 'espece',
            }
            request.META = {'REMOTE_ADDR': '127.0.0.1'}

            with pytest.raises(ValueError, match="tarif"):
                with db_transaction.atomic():
                    lignes = _creer_lignes_articles(articles_panier, 'espece')
                    _creer_billets_depuis_panier(
                        request, articles_panier, lignes_articles=lignes,
                    )

            # Nettoyage : restaurer le stock
            # / Cleanup: restore stock
            price.stock = old_stock
            price.save(update_fields=['stock'])
            Ticket.objects.filter(reservation=reservation_existante).delete()
            reservation_existante.delete()


# ===========================================================================
# PARTIE 3 — Tests HTTP du flow complet billetterie
# Testent le vrai chemin POST : moyens_paiement → identifier_client → payer.
# Utilisent APIClient avec schema_context (pas de MagicMock).
# / PART 3 — HTTP tests for the full ticketing flow.
# Test the real POST path: moyens_paiement → identifier_client → payer.
# Use APIClient with schema_context (no MagicMock).
# ===========================================================================

def _make_client_billetterie(admin_user, tenant):
    """Cree un APIClient authentifie pour le tenant.
    / Creates an authenticated APIClient for the tenant."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


@pytest.fixture(scope="module")
def admin_user_billetterie(tenant):
    """Admin pour les tests HTTP billetterie.
    / Admin for HTTP ticketing tests."""
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-billetterie@tibillet.localhost'
        user, _created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        return user


class TestBilletterieFlowHTTP:
    """Tests HTTP du flow complet billetterie sur le tenant lespass.
    / HTTP tests for the full ticketing flow on the lespass tenant.

    FLUX teste :
    1. POST moyens_paiement avec repid-{event_uuid}__{price_uuid}
       → reponse contient "Billetterie" et ecran identification
    2. POST identifier_client avec email
       → reponse contient recapitulatif avec "Billet" dans la description
    3. POST payer en especes
       → reponse succes + Reservation + Ticket en DB
    """

    def test_moyens_paiement_billet_declenche_identification(
        self, admin_user_billetterie, tenant, donnees_billetterie,
    ):
        """
        POST moyens_paiement avec un billet → ecran identification
        avec titre "Billetterie" et boutons NFC + email.
        / POST moyens_paiement with a ticket → identification screen
        with "Billetterie" title and NFC + email buttons.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client_billetterie(admin_user_billetterie, tenant)
            pv = donnees_billetterie['pv']
            event = donnees_billetterie['event']
            price = donnees_billetterie['price_billet']

            # POST avec l'ID composite event__price (comme le JS l'envoie)
            # / POST with composite event__price ID (as the JS sends it)
            id_composite = f"{event.uuid}__{price.uuid}"
            response = client.post('/laboutik/paiement/moyens_paiement/', data={
                'uuid_pv': str(pv.uuid),
                f'repid-{id_composite}': '1',
            })

            assert response.status_code == 200
            contenu = response.content.decode()

            # L'ecran d'identification doit apparaitre (pas les boutons de paiement directs)
            # / The identification screen must appear (not direct payment buttons)
            assert 'client-choose-nfc' in contenu or 'client-choose-email' in contenu, (
                "L'ecran d'identification n'apparait pas pour un billet"
            )
            # Le titre doit contenir "Billetterie"
            # / The title must contain "Billetterie"
            assert 'Billetterie' in contenu or 'billetterie' in contenu, (
                f"Le titre 'Billetterie' manque dans la reponse"
            )

    def test_moyens_paiement_billet_plus_biere_declenche_identification(
        self, admin_user_billetterie, tenant, donnees_billetterie,
    ):
        """
        POST moyens_paiement avec biere + billet → ecran identification aussi.
        / POST moyens_paiement with beer + ticket → identification screen too.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client_billetterie(admin_user_billetterie, tenant)
            pv = donnees_billetterie['pv']
            event = donnees_billetterie['event']
            price_billet = donnees_billetterie['price_billet']
            product_biere = donnees_billetterie['product_biere']

            id_composite = f"{event.uuid}__{price_billet.uuid}"
            response = client.post('/laboutik/paiement/moyens_paiement/', data={
                'uuid_pv': str(pv.uuid),
                f'repid-{id_composite}': '1',
                f'repid-{product_biere.uuid}': '1',
            })

            assert response.status_code == 200
            contenu = response.content.decode()
            assert 'client-choose-nfc' in contenu or 'client-choose-email' in contenu

    def test_identifier_client_email_affiche_recap_billet(
        self, admin_user_billetterie, tenant, donnees_billetterie,
    ):
        """
        POST identifier_client avec email + repid billet → recapitulatif
        avec description "Billet ... — ..." dans les articles.
        / POST identifier_client with email + ticket repid → recap
        with "Billet ... — ..." description in articles.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client_billetterie(admin_user_billetterie, tenant)
            pv = donnees_billetterie['pv']
            event = donnees_billetterie['event']
            price = donnees_billetterie['price_billet']

            id_composite = f"{event.uuid}__{price.uuid}"
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'uuid_pv': str(pv.uuid),
                'email_adhesion': 'billet-http-test@tibillet.localhost',
                'prenom_adhesion': 'Test',
                'nom_adhesion': 'Billet',
                'panier_a_recharges': 'False',
                'panier_a_adhesions': 'False',
                'panier_a_billets': 'True',
                'moyens_paiement': 'espece,carte_bancaire',
                f'repid-{id_composite}': '1',
            })

            assert response.status_code == 200
            contenu = response.content.decode()

            # Le recapitulatif doit contenir "Billet" dans la description
            # / The recap must contain "Billet" in the description
            assert 'Billet' in contenu or 'billet' in contenu, (
                f"Le mot 'Billet' manque dans le recapitulatif"
            )
            # Le recapitulatif doit contenir le nom de l'event
            # / The recap must contain the event name
            assert event.name in contenu or 'client-recapitulatif' in contenu, (
                f"Le nom de l'event '{event.name}' manque dans le recapitulatif"
            )
            # Les boutons de paiement doivent etre presents
            # / Payment buttons must be present
            assert 'client-btn-especes' in contenu or 'espece' in contenu.lower()

    def test_payer_especes_cree_reservation_et_ticket(
        self, admin_user_billetterie, tenant, donnees_billetterie,
    ):
        """
        POST payer en especes avec billet → Reservation(status=V) + Ticket(status=K) en DB.
        / POST pay cash with ticket → Reservation(status=V) + Ticket(status=K) in DB.

        FLUX complet :
        1. POST /laboutik/paiement/payer/ avec repid-{event__price}, email, moyen=espece
        2. Verifier response 200 + "succes" ou "reussi"
        3. Verifier Reservation + Ticket en DB
        """
        from BaseBillet.models import Reservation, Ticket, LigneArticle

        with schema_context(TENANT_SCHEMA):
            client = _make_client_billetterie(admin_user_billetterie, tenant)
            pv = donnees_billetterie['pv']
            event = donnees_billetterie['event']
            price = donnees_billetterie['price_billet']
            prix_centimes = int(round(price.prix * 100))

            id_composite = f"{event.uuid}__{price.uuid}"
            response = client.post('/laboutik/paiement/payer/', data={
                'uuid_pv': str(pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes),
                'given_sum': '0',
                'email_adhesion': 'billet-payer-test@tibillet.localhost',
                'prenom_adhesion': 'Payer',
                'nom_adhesion': 'Test',
                f'repid-{id_composite}': '1',
            })

            assert response.status_code == 200
            contenu = response.content.decode()
            # L'ecran de succes doit apparaitre (pas un message d'erreur)
            # / The success screen must appear (not an error message)
            assert 'ussi' in contenu.lower() or 'success' in contenu.lower(), (
                f"Le paiement n'a pas reussi. Contenu : {contenu[:300]}"
            )

            # Verifier en DB : Reservation creee
            # / Verify in DB: Reservation created
            from AuthBillet.models import TibilletUser
            user_payer = TibilletUser.objects.filter(
                email='billet-payer-test@tibillet.localhost',
            ).first()
            assert user_payer is not None, "User billet-payer-test non cree"

            reservation = Reservation.objects.filter(
                user_commande=user_payer,
                event=event,
            ).order_by('-datetime').first()
            assert reservation is not None, "Reservation non creee"
            assert reservation.status == Reservation.VALID
            assert reservation.to_mail is True

            # Verifier en DB : Ticket cree avec status NOT_SCANNED
            # / Verify in DB: Ticket created with NOT_SCANNED status
            tickets = Ticket.objects.filter(reservation=reservation)
            assert tickets.count() == 1, f"Attendu 1 Ticket, trouve {tickets.count()}"
            ticket = tickets.first()
            assert ticket.status == Ticket.NOT_SCANNED

            # Verifier la LigneArticle liee a la reservation
            # / Verify the LigneArticle linked to the reservation
            ligne = LigneArticle.objects.filter(reservation=reservation).first()
            assert ligne is not None, "LigneArticle non liee a la reservation"
            assert ligne.amount == prix_centimes
            assert ligne.sale_origin == 'LB'

            # Nettoyage (ordre FK : LigneArticle → Ticket → Reservation)
            # / Cleanup (FK order: LigneArticle → Ticket → Reservation)
            LigneArticle.objects.filter(reservation=reservation).delete()
            # Supprimer aussi les LigneArticle sans reservation (biere dans paniers mixtes)
            # / Also delete LigneArticle without reservation (beer in mixed carts)
            LigneArticle.objects.filter(
                pricesold__productsold__product__name__startswith=TEST_PREFIX,
                reservation__isnull=True,
            ).delete()
            tickets.delete()
            reservation.delete()
