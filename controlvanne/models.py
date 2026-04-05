"""
Modeles du module tireuse connectee (controlvanne).
/ Models for the connected tap module (controlvanne).

LOCALISATION : controlvanne/models.py

Modeles definis ici :
- Configuration : singleton de configuration du module tireuse (django-solo)
- Debimetre : modele et facteur de calibration du capteur de debit
- CarteMaintenance : carte NFC dediee aux operations de maintenance (OneToOne CarteCashless)
- TireuseBec : une tireuse physique avec son fut, son debimetre, son point de vente
- RfidSession : session de service d'un liquide (de la pose a la depose de la carte NFC)
- SessionCalibration : proxy RfidSession pour les sessions de calibration
- HistoriqueMaintenance : proxy RfidSession pour les sessions de maintenance
- HistoriqueTireuse : proxy RfidSession pour les debits par tireuse
- HistoriqueCarte : proxy RfidSession pour les mouvements par carte

Dependances externes :
- QrcodeCashless.CarteCashless : carte NFC physique (SHARED_APPS)
- BaseBillet.Product : produit unifie (categorie_article='U' pour les futs)
- BaseBillet.LigneArticle : ligne de vente POS
- laboutik.PointDeVente : point de vente physique ou virtuel
- discovery.PairingDevice : appareil en attente d'appairage
- inventaire.Stock : stock d'un produit (OneToOne Product)
- solo.SingletonModel : singleton propre (pas de hack pk=1)
"""

from uuid import uuid4
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from solo.models import SingletonModel
from rest_framework_api_key.models import AbstractAPIKey


# ──────────────────────────────────────────────────────────────────────
# Configuration — singleton django-solo
# ──────────────────────────────────────────────────────────────────────


class Configuration(SingletonModel):
    """
    Singleton de configuration du module tireuse.
    / Singleton configuration for the connected tap module.
    LOCALISATION : controlvanne/models.py
    """

    class Meta:
        verbose_name = _("Tap module configuration")
        verbose_name_plural = _("Tap module configuration")

    def __str__(self):
        return str(_("Tap module configuration"))


# ──────────────────────────────────────────────────────────────────────
# TireuseAPIKey — clé API dédiée aux Raspberry Pi des tireuses
# / TireuseAPIKey — API key dedicated to tap Raspberry Pi devices
# ──────────────────────────────────────────────────────────────────────


class TireuseAPIKey(AbstractAPIKey):
    """
    Clé API dédiée aux tireuses connectées (controlvanne).
    Même pattern que LaBoutikAPIKey mais pour les tireuses.
    Créée par discovery lors de l'appairage d'un Pi.
    / API key dedicated to connected taps (controlvanne).
    Same pattern as LaBoutikAPIKey but for taps.
    Created by discovery when pairing a Pi.
    LOCALISATION : controlvanne/models.py
    """

    class Meta:
        ordering = ("-created",)
        verbose_name = _("Tap API Key")
        verbose_name_plural = _("Tap API Keys")


# ──────────────────────────────────────────────────────────────────────
# Debimetre — capteur de debit
# ──────────────────────────────────────────────────────────────────────


class Debimetre(models.Model):
    """
    Modele de debitmetre utilise sur les tireuses.
    Le facteur de calibration convertit les impulsions du capteur en volume.
    / Flow meter model used on taps.
    The calibration factor converts sensor pulses to volume.
    LOCALISATION : controlvanne/models.py
    """

    name = models.CharField(
        max_length=100,
        verbose_name=_("Model"),
        help_text=_("Flow meter model (e.g. YF-S201, FS300A)"),
    )
    flow_calibration_factor = models.FloatField(
        default=6.5,
        verbose_name=_("Calibration factor"),
        help_text=_("Calibration factor (Hz per L/min) — 1 L = factor × 60 pulses"),
    )

    class Meta:
        verbose_name = _("Flow meter")
        verbose_name_plural = _("Flow meters")

    def __str__(self):
        return f"{self.name} (factor={self.flow_calibration_factor})"


# ──────────────────────────────────────────────────────────────────────
# CarteMaintenance — carte NFC de maintenance (OneToOne CarteCashless)
# ──────────────────────────────────────────────────────────────────────


class CarteMaintenance(models.Model):
    """
    Carte NFC dediee aux operations de maintenance et nettoyage des tireuses.
    Meme patron que CartePrimaire dans laboutik : OneToOne vers CarteCashless.
    / NFC card dedicated to tap maintenance and cleaning operations.
    Same pattern as CartePrimaire in laboutik: OneToOne to CarteCashless.
    LOCALISATION : controlvanne/models.py
    """

    carte = models.OneToOneField(
        "QrcodeCashless.CarteCashless",
        on_delete=models.CASCADE,
        related_name="carte_maintenance",
        verbose_name=_("NFC card"),
    )
    tireuses = models.ManyToManyField(
        "controlvanne.TireuseBec",
        blank=True,
        related_name="cartes_maintenance",
        verbose_name=_("Authorized taps"),
        help_text=_("Leave empty for all taps."),
    )
    produit = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Cleaning product"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("Notes"),
    )

    class Meta:
        verbose_name = _("Maintenance card")
        verbose_name_plural = _("Maintenance cards")

    def __str__(self):
        return str(self.carte)


# ──────────────────────────────────────────────────────────────────────
# TireuseBec — tireuse physique
# ──────────────────────────────────────────────────────────────────────


class TireuseBec(models.Model):
    """
    Une tireuse physique (un bec) avec son fut actif, son debimetre, et son POS.
    / A physical tap (one spout) with its active keg, flow meter, and POS.
    LOCALISATION : controlvanne/models.py
    """

    uuid = models.UUIDField(default=uuid4, primary_key=True, editable=False)

    nom_tireuse = models.CharField(
        max_length=50,
        verbose_name=_("Tap name"),
        help_text=_("Display name: e.g. 'Beer', 'Soft drink'"),
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("In service"),
    )
    notes = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Notes"),
    )

    # --- Relations ---

    point_de_vente = models.OneToOneField(
        "laboutik.PointDeVente",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tireuse",
        verbose_name=_("Point of sale"),
        help_text=_("POS linked to this tap (auto-created or manually assigned)."),
    )

    fut_actif = models.ForeignKey(
        "BaseBillet.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tireuses_actives",
        verbose_name=_("Active keg"),
        limit_choices_to={"categorie_article": "U"},
        help_text=_("Product of type FUT currently on this tap."),
    )

    debimetre = models.ForeignKey(
        "controlvanne.Debimetre",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tireuses",
        verbose_name=_("Flow meter"),
        help_text=_("Associated flow meter (determines calibration factor)."),
    )

    pairing_device = models.ForeignKey(
        "discovery.PairingDevice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tireuses",
        verbose_name=_("Pairing device"),
        help_text=_("Raspberry Pi or ESP32 controlling this tap."),
    )

    # --- Volume / jauge ---

    reservoir_ml = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Remaining volume"),
        help_text=_("Current volume in ml (decremented in real time)."),
    )
    seuil_mini_ml = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Minimum threshold"),
        help_text=_("Low threshold in ml (this volume is reserved)."),
    )
    appliquer_reserve = models.BooleanField(
        default=True,
        verbose_name=_("Apply reserve"),
        help_text=_("Apply reserve (stock - threshold)."),
    )

    # --- Proprietes calculees ---

    @property
    def liquid_label(self) -> str:
        """Nom du liquide affiche sur le kiosk.
        Deduit du fut actif ; retourne 'Liquide' si aucun fut n'est assigne.
        / Liquid name displayed on the kiosk.
        Derived from the active keg; returns 'Liquide' if none assigned."""
        if self.fut_actif:
            return self.fut_actif.name
        return "Liquide"

    @property
    def prix_litre(self) -> Decimal:
        """Prix au litre depuis le premier Price poids_mesure du fut actif.
        Retourne Decimal('0.00') si aucun prix n'est trouve.
        / Per-liter price from the first poids_mesure Price of the active keg.
        Returns Decimal('0.00') if no price found."""
        if self.fut_actif:
            price = self.fut_actif.prices.filter(poids_mesure=True).first()
            if price and price.prix:
                return price.prix
        return Decimal("0.00")

    @property
    def reservoir_max_ml(self) -> float:
        """Volume de reference (fut plein) en ml, pour calcul du % jauge.
        Lit la quantite initiale depuis le Stock inventaire du fut actif.
        / Reference volume (full keg) in ml, for gauge % calculation.
        Reads initial quantity from the active keg's inventory Stock."""
        if self.fut_actif:
            try:
                from inventaire.models import Stock

                stock = Stock.objects.filter(product=self.fut_actif).first()
                if stock and stock.quantite > 0:
                    # Stock en centilitres → conversion en ml
                    # / Stock in centiliters → convert to ml
                    return float(stock.quantite) * 10
            except Exception:
                pass
        return float(self.reservoir_ml) if self.reservoir_ml else 1.0

    class Meta:
        verbose_name = _("Tap")
        verbose_name_plural = _("Taps")

    def __str__(self):
        return self.nom_tireuse


# ──────────────────────────────────────────────────────────────────────
# RfidSession — session de service (pose → depose de la carte NFC)
# ──────────────────────────────────────────────────────────────────────


class RfidSession(models.Model):
    """
    Presence continue d'une carte NFC sur une tireuse (de present=True a present=False).
    Chaque session enregistre le volume servi, la tireuse, et la carte utilisee.
    / Continuous presence of an NFC card on a tap (from present=True to present=False).
    Each session records the volume served, the tap, and the card used.
    LOCALISATION : controlvanne/models.py
    """

    uid = models.CharField(
        max_length=32,
        db_index=True,
        verbose_name=_("Card UID"),
    )
    carte = models.ForeignKey(
        "QrcodeCashless.CarteCashless",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rfid_sessions",
        verbose_name=_("NFC card"),
    )
    label_snapshot = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Card name"),
        help_text=_("Copy of the card label at session start."),
    )
    authorized = models.BooleanField(
        default=False,
        verbose_name=_("Authorized"),
    )
    tireuse_bec = models.ForeignKey(
        "controlvanne.TireuseBec",
        on_delete=models.CASCADE,
        related_name="sessions",
        null=True,
        blank=True,
        verbose_name=_("Tap"),
    )
    liquid_label_snapshot = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Beverage name"),
        help_text=_("Copy of the liquid name at session start."),
    )
    allowed_ml_session = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Allowed ml"),
        help_text=_("Maximum volume allowed for this session (ml)."),
    )

    # --- Lien vers la ligne de vente POS ---

    ligne_article = models.ForeignKey(
        "BaseBillet.LigneArticle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rfid_sessions",
        verbose_name=_("Sale line"),
        help_text=_("POS sale line created for this session."),
    )

    # --- Temps ---

    started_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name=_("Start"),
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("End"),
    )

    # --- Volume ---

    volume_start_ml = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Volume start (ml)"),
    )
    volume_end_ml = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Volume end (ml)"),
    )
    volume_delta_ml = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Volume served (ml)"),
    )
    dernier_volume_ml = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Last volume (ml)"),
    )

    # --- Maintenance / calibration ---

    is_maintenance = models.BooleanField(
        default=False,
        verbose_name=_("Maintenance session"),
    )
    is_calibration = models.BooleanField(
        default=False,
        verbose_name=_("Calibration session"),
    )
    volume_reel_ml = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Actual volume (ml)"),
        help_text=_("Volume physically measured in a graduated glass."),
    )
    carte_maintenance = models.ForeignKey(
        "controlvanne.CarteMaintenance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sessions",
        verbose_name=_("Maintenance card"),
    )
    produit_maintenance_snapshot = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Cleaning product used"),
    )

    # --- Divers ---

    last_message = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Last message"),
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("Session")
        verbose_name_plural = _("Sessions")

    @property
    def duration_seconds(self):
        """Duree de la session en secondes. None si la session est encore ouverte.
        / Session duration in seconds. None if session is still open."""
        if not self.ended_at:
            return None
        return (self.ended_at - self.started_at).total_seconds()

    def close_with_volume(self, served_volume_ml: float):
        """
        Clot la session avec le volume cumulatif servi depuis le debut de la session.
        `served_volume_ml` est le volume total verse (Pi: flow_meter.volume_l()*1000 - session_start_vol),
        coherent avec ce que views.py stocke dans volume_delta_ml.
        / Close the session with the cumulative volume served since session start.
        """
        self.ended_at = timezone.now()
        vol = Decimal(str(float(served_volume_ml or 0))).quantize(Decimal("0.01"))
        self.volume_delta_ml = max(Decimal("0.00"), vol)
        self.volume_end_ml = self.volume_delta_ml
        self.save()

    def __str__(self):
        status = "OPEN" if not self.ended_at else "CLOSED"
        return f"{self.tireuse_bec.nom_tireuse}:{self.uid} [{status}] {self.started_at:%Y-%m-%d %H:%M:%S}"


# ──────────────────────────────────────────────────────────────────────
# Proxy models — vues filtrees de RfidSession pour l'admin
# ──────────────────────────────────────────────────────────────────────


class SessionCalibration(RfidSession):
    """Vue proxy de RfidSession filtree sur les sessions de calibration debitmetre.
    / Proxy view of RfidSession filtered on flow meter calibration sessions."""

    class Meta:
        proxy = True
        verbose_name = _("Calibration session")
        verbose_name_plural = _("Calibration sessions")


class HistoriqueMaintenance(RfidSession):
    """Vue proxy de RfidSession filtree sur les sessions maintenance.
    / Proxy view of RfidSession filtered on maintenance sessions."""

    class Meta:
        proxy = True
        verbose_name = _("Maintenance history")
        verbose_name_plural = _("Maintenance history")


class HistoriqueTireuse(RfidSession):
    """Vue proxy de RfidSession centree sur les debits par tireuse.
    / Proxy view of RfidSession focused on volumes per tap."""

    class Meta:
        proxy = True
        verbose_name = _("Tap history")
        verbose_name_plural = _("Tap history")


class HistoriqueCarte(RfidSession):
    """Vue proxy de RfidSession centree sur les mouvements par carte.
    / Proxy view of RfidSession focused on movements per card."""

    class Meta:
        proxy = True
        verbose_name = _("Card history")
        verbose_name_plural = _("Card history")
