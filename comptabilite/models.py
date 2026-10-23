"""
Modeles de l'app comptabilite.
/ Models of the comptabilite app.

LOCALISATION : comptabilite/models.py

Modele principal : ClotureCaisse, la cloture unique du lieu.
Une cloture est le rapport fige des ventes reglees du lieu (toutes origines :
caisse, en ligne, admin...) sur une periode [datetime_debut, datetime_fin[. Elle
stocke le rapport complet (rapport_json, `comptabilite/rapport.py`) : le PDF,
l'Excel, les CSV se relisent sans rien recalculer.

- J (journee) : glissante, de la fin de la J precedente au moment de la cloture.
- H, M, A (semaine, mois, annee) : calendaires, en heure locale du lieu.

Le numero_sequentiel est CONTINU GLOBAL par lieu : toutes les clotures
(J + H + M + A) partagent le meme compteur. Elles forment une seule chaine :
chaque cloture porte l'empreinte HMAC de son contenu et celle de la cloture
precedente (`comptabilite/integrite.py`). Conformite LNE V2.

/ Main model: ClotureCaisse, the venue's single closure: the frozen report of the
settled sales of a period, every origin. Sliding J, calendar H / M / A. One global
counter and one chain of fingerprints for every level.
"""
import uuid as uuid_lib

from django.db import models
from django.utils.translation import gettext_lazy as _
from solo.models import SingletonModel


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
            "La clôture journalière va de la clôture journalière précédente à la fin du service. "
            "Les clôtures hebdomadaire, mensuelle et annuelle comptent les ventes de la semaine, "
            "du mois ou de l'année, en heure locale du lieu."
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

    # Le poste depuis lequel la clôture a été lancée. Informatif seulement : une
    # clôture couvre tout le lieu. Hors de l'empreinte de la clôture.
    # / The point of sale the closure was started from. Informative only.
    point_de_vente = models.ForeignKey(
        "laboutik.PointDeVente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clotures_comptables",
        verbose_name=_("Point de vente"),
        help_text=_("Poste depuis lequel la clôture a été lancée (pour information)."),
    )

    numero_premiere_vente = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Numéro de la première vente"),
    )
    numero_derniere_vente = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Numéro de la dernière vente"),
    )

    total_general = models.IntegerField(
        default=0,
        verbose_name=_("Total TTC (centimes)"),
        help_text=_("Chiffre d'affaires TTC de la période."),
    )
    total_ht = models.IntegerField(
        default=0,
        verbose_name=_("Total HT (centimes)"),
    )
    total_tva = models.IntegerField(
        default=0,
        verbose_name=_("Total TVA (centimes)"),
    )

    total_argent_recu = models.IntegerField(
        default=0,
        verbose_name=_("Argent reçu (centimes)"),
        help_text=_("Tout l'argent entré moins tout l'argent sorti sur la période."),
    )

    nombre_transactions = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de ventes"),
    )

    total_perpetuel = models.IntegerField(
        default=0,
        verbose_name=_("Total perpétuel (centimes)"),
        help_text=_(
            "Somme des totaux TTC de toutes les clôtures journalières depuis la mise en service. "
            "Jamais remis à zéro."
        ),
    )

    nombre_ventes_perpetuel = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de ventes perpétuel"),
        help_text=_(
            "Somme des nombres de ventes de toutes les clôtures journalières depuis la mise en service."
        ),
    )

    rapport_json = models.JSONField(
        default=dict,
        verbose_name=_("Contenu du rapport"),
        help_text=_(
            "Toutes les sections du rapport des ventes, figées au moment de la clôture."
        ),
    )

    hmac_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Empreinte"),
        help_text=_("Empreinte HMAC de la clôture, chaînée avec la clôture précédente."),
    )
    previous_hmac = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Empreinte précédente"),
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

    @classmethod
    def derniere_journaliere(cls):
        """
        La dernière clôture journalière (J) du lieu, par numéro, ou None s'il n'y en
        a aucune. C'est la seule lecture de « la dernière J » : le début du service,
        le tiroir de la caisse et les clôtures automatiques la lisent ici.
        / The venue's last daily closure (J), by number, or None. The single read of
        "the last J".
        """
        return (
            cls.objects.filter(niveau=cls.NIVEAU_JOURNALIER)
            .order_by("-numero_sequentiel")
            .first()
        )


class ConfigurationDesRapports(SingletonModel):
    """
    Les réglages des envois automatiques du lieu : le récap du matin et les rapports
    de clôture hebdomadaire, mensuelle et annuelle. Un booléen par envoi, une seule
    liste de destinataires pour tous.
    / The venue's automatic mail settings: one boolean per mail, one recipient list.

    LOCALISATION : comptabilite/models.py

    LUE PAR :
    - Administration/recap_quotidien.py (`destinataires_du_recap`,
      `envoyer_le_recap_du_lieu_si_c_est_l_heure`) : le booléen J et la liste ;
    - comptabilite/tasks.py (`demander_l_email_automatique_si_configure`,
      `_envoyer_l_email_de_la_cloture`) : les booléens H, M, A et la liste.
    Seule la liste reçoit les mails : aucun admin n'est destinataire d'office.
    / Only the list receives the mails: no admin is a recipient by default.

    Spécification : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/CHANTIER-02-recap-allege.md §5.
    """

    envoyer_le_recap_quotidien = models.BooleanField(
        default=True,
        verbose_name=_("Récap du matin"),
        help_text=_(
            "Chaque matin, ce qui s'est passé la veille, avec le ticket Z de la journée "
            "en pièce jointe."
        ),
    )
    envoyer_le_rapport_hebdomadaire = models.BooleanField(
        default=True,
        verbose_name=_("Rapport hebdomadaire"),
        help_text=_(
            "Le ticket Z de la semaine, avec les chiffres de l'activité de la semaine."
        ),
    )
    envoyer_le_rapport_mensuel = models.BooleanField(
        default=True,
        verbose_name=_("Rapport mensuel"),
        help_text=_("Le ticket Z du mois, avec les chiffres de l'activité du mois."),
    )
    envoyer_le_rapport_annuel = models.BooleanField(
        default=True,
        verbose_name=_("Rapport annuel"),
        help_text=_("Le ticket Z de l'année."),
    )

    # Le M2M vise le proxy HumanUser, pas TibilletUser : son manager ne rend que les
    # users du lieu courant (`client_achat`). C'est ce queryset qui VALIDE les pk
    # postés par le formulaire de l'admin : un pk forcé vers un user d'un autre lieu
    # est refusé. Piège : `.add()` exige une instance HumanUser ; avec un TibilletUser
    # (ce que rend `get_or_create_user`), écrire `.add(user.pk)`.
    # / The M2M targets the HumanUser proxy: its manager only holds this venue's users
    # and validates the posted pks. `.add()` needs a HumanUser: use `.add(user.pk)`.
    destinataires = models.ManyToManyField(
        "AuthBillet.HumanUser",
        blank=True,
        related_name="rapports_recus",
        verbose_name=_("Destinataires"),
        help_text=_(
            "Les personnes qui reçoivent ces mails. Recherche parmi les personnes du "
            "lieu. Liste vide : aucun mail."
        ),
    )

    class Meta:
        verbose_name = _("Envoi des rapports")
        verbose_name_plural = _("Envoi des rapports")

    def __str__(self):
        return str(_("Envoi des rapports"))

    def envoie_le_rapport_du_niveau(self, niveau):
        """
        Vrai si le rapport de clôture de ce niveau (H, M ou A) est coché. Une J n'a pas
        de rapport à elle : son Z part dans le récap du matin (`envoyer_le_recap_quotidien`).
        / True if the closure report of this level (H, M or A) is ticked.
        """
        if niveau == ClotureCaisse.NIVEAU_HEBDOMADAIRE:
            return self.envoyer_le_rapport_hebdomadaire
        if niveau == ClotureCaisse.NIVEAU_MENSUEL:
            return self.envoyer_le_rapport_mensuel
        if niveau == ClotureCaisse.NIVEAU_ANNUEL:
            return self.envoyer_le_rapport_annuel
        return False

    def adresses_des_destinataires(self):
        """
        Les e-mails des destinataires : minuscules, sans espaces, sans doublon, sans
        vide, triés par e-mail.
        / The recipients' e-mails: lowercase, trimmed, no duplicates, no blanks.
        """
        adresses = []
        for destinataire in self.destinataires.order_by("email"):
            adresse = (destinataire.email or "").strip().lower()
            if adresse and adresse not in adresses:
                adresses.append(adresse)
        return adresses
