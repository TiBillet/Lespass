"""
Modèles de l'app booking — réservation de ressources partagées.
/ booking app models — shared resource reservation.

LOCALISATION : booking/models.py
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

WEEK_MINUTES = 7 * 24 * 60  # 10 080 — durée d'une semaine en minutes


class Resource(models.Model):
    """
    Une ressource réservable (salle, machine, bureau coworking, etc.).
    / A bookable resource (room, machine, coworking desk, etc.).

    LOCALISATION : booking/models.py

    La disponibilité est calculée à la volée depuis weekly_opening et calendar.
    / Availability is computed on the fly from weekly_opening and calendar.
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_('Name'),
    )
    group = models.ForeignKey(
        'ResourceGroup',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='resources',
        verbose_name=_('Group'),
    )
    calendar = models.ForeignKey(
        'Calendar',
        on_delete=models.PROTECT,
        related_name='resources',
        verbose_name=_('Calendar'),
    )
    weekly_opening = models.ForeignKey(
        'WeeklyOpening',
        on_delete=models.PROTECT,
        related_name='resources',
        verbose_name=_('Weekly opening'),
    )
    capacity = models.PositiveIntegerField(
        default=1,
        verbose_name=_('Capacity'),
        help_text=_('Maximum simultaneous bookings per slot. 1 = exclusive use.'),
    )
    cancellation_deadline_hours = models.PositiveIntegerField(
        default=24,
        verbose_name=_('Cancellation deadline (hours)'),
        help_text=_('Hours before slot start within which cancellation is allowed.'),
    )
    booking_horizon_days = models.PositiveIntegerField(
        default=28,
        verbose_name=_('Booking horizon (days)'),
        help_text=_('How far ahead a member can book.'),
    )
    description = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Description'),
    )
    image = models.URLField(
        blank=True,
        default='',
        verbose_name=_('Image URL'),
    )

    class Meta:
        verbose_name = _('Resource')
        verbose_name_plural = _('Resources')
        ordering = ['name']

    def __str__(self):
        return self.name


class ResourceGroup(models.Model):
    """
    Groupement optionnel de ressources pour la page publique.
    / Optional grouping of resources for the public page.

    LOCALISATION : booking/models.py

    Un groupe n'a aucune logique métier : il sert uniquement à regrouper
    des ressources visuellement (ex: "Salles de répétitions").
    / A group has no business logic: it only groups resources visually
    (e.g. "Rehearsal rooms").
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_('Name'),
    )
    description = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Description'),
    )
    image = models.URLField(
        blank=True,
        default='',
        verbose_name=_('Image URL'),
    )

    class Meta:
        verbose_name = _('Resource group')
        verbose_name_plural = _('Resource groups')
        ordering = ['name']

    def __str__(self):
        return self.name


class Calendar(models.Model):
    """
    Calendrier de fermetures d'une ou plusieurs ressources.
    / Closure calendar for one or more resources.

    LOCALISATION : booking/models.py

    En dehors des ClosedPeriod déclarées, une ressource est
    implicitement ouverte.
    / Outside declared ClosedPeriods, a resource is implicitly open.
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_('Name'),
    )

    class Meta:
        verbose_name = _('Calendar')
        verbose_name_plural = _('Calendars')
        ordering = ['name']

    def __str__(self):
        return self.name


class ClosedPeriod(models.Model):
    """
    Une période de fermeture dans un calendrier.
    / A closure period inside a calendar.

    LOCALISATION : booking/models.py

    end_date null = fermeture sans fin.
    end_date == start_date = fermeture d'un seul jour.
    / end_date null = endless closure.
    / end_date == start_date = single-day closure.
    """
    calendar = models.ForeignKey(
        Calendar,
        on_delete=models.PROTECT,
        related_name='closed_periods',
        verbose_name=_('Calendar'),
    )
    start_date = models.DateField(
        verbose_name=_('Start date'),
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('End date'),
        help_text=_(
            'Same as start date: single-day closure. '
            'Later than start date: multi-day closure. '
            'Leave empty: endless closure.'
        ),
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name=_('Label'),
        help_text=_('e.g. "Summer closure", "Public holiday"'),
    )

    class Meta:
        verbose_name = _('Closed period')
        verbose_name_plural = _('Closed periods')
        ordering = ['start_date']
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__isnull=True) | models.Q(end_date__gte=models.F('start_date')),
                name='closed_period_end_date_gte_start_date',
            )
        ]

    def clean(self):
        """
        Vérifie que end_date est postérieure ou égale à start_date.
        / Validates that end_date is on or after start_date.

        LOCALISATION : booking/models.py — classe ClosedPeriod

        end_date null est autorisé (fermeture sans fin — decisions §8).
        / end_date null is allowed (endless closure — decisions §8).
        """
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValidationError(
                _('End date must be equal to or later than start date.')
            )

    def __str__(self):
        if self.end_date:
            return f'{self.calendar} — {self.start_date} → {self.end_date}'
        return f'{self.calendar} — {self.start_date} → ∞'


class WeeklyOpening(models.Model):
    """
    Planning hebdomadaire de créneaux, réutilisable sur plusieurs ressources.
    / Reusable weekly opening schedule, shared across multiple resources.

    LOCALISATION : booking/models.py
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_('Name'),
    )

    class Meta:
        verbose_name = _('Weekly opening')
        verbose_name_plural = _('Weekly openings')
        ordering = ['name']

    def __str__(self):
        return self.name


class OpeningEntry(models.Model):
    """
    Un créneau récurrent dans un WeeklyOpening.
    / One recurring slot inside a WeeklyOpening.

    LOCALISATION : booking/models.py

    Exemple : weekday=0 (lundi), start_time=10:00,
    slot_duration_minutes=60, slot_count=5 génère :
    10:00–11:00, 11:00–12:00, 12:00–13:00, 13:00–14:00, 14:00–15:00.
    / Example: weekday=0 (Monday), start_time=10:00,
    slot_duration_minutes=60, slot_count=5 generates:
    10:00–11:00, 11:00–12:00, 12:00–13:00, 13:00–14:00, 14:00–15:00.

    weekday suit la convention Python date.weekday() : 0=lundi, 6=dimanche.
    / weekday follows Python's date.weekday() convention: 0=Monday, 6=Sunday.
    """

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    WEEKDAY_CHOICES = [
        (MONDAY, _('Monday')),
        (TUESDAY, _('Tuesday')),
        (WEDNESDAY, _('Wednesday')),
        (THURSDAY, _('Thursday')),
        (FRIDAY, _('Friday')),
        (SATURDAY, _('Saturday')),
        (SUNDAY, _('Sunday')),
    ]

    weekly_opening = models.ForeignKey(
        WeeklyOpening,
        on_delete=models.PROTECT,
        related_name='opening_entries',
        verbose_name=_('Weekly opening'),
    )
    weekday = models.IntegerField(
        choices=WEEKDAY_CHOICES,
        verbose_name=_('Weekday'),
    )
    start_time = models.TimeField(
        verbose_name=_('Start time'),
    )
    slot_duration_minutes = models.PositiveIntegerField(
        verbose_name=_('Slot duration (minutes)'),
    )
    slot_count = models.PositiveIntegerField(
        verbose_name=_('Slot count'),
    )

    class Meta:
        verbose_name = _('Opening entry')
        verbose_name_plural = _('Opening entries')
        ordering = ['weekday', 'start_time']

    def _position_minutes(self):
        """
        Position de cet entry dans la semaine, en minutes depuis lundi 00:00.
        / Position of this entry in the week, in minutes from Monday 00:00.
        """
        return (
            self.weekday * 24 * 60
            + self.start_time.hour * 60
            + self.start_time.minute
        )

    def clean(self):
        """
        Vérifie qu'aucun autre entry du même WeeklyOpening ne chevauche
        cet entry. La semaine est traitée comme une timeline circulaire :
        un entry qui dépasse minuit déborde sur le jour suivant, et un
        entry du dimanche peut déborder sur le lundi.
        / Checks that no sibling entry in the same WeeklyOpening overlaps
        this one. The week is circular: an entry that extends past midnight
        bleeds into the next day; a Sunday entry can bleed into Monday.

        Représentation : chaque entry occupe l'intervalle semi-ouvert
        [start, end) en minutes depuis lundi 00:00.
        Si end > WEEK_MINUTES, le débordement occupe [0, end − WEEK_MINUTES).
        / Representation: each entry occupies the half-open interval
        [start, end) in minutes from Monday 00:00.
        If end > WEEK_MINUTES, the bleed occupies [0, end − WEEK_MINUTES).
        """
        if not self.weekly_opening_id:
            return

        # La durée totale ne doit pas dépasser une semaine (decisions §9).
        # / Total duration must not exceed one week (decisions §9).
        if self.slot_duration_minutes * self.slot_count > WEEK_MINUTES:
            raise ValidationError(
                _(
                    'Total duration (slot_duration_minutes × slot_count) '
                    'must not exceed one week (%(week)d minutes).'
                ) % {'week': WEEK_MINUTES}
            )

        new_start = self._position_minutes()
        new_end = new_start + self.slot_duration_minutes * self.slot_count

        siblings = OpeningEntry.objects.filter(
            weekly_opening=self.weekly_opening,
        )
        if self.pk:
            siblings = siblings.exclude(pk=self.pk)

        for sibling in siblings:
            sib_start = sibling._position_minutes()
            sib_end = sib_start + sibling.slot_duration_minutes * sibling.slot_count

            # Chevauchement linéaire direct sur la timeline hebdomadaire circulaire.
            # / Direct linear overlap on the circular weekly timeline.
            linear_overlap = new_start < sib_end and sib_start < new_end

            # Débordement de new_end au-delà de la semaine : la portion circulaire
            # [0, new_end − WEEK) est comparée à sib_start.
            # / new_end bleed: circular portion [0, new_end − WEEK) against sib_start.
            new_bleed_overlap = (
                new_end > WEEK_MINUTES and sib_start < new_end - WEEK_MINUTES
            )

            # Débordement de sib_end au-delà de la semaine : la portion circulaire
            # [0, sib_end − WEEK) est comparée à new_start.
            # / sib_end bleed: circular portion [0, sib_end − WEEK) against new_start.
            sib_bleed_overlap = (
                sib_end > WEEK_MINUTES and new_start < sib_end - WEEK_MINUTES
            )

            if linear_overlap or new_bleed_overlap or sib_bleed_overlap:
                raise ValidationError(
                    _(
                        'This opening entry overlaps with "%(sibling)s".'
                    ) % {'sibling': sibling}
                )

    def __str__(self):
        weekday_label = dict(self.WEEKDAY_CHOICES).get(self.weekday, self.weekday)
        return (
            f'{self.weekly_opening} — {weekday_label} {self.start_time}'
            f' × {self.slot_count} × {self.slot_duration_minutes}min'
        )


class Booking(models.Model):
    """
    Une réservation pour un membre sur une ressource.
    / A reservation for a member on a resource.

    LOCALISATION : booking/models.py

    La réservation stocke le créneau convenu de façon autonome : si le
    WeeklyOpening change après la réservation, la réservation n'est pas
    affectée.
    / The booking stores the agreed slot independently: if the WeeklyOpening
    changes after booking, the booking is unaffected.

    L'annulation est modélisée par la suppression de la ligne Booking —
    pas de statut 'cancelled'.
    / Cancellation is modelled as deletion of the Booking row —
    no 'cancelled' status.
    """

    STATUS_NEW = 'new'
    STATUS_VALIDATED = 'validated'
    STATUS_CONFIRMED = 'confirmed'

    STATUS_CHOICES = [
        (STATUS_NEW, _('New — in basket')),
        (STATUS_VALIDATED, _('Validated — pending payment')),
        (STATUS_CONFIRMED, _('Confirmed — payment done')),
    ]

    resource = models.ForeignKey(
        Resource,
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('Resource'),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('User'),
    )
    start_datetime = models.DateTimeField(
        verbose_name=_('Slot begining'),
    )
    slot_duration_minutes = models.PositiveIntegerField(
        verbose_name=_('Slot duration (minutes)'),
    )
    slot_count = models.PositiveIntegerField(
        verbose_name=_('Slot count'),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        verbose_name=_('Status'),
    )
    booked_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Booked at'),
    )
    payment_ref = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name=_('Payment reference'),
    )

    class Meta:
        verbose_name = _('Booking')
        verbose_name_plural = _('Bookings')
        ordering = ['start_datetime']

    def __str__(self):
        return f'{self.resource} — {self.user} — {self.start_datetime}'
