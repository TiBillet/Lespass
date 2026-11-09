"""
tests/pytest/test_recap_quotidien.py
Le récap du matin des admins : un mail par lieu qui résume la veille.
/ The admins' morning recap: one mail per venue summarising yesterday.

LOCALISATION : tests/pytest/test_recap_quotidien.py

Spécifications : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md (chantier 01)
et TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/CHANTIER-02-recap-allege.md (chantier 02).

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
    compteurs_de_la_periode,
    destinataires_du_recap,
    envoyer_le_recap_du_lieu_si_c_est_l_heure,
    lien_des_reglages_des_envois,
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
from fabriques_vente import (  # noqa: E402
    abonner_aux_envois_des_rapports,
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
)
from comptabilite.models import ClotureCaisse, ConfigurationDesRapports  # noqa: E402
from inventaire.models import MouvementStock, Stock, TypeMouvement  # noqa: E402
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
        configuration.email = "lieu@example.org"
        configuration.save()

        # Les réglages des envois : tout coché, aucun destinataire. Les cases sont
        # réécrites ici, leur cache survit au rollback (comme celui de la configuration).
        # / Mail settings: all ticked, no recipient; rewritten because of the cache.
        abonner_aux_envois_des_rapports()


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

    # --- Adhésions en attente ---

    def test_adhesions_en_attente_ne_montre_que_les_demandes_d_hier(self):
        # Même en attente, un objet n'est dans le récap que le lendemain de sa création.
        self._adhesion(self.hier, status=Membership.ADMIN_WAITING)
        self._adhesion(self.avant_hier, status=Membership.ADMIN_WAITING)
        self._adhesion(self.aujourd_hui, status=Membership.ADMIN_WAITING)
        rubrique = self._rubrique("adhesions_en_attente")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/BaseBillet/membership/"

    def test_adhesions_en_attente_ignore_les_autres_statuts(self):
        for statut in [Membership.ONCE, Membership.ADMIN_VALID, Membership.CANCELED]:
            with self.subTest(statut=statut):
                self._adhesion(self.hier, status=statut)
                assert self._rubrique("adhesions_en_attente") is None

    def test_une_demande_d_adhesion_d_hier_est_en_attente_et_pas_dans_les_nouvelles(self):
        self._adhesion(self.hier, status=Membership.ADMIN_WAITING)
        assert self._rubrique("nouvelles_adhesions") is None
        assert self._rubrique("adhesions_en_attente")["nombre"] == 1

    def test_une_vieille_demande_en_attente_n_est_plus_dans_le_recap(self):
        self._adhesion(self.avant_hier, status=Membership.ADMIN_WAITING)
        assert self._rubrique("adhesions_en_attente") is None

    def test_une_demande_en_attente_n_ecrit_pas_son_statut(self):
        # Le titre de la rubrique dit déjà « en attente ».
        adherent = creer_utilisateur(prenom="Lea", nom="Martin")
        adhesion = self._adhesion(
            self.hier, status=Membership.ADMIN_WAITING, user=adherent
        )
        with translation.override("fr"):
            ligne = self._rubrique("adhesions_en_attente")["lignes"][0]
        assert ligne == f"Lea Martin — {adhesion.price.product.name}"

    def test_une_adhesion_sans_personne_ne_fait_pas_planter(self):
        self._adhesion(self.hier, user=None)
        rubrique = self._rubrique("nouvelles_adhesions")
        assert len(rubrique["lignes"]) == 1
        with translation.override("fr"):
            rubrique = self._rubrique("nouvelles_adhesions")
        assert "(sans nom)" in rubrique["lignes"][0]

    def test_une_rubrique_de_six_lignes_en_montre_cinq(self):
        for _numero in range(6):
            self._adhesion(self.hier)
        rubrique = self._rubrique("nouvelles_adhesions")
        assert rubrique["nombre"] == 6
        assert len(rubrique["lignes"]) == 5
        assert rubrique["nombre_de_lignes_cachees"] == 1

    # --- Le statut sur une ligne ---

    def test_une_adhesion_au_statut_normal_n_ecrit_pas_son_statut(self):
        adhesion = self._adhesion(self.hier, status=Membership.ONCE)
        with translation.override("fr"):
            ligne = self._rubrique("nouvelles_adhesions")["lignes"][0]
            statut = adhesion.get_status_display()
        assert statut not in ligne
        assert ligne.count(" — ") == 1

    def test_une_adhesion_au_statut_intermediaire_ecrit_son_statut(self):
        adhesion = self._adhesion(self.hier, status=Membership.PAYMENT_PENDING)
        with translation.override("fr"):
            ligne = self._rubrique("nouvelles_adhesions")["lignes"][0]
            statut = adhesion.get_status_display()
        assert ligne.endswith(f" — {statut}")

    def test_une_reservation_confirmee_n_ecrit_pas_son_statut(self):
        self._reservation(self.hier, status=Reservation.VALID)
        ligne = self._rubrique("nouvelles_reservations")["lignes"][0]
        assert ligne.count(" — ") == 1

    def test_une_reservation_gratuite_non_confirmee_ecrit_son_statut(self):
        reservation = self._reservation(self.hier, status=Reservation.FREERES)
        with translation.override("fr"):
            ligne = self._rubrique("nouvelles_reservations")["lignes"][0]
            statut = reservation.get_status_display()
        assert ligne.endswith(f" — {statut}")

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

    # --- Demandes de réservation en attente ---

    def test_une_demande_de_reservation_d_hier_est_en_attente_et_pas_dans_les_nouvelles(self):
        self._booking(self.hier, status=Booking.ADMIN_WAITING)
        assert self._rubrique("nouvelles_reservations_de_ressources") is None
        rubrique = self._rubrique("demandes_de_reservation_en_attente")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == (
            f"https://{self.DOMAINE}/admin/booking/booking/?status__exact=WA"
        )

    def test_demandes_de_reservation_en_attente_ne_montre_que_celles_d_hier(self):
        self._booking(self.hier, status=Booking.ADMIN_WAITING)
        self._booking(self.avant_hier, status=Booking.ADMIN_WAITING)
        self._booking(self.aujourd_hui, status=Booking.ADMIN_WAITING)
        assert self._rubrique("demandes_de_reservation_en_attente")["nombre"] == 1

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
        # Publié est l'état normal : la ligne ne porte que le nom.
        evenement = self._evenement(self.hier, published=True, is_proposal=False)
        rubrique = self._rubrique("nouveaux_evenements")
        assert rubrique["nombre"] == 1
        assert rubrique["lignes"][0] == evenement.name

    def test_une_proposition_d_hier_n_a_pas_de_rubrique_a_part(self):
        # Elle est dans « Nouveaux événements », marquée « proposition en attente ».
        self._evenement(self.hier, published=False, is_proposal=True)
        cles = []
        for rubrique in rubriques_de_la_veille(self.debut, self.fin, self.DOMAINE):
            cles.append(rubrique["cle"])
        assert cles == ["nouveaux_evenements"]

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

    # --- Tombés en rupture hier ---

    def _mouvement(self, moment, avant, variation, type_mouvement=TypeMouvement.VE, stock=None):
        """
        Un mouvement de stock écrit à `moment` : de `avant` à `avant + variation`.
        / A stock movement written at `moment`.
        """
        if stock is None:
            produit = creer_tarif_vendu(nom="TEST_recap Biere").productsold.product
            stock = Stock.objects.create(product=produit, quantite=avant + variation)
        mouvement = MouvementStock.objects.create(
            stock=stock,
            type_mouvement=type_mouvement,
            quantite=variation,
            quantite_avant=avant,
        )
        MouvementStock.objects.filter(pk=mouvement.pk).update(cree_le=moment)
        return stock

    def test_un_article_passe_de_3_a_0_hier_est_tombe_en_rupture(self):
        stock = self._mouvement(self.hier, avant=3, variation=-3)
        rubrique = self._rubrique("ruptures_de_stock")
        assert rubrique["nombre"] == 1
        assert rubrique["lignes"] == [stock.product.name]
        assert rubrique["nombre_de_lignes_cachees"] == 0
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/inventaire/stock/"

    def test_un_article_passe_de_3_a_moins_2_hier_est_tombe_en_rupture(self):
        self._mouvement(self.hier, avant=3, variation=-5)
        assert self._rubrique("ruptures_de_stock")["nombre"] == 1

    def test_un_article_deja_a_zero_n_est_pas_tombe_hier(self):
        self._mouvement(self.hier, avant=0, variation=-1)
        assert self._rubrique("ruptures_de_stock") is None

    def test_une_rupture_d_avant_hier_ou_d_aujourd_hui_n_est_pas_dans_le_recap(self):
        self._mouvement(self.avant_hier, avant=3, variation=-3)
        self._mouvement(self.aujourd_hui, avant=3, variation=-3)
        assert self._rubrique("ruptures_de_stock") is None

    def test_un_article_tombe_deux_fois_hier_n_est_nomme_qu_une_fois(self):
        stock = self._mouvement(self.hier, avant=2, variation=-2)
        self._mouvement(self.hier, avant=5, variation=-5, stock=stock)
        rubrique = self._rubrique("ruptures_de_stock")
        assert rubrique["nombre"] == 1
        assert rubrique["lignes"] == [stock.product.name]

    def test_un_ajustement_d_inventaire_n_est_pas_une_rupture(self):
        self._mouvement(self.hier, avant=5, variation=-5, type_mouvement=TypeMouvement.AJ)
        assert self._rubrique("ruptures_de_stock") is None

    def test_sept_ruptures_tiennent_sur_une_ligne_avec_et_2_autres(self):
        noms = []
        for _numero in range(7):
            noms.append(self._mouvement(self.hier, avant=1, variation=-1).product.name)
        with translation.override("fr"):
            rubrique = self._rubrique("ruptures_de_stock")
        noms_tries = sorted(noms)
        assert rubrique["nombre"] == 7
        assert rubrique["lignes"] == [", ".join(noms_tries[:5]) + " et 2 autres"]
        assert rubrique["nombre_de_lignes_cachees"] == 0

    # --- Les compteurs des rapports H et M ---

    def test_les_compteurs_de_la_periode_lisent_les_memes_sources_que_le_recap(self):
        self._adhesion(self.hier)
        self._adhesion(self.hier)
        self._adhesion(self.avant_hier)
        self._evenement(self.hier, published=False, is_proposal=True)
        self._evenement(self.hier)
        self._mouvement(self.hier, avant=1, variation=-1)
        with translation.override("fr"):
            compteurs = compteurs_de_la_periode(self.debut, self.fin)
        assert compteurs == [
            "2 nouvelles adhésions",
            "2 nouveaux événements (dont 1 proposition)",
            "1 article tombé en rupture",
        ]

    def test_sans_activite_il_n_y_a_aucun_compteur(self):
        self._adhesion(self.avant_hier)
        assert compteurs_de_la_periode(self.debut, self.fin) == []


def _assert_argent_rendu(ligne, montant_attendu):
    """
    La ligne d'un remboursement finit par « remboursé » et le montant en positif :
    jamais de signe moins.
    / A refund line ends with "remboursé" and the positive amount: never a minus sign.
    """
    montant_de_la_ligne = ligne.split(" — ")[-1]
    assert montant_de_la_ligne == f"remboursé {montant_attendu}\u00a0€"
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

    def _projet(self, moment, devise="€", nom=None):
        if nom is None:
            nom = f"TEST_recap projet {identifiant_unique()}"
        return Initiative.objects.create(name=nom, created_at=moment, currency=devise)

    def _ancien_projet(self, projet, devise="€"):
        """Le projet donné, sinon un projet d'avant-hier. / Given project or an old one."""
        if projet is None:
            return self._projet(self.avant_hier, devise)
        return projet

    def _ligne_de_budget(
        self, moment, state=BudgetItem.State.REQUESTED, devise="€", projet=None
    ):
        return BudgetItem.objects.create(
            initiative=self._ancien_projet(projet, devise),
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
        projet=None,
    ):
        if contributeur == "par defaut":
            contributeur = creer_utilisateur()
        return Contribution.objects.create(
            initiative=self._ancien_projet(projet, devise),
            contributor=contributeur,
            contributor_name=nom_du_contributeur,
            amount=2500,
            payment_status=statut,
            paid_at=paye_le,
            created_at=self.avant_hier,
        )

    def _vote(self, moment, projet=None):
        return Vote.objects.create(
            initiative=self._ancien_projet(projet),
            user=creer_utilisateur(),
            created_at=moment,
        )

    def _participation(self, moment, state=Participation.State.REQUESTED, projet=None):
        return Participation.objects.create(
            initiative=self._ancien_projet(projet),
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

    # --- Financement participatif ---

    def _ligne_du_projet(self, projet):
        """La ligne d'un projet dans la rubrique, en français. / A project's line."""
        with translation.override("fr"):
            rubrique = self._rubrique("financement_participatif")
        for ligne in rubrique["lignes"]:
            if ligne.startswith(f"{projet.name} — "):
                return ligne
        return None

    def test_un_projet_cree_hier_est_un_nouveau_projet(self):
        projet = self._projet(self.hier)
        self._projet(self.avant_hier)
        self._projet(self.aujourd_hui)
        rubrique = self._rubrique("financement_participatif")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/crowds/initiative/"
        assert self._ligne_du_projet(projet) == f"{projet.name} — nouveau projet"

    def test_un_projet_sans_activite_hier_n_est_pas_dans_le_recap(self):
        projet = self._projet(self.avant_hier)
        self._vote(self.avant_hier, projet=projet)
        self._contribution(self.aujourd_hui, projet=projet)
        assert self._rubrique("financement_participatif") is None

    def test_les_votes_et_contributions_d_un_projet_tiennent_sur_une_ligne(self):
        projet = self._projet(self.avant_hier)
        self._vote(self.hier, projet=projet)
        self._vote(self.hier, projet=projet)
        self._contribution(self.hier, projet=projet)
        assert self._rubrique("financement_participatif")["nombre"] == 1
        assert self._ligne_du_projet(projet) == (
            f"{projet.name} — 1 contribution (25,00\u00a0€), 2 votes"
        )

    def test_les_lignes_de_budget_disent_combien_sont_a_valider(self):
        projet = self._projet(self.avant_hier)
        self._ligne_de_budget(self.hier, projet=projet)
        self._ligne_de_budget(self.hier, state=BudgetItem.State.APPROVED, projet=projet)
        assert self._ligne_du_projet(projet) == (
            f"{projet.name} — 2 lignes de budget dont 1 à valider"
        )

    def test_les_participations_disent_combien_sont_a_valider(self):
        projet = self._projet(self.avant_hier)
        self._participation(self.hier, projet=projet)
        assert self._ligne_du_projet(projet) == (
            f"{projet.name} — 1 participation dont 1 à valider"
        )

    def test_une_contribution_en_heures_s_ecrit_en_heures(self):
        projet = self._projet(self.avant_hier, devise="heures")
        self._contribution(self.hier, projet=projet)
        ligne = self._ligne_du_projet(projet)
        assert "25,00\u00a0heures" in ligne
        assert "€" not in ligne

    def test_contributions_payees_accepte_paye_et_indique_comme_paye(self):
        projet = self._projet(self.avant_hier)
        self._contribution(self.hier, statut=Contribution.PaymentStatus.PAID, projet=projet)
        self._contribution(
            self.hier, statut=Contribution.PaymentStatus.PAID_ADMIN, projet=projet
        )
        assert "2 contributions (50,00\u00a0€)" in self._ligne_du_projet(projet)

    def test_une_contribution_en_attente_ne_compte_pas(self):
        self._contribution(None, statut=Contribution.PaymentStatus.PENDING)
        assert self._rubrique("financement_participatif") is None

    def test_une_contribution_creee_avant_hier_et_payee_hier_compte(self):
        self._contribution(self.hier)
        assert self._rubrique("financement_participatif")["nombre"] == 1

    def test_les_projets_les_plus_actifs_d_abord(self):
        projet_calme = self._projet(self.avant_hier, nom="TEST_recap A calme")
        projet_actif = self._projet(self.avant_hier, nom="TEST_recap B actif")
        self._vote(self.hier, projet=projet_calme)
        for _numero in range(3):
            self._vote(self.hier, projet=projet_actif)
        lignes = self._rubrique("financement_participatif")["lignes"]
        assert lignes[0].startswith(projet_actif.name)
        assert lignes[1].startswith(projet_calme.name)

    # --- Annulations et remboursements ---

    def _rubrique_des_annulations(self):
        with translation.override("fr"):
            return self._rubrique("annulations_et_remboursements")

    def test_annulations_compte_hier_et_pas_avant_hier_ni_aujourd_hui(self):
        for moment in [self.hier, self.avant_hier, self.aujourd_hui]:
            reservation = self._reservation_payee_en_especes()
            Reservation.objects.filter(pk=reservation.pk).update(annulee_le=moment)
        rubrique = self._rubrique("annulations_et_remboursements")
        assert rubrique["nombre"] == 1
        assert rubrique["lien"] == f"https://{self.DOMAINE}/admin/BaseBillet/vente/"

    def test_annulations_ne_liste_pas_ce_qui_n_a_pas_de_date_d_annulation(self):
        # Statut annulé mais `annulee_le` vide (annulation automatique) : exclu.
        reservation = self._reservation_payee_en_especes()
        Reservation.objects.filter(pk=reservation.pk).update(
            status=Reservation.CANCELED, annulee_le=None
        )
        assert self._rubrique("annulations_et_remboursements") is None

    def test_annulations_reunit_reservations_bookings_et_adhesions_avec_leur_statut(self):
        reservation = self._reservation_payee_en_especes()
        Reservation.objects.filter(pk=reservation.pk).update(annulee_le=self.hier)
        ressource = creer_ressource_avec_tarif()
        booking = Booking.objects.create(
            resource=ressource.ressource,
            user=creer_utilisateur(),
            start_datetime=ressource.debut_du_creneau,
            slot_duration_minutes=60,
            slot_count=1,
            status=Booking.USER_CANCELED,
        )
        Booking.objects.filter(pk=booking.pk).update(annulee_le=self.hier)
        adhesion = Membership.objects.create(
            price=creer_adhesion().tarif,
            user=creer_utilisateur(),
            status=Membership.ADMIN_CANCELED,
        )
        Membership.objects.filter(pk=adhesion.pk).update(annulee_le=self.hier)
        rubrique = self._rubrique_des_annulations()
        assert rubrique["nombre"] == 3
        texte_des_lignes = "\n".join(rubrique["lignes"])
        assert reservation.event.name in texte_des_lignes
        assert ressource.ressource.name in texte_des_lignes
        assert adhesion.price.product.name in texte_des_lignes
        # Le statut réel dit qui a annulé.
        # / The real status tells who cancelled.
        with translation.override("fr"):
            assert booking.get_status_display() in texte_des_lignes
            assert adhesion.get_status_display() in texte_des_lignes

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
        rubrique = self._rubrique("annulations_et_remboursements")
        assert adhesion.price.product.name in rubrique["lignes"][0]
        assert reservation.event.name in rubrique["lignes"][1]

    def test_une_annulation_remboursee_hier_tient_sur_une_seule_ligne(self):
        reservation = self._reservation_payee_en_especes()
        self._annuler_avec_avoir_hier(reservation)
        rubrique = self._rubrique_des_annulations()
        assert rubrique["nombre"] == 1
        assert reservation.event.name in rubrique["lignes"][0]
        _assert_argent_rendu(rubrique["lignes"][0], "10,00")

    def test_le_montant_rembourse_est_l_argent_rendu(self):
        # 10 € dont 4 € offerts : l'argent rendu est 6 €, pas 10 €.
        reservation = self._reservation_payee_en_especes(part_offerte=400)
        self._annuler_avec_avoir_hier(reservation)
        rubrique = self._rubrique_des_annulations()
        _assert_argent_rendu(rubrique["lignes"][0], "6,00")
        assert "10,00" not in rubrique["lignes"][0]

    def test_une_annulation_sans_argent_ecrit_son_statut_sans_rembourse(self):
        reservation = self._reservation_gratuite_annulee_hier()
        rubrique = self._rubrique_des_annulations()
        assert rubrique["nombre"] == 1
        assert "remboursé" not in rubrique["lignes"][0]
        with translation.override("fr"):
            statut = Reservation.objects.get(pk=reservation.pk).get_status_display()
        assert rubrique["lignes"][0].endswith(f" — {statut}")

    def test_un_avoir_d_hier_sur_un_objet_annule_avant_hier_a_sa_ligne(self):
        # L'objet n'est pas annulé hier : la ligne d'avoir d'hier le nomme quand même.
        reservation = self._reservation_payee_en_especes()
        self._annuler_avec_avoir_hier(reservation)
        Reservation.objects.filter(pk=reservation.pk).update(annulee_le=self.avant_hier)
        rubrique = self._rubrique_des_annulations()
        assert rubrique["nombre"] == 1
        assert rubrique["lignes"][0].startswith(reservation.event.name)
        _assert_argent_rendu(rubrique["lignes"][0], "10,00")

    def test_un_avoir_de_caisse_d_hier_nomme_l_article(self):
        tarif_vendu = self._ligne_de_caisse_remboursee(self.hier)
        self._ligne_de_caisse_remboursee(self.avant_hier)
        self._ligne_de_caisse_remboursee(self.aujourd_hui)
        rubrique = self._rubrique_des_annulations()
        assert rubrique["nombre"] == 1
        assert tarif_vendu.productsold.product.name in rubrique["lignes"][0]
        _assert_argent_rendu(rubrique["lignes"][0], "5,00")

    def test_une_vente_d_hier_n_est_pas_un_remboursement(self):
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
                assert self._rubrique("annulations_et_remboursements") is None

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

    def test_une_rubrique_d_annulations_de_six_lignes_en_montre_cinq(self):
        for _numero in range(6):
            reservation = self._reservation_payee_en_especes()
            Reservation.objects.filter(pk=reservation.pk).update(annulee_le=self.hier)
        rubrique = self._rubrique("annulations_et_remboursements")
        assert rubrique["nombre"] == 6
        assert len(rubrique["lignes"]) == 5
        assert rubrique["nombre_de_lignes_cachees"] == 1

def une_rubrique(cle):
    """Une rubrique minimale pour `le_recap_a_du_contenu`. / A minimal section."""
    return {"cle": cle}


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

    def test_une_rubrique_en_attente_est_du_contenu(self):
        # Elle ne porte que des demandes d'hier : elle suffit à envoyer le récap.
        rubriques = [une_rubrique("adhesions_en_attente")]
        assert le_recap_a_du_contenu(rubriques, []) is True

    def test_une_rubrique_de_nouveautes_est_du_contenu(self):
        rubriques = [une_rubrique("nouvelles_reservations")]
        assert le_recap_a_du_contenu(rubriques, []) is True

    def test_un_z_seul_est_du_contenu(self):
        assert le_recap_a_du_contenu([], ["un Z"]) is True

    # --- Les destinataires / Recipients ---

    def test_les_destinataires_sont_la_liste_des_reglages_des_envois(self):
        abonner_aux_envois_des_rapports("second@example.org", "premier@example.org")
        assert destinataires_du_recap() == ["premier@example.org", "second@example.org"]

    def test_un_admin_hors_de_la_liste_ne_recoit_rien(self):
        # Plus d'admin d'office, plus de repli sur l'e-mail du lieu.
        self._creer_un_admin("admin@example.org")
        assert destinataires_du_recap() == []

    def test_les_adresses_sont_en_minuscules_sans_espaces_ni_doublon_ni_vide(self):
        compta, sans_adresse = abonner_aux_envois_des_rapports(
            "compta@example.org", "vide@example.org"
        )
        TibilletUser.objects.filter(pk=compta.pk).update(email=" Compta@Example.org ")
        TibilletUser.objects.filter(pk=sans_adresse.pk).update(email="")
        assert destinataires_du_recap() == ["compta@example.org"]

    def test_une_personne_qui_n_est_plus_du_lieu_ne_recoit_plus_rien(self):
        # La liste passe par le manager de HumanUser, filtré sur `client_achat`.
        (personne,) = abonner_aux_envois_des_rapports("partie@example.org")
        personne.client_achat.remove(self.tenant)
        assert destinataires_du_recap() == []

    def test_le_formulaire_refuse_une_personne_d_un_autre_lieu(self):
        # Le queryset du champ (HumanUser.objects, filtré sur le lieu) valide les pk
        # postés : un pk forcé vers une personne d'ailleurs est refusé.
        from django.forms import modelform_factory

        personne_d_ailleurs = TibilletUser.objects.create(
            email="ailleurs@example.org", username="ailleurs@example.org"
        )
        (personne_du_lieu,) = abonner_aux_envois_des_rapports("ici@example.org")
        Formulaire = modelform_factory(ConfigurationDesRapports, fields=["destinataires"])
        reglages_des_envois = ConfigurationDesRapports.get_solo()

        formulaire_d_ailleurs = Formulaire(
            data={"destinataires": [str(personne_d_ailleurs.pk)]},
            instance=reglages_des_envois,
        )
        formulaire_du_lieu = Formulaire(
            data={"destinataires": [str(personne_du_lieu.pk)]},
            instance=reglages_des_envois,
        )

        assert formulaire_d_ailleurs.is_valid() is False
        assert "destinataires" in formulaire_d_ailleurs.errors
        assert formulaire_du_lieu.is_valid() is True


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
        abonner_aux_envois_des_rapports("destinataire@example.org")
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
        assert arguments["email"] == ["destinataire@example.org"]
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
        Une vieille demande en attente + un Z d'avant-hier (hors fenêtre) :
        ni mail, ni PDF, mais le marqueur est posé.
        / An old pending request + a Z from the day before yesterday.
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
        ConfigurationDesRapports.get_solo().destinataires.clear()
        self._faire_un_z_hier_soir()

        with self.assertLogs("Administration.recap_quotidien", level="WARNING"):
            resultat, mailer, pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert resultat is False
        assert mailer.call_count == 0
        assert pdf.call_count == 0
        assert self._le_marqueur() == date(2026, 10, 13)

    def test_recap_decoche_rien_ne_part_et_le_marqueur_n_est_pas_pose(self):
        abonner_aux_envois_des_rapports("destinataire@example.org", recap_quotidien=False)
        self._faire_un_z_hier_soir()

        resultat, mailer, pdf = self._appeler_a(heure_de_paris(2026, 10, 13, 7, 10))

        assert resultat is False
        assert mailer.call_count == 0
        assert pdf.call_count == 0
        assert self._le_marqueur() is None

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
            "nombre": 12,
            "lignes": ["Alice — Cotisation"],
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
        assert "Alice" in page
        assert "et 11 autres" in page
        assert "Ticket Z n°" in page
        assert "3,50" in page
        # Le titre est le lien de la rubrique. Plus de bouton par rubrique : le fond
        # bleu du bouton a disparu du gabarit.
        # / The title is the section link. No more per-section button.
        assert 'href="https://exemple.test/admin/BaseBillet/membership/"' in page
        assert "background:#2d76a6" not in page
        # Le pied porte le lien de désabonnement : la page des réglages des envois.
        # / The footer carries the unsubscribe link.
        assert 'data-testid="recap-desabonnement"' in page
        assert "/admin/comptabilite/configurationdesrapports/" in page

    def test_le_gabarit_echappe_les_noms_saisis(self):
        self._faire_un_z_hier_soir()
        rubrique_de_test = {
            "cle": "nouvelles_adhesions",
            "titre": "Nouvelles adhésions",
            "nombre": 1,
            "lignes": ["<b>x</b> — Cotisation"],
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
        abonner_aux_envois_des_rapports("destinataire@example.org")
        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )

    def _regler_les_rapports(self, niveau):
        """
        Un destinataire de rapport, et seul l'envoi de ce niveau coché (J = le récap du
        matin, H, M ou A = le rapport de clôture).
        / A report recipient, and only this level's mail ticked.
        """
        abonner_aux_envois_des_rapports(
            "compta@example.org",
            recap_quotidien=niveau == ClotureCaisse.NIVEAU_JOURNALIER,
            hebdomadaire=niveau == ClotureCaisse.NIVEAU_HEBDOMADAIRE,
            mensuel=niveau == ClotureCaisse.NIVEAU_MENSUEL,
            annuel=niveau == ClotureCaisse.NIVEAU_ANNUEL,
        )

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
        Récap du matin coché, avec un destinataire : une J ne demande aucune tâche de
        mail (son Z part dans le récap du matin).
        / Morning recap ticked, with a recipient: a J requests no mail task.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 12, 20, 0))
        j_d_hier_soir = self._cloturer_a(heure_de_paris(2026, 10, 12, 23, 0))
        self._regler_les_rapports(ClotureCaisse.NIVEAU_JOURNALIER)

        with taches_celery_enregistrees() as taches_demandees:
            comptabilite.tasks.demander_l_email_automatique_si_configure(
                self.tenant.schema_name, j_d_hier_soir
            )

        assert taches_demandees == []

    def test_une_h_demande_toujours_son_mail(self):
        """
        Rapport hebdomadaire coché, avec un destinataire : la clôture de la semaine
        demande son mail.
        / Weekly report ticked, with a recipient: the week closure requests its mail.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 7, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 12, 4, 10))
        semaine = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_HEBDOMADAIRE)
        self._regler_les_rapports(ClotureCaisse.NIVEAU_HEBDOMADAIRE)

        with taches_celery_enregistrees() as taches_demandees:
            comptabilite.tasks.demander_l_email_automatique_si_configure(
                self.tenant.schema_name, semaine
            )

        assert taches_demandees == [
            ("envoyer_email_cloture", (self.tenant.schema_name, str(semaine.uuid))),
        ]

    def test_une_h_decochee_ne_demande_pas_son_mail(self):
        """
        Seul le rapport mensuel est coché : la clôture de la semaine ne demande rien.
        / Only the monthly report is ticked: the week closure requests nothing.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 7, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 12, 4, 10))
        semaine = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_HEBDOMADAIRE)
        self._regler_les_rapports(ClotureCaisse.NIVEAU_MENSUEL)

        with taches_celery_enregistrees() as taches_demandees:
            comptabilite.tasks.demander_l_email_automatique_si_configure(
                self.tenant.schema_name, semaine
            )

        assert taches_demandees == []

    def test_une_h_cochee_sans_destinataire_ne_demande_pas_son_mail(self):
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 7, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 12, 4, 10))
        semaine = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_HEBDOMADAIRE)
        ConfigurationDesRapports.get_solo().destinataires.clear()

        with taches_celery_enregistrees() as taches_demandees:
            comptabilite.tasks.demander_l_email_automatique_si_configure(
                self.tenant.schema_name, semaine
            )

        assert taches_demandees == []


class TestCompteursDesRapportsHebdomadairesEtMensuels(RecapQuotidienTestCase):
    """
    Le mail de la clôture H ou M porte les compteurs de l'activité de sa période,
    sans détail. Il est rendu dans la langue du lieu.
    / The H or M closure mail carries its period's activity counters, without
    detail, in the venue's language.

    LOCALISATION : tests/pytest/test_recap_quotidien.py
    """

    # Les outils de la classe des Z : mêmes clôtures fabriquées par le vrai moteur.
    # / Same helpers as the Z test class.
    _vendre_des_jus_a = TestZContenuDestinataires._vendre_des_jus_a
    _lancer_la_tache_horaire_a = TestZContenuDestinataires._lancer_la_tache_horaire_a
    _regler_les_rapports = TestBranchementEtFusion._regler_les_rapports

    def setUp(self):
        super().setUp()
        Configuration.objects.update(recap_quotidien_traite_le=None)
        Configuration.clear_cache()
        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        # La semaine du lundi 5 au lundi 12 octobre : une vente le mercredi, puis la
        # tâche horaire du lundi 12 à 4 h 10 crée la clôture de la semaine.
        # / The week of 5-12 October, closed by Monday's 4:10 hourly task.
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 7, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 10, 12, 4, 10))
        self.semaine = ClotureCaisse.objects.get(
            niveau=ClotureCaisse.NIVEAU_HEBDOMADAIRE
        )
        self._regler_les_rapports(ClotureCaisse.NIVEAU_HEBDOMADAIRE)

    def _adhesion_creee_a(self, moment):
        adhesion = Membership.objects.create(
            price=creer_adhesion().tarif, user=None, status=Membership.ONCE
        )
        Membership.objects.filter(pk=adhesion.pk).update(date_added=moment)

    def _envoyer_le_mail_de_la_semaine(self):
        """
        Envoie le mail de la semaine, avec le mailer et le PDF remplacés.
        Rend (pages rendues, langues actives à la construction du mailer).
        / Sends the week's mail, mailer and PDF mocked.
        """
        pages_rendues = []
        langues_a_la_construction = []

        def construire_le_mailer(**arguments):
            pages_rendues.append(
                render_to_string(arguments["template"], arguments["context"])
            )
            langues_a_la_construction.append(translation.get_language())
            return SimpleNamespace(send=lambda: 1)

        with patch(
            "comptabilite.pdf.generer_pdf_cloture",
            return_value=(b"pdf", "cloture-test.pdf", "application/pdf"),
        ):
            with patch(
                "comptabilite.tasks.CeleryMailerClass", side_effect=construire_le_mailer
            ):
                mail_envoye = comptabilite.tasks.envoyer_email_cloture(
                    self.tenant.schema_name, str(self.semaine.uuid)
                )
        assert mail_envoye is True
        return pages_rendues, langues_a_la_construction

    def test_le_mail_de_la_semaine_compte_l_activite_de_sa_periode_seulement(self):
        self._adhesion_creee_a(heure_de_paris(2026, 10, 8, 12, 0))
        self._adhesion_creee_a(heure_de_paris(2026, 10, 12, 14, 0))

        pages_rendues, _langues = self._envoyer_le_mail_de_la_semaine()

        assert "1 nouvelle adhésion" in pages_rendues[0]
        assert "2 nouvelles adhésions" not in pages_rendues[0]

    def test_le_mail_de_la_semaine_porte_le_lien_de_desabonnement(self):
        pages_rendues, _langues = self._envoyer_le_mail_de_la_semaine()
        lien = lien_des_reglages_des_envois(self.tenant.get_primary_domain().domain)
        assert 'data-testid="cloture-desabonnement"' in pages_rendues[0]
        assert f'href="{lien}"' in pages_rendues[0]

    def test_le_mail_de_la_semaine_decoche_n_est_pas_envoye(self):
        self._regler_les_rapports(ClotureCaisse.NIVEAU_MENSUEL)
        with patch("comptabilite.tasks.CeleryMailerClass") as mailer_remplace:
            mail_envoye = comptabilite.tasks.envoyer_email_cloture(
                self.tenant.schema_name, str(self.semaine.uuid)
            )
        assert mail_envoye is False
        assert mailer_remplace.call_count == 0

    def test_sans_activite_le_mail_de_la_semaine_n_a_pas_de_bloc(self):
        pages_rendues, _langues = self._envoyer_le_mail_de_la_semaine()
        assert "activité de la période" not in pages_rendues[0]

    def test_le_mail_de_cloture_est_dans_la_langue_du_lieu(self):
        configuration = Configuration.get_solo()
        configuration.language = "en"
        configuration.save()

        _pages, langues_a_la_construction = self._envoyer_le_mail_de_la_semaine()

        assert langues_a_la_construction == ["en"]


class TestPageDesReglagesDesEnvois(RecapQuotidienTestCase):
    """
    La page « Envoi des rapports » de l'admin, et sa recherche de destinataires
    limitée aux personnes du lieu.
    / The "Envoi des rapports" admin page, and its recipient search limited to the
    venue's people.

    LOCALISATION : tests/pytest/test_recap_quotidien.py
    """

    def setUp(self):
        super().setUp()
        # `TibilletUser` vit dans le schéma public ; il est annulé avec le test.
        # / TibilletUser lives in the public schema; rolled back with the test.
        self.administrateur = TibilletUser.objects.create(
            email="admin-reglages-envois@example.org",
            username="admin-reglages-envois@example.org",
            is_staff=True,
            is_active=True,
        )
        self.administrateur.client_admin.add(self.tenant)
        self.administrateur.client_achat.add(self.tenant)
        self.client_de_l_admin = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        self.client_de_l_admin.force_login(self.administrateur)

    def test_la_page_des_reglages_s_ouvre_pour_un_admin_du_lieu(self):
        reponse = self.client_de_l_admin.get(
            reverse("staff_admin:comptabilite_configurationdesrapports_changelist")
        )
        assert reponse.status_code == 200
        page = reponse.content.decode()
        assert 'name="envoyer_le_recap_quotidien"' in page
        assert 'name="destinataires"' in page

    def test_le_lien_des_mails_est_l_adresse_de_la_page(self):
        lien = lien_des_reglages_des_envois("exemple.test")
        chemin = reverse("staff_admin:comptabilite_configurationdesrapports_changelist")
        assert lien == f"https://exemple.test{chemin}"

    def test_la_liste_des_clotures_propose_le_bouton_des_reglages(self):
        reponse = self.client_de_l_admin.get(
            reverse("staff_admin:comptabilite_cloturecaisse_changelist")
        )
        assert reponse.status_code == 200
        assert 'data-testid="comptabilite-bouton-reglages-des-envois"' in (
            reponse.content.decode()
        )

    def test_la_recherche_ne_propose_que_les_personnes_du_lieu(self):
        personne_du_lieu = TibilletUser.objects.create(
            email="autocompletion-ici@example.org",
            username="autocompletion-ici@example.org",
        )
        personne_du_lieu.client_achat.add(self.tenant)
        TibilletUser.objects.create(
            email="autocompletion-ailleurs@example.org",
            username="autocompletion-ailleurs@example.org",
        )

        reponse = self.client_de_l_admin.get(
            "/admin/autocomplete/",
            {
                "app_label": "comptabilite",
                "model_name": "configurationdesrapports",
                "field_name": "destinataires",
                "term": "autocompletion",
            },
        )

        assert reponse.status_code == 200
        identifiants_proposes = []
        for resultat in reponse.json()["results"]:
            identifiants_proposes.append(resultat["id"])
        assert identifiants_proposes == [str(personne_du_lieu.pk)]
