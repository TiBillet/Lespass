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
    ├─ get_closed_dates_for_resource(resource, ...)      [DB]
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



def get_closed_dates_for_resource(resource, date_from, date_to):
    """
    Retourne l'ensemble des dates fermées dans [date_from, date_to].
    / Returns the set of closed dates within [date_from, date_to].

    LOCALISATION : booking/slot_engine.py

    Parcourt les ClosedPeriod du Calendar de la ressource.
    Si end_date est None, la fermeture s'étend jusqu'à date_to (decisions §8).
    / Iterates ClosedPeriods of the resource's Calendar.
    If end_date is None, the closure extends to date_to (decisions §8).

    :param resource: instance Resource
    :param date_from: datetime.date — borne inférieure incluse / lower bound (inclusive)
    :param date_to:   datetime.date — borne supérieure incluse / upper bound (inclusive)
    :return: set[datetime.date]
    """
    closed = set()

    for period in resource.calendar.closed_periods.all():
        period_start = period.start_date
        # Si end_date est None, la fermeture court jusqu'à date_to.
        # / If end_date is None, closure runs to date_to.
        period_end = period.end_date if period.end_date is not None else date_to

        # On se limite à la fenêtre demandée.
        # / Clamp to the requested window.
        current = max(period_start, date_from)
        end_clamped = min(period_end, date_to)

        while current <= end_clamped:
            closed.add(current)
            current += datetime.timedelta(days=1)

    return closed


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


def _slot_intersects_closed_date(start_dt, end_dt, closed_dates):
    """
    Retourne True si le créneau [start_dt, end_dt) intersecte au moins
    une date fermée.
    / Returns True if the slot [start_dt, end_dt) intersects at least
    one closed date.

    LOCALISATION : booking/slot_engine.py

    Utilise l'intervalle semi-ouvert : end_dt − 1 µs donne le dernier
    instant appartenant réellement au créneau. Un créneau finissant
    exactement à minuit (end = 00:00:00 du lendemain) n'intersecte pas
    le lendemain — il se termine à la frontière, sans y avoir de durée.
    / Uses half-open interval: end_dt − 1 µs gives the last instant
    actually within the slot. A slot ending exactly at midnight
    (end = 00:00:00 of the next day) does NOT intersect the next day —
    it ends at the boundary with zero duration there.
    """
    last_dt = end_dt - datetime.timedelta(microseconds=1)
    check_date = start_dt.date()
    last_day = last_dt.date()

    while check_date <= last_day:
        if check_date in closed_dates:
            return True
        check_date += datetime.timedelta(days=1)

    return False


def generate_theoretical_slots(opening_entries, date_from, date_to, closed_dates):
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
    :param closed_dates:     set[datetime.date]
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

                # Exclure si au moins un jour intersecté est fermé (decisions §7).
                # / Exclude if any intersected day is closed (decisions §7).
                if _slot_intersects_closed_date(start_dt, end_dt, closed_dates):
                    continue

                bookable_intervals.append(BookableInterval(
                    interval=Interval(start=start_dt, end=end_dt),
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


def compute_slots(resource, date_from, date_to):
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
    3. get_closed_dates_for_resource    → set[date]
    4. get_existing_bookings_for_resource → QuerySet
    5. generate_theoretical_slots       → list[BookableInterval] (capacités à 0)
    6. compute_remaining_capacity       → remplissage de max_capacity et
                                          remaining_capacity

    :param resource:  instance Resource
    :param date_from: datetime.date
    :param date_to:   datetime.date
    :return: list[BookableInterval]
    """
    # timezone.localdate() utilise le fuseau horaire du tenant (decisions §2).
    # / timezone.localdate() uses the tenant's timezone (decisions §2).
    today = timezone.localdate()
    horizon_end = today + datetime.timedelta(days=resource.booking_horizon_days)
    effective_date_to = min(date_to, horizon_end)

    if effective_date_to < date_from:
        return []

    opening_entries = get_opening_entries_for_resource(resource)
    closed_dates = get_closed_dates_for_resource(resource, date_from, effective_date_to)
    existing_bookings = get_existing_bookings_for_resource(resource, date_from, effective_date_to)

    bookable_intervals = generate_theoretical_slots(
        opening_entries=opening_entries,
        date_from=date_from,
        date_to=effective_date_to,
        closed_dates=closed_dates,
    )

    result = []
    for bookable in bookable_intervals:
        bookable.max_capacity = resource.capacity
        bookable.remaining_capacity = compute_remaining_capacity(
            bookable, capacity=resource.capacity, existing_bookings=existing_bookings
        )
        result.append(bookable)

    return result
