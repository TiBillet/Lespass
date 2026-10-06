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
  - Le flow HTTP complet : moyens_paiement → identifier_client → payer
  - Le billet a 0 € (bouton VALIDER, moyen « gift »)

SCHEMA DEDIE / DEDICATED SCHEMA
Ces tests tournent dans un schema a eux (`FastTenantTestCase`), jamais sur le lieu
`lespass` de la base de dev. Chaque test annule sa transaction a la fin : il ne
supprime rien lui-meme. Avant, le nettoyage supprimait par queryset les articles de
ventes REGLEES du lieu `lespass` : la vente et son reglement restaient sans article
(egalite rompue, empreinte fausse, rapports faux). Un article d'une vente reglee ne se
supprime jamais (garde `pre_delete` de `LigneArticle`, BaseBillet/models.py).
/ These tests run in their own schema, never on the dev `lespass` venue. Each test is
rolled back: it deletes nothing itself. The old cleanup deleted items of SETTLED sales
of the `lespass` venue, which broke their equalities and fingerprints.

Lancement / Run:
    make test ARGS="tests/pytest/test_billetterie_pos.py"
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.db import connection
from django.db import transaction as db_transaction
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient


# Prefixe des noms des donnees de ce module (lisibles dans les messages d'erreur).
# / Prefix of this module's data names (readable in error messages).
TEST_PREFIX = "zz_test_billetterie"


# ---------------------------------------------------------------------------
# Donnees communes a toutes les classes
# / Data shared by every class
# ---------------------------------------------------------------------------


class DonneesBilletterieMixin:
    """
    Le schema dedie et les donnees de chaque test : un Event futur + un Product
    BILLET + son Price, un Product biere + son Price, un PointDeVente BILLETTERIE,
    un client et un admin connecte.
    / The dedicated schema and each test's data: a future Event + BILLET Product +
    Price, a beer Product + Price, a BILLETTERIE PointDeVente, a client and a
    logged-in admin.

    Toutes les classes du fichier partagent le meme schema (`test_billetterie_pos`).
    `setUp` recree les donnees a chaque test : le rollback du test precedent les a
    effacees.
    / Every class shares the same schema. setUp recreates the data for each test:
    the previous test's rollback erased them.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_billetterie_pos"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-billetterie-pos.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test billetterie POS"

    def setUp(self):
        from AuthBillet.models import TibilletUser
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.models import Configuration, Event, Price, Product
        from laboutik.models import LaboutikConfiguration, PointDeVente

        # Le rollback du test precedent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Active la caisse V2 (le garde HasLaBoutikTerminalAccess l'exige).
        # module_caisse exige module_monnaie_locale : on active les deux.
        # / Enable V2 POS (required by the HasLaBoutikTerminalAccess guard).
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.save()

        # Le singleton de la caisse porte la cle de l'empreinte des ventes (PIEGES 9.86).
        # / The register singleton holds the sales fingerprint key.
        LaboutikConfiguration.get_solo().save()

        # Le Product billet et son Price
        # / The ticket Product and its Price
        self.product_billet = Product.objects.create(
            name=f"{TEST_PREFIX} Concert Rock",
            categorie_article=Product.BILLET,
            publish=True,
        )
        self.price_billet = Price.objects.create(
            product=self.product_billet,
            name=f"{TEST_PREFIX} Plein tarif",
            prix=Decimal("15.00"),
            publish=True,
        )

        # L'Event futur, jauge a 10
        # / The future Event, gauge at 10
        self.event = Event.objects.create(
            name=f"{TEST_PREFIX} Festival Rock",
            datetime=timezone.now() + timedelta(days=7),
            jauge_max=10,
            published=True,
        )
        self.event.products.add(self.product_billet)

        # Un Product biere standard (pour les paniers mixtes)
        # / A standard beer Product (for mixed carts)
        self.product_biere = Product.objects.create(
            name=f"{TEST_PREFIX} Biere",
            categorie_article=Product.NONE,
            methode_caisse=Product.VENTE,
            publish=True,
        )
        self.price_biere = Price.objects.create(
            product=self.product_biere,
            name=f"{TEST_PREFIX} Biere prix",
            prix=Decimal("5.00"),
            publish=True,
        )

        # Le PointDeVente BILLETTERIE
        # / The BILLETTERIE PointDeVente
        self.pv = PointDeVente.objects.create(
            name=f"{TEST_PREFIX} Accueil",
            comportement=PointDeVente.BILLETTERIE,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            poid_liste=9999,
        )
        self.pv.products.add(self.product_biere)

        # Le client des billets (schema public, annule lui aussi par le rollback)
        # / The ticket client (public schema, rolled back too)
        self.user_client = get_or_create_user(
            f"{TEST_PREFIX.lower()}@test.local", send_mail=False
        )
        if not self.user_client.first_name:
            self.user_client.first_name = "Test"
            self.user_client.last_name = "Billet"
            self.user_client.save(update_fields=["first_name", "last_name"])

        # L'admin du lieu et son client HTTP connecte
        # / The venue admin and its logged-in HTTP client
        email_admin = "admin-test-billetterie@tibillet.localhost"
        self.admin_user, _admin_cree = TibilletUser.objects.get_or_create(
            email=email_admin,
            defaults={
                "username": email_admin,
                "is_staff": True,
                "is_active": True,
            },
        )
        self.admin_user.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.admin_user)

    def carte_du_client(self):
        """
        La carte NFC qui identifie le client (`tag_id` BTST0001).
        / The NFC card identifying the client.
        """
        from QrcodeCashless.models import CarteCashless

        carte, _carte_creee = CarteCashless.objects.get_or_create(
            tag_id="BTST0001",
            defaults={"number": "BTST0001", "user": self.user_client},
        )
        if carte.user != self.user_client:
            carte.user = self.user_client
            carte.save(update_fields=["user"])
        return carte

    def requete_especes_avec_carte(self):
        """
        Une requete POST simulee : paiement especes, client identifie par sa carte.
        / A simulated POST request: cash payment, client identified by card.
        """
        request = MagicMock()
        request.POST = {
            "tag_id": "BTST0001",
            "moyen_paiement": "espece",
        }
        request.META = {"REMOTE_ADDR": "127.0.0.1"}
        return request

    def article_billet(self, quantite=1):
        """
        L'article « billet plein tarif » d'un panier.
        / The "full price ticket" cart item.
        """
        return {
            "product": self.product_billet,
            "price": self.price_billet,
            "quantite": quantite,
            "prix_centimes": 1500,
            "custom_amount_centimes": None,
            "est_billet": True,
            "event": self.event,
        }

    def remplir_avec_des_tickets(self, nombre_de_tickets):
        """
        Cree une Reservation VALID et `nombre_de_tickets` tickets non scannes.
        / Creates a VALID Reservation and `nombre_de_tickets` unscanned tickets.
        """
        from BaseBillet.models import PriceSold, ProductSold, Reservation, Ticket

        reservation = Reservation.objects.create(
            user_commande=self.user_client,
            event=self.event,
            status=Reservation.VALID,
        )
        produit_vendu, _produit_vendu_cree = ProductSold.objects.get_or_create(
            product=self.product_billet,
            event=self.event,
            defaults={"categorie_article": self.product_billet.categorie_article},
        )
        tarif_vendu, _tarif_vendu_cree = PriceSold.objects.get_or_create(
            productsold=produit_vendu,
            price=self.price_billet,
            defaults={"prix": self.price_billet.prix},
        )
        for _numero_du_ticket in range(nombre_de_tickets):
            Ticket.objects.create(
                reservation=reservation,
                pricesold=tarif_vendu,
                status=Ticket.NOT_SCANNED,
            )
        return reservation


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtraireArticlesBilletterie(DonneesBilletterieMixin, FastTenantTestCase):
    """Tests de _extraire_articles_du_panier pour les articles BILLETTERIE."""

    def test_extraire_article_billet_id_composite(self):
        """
        POST avec repid-{event_uuid}__{price_uuid} → article trouve
        avec est_billet=True et event correct.
        / POST with repid-{event_uuid}__{price_uuid} → article found
        with est_billet=True and correct event.
        """
        from laboutik.views import _extraire_articles_du_panier

        # Simuler le POST avec l'ID composite
        # / Simulate POST with composite ID
        id_composite = f"{self.event.uuid}__{self.price_billet.uuid}"
        post_data = {
            f"repid-{id_composite}": "2",
        }

        articles = _extraire_articles_du_panier(post_data, self.pv)

        assert len(articles) == 1
        article = articles[0]
        assert article["est_billet"] is True
        assert article["event"] is not None
        assert str(article["event"].uuid) == str(self.event.uuid)
        assert article["product"] == self.product_billet
        assert article["price"] == self.price_billet
        assert article["quantite"] == 2
        assert article["prix_centimes"] == 1500

    def test_extraire_article_standard_dans_pv_billetterie(self):
        """
        Un article standard (biere) dans un PV BILLETTERIE est extrait normalement.
        / A standard article (beer) in a BILLETTERIE PV is extracted normally.
        """
        from laboutik.views import _extraire_articles_du_panier

        post_data = {
            f"repid-{self.product_biere.uuid}": "1",
        }

        articles = _extraire_articles_du_panier(post_data, self.pv)

        assert len(articles) == 1
        article = articles[0]
        assert article["est_billet"] is False
        assert article["event"] is None
        assert article["product"] == self.product_biere


class TestCreerBilletDepuisPanier(DonneesBilletterieMixin, FastTenantTestCase):
    """Tests de _creer_billets_depuis_panier."""

    def test_creer_billet_espece_sans_email(self):
        """
        Paiement especes avec tag_id → Reservation VALID + Ticket NOT_SCANNED, to_mail=False.
        / Cash payment with tag_id → Reservation VALID + Ticket NOT_SCANNED, to_mail=False.
        """
        from BaseBillet.models import Reservation, Ticket
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles

        # Creer/recuperer une carte NFC pour l'identification
        # / Create/get an NFC card for identification
        self.carte_du_client()
        articles_panier = [self.article_billet()]
        request = self.requete_especes_avec_carte()

        with db_transaction.atomic():
            lignes, _produits_en_stock_negatif = _creer_lignes_articles(
                articles_panier, "espece"
            )
            reservations = _creer_billets_depuis_panier(
                request,
                articles_panier,
                lignes_articles=lignes,
            )

        assert len(reservations) == 1
        reservation = reservations[0]
        assert reservation.status == Reservation.VALID
        assert reservation.to_mail is False
        assert reservation.user_commande == self.user_client
        assert reservation.event == self.event

        tickets = Ticket.objects.filter(reservation=reservation)
        assert tickets.count() == 1
        ticket = tickets.first()
        assert ticket.status == Ticket.NOT_SCANNED

    def test_creer_billet_avec_email(self):
        """
        Paiement avec email → to_mail=True, user cree.
        / Payment with email → to_mail=True, user created.
        """
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles

        articles_panier = [self.article_billet()]

        request = MagicMock()
        request.POST = {
            "email_adhesion": f"{TEST_PREFIX.lower()}email@test.local",
            "prenom_adhesion": "Alice",
            "nom_adhesion": "Dupont",
            "moyen_paiement": "carte_bancaire",
        }
        request.META = {"REMOTE_ADDR": "127.0.0.1"}

        with db_transaction.atomic():
            lignes, _produits_en_stock_negatif = _creer_lignes_articles(
                articles_panier, "carte_bancaire"
            )
            reservations = _creer_billets_depuis_panier(
                request,
                articles_panier,
                lignes_articles=lignes,
            )

        assert len(reservations) == 1
        reservation = reservations[0]
        assert reservation.to_mail is True

    def test_jauge_bloque_vente(self):
        """
        Jauge pleine → ValueError levee, aucun Ticket cree (rollback).
        / Full gauge → ValueError raised, no Ticket created (rollback).
        """
        from BaseBillet.models import Ticket
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles

        # Remplir la jauge : creer 10 tickets (jauge_max=10)
        # / Fill the gauge: create 10 tickets (jauge_max=10)
        self.remplir_avec_des_tickets(10)

        # Tenter d'acheter un billet de plus → ValueError
        # / Try to buy one more ticket → ValueError
        articles_panier = [self.article_billet()]
        self.carte_du_client()
        request = self.requete_especes_avec_carte()

        with pytest.raises(ValueError, match="complet"):
            with db_transaction.atomic():
                lignes, _produits_en_stock_negatif = _creer_lignes_articles(
                    articles_panier, "espece"
                )
                _creer_billets_depuis_panier(
                    request,
                    articles_panier,
                    lignes_articles=lignes,
                )

        # Verifier qu'aucun nouveau ticket n'a ete cree (rollback)
        # / Verify no new ticket was created (rollback)
        assert Ticket.objects.filter(reservation__event=self.event).count() == 10

    def test_ticket_status_not_scanned(self):
        """
        Le Ticket cree a status='K' (NOT_SCANNED).
        / The created Ticket has status='K' (NOT_SCANNED).
        """
        from BaseBillet.models import Ticket
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles

        self.carte_du_client()
        articles_panier = [self.article_billet(quantite=3)]
        request = self.requete_especes_avec_carte()

        with db_transaction.atomic():
            lignes, _produits_en_stock_negatif = _creer_lignes_articles(
                articles_panier, "espece"
            )
            reservations = _creer_billets_depuis_panier(
                request,
                articles_panier,
                lignes_articles=lignes,
            )

        tickets = Ticket.objects.filter(reservation=reservations[0])
        assert tickets.count() == 3
        for ticket in tickets:
            assert ticket.status == "K"
            assert ticket.status == Ticket.NOT_SCANNED

    def test_panier_mixte_billet_et_vente(self):
        """
        Biere + Billet → 2 LigneArticle, 1 Ticket pour le billet.
        / Beer + Ticket → 2 LigneArticle, 1 Ticket for the ticket.
        """
        from BaseBillet.models import Ticket
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles

        self.carte_du_client()
        articles_panier = [
            {
                "product": self.product_biere,
                "price": self.price_biere,
                "quantite": 1,
                "prix_centimes": 500,
                "custom_amount_centimes": None,
                "est_billet": False,
                "event": None,
            },
            self.article_billet(),
        ]
        request = self.requete_especes_avec_carte()

        with db_transaction.atomic():
            lignes, _produits_en_stock_negatif = _creer_lignes_articles(
                articles_panier, "espece"
            )
            reservations = _creer_billets_depuis_panier(
                request,
                articles_panier,
                lignes_articles=lignes,
            )

        # 2 LigneArticle creees (biere + billet)
        # / 2 LigneArticle created (beer + ticket)
        assert len(lignes) == 2

        # 1 Reservation + 1 Ticket pour le billet
        # / 1 Reservation + 1 Ticket for the ticket
        assert len(reservations) == 1
        tickets = Ticket.objects.filter(reservation=reservations[0])
        assert tickets.count() == 1

    def test_jauge_price_stock(self):
        """
        Price.stock=2, 2 tickets existants → ValueError au 3e billet.
        / Price.stock=2, 2 existing tickets → ValueError on 3rd ticket.
        """
        from laboutik.views import _creer_billets_depuis_panier, _creer_lignes_articles

        # Mettre un stock de 2 sur la Price
        # / Set stock to 2 on the Price
        self.price_billet.stock = 2
        self.price_billet.save(update_fields=["stock"])

        # Creer 2 tickets existants
        # / Create 2 existing tickets
        self.remplir_avec_des_tickets(2)

        self.carte_du_client()
        articles_panier = [self.article_billet()]
        request = self.requete_especes_avec_carte()

        with pytest.raises(ValueError, match="tarif"):
            with db_transaction.atomic():
                lignes, _produits_en_stock_negatif = _creer_lignes_articles(
                    articles_panier, "espece"
                )
                _creer_billets_depuis_panier(
                    request,
                    articles_panier,
                    lignes_articles=lignes,
                )


# ===========================================================================
# PARTIE 3 — Tests HTTP du flow complet billetterie
# Testent le vrai chemin POST : moyens_paiement → identifier_client → payer.
# Utilisent le client HTTP du lieu de test (TenantClient, pas de MagicMock).
# / PART 3 — HTTP tests for the full ticketing flow.
# Test the real POST path: moyens_paiement → identifier_client → payer.
# Use the test venue's HTTP client (TenantClient, no MagicMock).
# ===========================================================================


class TestBilletterieFlowHTTP(DonneesBilletterieMixin, FastTenantTestCase):
    """Tests HTTP du flow complet billetterie sur le lieu de test.
    / HTTP tests for the full ticketing flow on the test venue.

    FLUX teste :
    1. POST moyens_paiement avec repid-{event_uuid}__{price_uuid}
       → reponse contient "Billetterie" et ecran identification
    2. POST identifier_client avec email
       → reponse contient recapitulatif avec "Billet" dans la description
    3. POST payer en especes
       → reponse succes + Reservation + Ticket en DB
    """

    def test_moyens_paiement_billet_declenche_identification(self):
        """
        POST moyens_paiement avec un billet → ecran identification
        avec titre "Billetterie" et boutons NFC + email.
        / POST moyens_paiement with a ticket → identification screen
        with "Billetterie" title and NFC + email buttons.
        """
        # POST avec l'ID composite event__price (comme le JS l'envoie)
        # / POST with composite event__price ID (as the JS sends it)
        id_composite = f"{self.event.uuid}__{self.price_billet.uuid}"
        response = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.pv.uuid),
                f"repid-{id_composite}": "1",
            },
        )

        assert response.status_code == 200
        contenu = response.content.decode()

        # L'ecran d'identification doit apparaitre (pas les boutons de paiement directs)
        # / The identification screen must appear (not direct payment buttons)
        assert "client-choose-nfc" in contenu or "client-choose-email" in contenu, (
            "L'ecran d'identification n'apparait pas pour un billet"
        )
        # Le titre doit contenir "Billetterie"
        # / The title must contain "Billetterie"
        assert "Billetterie" in contenu or "billetterie" in contenu, (
            "Le titre 'Billetterie' manque dans la reponse"
        )

    def test_moyens_paiement_billet_plus_biere_declenche_identification(self):
        """
        POST moyens_paiement avec biere + billet → ecran identification aussi.
        / POST moyens_paiement with beer + ticket → identification screen too.
        """
        id_composite = f"{self.event.uuid}__{self.price_billet.uuid}"
        response = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.pv.uuid),
                f"repid-{id_composite}": "1",
                f"repid-{self.product_biere.uuid}": "1",
            },
        )

        assert response.status_code == 200
        contenu = response.content.decode()
        assert "client-choose-nfc" in contenu or "client-choose-email" in contenu

    def test_identifier_client_email_affiche_recap_billet(self):
        """
        POST identifier_client avec email + repid billet → recapitulatif
        avec description "Billet ... — ..." dans les articles.
        / POST identifier_client with email + ticket repid → recap
        with "Billet ... — ..." description in articles.
        """
        id_composite = f"{self.event.uuid}__{self.price_billet.uuid}"
        response = self.client_http.post(
            "/laboutik/paiement/identifier_client/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "email_adhesion": "billet-http-test@tibillet.localhost",
                "prenom_adhesion": "Test",
                "nom_adhesion": "Billet",
                "panier_a_recharges": "False",
                "panier_a_adhesions": "False",
                "panier_a_billets": "True",
                "moyens_paiement": "espece,carte_bancaire",
                f"repid-{id_composite}": "1",
            },
        )

        assert response.status_code == 200
        contenu = response.content.decode()

        # Le recapitulatif doit contenir "Billet" dans la description
        # / The recap must contain "Billet" in the description
        assert "Billet" in contenu or "billet" in contenu, (
            "Le mot 'Billet' manque dans le recapitulatif"
        )
        # Le recapitulatif doit contenir le nom de l'event
        # / The recap must contain the event name
        assert self.event.name in contenu or "client-recapitulatif" in contenu, (
            f"Le nom de l'event '{self.event.name}' manque dans le recapitulatif"
        )
        # Les boutons de paiement doivent etre presents
        # / Payment buttons must be present
        assert "paiement-btn-especes" in contenu or "espece" in contenu.lower()

    def test_payer_especes_cree_reservation_et_ticket(self):
        """
        POST payer en especes avec billet → Reservation(status=V) + Ticket(status=K) en DB.
        / POST pay cash with ticket → Reservation(status=V) + Ticket(status=K) in DB.

        FLUX complet :
        1. POST /laboutik/paiement/payer/ avec repid-{event__price}, email, moyen=espece
        2. Verifier response 200 + "succes" ou "reussi"
        3. Verifier Reservation + Ticket en DB
        """
        from AuthBillet.models import TibilletUser
        from BaseBillet.models import LigneArticle, Reservation, Ticket

        prix_centimes = int(round(self.price_billet.prix * 100))
        id_composite = f"{self.event.uuid}__{self.price_billet.uuid}"
        response = self.client_http.post(
            "/laboutik/paiement/payer/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "moyen_paiement": "espece",
                "total": str(prix_centimes),
                "given_sum": "0",
                "email_adhesion": "billet-payer-test@tibillet.localhost",
                "prenom_adhesion": "Payer",
                "nom_adhesion": "Test",
                f"repid-{id_composite}": "1",
            },
        )

        assert response.status_code == 200
        contenu = response.content.decode()
        # L'ecran de succes doit apparaitre (pas un message d'erreur)
        # / The success screen must appear (not an error message)
        assert "ussi" in contenu.lower() or "success" in contenu.lower(), (
            f"Le paiement n'a pas reussi. Contenu : {contenu[:300]}"
        )

        # Verifier en DB : Reservation creee
        # / Verify in DB: Reservation created
        user_payer = TibilletUser.objects.filter(
            email="billet-payer-test@tibillet.localhost",
        ).first()
        assert user_payer is not None, "User billet-payer-test non cree"

        reservation = (
            Reservation.objects.filter(
                user_commande=user_payer,
                event=self.event,
            )
            .order_by("-datetime")
            .first()
        )
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
        assert ligne.sale_origin == "LB"


class TestBilletGratuit(DonneesBilletterieMixin, FastTenantTestCase):
    """
    Billet a 0 € : apres l'identification, pas de choix du moyen de paiement.
    Un seul bouton VALIDER envoie moyen_paiement=gift, enregistre « Offert ».
    / 0 € ticket: after identification, no payment choice. A single VALIDATE
    button sends moyen_paiement=gift, recorded as "Offered".
    """

    def setUp(self):
        """
        Les donnees communes, plus un tarif a 0 € sur le produit billet.
        / The shared data, plus a 0 € price on the ticket product.
        """
        from BaseBillet.models import Price

        super().setUp()
        self.tarif_billet_gratuit = Price.objects.create(
            product=self.product_billet,
            name=f"{TEST_PREFIX} Gratuit",
            prix=Decimal("0.00"),
            publish=True,
        )

    def test_identifier_client_panier_gratuit_affiche_seulement_valider(self):
        id_composite = f"{self.event.uuid}__{self.tarif_billet_gratuit.uuid}"

        response = self.client_http.post(
            "/laboutik/paiement/identifier_client/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "email_adhesion": "billet-gratuit-test@tibillet.localhost",
                "prenom_adhesion": "Gratuit",
                "nom_adhesion": "Test",
                "panier_a_billets": "True",
                "moyens_paiement": "espece,carte_bancaire",
                f"repid-{id_composite}": "1",
            },
        )

        assert response.status_code == 200
        contenu = response.content.decode()
        assert 'data-testid="client-recapitulatif"' in contenu
        assert 'data-testid="paiement-btn-gratuit"' in contenu
        assert 'data-testid="paiement-btn-especes"' not in contenu
        assert 'data-testid="paiement-btn-cb"' not in contenu

    def test_identifier_client_panier_payant_affiche_les_tuiles_avec_le_total(self):
        """
        Panier payant : les tuiles de la vente normale, et la tuile CB
        envoie le total a la popup de confirmation (plus de « 0 € »).
        / Paid cart: normal-sale tiles; the card tile passes the total.
        """
        id_composite = f"{self.event.uuid}__{self.price_billet.uuid}"

        response = self.client_http.post(
            "/laboutik/paiement/identifier_client/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "email_adhesion": "billet-http-test@tibillet.localhost",
                "prenom_adhesion": "Test",
                "nom_adhesion": "Billet",
                "panier_a_billets": "True",
                f"repid-{id_composite}": "1",
            },
        )

        contenu = response.content.decode()
        assert 'data-testid="paiement-btn-cb"' in contenu
        assert "method=carte_bancaire&total=15" in contenu
        assert 'data-testid="paiement-btn-gratuit"' not in contenu

    def test_payer_gift_panier_gratuit_cree_billet_offert(self):
        from AuthBillet.models import TibilletUser
        from BaseBillet.models import LigneArticle, PaymentMethod, Reservation, Ticket

        id_composite = f"{self.event.uuid}__{self.tarif_billet_gratuit.uuid}"

        response = self.client_http.post(
            "/laboutik/paiement/payer/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "moyen_paiement": "gift",
                "total": "0",
                "email_adhesion": "billet-gratuit-test@tibillet.localhost",
                "prenom_adhesion": "Gratuit",
                "nom_adhesion": "Test",
                f"repid-{id_composite}": "1",
            },
        )

        assert response.status_code == 200
        assert 'data-testid="paiement-succes"' in response.content.decode()

        user_gratuit = TibilletUser.objects.get(
            email="billet-gratuit-test@tibillet.localhost",
        )
        reservation = (
            Reservation.objects.filter(user_commande=user_gratuit, event=self.event)
            .order_by("-datetime")
            .first()
        )
        assert reservation is not None
        tickets = Ticket.objects.filter(reservation=reservation)
        assert tickets.count() == 1
        assert tickets.first().payment_method == PaymentMethod.FREE
        ligne = LigneArticle.objects.get(reservation=reservation)
        assert ligne.amount == 0
        # Le moyen est sur la vente (une vente gratuite n'a aucun règlement),
        # jamais sur la ligne (Q-H2).
        # / The method lives on the sale, never on the line (Q-H2).
        assert ligne.payment_method is None

    def test_payer_gift_panier_payant_est_refuse(self):
        """
        Un POST force « gift » sur un panier payant est refuse (400).
        / A forged "gift" POST on a paid cart is refused (400).
        """
        from BaseBillet.models import Reservation

        id_composite = f"{self.event.uuid}__{self.price_billet.uuid}"
        nombre_de_reservations_avant = Reservation.objects.filter(
            event=self.event
        ).count()

        response = self.client_http.post(
            "/laboutik/paiement/payer/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "moyen_paiement": "gift",
                "total": "0",
                "email_adhesion": "billet-gift-force@tibillet.localhost",
                "prenom_adhesion": "Force",
                "nom_adhesion": "Test",
                f"repid-{id_composite}": "1",
            },
        )

        assert response.status_code == 400
        assert (
            Reservation.objects.filter(event=self.event).count()
            == nombre_de_reservations_avant
        )
