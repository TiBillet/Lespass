from uuid import uuid4

from django.db import models
from solo.models import SingletonModel
from django.db import models
from django.utils import timezone
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


# Create your models here.

class CrowdConfig(SingletonModel):
    active = models.BooleanField(default=False, verbose_name="Activer")
    title = models.CharField(max_length=255, blank=True, verbose_name=_("Titre"), default="Financement participatif")
    description = models.TextField(blank=True, default="Découvrez les projets en cours de financement participatif")
    vote_button_name = models.CharField(max_length=255, blank=True, verbose_name=_("Nom du bouton de vote"), default="Voter")

class Initiative(models.Model):
    """
    Représente un projet à financer.
    Conforme à schema.org/Project.
    """
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid4)
    name = models.CharField(max_length=255, verbose_name="Nom du projet")
    description = models.TextField(blank=True, verbose_name="Description")
    image = models.URLField(blank=True, null=True, verbose_name="Image (URL)")
    funding_goal = models.PositiveIntegerField(verbose_name="Objectif (centimes)")
    # funded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Montant financé (€)")
    created_at = models.DateTimeField(default=timezone.now)
    asset = models.ForeignKey("fedow_public.AssetFedowPublic", on_delete=models.PROTECT, related_name="projects")

    # Type de financement : "cascade" ou "adaptatif"
    funding_mode = models.CharField(
        max_length=20,
        choices=[("cascade", "Contribution en cascade"), ("adaptative", "Contribution adaptative")],
        default="adaptative"
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
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid4)
    initiative = models.ForeignKey(Initiative, related_name="contributions", on_delete=models.PROTECT)
    contributor = models.ForeignKey("AuthBillet.TibilletUser", related_name="contributions", on_delete=models.PROTECT)
    amount = models.PositiveIntegerField(verbose_name="Montant (centimes)")
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
        COMPLETED_USER = "completed_user", _("Participation indiquée comme terminée par l'utilisateur·ice")  # CompletedActionStatus
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

