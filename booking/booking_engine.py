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
Orchestrateurs : compute_slots → E,  validate_new_booking → B

DÉPENDANCE MOTEUR DE BASE DE DONNÉES :
  validate_new_booking utilise l'isolation SERIALIZABLE de PostgreSQL (SSI —
  Serializable Snapshot Isolation) pour garantir l'absence de sur-réservation.
  Ce module ne fonctionnera pas correctement avec SQLite ou MySQL.
  / validate_new_booking relies on PostgreSQL SERIALIZABLE isolation (SSI)
  to guarantee no overbooking. This module will not work correctly with
  SQLite or MySQL.
"""
import dataclasses
import datetime

from django.db import connection, transaction
from django.db.utils import OperationalError
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


def compute_open_intervals(closed_periods, window: Interval):
    """
    Calcule O = complémentaire des ClosedPeriods fusionnées (pure).
    / Computes O = complement of merged ClosedPeriods (pure).

    LOCALISATION : booking/booking_engine.py

    Fenêtre : window = [window.start, window.end) — intervalle tz-aware.
    Le fuseau est dérivé de window.start.tzinfo.
    end_date=None étend la fermeture jusqu'à window.end (spec §3.2.1).

    Accepte tout itérable avec .start_date et .end_date (date | None) —
    pas besoin d'un modèle Django pour les tests unitaires.

    :param closed_periods: itérable avec .start_date, .end_date (date|None)
    :param window: Interval tz-aware — fenêtre [début, fin exclusive)
    :return: list[Interval] — O, sans chevauchement, ordonné par start
    """
    tz = window.start.tzinfo

    closed_intervals = []
    for period in closed_periods:
        cp_start_dt = timezone.make_aware(
            datetime.datetime.combine(period.start_date, datetime.time.min), tz
        )
        if period.end_date is None:
            cp_end_dt = window.end
        else:
            cp_end_dt = timezone.make_aware(
                datetime.datetime.combine(
                    period.end_date + datetime.timedelta(days=1), datetime.time.min
                ),
                tz,
            )
        clamped_start = max(cp_start_dt, window.start)
        clamped_end   = min(cp_end_dt, window.end)
        if clamped_start >= clamped_end:
            continue
        closed_intervals.append(Interval(start=clamped_start, end=clamped_end))

    open_intervals = []
    current_start  = window.start

    for closed in merge_intervals(closed_intervals):
        if closed.start > current_start:
            open_intervals.append(Interval(start=current_start, end=closed.start))
        current_start = closed.end

    if current_start < window.end:
        open_intervals.append(Interval(start=current_start, end=window.end))

    return open_intervals


# ─── W — Créneaux théoriques / Theoretical slots ─────────────────────────────

def generate_theoretical_slots(opening_entries, open_intervals, window: Interval):
    """
    Génère W — créneaux théoriques sur les jours ouverts (pure).
    / Generates W — theoretical slots over open days (pure).

    LOCALISATION : booking/booking_engine.py

    Règle W (spec §3.2.2) : w ∈ W ⟺ ∃ o ∈ O, w ⊆ o
    Un créneau qui déborde sur une fermeture est exclu entièrement.
    Un créneau dont le start est avant window.start est exclu (créneaux passés).

    Les starts sont calculés par timedelta (pas par recomposition
    heure/minute) pour supporter les durées > 1440 min.
    Le fuseau est dérivé de window.start.tzinfo.

    Accepte tout itérable avec .weekday, .start_time,
    .slot_duration_minutes, .slot_count — pas de DB.

    :param opening_entries: itérable avec .weekday, .start_time,
                            .slot_duration_minutes, .slot_count
    :param open_intervals:  list[Interval] — O
    :param window: Interval tz-aware — fenêtre [début, fin exclusive)
    :return: list[BookableInterval] — capacités à 0, remplies par compute_slots
    """
    tz = window.start.tzinfo
    bookable_intervals = []
    current_date = window.start.date()

    while timezone.make_aware(
        datetime.datetime.combine(current_date, datetime.time.min), tz
    ) < window.end:
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
                # Masque les créneaux passés quand window.start = timezone.now().
                # / Exclude slots starting before the window start.
                # Hides past-today slots when window.start = timezone.now().
                if start_dt < window.start:
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


def get_existing_bookings_for_resource(resource, window: Interval = None):
    """
    Retourne les réservations actives de la ressource qui chevauchent
    la fenêtre donnée. Si window est None, retourne toutes les
    réservations (fallback sûr, moins performant).
    / Returns active bookings for the resource that overlap the given
    window. If window is None, returns all bookings (safe fallback).

    LOCALISATION : booking/booking_engine.py

    Filtre SQL (finding §15) : start_datetime < window.end
    AND end_datetime > window.start.
    Ce filtre est exact car end_datetime est stocké en base et
    toujours synchronisé par Booking.save().
    / SQL filter (finding §15): start_datetime < window.end
    AND end_datetime > window.start.
    Exact because end_datetime is stored and kept in sync by
    Booking.save().

    L'annulation = suppression de ligne, pas de statut cancelled (finding §1).
    / Cancellation = row deletion, no cancelled status (finding §1).
    """
    from booking.models import Booking

    requete_de_base = Booking.objects.filter(resource=resource)

    if window is None:
        return requete_de_base

    return requete_de_base.filter(
        start_datetime__lt=window.end,
        end_datetime__gt=window.start,
    )


# ─── Orchestrateurs / Orchestrators ──────────────────────────────────────────

def compute_slots(resource, window: Interval = None, reference_now=None):
    """
    Calcule E pour la ressource sur la fenêtre donnée.
    / Computes E for the resource over the given window.

    LOCALISATION : booking/booking_engine.py

    window=None → [maintenant, minuit du jour (today + booking_horizon_days + 1)).
    reference_now injecte un datetime fixe dans les tests (finding §13).

    :param window: Interval tz-aware — fenêtre [début, fin exclusive)
                   (défaut : [now, fin de l'horizon))
    :param reference_now: datetime.datetime tz-aware — injecté dans les tests
    :return: list[BookableInterval]
    """
    tz  = timezone.get_current_timezone()
    now = reference_now or timezone.now()

    # Convertit 'now' dans le fuseau courant du tenant pour que window.start.tzinfo
    # corresponde au fuseau utilisé dans le reste de la requête. Sans cette conversion,
    # window.start aurait tzinfo=UTC (de timezone.now()) alors que d'autres datetimes
    # construits via timezone.get_current_timezone() (ex : fixtures, vues) utiliseraient
    # le fuseau tenant — décalage dans les comparaisons d'intervalles.
    # / Convert 'now' to the current tenant timezone so window.start.tzinfo matches
    # the timezone used elsewhere in the same request. Without this, window.start
    # would have UTC tzinfo while datetimes built via get_current_timezone() would
    # use the tenant timezone — mismatch in interval comparisons.
    now_local = now.astimezone(tz)

    if window is None:
        horizon_end_date = now_local.date() + datetime.timedelta(days=resource.booking_horizon_days)
        window = Interval(
            start=now_local,
            end=timezone.make_aware(
                datetime.datetime.combine(
                    horizon_end_date + datetime.timedelta(days=1), datetime.time.min
                ),
                tz,
            ),
        )

    horizon_cap = timezone.make_aware(
        datetime.datetime.combine(
            now_local.date() + datetime.timedelta(days=resource.booking_horizon_days + 1),
            datetime.time.min,
        ),
        tz,
    )
    effective_window = Interval(
        start=window.start,
        end=min(window.end, horizon_cap),
    )

    if effective_window.end <= effective_window.start:
        return []

    opening_entries   = get_opening_entries_for_resource(resource)
    closed_periods    = get_closed_periods_for_resource(resource)
    existing_bookings = get_existing_bookings_for_resource(resource, window=effective_window)

    open_intervals = compute_open_intervals(
        closed_periods=closed_periods,
        window=effective_window,
    )
    bookable_intervals = generate_theoretical_slots(
        opening_entries=opening_entries,
        open_intervals=open_intervals,
        window=effective_window,
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
    Valide B ⊆ E' et crée la réservation dans une transaction SERIALIZABLE.
    / Validates B ⊆ E' and creates the booking in a SERIALIZABLE transaction.

    LOCALISATION : booking/booking_engine.py

    ── Garde temporelle (sans DB) ───────────────────────────────────────────────

    Un créneau déjà commencé (start_datetime <= now) est refusé immédiatement,
    sans ouvrir de transaction.
    / A slot that has already started is rejected immediately, without opening
    a transaction.

    ── Isolation SERIALIZABLE et rôle de end_datetime ───────────────────────────

    La race condition est la suivante : deux utilisateurs voient simultanément
    remaining_capacity = 1, valident tous les deux, et créent deux réservations
    — laissant la ressource en sur-réservation.

    La solution est l'isolation SERIALIZABLE de PostgreSQL (SSI — Serializable
    Snapshot Isolation). PostgreSQL enregistre un verrou de prédicat (SIReadLock)
    sur chaque requête de lecture. Si une transaction concurrente insère une
    ligne qui aurait modifié le résultat d'une lecture déjà effectuée, PostgreSQL
    détecte le conflit et annule l'une des deux transactions avec SQLSTATE 40001
    (serialization_failure). L'appelant doit intercepter cette erreur et la
    traiter comme "créneau non disponible".

    Contrairement à SELECT FOR UPDATE, SSI gère les créneaux sans réservation
    existante (problème du "phantom row") : le verrou de prédicat couvre la
    requête elle-même, même si elle retourne zéro lignes.

    Le champ Booking.end_datetime joue un rôle fonctionnel ici, pas seulement
    de performance (finding §15) : le filtre DB
    "start_datetime < window.end AND end_datetime > window.start"
    définit le prédicat exact que SSI verrouille. Deux réservations pour des
    créneaux qui ne se chevauchent pas sur la même ressource génèrent des
    prédicats disjoints — elles ne se bloquent pas mutuellement. Sans
    end_datetime en base, le prédicat couvrirait toutes les réservations de la
    ressource, sérialisant des transactions indépendantes à tort.

    / The race condition: two users see remaining_capacity = 1, both validate,
    both create a booking — overbooking the resource.

    The solution is PostgreSQL SERIALIZABLE isolation (SSI). PostgreSQL records
    a predicate lock (SIReadLock) on each read. If a concurrent transaction
    inserts a row that would have changed a prior read's result, PostgreSQL
    detects the conflict and aborts one transaction with SQLSTATE 40001
    (serialization_failure). The caller must catch this error and treat it as
    "slot no longer available".

    Unlike SELECT FOR UPDATE, SSI handles empty slots (no existing bookings):
    the predicate lock covers the query itself, even if it returns zero rows.

    Booking.end_datetime has a functional role here, not just performance (§15):
    the DB filter "start_datetime < window.end AND end_datetime > window.start"
    defines the exact predicate SSI locks. Two bookings for non-overlapping slots
    on the same resource generate disjoint predicates — they do not block each
    other. Without end_datetime in the DB, the predicate would cover all bookings
    for the resource, serialising independent transactions unnecessarily.

    ── Dépendance PostgreSQL ────────────────────────────────────────────────────

    SSI tel qu'implémenté ici est spécifique à PostgreSQL. SQLite ne supporte
    pas SERIALIZABLE. MySQL implémente SERIALIZABLE par des verrous bloquants,
    pas par SSI — le comportement serait différent.
    / SSI as implemented here is PostgreSQL-specific. SQLite does not support
    SERIALIZABLE. MySQL implements SERIALIZABLE via blocking locks, not SSI.

    ── Paramètres / Parameters ──────────────────────────────────────────────────

    reference_now : datetime fixe injecté pour les tests (finding §13).
                    / Fixed datetime injected for tests (finding §13).

    :return: (True, Booking) si créé / if created
             (False, str)    message d'erreur / error message
    """
    from booking.models import Booking

    # Refuse tout créneau dont le début est passé — sans ouvrir de transaction.
    # / Reject any past slot — without opening a transaction.
    now = reference_now or timezone.now()
    if start_datetime <= now:
        return False, str(_('Cannot book a slot that has already started.'))

    last_slot_end_dt = start_datetime + datetime.timedelta(
        minutes=slot_duration_minutes * slot_count
    )
    booking_window = Interval(start=start_datetime, end=last_slot_end_dt)

    # Mémorise si on est déjà dans une transaction avant d'entrer dans le bloc.
    # En production : already_in_transaction est False → on peut fixer
    # l'isolation SERIALIZABLE avant toute lecture.
    # En tests : le framework de test enveloppe chaque test dans une transaction
    # pour le rollback → already_in_transaction est True → on ne peut pas changer
    # l'isolation en cours de transaction (PostgreSQL rejette la commande).
    # Dans ce cas on saute le SET et on garde l'isolation par défaut du test.
    # La garantie SSI ne s'applique qu'en production — les tests couvrent
    # la logique métier, pas le comportement de l'isolation DB.
    # / In production: already_in_transaction is False → can set SERIALIZABLE.
    # In tests: test framework wraps each test in a transaction for rollback
    # → already_in_transaction is True → cannot change isolation mid-transaction.
    # Skip SET, keep test's default isolation. SSI guarantee applies in
    # production only.
    already_in_transaction = connection.in_atomic_block

    try:
        with transaction.atomic():
            # Active l'isolation SERIALIZABLE pour cette transaction.
            # Doit être exécuté avant toute lecture dans la transaction.
            # Ignoré dans les tests (voir commentaire ci-dessus).
            # / Enable SERIALIZABLE isolation for this transaction.
            # Must run before any read inside the transaction.
            # Skipped in tests (see comment above).
            if not already_in_transaction:
                connection.cursor().execute(
                    'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'
                )

            # Calcule E sur la fenêtre de la réservation demandée.
            # compute_slots lit WeeklyOpening, ClosedPeriods et Bookings —
            # toutes ces lectures sont verrouillées par prédicat sous SSI.
            # / Compute E over the requested booking window.
            # compute_slots reads WeeklyOpening, ClosedPeriods and Bookings —
            # all these reads are predicate-locked under SSI.
            available_slots = compute_slots(
                resource, booking_window, reference_now=reference_now,
            )
            slot_by_key = {
                (slot.start, slot.duration_minutes()): slot
                for slot in available_slots
            }

            # Vérifie que chaque créneau de B existe dans E' (capacité > 0).
            # / Verify that each slot of B exists in E' (capacity > 0).
            for i in range(slot_count):
                slot_start = start_datetime + datetime.timedelta(
                    minutes=i * slot_duration_minutes
                )
                key = (slot_start, slot_duration_minutes)

                if key not in slot_by_key:
                    return False, str(_(
                        'Slot starting at %(start)s is not available.'
                    ) % {'start': slot_start})

                if slot_by_key[key].remaining_capacity <= 0:
                    return False, str(_(
                        'Slot starting at %(start)s is fully booked.'
                    ) % {'start': slot_start})

            new_booking = Booking.objects.create(
                resource=resource,
                user=member,
                start_datetime=start_datetime,
                slot_duration_minutes=slot_duration_minutes,
                slot_count=slot_count,
                status=Booking.STATUS_CONFIRMED,
            )

    except OperationalError as e:
        # SQLSTATE 40001 : échec de sérialisation — PostgreSQL a détecté que
        # deux transactions concurrentes ont lu et modifié les mêmes données.
        # L'une des deux est annulée. On la traite comme "créneau non disponible".
        # / SQLSTATE 40001: serialization failure — PostgreSQL detected that two
        # concurrent transactions read and modified the same data. One is aborted.
        # Treat as "slot no longer available".
        cause = getattr(e, '__cause__', None)
        pgcode = getattr(cause, 'pgcode', None) or getattr(cause, 'sqlstate', None)
        if pgcode == '40001':
            return False, str(_(
                'This slot was just booked by another user. Please try again.'
            ))
        raise

    return True, new_booking
