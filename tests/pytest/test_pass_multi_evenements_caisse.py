"""
Tests du pass multi-événements vendu à la caisse LaBoutik.
/ Multi-event pass sold at the LaBoutik register.

LOCALISATION : tests/pytest/test_pass_multi_evenements_caisse.py

LA RÈGLE TESTÉE
Un pass vendu au comptoir (tuile billet d'un événement du pass) est déplié en un
article par événement, au prix de sa ligne dans le pass (laboutik/views.py,
_deplier_l_article_pass). La vente a donc une ligne par événement. Chaque événement
reçoit sa réservation, son billet et sa ligne, et les billets d'un même pass portent
le même identifiant (`Ticket.pass_vendu`).
/ A pass sold at the register becomes one article per event, at its line price: one
line, one reservation and one ticket per event, all sharing the pass id.

Schéma dédié : `test_pass_caisse`. Les données viennent de DonneesBilletterieMixin
(tests/pytest/test_billetterie_pos.py) : un PointDeVente BILLETTERIE et un admin connecté.
/ Dedicated schema; data from DonneesBilletterieMixin.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_pass_multi_evenements_caisse.py -q
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase

from test_billetterie_pos import TEST_PREFIX, DonneesBilletterieMixin


@pytest.fixture(autouse=True, scope="session")
def _inject_cli_env():
    """Remplace la fixture du conftest, qui crée en base une clé API et un superutilisateur
    à chaque lancement. Aucun test de ce fichier n'appelle l'API.
    / Overrides the conftest fixture, which creates an API key and a superuser per run."""


class TestPassVenduEnCaisse(DonneesBilletterieMixin, FastTenantTestCase):
    """
    Un pass samedi (12 €) + dimanche (13 €) vendu en espèces à la caisse.
    / A Saturday (12 €) + Sunday (13 €) pass sold in cash at the register.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_pass_caisse"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-pass-caisse.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test pass caisse"

    def setUp(self):
        from BaseBillet.models import EvenementDuPass, Event, Price, Product

        super().setUp()

        # Le samedi est l'événement du mixin. On ajoute le dimanche, et le pass.
        # / Saturday is the mixin's event. Add Sunday and the pass.
        self.samedi = self.event
        self.dimanche = Event.objects.create(
            name=f"{TEST_PREFIX} Festival Rock dimanche",
            datetime=timezone.now() + timedelta(days=8),
            jauge_max=10,
            published=True,
        )
        self.produit_pass = Product.objects.create(
            name=f"{TEST_PREFIX} Pass week-end",
            categorie_article=Product.BILLET,
            publish=True,
            est_un_pass=True,
        )
        EvenementDuPass.objects.create(produit=self.produit_pass, evenement=self.samedi, prix=Decimal("12.00"))
        EvenementDuPass.objects.create(produit=self.produit_pass, evenement=self.dimanche, prix=Decimal("13.00"))
        self.samedi.products.add(self.produit_pass)
        self.dimanche.products.add(self.produit_pass)
        self.tarif_pass = Price.objects.create(
            product=self.produit_pass,
            name=f"{TEST_PREFIX} Pass 2 jours",
            prix=Decimal("25.00"),
            publish=True,
        )

    def payer_le_pass_en_especes(self, email_client):
        """
        Le POST de la caisse : 1 pass, depuis la tuile du samedi, payé en espèces.
        / The register POST: 1 pass from Saturday's tile, paid in cash.
        """
        id_composite = f"{self.samedi.uuid}__{self.tarif_pass.uuid}"
        return self.client_http.post(
            "/laboutik/paiement/payer/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "moyen_paiement": "espece",
                "total": "2500",
                "given_sum": "0",
                "email_adhesion": email_client,
                "prenom_adhesion": "Pass",
                "nom_adhesion": "Caisse",
                f"repid-{id_composite}": "1",
            },
        )

    def test_pass_vendu_en_caisse_cree_un_billet_par_jour_avec_le_meme_identifiant(self):
        """Un pass vendu : un billet le samedi, un le dimanche, même identifiant de pass.
        / One pass sold: one ticket per day, same pass id."""
        from BaseBillet.models import Ticket

        reponse = self.payer_le_pass_en_especes("pass-caisse-1@tibillet.localhost")

        assert reponse.status_code == 200
        billet_du_samedi = Ticket.objects.get(reservation__event=self.samedi, pricesold__price=self.tarif_pass)
        billet_du_dimanche = Ticket.objects.get(reservation__event=self.dimanche, pricesold__price=self.tarif_pass)
        assert billet_du_samedi.pass_vendu is not None
        assert billet_du_samedi.pass_vendu == billet_du_dimanche.pass_vendu

    def test_chaque_jour_du_pass_a_sa_ligne_de_vente_et_son_prix(self):
        """
        La vente a une ligne à 12 € rattachée au samedi et une à 13 € rattachée au
        dimanche. Chaque billet est photographié au prix de sa ligne.
        / One 12 € line on Saturday, one 13 € line on Sunday; ticket prices match.
        """
        from BaseBillet.models import LigneArticle, Reservation

        self.payer_le_pass_en_especes("pass-caisse-2@tibillet.localhost")

        reservation_du_samedi = Reservation.objects.get(event=self.samedi, tickets__pricesold__price=self.tarif_pass)
        reservation_du_dimanche = Reservation.objects.get(event=self.dimanche, tickets__pricesold__price=self.tarif_pass)
        assert LigneArticle.objects.get(reservation=reservation_du_samedi).amount == 1200
        assert LigneArticle.objects.get(reservation=reservation_du_dimanche).amount == 1300
        assert reservation_du_samedi.tickets.get().pricesold.prix == Decimal("12.00")
        assert reservation_du_dimanche.tickets.get().pricesold.prix == Decimal("13.00")

    def test_pass_vendu_en_caisse_le_premier_jour_apres_le_debut(self):
        """
        Le samedi a commencé il y a une heure : au comptoir, le pass se vend encore
        (vente à l'entrée). Un billet est créé sur chaque jour.
        / Saturday started an hour ago: the register still sells the pass.
        """
        from BaseBillet.models import Ticket

        self.samedi.datetime = timezone.now() - timedelta(hours=1)
        self.samedi.end_datetime = timezone.now() + timedelta(hours=5)
        self.samedi.save()

        self.payer_le_pass_en_especes("pass-caisse-3@tibillet.localhost")

        assert Ticket.objects.filter(pricesold__price=self.tarif_pass, reservation__event=self.samedi).count() == 1
        assert Ticket.objects.filter(pricesold__price=self.tarif_pass, reservation__event=self.dimanche).count() == 1

    def test_pass_refuse_en_caisse_quand_le_premier_jour_est_termine(self):
        """Le samedi est terminé : le pass n'est plus vendu, aucun billet n'est créé.
        / Saturday is over: the pass is refused, no ticket created."""
        from BaseBillet.models import Ticket

        self.samedi.datetime = timezone.now() - timedelta(hours=30)
        self.samedi.end_datetime = timezone.now() - timedelta(hours=20)
        self.samedi.save()

        reponse = self.payer_le_pass_en_especes("pass-caisse-5@tibillet.localhost")

        assert "plus disponible" in reponse.content.decode()
        assert not Ticket.objects.filter(pricesold__price=self.tarif_pass).exists()

    def test_pass_refuse_en_caisse_quand_le_stock_de_passes_est_epuise(self):
        """
        Stock de 1 pass, déjà vendu. Le premier jour a commencé : le second pass est
        refusé quand même, à cause du stock.
        / Stock of 1 pass already sold: the second one is refused, even on day one.
        """
        from BaseBillet.models import Ticket

        self.tarif_pass.stock = 1
        self.tarif_pass.save()
        self.samedi.datetime = timezone.now() - timedelta(hours=1)
        self.samedi.end_datetime = timezone.now() + timedelta(hours=5)
        self.samedi.save()
        self.payer_le_pass_en_especes("pass-caisse-6@tibillet.localhost")

        reponse = self.payer_le_pass_en_especes("pass-caisse-7@tibillet.localhost")

        assert "Plus de pass" in reponse.content.decode()
        assert Ticket.objects.filter(pricesold__price=self.tarif_pass, reservation__event=self.samedi).count() == 1
        assert Ticket.objects.filter(pricesold__price=self.tarif_pass, reservation__event=self.dimanche).count() == 1

    def test_billet_normal_en_caisse_garde_sa_ligne(self):
        """
        Un billet normal vendu en caisse garde le comportement d'avant : une réservation,
        un billet sans identifiant de pass, sa ligne rattachée.
        / A normal ticket keeps its previous behaviour.
        """
        from BaseBillet.models import LigneArticle, Reservation

        id_composite = f"{self.event.uuid}__{self.price_billet.uuid}"
        self.client_http.post(
            "/laboutik/paiement/payer/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "moyen_paiement": "espece",
                "total": "1500",
                "given_sum": "0",
                "email_adhesion": "billet-normal-caisse@tibillet.localhost",
                "prenom_adhesion": "Billet",
                "nom_adhesion": "Normal",
                f"repid-{id_composite}": "1",
            },
        )

        reservation = Reservation.objects.get(event=self.event, tickets__pricesold__price=self.price_billet)
        assert reservation.tickets.get().pass_vendu is None
        assert LigneArticle.objects.get(reservation=reservation).amount == 1500

    def test_annulation_admin_d_un_pass_vendu_en_caisse_rembourse_les_deux_jours(self):
        """
        L'admin annule le billet du samedi d'un pass vendu au comptoir, en rendant des
        espèces : les deux jours sont annulés et il ne reste rien de payé sur aucun.
        / Admin cancels a register-sold pass: both days cancelled, nothing left paid.
        """
        from BaseBillet.models import PaymentMethod, Reservation, Ticket

        self.payer_le_pass_en_especes("pass-caisse-4@tibillet.localhost")
        reservation_du_samedi = Reservation.objects.get(event=self.samedi, tickets__pricesold__price=self.tarif_pass)
        reservation_du_dimanche = Reservation.objects.get(event=self.dimanche, tickets__pricesold__price=self.tarif_pass)
        assert reservation_du_samedi.total_paid() == Decimal("12.00")
        assert reservation_du_dimanche.total_paid() == Decimal("13.00")

        reservation_du_samedi.cancel_and_refund_ticket(
            reservation_du_samedi.tickets.get(),
            annulation_par_l_admin=True,
            moyen_rembourse=PaymentMethod.CASH,
        )

        assert reservation_du_samedi.total_paid() == 0
        assert reservation_du_dimanche.total_paid() == 0
        assert reservation_du_dimanche.tickets.get().status == Ticket.CANCELED

    def test_pass_a_prix_libre_vendu_en_caisse_repartit_le_montant(self):
        """
        Pass 12 € + 13 € à prix libre, 30 € saisis au comptoir : le samedi reçoit 14,50 € et
        le dimanche 15,50 € (minimum + la moitié des 5 € de reste).
        / Free-price pass sold 30 at the register: 14.50 and 15.50.
        """
        from BaseBillet.models import LigneArticle, Reservation

        self.tarif_pass.free_price = True
        self.tarif_pass.save()
        id_composite = f"{self.samedi.uuid}__{self.tarif_pass.uuid}"

        self.client_http.post(
            "/laboutik/paiement/payer/",
            data={
                "uuid_pv": str(self.pv.uuid),
                "moyen_paiement": "espece",
                "total": "3000",
                "given_sum": "0",
                "email_adhesion": "pass-caisse-libre@tibillet.localhost",
                "prenom_adhesion": "Pass",
                "nom_adhesion": "Libre",
                f"repid-{id_composite}": "1",
                f"custom-{id_composite}": "3000",
            },
        )

        reservation_du_samedi = Reservation.objects.get(event=self.samedi, tickets__pricesold__price=self.tarif_pass)
        reservation_du_dimanche = Reservation.objects.get(event=self.dimanche, tickets__pricesold__price=self.tarif_pass)
        assert LigneArticle.objects.get(reservation=reservation_du_samedi).amount == 1450
        assert LigneArticle.objects.get(reservation=reservation_du_dimanche).amount == 1550
        assert reservation_du_dimanche.tickets.get().pricesold.prix == Decimal("15.50")
