"""
Moteur de calcul de créneaux disponibles pour une ressource.
/ Slot computation engine for a bookable resource.

LOCALISATION : booking/slot_engine.py

Ce module est pur Python (pas de vues, pas de formulaires). Il est
appelé par les vues de réservation pour afficher les créneaux disponibles.
/ This module is pure Python (no views, no forms). It is called by
booking views to display available slots.

FLUX D'APPEL / CALL FLOW :
  compute_slots(resource, date_from, date_to)
    ├─ get_opening_entries_for_resource(resource)        [DB]
    ├─ get_closed_intervals_for_resource(resource, ...)  [DB]
    ├─ get_existing_bookings_for_resource(resource, ...) [DB]
    ├─ generate_theoretical_slots(...)                   [pur / pure]
    └─ compute_remaining_capacity(slot, ...)             [pur / pure]

DECISIONS :
  §2  — start_datetime est timezone-aware (DateTimeField, pas date+time)
  §7  — un créneau est généré uniquement si chaque jour qu'il intersecte
         est ouvert ; vérification slot par slot, pas par entry
  §8  — ClosedPeriod.end_date peut être None (fermeture sans fin)
"""
import dataclasses
import datetime

from django.utils import timezone


@dataclasses.dataclass(frozen=True)
class Interval:
    """
    Intervalle de temps semi-ouvert [start, end).
    / Half-open time interval [start, end).

    LOCALISATION : booking/slot_engine.py

    Immuable et hashable grâce à frozen=True — peut être utilisé comme
    clé de dictionnaire ou élément de set.
    Les deux bornes doivent être timezone-aware (decisions §2).
    / Immutable and hashable via frozen=True — usable as dict key or set element.
    Both bounds must be timezone-aware (decisions §2).
    """
    start: datetime.datetime   # timezone-aware, borne inférieure incluse / inclusive lower bound
    end:   datetime.datetime   # timezone-aware, borne supérieure exclue / exclusive upper bound

    def overlaps(self, other: 'Interval') -> bool:
        """
        Vrai si les deux intervalles se chevauchent.
        [a, b) et [c, d) se chevauchent ssi a < d et c < b.
        / True if the two intervals overlap.
        [a, b) and [c, d) overlap iff a < d and c < b.
        """
        return self.start < other.end and other.start < self.end

    def contains(self, other: 'Interval') -> bool:
        """
        Vrai si other est entièrement contenu dans cet intervalle.
        self.start ≤ other.start et other.end ≤ self.end.
        / True if other is entirely contained within this interval.
        self.start ≤ other.start and other.end ≤ self.end.
        """
        return self.start <= other.start and other.end <= self.end

    def duration_minutes(self) -> int:
        """
        Durée de l'intervalle en minutes entières (arrondi vers le bas).
        / Duration of the interval in whole minutes (floor).
        """
        return int((self.end - self.start).total_seconds() / 60)


@dataclasses.dataclass
class BookableInterval:
    """
    Créneau réservable : un Interval avec une capacité maximale et une
    capacité restante calculée à la volée.
    / Bookable slot: an Interval with max capacity and remaining capacity
    computed on the fly.

    LOCALISATION : booking/slot_engine.py

    Composé à partir d'un Interval (pas d'héritage) pour éviter de porter
    la capacité sur les intervalles purs (fenêtres d'ouverture, créneaux
    hebdomadaires). Voir design §4 dans tibillet-booking-logic-design.md.
    / Composed from an Interval (no inheritance) to avoid attaching capacity
    to pure intervals (open-day windows, weekly slots).
    See design §4 in tibillet-booking-logic-design.md.
    """
    interval:           Interval
    max_capacity:       int
    remaining_capacity: int

    @property
    def start(self) -> datetime.datetime:
        """Délègue à interval.start. / Delegates to interval.start."""
        return self.interval.start

    @property
    def end(self) -> datetime.datetime:
        """Délègue à interval.end. / Delegates to interval.end."""
        return self.interval.end

    def duration_minutes(self) -> int:
        """Délègue à interval.duration_minutes(). / Delegates to interval.duration_minutes()."""
        return self.interval.duration_minutes()



def get_closed_intervals_for_resource(resource, date_from, date_to):
    """
    Retourne la liste des intervalles fermés dans [date_from, date_to].
    / Returns the list of closed Intervals within [date_from, date_to].

    LOCALISATION : booking/slot_engine.py

    Chaque ClosedPeriod devient un Interval timezone-aware :
      [start_clamped 00:00 local, end_clamped+1 00:00 local)
    Utilise le fuseau courant (timezone.get_current_timezone()), cohérent
    avec generate_theoretical_slots qui construit les créneaux dans ce même fuseau.
    Si end_date est None, la fermeture s'étend jusqu'à date_to (decisions §8).
    Les intervalles sont ensuite comparés avec Interval.overlaps() — pas de
    conversion jour-par-jour.
    / Each ClosedPeriod becomes a timezone-aware Interval:
      [start_clamped 00:00 local, end_clamped+1 00:00 local)
    Uses the current timezone (timezone.get_current_timezone()), consistent
    with generate_theoretical_slots which builds slots in the same timezone.
    If end_date is None, the closure extends to date_to (decisions §8).
    Intervals are then compared with Interval.overlaps() — no day-by-day loop.

    :param resource: instance Resource
    :param date_from: datetime.date — borne inférieure incluse / lower bound (inclusive)
    :param date_to:   datetime.date — borne supérieure incluse / upper bound (inclusive)
    :return: list[Interval]
    """
    tz = timezone.get_current_timezone()
    closed_intervals = []

    for period in resource.calendar.closed_periods.all():
        period_start = period.start_date
        # Si end_date est None, la fermeture court jusqu'à date_to.
        # / If end_date is None, closure runs to date_to.
        period_end = period.end_date if period.end_date is not None else date_to

        # On se limite à la fenêtre demandée.
        # / Clamp to the requested window.
        start_clamped = max(period_start, date_from)
        end_clamped = min(period_end, date_to)

        if start_clamped > end_clamped:
            # La période est entièrement hors de la fenêtre.
            # / Period is entirely outside the window.
            continue

        # [start_clamped 00:00 local, end_clamped+1 00:00 local)
        interval_start = timezone.make_aware(
            datetime.datetime.combine(start_clamped, datetime.time(0, 0)), tz
        )
        interval_end = timezone.make_aware(
            datetime.datetime.combine(
                end_clamped + datetime.timedelta(days=1), datetime.time(0, 0)
            ),
            tz,
        )
        closed_intervals.append(Interval(start=interval_start, end=interval_end))

    return closed_intervals


def get_opening_entries_for_resource(resource):
    """
    Retourne les OpeningEntry du WeeklyOpening de la ressource.
    / Returns the OpeningEntries for the resource's WeeklyOpening.

    LOCALISATION : booking/slot_engine.py

    :param resource: instance Resource
    :return: QuerySet[OpeningEntry]
    """
    return resource.weekly_opening.opening_entries.all()


def get_existing_bookings_for_resource(resource, date_from, date_to):
    """
    Retourne les Booking de la ressource dont start_datetime tombe dans
    [date_from, date_to + 1 jour[. Tous les statuts sont inclus.
    / Returns Bookings for the resource with start_datetime in
    [date_from, date_to + 1 day[. All statuses are included.

    LOCALISATION : booking/slot_engine.py

    On inclut le lendemain de date_to pour capturer les réservations
    qui commencent en fin de journée et chevauchent des créneaux dans
    la plage demandée.
    / date_to + 1 day is included to capture bookings starting at the
    end of the last day that may overlap slots within the range.

    :param resource: instance Resource
    :param date_from: datetime.date
    :param date_to:   datetime.date
    :return: QuerySet[Booking]
    """
    from booking.models import Booking

    return Booking.objects.filter(
        resource=resource,
        start_datetime__date__range=(date_from, date_to),
    )


def generate_theoretical_slots(opening_entries, date_from, date_to, closed_intervals):
    """
    Calcul pur — génère tous les créneaux théoriques pour la plage donnée.
    / Pure computation — generates all theoretical slots for the given range.

    LOCALISATION : booking/slot_engine.py

    Pour chaque date dans [date_from, date_to] :
      Pour chaque OpeningEntry dont weekday correspond :
        Génère slot_count créneaux consécutifs à partir de start_time.
        Chaque créneau est évalué indépendamment (decisions §7) :
        si l'un des jours intersectés est fermé, le créneau est exclu.
    / For each date in [date_from, date_to]:
      For each matching OpeningEntry:
        Generate slot_count consecutive slots from start_time.
        Each slot is evaluated independently (decisions §7):
        if any intersected day is closed, the slot is excluded.

    Note : la vérification des fermetures est faite SLOT PAR SLOT,
    pas une fois pour l'OpeningEntry entière. Un entry dont le jour de
    départ est fermé peut quand même produire des créneaux dont le
    start tombe un jour ouvert (bleed-over).
    / Note: closure check is done PER SLOT, not once for the whole
    OpeningEntry. An entry whose start day is closed can still produce
    slots whose start falls on an open day (bleed-over).

    Note : start est calculé par addition de timedelta, pas par division
    heures/minutes — une durée > 1440 min (ex : 8640 min) produirait
    datetime(y, m, d, 144, 0) qui lève ValueError.
    / Note: start is computed via timedelta addition, not hour/minute
    division — duration > 1440 min (e.g. 8640 min) would produce
    datetime(y, m, d, 144, 0) which raises ValueError.

    :param opening_entries:  iterable[OpeningEntry]
    :param date_from:        datetime.date
    :param date_to:          datetime.date
    :param closed_intervals: list[Interval] — intervalles fermés en heure locale
                             / list[Interval] — closed intervals in local time
    :return: list[BookableInterval] — max_capacity et remaining_capacity
             initialisés à 0, remplis par compute_slots
             / max_capacity and remaining_capacity initialised to 0,
             filled by compute_slots
    """
    bookable_intervals = []
    tz = timezone.get_current_timezone()
    current_date = date_from

    while current_date <= date_to:
        for entry in opening_entries:
            if entry.weekday != current_date.weekday():
                continue

            # Point de départ du premier créneau de cette journée.
            # / Start point of the first slot for this day.
            base_dt = timezone.make_aware(
                datetime.datetime.combine(current_date, entry.start_time),
                tz,
            )

            for i in range(entry.slot_count):
                # Addition par timedelta — fonctionne même si le créneau
                # dépasse minuit ou couvre plusieurs jours.
                # / timedelta addition — works even when the slot crosses
                # midnight or spans multiple days.
                start_dt = base_dt + datetime.timedelta(
                    minutes=i * entry.slot_duration_minutes
                )
                end_dt = start_dt + datetime.timedelta(
                    minutes=entry.slot_duration_minutes
                )

                # Construit l'Interval maintenant pour pouvoir l'utiliser
                # dans le test de fermeture ET dans BookableInterval.
                # / Build the Interval now to reuse it in both the closure
                # check and the BookableInterval constructor.
                slot_interval = Interval(start=start_dt, end=end_dt)

                # Exclure si le créneau chevauche un intervalle fermé (decisions §7).
                # Interval.overlaps() gère la sémantique semi-ouverte [start, end).
                # / Exclude if the slot overlaps any closed interval (decisions §7).
                # Interval.overlaps() handles half-open [start, end) semantics.
                if any(slot_interval.overlaps(ci) for ci in closed_intervals):
                    continue

                bookable_intervals.append(BookableInterval(
                    interval=slot_interval,
                    max_capacity=0,
                    remaining_capacity=0,
                ))

        current_date += datetime.timedelta(days=1)

    return bookable_intervals


def compute_remaining_capacity(slot, capacity, existing_bookings):
    """
    Calcul pur — retourne capacity − nombre de réservations chevauchant le créneau.
    / Pure computation — returns capacity − count of bookings overlapping the slot.

    LOCALISATION : booking/slot_engine.py

    Une réservation chevauche le créneau si son Interval chevauche celui du
    créneau (méthode Interval.overlaps). Le chevauchement partiel compte
    comme un chevauchement complet.
    / A booking overlaps the slot if its Interval overlaps the slot's Interval
    (Interval.overlaps method). Partial overlap counts as full overlap.

    booking_end = booking_start + slot_duration_minutes × slot_count
    (une réservation peut couvrir plusieurs créneaux consécutifs)
    / booking_end = booking_start + slot_duration_minutes × slot_count
    (a booking can cover multiple consecutive slots)

    :param slot:               BookableInterval
    :param capacity:           int — capacité totale de la ressource / total capacity
    :param existing_bookings:  iterable[Booking]
    :return: int — toujours ≥ 0 / always ≥ 0
    """
    overlap_count = 0

    for booking in existing_bookings:
        booking_end = booking.start_datetime + datetime.timedelta(
            minutes=booking.slot_duration_minutes * booking.slot_count
        )
        # Construit l'Interval de la réservation pour utiliser overlaps().
        # / Builds the booking's Interval to use overlaps().
        booking_interval = Interval(start=booking.start_datetime, end=booking_end)
        if slot.interval.overlaps(booking_interval):
            overlap_count += 1

    return max(0, capacity - overlap_count)


def compute_slots(resource, date_from, date_to, reference_date=None):
    """
    Point d'entrée — orchestre toutes les fonctions du moteur.
    / Entry point — orchestrates all engine functions.

    LOCALISATION : booking/slot_engine.py

    Applique le booking_horizon_days de la ressource :
      effective_date_to = min(date_to, aujourd'hui + booking_horizon_days)
    Retourne [] si effective_date_to < date_from.
    / Enforces the resource's booking_horizon_days:
      effective_date_to = min(date_to, today + booking_horizon_days)
    Returns [] if effective_date_to < date_from.

    FLUX / FLOW :
    1. Calcul de effective_date_to (horizon)
    2. get_opening_entries_for_resource → QuerySet
    3. get_closed_intervals_for_resource → list[Interval]
    4. get_existing_bookings_for_resource → QuerySet
    5. generate_theoretical_slots       → list[BookableInterval] (capacités à 0)
    6. compute_remaining_capacity       → remplissage de max_capacity et
                                          remaining_capacity

    :param resource:       instance Resource
    :param date_from:      datetime.date
    :param date_to:        datetime.date
    :param reference_date: datetime.date | None — date de référence pour le
                           calcul de l'horizon. None = date du jour réelle.
                           Utilisé dans les tests pour des dates fixes.
                           / reference date for horizon calculation.
                           None = real today. Used in tests for fixed dates.
    :return: list[BookableInterval]
    """
    # reference_date permet d'injecter une date fixe dans les tests (§13).
    # En production, reference_date est None → on utilise la date du jour réelle.
    # / reference_date allows injecting a fixed date in tests (§13).
    # In production, reference_date is None → use the real current date.
    today = reference_date or timezone.localdate()
    horizon_end = today + datetime.timedelta(days=resource.booking_horizon_days)
    effective_date_to = min(date_to, horizon_end)

    if effective_date_to < date_from:
        return []

    opening_entries = get_opening_entries_for_resource(resource)
    closed_intervals = get_closed_intervals_for_resource(resource, date_from, effective_date_to)
    existing_bookings = get_existing_bookings_for_resource(resource, date_from, effective_date_to)

    bookable_intervals = generate_theoretical_slots(
        opening_entries=opening_entries,
        date_from=date_from,
        date_to=effective_date_to,
        closed_intervals=closed_intervals,
    )

    result = []
    for bookable in bookable_intervals:
        bookable.max_capacity = resource.capacity
        bookable.remaining_capacity = compute_remaining_capacity(
            bookable, capacity=resource.capacity, existing_bookings=existing_bookings
        )
        result.append(bookable)

    return result
