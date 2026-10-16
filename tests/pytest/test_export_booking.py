"""
tests/pytest/test_export_booking.py
Export des réservations de ressources : date et heures lisibles, à l'heure du lieu.
/ Resource bookings export: readable date and times, in venue time.

LOCALISATION : tests/pytest/test_export_booking.py

Ces tests n'écrivent RIEN en base : les Booking sont construits en mémoire,
end_datetime est posé à la main (save() n'est pas appelé).
Seule la Configuration du tenant est lue.
/ Nothing is written: bookings are built in memory, only the Configuration is read.

Lancement / Run:
    poetry run pytest /DjangoFiles/tests/pytest/test_export_booking.py -v
"""

import datetime
import zoneinfo

import pytest
from django_tenants.utils import tenant_context

from Administration.importers.resources_bookings_exporters import BookingExportResource
from BaseBillet.models import Configuration
from booking.models import Booking, Resource
from Customers.models import Client as TenantClient


@pytest.fixture
def tenant():
    """Le tenant de développement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


def _booking_en_memoire(debut_utc, duree_en_minutes, fuseau_du_lieu):
    """
    Un Booking non sauvé, avec ses dates déjà calculées.
    / An unsaved Booking, with its dates already computed.
    """
    booking = Booking(
        resource=Resource(name="Salle de répétition"),
        start_datetime=debut_utc,
        slot_duration_minutes=duree_en_minutes,
        slot_count=1,
        status=Booking.PAID_BY_USER,
        first_name=None,
        last_name="Dupont",
    )
    booking.end_datetime = debut_utc + datetime.timedelta(minutes=duree_en_minutes)
    booking.booked_at = debut_utc
    return booking


@pytest.mark.django_db
def test_les_heures_de_debut_et_de_fin_sont_a_l_heure_du_lieu(tenant):
    """Un créneau 12h00 -> 13h30 UTC sort aux heures locales du lieu.
    / A 12:00 -> 13:30 UTC slot is exported in venue local times."""
    with tenant_context(tenant):
        fuseau_du_lieu = zoneinfo.ZoneInfo(Configuration.get_solo().fuseau_horaire)
        debut_utc = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)
        booking = _booking_en_memoire(debut_utc, 90, fuseau_du_lieu)

        heure_de_debut_attendue = debut_utc.astimezone(fuseau_du_lieu).strftime("%H:%M")
        fin_utc = debut_utc + datetime.timedelta(minutes=90)
        heure_de_fin_attendue = fin_utc.astimezone(fuseau_du_lieu).strftime("%H:%M")

        assert booking.start_time_display() == heure_de_debut_attendue
        assert booking.end_time_display() == heure_de_fin_attendue


@pytest.mark.django_db
def test_un_creneau_apres_minuit_est_date_du_jour_local(tenant):
    """23h30 UTC le 15 est le 16 dans un fuseau à l'est de UTC.
    / 23:30 UTC on the 15th is the 16th east of UTC."""
    with tenant_context(tenant):
        fuseau_du_lieu = zoneinfo.ZoneInfo(Configuration.get_solo().fuseau_horaire)
        debut_utc = datetime.datetime(2026, 7, 15, 23, 30, tzinfo=datetime.timezone.utc)
        booking = _booking_en_memoire(debut_utc, 60, fuseau_du_lieu)

        date_attendue = debut_utc.astimezone(fuseau_du_lieu).strftime("%d/%m/%Y")
        assert booking.date_display() == date_attendue


@pytest.mark.django_db
def test_la_ligne_exportee_est_lisible(tenant):
    """Les colonnes sortent en clair : heures, libellé du statut, cases vides sans « None ».
    / Columns are readable: times, status label, empty cells instead of "None"."""
    with tenant_context(tenant):
        fuseau_du_lieu = zoneinfo.ZoneInfo(Configuration.get_solo().fuseau_horaire)
        debut_utc = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)
        booking = _booking_en_memoire(debut_utc, 90, fuseau_du_lieu)

        ressource_d_export = BookingExportResource()
        ressource_d_export.before_export(queryset=[])

        champs = ressource_d_export.fields
        assert (
            ressource_d_export.export_field(champs["heure_de_debut"], booking)
            == booking.start_time_display()
        )
        assert (
            ressource_d_export.export_field(champs["heure_de_fin"], booking)
            == booking.end_time_display()
        )
        assert ressource_d_export.export_field(champs["duree"], booking) == "90min"
        assert (
            ressource_d_export.export_field(champs["ressource"], booking)
            == "Salle de répétition"
        )
        assert ressource_d_export.export_field(champs["statut"], booking) == str(
            booking.get_status_display()
        )
        assert ressource_d_export.export_field(champs["prenom"], booking) == ""
        assert ressource_d_export.export_field(champs["nom"], booking) == "Dupont"


@pytest.mark.django_db
def test_le_total_paye_sort_avec_deux_decimales_et_une_virgule(tenant):
    """1250 centimes -> « 12,50 » ; 0 -> « 0,00 » ; un remboursement reste négatif.
    / 1250 cents -> "12,50"; 0 -> "0,00"; a refund stays negative."""
    with tenant_context(tenant):
        debut_utc = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)
        booking = _booking_en_memoire(debut_utc, 60, None)
        ressource_d_export = BookingExportResource()
        champ_total_paye = ressource_d_export.fields["total_paye"]

        booking.total_paye_en_centimes = 1250
        assert ressource_d_export.export_field(champ_total_paye, booking) == "12,50"

        booking.total_paye_en_centimes = 0
        assert ressource_d_export.export_field(champ_total_paye, booking) == "0,00"

        booking.total_paye_en_centimes = -500
        assert ressource_d_export.export_field(champ_total_paye, booking) == "-5,00"


@pytest.mark.django_db
def test_la_somme_sql_de_l_export_egale_total_paid(tenant, rf):
    """La somme calculée par la base pour l'export donne le même montant que
    Booking.total_paid(), pour chaque réservation du tenant. Lecture seule.
    / The export SQL sum equals Booking.total_paid() for every booking. Read only."""
    from Administration.admin.resources import BookingAdmin
    from Administration.admin.site import staff_admin_site

    with tenant_context(tenant):
        admin_des_bookings = BookingAdmin(Booking, staff_admin_site)
        requete = rf.get("/admin/booking/booking/export/")
        requete.user = None
        queryset_de_l_export = admin_des_bookings.get_export_queryset(requete)

        ressource_d_export = BookingExportResource()
        champ_total_paye = ressource_d_export.fields["total_paye"]
        for booking in queryset_de_l_export:
            total_attendu = f"{booking.total_paid() or 0:.2f}".replace(".", ",")
            assert (
                ressource_d_export.export_field(champ_total_paye, booking)
                == total_attendu
            )
