"""
Modèles de l'app booking — réservation de ressources partagées.
/ booking app models — shared resource reservation.

LOCALISATION : booking/models.py
"""
import logging

import stripe
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.transaction import atomic
from datetime import timedelta
from BaseBillet.models import Product, ResourceProduct, Price, LigneArticle, Configuration, Paiement_stripe, Commande
from BaseBillet.services_vente import ligne_sans_argent_a_rendre
from PaiementStripe.utils import partial_refund_payment
from fedow_connect.utils import dround
from root_billet.models import RootConfiguration
from stripe import InvalidRequestError

logger = logging.getLogger(__name__)

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
        max_length=250,
        verbose_name=_("Name")
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Long description"),
        help_text=_("Displayed only for membership/subscription products.")
    )

    group = models.ForeignKey(
        'ResourceGroup',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='resources',
        verbose_name=_('Group'),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='resources',
        verbose_name=_('Produit'),
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
    #
    # HOUR, DAY = "H", "D"
    #
    # STATUS_CHOICES = [
    #     (HOUR, _("à l'heure")),
    #     (DAY, _('à la journée')),
    # ]
    #
    # slot_type = models.CharField(
    #     max_length=1,
    #     choices=STATUS_CHOICES,
    #     default=HOUR,
    #     verbose_name=_('Type de réservation'),
    # )


    class Meta:
        verbose_name = _('Resource')
        verbose_name_plural = _('Resources')

    def published_prices(self):
        return self.product.prices.filter(publish=True)

    def __str__(self):
        return self.product.name


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
        verbose_name = _("Période d'ouverture")
        verbose_name_plural = _("Périodes d'ouvertures")
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

        # Durée minimale d'un slot est 30 minutes pour l'instant
        if self.slot_duration_minutes < 30:
            raise ValidationError(
                _("Le temps minimal d'un slot est de 30 minutes.")
            )

        # La durée totale ne doit pas dépasser une semaine (decisions §9).
        # / Total duration must not exceed one week (decisions §9).
        if self.slot_duration_minutes * self.slot_count > WEEK_MINUTES:
            raise ValidationError(
                _(
                    'Total duration (slot_duration_minutes × slot_count) '
                    'must not exceed one week (%(week)d minutes).'
                ) % {'week': WEEK_MINUTES}
            )

        if not self.start_time:
            raise ValidationError(_("Il faut une date de début valide."))

        new_start = self._position_minutes()
        new_end = new_start + self.slot_duration_minutes * self.slot_count

        # L'heure de fin doit être située le même jour que l'heure de début.
        # Un créneau se terminant exactement à minuit est considéré comme valide.
        # / End time must be on the same day as the start time.
        # / A slot ending exactly at midnight is considered valid.
        end_minutes_today = (
            self.start_time.hour * 60
            + self.start_time.minute
            + self.slot_duration_minutes * self.slot_count
        )
        if end_minutes_today > 24 * 60:
            raise ValidationError(
                _('The end time must be on the same day as the start time.')
            )

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

    WAITING_PAYMENT, ADMIN_CANCELED, ADMIN_VALID, ADMIN_WAITING, PAID_BY_USER, NO_ADMIN_VALID, USER_CANCELED = "WP", "CA", "VA", "WA", "PA", "AU", "UC"
    FREERES, FREERES_USERACTIV = "FR", "FU"

    STATUS_CHOICES = [
        (WAITING_PAYMENT, _("Waiting for payment")),
        (ADMIN_CANCELED, _('Cancelled')),
        (ADMIN_WAITING, _('Waiting for admin validation')),
        (ADMIN_VALID, _('Confirmed by admin, waiting for payment')),
        (PAID_BY_USER, _('Paid by user')),
        (NO_ADMIN_VALID, _('Confirmed by system')),
        (FREERES, _('Email verification still pending')),
        (FREERES_USERACTIV, _('Email verified')),
        (USER_CANCELED, _('Canceled by user')),
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
    end_datetime = models.DateTimeField(
        # Redondant avec start_datetime + slot_duration_minutes * slot_count.
        # Deux rôles distincts :
        # 1. Performance (finding §15) : filtrage SQL direct
        #    "start_datetime < window.end AND end_datetime > window.start".
        # 2. Fonctionnel : définit le prédicat SSI dans validate_new_booking.
        #    Sans ce champ, le prédicat couvrirait toutes les réservations de
        #    la ressource — deux réservations pour des créneaux différents sur
        #    la même ressource se bloqueraient mutuellement à tort.
        # Toujours calculé par save() — ne jamais écrire ce champ directement.
        # / Redundant with start_datetime + slot_duration_minutes * slot_count.
        # Two distinct roles:
        # 1. Performance (finding §15): direct SQL filtering.
        # 2. Functional: defines the SSI predicate in validate_new_booking.
        #    Without this field, the predicate would cover all bookings for the
        #    resource — two bookings for different slots would conflict wrongly.
        # Always computed by save() — never write this field directly.
        editable=False,
        verbose_name=_('Slot end'),
    )
    status = models.CharField(
        max_length=2,
        choices=STATUS_CHOICES,
        default=WAITING_PAYMENT,
        verbose_name=_('Status'),
    )
    booked_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Booked at'),
    )

    commande = models.ForeignKey(
        Commande,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
        verbose_name=_("Order"),
        help_text=_(
            "Renseignée uniquement si la réservation a été créée via un panier multi-items. "
            "/ Only set if the booking was created via a multi-item cart."
        ),
    )

    first_name = models.CharField(
        max_length=200,
        verbose_name=_("First name"),
        null=True, blank=True
    )

    last_name = models.CharField(
        max_length=200,
        verbose_name=_("Last name"),
        null=True, blank=True
    )


    class Meta:
        verbose_name = _('Booking')
        verbose_name_plural = _('Bookings')
        ordering = ['start_datetime']

    def save(self, *args, **kwargs):
        import datetime
        # Calcule end_datetime avant chaque sauvegarde pour garantir la cohérence.
        # / Compute end_datetime before every save to keep it in sync.
        self.end_datetime = self.start_datetime + datetime.timedelta(
            minutes=self.slot_duration_minutes * self.slot_count
        )
        super().save(*args, **kwargs)

    def total_time(self):
        return str(self.slot_duration_minutes * self.slot_count) + "min"

    def to_pay(self):
        """
        Le reste à payer : la somme des nets vendus (`total_ttc`) des lignes pas encore
        payées. Lu pour choisir Stripe ou gratuit (booking/booking_engine.py).
        / Amount still to pay: sum of the unpaid lines' net sold.
        """
        to_pay = 0
        for ligne_article in self.lignearticles.filter(status__in=[LigneArticle.UNPAID, LigneArticle.CREATED]):
            to_pay += ligne_article.total_ttc
        return dround(to_pay)

    def total_paid(self):
        """
        Le montant payé : la somme des nets vendus (`total_ttc`) des lignes payées,
        remboursements et avoirs compris (négatifs), comme `Reservation.total_paid`.
        / Amount paid: sum of the paid lines' net sold, refunds and credit notes
        included, like Reservation.total_paid.
        """
        total_paid = 0
        statuts_des_lignes_payees = [
            LigneArticle.PAID,
            LigneArticle.VALID,
            LigneArticle.REFUNDED,
            LigneArticle.CREDIT_NOTE,
        ]
        for ligne_article in self.lignearticles.filter(status__in=statuts_des_lignes_payees):
            total_paid += ligne_article.total_ttc
        return dround(total_paid)

    def _lignes_hors_stripe(self):
        """
        Les lignes VALID/PAID payantes (net vendu `total_ttc` non nul) de ce booking sans paiement
        Stripe (réglées sur place : espèces, chèque…), pas encore créditées. Seule la FK
        directe compte. Une ligne entièrement offerte (net 0) n'y est pas ; une ligne
        payée en jetons cadeau y est (son net n'est pas nul) : l'appelant l'écarte par
        `ligne_sans_argent_a_rendre`.
        / Paid (non-zero) VALID/PAID non-Stripe lines of this booking, not yet credited.
        A fully offered line is out; a gift-token line is in, the caller filters it.

        Lue par `cancel_and_refund_booking` pour choisir le message de l'annulation.
        / Read by cancel_and_refund_booking to pick the cancellation message.
        """
        lignes = self.lignearticles.filter(
            paiement_stripe__isnull=True,
            status__in=[LigneArticle.VALID, LigneArticle.PAID],
            total_ttc__gt=0,
        ).exclude(
            credit_notes__isnull=False,
        )
        return lignes

    def deadline(self):
        deadline = self.start_datetime - timedelta(
            hours=self.resource.cancellation_deadline_hours,
        )
        return deadline

    def deadline_passed(self):
        deadline_passed = timezone.now() > self.deadline()
        return deadline_passed

    def can_refund(self):
        return not self.deadline_passed()

    def cancel_text(self):
        if self.can_refund():
            return _("You will be refunded to the credit card used to make the reservation.")
        else:
            return _("The deadline for getting a refund has passed.")

    @atomic
    def cancel_and_refund_booking(self):
        if self.status in [Booking.USER_CANCELED, Booking.ADMIN_CANCELED]:
            raise Exception(_("This booking is already cancelled."))

        # 1) Remboursement Stripe (flow existant, inchange)
        # / Stripe refund (existing flow, unchanged)
        if self.total_paid() > 0:
            config = Configuration.get_solo()

            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()

            # Si la commande est faite AVEC le panier, récupère la lignearticle depuis self
            if self.commande and self.lignearticles:

                paiement = self.lignearticles.first().paiement_stripe
                partial_refund_payment(paiement, config, self.lignearticles.filter(status__in=[LigneArticle.VALID, LigneArticle.PAID]))
            # Si la commande est faite SANS le panier, récupère la lignearticle depuis le paiement
            elif self.paiements.count() > 0:
                for paiement in self.paiements.filter(status__in=[Paiement_stripe.VALID,
                                                              Paiement_stripe.PAID,
                                                              Paiement_stripe.NOTSYNC,
                                                              ]):
                    partial_refund_payment(paiement, config, paiement.lignearticles.filter(status__in=[LigneArticle.VALID, LigneArticle.PAID]))

        # 2) Lignes réglées hors Stripe (espèces, chèque…) : AUCUN avoir (D31). Seule la
        # personne annule un booking ; l'argent reste acquis, et si le lieu rembourse,
        # l'admin fait un avoir depuis la liste des ventes.
        # / 2) Non-Stripe lines: NO credit note (D31); the venue issues one if it refunds.
        # Le message « réglée sur place » ne vaut que pour de l'ARGENT : un créneau
        # entièrement offert (ou payé en jetons cadeau) garde le message d'avant.
        # / The "paid on site" message is for money only: a fully offered (or token
        # paid) slot keeps the old message.
        reglee_hors_stripe_en_argent = False
        for ligne in self._lignes_hors_stripe():
            if not ligne_sans_argent_a_rendre(ligne):
                reglee_hors_stripe_en_argent = True

        self.status = Booking.USER_CANCELED

        self.save()

        if reglee_hors_stripe_en_argent:
            return _("Votre réservation est annulée. Elle a été réglée sur place : pour un éventuel remboursement, contactez l'organisateur.")
        return self.cancel_text()



    def __str__(self):
        return f'{self.resource} — {self.user} {_("de")} {self.start_datetime} {_("à")} {self.end_datetime}'
