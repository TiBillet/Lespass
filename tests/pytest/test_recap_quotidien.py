"""
tests/pytest/test_recap_quotidien.py
Le récap du matin des admins : un mail par lieu qui résume la veille.
/ The admins' morning recap: one mail per venue summarising yesterday.

LOCALISATION : tests/pytest/test_recap_quotidien.py

Spécification : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md

Dates de référence : le mardi 13 octobre 2026, heure de Paris (CEST, UTC+2).
« La veille » = lundi 12 octobre.
/ Reference date: Tuesday 13 October 2026, Paris time.

Lancer / Run : make test ARGS="tests/pytest/test_recap_quotidien.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import date, datetime, time, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.db import connection  # noqa: E402
from django.utils import timezone, translation  # noqa: E402
from django.template.loader import render_to_string  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.urls import reverse  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from Administration.admin.resources import BookingAdmin  # noqa: E402
from Administration.admin.site import staff_admin_site  # noqa: E402
from Administration.recap_quotidien import (  # noqa: E402
    _nom_de_l_objet_rembourse,
    clotures_j_a_joindre,
    destinataires_du_recap,
    envoyer_le_recap_du_lieu_si_c_est_l_heure,
    fenetre_de_la_veille,
    le_recap_a_du_contenu,
    rubriques_de_la_veille,
)
from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    Event,
    LigneArticle,
    Membership,
    PaymentMethod,
    PriceSold,
    Product,
    ProductSold,
    Reservation,
    SaleOrigin,
    Ticket,
)
from BaseBillet.services_vente import ecrire_la_vente_d_avoir_d_une_ligne  # noqa: E402
from booking.models import (  # noqa: E402
    BesoinBenevole,
    Booking,
    InscriptionBenevole,
    PlanningBenevole,
    TacheBenevole,
)
from fabriques_panier import (  # noqa: E402
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from crowds.models import (  # noqa: E402
    BudgetItem,
    Contribution,
    Initiative,
    Participation,
    Vote,
)
from fabriques_vente import creer_tarif_vendu, fabriquer_vente_encaissee  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from laboutik.models import LaboutikConfiguration  # noqa: E402
import comptabilite.tasks  # noqa: E402
from django.core.management import call_command  # noqa: E402
from io import StringIO  # noqa: E402

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")
FUSEAU_UTC = ZoneInfo("UTC")


def heure_de_paris(annee, mois, jour, heure, minute=0):
    """Un moment en heure de Paris. / A moment in Paris time."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_DE_PARIS)


def heure_utc(annee, mois, jour, heure, minute=0):
    """Un moment en UTC. / A moment in UTC."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_UTC)


class RecapQuotidienTestCase(FastTenantTestCase):
    """
    Base commune : le lieu de test et sa configuration réécrite à chaque test.
    / Common base: the test venue and its configuration rewritten in every test.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_recap_quotidien"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-recap-quotidien.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test recap quotidien"

    def setUp(self):
        """
        Le rollback du test précédent a rendu le `search_path` au public. Le cache
        de la configuration (django-solo) survit au rollback : on écrit ici toutes
        les valeurs lues par le récap, puis on sauvegarde.
        / Previous rollback reset search_path; the solo cache survives it, so every
        value read by the recap is written here, then saved.
        """
        connection.set_tenant(self.tenant)
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.language = "fr"
        configuration.rapport_emails = ""
        configuration.rapport_periodicite = Configuration.PERIODICITE_NONE
        configuration.email = "lieu@example.org"
        configuration.save()


class TestLesDatesDeCreation(RecapQuotidienTestCase):
    """
    Les champs de date qui rendent « créé hier » et « annulé hier » fiables.
    / The date fields that make "created yesterday" and "cancelled yesterday" reliable.
    """

    def _creer_une_reservation(self):
        utilisateur = creer_utilisateur()
        billetterie = creer_evenement_avec_tarif()
        return Reservation.objects.create(
            user_commande=utilisateur, event=billetterie.evenement
        )

    def test_une_reservation_garde_sa_date_de_creation_quand_on_la_modifie(self):
        # created_at est posé à la création, puis ne bouge plus.
        reservation = self._creer_une_reservation()
        date_de_creation = reservation.created_at
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 10, 14, 9)
        ):
            reservation.save()
        reservation.refresh_from_db()
        assert reservation.created_at is not None
        assert reservation.created_at == date_de_creation

    def test_un_evenement_garde_sa_date_de_creation_quand_on_le_modifie(self):
        evenement = creer_evenement_avec_tarif().evenement
        date_de_creation = evenement.created_at
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 10, 14, 9)
        ):
            evenement.save()
        evenement.refresh_from_db()
        assert evenement.created_at is not None
        assert evenement.created_at == date_de_creation

    def test_annulee_le_est_vide_a_la_creation(self):
        # Réservation, booking, adhésion : annulee_le vaut None tant que rien n'est annulé.
        reservation = self._creer_une_reservation()

        ressource = creer_ressource_avec_tarif()
        booking = Booking.objects.create(
            resource=ressource.ressource,
            user=creer_utilisateur(),
            start_datetime=ressource.debut_du_creneau,
            slot_duration_minutes=60,
            slot_count=1,
        )

        adhesion = creer_adhesion()
        membership = Membership.objects.create(price=adhesion.tarif, user=None)

        assert reservation.annulee_le is None
        assert booking.annulee_le is None
        assert membership.annulee_le is None

    def test_la_configuration_a_un_marqueur_de_recap_vide(self):
        # On lit le DÉFAUT DU CHAMP, jamais get_solo() : le schéma de test reste en base,
        # et la vraie tâche horaire de Celery passe aussi sur lui et pose le marqueur.
        # / Read the FIELD DEFAULT, never get_solo(): the real hourly task also visits
        # the persistent test schema and sets the marker.
        champ_du_marqueur = Configuration._meta.get_field("recap_quotidien_traite_le")
        assert champ_du_marqueur.get_default() is None


class TestAnnuleeLe(RecapQuotidienTestCase):
    """
    `annulee_le` est posé à chaque annulation voulue par une personne ou un admin,
    et PAS à l'annulation automatique ni à l'arrêt du renouvellement.
    L'arrêt du renouvellement (`ApiBillet/views.py`, `Membership.CANCELED`) ne pose
    pas `annulee_le` : ce n'est pas une annulation.
    / `annulee_le` is set on every deliberate cancellation, NOT on the automatic one
    nor on the end of a renewal (stopping a renewal is not a cancellation).
    """

    def _creer_une_reservation_gratuite_avec_un_billet(self, **champs_reservation):
        billetterie = creer_evenement_avec_tarif(prix="0.00")
        produit_vendu = ProductSold.objects.create(
            product=billetterie.produit, event=billetterie.evenement
        )
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=billetterie.tarif, prix=0
        )
        reservation = Reservation.objects.create(
            user_commande=creer_utilisateur(),
            event=billetterie.evenement,
            status=champs_reservation.pop("status", Reservation.VALID),
            **champs_reservation,
        )
        billet = Ticket.objects.create(
            reservation=reservation,
            pricesold=tarif_vendu,
            status=Ticket.NOT_SCANNED,
        )
        return reservation, billet

    def _creer_un_booking(self):
        ressource = creer_ressource_avec_tarif()
        return Booking.objects.create(
            resource=ressource.ressource,
            user=creer_utilisateur(),
            start_datetime=ressource.debut_du_creneau,
            slot_duration_minutes=60,
            slot_count=1,
            status=Booking.WAITING_PAYMENT,
        )

    def test_annuler_une_reservation_pose_annulee_le(self):
        moment = heure_de_paris(2026, 10, 13, 8, 10)
        reservation, _billet = self._creer_une_reservation_gratuite_avec_un_billet()
        with patch("django.utils.timezone.now", return_value=moment):
            reservation.cancel_and_refund_resa(annulation_par_l_admin=True)
        reservation.refresh_from_db()
        assert reservation.status == Reservation.CANCELED
        assert reservation.annulee_le == moment

    def test_annuler_le_dernier_billet_pose_annulee_le(self):
        moment = heure_de_paris(2026, 10, 13, 8, 10)
        reservation, billet = self._creer_une_reservation_gratuite_avec_un_billet()
        with patch("django.utils.timezone.now", return_value=moment):
            reservation.cancel_and_refund_ticket(billet, annulation_par_l_admin=True)
        reservation.refresh_from_db()
        assert reservation.status == Reservation.CANCELED
        assert reservation.annulee_le == moment

    def test_annuler_un_booking_pose_annulee_le(self):
        moment = heure_de_paris(2026, 10, 13, 8, 10)
        booking = self._creer_un_booking()
        with patch("django.utils.timezone.now", return_value=moment):
            booking.cancel_and_refund_booking()
        booking.refresh_from_db()
        assert booking.status == Booking.USER_CANCELED
        assert booking.annulee_le == moment

    def test_annuler_un_booking_dans_l_admin_pose_annulee_le(self):
        moment = heure_de_paris(2026, 10, 13, 8, 10)
        booking = self._creer_un_booking()
        booking.status = Booking.ADMIN_CANCELED
        formulaire_factice = SimpleNamespace(changed_data=["status"])
        requete = RequestFactory().post("/")
        with patch("django.utils.timezone.now", return_value=moment):
            BookingAdmin(Booking, staff_admin_site).save_model(
                requete, booking, formulaire_factice, change=True
            )
        booking.refresh_from_db()
        assert booking.status == Booking.ADMIN_CANCELED
        assert booking.annulee_le == moment

    def test_annuler_une_adhesion_par_l_admin_pose_annulee_le(self):
        moment = heure_de_paris(2026, 10, 13, 8, 10)
        administrateur = creer_utilisateur()
        administrateur.client_admin.add(self.tenant)
        adherent = creer_utilisateur()
        adhesion = Membership.objects.create(
            price=creer_adhesion().tarif,
            user=adherent,
            status=Membership.ADMIN_VALID,
        )
        client = TenantClient(self.tenant)
        client.force_login(administrateur)
        with patch("django.utils.timezone.now", return_value=moment):
            reponse = client.post(
                reverse("membership_mvt-cancel", kwargs={"pk": adhesion.pk}),
                {"with_credit_note": "0"},
                HTTP_HX_REQUEST="true",
            )
        assert reponse.status_code == 204
        assert "HX-Redirect" in reponse.headers
        adhesion.refresh_from_db()
        assert adhesion.status == Membership.ADMIN_CANCELED
        assert adhesion.annulee_le == moment

    def test_l_annulation_automatique_d_une_reservation_gratuite_ne_pose_pas_annulee_le(
        self,
    ):
        utilisateur = creer_utilisateur(actif=False)
        evenement = creer_evenement_avec_tarif(jauge_max=0).evenement
        reservation = Reservation.objects.create(
            user_commande=utilisateur,
            event=evenement,
            status=Reservation.FREERES,
            to_mail=True,
        )
        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_SCANNED)
        # `datetime` est en auto_now : on le recule par update(), il y a 1 h.
        Reservation.objects.filter(pk=reservation.pk).update(
            datetime=timezone.now() - timedelta(hours=1)
        )

        utilisateur.is_active = True
        utilisateur.save()

        reservation.refresh_from_db()
        assert reservation.status == Reservation.CANCELED
        assert reservation.annulee_le is None


class TestLesRubriques(RecapQuotidienTestCase):
    """
    La fenêtre de la veille et les rubriques billetterie, adhésions, ressources,
    bénévoles, événements.
    / The yesterday window and the ticketing, membership, resource, volunteer
    and event sections.
    """

    DOMAINE = "test-recap-quotidien.tibillet.localhost"

    def setUp(self):
        super().setUp()
        # La veille de référence : lundi 12 octobre 2026, heure de Paris.
        # / Reference "yesterday": Monday 12 October 2026, Paris time.
        self.debut, self.fin = fenetre_de_la_veille(
            heure_de_paris(2026, 10, 13, 7, 10), FUSEAU_DE_PARIS
        )
        self.hier = heure_de_paris(2026, 10, 12, 14, 10)
        self.avant_hier = heure_de_paris(2026, 10, 11, 14, 10)
        self.aujourd_hui = heure_de_paris(2026, 10, 13, 3, 10)

    # --- Outils / Helpers ---

    def _rubrique(self, cle):
        rubriques = rubriques_de_la_veille(self.debut, self.fin, self.DOMAINE)
        for rubrique in rubriques:
            if rubrique["cle"] == cle:
                return rubrique
        return None

    def _adhesion(self, moment, status=Membership.ONCE, user=None):
        adhesion = Membership.objects.create(
            price=self.tarif_adhesion, user=user, status=status
        )
        Membership.objects.filter(pk=adhesion.pk).update(date_added=moment)
        return adhesion

    @property
    def tarif_adhesion(self):
        if not hasattr(self, "_tarif_adhesion"):
            self._tarif_adhesion = creer_adhesion().tarif
        return self._tarif_adhesion

    def _reservation(self, moment, status=Reservation.VALID):
        billetterie = creer_evenement_avec_tarif()
        reservation = Reservation.objects.create(
            user_commande=creer_utilisateur(),
            event=billetterie.evenement,
            status=status,
        )
        Reservation.objects.filter(pk=reservation.pk).update(created_at=moment)
        return reservation

    def _booking(self, moment, status=Booking.PAID_BY_USER):
        ressource = creer_ressource_avec_tarif()
        booking = Booking.objects.create(
            resource=ressource.ressource,
            user=creer_utilisateur(),
            start_datetime=ressource.debut_du_creneau,
            slot_duration_minutes=60,
            slot_count=1,
            status=status,
        )
        Booking.objects.filter(pk=booking.pk).update(booked_at=moment)
        return booking

    def _inscription(self, moment):
        identifiant = identifiant_unique()
        planning = PlanningBenevole.objects.create(
            name=f"TEST_recap planning {identifiant}",
            slug=f"test-recap-{identifiant}",
            published=True,
        )
        tache = TacheBenevole.objects.create(name=f"TEST_recap bar {identifiant}")
        besoin = BesoinBenevole.objects.create(
            planning=planning,
            tache=tache,
            date=moment.date() + timedelta(days=5),
            heure_debut=time(18),
            heure_fin=time(21),
            nombre_souhaite=2,
        )
        inscription = InscriptionBenevole.objects.create(
            besoin=besoin, user=creer_utilisateur()
        )
        InscriptionBenevole.objects.filter(pk=inscription.pk).update(created_at=moment)
        return inscription

    def _evenement(self, moment, published=True, is_proposal=False):
        evenement = Event.objects.create(
            name=f"TEST_recap evenement {identifiant_unique()}",
            datetime=moment + timedelta(days=10),
            published=published,
            is_proposal=is_proposal,
        )
        Event.objects.filter(pk=evenement.pk).update(created_at=moment)
        return evenement

    # --- La fenêtre / The window ---

    def test_la_veille_va_de_minuit_a_minuit_heure_du_lieu(self):
        debut, fin = fenetre_de_la_veille(
            heure_de_paris(2026, 10, 13, 7), FUSEAU_DE_PARIS
        )
        assert debut == heure_utc(2026, 10, 11, 22)
        assert fin == heure_utc(2026, 10, 12, 22)

    def test_la_veille_d_une_nuit_de_changement_d_heure_dure_25_heures(self):
        debut, fin = fenetre_de_la_veille(
            heure_de_paris(2026, 10, 26, 7), FUSEAU_DE_PARIS
        )
        assert fin - debut == timedelta(hours=25)

    def test_la_veille_en_martinique(self):
        martinique = ZoneInfo("America/Martinique")
        maintenant = datetime(2026, 10, 13, 7, tzinfo=martinique)
        debut, fin = fenetre_de_la_veille(maintenant, martinique)
        assert debut == heure_utc(2026, 10, 12, 4)
        assert fin == heure_utc(2026, 10, 13, 4)

    # --- Nouvelles adhésions ---

    def test_nouvelles_adhesions_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._adhesion(self.hier)
        self._adhesion(self.avant_hier)
        self._adhesion(self.aujourd_hui)
        rubrique = self._rubrique("nouvelles_adhesions")
        assert rubrique["nombre"] == 1
        assert rubrique["nombre_de_nouveaux"] == 1
        assert rubrique["est_un_stock"] is False
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/BaseBillet/membership/"

    def test_nouvelles_adhesions_ignore_les_statuts_exclus(self):
        for statut in [
            Membership.WAITING_PAYMENT,
            Membership.CANCELED,
            Membership.ADMIN_CANCELED,
            Membership.ADMIN_WAITING,
        ]:
            with self.subTest(statut=statut):
                self._adhesion(self.hier, status=statut)
                assert self._rubrique("nouvelles_adhesions") is None

    # --- Adhésions en attente (stock) ---

    def test_adhesions_en_attente_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        # Un stock garde tout ce qui attend ; seule la part « nouvelle » dépend de la fenêtre.
        self._adhesion(self.hier, status=Membership.ADMIN_WAITING)
        self._adhesion(self.avant_hier, status=Membership.ADMIN_WAITING)
        self._adhesion(self.aujourd_hui, status=Membership.ADMIN_WAITING)
        rubrique = self._rubrique("adhesions_en_attente")
        assert rubrique["est_un_stock"] is True
        assert rubrique["nombre"] == 3
        assert rubrique["nombre_de_nouveaux"] == 1

    def test_adhesions_en_attente_ignore_les_autres_statuts(self):
        for statut in [Membership.ONCE, Membership.ADMIN_VALID, Membership.CANCELED]:
            with self.subTest(statut=statut):
                self._adhesion(self.hier, status=statut)
                assert self._rubrique("adhesions_en_attente") is None

    def test_une_demande_d_adhesion_d_hier_est_dans_le_stock_et_pas_dans_les_nouvelles(self):
        self._adhesion(self.hier, status=Membership.ADMIN_WAITING)
        assert self._rubrique("nouvelles_adhesions") is None
        rubrique = self._rubrique("adhesions_en_attente")
        assert rubrique["nombre"] == 1
        assert rubrique["nombre_de_nouveaux"] == 1

    def test_une_vieille_demande_en_attente_est_dans_le_stock_sans_etre_nouvelle(self):
        self._adhesion(self.avant_hier, status=Membership.ADMIN_WAITING)
        rubrique = self._rubrique("adhesions_en_attente")
        assert rubrique["nombre"] == 1
        assert rubrique["nombre_de_nouveaux"] == 0

    def test_une_adhesion_sans_personne_ne_fait_pas_planter(self):
        self._adhesion(self.hier, user=None)
        rubrique = self._rubrique("nouvelles_adhesions")
        assert len(rubrique["lignes"]) == 1
        with translation.override("fr"):
            rubrique = self._rubrique("nouvelles_adhesions")
        assert "(sans nom)" in rubrique["lignes"][0]

    def test_une_rubrique_de_douze_lignes_en_montre_dix(self):
        for _numero in range(12):
            self._adhesion(self.hier)
        rubrique = self._rubrique("nouvelles_adhesions")
        assert rubrique["nombre"] == 12
        assert len(rubrique["lignes"]) == 10
        assert rubrique["nombre_de_lignes_cachees"] == 2

    # --- Nouvelles réservations ---

    def test_nouvelles_reservations_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._reservation(self.hier)
        self._reservation(self.avant_hier)
        self._reservation(self.aujourd_hui)
        rubrique = self._rubrique("nouvelles_reservations")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/BaseBillet/reservation/"

    def test_nouvelles_reservations_ignore_les_statuts_exclus(self):
        for statut in [Reservation.CREATED, Reservation.UNPAID, Reservation.CANCELED]:
            with self.subTest(statut=statut):
                self._reservation(self.hier, status=statut)
                assert self._rubrique("nouvelles_reservations") is None

    def test_une_reservation_ancienne_modifiee_hier_ne_compte_pas(self):
        reservation = self._reservation(self.avant_hier)
        Reservation.objects.filter(pk=reservation.pk).update(datetime=self.hier)
        assert self._rubrique("nouvelles_reservations") is None

    # --- Nouvelles réservations de ressources ---

    def test_nouvelles_reservations_de_ressources_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._booking(self.hier)
        self._booking(self.avant_hier)
        self._booking(self.aujourd_hui)
        rubrique = self._rubrique("nouvelles_reservations_de_ressources")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/booking/booking/"

    def test_nouvelles_reservations_de_ressources_ignore_les_statuts_exclus(self):
        for statut in [
            Booking.WAITING_PAYMENT,
            Booking.ADMIN_CANCELED,
            Booking.USER_CANCELED,
        ]:
            with self.subTest(statut=statut):
                self._booking(self.hier, status=statut)
                assert self._rubrique("nouvelles_reservations_de_ressources") is None

    # --- Demandes de réservation en attente (stock) ---

    def test_une_demande_de_reservation_d_hier_est_dans_le_stock_et_pas_dans_les_nouvelles(self):
        self._booking(self.hier, status=Booking.ADMIN_WAITING)
        assert self._rubrique("nouvelles_reservations_de_ressources") is None
        rubrique = self._rubrique("demandes_de_reservation_en_attente")
        assert rubrique["est_un_stock"] is True
        assert rubrique["nombre"] == 1
        assert rubrique["nombre_de_nouveaux"] == 1
        assert rubrique["lien"] == (
            f"https://{self.DOMAINE}/admin/booking/booking/?status__exact=WA"
        )

    def test_demandes_de_reservation_en_attente_garde_tout_le_stock(self):
        # Un stock garde tout ce qui attend ; seule la part « nouvelle » dépend de la fenêtre.
        self._booking(self.hier, status=Booking.ADMIN_WAITING)
        self._booking(self.avant_hier, status=Booking.ADMIN_WAITING)
        self._booking(self.aujourd_hui, status=Booking.ADMIN_WAITING)
        rubrique = self._rubrique("demandes_de_reservation_en_attente")
        assert rubrique["nombre"] == 3
        assert rubrique["nombre_de_nouveaux"] == 1

    def test_demandes_de_reservation_en_attente_ignore_les_autres_statuts(self):
        for statut in [
            Booking.ADMIN_VALID,
            Booking.PAID_BY_USER,
            Booking.ADMIN_CANCELED,
        ]:
            with self.subTest(statut=statut):
                self._booking(self.hier, status=statut)
                assert self._rubrique("demandes_de_reservation_en_attente") is None

    # --- Nouvelles inscriptions de bénévoles ---

    def test_nouvelles_inscriptions_benevoles_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._inscription(self.hier)
        self._inscription(self.avant_hier)
        self._inscription(self.aujourd_hui)
        rubrique = self._rubrique("nouvelles_inscriptions_benevoles")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == (
            f"https://{self.DOMAINE}/admin/booking/inscriptionbenevole/"
        )

    # --- Nouveaux événements ---

    def test_nouveaux_evenements_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._evenement(self.hier)
        self._evenement(self.avant_hier)
        self._evenement(self.aujourd_hui)
        rubrique = self._rubrique("nouveaux_evenements")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/BaseBillet/event/"

    def test_chaque_evenement_montre_son_etat(self):
        self._evenement(self.hier, published=False, is_proposal=True)
        self._evenement(self.hier, published=False, is_proposal=False)
        with translation.override("fr"):
            lignes = self._rubrique("nouveaux_evenements")["lignes"]
        assert any("proposition en attente" in ligne for ligne in lignes)
        assert any("brouillon" in ligne for ligne in lignes)

    def test_une_proposition_creee_et_validee_hier_est_dans_les_nouveaux_evenements(self):
        self._evenement(self.hier, published=True, is_proposal=False)
        with translation.override("fr"):
            rubrique = self._rubrique("nouveaux_evenements")
        assert rubrique["nombre"] == 1
        assert "publié" in rubrique["lignes"][0]

    # --- Propositions en attente (stock) ---

    def test_propositions_en_attente_compte_tout_le_stock_dont_les_nouvelles(self):
        self._evenement(self.hier, published=False, is_proposal=True)
        self._evenement(self.avant_hier, published=False, is_proposal=True)
        self._evenement(self.aujourd_hui, published=False, is_proposal=True)
        rubrique = self._rubrique("propositions_en_attente")
        assert rubrique["est_un_stock"] is True
        assert rubrique["nombre"] == 3
        assert rubrique["nombre_de_nouveaux"] == 1

    def test_propositions_en_attente_ignore_les_evenements_publies_ou_non_proposes(self):
        cas = [(True, True), (False, False), (True, False)]
        for publie, proposition in cas:
            with self.subTest(publie=publie, proposition=proposition):
                self._evenement(self.hier, published=publie, is_proposal=proposition)
                assert self._rubrique("propositions_en_attente") is None

    def test_nouveaux_evenements_ignore_les_actions_enfants(self):
        # Les actions s'affichent dans leur événement parent, pas à part.
        parent = self._evenement(self.hier)
        for _numero in range(2):
            action = Event.objects.create(
                name=f"TEST_recap action {identifiant_unique()}",
                datetime=self.hier + timedelta(days=10),
                parent=parent,
            )
            Event.objects.filter(pk=action.pk).update(created_at=self.hier)
        assert self._rubrique("nouveaux_evenements")["nombre"] == 1

    def test_les_lignes_sont_classees_de_la_plus_recente_a_la_plus_ancienne(self):
        matin = heure_de_paris(2026, 10, 12, 9, 10)
        apres_midi = heure_de_paris(2026, 10, 12, 15, 10)
        user_matin = creer_utilisateur(prenom="Matin", nom="Tot")
        user_apres_midi = creer_utilisateur(prenom="Apresmidi", nom="Tard")
        self._adhesion(matin, user=user_matin)
        self._adhesion(apres_midi, user=user_apres_midi)
        rubrique = self._rubrique("nouvelles_adhesions")
        assert "Apresmidi" in rubrique["lignes"][0]
        assert "Matin" in rubrique["lignes"][1]


def _assert_argent_rendu(ligne, montant_attendu):
    """
    La ligne d'un remboursement finit par le montant en positif : jamais de signe moins.
    / A refund line ends with the positive amount: never a minus sign.
    """
    montant_de_la_ligne = ligne.split(" — ")[-1]
    assert montant_de_la_ligne == f"{montant_attendu}\u00a0€"
    assert "\u2212" not in montant_de_la_ligne
    assert "-" not in montant_de_la_ligne


class TestLesRubriquesSuite(RecapQuotidienTestCase):
    """
    Les rubriques financement participatif, remboursements et annulations.
    / The crowdfunding, refund and cancellation sections.
    """

    DOMAINE = "test-recap-quotidien.tibillet.localhost"

    def setUp(self):
        super().setUp()
        self.debut, self.fin = fenetre_de_la_veille(
            heure_de_paris(2026, 10, 13, 7, 10), FUSEAU_DE_PARIS
        )
        self.hier = heure_de_paris(2026, 10, 12, 14, 10)
        self.avant_hier = heure_de_paris(2026, 10, 11, 14, 10)
        self.aujourd_hui = heure_de_paris(2026, 10, 13, 3, 10)

    # --- Outils / Helpers ---

    def _rubrique(self, cle):
        rubriques = rubriques_de_la_veille(self.debut, self.fin, self.DOMAINE)
        for rubrique in rubriques:
            if rubrique["cle"] == cle:
                return rubrique
        return None

    def _projet(self, moment, devise="€"):
        return Initiative.objects.create(
            name=f"TEST_recap projet {identifiant_unique()}",
            created_at=moment,
            currency=devise,
        )

    def _ligne_de_budget(self, moment, state=BudgetItem.State.REQUESTED, devise="€"):
        return BudgetItem.objects.create(
            initiative=self._projet(self.avant_hier, devise),
            contributor=creer_utilisateur(),
            description="TEST_recap sono",
            amount=5000,
            state=state,
            created_at=moment,
        )

    def _contribution(
        self,
        paye_le,
        statut=Contribution.PaymentStatus.PAID,
        contributeur="par defaut",
        nom_du_contributeur="Camille",
        devise="€",
    ):
        if contributeur == "par defaut":
            contributeur = creer_utilisateur()
        return Contribution.objects.create(
            initiative=self._projet(self.avant_hier, devise),
            contributor=contributeur,
            contributor_name=nom_du_contributeur,
            amount=2500,
            payment_status=statut,
            paid_at=paye_le,
            created_at=self.avant_hier,
        )

    def _vote(self, moment):
        return Vote.objects.create(
            initiative=self._projet(self.avant_hier),
            user=creer_utilisateur(),
            created_at=moment,
        )

    def _participation(self, moment, state=Participation.State.REQUESTED):
        return Participation.objects.create(
            initiative=self._projet(self.avant_hier),
            participant=creer_utilisateur(),
            description="TEST_recap aide",
            amount=1000,
            state=state,
            created_at=moment,
        )

    def _reservation_payee_en_especes(self, part_offerte=0):
        """
        Une réservation d'un billet à 10 €, vendue par le service de vente, payée en
        espèces (le reste est offert si `part_offerte` > 0).
        / A one-ticket reservation at 10 €, written by the sale service, paid in cash.
        """
        billetterie = creer_evenement_avec_tarif(prix="10.00")
        reservation = Reservation.objects.create(
            user_commande=creer_utilisateur(),
            event=billetterie.evenement,
            status=Reservation.VALID,
        )
        produit_vendu = ProductSold.objects.create(
            product=billetterie.produit, event=billetterie.evenement
        )
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=billetterie.tarif, prix=10
        )
        Ticket.objects.create(
            reservation=reservation,
            pricesold=tarif_vendu,
            status=Ticket.NOT_SCANNED,
        )
        article = {
            "pricesold": tarif_vendu,
            "quantite": Decimal("1"),
            "prix_unitaire": 1000,
            "taux_tva": Decimal("20"),
            "reservation": reservation,
            "status": LigneArticle.VALID,
            "payment_method": PaymentMethod.CASH,
        }
        reglements = [{"moyen": PaymentMethod.CASH, "montant": 1000}]
        if part_offerte > 0:
            article["part_offerte"] = part_offerte
            article["source_offert"] = LigneArticle.SourceOffert.OFFRIR
            reglements = [
                {"moyen": PaymentMethod.CASH, "montant": 1000 - part_offerte},
                {"moyen": PaymentMethod.FREE, "montant": part_offerte},
            ]
        fabriquer_vente_encaissee(
            origine=SaleOrigin.ADMIN, articles=[article], reglements=reglements
        )
        return reservation

    def _annuler_avec_avoir_hier(self, reservation):
        """L'admin annule et rembourse en espèces, hier. / Admin cancels, cash refund."""
        with patch("django.utils.timezone.now", return_value=self.hier):
            reservation.cancel_and_refund_resa(
                annulation_par_l_admin=True, moyen_rembourse=PaymentMethod.CASH
            )

    def _reservation_gratuite_annulee_hier(self):
        billetterie = creer_evenement_avec_tarif(prix="0.00")
        produit_vendu = ProductSold.objects.create(
            product=billetterie.produit, event=billetterie.evenement
        )
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=billetterie.tarif, prix=0
        )
        reservation = Reservation.objects.create(
            user_commande=creer_utilisateur(),
            event=billetterie.evenement,
            status=Reservation.VALID,
        )
        Ticket.objects.create(
            reservation=reservation, pricesold=tarif_vendu, status=Ticket.NOT_SCANNED
        )
        with patch("django.utils.timezone.now", return_value=self.hier):
            reservation.cancel_and_refund_resa(annulation_par_l_admin=True)
        return reservation

    def _ligne_de_caisse_remboursee(self, moment):
        """Un article de caisse payé en espèces, puis son avoir écrit au moment donné.
        / A register item paid in cash, then its credit note written at that moment."""
        tarif_vendu = creer_tarif_vendu(nom="Biere", prix_en_euros="5.00")
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_vendu,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "status": LigneArticle.VALID,
                    "payment_method": PaymentMethod.CASH,
                }
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
        )
        ligne = vente.articles.get()
        with patch("django.utils.timezone.now", return_value=moment):
            ecrire_la_vente_d_avoir_d_une_ligne(
                ligne, Decimal("1"), PaymentMethod.CASH, SaleOrigin.ADMIN
            )
        return tarif_vendu

    # --- Nouveaux projets ---

    def test_nouveaux_projets_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._projet(self.hier)
        self._projet(self.avant_hier)
        self._projet(self.aujourd_hui)
        rubrique = self._rubrique("nouveaux_projets")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/crowds/initiative/"

    # --- Nouvelles lignes de budget ---

    def test_nouvelles_lignes_de_budget_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._ligne_de_budget(self.hier)
        self._ligne_de_budget(self.avant_hier)
        self._ligne_de_budget(self.aujourd_hui)
        rubrique = self._rubrique("nouvelles_lignes_de_budget")
        assert rubrique["nombre"] == 1

    def test_une_ligne_de_budget_montre_son_montant(self):
        self._ligne_de_budget(self.hier)
        with translation.override("fr"):
            rubrique = self._rubrique("nouvelles_lignes_de_budget")
        assert "50,00" in rubrique["lignes"][0]

    def test_une_ligne_de_budget_montre_son_etat(self):
        self._ligne_de_budget(self.hier)
        with translation.override("fr"):
            rubrique = self._rubrique("nouvelles_lignes_de_budget")
        assert rubrique["lignes"][0].endswith(str(BudgetItem.State.REQUESTED.label))

    def test_une_ligne_de_budget_en_heures_s_ecrit_en_heures(self):
        self._ligne_de_budget(self.hier, devise="heures")
        with translation.override("fr"):
            rubrique = self._rubrique("nouvelles_lignes_de_budget")
        assert "50,00\u00a0heures" in rubrique["lignes"][0]
        assert "€" not in rubrique["lignes"][0]

    # --- Lignes de budget en attente (stock) ---

    def test_lignes_de_budget_en_attente_compte_tout_le_stock_dont_les_nouvelles(self):
        self._ligne_de_budget(self.hier)
        self._ligne_de_budget(self.avant_hier)
        self._ligne_de_budget(self.aujourd_hui)
        rubrique = self._rubrique("lignes_de_budget_en_attente")
        assert rubrique["est_un_stock"] is True
        assert rubrique["nombre"] == 3
        assert rubrique["nombre_de_nouveaux"] == 1

    def test_lignes_de_budget_en_attente_ignore_les_autres_statuts(self):
        for etat in [BudgetItem.State.APPROVED, BudgetItem.State.REJECTED]:
            with self.subTest(etat=etat):
                self._ligne_de_budget(self.hier, state=etat)
                assert self._rubrique("lignes_de_budget_en_attente") is None

    # --- Contributions payées ---

    def test_contributions_payees_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._contribution(self.hier)
        self._contribution(self.avant_hier)
        self._contribution(self.aujourd_hui)
        rubrique = self._rubrique("contributions_payees")
        assert rubrique["nombre"] == 1

    def test_contributions_payees_accepte_paye_et_indique_comme_paye(self):
        self._contribution(self.hier, statut=Contribution.PaymentStatus.PAID)
        self._contribution(self.hier, statut=Contribution.PaymentStatus.PAID_ADMIN)
        assert self._rubrique("contributions_payees")["nombre"] == 2

    def test_contributions_payees_ignore_les_statuts_exclus(self):
        self._contribution(self.hier, statut=Contribution.PaymentStatus.PENDING)
        assert self._rubrique("contributions_payees") is None

    def test_une_contribution_creee_avant_hier_et_payee_hier_compte(self):
        self._contribution(self.hier)
        assert self._rubrique("contributions_payees")["nombre"] == 1

    def test_une_contribution_en_attente_ne_compte_pas(self):
        self._contribution(None, statut=Contribution.PaymentStatus.PENDING)
        assert self._rubrique("contributions_payees") is None

    def test_une_contribution_sans_contributeur_ne_fait_pas_planter(self):
        self._contribution(self.hier, contributeur=None, nom_du_contributeur=None)
        with translation.override("fr"):
            rubrique = self._rubrique("contributions_payees")
        assert "(sans nom)" in rubrique["lignes"][0]
        assert "25,00" in rubrique["lignes"][0]

    def test_une_contribution_montre_son_statut_de_paiement(self):
        self._contribution(self.hier, statut=Contribution.PaymentStatus.PAID_ADMIN)
        with translation.override("fr"):
            rubrique = self._rubrique("contributions_payees")
        assert rubrique["lignes"][0].endswith(
            str(Contribution.PaymentStatus.PAID_ADMIN.label)
        )

    def test_une_contribution_en_heures_s_ecrit_en_heures(self):
        self._contribution(self.hier, devise="heures")
        with translation.override("fr"):
            rubrique = self._rubrique("contributions_payees")
        assert "25,00\u00a0heures" in rubrique["lignes"][0]
        assert "€" not in rubrique["lignes"][0]

    def test_une_contribution_en_euros_s_ecrit_en_euros(self):
        self._contribution(self.hier)
        with translation.override("fr"):
            rubrique = self._rubrique("contributions_payees")
        assert "25,00\u00a0€" in rubrique["lignes"][0]

    # --- Nouveaux votes ---

    def test_nouveaux_votes_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._vote(self.hier)
        self._vote(self.avant_hier)
        self._vote(self.aujourd_hui)
        assert self._rubrique("nouveaux_votes")["nombre"] == 1

    # --- Nouvelles participations ---

    def test_nouvelles_participations_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._participation(self.hier)
        self._participation(self.avant_hier)
        self._participation(self.aujourd_hui)
        assert self._rubrique("nouvelles_participations")["nombre"] == 1

    # --- Participations en attente (stock) ---

    def test_participations_en_attente_compte_tout_le_stock_dont_les_nouvelles(self):
        self._participation(self.hier)
        self._participation(self.avant_hier)
        rubrique = self._rubrique("participations_en_attente")
        assert rubrique["est_un_stock"] is True
        assert rubrique["nombre"] == 2
        assert rubrique["nombre_de_nouveaux"] == 1

    def test_participations_en_attente_ignore_les_autres_statuts(self):
        for etat in [
            Participation.State.REJECTED,
            Participation.State.APPROVED_ADMIN,
            Participation.State.COMPLETED_USER,
            Participation.State.VALIDATED_ADMIN,
        ]:
            with self.subTest(etat=etat):
                self._participation(self.hier, state=etat)
                assert self._rubrique("participations_en_attente") is None

    # --- Remboursements ---

    def test_remboursements_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        self._ligne_de_caisse_remboursee(self.hier)
        self._ligne_de_caisse_remboursee(self.avant_hier)
        self._ligne_de_caisse_remboursee(self.aujourd_hui)
        rubrique = self._rubrique("remboursements")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/BaseBillet/vente/"

    def test_remboursements_ignore_les_statuts_exclus(self):
        # Une vente d'hier (ligne VALID, pas un avoir) n'est pas un remboursement.
        tarif_vendu = creer_tarif_vendu(nom="Biere", prix_en_euros="5.00")
        with patch("django.utils.timezone.now", return_value=self.hier):
            fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_vendu,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 500,
                        "taux_tva": Decimal("20"),
                        "status": LigneArticle.VALID,
                        "payment_method": PaymentMethod.CASH,
                    }
                ],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
            )
        for statut in [LigneArticle.VALID, LigneArticle.PAID, LigneArticle.CANCELED]:
            with self.subTest(statut=statut):
                LigneArticle.objects.filter(pricesold=tarif_vendu).update(
                    status=statut, datetime=self.hier
                )
                assert self._rubrique("remboursements") is None

    def test_un_remboursement_d_hier_nomme_la_reservation_et_le_montant(self):
        reservation = self._reservation_payee_en_especes()
        self._annuler_avec_avoir_hier(reservation)
        with translation.override("fr"):
            rubrique = self._rubrique("remboursements")
        assert rubrique["nombre"] == 1
        assert reservation.event.name in rubrique["lignes"][0]
        _assert_argent_rendu(rubrique["lignes"][0], "10,00")

    def test_un_remboursement_d_un_article_de_caisse_nomme_l_article(self):
        tarif_vendu = self._ligne_de_caisse_remboursee(self.hier)
        with translation.override("fr"):
            rubrique = self._rubrique("remboursements")
        assert tarif_vendu.productsold.product.name in rubrique["lignes"][0]
        _assert_argent_rendu(rubrique["lignes"][0], "5,00")

    def test_le_montant_rembourse_est_l_argent_rendu(self):
        # 10 € dont 4 € offerts : l'argent rendu est 6 €, pas 10 €.
        reservation = self._reservation_payee_en_especes(part_offerte=400)
        self._annuler_avec_avoir_hier(reservation)
        with translation.override("fr"):
            rubrique = self._rubrique("remboursements")
        _assert_argent_rendu(rubrique["lignes"][0], "6,00")
        assert "10,00" not in rubrique["lignes"][0]

    def test_le_nom_d_un_remboursement_d_adhesion_est_le_produit_d_adhesion(self):
        ligne_d_avoir = SimpleNamespace(
            reservation=None,
            membership=SimpleNamespace(
                price=SimpleNamespace(product=SimpleNamespace(name="TEST_recap Adhesion"))
            ),
            booking=None,
        )
        assert _nom_de_l_objet_rembourse(ligne_d_avoir) == "TEST_recap Adhesion"

    def test_le_nom_d_un_remboursement_de_booking_est_la_ressource(self):
        ligne_d_avoir = SimpleNamespace(
            reservation=None,
            membership=None,
            booking=SimpleNamespace(resource=SimpleNamespace(name="TEST_recap Salle")),
        )
        assert _nom_de_l_objet_rembourse(ligne_d_avoir) == "TEST_recap Salle"

    # --- Annulations ---

    def test_annulations_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        for moment in [self.hier, self.avant_hier, self.aujourd_hui]:
            reservation = self._reservation_payee_en_especes()
            Reservation.objects.filter(pk=reservation.pk).update(annulee_le=moment)
        rubrique = self._rubrique("annulations")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/BaseBillet/reservation/"

    def test_annulations_ne_liste_pas_ce_qui_n_a_pas_de_date_d_annulation(self):
        # Statut annulé mais `annulee_le` vide (annulation automatique) : exclu.
        reservation = self._reservation_payee_en_especes()
        Reservation.objects.filter(pk=reservation.pk).update(
            status=Reservation.CANCELED, annulee_le=None
        )
        assert self._rubrique("annulations") is None

    def test_annulations_reunit_reservations_bookings_et_adhesions(self):
        reservation = self._reservation_payee_en_especes()
        Reservation.objects.filter(pk=reservation.pk).update(annulee_le=self.hier)
        ressource = creer_ressource_avec_tarif()
        booking = Booking.objects.create(
            resource=ressource.ressource,
            user=creer_utilisateur(),
            start_datetime=ressource.debut_du_creneau,
            slot_duration_minutes=60,
            slot_count=1,
            status=Booking.ADMIN_CANCELED,
        )
        Booking.objects.filter(pk=booking.pk).update(annulee_le=self.hier)
        adhesion = Membership.objects.create(
            price=creer_adhesion().tarif,
            user=creer_utilisateur(),
            status=Membership.ADMIN_CANCELED,
        )
        Membership.objects.filter(pk=adhesion.pk).update(annulee_le=self.hier)
        rubrique = self._rubrique("annulations")
        assert rubrique["nombre"] == 3
        assert len(rubrique["lignes"]) == 3
        texte_des_lignes = "\n".join(rubrique["lignes"])
        assert reservation.event.name in texte_des_lignes
        assert ressource.ressource.name in texte_des_lignes
        assert adhesion.price.product.name in texte_des_lignes

    def test_annulations_les_plus_recentes_d_abord(self):
        reservation = self._reservation_payee_en_especes()
        Reservation.objects.filter(pk=reservation.pk).update(
            annulee_le=heure_de_paris(2026, 10, 12, 9, 10)
        )
        adhesion = Membership.objects.create(
            price=creer_adhesion().tarif,
            user=creer_utilisateur(),
            status=Membership.ADMIN_CANCELED,
        )
        Membership.objects.filter(pk=adhesion.pk).update(
            annulee_le=heure_de_paris(2026, 10, 12, 15, 10)
        )
        rubrique = self._rubrique("annulations")
        assert adhesion.price.product.name in rubrique["lignes"][0]
        assert reservation.event.name in rubrique["lignes"][1]

    def test_une_annulation_remboursee_est_marquee_rembourse(self):
        reservation = self._reservation_payee_en_especes()
        self._annuler_avec_avoir_hier(reservation)
        with translation.override("fr"):
            rubrique = self._rubrique("annulations")
        assert rubrique["nombre"] == 1
        assert "remboursé" in rubrique["lignes"][0]

    def test_une_annulation_sans_argent_est_listee(self):
        self._reservation_gratuite_annulee_hier()
        with translation.override("fr"):
            rubrique = self._rubrique("annulations")
        assert rubrique["nombre"] == 1
        assert "remboursé" not in rubrique["lignes"][0]

    def test_une_rubrique_d_annulations_de_douze_lignes_en_montre_dix(self):
        for _numero in range(12):
            reservation = self._reservation_payee_en_especes()
            Reservation.objects.filter(pk=reservation.pk).update(annulee_le=self.hier)
        rubrique = self._rubrique("annulations")
        assert rubrique["nombre"] == 12
        assert len(rubrique["lignes"]) == 10
        assert rubrique["nombre_de_lignes_cachees"] == 2


def une_rubrique(cle, est_un_stock, nombre_de_nouveaux):
    """Une rubrique minimale pour `le_recap_a_du_contenu`. / A minimal section."""
    return {
        "cle": cle,
        "est_un_stock": est_un_stock,
        "nombre_de_nouveaux": nombre_de_nouveaux,
    }


class TestZContenuDestinataires(RecapQuotidienTestCase):
    """
    Les Z à joindre, « y a-t-il du contenu ? » et les destinataires.
    Les J sont fabriquées par le vrai moteur de clôture.
    / The Z to attach, "is there content?" and the recipients.

    LOCALISATION : tests/pytest/test_recap_quotidien.py
    """

    def setUp(self):
        super().setUp()
        configuration = Configuration.get_solo()
        configuration.module_billetterie = True
        configuration.module_adhesion = True
        configuration.save()
        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )

    # --- Outils / Helpers ---

    def _vendre_des_jus_a(self, moment):
        """Une vente de caisse en espèces à `moment`. / A cash sale at `moment`."""
        with patch("django.utils.timezone.now", return_value=moment):
            return fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": self.tarif_du_jus,
                        "quantite": Decimal(1),
                        "prix_unitaire": 350,
                        "taux_tva": Decimal("20"),
                    },
                ],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
            )

    def _cloturer_a(self, moment):
        """Un Z manuel (J) à `moment`. / A manual Z (J) at `moment`."""
        with patch("django.utils.timezone.now", return_value=moment):
            uuid_de_la_cloture = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_cloture)

    def _lancer_la_tache_horaire_a(self, moment):
        """La tâche horaire du lieu à `moment`. / The hourly task at `moment`."""
        with patch("django.utils.timezone.now", return_value=moment):
            comptabilite.tasks.generer_les_clotures_automatiques_du_lieu(
                self.tenant.schema_name
            )

    def _les_clotures_du_mardi_13(self):
        """
        Les J à joindre au récap du mardi 13 : de lundi 4 h à mardi 4 h (heure de Paris).
        / The J for the Tuesday 13 recap.
        """
        return clotures_j_a_joindre(
            heure_de_paris(2026, 10, 12, 4, 0),
            heure_de_paris(2026, 10, 13, 4, 0),
        )

    def _creer_un_admin(self, adresse):
        """Un admin du lieu. / An admin of the venue."""
        admin = TibilletUser.objects.create(email=adresse, username=adresse)
        admin.client_admin.add(self.tenant)
        return admin

    # --- Les Z à joindre / The Z to attach ---

    def test_le_z_manuel_d_hier_soir_et_le_filet_de_ce_matin_sont_joints(self):
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 20, 0))
        z_manuel = self._cloturer_a(heure_de_paris(2026, 10, 12, 23, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 23, 30))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 13, 4, 10))
        filet = ClotureCaisse.objects.get(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            numero_sequentiel__gt=z_manuel.numero_sequentiel,
        )

        clotures = self._les_clotures_du_mardi_13()

        assert [cloture.pk for cloture in clotures] == [z_manuel.pk, filet.pk]

    def test_un_z_de_ce_matin_10h_n_est_pas_joint(self):
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 13, 9, 0))
        self._cloturer_a(heure_de_paris(2026, 10, 13, 10, 0))

        assert self._les_clotures_du_mardi_13() == []

    def test_la_j_du_filet_de_la_veille_n_est_pas_rejointe(self):
        """Fin PILE au seuil de la veille : la borne basse est exclue. / Low bound excluded."""
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 11, 23, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 12, 4, 10))
        filet_de_la_veille = ClotureCaisse.objects.get(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER
        )
        assert filet_de_la_veille.datetime_fin == heure_de_paris(2026, 10, 12, 4, 0)

        assert self._les_clotures_du_mardi_13() == []

    def test_une_cloture_finie_a_la_mise_en_service_n_est_pas_jointe(self):
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 20, 0))
        with patch(
            "django.utils.timezone.now",
            return_value=heure_de_paris(2026, 10, 12, 23, 0),
        ):
            call_command(
                "creer_la_cloture_de_reprise",
                "--schema",
                self.tenant.schema_name,
                stdout=StringIO(),
                stderr=StringIO(),
            )
        assert comptabilite.tasks.mise_en_service_du_lieu() is not None

        # La J de reprise finit EXACTEMENT à la mise en service : pas jointe.
        # / The reprise J ends exactly at go-live: not attached.
        assert self._les_clotures_du_mardi_13() == []

        # Une J d'après la mise en service est jointe.
        # / A J after the go-live is attached.
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 23, 30))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 13, 4, 10))
        clotures = self._les_clotures_du_mardi_13()
        assert len(clotures) == 1
        assert clotures[0].datetime_fin == heure_de_paris(2026, 10, 13, 4, 0)

    def test_une_cloture_hebdomadaire_n_est_pas_jointe(self):
        """
        Lundi 12 octobre à 4 h 10 le filet clôture aussi la semaine du 5 au 12 (fin à
        minuit, dans la fenêtre du récap du lundi) : seule la J est jointe.
        / The weekly closure ends in the window but is not attached.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 7, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 12, 4, 10))
        hebdomadaire = ClotureCaisse.objects.get(
            niveau=ClotureCaisse.NIVEAU_HEBDOMADAIRE
        )
        assert hebdomadaire.datetime_fin == heure_de_paris(2026, 10, 12, 0, 0)

        clotures = clotures_j_a_joindre(
            heure_de_paris(2026, 10, 11, 4, 0),
            heure_de_paris(2026, 10, 12, 4, 0),
        )

        assert len(clotures) >= 1
        for cloture in clotures:
            assert cloture.niveau == ClotureCaisse.NIVEAU_JOURNALIER

    # --- Le contenu / Content ---

    def test_sans_rubrique_ni_z_il_n_y_a_pas_de_contenu(self):
        assert le_recap_a_du_contenu([], []) is False

    def test_un_stock_sans_nouveau_n_est_pas_du_contenu(self):
        rubriques = [une_rubrique("adhesions_en_attente", True, 0)]
        assert le_recap_a_du_contenu(rubriques, []) is False

    def test_un_stock_avec_un_nouveau_est_du_contenu(self):
        rubriques = [une_rubrique("adhesions_en_attente", True, 1)]
        assert le_recap_a_du_contenu(rubriques, []) is True

    def test_une_rubrique_qui_n_est_pas_un_stock_est_du_contenu(self):
        rubriques = [une_rubrique("reservations", False, 0)]
        assert le_recap_a_du_contenu(rubriques, []) is True

    def test_un_z_seul_est_du_contenu(self):
        assert le_recap_a_du_contenu([], ["un Z"]) is True

    # --- Les destinataires / Recipients ---

    def test_les_destinataires_sont_les_admins_du_lieu(self):
        self._creer_un_admin("premier@example.org")
        self._creer_un_admin("second@example.org")

        destinataires = destinataires_du_recap(self.tenant, Configuration.get_solo())

        assert sorted(destinataires) == ["premier@example.org", "second@example.org"]

    def test_sans_admin_le_mail_du_lieu_sert_de_secours(self):
        destinataires = destinataires_du_recap(self.tenant, Configuration.get_solo())
        assert destinataires == ["lieu@example.org"]

    def test_un_seul_admin_a_email_vide_laisse_le_mail_du_lieu(self):
        admin = self._creer_un_admin("a-effacer@example.org")
        TibilletUser.objects.filter(pk=admin.pk).update(email="")

        destinataires = destinataires_du_recap(self.tenant, Configuration.get_solo())

        assert destinataires == ["lieu@example.org"]

    def test_sans_admin_ni_mail_du_lieu_il_n_y_a_aucun_destinataire(self):
        configuration = Configuration.get_solo()
        configuration.email = ""
        configuration.save()

        assert destinataires_du_recap(self.tenant, configuration) == []

    def test_rapport_emails_ajoute_en_periodicite_journaliere(self):
        self._creer_un_admin("admin@example.org")
        configuration = Configuration.get_solo()
        configuration.rapport_periodicite = Configuration.PERIODICITE_JOURNALIER
        configuration.rapport_emails = "compta@example.org, autre@example.org"
        configuration.save()

        destinataires = destinataires_du_recap(self.tenant, configuration)

        assert destinataires == [
            "admin@example.org",
            "compta@example.org",
            "autre@example.org",
        ]

    def test_rapport_emails_ignore_hors_periodicite_journaliere(self):
        self._creer_un_admin("admin@example.org")
        configuration = Configuration.get_solo()
        configuration.rapport_periodicite = Configuration.PERIODICITE_MENSUEL
        configuration.rapport_emails = "compta@example.org"
        configuration.save()

        assert destinataires_du_recap(self.tenant, configuration) == [
            "admin@example.org"
        ]

    def test_un_admin_aussi_dans_rapport_emails_n_est_compte_qu_une_fois(self):
        self._creer_un_admin("admin@example.org")
        configuration = Configuration.get_solo()
        configuration.rapport_periodicite = Configuration.PERIODICITE_JOURNALIER
        configuration.rapport_emails = " Admin@Example.org ,, compta@example.org"
        configuration.save()

        assert destinataires_du_recap(self.tenant, configuration) == [
            "admin@example.org",
            "compta@example.org",
        ]


class TestEnvoiDuRecap(RecapQuotidienTestCase):
    """
    L'heure d'envoi, le seuil, le marqueur, les pièces jointes, la langue.
    `CeleryMailerClass` est remplacé : on lit seulement ses arguments d'appel.
    / Send hour, threshold, marker, attachments, language. The mailer is mocked:
    only its call arguments are read.

    LOCALISATION : tests/pytest/test_recap_quotidien.py
    """

    # Les outils de la classe des Z : mêmes J fabriquées par le vrai moteur.
    # / Same helpers as the Z test class.
    _vendre_des_jus_a = TestZContenuDestinataires._vendre_des_jus_a
    _cloturer_a = TestZContenuDestinataires._cloturer_a
    _lancer_la_tache_horaire_a = TestZContenuDestinataires._lancer_la_tache_horaire_a
    _creer_un_admin = TestZContenuDestinataires._creer_un_admin

    def setUp(self):
        super().setUp()
        Configuration.objects.update(recap_quotidien_traite_le=None)
        Configuration.clear_cache()
        configuration = Configuration.get_solo()
        configuration.module_billetterie = True
        configuration.module_adhesion = True
        configuration.save()
        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        # Les seuils du mardi 13 (fermeture à 2 h : seuils à 4 h).
        # / Thresholds for Tuesday 13 (closing at 2 am: thresholds at 4 am).
        self.seuil_de_la_veille = heure_de_paris(2026, 10, 12, 4, 0)
        self.seuil_d_aujourd_hui = heure_de_paris(2026, 10, 13, 4, 0)

    # --- Outils / Helpers ---

    def _faire_un_z_hier_soir(self):
        """Une vente puis un Z manuel lundi 23 h. / A sale then a manual Z."""
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 20, 0))
        return self._cloturer_a(heure_de_paris(2026, 10, 12, 23, 0))

    def _appeler_a(
        self,
        moment,
        seuil_de_la_veille=None,
        seuil_d_aujourd_hui=None,
        effet_du_mailer=None,
    ):
        """
        Appelle la fonction d'heure à `moment`, avec le mailer et le PDF remplacés.
        Rend (résultat, classe du mailer remplacée, fonction PDF remplacée).
        / Calls the hour function at `moment`, mailer and PDF mocked.
        """
        if seuil_de_la_veille is None:
            seuil_de_la_veille = self.seuil_de_la_veille
        if seuil_d_aujourd_hui is None:
            seuil_d_aujourd_hui = self.seuil_d_aujourd_hui

        def faux_pdf(cloture):
            return (b"pdf", f"z-{cloture.numero_sequentiel}.pdf", "application/pdf")

        with patch("django.utils.timezone.now", return_value=moment):
            with patch(
                "Administration.recap_quotidien.generer_pdf_cloture",
                side_effect=faux_pdf,
            ) as pdf_remplace:
                with patch(
                    "Administration.recap_quotidien.CeleryMailerClass",
                    side_effect=effet_du_mailer,
                ) as mailer_remplace:
                    mailer_remplace.return_value.send.return_value = True
                    resultat = envoyer_le_recap_du_lieu_si_c_est_l_heure(
                        seuil_de_la_veille, seuil_d_aujourd_hui
                    )
        return resultat, mailer_remplace, pdf_remplace

    def _le_marqueur(self):
        """Le marqueur lu en base. / The marker read from the database."""
        return Configuration.objects.get().recap_quotidien_traite_le

    # --- L'heure / The hour ---

    def test_a_6h10_rien_ne_part(self):
        self._faire_un_z_hier_soir()

        resultat, mailer, _pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 6, 10))

        assert resultat is False
        assert mailer.call_count == 0
        assert self._le_marqueur() is None

    def test_a_7h10_le_recap_part(self):
        self._faire_un_z_hier_soir()

        resultat, mailer, _pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert resultat is True
        assert mailer.call_count == 1
        arguments = mailer.call_args.kwargs
        assert arguments["email"] == ["lieu@example.org"]
        assert arguments["template"] == "emails/recap_quotidien.html"
        assert "12/10/2026" in arguments["title"]
        assert mailer.return_value.send.call_count == 1
        assert self._le_marqueur() == date(2026, 10, 13)

    def test_un_second_passage_a_8h10_n_envoie_rien(self):
        self._faire_un_z_hier_soir()
        self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        resultat, mailer, _pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 8, 10))

        assert resultat is False
        assert mailer.call_count == 0

    def test_fermeture_a_6h_rien_a_7h10_envoi_a_8h10(self):
        configuration = Configuration.get_solo()
        configuration.heure_de_fermeture = time(6, 0)
        configuration.save()
        self._faire_un_z_hier_soir()
        seuil_de_la_veille = heure_de_paris(2026, 10, 12, 8, 0)
        seuil_d_aujourd_hui = heure_de_paris(2026, 10, 13, 8, 0)

        a_7h10, mailer_a_7h10, _pdf = self._appeler_a(
            heure_de_paris(2026, 10, 13, 7, 10), seuil_de_la_veille, seuil_d_aujourd_hui
        )
        a_8h10, mailer_a_8h10, _pdf = self._appeler_a(
            heure_de_paris(2026, 10, 13, 8, 10), seuil_de_la_veille, seuil_d_aujourd_hui
        )

        assert a_7h10 is False
        assert mailer_a_7h10.call_count == 0
        assert a_8h10 is True
        assert mailer_a_8h10.call_count == 1

    # --- Pas de contenu / No content ---

    def test_sans_contenu_aucun_pdf_n_est_genere(self):
        """
        Un stock en attente sans nouveau + un Z d'avant-hier (hors fenêtre) :
        ni mail, ni PDF, mais le marqueur est posé.
        / A stock without new items + a Z from the day before yesterday.
        """
        adhesion = Membership.objects.create(
            price=creer_adhesion().tarif, user=None, status=Membership.ADMIN_WAITING
        )
        Membership.objects.filter(pk=adhesion.pk).update(
            date_added=heure_de_paris(2026, 10, 10, 12, 0)
        )
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 11, 20, 0))
        self._cloturer_a(heure_de_paris(2026, 10, 11, 23, 0))

        resultat, mailer, pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert resultat is False
        assert self._le_marqueur() == date(2026, 10, 13)
        assert pdf.call_count == 0
        assert mailer.call_count == 0

    def test_sans_contenu_pas_de_mail_mais_le_marqueur_est_pose(self):
        resultat, mailer, _pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert resultat is False
        assert mailer.call_count == 0
        assert self._le_marqueur() == date(2026, 10, 13)

    def test_sans_destinataire_pas_de_mail_un_avertissement_et_le_marqueur(self):
        configuration = Configuration.get_solo()
        configuration.email = ""
        configuration.save()
        self._faire_un_z_hier_soir()

        with self.assertLogs("Administration.recap_quotidien", level="WARNING"):
            resultat, mailer, pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert resultat is False
        assert mailer.call_count == 0
        assert pdf.call_count == 0
        assert self._le_marqueur() == date(2026, 10, 13)

    # --- Le marqueur / The marker ---

    def test_le_marqueur_est_pose_sans_configuration_save(self):
        self._faire_un_z_hier_soir()

        with patch.object(Configuration, "save") as save_remplace:
            self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert save_remplace.call_count == 0
        assert self._le_marqueur() == date(2026, 10, 13)

    def test_le_marqueur_est_pose_avant_l_envoi(self):
        """Un envoi qui plante laisse le marqueur posé : pas de doublon à l'heure suivante."""
        self._faire_un_z_hier_soir()

        def mailer_qui_plante(**arguments):
            raise RuntimeError("envoi en panne")

        with self.assertRaises(RuntimeError):
            self._appeler_a(
                heure_de_paris(2026, 10, 13, 7, 10), effet_du_mailer=mailer_qui_plante
            )

        assert self._le_marqueur() == date(2026, 10, 13)

    def test_un_envoi_qui_echoue_rend_false(self):
        self._faire_un_z_hier_soir()

        def mailer_sans_envoi(**arguments):
            return SimpleNamespace(send=lambda: 0)

        resultat, _mailer, _pdf = self._appeler_a(
            heure_de_paris(2026, 10, 13, 7, 10), effet_du_mailer=mailer_sans_envoi
        )

        assert resultat is False

    def test_un_marqueur_pose_entre_la_lecture_et_la_pose_n_envoie_rien(self):
        """Une autre sous-tâche pose le marqueur pendant le calcul : aucun mail."""
        from Administration import recap_quotidien

        self._faire_un_z_hier_soir()
        preparer_reel = recap_quotidien.preparer_le_recap_du_lieu

        def preparer_puis_poser_le_marqueur(*arguments):
            recap = preparer_reel(*arguments)
            Configuration.objects.update(recap_quotidien_traite_le=date(2026, 10, 13))
            return recap

        with patch(
            "Administration.recap_quotidien.preparer_le_recap_du_lieu",
            side_effect=preparer_puis_poser_le_marqueur,
        ):
            resultat, mailer, _pdf = self._appeler_a(
                heure_de_paris(2026, 10, 13, 7, 10)
            )

        assert resultat is False
        assert mailer.call_count == 0

    def test_une_erreur_de_calcul_ne_pose_pas_le_marqueur(self):
        self._faire_un_z_hier_soir()

        with patch(
            "Administration.recap_quotidien.rubriques_de_la_veille",
            side_effect=RuntimeError("calcul en panne"),
        ):
            with self.assertRaises(RuntimeError):
                self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert self._le_marqueur() is None

    # --- Les pièces jointes / Attachments ---

    def test_les_z_sont_en_piece_jointe(self):
        z_manuel = self._faire_un_z_hier_soir()
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 23, 30))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 13, 4, 10))
        filet = ClotureCaisse.objects.get(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            numero_sequentiel__gt=z_manuel.numero_sequentiel,
        )

        resultat, mailer, pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert resultat is True
        assert pdf.call_count == 2
        fichiers = mailer.call_args.kwargs["attached_files"]
        assert sorted(fichiers.keys()) == sorted(
            [
                f"z-{z_manuel.numero_sequentiel}.pdf",
                f"z-{filet.numero_sequentiel}.pdf",
            ]
        )

    # --- La langue / Language ---

    def test_le_mail_est_dans_la_langue_du_lieu(self):
        configuration = Configuration.get_solo()
        configuration.language = "en"
        configuration.save()
        self._faire_un_z_hier_soir()
        langues_a_la_construction = []

        def construire_le_mailer(**arguments):
            langues_a_la_construction.append(translation.get_language())
            return SimpleNamespace(send=lambda: True)

        resultat, _mailer, _pdf = self._appeler_a(
            heure_de_paris(2026, 10, 13, 7, 10), effet_du_mailer=construire_le_mailer
        )

        assert resultat is True
        assert langues_a_la_construction == ["en"]

    # --- Le gabarit / Template ---

    def test_le_gabarit_montre_les_rubriques_et_les_z(self):
        self._faire_un_z_hier_soir()
        rubrique_de_test = {
            "cle": "nouvelles_adhesions",
            "titre": "Nouvelles adhésions",
            "est_un_stock": True,
            "nombre": 12,
            "nombre_de_nouveaux": 3,
            "lignes": ["Alice — Cotisation — Valide"],
            "nombre_de_lignes_cachees": 11,
            "lien": "https://exemple.test/admin/BaseBillet/membership/",
        }
        pages_rendues = []

        def construire_le_mailer(**arguments):
            pages_rendues.append(
                render_to_string(arguments["template"], arguments["context"])
            )
            return SimpleNamespace(send=lambda: True)

        with patch(
            "Administration.recap_quotidien.rubriques_de_la_veille",
            return_value=[rubrique_de_test],
        ):
            self._appeler_a(
                heure_de_paris(2026, 10, 13, 7, 10),
                effet_du_mailer=construire_le_mailer,
            )

        page = pages_rendues[0]
        assert "Nouvelles adhésions (12)" in page
        assert "dont 3 nouvelles hier" in page
        assert "Alice" in page
        assert "et 11 autres" in page
        assert "https://exemple.test/admin/BaseBillet/membership/" in page
        assert "Ticket Z n°" in page
        assert "3,50" in page

    def test_le_gabarit_echappe_les_noms_saisis(self):
        self._faire_un_z_hier_soir()
        rubrique_de_test = {
            "cle": "nouvelles_adhesions",
            "titre": "Nouvelles adhésions",
            "est_un_stock": False,
            "nombre": 1,
            "nombre_de_nouveaux": 1,
            "lignes": ["<b>x</b> — Cotisation — Valide"],
            "nombre_de_lignes_cachees": 0,
            "lien": "https://exemple.test/admin/",
        }
        pages_rendues = []

        def construire_le_mailer(**arguments):
            pages_rendues.append(
                render_to_string(arguments["template"], arguments["context"])
            )
            return SimpleNamespace(send=lambda: True)

        with patch(
            "Administration.recap_quotidien.rubriques_de_la_veille",
            return_value=[rubrique_de_test],
        ):
            self._appeler_a(
                heure_de_paris(2026, 10, 13, 7, 10),
                effet_du_mailer=construire_le_mailer,
            )

        assert "&lt;b&gt;x&lt;/b&gt;" in pages_rendues[0]
        assert "<b>x</b>" not in pages_rendues[0]


class TestBranchementEtFusion(RecapQuotidienTestCase):
    """
    Le récap est appelé à la fin de la tâche horaire du lieu, après le filet J.
    Une J ne demande plus de mail séparé : son Z part dans le récap du matin.
    Les H, M et A gardent leur mail.
    / The recap runs at the end of the venue's hourly task, after the J net.
    A J no longer requests its own mail; H, M and A keep theirs.

    LOCALISATION : tests/pytest/test_recap_quotidien.py
    """

    # Les outils de la classe des Z : mêmes J fabriquées par le vrai moteur.
    # / Same helpers as the Z test class.
    _vendre_des_jus_a = TestZContenuDestinataires._vendre_des_jus_a
    _cloturer_a = TestZContenuDestinataires._cloturer_a
    _lancer_la_tache_horaire_a = TestZContenuDestinataires._lancer_la_tache_horaire_a

    def setUp(self):
        super().setUp()
        Configuration.objects.update(recap_quotidien_traite_le=None)
        Configuration.clear_cache()
        configuration = Configuration.get_solo()
        configuration.module_billetterie = True
        configuration.module_adhesion = True
        configuration.save()
        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )

    def _regler_les_rapports(self, periodicite):
        """
        Un destinataire de rapport et une périodicité.
        / A report recipient and a periodicity.
        """
        configuration = Configuration.get_solo()
        configuration.rapport_emails = "compta@example.org"
        configuration.rapport_periodicite = periodicite
        configuration.save()

    def _lancer_la_tache_horaire_avec_le_mailer_remplace_a(self, moment):
        """
        La tâche horaire du lieu à `moment`, avec le mailer et le PDF du récap
        remplacés (aucun mail réel). Rend la classe du mailer remplacée.
        / The hourly task at `moment`, recap mailer and PDF mocked; returns the mailer.
        """

        def faux_pdf(cloture):
            return (b"pdf", f"z-{cloture.numero_sequentiel}.pdf", "application/pdf")

        with patch(
            "Administration.recap_quotidien.generer_pdf_cloture",
            side_effect=faux_pdf,
        ):
            with patch(
                "Administration.recap_quotidien.CeleryMailerClass"
            ) as mailer_remplace:
                mailer_remplace.return_value.send.return_value = True
                self._lancer_la_tache_horaire_a(moment)
        return mailer_remplace

    def test_la_tache_horaire_envoie_le_recap_avec_le_filet_de_ce_matin(self):
        """
        Fermeture à 5 h : seuil du filet à 7 h. Une vente dimanche 23 h : la tâche
        horaire de lundi 7 h 10 crée la J du filet de lundi (finie lundi 7 h, PILE au
        seuil de la veille de mardi). Une vente lundi 23 h, aucun Z manuel : la tâche
        horaire de mardi 7 h 10 crée la J du filet de mardi, puis le récap part avec le
        PDF de cette J seule (la J de lundi est hors de la fenêtre des Z de mardi).
        / Closing at 5 am (net at 7 am). Monday's net J ends exactly at Tuesday's lower
        bound; Tuesday's 7:10 run creates Tuesday's net J and the recap carries its PDF
        only.
        """
        configuration = Configuration.get_solo()
        configuration.heure_de_fermeture = time(5, 0)
        configuration.save()
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 11, 23, 0))
        self._lancer_la_tache_horaire_avec_le_mailer_remplace_a(
            heure_de_paris(2026, 10, 12, 7, 10)
        )
        filet_de_lundi = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        assert filet_de_lundi.datetime_fin == heure_de_paris(2026, 10, 12, 7, 0)
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 23, 0))

        mailer_remplace = self._lancer_la_tache_horaire_avec_le_mailer_remplace_a(
            heure_de_paris(2026, 10, 13, 7, 10)
        )

        filet_de_mardi = ClotureCaisse.objects.get(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            numero_sequentiel__gt=filet_de_lundi.numero_sequentiel,
        )
        assert filet_de_mardi.datetime_fin == heure_de_paris(2026, 10, 13, 7, 0)
        assert mailer_remplace.call_count == 1
        fichiers = mailer_remplace.call_args.kwargs["attached_files"]
        assert list(fichiers.keys()) == [f"z-{filet_de_mardi.numero_sequentiel}.pdf"]
        assert Configuration.objects.get().recap_quotidien_traite_le == date(2026, 10, 13)

    def test_une_j_ne_demande_plus_de_mail_separe(self):
        """
        Périodicité journalière avec un destinataire : une J ne demande aucune tâche
        de mail (son Z part dans le récap du matin).
        / Daily periodicity with a recipient: a J requests no mail task.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 20, 0))
        j_d_hier_soir = self._cloturer_a(heure_de_paris(2026, 10, 12, 23, 0))
        self._regler_les_rapports(Configuration.PERIODICITE_JOURNALIER)

        with taches_celery_enregistrees() as taches_demandees:
            comptabilite.tasks.demander_l_email_automatique_si_configure(
                self.tenant.schema_name, j_d_hier_soir
            )

        assert taches_demandees == []

    def test_une_h_demande_toujours_son_mail(self):
        """
        Périodicité hebdomadaire avec un destinataire : la clôture de la semaine
        demande toujours son mail.
        / Weekly periodicity with a recipient: the week closure still requests its mail.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 7, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 12, 4, 10))
        semaine = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_HEBDOMADAIRE)
        self._regler_les_rapports(Configuration.PERIODICITE_HEBDOMADAIRE)

        with taches_celery_enregistrees() as taches_demandees:
            comptabilite.tasks.demander_l_email_automatique_si_configure(
                self.tenant.schema_name, semaine
            )

        assert taches_demandees == [
            ("envoyer_email_cloture", (self.tenant.schema_name, str(semaine.uuid))),
        ]
