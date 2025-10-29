from uuid import uuid4
import logging
from django.db import models
from django.core.cache import cache

from solo.models import SingletonModel
from django.db import models
from django.utils import timezone
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from stdimage import StdImageField

from BaseBillet.models import Configuration

logger = logging.getLogger(__name__)


# Create your models here.

class CrowdConfig(SingletonModel):
    active = models.BooleanField(default=True, verbose_name=_("Activer Crowds"), help_text=_("Vous pouvez activer ou desactiver cette fonction pour la faire apparaitre dans le menu général."))
    title = models.CharField(max_length=255, blank=True, verbose_name=_("Titre"), default="Contribuez")
    description = models.TextField(blank=True, default="Découvrez les projets à financer et les budgets contributifs")
    vote_button_name = models.CharField(max_length=255, blank=True, verbose_name=_("Nom du bouton de vote"),
                                        default="Ça m'intérèsse !")


class Initiative(models.Model):
    """
    Représente un projet à financer.
    Conforme à schema.org/Project.
    """
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid4)
    name = models.CharField(max_length=255, verbose_name=_("Name"), help_text=_("Name of the contributing project or initiative."))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    short_description = models.CharField(max_length=500, blank=True, verbose_name=_("Short description"), help_text=_("Short description for the cards view and social card."))
    funding_goal = models.PositiveIntegerField(verbose_name=_("Goal (cents)"), help_text=_("Serves only to calculate the percentage claimed by participants."))
    # funded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Montant financé (€)")
    created_at = models.DateTimeField(default=timezone.now, verbose_name=_("Created at"))

    asset = models.ForeignKey("fedow_public.AssetFedowPublic", on_delete=models.PROTECT,
                              related_name="projects", verbose_name=_("Asset"),
                              help_text=_("Force a specific asset for project financing. If empty, it will be in euros."),
                              blank=True, null=True)

    tags = models.ManyToManyField('BaseBillet.Tag', blank=True, related_name='initiatives', verbose_name=_('Tags'))

    # Type de financement : "cascade" ou "adaptatif"
    funding_mode = models.CharField(
        max_length=20,
        choices=[("cascade", "Contribution en cascade"), ("adaptative", "Contribution adaptative")],
        default="adaptative"
    )

    budget_contributif = models.BooleanField(default=False, verbose_name=_("Budget contributif"), help_text=_("Permettez a votre communauté de proposer des actions qui s'inscrivent dans un budget contributif : https://movilab.org/wiki/Coremuneration_et_budget_contributif"))
    currency = models.CharField(max_length=250, default="€", verbose_name=_("Valeur"), help_text=_("Changez la valeur de la contribution : Comptez en €, monnaie locale, monnaie temps, bonbons ?"))
    direct_debit = models.BooleanField(default=False, verbose_name=_("Paiement direct"), help_text=_("Réclamer le paiement de la contribution financière en ligne. Cela redirigera la personne sur Stripe pour un paiement."))

    image = models.URLField(blank=True, null=True, verbose_name="Image (URL)")
    img = StdImageField(upload_to='images/',
                        blank=True, null=True,
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (1280, 1280),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                            'crop_hdr': (960, 540, True),
                            'crop': (480, 270, True),
                            'social_card': (1200, 630, True),
                        },
                        delete_orphans=True, verbose_name=_("Main image"),
                        help_text=_(
                            "The main image of the initiative, displayed in the head of the page and for social shares. If empty, the config image is displayed.")
                        )

    def get_img(self):
        # Cache key based on instance ID and method name
        cache_key = f'event_get_img_{self.pk}'
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return cached_result

        # Algo pour récupérer l'image à afficher.
        if self.img:
            result = self.img
        else:
            config = Configuration.get_solo()
            if config.img:
                logger.info("config img")
                result = config.img
            else:
                result = None

        # Cache the result for 1 hour (3600 seconds)
        cache.set(cache_key, result, 3600)
        return result

    sticker_img = StdImageField(upload_to='images/',
                                blank=True, null=True,
                                variations={
                                    'fhd': (1920, 1920),
                                    'hdr': (1280, 1280),
                                    'med': (480, 480),
                                    'thumbnail': (150, 90),
                                    'crop_hdr': (960, 540, True),
                                    'crop': (480, 270, True),
                                },
                                delete_orphans=True, verbose_name=_("Sticker image"),
                                help_text=_(
                                    "The small image displayed in the events list. If None, img will be displayed. 4x3 ratio.")
                                )

    def __str__(self):
        return self.name

    # --- Financement reçu ---
    @property
    def funded_amount(self):
        return self.contributions.aggregate(models.Sum("amount"))["amount__sum"] or 0

    @property
    def funded_amount_eur(self) -> float:
        """Montant financé en euros (arrondi côté template)."""
        try:
            return (self.funded_amount or 0) / 100
        except Exception:
            return 0

    @property
    def funding_goal_eur(self):
        try:
            return (self.funding_goal or 0) / 100
        except Exception:
            return 0

    # --- Sommes demandées par les participations ---
    @property
    def requested_total_cents(self) -> int:
        """Total des montants demandés pris en compte (en centimes).
        Ne comptabilise pas les participations non validées par un·e admin (APPROVED_ADMIN).
        """
        try:
            return (
                    self.participations
                    .exclude(state=Participation.State.REQUESTED)
                    .aggregate(models.Sum("requested_amount_cents"))
                    ["requested_amount_cents__sum"]
                    or 0
            )
        except Exception:
            return 0

    @property
    def requested_total_eur(self) -> float:
        return (self.requested_total_cents or 0) / 100

    @property
    def requested_vs_funded_percent(self) -> float:
        """Pourcentage demandé par rapport au montant financé.
        Si aucun financement n'a encore été reçu, retourne 0 pour éviter une division par zéro.
        """
        funded = self.funded_amount or 0
        requested = self.requested_total_cents or 0
        if funded <= 0 or requested <= 0:
            return 0
        return (requested / funded) * 100

    @property
    def requested_vs_funded_percent_int(self) -> int:
        try:
            return int(self.requested_vs_funded_percent)
        except Exception:
            return 0

    @property
    def requested_ratio_color(self) -> str:
        """Couleur Bootstrap en fonction des seuils (<80 vert, 80-99 orange, >=100 rouge)."""
        p = self.requested_vs_funded_percent
        if p >= 100:
            return "danger"
        if p >= 80:
            return "warning"
        return "success"

    @property
    def progress_percent(self):
        if self.funding_goal == 0:
            return 0
        return min(100, (self.funded_amount / self.funding_goal) * 100)

    @property
    def progress_percent_int(self):
        try:
            return int(self.progress_percent)
        except Exception:
            return 0

    @property
    def votes_count(self) -> int:
        """Nombre de votes (pertinence publique)."""
        try:
            return self.votes.count()
        except Exception:
            return 0

    def get_absolute_url(self):
        return reverse("crowds-detail", args=[self.uuid])


class Contribution(models.Model):
    """
    Représente une contribution financière à un projet.
    Conforme à schema.org/MonetaryContribution.
    """
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("En attente de paiement")
        PAID = "paid", _("Payée")
        PAID_ADMIN = "admin_paid", _("Indiquée comme payée")

    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid4)
    initiative = models.ForeignKey(Initiative, related_name="contributions", on_delete=models.PROTECT)
    contributor_name = models.CharField(max_length=255, verbose_name=_("Name"), help_text=_("Nom affiché de l'origine de la contribution"), blank=True, null=True)
    description = models.TextField(blank=True, verbose_name=_("Decrivez ce que vous attendez de la contribution, ou envoyez un messages sympa à l'équipe !"))
    contributor = models.ForeignKey("AuthBillet.TibilletUser", related_name="contributions", on_delete=models.PROTECT)
    amount = models.PositiveIntegerField(verbose_name="Montant (centimes)")
    payment_status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, verbose_name=_("Statut de paiement"))
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Payée le"))
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def amount_eur(self) -> float:
        return (self.amount or 0) / 100

    def __str__(self):
        return f"{self.contributor.email} → {self.amount / 100:.2f} {self.initiative.asset.currency_code}"


class Vote(models.Model):
    """
    Vote de pertinence sur une initiative par un utilisateur authentifié.
    Un seul vote par utilisateur et par initiative.
    """
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid4)
    initiative = models.ForeignKey(Initiative, related_name="votes", on_delete=models.CASCADE)
    user = models.ForeignKey("AuthBillet.TibilletUser", related_name="initiative_votes", on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("initiative", "user")

    def __str__(self):
        return f"{self.user.email} → {self.initiative.name}"


class Participation(models.Model):
    """
    Déclaration de participation non financière à une initiative par un utilisateur.
    Sémantique schema.org approximative:
    - L'initiative est un Project (schema.org/Project)
    - Cette participation s'apparente à une Action avec un "object" (le Project) et une "description".
    - Le montant demandé est un MonetaryAmount (nous stockons en centimes: requested_amount_cents).
    - L'état se rapproche de ActionStatusType (proposé, approuvé, terminé, validé).
    """

    class State(models.TextChoices):
        REQUESTED = "requested", _("Demande formulée")  # proposedActionStatus
        APPROVED_ADMIN = "approved_admin", _("Demande validée par un·e admin")  # PotentialActionStatus/Approved
        COMPLETED_USER = "completed_user", _(
            "Participation indiquée comme terminée par l'utilisateur·ice")  # CompletedActionStatus
        VALIDATED_ADMIN = "validated_admin", _("Participation validée par un·e admin")  # Completed/Verified

    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid4)
    initiative = models.ForeignKey(Initiative, related_name="participations", on_delete=models.CASCADE,
                                   help_text=_("Projet concerné (schema.org/Project)"))
    participant = models.ForeignKey(
        "AuthBillet.TibilletUser",
        related_name="crowd_participations",
        on_delete=models.CASCADE,
        help_text=_("Utilisateur·ice qui participe (schema.org/Person)")
    )
    description = models.TextField(blank=False, help_text=_("Description de la participation (schema.org/description)"))
    requested_amount_cents = models.PositiveIntegerField(
        help_text=_("Part du budget sollicité en centimes (schema.org/MonetaryAmount)")
    )
    state = models.CharField(max_length=32, choices=State.choices, default=State.REQUESTED,
                             help_text=_("Statut de l'action (schema.org/ActionStatusType)"))
    time_spent_minutes = models.PositiveIntegerField(null=True, blank=True,
                                                     help_text=_("Temps passé déclaré par la personne (minutes)"))
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Participation")
        verbose_name_plural = _("Participations")
        indexes = [
            models.Index(fields=["initiative", "participant"])
        ]

    @property
    def requested_amount_eur(self) -> float:
        return (self.requested_amount_cents or 0) / 100

    def __str__(self):
        return f"{self.participant.email} → {self.initiative.name} ({self.requested_amount_eur:.2f}€)"
