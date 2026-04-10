"""
Validation d'une nouvelle réservation avant création de la ligne Booking.
/ Validation of a new booking before creating the Booking row.

LOCALISATION : booking/booking_validator.py

Ce module est appelé par la vue "ajouter au panier" (Session 10).
Il réutilise le moteur de calcul (slot_engine) pour ne pas dupliquer
la logique d'ouverture et de fermeture.
/ This module is called by the "add to basket" view (Session 10).
It reuses the slot engine to avoid duplicating opening/closure logic.

FLUX D'APPEL / CALL FLOW :
  validate_new_booking(resource, start_datetime, slot_duration_minutes,
                       slot_count, member, reference_date=None)
    └─ compute_slots(resource, date_from, date_to, reference_date)   [slot_engine]
         → dict { (start_datetime, slot_duration_minutes) → Slot }
         → vérification créneau par créneau / per-slot check

RÈGLES VÉRIFIÉES / RULES CHECKED :
  Chaque créneau de la série est vérifié de la même façon :
  1. Il s'aligne exactement sur un créneau théorique
     (même start_datetime, même slot_duration_minutes).
     Un créneau absent = non ouvert, fermé, ou hors horizon.
     compute_slots gère déjà l'horizon, les fermetures et les ouvertures.
  2. Il a une remaining_capacity > 0.
  / Each slot in the series is checked the same way:
  / 1. It aligns exactly to a theoretical slot
  /    (same start_datetime, same slot_duration_minutes).
  /    An absent slot = not in opening, closed, or beyond horizon.
  /    compute_slots already enforces horizon, closures and openings.
  / 2. It has remaining_capacity > 0.
"""
import datetime

from django.utils.translation import gettext_lazy as _

from booking.slot_engine import compute_slots


def validate_new_booking(resource, start_datetime, slot_duration_minutes, slot_count, member,
                         reference_date=None):
    """
    Vérifie qu'une demande de réservation est valide avant création.
    / Checks that a booking request is valid before creation.

    LOCALISATION : booking/booking_validator.py

    :param resource:               instance Resource
    :param start_datetime:         datetime timezone-aware — début du premier créneau
                                   / timezone-aware datetime — start of the first slot
    :param slot_duration_minutes:  int — durée de chaque créneau en minutes
                                   / duration of each slot in minutes
    :param slot_count:             int — nombre de créneaux consécutifs demandés
                                   / number of consecutive slots requested
    :param member:                 utilisateur qui réserve / user making the booking
    :param reference_date:         datetime.date | None — date de référence pour le
                                   calcul de l'horizon (voir §13 dans finding.md).
                                   None = date du jour réelle.
                                   / reference date for horizon calculation (see §13).
                                   None = real today.
    :return: tuple (is_valid: bool, error: str | None)
    """
    # --- Calcul de la plage de dates à couvrir ---
    # date_from : jour du premier créneau.
    # date_to   : dernier jour réellement occupé par la période entière,
    #             calculé avec (fin − 1 µs).date().
    #             Un créneau se terminant exactement à minuit n'occupe pas
    #             le lendemain — cohérent avec la sémantique semi-ouverte [)
    #             gérée par Interval.overlaps() dans slot_engine.
    # / date_from : day of the first slot.
    # / date_to   : last day actually occupied by the whole period,
    # /             using (end − 1 µs).date().
    # /             A slot ending exactly at midnight does not occupy the next
    # /             day — consistent with half-open [) semantics in Interval.overlaps().
    last_slot_end_dt = start_datetime + datetime.timedelta(
        minutes=slot_duration_minutes * slot_count
    )
    date_from = start_datetime.date()
    date_to = (last_slot_end_dt - datetime.timedelta(microseconds=1)).date()

    # compute_slots applique l'horizon, les fermetures et les capacités.
    # reference_date est transmis pour permettre les tests avec dates fixes (§13).
    # / compute_slots enforces horizon, closures and capacities.
    # reference_date is threaded through to allow fixed-date tests (§13).
    available_slots = compute_slots(resource, date_from, date_to,
                                    reference_date=reference_date)

    # Dictionnaire d'accès rapide :
    # clé = (start, duration_minutes) → BookableInterval
    # / Fast-lookup dict:
    # key = (start, duration_minutes) → BookableInterval
    slot_by_key = {
        (slot.start, slot.duration_minutes()): slot
        for slot in available_slots
    }

    # Vérification créneau par créneau — même règle pour tous.
    # / Per-slot check — same rule for every slot.
    for i in range(slot_count):
        requested_start = start_datetime + datetime.timedelta(
            minutes=i * slot_duration_minutes
        )
        lookup_key = (requested_start, slot_duration_minutes)

        # Règle 1 : le créneau doit exister dans les créneaux théoriques.
        # Absent = start non aligné, durée incorrecte, jour fermé ou hors horizon.
        # / Rule 1: the slot must exist among the theoretical slots.
        # Absent = misaligned start, wrong duration, closed day, or beyond horizon.
        if lookup_key not in slot_by_key:
            return False, str(_(
                'Slot starting at %(start)s is not available.'
            ) % {'start': requested_start})

        # Règle 2 : le créneau doit avoir de la capacité restante.
        # / Rule 2: the slot must have remaining capacity.
        if slot_by_key[lookup_key].remaining_capacity <= 0:
            return False, str(_(
                'Slot starting at %(start)s is fully booked.'
            ) % {'start': requested_start})

    return True, None
