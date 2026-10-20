"""
Modèles de l'app booking — réservation de ressources partagées.
/ booking app models — shared resource reservation.

LOCALISATION : booking/models.py
"""
import datetime
import logging
from uuid import uuid4

import stripe
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.db.transaction import atomic
from datetime import timedelta
from BaseBillet.models import Product, ResourceProduct, Price, LigneArticle, Configuration, Paiement_stripe, Commande
from BaseBillet.services_vente import annuler_vente, ligne_sans_argent_a_rendre
from PaiementStripe.utils import partial_refund_payment
from fedow_connect.utils import dround
from root_billet.models import RootConfiguration
from stripe import InvalidRequestError
from stdimage import StdImageField

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
        verbose_name=_("Description"),
        help_text=_("Texte riche affiché sur la carte de la ressource (page Ressources) "
                    "et en haut de sa page de réservation."),
    )

    # Image de la ressource : carte de /booking/ et en-tête de sa page.
    # Mêmes variations que Product.img : commun/partials/picture.html les attend.
    # / Resource image: /booking/ card and page header. Same variations as Product.img.
    img = StdImageField(
        upload_to='images/',
        null=True,
        blank=True,
        variations={
            'fhd': (1920, 1920),
            'hdr': (720, 720),
            'med': (480, 480),
            'thumbnail': (150, 90),
            'crop_hdr': (960, 540, True),
            'crop': (480, 270, True),
            'social_card': (1200, 630, True),
        },
        delete_orphans=True,
        verbose_name=_('Image de la ressource'),
    )

    group = models.ForeignKey(
        'ResourceGroup',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='resources',
        verbose_name=_('Group'),
    )

    # FK vers le proxy ResourceProduct : les formulaires ne proposent que des
    # produits ressource (manager ResourceProductManager). Meme table, meme colonne.
    # limit_choices_to : full_clean() controle aussi la categorie, car
    # ForeignKey.validate() passe par le manager de base, qui ne filtre pas.
    # / FK to the ResourceProduct proxy: forms only offer resource products.
    # limit_choices_to makes full_clean() check the category too.
    product = models.ForeignKey(
        ResourceProduct,
        on_delete=models.PROTECT,
        related_name='resources',
        verbose_name=_('Produit'),
        limit_choices_to={'categorie_article': Product.RESOURCE},
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
        return self.product.prices.filter(publish=True, archived=False)

    def __str__(self):
        # Le nom de la RESSOURCE, pas celui de son produit : plusieurs ressources
        # peuvent partager un produit (mêmes tarifs). Tous les menus déroulants
        # (ex : Event.ressource_bloquee) et les listes admin lisent ce texte.
        # / The RESOURCE's name, not its product's: several resources may share one.
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

    # Les statuts de LigneArticle comptés comme « payé ».
    # Lus par total_paid() ET par la somme SQL de l'export
    # (Administration/admin/resources.py : BookingAdmin.get_export_queryset).
    # Une seule liste : les deux totaux ne peuvent pas diverger.
    # / LigneArticle statuses counted as paid, shared by total_paid() and the export.
    STATUTS_DES_LIGNES_PAYEES = [
        LigneArticle.PAID,
        LigneArticle.VALID,
        LigneArticle.REFUNDED,
        LigneArticle.CREDIT_NOTE,
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
        help_text=_(
            "Changer le statut à la main n'envoie aucun mail et ne touche pas la vente. "
            "Pour une demande à valider, utilisez les boutons « Valider » et « Refuser » en haut de la fiche."
        ),
    )
    booked_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Booked at'),
    )
    annulee_le = models.DateTimeField(
        null=True, blank=True, editable=False, verbose_name=_("Annulée le")
    )

    # Texte libre tapé par l'admin au refus d'une demande, repris dans le mail de refus.
    # / Free text typed by the admin when refusing a request, used in the refusal email.
    motif_du_refus = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Motif du refus"),
        help_text=_("Envoyé à la personne dans le mail de refus."),
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

    # Réponses au formulaire dynamique du produit de la ressource (ProductFormField).
    # Rangées sous le LIBELLÉ de chaque question par build_custom_form_from_request
    # (BaseBillet/validators.py), comme Reservation.custom_form et Membership.custom_form.
    # / Answers to the resource product's dynamic form, keyed by question label.
    custom_form = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("Réponses au formulaire"),
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

    def start_datetime_local(self, fuseau_du_lieu=None):
        """
        Le début du créneau, à l'heure du lieu.
        / Slot start, in venue time.

        En base, les dates sont en UTC. On les convertit dans le fuseau du lieu
        (Configuration.get_tzinfo). Sinon, une réservation à 14h à La Réunion
        s'afficherait 10h.
        / Stored in UTC, converted to the venue timezone.

        :param fuseau_du_lieu: fuseau déjà lu (optionnel). Un export le lit une seule
            fois et le passe ici, pour éviter une requête par ligne.
            / Timezone already read (optional), avoids one query per row.
        """
        if fuseau_du_lieu is None:
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        return self.start_datetime.astimezone(fuseau_du_lieu)

    def end_datetime_local(self, fuseau_du_lieu=None):
        """
        La fin du créneau, à l'heure du lieu.
        / Slot end, in venue time.

        Même principe que start_datetime_local.
        / Same as start_datetime_local.
        """
        if fuseau_du_lieu is None:
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        return self.end_datetime.astimezone(fuseau_du_lieu)

    def date_display(self, fuseau_du_lieu=None):
        """
        La date du début du créneau, lisible : « 13/10/2026 ».
        / Slot start date, human readable.
        """
        return self.start_datetime_local(fuseau_du_lieu).strftime('%d/%m/%Y')

    def start_time_display(self, fuseau_du_lieu=None):
        """
        L'heure de début du créneau, lisible : « 14:30 ».
        / Slot start time, human readable.
        """
        return self.start_datetime_local(fuseau_du_lieu).strftime('%H:%M')

    def end_time_display(self, fuseau_du_lieu=None):
        """
        L'heure de fin du créneau, lisible : « 16:00 ».
        / Slot end time, human readable.
        """
        return self.end_datetime_local(fuseau_du_lieu).strftime('%H:%M')

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
        for ligne_article in self.lignearticles.filter(status__in=Booking.STATUTS_DES_LIGNES_PAYEES):
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

    def est_une_demande_non_payee(self):
        """
        Vrai pour une demande à validation manuelle où aucun argent n'est en jeu :
        - en attente de l'administrateur (ADMIN_WAITING) ;
        - ou validée mais pas encore payée (ADMIN_VALID, rien de payé).
        / True for a manual validation request with no money involved.

        Lue par annulation_possible() et cancel_and_refund_booking().
        """
        if self.status == Booking.ADMIN_WAITING:
            return True
        if self.status == Booking.ADMIN_VALID and self.total_paid() == 0:
            return True
        return False

    def annulation_possible(self):
        """
        Vrai si la personne peut encore annuler.
        - Une demande non payée se retire jusqu'au début du créneau : le délai
          d'annulation protège un remboursement, et ici rien n'a été débité.
        - Sinon, le délai d'annulation de la ressource s'applique.
        / True if the person can still cancel. An unpaid request: until the slot
        starts. Otherwise: the resource's cancellation deadline.

        Lue par booking/views.py (cancel_confirm) et les gabarits « Mes réservations ».
        """
        if self.est_une_demande_non_payee():
            return timezone.now() < self.start_datetime
        return not self.deadline_passed()

    def cancel_text(self):
        if self.can_refund():
            return _("You will be refunded to the credit card used to make the reservation.")
        else:
            return _("The deadline for getting a refund has passed.")

    @atomic
    def annuler_la_demande_non_payee(self, statut_d_annulation, motif_du_refus=""):
        """
        Annule une demande où rien n'est payé : retrait par la personne (USER_CANCELED)
        ou refus par l'admin (ADMIN_CANCELED, avec un motif facultatif).
        / Cancels an unpaid request: withdrawn by the person or refused by the admin.

        LOCALISATION : booking/models.py

        Appelée par cancel_and_refund_booking() et booking/views.py (admin_refuse).
        L'appelant vérifie est_une_demande_non_payee() avant.

        1. Ferme la session Stripe encore ouverte (une demande validée peut en avoir une).
        2. Annule la vente et ses lignes. INDISPENSABLE de passer les lignes en CANCELED
           à la main : annuler_vente() ne change que la vente, pas ses lignes.
        3. Pose le statut, la date d'annulation (récap du matin) et le motif.
        Le créneau est libéré : un booking annulé n'occupe plus de place.
        / Closes the open Stripe session, cancels the sale AND its lines (annuler_vente
        does not touch lines), sets status, date and reason. The slot is freed.
        """
        # Import local : booking_engine importe ce module.
        # / Local import: booking_engine imports this module.
        from booking.booking_engine import expirer_la_session_stripe_ouverte

        expirer_la_session_stripe_ouverte(self)
        for ligne in self.lignearticles.all():
            if ligne.vente is not None:
                annuler_vente(ligne.vente)
            ligne.status = LigneArticle.CANCELED
            ligne.save()

        self.annulee_le = timezone.now()
        self.status = statut_d_annulation
        self.motif_du_refus = motif_du_refus
        self.save()

    @atomic
    def cancel_and_refund_booking(self):
        if self.status in [Booking.USER_CANCELED, Booking.ADMIN_CANCELED]:
            raise Exception(_("This booking is already cancelled."))

        # 0) Demande non payée : rien à rembourser (annuler_la_demande_non_payee).
        # / 0) Unpaid request: nothing to refund.
        if self.est_une_demande_non_payee():
            self.annuler_la_demande_non_payee(Booking.USER_CANCELED)
            return _("Votre demande est annulée. Rien n'a été débité.")

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

        # La date d'annulation sert au récap du matin.
        # / The cancellation date feeds the morning recap.
        self.annulee_le = timezone.now()
        self.status = Booking.USER_CANCELED

        self.save()

        if reglee_hors_stripe_en_argent:
            return _("Votre réservation est annulée. Elle a été réglée sur place : pour un éventuel remboursement, contactez l'organisateur.")
        return self.cancel_text()



    def __str__(self):
        return f'{self.resource} — {self.user} {_("de")} {self.start_datetime} {_("à")} {self.end_datetime}'


# ---------------------------------------------------------------------------
# BÉNÉVOLAT — planning des besoins en bénévoles (façon Framadate)
# / VOLUNTEERING — volunteer needs planning (Framadate style)
#
# Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§4)
#
# PlanningBenevole ──< BesoinBenevole >── TacheBenevole
#                          │
#                          └──< InscriptionBenevole >── TibilletUser
#
# Aucun lien avec la vente : pas de Product vendu, pas de LigneArticle, pas de Stripe.
# Seuls Calendar et ClosedPeriod (les jours de fermeture) sont repris de booking.
# / No link with sales. Only Calendar / ClosedPeriod (closing days) are reused.
#
# Les quatre modèles ont un uuid comme clé primaire : c'est l'identifiant de l'API v2,
# et c'est ce que signe le lien de désistement des mails. Un uuid ne désigne rien dans
# un autre lieu, alors qu'un entier y désignerait la ligne de quelqu'un d'autre.
# / uuid primary keys: API v2 identifier, and safe to sign across tenants.
# ---------------------------------------------------------------------------

# Slugs refusés pour un planning : ce sont des segments des routes
# /booking/benevolat/besoin/… et /booking/benevolat/desistement/… (booking/urls.py).
# / Slugs refused for a planning: they are segments of the volunteering routes.
SLUGS_DE_PLANNING_RESERVES = ["besoin", "desistement"]


class TacheBenevole(models.Model):
    """
    Une tâche que le lieu demande à ses bénévoles : « Tenir le bar », « Faire le ménage ».
    C'est un catalogue du lieu, réutilisé d'un planning à l'autre.
    / A volunteer task of the venue, reused from one planning to the next.

    LOCALISATION : booking/models.py
    """
    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        verbose_name=_("Identifiant"),
    )

    name = models.CharField(
        max_length=200,
        verbose_name=_("Nom de la tâche"),
        help_text=_("Par exemple : « Tenir le bar », « Faire le ménage »."),
    )

    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Consignes"),
        help_text=_(
            "Affichées sous le nom de la tâche sur le planning, et reprises dans le mail "
            "de confirmation : où aller, quoi apporter, à qui parler."
        ),
    )

    class Meta:
        verbose_name = _("Tâche bénévole")
        verbose_name_plural = _("Tâches bénévoles")
        ordering = ["name"]

    def __str__(self):
        return self.name


class PlanningBenevole(models.Model):
    """
    Un tableau de besoins en bénévoles, publié sur le site du lieu.
    Par exemple : « Bar associatif : octobre ».
    / A volunteer needs board, published on the venue website.

    LOCALISATION : booking/models.py

    Page publique : /booking/benevolat/<slug>/

    Deux types (spec §11.2, D29) :
    - PONCTUEL : les besoins sont saisis à la main (ou répétés), datés.
    - HEBDOMADAIRE : une semaine type (LigneDeSemaineType) crée les besoins réels, à partir
      d'aujourd'hui, horizon_en_semaines à l'avance. Création à l'enregistrement de la fiche
      et chaque nuit (booking/benevolat.py, creer_les_besoins_de_la_semaine_type).
      Seulement tant que le planning est actif (published). Les pauses (vacances, fermeture
      d'été) viennent du calendrier des fermetures : ces jours-là, aucun besoin.
    / Two kinds: PONCTUEL (dated needs) or HEBDOMADAIRE (a template week creates real needs,
      from today on, while the planning is active).
    """
    PONCTUEL = "PONCTUEL"
    HEBDOMADAIRE = "HEBDOMADAIRE"
    TYPES_DE_PLANNING = [
        (PONCTUEL, _("Ponctuel")),
        (HEBDOMADAIRE, _("Chaque semaine")),
    ]

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        verbose_name=_("Identifiant"),
    )

    name = models.CharField(
        max_length=250,
        verbose_name=_("Nom du planning"),
        help_text=_("Par exemple : « Bar associatif : octobre »."),
    )

    slug = models.SlugField(
        max_length=250,
        unique=True,
        verbose_name=_("Adresse de la page"),
        help_text=_("La fin de l'adresse publique : /booking/benevolat/nom-du-planning/"),
    )

    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Présentation"),
        help_text=_("Le texte affiché en haut de la page du planning."),
    )

    # Le bouton « activer / désactiver » du planning : il pilote la page publique ET, pour
    # un planning hebdomadaire, la création automatique des besoins.
    # / The planning's on/off switch: public page AND automatic needs creation.
    published = models.BooleanField(
        default=False,
        verbose_name=_("Actif"),
        help_text=_(
            "Actif : le planning est visible sur le site et, s'il est « Chaque semaine », "
            "il crée ses créneaux tout seul. Inactif : il est invisible et ne crée plus rien."
        ),
    )

    # Vide = ouvert à tout compte connecté.
    # Non vide = réservé aux adhérent·es d'au moins une de ces adhésions.
    # Un seul champ : pas de choix « accès » à garder cohérent avec lui.
    # / Empty = open to any logged-in account. Not empty = members of one of these only.
    adhesions_requises = models.ManyToManyField(
        Product,
        blank=True,
        limit_choices_to={"categorie_article": Product.ADHESION},
        related_name="plannings_benevoles",
        verbose_name=_("Adhésions requises"),
        help_text=_(
            "Laisser vide pour ouvrir le planning à toute personne connectée. "
            "Sinon, seules les personnes qui ont au moins une de ces adhésions peuvent s'inscrire."
        ),
    )

    calendrier = models.ForeignKey(
        Calendar,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="plannings_benevoles",
        verbose_name=_("Calendrier des fermetures"),
        help_text=_(
            "Les jours fermés de ce calendrier ne reçoivent aucun créneau (vacances, "
            "fermeture d'été). Laisser vide : aucun jour fermé."
        ),
    )

    delai_desinscription_heures = models.PositiveIntegerField(
        default=24,
        verbose_name=_("Délai pour se retirer (heures)"),
        help_text=_(
            "Moins de ce nombre d'heures avant le créneau, la personne peut encore se retirer, "
            "mais l'équipe est prévenue par mail."
        ),
    )

    type_de_planning = models.CharField(
        max_length=20,
        choices=TYPES_DE_PLANNING,
        default=PONCTUEL,
        verbose_name=_("Type de planning"),
        help_text=_(
            "Ponctuel : vous saisissez les besoins jour par jour. "
            "Chaque semaine : enregistrez, puis saisissez la semaine type ; "
            "les besoins sont créés tout seuls, semaine après semaine."
        ),
    )

    horizon_en_semaines = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(26)],
        verbose_name=_("Semaines ouvertes à l'avance"),
        help_text=_("Chaque semaine : combien de semaines d'avance sont ouvertes aux inscriptions (1 à 26)."),
    )

    # Interne : les besoins de la semaine type sont créés jusqu'à ce jour. Ce qui est
    # avant n'est jamais recréé (un besoin supprimé à la main reste supprimé). Ne recule jamais.
    # / Internal: needs are created up to this day; nothing before it is ever re-created.
    besoins_crees_jusqu_au = models.DateField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("Besoins créés jusqu'au"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Créé le"),
    )

    class Meta:
        verbose_name = _("Planning bénévole")
        verbose_name_plural = _("Plannings bénévoles")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        """
        Refuse les slugs qui sont aussi des segments des routes du bénévolat.
        / Refuses slugs that are also segments of the volunteering routes.

        LOCALISATION : booking/models.py — classe PlanningBenevole

        Sans ce contrôle, un planning au slug « desistement » enverrait le POST de sa
        lettre d'information dans la vue de désistement.
        / Without it, a "desistement" slug would route its newsletter POST to the
        withdrawal view.
        """
        if self.slug in SLUGS_DE_PLANNING_RESERVES:
            raise ValidationError({
                "slug": _("Cette adresse est réservée. Choisissez-en une autre."),
            })

    def date_est_fermee(self, une_date):
        """
        Renvoie la période de fermeture qui couvre ce jour, ou None.
        / Returns the closed period covering this day, or None.

        LOCALISATION : booking/models.py — classe PlanningBenevole

        Un jour est fermé si start_date <= une_date et si end_date est vide
        (fermeture sans fin) ou >= une_date. Planning sans calendrier : jamais fermé.
        / A day is closed if start_date <= day and (end_date empty or >= day).
        """
        if self.calendrier_id is None:
            return None

        # .all() et pas .filter() : l'inline de l'admin précharge les fermetures
        # (prefetch_related) ; .filter() referait une requête par ligne.
        # Un calendrier n'a que quelques fermetures.
        # / .all(): uses the admin inline prefetch, few periods anyway.
        return periode_fermee_qui_couvre(self.calendrier.closed_periods.all(), une_date)

    def libelle_de_fermeture(self, une_date):
        """
        Le texte à afficher pour un jour fermé, ou None si le jour est ouvert.
        / The text to show for a closed day, or None if the day is open.

        LOCALISATION : booking/models.py — classe PlanningBenevole
        """
        periode_fermee = self.date_est_fermee(une_date)
        if periode_fermee is None:
            return None
        return libelle_d_une_fermeture(periode_fermee)


# Les deux fonctions suivantes ne touchent pas la base : elles servent aussi au calcul
# pur de « Répéter des besoins » (booking/benevolat.py, calculer_repetitions).
# / These two functions don't touch the database: also used by calculer_repetitions.

def periode_fermee_qui_couvre(periodes_fermees, une_date):
    """
    Parmi ces périodes de fermeture, celle qui couvre ce jour, ou None.
    Un jour est fermé si start_date <= une_date et si end_date est vide
    (fermeture sans fin) ou >= une_date.
    / Among these closed periods, the one covering this day, or None.
    """
    for periode_fermee in periodes_fermees:
        commence_avant_ou_ce_jour = periode_fermee.start_date <= une_date
        finit_apres_ou_ce_jour = periode_fermee.end_date is None or periode_fermee.end_date >= une_date
        if commence_avant_ou_ce_jour and finit_apres_ou_ce_jour:
            return periode_fermee
    return None


def libelle_d_une_fermeture(periode_fermee):
    """
    Le label de la fermeture s'il existe, sinon « fermé du 14 juillet au 15 juillet »
    (ou « fermé le 14 juillet », « fermé à partir du 14 juillet »).
    / The closure label, or a fallback built from its dates.
    """
    if periode_fermee.label:
        return periode_fermee.label

    debut_de_la_fermeture = date_format(periode_fermee.start_date, "j F")
    if periode_fermee.end_date is None:
        return _("fermé à partir du %(debut)s") % {"debut": debut_de_la_fermeture}
    if periode_fermee.end_date == periode_fermee.start_date:
        return _("fermé le %(debut)s") % {"debut": debut_de_la_fermeture}
    fin_de_la_fermeture = date_format(periode_fermee.end_date, "j F")
    return _("fermé du %(debut)s au %(fin)s") % {
        "debut": debut_de_la_fermeture,
        "fin": fin_de_la_fermeture,
    }


def verifier_les_heures(heure_debut, heure_fin):
    """
    Les règles des heures d'un besoin ou d'une ligne de semaine type, avec un message
    lisible dans l'admin. Lève ValidationError.
    / Hour rules of a need or a template-week row, with a readable admin message.

    - Les deux heures, ou aucune (toute la journée). Même règle que la contrainte en base.
    - Début = fin donnerait un créneau de 24 h : c'est presque toujours une faute de
      frappe. Pour toute la journée, on laisse les deux heures vides.
    """
    une_seule_heure_remplie = (heure_debut is None) != (heure_fin is None)
    if une_seule_heure_remplie:
        raise ValidationError(
            _("Remplissez les deux heures, ou aucune pour toute la journée.")
        )
    if heure_debut is not None and heure_debut == heure_fin:
        raise ValidationError(
            _("Le début et la fin sont à la même heure. Pour toute la journée, laissez les deux heures vides.")
        )


class LigneDeSemaineType(models.Model):
    """
    Une ligne de la semaine type d'un planning hebdomadaire : « le vendredi, Tenir le
    bar, 18h–21h, 2 personnes ». Chaque semaine, elle donne un besoin réel ce jour-là.
    / A template-week row of a weekly planning; each week it gives a real need that day.

    LOCALISATION : booking/models.py
    Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§11.2, D29 à D32)

    Les besoins créés gardent le lien (BesoinBenevole.ligne_de_semaine_type) : modifier la
    ligne met à jour ses besoins futurs sans inscrit (D30, Administration/admin/benevolat.py).
    / Created needs keep the link: editing the row updates its future needs without sign-up.
    """
    LUNDI, MARDI, MERCREDI, JEUDI, VENDREDI, SAMEDI, DIMANCHE = range(7)
    JOURS_DE_LA_SEMAINE = [
        (LUNDI, _("Lundi")),
        (MARDI, _("Mardi")),
        (MERCREDI, _("Mercredi")),
        (JEUDI, _("Jeudi")),
        (VENDREDI, _("Vendredi")),
        (SAMEDI, _("Samedi")),
        (DIMANCHE, _("Dimanche")),
    ]

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        verbose_name=_("Identifiant"),
    )

    planning = models.ForeignKey(
        PlanningBenevole,
        on_delete=models.CASCADE,
        related_name="semaine_type",
        verbose_name=_("Planning"),
    )

    # 0 = lundi … 6 = dimanche : la même numérotation que date.weekday().
    # / 0 = Monday … 6 = Sunday, like date.weekday().
    jour_de_la_semaine = models.PositiveSmallIntegerField(
        choices=JOURS_DE_LA_SEMAINE,
        verbose_name=_("Jour de la semaine"),
    )

    tache = models.ForeignKey(
        TacheBenevole,
        on_delete=models.PROTECT,
        related_name="lignes_de_semaine_type",
        verbose_name=_("Tâche"),
    )

    heure_debut = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_("Début"),
        help_text=_("Laisser les deux heures vides pour toute la journée."),
    )

    heure_fin = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_("Fin"),
        help_text=_("Une fin plus tôt que le début veut dire le lendemain (21:00 → 00:00)."),
    )

    nombre_souhaite = models.PositiveSmallIntegerField(
        default=1,
        verbose_name=_("Nbr postes"),
    )

    class Meta:
        verbose_name = _("Ligne de la semaine type")
        verbose_name_plural = _("Semaine type")
        ordering = ["jour_de_la_semaine", "heure_debut"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(nombre_souhaite__gte=1),
                name="ligne_semaine_type_nombre_souhaite_au_moins_un",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(heure_debut__isnull=True, heure_fin__isnull=True)
                    | models.Q(heure_debut__isnull=False, heure_fin__isnull=False)
                ),
                name="ligne_semaine_type_deux_heures_ou_aucune",
            ),
            models.CheckConstraint(
                check=models.Q(jour_de_la_semaine__lte=6),
                name="ligne_semaine_type_jour_de_0_a_6",
            ),
        ]

    def __str__(self):
        if self.heure_debut is None:
            return f"{self.get_jour_de_la_semaine_display()} — {self.tache} ({_('journée')})"
        return f"{self.get_jour_de_la_semaine_display()} — {self.tache} {self.heure_debut:%H:%M}–{self.heure_fin:%H:%M}"

    def clean(self):
        """Mêmes règles d'heures que les besoins. / Same hour rules as the needs."""
        verifier_les_heures(self.heure_debut, self.heure_fin)


class BesoinBenevole(models.Model):
    """
    Une case du planning : une tâche, un jour, une plage horaire facultative,
    et le nombre de personnes souhaité.
    / A cell of the planning: a task, a day, an optional time range, a wanted count.

    LOCALISATION : booking/models.py

    nombre_souhaite est un OBJECTIF, pas un plafond : on peut toujours s'inscrire
    au-delà (« on peut être 3 sur une tâche prévue pour 2 »).
    / nombre_souhaite is a goal, not a cap.

    Les heures sont saisies en heure locale, sans fuseau. Les gabarits et les mails
    affichent date / heure_debut / heure_fin. debut() et fin() ne servent qu'aux
    comparaisons : TIME_ZONE vaut UTC, un |date sur eux afficherait l'heure UTC.
    / Hours are local, without timezone. Templates show the raw fields;
    debut() / fin() are for comparisons only.
    """
    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        verbose_name=_("Identifiant"),
    )

    planning = models.ForeignKey(
        PlanningBenevole,
        on_delete=models.CASCADE,
        related_name="besoins",
        verbose_name=_("Planning"),
    )

    # PROTECT : on ne supprime pas une tâche qui sert encore à un besoin.
    # / PROTECT: a task still used by a need cannot be deleted.
    tache = models.ForeignKey(
        TacheBenevole,
        on_delete=models.PROTECT,
        related_name="besoins",
        verbose_name=_("Tâche"),
    )

    date = models.DateField(
        verbose_name=_("Jour"),
    )

    heure_debut = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_("Début"),
        help_text=_("Laisser les deux heures vides pour toute la journée."),
    )

    heure_fin = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_("Fin"),
        help_text=_("Une fin plus tôt que le début veut dire le lendemain (21:00 → 00:00)."),
    )

    nombre_souhaite = models.PositiveSmallIntegerField(
        default=1,
        verbose_name=_("Nbr postes"),
        help_text=_("Un objectif, pas un plafond : d'autres personnes peuvent venir en renfort."),
    )

    # Rempli : le besoin a été créé par cette ligne de la semaine type, et la suit
    # (modifier la ligne le met à jour, D30). Vide : un besoin saisi à la main.
    # / Set: created by this template-week row and follows it. Empty: a manual need.
    ligne_de_semaine_type = models.ForeignKey(
        LigneDeSemaineType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="besoins",
        verbose_name=_("Ligne de la semaine type"),
    )

    class Meta:
        verbose_name = _("Besoin bénévole")
        verbose_name_plural = _("Besoins bénévoles")
        ordering = ["date", "heure_debut"]
        # Toutes les requêtes du bénévolat filtrent par planning et par date (D33).
        # / Every volunteering query filters by planning and date.
        indexes = [
            models.Index(fields=["planning", "date"], name="besoin_benevole_planning_date"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(nombre_souhaite__gte=1),
                name="besoin_benevole_nombre_souhaite_au_moins_un",
            ),
            # Les deux heures sont vides (journée), ou les deux sont remplies.
            # / Both hours empty (whole day), or both filled.
            models.CheckConstraint(
                check=(
                    models.Q(heure_debut__isnull=True, heure_fin__isnull=True)
                    | models.Q(heure_debut__isnull=False, heure_fin__isnull=False)
                ),
                name="besoin_benevole_deux_heures_ou_aucune",
            ),
        ]

    def __str__(self):
        if self.heure_debut is None:
            return f"{self.tache} — {self.date} ({_('journée')})"
        return f"{self.tache} — {self.date} {self.heure_debut:%H:%M}–{self.heure_fin:%H:%M}"

    def clean(self):
        """
        Même règle que la contrainte en base, avec un message lisible dans l'admin.
        / Same rule as the database constraint, with a readable admin message.

        LOCALISATION : booking/models.py — classe BesoinBenevole
        """
        verifier_les_heures(self.heure_debut, self.heure_fin)

    def correspond_a_sa_ligne(self):
        """
        Vrai si le besoin a encore les valeurs de sa ligne de semaine type : même jour de
        la semaine, même tâche, mêmes heures, même nombre souhaité.
        / True if the need still has its template-week row's values.
        """
        ligne = self.ligne_de_semaine_type
        return (
            self.date.weekday() == ligne.jour_de_la_semaine
            and self.tache_id == ligne.tache_id
            and self.heure_debut == ligne.heure_debut
            and self.heure_fin == ligne.heure_fin
            and self.nombre_souhaite == ligne.nombre_souhaite
        )

    def est_une_journee(self):
        """
        Vrai si le besoin n'a pas de plage horaire (toute la journée).
        / True if the need has no time range (whole day).
        """
        return self.heure_debut is None

    def debut(self, fuseau_du_lieu=None):
        """
        Le début du besoin, en datetime avec le fuseau du lieu.
        Journée entière : le jour à 00:00.
        / Start of the need, timezone-aware in the venue timezone.

        LOCALISATION : booking/models.py — classe BesoinBenevole

        :param fuseau_du_lieu: fuseau déjà lu (facultatif). La page du planning le lit
            une seule fois et le passe ici : sinon, chaque besoin relit la Configuration.
            / Timezone already read (optional): avoids one Configuration read per need.
        """
        if fuseau_du_lieu is None:
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        if self.est_une_journee():
            heure_de_debut = datetime.time(0, 0)
        else:
            heure_de_debut = self.heure_debut
        return datetime.datetime.combine(self.date, heure_de_debut, tzinfo=fuseau_du_lieu)

    def fin(self, fuseau_du_lieu=None):
        """
        La fin du besoin, en datetime avec le fuseau du lieu.
        - Journée entière : le lendemain à 00:00.
        - heure_fin <= heure_debut : la fin tombe le lendemain (21:00 → 00:00).
        / End of the need, timezone-aware. Whole day: next day 00:00.
        / heure_fin <= heure_debut: ends the next day.

        LOCALISATION : booking/models.py — classe BesoinBenevole

        :param fuseau_du_lieu: fuseau déjà lu (facultatif), comme pour debut().
        """
        if fuseau_du_lieu is None:
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        lendemain = self.date + timedelta(days=1)

        if self.est_une_journee():
            return datetime.datetime.combine(lendemain, datetime.time(0, 0), tzinfo=fuseau_du_lieu)

        se_termine_le_lendemain = self.heure_fin <= self.heure_debut
        if se_termine_le_lendemain:
            jour_de_fin = lendemain
        else:
            jour_de_fin = self.date
        return datetime.datetime.combine(jour_de_fin, self.heure_fin, tzinfo=fuseau_du_lieu)

    def limite_pour_se_retirer_sans_prevenir(self, fuseau_du_lieu=None):
        """
        Avant ce moment, on se retire en silence. Après, le retrait marche aussi, mais
        l'équipe est prévenue (P10) : debut() - delai_desinscription_heures du planning.
        / Before this moment, silent withdrawal; after it, the team is warned.
        """
        return self.debut(fuseau_du_lieu) - timedelta(hours=self.planning.delai_desinscription_heures)

    def save(self, *args, **kwargs):
        """
        Un besoin qui change de jour ou d'heures doit avoir son rappel de la veille pour
        sa NOUVELLE date : on vide rappel_envoye_le de ses inscriptions.
        / A need moved to another day or time gets its reminder again.

        Un besoin enregistré un par un (admin, API) qui ne correspond plus à sa ligne de
        semaine type en est détaché : c'est une exception manuelle, que la ligne n'écrase
        jamais (D30). Les mises à jour faites PAR la ligne passent par queryset.update(),
        qui n'appelle pas save().
        / A need saved one by one that no longer matches its row is detached (manual
        exception). Updates made BY the row use queryset.update(), which skips save().
        """
        if self.ligne_de_semaine_type_id is not None and not self.correspond_a_sa_ligne():
            self.ligne_de_semaine_type = None

        a_change_de_moment = False
        if not self._state.adding:
            ancien = BesoinBenevole.objects.filter(pk=self.pk).values("date", "heure_debut", "heure_fin").first()
            if ancien is not None:
                a_change_de_moment = (
                    ancien["date"] != self.date
                    or ancien["heure_debut"] != self.heure_debut
                    or ancien["heure_fin"] != self.heure_fin
                )
        super().save(*args, **kwargs)
        if a_change_de_moment:
            self.inscriptions.update(rappel_envoye_le=None)

    def est_passe(self, fuseau_du_lieu=None):
        """
        Un besoin est passé quand sa FIN est passée : un besoin 18h–21h reste ouvert à 18h30.
        / A need is past when its END is past.
        """
        return self.fin(fuseau_du_lieu) <= timezone.now()

    def nombre_inscrits(self):
        """Le nombre d'inscriptions. / Number of sign-ups."""
        # len(...all()) et pas count() : la page du planning précharge les inscriptions
        # (prefetch_related). all() lit ce cache, count() ferait une requête par besoin.
        # / len(all()) not count(): reads the prefetch cache instead of one query per need.
        return len(self.inscriptions.all())

    def places_couvertes(self):
        """Les places remplies, sans compter les renforts. / Filled places, without extras."""
        return min(self.nombre_inscrits(), self.nombre_souhaite)

    def places_libres(self):
        """Les places encore à prendre. / Places still to take."""
        return max(0, self.nombre_souhaite - self.nombre_inscrits())

    def nombre_de_renforts(self):
        """Les inscriptions au-delà du nombre souhaité. / Sign-ups beyond the wanted count."""
        return max(0, self.nombre_inscrits() - self.nombre_souhaite)


class InscriptionBenevole(models.Model):
    """
    Une personne s'est positionnée sur un besoin.
    / A person signed up for a need.

    LOCALISATION : booking/models.py

    Se retirer = supprimer la ligne. Il n'y a pas de statut.
    / Withdrawing = deleting the row. No status.
    """
    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        verbose_name=_("Identifiant"),
    )

    besoin = models.ForeignKey(
        BesoinBenevole,
        on_delete=models.CASCADE,
        related_name="inscriptions",
        verbose_name=_("Besoin"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inscriptions_benevoles",
        verbose_name=_("Bénévole"),
    )

    # Sert aussi à l'ordre d'affichage des prénoms : les premiers inscrits d'abord.
    # / Also the display order of first names: earliest first.
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Inscrit·e le"),
    )

    # Rempli quand le mail de rappel de la veille part : empêche un second envoi.
    # / Set when the day-before reminder is sent: prevents a second send.
    rappel_envoye_le = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Rappel envoyé le"),
    )

    # Vide = la personne s'est inscrite elle-même.
    # Rempli = l'admin qui l'a inscrite, ou le compte de la clé API.
    # / Empty = self sign-up. Filled = the admin or the API key account who did it.
    inscrit_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Inscrit·e par"),
    )

    class Meta:
        verbose_name = _("Inscription bénévole")
        verbose_name_plural = _("Inscriptions bénévoles")
        ordering = ["created_at"]
        constraints = [
            # Une personne ne s'inscrit qu'une fois par besoin. Rattrape aussi le double clic.
            # / One sign-up per person and need. Also catches double clicks.
            models.UniqueConstraint(
                fields=["besoin", "user"],
                name="inscription_benevole_une_par_personne_et_besoin",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.besoin}"
