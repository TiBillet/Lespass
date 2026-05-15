"""
Modeles de l'app comptabilite.
/ Models of the comptabilite app.

LOCALISATION : comptabilite/models.py

Modele principal : ClotureCaisse.
Une cloture est un instantane agrege des ventes (reservations + adhesions)
sur une periode fermee [datetime_debut, datetime_fin]. Elle stocke un dict
complet (rapport_json) qui permet de regenerer tout le PDF/Excel/CSV/FEC
sans recalculer depuis les LigneArticle.

Le numero_sequentiel est CONTINU GLOBAL par tenant : toutes les clotures
(J + H + M + A) partagent le meme compteur incremental. Conformite LNE V2.

/ Main model: ClotureCaisse. A closure is an aggregated snapshot of sales
(reservations + memberships) for a closed period. Sequential number is
continuous global per tenant (all periodicities share one counter).
"""
import uuid as uuid_lib

from django.db import models
from django.utils.translation import gettext_lazy as _


class ClotureCaisse(models.Model):
    NIVEAU_JOURNALIER = "J"
    NIVEAU_HEBDOMADAIRE = "H"
    NIVEAU_MENSUEL = "M"
    NIVEAU_ANNUEL = "A"
    NIVEAU_CHOICES = [
        (NIVEAU_JOURNALIER, _("Daily")),
        (NIVEAU_HEBDOMADAIRE, _("Weekly")),
        (NIVEAU_MENSUEL, _("Monthly")),
        (NIVEAU_ANNUEL, _("Yearly")),
    ]

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid_lib.uuid4,
        editable=False,
    )

    niveau = models.CharField(
        max_length=1,
        choices=NIVEAU_CHOICES,
        default=NIVEAU_JOURNALIER,
        verbose_name=_("Periodicity"),
        help_text=_(
            "Daily closure aggregates one day. "
            "Weekly/monthly/yearly aggregate the matching daily closures."
        ),
    )

    numero_sequentiel = models.PositiveIntegerField(
        unique=True,
        verbose_name=_("Sequential number"),
        help_text=_(
            "Continuous global counter per tenant (LNE compliance). "
            "Shared across all periodicities (daily, weekly, monthly, yearly)."
        ),
    )

    datetime_debut = models.DateTimeField(
        verbose_name=_("Period start"),
    )

    datetime_fin = models.DateTimeField(
        verbose_name=_("Period end"),
    )

    responsable = models.ForeignKey(
        "AuthBillet.TibilletUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clotures_caisse",
        verbose_name=_("Operator"),
        help_text=_("User who triggered a manual closure. Null if Celery auto."),
    )

    total_general = models.IntegerField(
        default=0,
        verbose_name=_("Total TTC (cents)"),
    )
    total_ht = models.IntegerField(
        default=0,
        verbose_name=_("Total HT (cents)"),
    )
    total_tva = models.IntegerField(
        default=0,
        verbose_name=_("Total VAT (cents)"),
    )

    nombre_transactions = models.IntegerField(
        default=0,
        verbose_name=_("Number of transactions"),
    )

    total_perpetuel = models.IntegerField(
        default=0,
        verbose_name=_("Perpetual total (cents)"),
        help_text=_(
            "Sum of total_general of all daily closures since tenant creation. "
            "Safety check against retroactive modification."
        ),
    )

    hash_lignes = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Lines hash"),
        help_text=_(
            "SHA-256 of sorted (pk, amount, qty, status) tuples of every "
            "LigneArticle covered. Changes if any line is altered post-closure."
        ),
    )

    rapport_json = models.JSONField(
        default=dict,
        verbose_name=_("Report payload"),
        help_text=_(
            "Full report sections (totals by payment method, sales by category, "
            "VAT breakdown, memberships, tickets, refunds, synthesis, legal info)."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-datetime_fin", "-numero_sequentiel"]
        verbose_name = _("Cash closure")
        verbose_name_plural = _("Cash closures")
        indexes = [
            models.Index(fields=["niveau", "-datetime_fin"]),
            models.Index(fields=["-numero_sequentiel"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["niveau", "datetime_debut", "datetime_fin"],
                name="unique_cloture_periode",
            ),
        ]

    def __str__(self):
        return f"{self.get_niveau_display()} #{self.numero_sequentiel} — {self.datetime_fin:%Y-%m-%d}"
