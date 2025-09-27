from django.db import models
from uuid import uuid4
from django.db.models import UniqueConstraint, Q
from django.utils.translation import gettext_lazy as _


class AssetFedowPublic(models.Model):
    """
    Le nouveau model fédéré d'asset
    On internalise Fedow tipatipa en attendant le grand nétoyage de la V2
    """

    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=100, db_index=True)
    currency_code = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    wallet_origin = models.ForeignKey('AuthBillet.Wallet', on_delete=models.PROTECT, related_name='assets_fedow_public')
    origin = models.ForeignKey('Customers.Client', on_delete=models.CASCADE,
                               related_name="assets_fedow_public")  # La bonne relation a utiliser au lieu des deux précédents, relicats de la migration

    STRIPE_FED_FIAT = 'FED'
    TOKEN_LOCAL_FIAT = 'TLF'
    TOKEN_LOCAL_NOT_FIAT = 'TNF'
    TIME = 'TIM'
    FIDELITY = 'FID'
    BADGE = 'BDG'
    SUBSCRIPTION = 'SUB'

    CATEGORIES = [
        (TOKEN_LOCAL_FIAT, _('Fiduciaire')),
        (TOKEN_LOCAL_NOT_FIAT, _('Cadeau')),
        (STRIPE_FED_FIAT, _('Fiduciaire fédérée')),
        (TIME, _("Monnaie temps")),
        (FIDELITY, _("Points de fidélité")),
        (BADGE, _("Badgeuse/Pointeuse")),
        (SUBSCRIPTION, _('Adhésion ou abonnement')),
    ]

    category = models.CharField(
        max_length=3,
        choices=CATEGORIES
    )

    pending_invitations = models.ManyToManyField('Customers.Client', related_name="pending_invitations_fedow_public",
                                                 blank=True,
                                                 verbose_name=_("Partager cet actif"),
                                                 help_text=_(
                                                     "Invitez une organisation à partager cet actif, il recevra un mail de confirmation. Une fois validé, l'actif disparaitra de cette liste pour aller dans celle ci dessous"),
                                                 )
    federated_with = models.ManyToManyField('Customers.Client', related_name="federated_assets_fedow_public",
                                            verbose_name=_("Lieux fédérés"),
                                            help_text=_("Lieux fédérés"),
                                            blank=True)

    def __str__(self):
        return self.name

    class Meta:
        # Only one can be true :
        constraints = [UniqueConstraint(fields=["category"],
                                        condition=Q(category='FED'),
                                        name="unique_primary_asset")]
