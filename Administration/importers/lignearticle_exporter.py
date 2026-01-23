import logging
from decimal import Decimal, ROUND_HALF_UP

import pytz

from django.utils.translation import gettext_lazy as _
from import_export import resources
from import_export.fields import Field

from BaseBillet.models import Configuration, LigneArticle

logger = logging.getLogger(__name__)

class LigneArticleExportResource(resources.ModelResource):
    # Cached timezone to prevent from loading for each line
    _cached_timezone = None

    uuid = Field(attribute='uuid', column_name=_('Référence paiement'))
    date = Field(attribute='datetime', column_name=_('Date'))
    product = Field(attribute='pricesold', column_name=_("Libellé"))
    qty = Field(attribute='qty', column_name=_("Quantité"))
    amount = Field(attribute='amount', column_name=_("Prix Unitaire"))
    vat = Field(attribute='vat', column_name=_("VAT"))
    total = Field(column_name=_("Montant"))
    payment_method = Field(column_name=_("Payment method"))
    status = Field(column_name=_("Product entry status"))
    user_email = Field(column_name=_("User Email"))
    paiement_stripe = Field(column_name=_("Stripe payment"))
    carte = Field(attribute='carte',column_name=_("Carte cashless"))
    wallet = Field(attribute='wallet',column_name=_("Wallet from"))

    def get_export_headers(self, selected_fields=None, *args, **kwargs):
        fields = selected_fields or self.get_export_fields(*args, **kwargs)
        return [f.column_name for f in fields]

    def before_export(self, queryset, *args, **kwargs):
        try:
            config = Configuration.get_solo()
            self._cached_timezone = pytz.timezone(config.fuseau_horaire)
        except Exception as e:
            self._cached_timezone = pytz.UTC
            logger.warning(f"Impossible to get timezone config: {e}")

    class Meta:
        model = LigneArticle
        fields = (
            'uuid',
            'date',
            'product',
            'qty',
            'amount',
            'vat',
            'total',
            'payment_method',
            'status',
            'user_email',
            'paiement_stripe',
            'carte',
            'wallet'
        )
        export_order = ('uuid', 'date','product','qty','amount','vat','total','payment_method','status','user_email','paiement_stripe','carte','wallet')

    def dehydrate_date(self, line):
        """
        Format event_datetime in a human-readable format with the venue's timezone.
        """
        if not line.datetime:
            return ""
        try:
            localized_datetime = line.datetime.astimezone(self._cached_timezone)
            return localized_datetime.strftime('%Y-%m-%d')
        except Exception:
            return line.datetime.strftime('%Y-%m-%d')

    def dehydrate_qty(self, line):
        return self.round_decimal(line.qty)

    def dehydrate_vat(self, line):
        return self.round_decimal(line.vat)

    def dehydrate_amount(self, line):
        return line.amount/100

    def dehydrate_total(self, line):
        return line.total()/100

    def dehydrate_status(self, line):
        return line.get_status_display()

    def dehydrate_payment_method(self, line):
        return line.get_payment_method_display()

    def dehydrate_user_email(self, line):
        return line.user_email()

    def dehydrate_paiement_stripe(self, line):
        return line.paiement_stripe_uuid()

    @staticmethod
    def round_decimal(value, decimal_places=2):
        if value is None:
            return 0.00
        try:
            decimal_value = Decimal(str(value))
            quantizer = Decimal('0.' + '0' * (decimal_places - 1) + '1')
            rounded = decimal_value.quantize(quantizer, rounding=ROUND_HALF_UP)
            return rounded
        except:
            return 0.00