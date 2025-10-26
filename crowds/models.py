from uuid import uuid4

from django.db import models
from solo.models import SingletonModel
from django.db import models
from django.utils import timezone
from django.urls import reverse


# Create your models here.

class CrowdConfig(SingletonModel):
    active = models.BooleanField(default=False)


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

    @property
    def funded_amount(self):
        return self.contributions.aggregate(models.Sum("amount"))["amount__sum"] or 0

    @property
    def progress_percent(self):
        if self.funding_goal == 0:
            return 0
        return min(100, (self.funded_amount / self.funding_goal) * 100)

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

    def __str__(self):
        return f"{self.contributor.email} → {self.amount / 100:.2f} {self.initiative.asset.currency_code}"

