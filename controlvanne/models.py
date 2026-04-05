from uuid import uuid4

from django.db import models
from django.utils import timezone
from decimal import Decimal


class CarteMaintenance(models.Model):
    uid = models.CharField("UID", max_length=32, unique=True,
                           help_text="UID hex sans espaces")
    label = models.CharField("Nom", max_length=100, blank=True)
    is_active = models.BooleanField("Active", default=True)
    produit = models.CharField(
        "Produit de nettoyage", max_length=100, blank=True,
        help_text="Ex : Eau, Désinfectant, Alcool isopropylique…",
    )
    notes = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name = "Carte maintenance"
        verbose_name_plural = "Cartes maintenance"

    def __str__(self):
        return self.label or self.uid


class Card(models.Model):
    uid = models.CharField(max_length=32, unique=True, help_text="UID hex sans espaces")
    label = models.CharField("Nom carte", max_length=100, blank=True)
    is_active = models.BooleanField("Active", default=True)
    valid_from = models.DateTimeField("Valide depuis", null=True, blank=True)
    valid_to = models.DateTimeField("Fin de validité", null=True, blank=True)
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Solde en unité (ex: patate)",
    )

    class Meta:
        verbose_name = "Carte"
        verbose_name_plural = "Cartes"

    def is_valid_now(self):
        now = timezone.now()
        return (
            self.is_active
            and (not self.valid_from or now >= self.valid_from)
            and (not self.valid_to or now <= self.valid_to)
        )

    def __str__(self):
        return self.label or self.uid


class Debimetre(models.Model):
    name = models.CharField(
        "Modèle",
        max_length=100,
        help_text="Modèle du débitmètre (ex: YF-S201, FS300A)",
    )
    flow_calibration_factor = models.FloatField(
        "Facteur de calibration",
        default=6.5,
        help_text="Facteur de calibration (Hz par L/min) — 1 L = facteur × 60 impulsions",
    )

    class Meta:
        verbose_name = "Débitmètre"
        verbose_name_plural = "Débitmètres"

    def __str__(self):
        return f"{self.name} (factor={self.flow_calibration_factor})"


class Fut(models.Model):
    TYPE_CHOICES = [
        ("blonde", "Blonde"),
        ("brune", "Brune"),
        ("ambree", "Ambrée"),
        ("blanche", "Blanche"),
        ("ipa", "IPA"),
        ("stout", "Stout"),
        ("lager", "Lager"),
        ("autre", "Autre"),
    ]

    nom = models.CharField("Nom de la bière", max_length=100)
    brasseur = models.CharField("Brasseur", max_length=100, blank=True)
    type_biere = models.CharField(
        "Type", max_length=20, choices=TYPE_CHOICES, default="blonde"
    )
    degre_alcool = models.DecimalField(
        "Degré d'alcool (%)", max_digits=4, decimal_places=1, default=Decimal("0.0")
    )
    volume_fut_l = models.DecimalField(
        "Volume du fût (L)", max_digits=6, decimal_places=1, default=Decimal("30.0")
    )
    quantite_stock = models.PositiveIntegerField("Quantité en stock", default=0)
    prix_achat = models.DecimalField(
        "Prix d'achat (€)",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Prix d'achat du fût (facultatif)",
    )
    prix_litre = models.DecimalField(
        "Prix au litre (€)",
        max_digits=8,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text="Prix de vente par litre pour ce fût",
    )

    class Meta:
        verbose_name = "Fût"
        verbose_name_plural = "Fûts"
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} — {self.brasseur} ({self.volume_fut_l}L)"


class TireuseBec(models.Model):
    uuid = models.UUIDField(default=uuid4, primary_key=True, editable=False)

    nom_tireuse = models.CharField(max_length=50, help_text="Nom affiché: ex. 'Bière', 'Soft'")

    enabled = models.BooleanField("En service", default=True)
    notes = models.CharField(max_length=200, blank=True)

    @property
    def liquid_label(self) -> str:
        """Nom du liquide affiché sur le kiosk.
        Déduit du fût actif ; retourne 'Liquide' si aucun fût n'est assigné."""
        if self.fut_actif:
            return self.fut_actif.nom
        return "Liquide"

    monnaie = models.CharField(
        max_length=20,
        default="patate",
        help_text="Nom de l'unité de solde (ex: patate)",
    )

    prix_litre_override = models.DecimalField(
        "Prix au litre (override)",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Laisser vide pour utiliser le prix du fût. Renseigner pour forcer un prix sur cette tireuse (réservé admin).",
    )

    @property
    def prix_litre(self) -> Decimal:
        """Prix effectif : override admin si défini ET non nul, sinon prix du fût, sinon 0.00.
        Un override à zéro (ou vide) est ignoré : on remonte le prix du fût."""
        if self.prix_litre_override is not None and self.prix_litre_override > 0:
            return self.prix_litre_override
        if self.fut_actif and self.fut_actif.prix_litre:
            return self.fut_actif.prix_litre
        return Decimal("0.00")

    @property
    def reservoir_max_ml(self) -> float:
        """Volume de référence (fût plein) en ml, pour calcul du % jauge."""
        if self.fut_actif and self.fut_actif.volume_fut_l:
            return float(self.fut_actif.volume_fut_l) * 1000
        return float(self.reservoir_ml) if self.reservoir_ml else 1.0

    @property
    def unit_ml(self) -> Decimal:
        """ml par unité de monnaie — calculé depuis prix_litre. Utilisé par le Pi.
        Retourne 0.00 quand le prix est à zéro : signal « service gratuit »,
        aucune facturation et volume limité par le stock (pas le solde)."""
        if self.prix_litre and self.prix_litre > 0:
            return (Decimal("1000") / self.prix_litre).quantize(Decimal("0.01"))
        return Decimal("0.00")

    fut_actif = models.ForeignKey(
        "Fut",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tireuses_actives",
        verbose_name="Fût en service",
    )

    debimetre = models.ForeignKey(
        "Debimetre",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tireuses",
        help_text="Débitmètre associé (détermine le facteur de calibration)",
    )


    reservoir_ml = models.DecimalField(
        "Volume restant",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Volume courant en ml (décrémenté en temps réel)",
    )
    seuil_mini_ml = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Seuil bas en ml (on réserve ce volume)",
    )
    appliquer_reserve = models.BooleanField(
        default=True, help_text="Appliquer la réserve (stock - seuil)"
    )

    class Meta:
        verbose_name = "Tireuse"
        verbose_name_plural = "Tireuses"

    def __str__(self):
        return self.nom_tireuse


class HistoriqueFut(models.Model):
    tireuse_bec = models.ForeignKey(
        TireuseBec,
        on_delete=models.CASCADE,
        related_name="historique_futs",
        verbose_name="Tireuse",
    )
    fut = models.ForeignKey(
        Fut,
        on_delete=models.CASCADE,
        related_name="historique",
        verbose_name="Fût",
    )
    mis_en_service_le = models.DateTimeField("Mis en service le", default=timezone.now)
    retire_le = models.DateTimeField("Retiré le", null=True, blank=True)
    volume_initial_ml = models.DecimalField(
        "Volume initial (ml)", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    volume_final_ml = models.DecimalField(
        "Volume final (ml)", max_digits=10, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = "Historique fût"
        verbose_name_plural = "Historique fûts"
        ordering = ["-mis_en_service_le"]

    @property
    def volume_consomme_l(self):
        if self.volume_final_ml is not None:
            return float((self.volume_initial_ml - self.volume_final_ml) / 1000)
        return None

    def __str__(self):
        return f"{self.tireuse_bec} ← {self.fut} ({self.mis_en_service_le:%Y-%m-%d})"


class RfidSession(models.Model):
    # presence continue d'une carte (de present=True a present=False)
    uid = models.CharField(max_length=32, db_index=True)
    card = models.ForeignKey(
        Card, null=True, blank=True, on_delete=models.SET_NULL, related_name="sessions"
    )
    label_snapshot = models.CharField(
        "Nom carte", max_length=100, blank=True, help_text="Copie du label au début"
    )
    authorized = models.BooleanField("En service", default=False)
    tireuse_bec = models.ForeignKey(
        TireuseBec,
        on_delete=models.CASCADE,
        related_name="sessions",
        null=True,
        blank=True,
        verbose_name="Nom tireuse",
    )
    liquid_label_snapshot = models.CharField(
        "Nom boisson", max_length=100, blank=True, help_text="Copie du nom du liquide au début"
    )
    unit_label_snapshot = models.CharField(max_length=20, blank=True, default="")
    unit_ml_snapshot = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("100.00")
    )
    allowed_ml_session = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    charged_units = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    started_at = models.DateTimeField("Début", default=timezone.now, db_index=True)
    ended_at = models.DateTimeField("Fin", null=True, blank=True, db_index=True)
    volume_start_ml = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    volume_end_ml = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    volume_delta_ml = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    dernier_volume_ml = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    is_maintenance = models.BooleanField("Session maintenance", default=False)
    is_calibration = models.BooleanField("Session calibration", default=False)
    volume_reel_ml = models.DecimalField(
        "Volume réel (ml)",
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="Volume mesuré physiquement dans un verre gradué",
    )
    carte_maintenance = models.ForeignKey(
        "CarteMaintenance", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sessions",
        verbose_name="Carte maintenance",
    )
    produit_maintenance_snapshot = models.CharField(
        "Produit utilisé", max_length=100, blank=True,
    )

    balance_avant = models.DecimalField(
        "Solde avant",
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Solde de la carte au début de la session",
    )
    balance_apres = models.DecimalField(
        "Solde après",
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Solde de la carte après facturation",
    )
    last_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Session"
        verbose_name_plural = "Sessions"

    @property
    def duration_seconds(self):
        if not self.ended_at:
            return None
        return (self.ended_at - self.started_at).total_seconds()

    def close_with_volume(self, served_volume_ml: float):
        """
        Clôt la session avec le volume cumulatif servi depuis le début de la session.
        `served_volume_ml` est le volume total versé (Pi: flow_meter.volume_l()*1000 - session_start_vol),
        cohérent avec ce que views.py stocke dans volume_delta_ml.
        """
        self.ended_at = timezone.now()
        vol = Decimal(str(float(served_volume_ml or 0))).quantize(Decimal("0.01"))
        self.volume_delta_ml = max(Decimal("0.00"), vol)
        self.volume_end_ml = self.volume_delta_ml
        self.save()

    def __str__(self):
        status = "OPEN" if not self.ended_at else "CLOSED"
        return f"{self.tireuse_bec.nom_tireuse}:{self.uid} [{status}] {self.started_at:%Y-%m-%d %H:%M:%S}"


class SessionCalibration(RfidSession):
    """Vue proxy de RfidSession filtrée sur les sessions de calibration débitmètre."""
    class Meta:
        proxy = True
        verbose_name = "Session calibration"
        verbose_name_plural = "Sessions calibration"


class HistoriqueMaintenance(RfidSession):
    """Vue proxy de RfidSession filtrée sur les sessions maintenance."""
    class Meta:
        proxy = True
        verbose_name = "Historique maintenance"
        verbose_name_plural = "Historique maintenances"


class HistoriqueTireuse(RfidSession):
    """Vue proxy de RfidSession centrée sur les débits par tireuse."""
    class Meta:
        proxy = True
        verbose_name = "Historique tireuse"
        verbose_name_plural = "Historique tireuses"


class HistoriqueCarte(RfidSession):
    """Vue proxy de RfidSession centrée sur les mouvements par carte."""
    class Meta:
        proxy = True
        verbose_name = "Historique carte"
        verbose_name_plural = "Historique cartes"


class Configuration(models.Model):
    """
    Singleton de configuration globale du serveur.
    Un seul objet possible (pk=1 forcé dans save()).
    """
    allow_self_register = models.BooleanField(
        "Autoriser l'auto-enregistrement des Pi",
        default=False,
        help_text=(
            "Activez temporairement pour qu'un nouveau Pi puisse s'enregistrer "
            "automatiquement au démarrage. Désactivez après l'enregistrement."
        ),
    )

    class Meta:
        verbose_name = "Configuration serveur"
        verbose_name_plural = "Configuration serveur"

    def save(self, *args, **kwargs):
        # Singleton : on force toujours pk=1 pour qu'il n'existe qu'un seul objet
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        """Retourne l'objet de configuration (le crée avec les defaults si absent)."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Configuration serveur"
