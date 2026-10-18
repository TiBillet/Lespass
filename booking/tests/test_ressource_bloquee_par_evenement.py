"""
Un événement qui bloque une ressource rend complets les créneaux qu'il chevauche.
/ An event blocking a resource makes the overlapping slots full.

LOCALISATION : booking/tests/test_ressource_bloquee_par_evenement.py

Code testé : booking/booking_engine.py, compute_slots() et validate_new_booking(),
via Event.ressource_bloquee (BaseBillet/models.py).

Scénario commun : une salle de capacité 2, ouverte le lundi de 9 h à 12 h en
trois créneaux d'une heure. Un concert occupe la salle de 10 h 15 à 10 h 45.

    09:00       10:00       11:00       12:00
      ├── [0] ───┼── [1] ───┼── [2] ───┤   capacité = 2
                   ├concert┤
    [0] = 2   [1] = 0   [2] = 2

Event.save() lit connection.tenant : on utilise tenant_context, jamais
schema_context (qui pose un FakeTenant, cf. tests/PIEGES.md).
/ Event.save() reads connection.tenant: tenant_context, never schema_context.

Lancement / Run:
    docker exec lespass_django poetry run pytest booking/tests/test_ressource_bloquee_par_evenement.py -v
"""
import datetime

import pytest
from django_tenants.utils import tenant_context

from booking.booking_engine import Interval
from booking.tests.test_booking_engine import (
    MONDAY_NEAR,
    REFERENCE_NOW,
    TEST_PREFIX,
    _add_opening_entry,
    _cleanup,
    _get_test_user,
    _make_aware_dt,
    _make_calendar,
    _make_resource,
    _make_weekly_opening,
)


def _creer_salle_ouverte_le_lundi_matin(nom):
    """
    Salle de capacité 2, trois créneaux d'une heure le lundi à partir de 9 h.
    / Capacity-2 room, three one-hour slots on Monday from 9 am.
    """
    calendrier = _make_calendar(nom)
    semaine_d_ouverture = _make_weekly_opening(nom)
    salle = _make_resource(nom, calendrier, semaine_d_ouverture, capacity=2, horizon=28)
    _add_opening_entry(
        semaine_d_ouverture,
        weekday=0,
        start_time=datetime.time(9, 0),
        slot_duration_minutes=60,
        slot_count=3,
    )
    return salle


def _creer_concert_dans_la_salle(salle, publie=True, archive=False):
    """
    Concert de 10 h 15 à 10 h 45 le lundi MONDAY_NEAR, qui bloque la salle.
    / Concert from 10:15 to 10:45 on MONDAY_NEAR, blocking the room.
    """
    from BaseBillet.models import Event

    return Event.objects.create(
        name=f"{TEST_PREFIX} concert",
        datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 15)),
        end_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 45)),
        ressource_bloquee=salle,
        published=publie,
        archived=archive,
    )


def _places_restantes_par_creneau(salle):
    """
    Les places restantes des trois créneaux du lundi MONDAY_NEAR, dans l'ordre.
    / Remaining capacity of the three MONDAY_NEAR slots, in order.
    """
    from booking.booking_engine import compute_slots

    fenetre_du_lundi = Interval(
        _make_aware_dt(MONDAY_NEAR, datetime.time(0, 0)),
        _make_aware_dt(MONDAY_NEAR + datetime.timedelta(days=1), datetime.time(0, 0)),
    )
    creneaux = compute_slots(salle, fenetre_du_lundi, reference_now=REFERENCE_NOW)
    places_restantes = []
    for creneau in creneaux:
        places_restantes.append(creneau.remaining_capacity)
    return places_restantes


def _supprimer_les_evenements_de_test():
    from BaseBillet.models import Event

    Event.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_le_creneau_chevauche_par_l_evenement_est_complet_les_autres_restent_libres(tenant):
    """
    Seul le créneau 10 h - 11 h, chevauché par le concert, tombe à 0 place.
    / Only the 10-11 slot, overlapped by the concert, drops to 0.
    """
    with tenant_context(tenant):
        try:
            salle = _creer_salle_ouverte_le_lundi_matin("bloquee_chevauchement")
            _creer_concert_dans_la_salle(salle)

            assert _places_restantes_par_creneau(salle) == [2, 0, 2]
        finally:
            _supprimer_les_evenements_de_test()
            _cleanup()


@pytest.mark.django_db
def test_un_evenement_non_publie_bloque_deja_la_salle(tenant):
    """
    Un concert en brouillon occupe déjà la salle.
    / A draft concert already occupies the room.
    """
    with tenant_context(tenant):
        try:
            salle = _creer_salle_ouverte_le_lundi_matin("bloquee_brouillon")
            _creer_concert_dans_la_salle(salle, publie=False)

            assert _places_restantes_par_creneau(salle) == [2, 0, 2]
        finally:
            _supprimer_les_evenements_de_test()
            _cleanup()


@pytest.mark.django_db
def test_un_evenement_archive_ne_bloque_plus_la_salle(tenant):
    """
    Un concert archivé libère la salle.
    / An archived concert frees the room.
    """
    with tenant_context(tenant):
        try:
            salle = _creer_salle_ouverte_le_lundi_matin("bloquee_archive")
            _creer_concert_dans_la_salle(salle, archive=True)

            assert _places_restantes_par_creneau(salle) == [2, 2, 2]
        finally:
            _supprimer_les_evenements_de_test()
            _cleanup()


@pytest.mark.django_db
def test_la_reservation_d_un_creneau_bloque_est_refusee(tenant):
    """
    Réserver le créneau 10 h - 11 h pendant le concert est refusé.
    / Booking the 10-11 slot during the concert is refused.
    """
    from booking.booking_engine import validate_new_booking

    with tenant_context(tenant):
        try:
            salle = _creer_salle_ouverte_le_lundi_matin("bloquee_validation")
            _creer_concert_dans_la_salle(salle)

            reservation_acceptee, erreur, _url_stripe = validate_new_booking(
                resource=salle,
                price=salle.product.prices.get(),
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert reservation_acceptee is False
            assert erreur is not None
        finally:
            _supprimer_les_evenements_de_test()
            _cleanup()
