"""
Modèles de la vente : `Vente` et `Reglement`.
/ Sale models: `Vente` (sale) and `Reglement` (payment).

LOCALISATION : BaseBillet/models_vente.py

Une vente réunit des articles vendus et des règlements :

    Vente ─┬─ n × LigneArticle (article vendu, BaseBillet/models.py)
           └─ n × Reglement    (un règlement par transaction Fedow, paiement Stripe
                                ou encaissement en caisse)

L'argent est écrit une seule fois, en centimes ENTIERS, au moment de la vente. Ensuite,
on ne fait que des sommes. Deux égalités sont vraies pour toute vente réglée :
    Σ règlements                  = Σ totaux catalogue des articles
    Σ règlements hors « offert »  = Σ nets vendus des articles
/ Money is written once, in whole cents, at sale time, then only summed.

Ce module est importé à la fin de `BaseBillet/models.py` : c'est cet import qui fait
connaître `Vente` et `Reglement` à Django (application `BaseBillet`, une seule
migration pour les trois tables).
/ Imported at the end of BaseBillet/models.py, which registers both models with Django.

FLUX :
- `BaseBillet/services_vente.py` est le seul point d'entrée pour écrire une vente
  (ouverture, articles, règlements, encaissement). Ce module ne porte que les tables.
- Les liens vers `Paiement_stripe`, `laboutik.PointDeVente`, `CarteCashless` et
  `Wallet` sont écrits en chaînes (« "BaseBillet.Paiement_stripe" ») : un import direct
  créerait un import circulaire.
  / FKs are written as strings to avoid circular imports.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-montants-entiers.md (§3)
et CHANTIER-05-A-vente-reglement.md (§2).
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

# Cet import lit `BaseBillet/models.py` pendant son chargement : il marche parce que
# `models.py` importe ce module à sa toute fin, quand `SaleOrigin` et `PaymentMethod`
# sont déjà définis. Ne pas remonter l'import de ce module plus haut dans `models.py`.
# / Works because models.py imports this module at its very end. Do not move that import up.
from BaseBillet.models import PaymentMethod, SaleOrigin


class Vente(models.Model):
    """
    Une vente : ses articles (`LigneArticle.vente`) et ses règlements (`Reglement.vente`).
    / A sale: its items and its payments.

    LOCALISATION : BaseBillet/models_vente.py

    CYCLE DE VIE / LIFECYCLE :
        EN_ATTENTE → REGLEE   (encaissement : numéro et empreinte posés sous verrou)
        EN_ATTENTE → ANNULEE  (Stripe a refusé ; pas de numéro, pas de retour arrière)

    Le numéro est une séquence sans trou par lieu. Il reste vide tant que la vente n'est
    pas réglée. Les totaux sont les sommes des articles, stockées à l'encaissement.
    / The number is a gapless sequence per venue, empty until the sale is settled.
    """

    class Nature(models.TextChoices):
        # Une recharge cashless n'est pas une nature : c'est un article
        # `hors_chiffre_affaires` d'une vente ordinaire.
        # / A cashless top-up is not a nature: it is an off-revenue item of a normal sale.
        VENTE = "VENTE", _("Vente")
        AVOIR = "AVOIR", _("Avoir")
        VIDAGE_CARTE = "VIDAGE_CARTE", _("Vidage de carte")
        CORRECTION = "CORRECTION", _("Correction de moyen de paiement")

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", _("En attente")
        REGLEE = "REGLEE", _("Réglée")
        ANNULEE = "ANNULEE", _("Annulée")

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # PostgreSQL accepte plusieurs valeurs vides sous `unique` : seules les ventes
    # réglées portent un numéro, et deux ventes réglées n'ont jamais le même.
    # / PostgreSQL allows several NULLs under `unique`: only settled sales have a number.
    numero = models.PositiveIntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("Numéro"),
    )
    nature = models.CharField(
        max_length=20,
        choices=Nature.choices,
        verbose_name=_("Nature"),
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
        verbose_name=_("Statut"),
    )
    origine = models.CharField(
        max_length=2,
        choices=SaleOrigin.choices,
        verbose_name=_("Origine"),
    )
    # "EUR", ou l'uuid de la monnaie de points : une seule monnaie par vente.
    # / "EUR", or the uuid of the points currency: one currency per sale.
    unite = models.CharField(
        max_length=36,
        default="EUR",
        verbose_name=_("Unité"),
    )

    # Contexte de la vente, tous facultatifs.
    # `point_de_vente` et `vente_liee` entrent dans l'empreinte de la vente : PROTECT
    # empêche qu'une suppression ailleurs les vide et casse la chaîne. Le client,
    # l'opérateur et la carte n'y entrent pas : SET_NULL laisse supprimer un compte.
    # / point_de_vente and vente_liee are part of the sale fingerprint: PROTECT keeps them.
    point_de_vente = models.ForeignKey(
        "laboutik.PointDeVente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ventes",
        verbose_name=_("Point de vente"),
    )
    operateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventes_operees",
        verbose_name=_("Opérateur"),
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventes_achetees",
        verbose_name=_("Client"),
    )
    carte = models.ForeignKey(
        "QrcodeCashless.CarteCashless",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventes",
        verbose_name=_("Carte"),
    )
    # La vente d'origine d'un avoir ou d'une correction.
    # / The original sale of a credit note or a correction.
    vente_liee = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ventes_derivees",
        verbose_name=_("Vente liée"),
    )

    # Sommes des articles, en centimes, stockées à l'encaissement.
    # / Sums of the items, in cents, stored at settlement.
    total_catalogue = models.IntegerField(default=0, verbose_name=_("Total catalogue"))
    total_offert = models.IntegerField(default=0, verbose_name=_("Total offert"))
    total_ttc = models.IntegerField(default=0, verbose_name=_("Total net vendu (TTC)"))
    total_ht = models.IntegerField(default=0, verbose_name=_("Total HT"))
    total_tva = models.IntegerField(default=0, verbose_name=_("Total TVA"))

    datetime_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création"),
    )
    datetime_encaissement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date d'encaissement"),
    )

    # Empreinte chaînée de la vente (posée à l'encaissement).
    # / Chained fingerprint of the sale (set at settlement).
    hmac_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Empreinte"),
    )
    previous_hmac = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Empreinte précédente"),
    )

    # La raison écrite par le caissier quand il corrige un moyen de paiement (vente
    # CORRECTION). Vide pour les autres ventes. Posée avant l'encaissement : une
    # vente réglée ne se modifie plus. Elle n'entre ni dans l'empreinte ni dans
    # l'archive : c'est un commentaire, pas de l'argent.
    # / The cashier's reason for a payment method correction (CORRECTION sale). Empty
    # otherwise. Set before settlement. Not in the fingerprint nor in the archive.
    raison = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Raison"),
        help_text=_(
            "Raison écrite par le caissier lors d'une correction de moyen de paiement."
        ),
    )

    # Clé anti double clic : une même clé = une seule vente.
    # / Anti double-click key: one key = one sale.
    idempotency_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Clé d'idempotence"),
    )

    class Meta:
        ordering = ("-datetime_creation",)
        verbose_name = _("Vente")
        verbose_name_plural = _("Ventes")
        constraints = [
            # Unicité de la clé seulement quand elle est posée.
            # / Key uniqueness only when it is set.
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_vente_idempotency_key",
            ),
        ]
        indexes = [
            # Le rapport des ventes et les clôtures lisent les ventes réglées d'une
            # période (`comptabilite/rapport.py`, `comptabilite/tasks.py`).
            # / The sales report and the closures read the settled sales of a period.
            models.Index(
                fields=["statut", "datetime_encaissement"],
                name="vente_statut_encaissement",
            ),
        ]

    def __str__(self):
        """
        Le nom d'une vente, lu par l'admin (titre de la fiche, fil d'Ariane) :
        « Vente n° 12 », ou « Vente sans numéro — En attente » tant qu'elle n'est pas
        réglée (le numéro n'est posé qu'à l'encaissement).
        / A sale's name for the admin: "Vente n° 12", or "Vente sans numéro — <status>".
        """
        if self.numero is None:
            return _("Vente sans numéro — %(statut)s") % {
                "statut": self.get_statut_display()
            }
        return _("Vente n° %(numero)s") % {"numero": self.numero}

    def save(self, *args, **kwargs):
        """
        Garde d'immutabilité : une vente REGLEE en base refuse toute modification.
        / Immutability guard: a sale SETTLED in the database refuses any change.

        LOCALISATION : BaseBillet/models_vente.py

        On lit le statut EN BASE, pas celui de l'objet en mémoire : `encaisser_vente`
        enregistre la vente au moment où elle passe de EN_ATTENTE à REGLEE, et ce
        passage doit rester permis. Une vente encaissée ne se corrige plus : on fait
        une nouvelle vente (avoir, correction).
        `.update()` ne passe pas par `save()` : c'est l'empreinte de la vente qui
        couvre ce cas.
        / The status is read in the database: settling (PENDING → SETTLED) stays allowed.
        .update() bypasses save(): the sale fingerprint covers that case.
        """
        vente_deja_en_base = not self._state.adding
        if vente_deja_en_base:
            statut_en_base = (
                Vente.objects.filter(pk=self.pk)
                .values_list("statut", flat=True)
                .first()
            )
            if statut_en_base == Vente.Statut.REGLEE:
                raise ValueError(
                    f"La vente {self.uuid} est réglée : elle ne peut plus être "
                    f"modifiée. Pour la corriger, faire un avoir ou une correction."
                )
        super().save(*args, **kwargs)


class Reglement(models.Model):
    """
    Un règlement d'une vente : un montant en centimes entiers, signé, par un moyen.
    / A payment of a sale: a signed whole-cent amount, by one payment method.

    LOCALISATION : BaseBillet/models_vente.py

    Un règlement par transaction Fedow, par paiement Stripe, par encaissement en caisse.
    Le montant n'est jamais calculé : il est COPIÉ de sa source (transaction, paiement
    Stripe, somme encaissée). Un règlement de 0 n'existe pas : la base le refuse.
    / One payment per Fedow transaction, Stripe payment or cash-register collection.
    The amount is copied from its source, never computed. A 0 payment is refused.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vente = models.ForeignKey(
        Vente,
        on_delete=models.PROTECT,
        related_name="reglements",
        verbose_name=_("Vente"),
    )
    moyen = models.CharField(
        max_length=2,
        choices=PaymentMethod.choices,
        verbose_name=_("Moyen de paiement"),
    )
    montant = models.IntegerField(verbose_name=_("Montant (centimes)"))

    # Monnaie, carte et portefeuille : pour le cashless, vides sinon.
    # La carte entre dans l'empreinte de la vente : PROTECT.
    # / Currency, card and wallet: for cashless only. The card is fingerprinted: PROTECT.
    asset = models.UUIDField(null=True, blank=True, verbose_name=_("Monnaie"))
    carte = models.ForeignKey(
        "QrcodeCashless.CarteCashless",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reglements",
        verbose_name=_("Carte"),
    )
    wallet = models.ForeignKey(
        "AuthBillet.Wallet",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reglements",
        verbose_name=_("Portefeuille"),
    )
    # Pas de clé étrangère : `fedow_core` est en SHARED_APPS (schéma public), et
    # `Reglement` en TENANT_APPS (schéma du lieu).
    # / No FK: fedow_core lives in the public schema, Reglement in the venue schema.
    fedow_transaction_uuid = models.UUIDField(
        null=True,
        blank=True,
        verbose_name=_("Transaction Fedow"),
    )
    paiement_stripe = models.ForeignKey(
        "BaseBillet.Paiement_stripe",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reglements",
        verbose_name=_("Paiement Stripe"),
    )
    # Identifiant de remboursement Stripe, numéro de chèque… Vide pour un avoir Stripe
    # fait sans appel à Stripe : le Z le compte « à rembourser à la main ».
    # / Stripe refund id, cheque number… Empty for a Stripe credit note done by hand.
    reference_externe = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Référence externe"),
    )
    datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("Date"))

    class Meta:
        ordering = ("datetime",)
        verbose_name = _("Règlement")
        verbose_name_plural = _("Règlements")
        constraints = [
            # Aucun règlement de 0 : une vente gratuite n'a pas de règlement.
            # / No 0 payment: a free sale has no payment at all.
            models.CheckConstraint(
                check=~Q(montant=0),
                name="reglement_montant_non_nul",
            ),
        ]

    def save(self, *args, **kwargs):
        """
        Garde d'immutabilité : un règlement d'une vente REGLEE refuse toute
        modification.
        / Immutability guard: a payment of a SETTLED sale refuses any change.

        LOCALISATION : BaseBillet/models_vente.py

        On lit en base la vente à laquelle le règlement appartient AUJOURD'HUI : changer
        sa vente dans l'objet en mémoire ne permet pas de sortir de la garde.
        `.update()` ne passe pas par `save()` : c'est l'empreinte de la vente qui
        couvre ce cas.
        / The sale is read in the database, so changing `vente` in memory does not escape.
        """
        reglement_deja_en_base = not self._state.adding
        if reglement_deja_en_base:
            statut_de_la_vente_en_base = (
                Reglement.objects.filter(pk=self.pk)
                .values_list("vente__statut", flat=True)
                .first()
            )
            if statut_de_la_vente_en_base == Vente.Statut.REGLEE:
                raise ValueError(
                    f"Le règlement {self.uuid} appartient à une vente réglée : il ne "
                    f"peut plus être modifié."
                )
        super().save(*args, **kwargs)
