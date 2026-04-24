"""
Moteur de réservation — logique §3.2 de la spécification.
/ Booking engine — spec §3.2 logic.

LOCALISATION : booking/booking_engine.py

Implémente les quatre ensembles de §3.2 :
  O — complémentaire des ClosedPeriods fusionnées dans la fenêtre
  W — WeeklyOpening déroulé sur O  (w ∈ W ⟺ ∃ o ∈ O, w ⊆ o)
  E — W annoté de la capacité restante par créneau
  B — réservation membre dans E' ; validation + création atomique

Aucun ensemble n'est persisté — calculé à la volée à chaque requête.

Fonctions pures (sans DB) : merge_intervals, compute_open_intervals,
  generate_theoretical_slots, compute_remaining_capacity
Accès DB : get_opening_entries_for_resource, get_closed_periods_for_resource,
  get_existing_bookings_for_resource
Orchestrateurs : compute_slots → E,  validate_new_booking → B + §14
"""
import dataclasses
import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ─── Conteneurs de données / Data containers ─────────────────────────────────

@dataclasses.dataclass(frozen=True)
class Interval:
    """
    Intervalle semi-ouvert [start, end), timezone-aware, immuable.
    / Half-open interval [start, end), timezone-aware, immutable.

    LOCALISATION : booking/booking_engine.py
    """
    start: datetime.datetime
    end:   datetime.datetime

    def overlaps(self, other: 'Interval') -> bool:
        """[a,b) et [c,d) se chevauchent ssi a < d et c < b."""
        return self.start < other.end and other.start < self.end

    def contains(self, other: 'Interval') -> bool:
        """Vrai si other est entièrement dans self."""
        return self.start <= other.start and other.end <= self.end

    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)


@dataclasses.dataclass
class BookableInterval:
    """
    Interval enrichi de la capacité — élément de E.
    / Interval enriched with capacity — element of E.

    LOCALISATION : booking/booking_engine.py
    """
    interval:           Interval
    max_capacity:       int
    remaining_capacity: int

    @property
    def start(self) -> datetime.datetime:
        return self.interval.start

    @property
    def end(self) -> datetime.datetime:
        return self.interval.end

    def duration_minutes(self) -> int:
        return self.interval.duration_minutes()


# ─── O — Intervalles ouverts / Open intervals ────────────────────────────────

def merge_intervals(intervals):
    """
    Fusionne les intervalles qui se chevauchent ou se touchent (pure).
    / Merges overlapping or adjacent intervals (pure).

    LOCALISATION : booking/booking_engine.py

    :param intervals: list[Interval]
    :return: list[Interval] sans chevauchement, ordonné par start
    """
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda i: i.start)
    merged = [sorted_intervals[0]]

    for current in sorted_intervals[1:]:
        last = merged[-1]
        if current.start <= last.end:
            merged[-1] = Interval(start=last.start, end=max(last.end, current.end))
        else:
            merged.append(current)

    return merged


def compute_open_intervals(closed_periods, date_from, date_to, tz):
    """
    Calcule O = complémentaire des ClosedPeriods fusionnées (pure).
    / Computes O = complement of merged ClosedPeriods (pure).

    LOCALISATION : booking/booking_engine.py

    Fenêtre : [date_from, date_to) — les deux sont des datetime tz-aware.
    end_date=None étend la fermeture jusqu'à la fin de la fenêtre (spec §3.2.1).

    Accepte tout itérable avec .start_date et .end_date (date | None) —
    pas besoin d'un modèle Django pour les tests unitaires.

    :param closed_periods: itérable avec .start_date, .end_date (date|None)
    :param date_from: datetime.datetime tz-aware — début exact de la fenêtre
    :param date_to:   datetime.datetime tz-aware — fin exclusive de la fenêtre
    :param tz:        tzinfo — fuseau horaire du tenant
    :return: list[Interval] — O, sans chevauchement, ordonné par start
    """
    window_start = date_from
    window_end   = date_to

    # Dates dérivées pour comparer avec .start_date / .end_date des ClosedPeriods.
    # / Derived dates for comparison with ClosedPeriod .start_date / .end_date.
    date_from_as_date = date_from.date()
    date_to_as_date   = (date_to - datetime.timedelta(microseconds=1)).date()

    closed_intervals = []
    for period in closed_periods:
        period_end_date = period.end_date if period.end_date is not None else date_to_as_date
        clamped_start = max(period.start_date, date_from_as_date)
        clamped_end   = min(period_end_date, date_to_as_date)
        if clamped_start > clamped_end:
            continue
        closed_intervals.append(Interval(
            start=timezone.make_aware(
                datetime.datetime.combine(clamped_start, datetime.time.min), tz
            ),
            end=timezone.make_aware(
                datetime.datetime.combine(
                    clamped_end + datetime.timedelta(days=1), datetime.time.min
                ),
                tz,
            ),
        ))

    open_intervals = []
    current_start = window_start

    for closed in merge_intervals(closed_intervals):
        if closed.start > current_start:
            open_intervals.append(Interval(start=current_start, end=closed.start))
        current_start = closed.end

    if current_start < window_end:
        open_intervals.append(Interval(start=current_start, end=window_end))

    return open_intervals


# ─── W — Créneaux théoriques / Theoretical slots ─────────────────────────────

def generate_theoretical_slots(opening_entries, open_intervals,
                                date_from, date_to, tz):
    """
    Génère W — créneaux théoriques sur les jours ouverts (pure).
    / Generates W — theoretical slots over open days (pure).

    LOCALISATION : booking/booking_engine.py

    Règle W (spec §3.2.2) : w ∈ W ⟺ ∃ o ∈ O, w ⊆ o
    Un créneau qui déborde sur une fermeture est exclu entièrement.
    Un créneau dont le start est avant date_from est exclu (créneaux passés).

    Les starts sont calculés par timedelta (pas par recomposition
    heure/minute) pour supporter les durées > 1440 min.

    Accepte tout itérable avec .weekday, .start_time,
    .slot_duration_minutes, .slot_count — pas de DB.

    :param opening_entries: itérable avec .weekday, .start_time,
                            .slot_duration_minutes, .slot_count
    :param open_intervals:  list[Interval] — O
    :param date_from: datetime.datetime tz-aware — début exact de la fenêtre
    :param date_to:   datetime.datetime tz-aware — fin exclusive de la fenêtre
    :param tz:        tzinfo
    :return: list[BookableInterval] — capacités à 0, remplies par compute_slots
    """
    bookable_intervals = []
    current_date = date_from.date()
    last_date    = (date_to - datetime.timedelta(microseconds=1)).date()

    while current_date <= last_date:
        for entry in opening_entries:
            if entry.weekday != current_date.weekday():
                continue

            base_dt = timezone.make_aware(
                datetime.datetime.combine(current_date, entry.start_time), tz
            )

            for i in range(entry.slot_count):
                start_dt = base_dt + datetime.timedelta(
                    minutes=i * entry.slot_duration_minutes
                )
                end_dt = start_dt + datetime.timedelta(
                    minutes=entry.slot_duration_minutes
                )
                slot_interval = Interval(start=start_dt, end=end_dt)

                # Exclure les créneaux commençant avant la borne de départ.
                # Masque les créneaux passés quand date_from = timezone.now().
                # / Exclude slots starting before the window start.
                # Hides past-today slots when date_from = timezone.now().
                if start_dt < date_from:
                    continue

                # w ∈ W ⟺ ∃ o ∈ O, w ⊆ o  (spec §3.2.2)
                if not any(o.contains(slot_interval) for o in open_intervals):
                    continue

                bookable_intervals.append(BookableInterval(
                    interval=slot_interval,
                    max_capacity=0,
                    remaining_capacity=0,
                ))

        current_date += datetime.timedelta(days=1)

    return bookable_intervals


# ─── E — Capacité restante / Remaining capacity ───────────────────────────────

def compute_remaining_capacity(slot, capacity, existing_bookings):
    """
    Retourne capacity − |{réservations chevauchant slot}|, toujours ≥ 0 (pure).
    / Returns capacity − |{bookings overlapping slot}|, always ≥ 0 (pure).

    LOCALISATION : booking/booking_engine.py

    Chevauchement partiel = chevauchement complet (spec §3.2.3).
    Une réservation multi-créneaux (slot_count > 1) s'étend de
    start_datetime à start_datetime + slot_duration_minutes × slot_count.

    Accepte tout itérable avec .start_datetime, .slot_duration_minutes,
    .slot_count — pas de DB.
    """
    overlap_count = 0
    for booking in existing_bookings:
        booking_interval = Interval(
            start=booking.start_datetime,
            end=booking.start_datetime + datetime.timedelta(
                minutes=booking.slot_duration_minutes * booking.slot_count
            ),
        )
        if slot.interval.overlaps(booking_interval):
            overlap_count += 1

    return max(0, capacity - overlap_count)


# ─── Accès base de données / Database access ─────────────────────────────────

def get_opening_entries_for_resource(resource):
    """
    Retourne resource.weekly_opening.opening_entries.all().
    LOCALISATION : booking/booking_engine.py
    """
    return resource.weekly_opening.opening_entries.all()


def get_closed_periods_for_resource(resource):
    """
    Retourne resource.calendar.closed_periods.all().
    LOCALISATION : booking/booking_engine.py
    """
    return resource.calendar.closed_periods.all()


def get_existing_bookings_for_resource(resource):
    """
    Retourne toutes les réservations actives de la ressource.
    / Returns all active bookings for the resource.

    LOCALISATION : booking/booking_engine.py

    Aucun filtre de date : on charge toutes les réservations de la
    ressource et on laisse compute_remaining_capacity calculer le
    chevauchement exact. Ce n'est pas optimal pour les ressources
    très réservées, mais c'est correct car une réservation peut
    déborder sur un créneau ultérieur (slot_count > 1, finding §15).
    Un filtre précis nécessite end_datetime en base (finding §15) —
    à affiner quand ce champ sera ajouté.

    L'annulation = suppression de ligne, pas de statut cancelled (finding §1).
    """
    from booking.models import Booking

    return Booking.objects.filter(resource=resource)


# ─── Orchestrateurs / Orchestrators ──────────────────────────────────────────

def compute_slots(resource, date_from=None, date_to=None, reference_now=None):
    """
    Calcule E pour la ressource sur [date_from, date_to).
    / Computes E for the resource over [date_from, date_to).

    LOCALISATION : booking/booking_engine.py

    date_from=None → maintenant (timezone.now()).
    date_to=None   → minuit du jour (today + booking_horizon_days + 1).
    reference_now  injecte un datetime fixe dans les tests (finding §13).

    :param date_from: datetime.datetime tz-aware — début exact (défaut : now)
    :param date_to:   datetime.datetime tz-aware — fin exclusive (défaut : fin de l'horizon)
    :param reference_now: datetime.datetime tz-aware — injecté dans les tests
    :return: list[BookableInterval]
    """
    tz  = timezone.get_current_timezone()
    now = reference_now or timezone.now()

    if date_from is None:
        date_from = now
    if date_to is None:
        horizon_end_date = now.date() + datetime.timedelta(days=resource.booking_horizon_days)
        date_to = timezone.make_aware(
            datetime.datetime.combine(
                horizon_end_date + datetime.timedelta(days=1), datetime.time.min
            ),
            tz,
        )

    horizon_cap = timezone.make_aware(
        datetime.datetime.combine(
            now.date() + datetime.timedelta(days=resource.booking_horizon_days + 1),
            datetime.time.min,
        ),
        tz,
    )
    effective_date_to = min(date_to, horizon_cap)

    if effective_date_to <= date_from:
        return []

    opening_entries   = get_opening_entries_for_resource(resource)
    closed_periods    = get_closed_periods_for_resource(resource)
    existing_bookings = get_existing_bookings_for_resource(resource)

    open_intervals = compute_open_intervals(
        closed_periods=closed_periods,
        date_from=date_from,
        date_to=effective_date_to,
        tz=tz,
    )
    bookable_intervals = generate_theoretical_slots(
        opening_entries=opening_entries,
        open_intervals=open_intervals,
        date_from=date_from,
        date_to=effective_date_to,
        tz=tz,
    )

    result = []
    for bookable in bookable_intervals:
        bookable.max_capacity = resource.capacity
        bookable.remaining_capacity = compute_remaining_capacity(
            slot=bookable,
            capacity=resource.capacity,
            existing_bookings=existing_bookings,
        )
        result.append(bookable)

    return result



def validate_new_booking(resource, start_datetime, slot_duration_minutes,
                         slot_count, member, reference_now=None):
    """
    Valide B ⊆ E' et crée la réservation de manière atomique (finding §14).
    / Validates B ⊆ E' and creates the booking atomically (finding §14).

    LOCALISATION : booking/booking_engine.py

    Étape 0 — garde temporelle (§5 Availability) :
      Un créneau déjà commencé (start_datetime <= maintenant) est refusé.
      Pas de délai minimum : un créneau démarrant dans quelques minutes
      est accepté.

    Étape 1 — pré-validation rapide (non atomique) :
      compute_slots → vérifie que chaque créneau de B existe dans E'
      (créneau ouvert, dans l'horizon, bonne durée, capacité > 0).

    Étape 2 — transaction avec verrou sur Resource (finding §14) :
      SELECT FOR UPDATE sur la ligne Resource sérialise les créations
      concurrentes. Re-lit les réservations et re-vérifie la capacité
      avec des données fraîches avant d'insérer.

    reference_now  : datetime fixe pour les tests (finding §13).

    :return: (True, Booking) si créé, (False, str) avec le message d'erreur
    """
    from booking.models import Booking, Resource

    # Refuse tout créneau dont le début est passé ou est maintenant.
    # / Reject any slot whose start time is in the past or right now.
    now = reference_now or timezone.now()
    if start_datetime <= now:
        return False, str(_('Cannot book a slot that has already started.'))

    last_slot_end_dt = start_datetime + datetime.timedelta(
        minutes=slot_duration_minutes * slot_count
    )
    # date_from / date_to sont des datetime (borne exclusive).
    # date_to = last_slot_end_dt car la convention est [date_from, date_to) exclusif.
    # Un créneau finissant à minuit a end = 00:00 qui est exactement dans la fenêtre.
    # / date_from / date_to are datetimes (exclusive upper bound).
    # date_to = last_slot_end_dt since the convention is [date_from, date_to) exclusive.
    date_from = start_datetime
    date_to   = last_slot_end_dt

    # ── Étape 1 : pré-validation ──────────────────────────────────────────────
    slot_by_key = {
        (slot.start, slot.duration_minutes()): slot
        for slot in compute_slots(resource, date_from, date_to,
                                  reference_now=reference_now)
    }

    for i in range(slot_count):
        requested_start = start_datetime + datetime.timedelta(
            minutes=i * slot_duration_minutes
        )
        lookup_key = (requested_start, slot_duration_minutes)

        if lookup_key not in slot_by_key:
            return False, str(_(
                'Slot starting at %(start)s is not available.'
            ) % {'start': requested_start})

        if slot_by_key[lookup_key].remaining_capacity <= 0:
            return False, str(_(
                'Slot starting at %(start)s is fully booked.'
            ) % {'start': requested_start})

    # ── Étape 2 : création atomique (finding §14) ─────────────────────────────
    with transaction.atomic():
        Resource.objects.select_for_update().get(pk=resource.pk)

        fresh_bookings = get_existing_bookings_for_resource(resource)

        for i in range(slot_count):
            slot_start = start_datetime + datetime.timedelta(
                minutes=i * slot_duration_minutes
            )
            slot_end = slot_start + datetime.timedelta(minutes=slot_duration_minutes)

            fresh_remaining = compute_remaining_capacity(
                slot=BookableInterval(
                    interval=Interval(start=slot_start, end=slot_end),
                    max_capacity=resource.capacity,
                    remaining_capacity=0,
                ),
                capacity=resource.capacity,
                existing_bookings=fresh_bookings,
            )

            if fresh_remaining <= 0:
                return False, str(_(
                    'Slot starting at %(start)s is no longer available.'
                ) % {'start': slot_start})

        new_booking = Booking.objects.create(
            resource=resource,
            user=member,
            start_datetime=start_datetime,
            slot_duration_minutes=slot_duration_minutes,
            slot_count=slot_count,
            status=Booking.STATUS_NEW,
        )

    return True, new_booking
