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


def _intervals_overlap(a_start, a_end, b_start, b_end):
    """
    Vérifie le chevauchement de deux blocs sur une timeline circulaire de
    7 jours. Les intervalles sont semi-ouverts : [start, end).
    / Checks overlap of two blocks on a circular 7-day timeline.
    Intervals are half-open: [start, end).

    Cas couverts :
    1. Chevauchement linéaire direct.
    2. Le bloc A déborde en fin de semaine → sa partie circulaire [0, a_end−WEEK)
       est comparée à B.
    3. Le bloc B déborde en fin de semaine → sa partie circulaire [0, b_end−WEEK)
       est comparée à A.
    / Cases covered:
    1. Direct linear overlap.
    2. Block A bleeds past end of week → its circular portion [0, a_end−WEEK)
       is compared against B.
    3. Block B bleeds past end of week → its circular portion [0, b_end−WEEK)
       is compared against A.
    """
    # Chevauchement linéaire direct.
    # / Direct linear overlap.
    if a_start < b_end and b_start < a_end:
        return True

    # Débordement de A : la portion circulaire [0, a_bleed) contre B.
    # / A bleed: circular portion [0, a_bleed) against B.
    if a_end > WEEK_MINUTES:
        a_bleed = a_end - WEEK_MINUTES
        if b_start < a_bleed:
            return True

    # Débordement de B : la portion circulaire [0, b_bleed) contre A.
    # / B bleed: circular portion [0, b_bleed) against A.
    if b_end > WEEK_MINUTES:
        b_bleed = b_end - WEEK_MINUTES
        if a_start < b_bleed:
            return True

    return False


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
    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Tags'),
        help_text=_('List of labels, e.g. ["salle", "machine"]'),
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
    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Tags'),
        help_text=_('List of labels, e.g. ["salle", "machine"]'),
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
        help_text=_('Leave empty for an endless closure.'),
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

            if _intervals_overlap(new_start, new_end, sib_start, sib_end):
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
