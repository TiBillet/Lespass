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
        (NIVEAU_JOURNALIER, _("Journalière")),
        (NIVEAU_HEBDOMADAIRE, _("Hebdomadaire")),
        (NIVEAU_MENSUEL, _("Mensuelle")),
        (NIVEAU_ANNUEL, _("Annuelle")),
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
        verbose_name=_("Périodicité"),
        help_text=_(
            "La clôture journalière agrège une journée. "
            "Les clôtures hebdomadaire, mensuelle et annuelle agrègent les clôtures journalières correspondantes."
        ),
    )

    numero_sequentiel = models.PositiveIntegerField(
        unique=True,
        verbose_name=_("Numéro séquentiel"),
        help_text=_(
            "Compteur continu global par tenant (conformité LNE). "
            "Partagé entre toutes les périodicités (journalière, hebdomadaire, mensuelle, annuelle)."
        ),
    )

    datetime_debut = models.DateTimeField(
        verbose_name=_("Début de la période"),
    )

    datetime_fin = models.DateTimeField(
        verbose_name=_("Fin de la période"),
    )

    responsable = models.ForeignKey(
        "AuthBillet.TibilletUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clotures_caisse",
        verbose_name=_("Opérateur"),
        help_text=_("Utilisateur ayant déclenché une clôture manuelle. Vide si déclenchement automatique par Celery."),
    )

    total_general = models.IntegerField(
        default=0,
        verbose_name=_("Total TTC (centimes)"),
    )
    total_ht = models.IntegerField(
        default=0,
        verbose_name=_("Total HT (centimes)"),
    )
    total_tva = models.IntegerField(
        default=0,
        verbose_name=_("Total TVA (centimes)"),
    )

    nombre_transactions = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de transactions"),
    )

    total_perpetuel = models.IntegerField(
        default=0,
        verbose_name=_("Total perpétuel (centimes)"),
        help_text=_(
            "Somme des total_general de toutes les clôtures journalières depuis la création du tenant. "
            "Filet de sécurité contre toute modification rétroactive."
        ),
    )

    hash_lignes = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Empreinte des lignes"),
        help_text=_(
            "SHA-256 des tuples (pk, montant, qte, statut) triés de chaque "
            "LigneArticle couverte. Change si une ligne est altérée après clôture."
        ),
    )

    rapport_json = models.JSONField(
        default=dict,
        verbose_name=_("Contenu du rapport"),
        help_text=_(
            "Sections complètes du rapport (totaux par moyen de paiement, ventes par catégorie, "
            "ventilation TVA, adhésions, billets, remboursements, synthèse, informations légales)."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-datetime_fin", "-numero_sequentiel"]
        verbose_name = _("Clôture de caisse")
        verbose_name_plural = _("Clôtures de caisse")
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


class CompteComptable(models.Model):
    """
    Compte comptable utilise pour la ventilation des ecritures (FEC, CSV comptable).
    / Accounting account used for entry dispatch (FEC, accounting CSV exports).

    LOCALISATION : comptabilite/models.py

    Modele paramétrable par tenant. Seed initial via data migration 0002
    (plan comptable francais general PCG). Le tenant peut modifier les
    numeros de compte selon son systeme comptable.
    / Tenant-customizable. Initial seed via data migration 0002 (French PCG).
    """

    TYPE_VENTE = "V"
    TYPE_TVA = "T"
    TYPE_TRESORERIE = "B"
    TYPE_CLIENT = "C"
    TYPE_AUTRE = "X"
    TYPE_CHOICES = [
        (TYPE_VENTE, _("Ventes")),
        (TYPE_TVA, _("TVA collectée")),
        (TYPE_TRESORERIE, _("Trésorerie (banque / caisse)")),
        (TYPE_CLIENT, _("Clients")),
        (TYPE_AUTRE, _("Autre")),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid_lib.uuid4, editable=False)
    numero = models.CharField(
        max_length=12, unique=True,
        verbose_name=_("Numéro de compte"),
    )
    libelle = models.CharField(max_length=120, verbose_name=_("Libellé"))
    type_compte = models.CharField(
        max_length=1, choices=TYPE_CHOICES,
        verbose_name=_("Type de compte"),
    )
    actif = models.BooleanField(default=True, verbose_name=_("Actif"))

    class Meta:
        ordering = ["numero"]
        verbose_name = _("Compte comptable")
        verbose_name_plural = _("Comptes comptables")

    def __str__(self):
        return f"{self.numero} — {self.libelle}"


class MappingMoyenDePaiement(models.Model):
    """
    Mappage d'un moyen de paiement (PaymentMethod) vers un compte comptable.
    / Maps a PaymentMethod code to an accounting account.

    LOCALISATION : comptabilite/models.py
    """

    payment_method = models.CharField(
        max_length=2, unique=True,
        verbose_name=_("Moyen de paiement"),
        help_text=_("Code PaymentMethod de BaseBillet (CC, CA, CH, TR, SF, ...)"),
    )
    compte = models.ForeignKey(
        CompteComptable,
        on_delete=models.PROTECT,
        verbose_name=_("Compte comptable"),
        limit_choices_to={"type_compte__in": ["B", "C"]},
    )

    class Meta:
        ordering = ["payment_method"]
        verbose_name = _("Mapping moyen de paiement")
        verbose_name_plural = _("Mappings moyens de paiement")

    def __str__(self):
        return f"{self.get_payment_method_display()} → {self.compte}"
