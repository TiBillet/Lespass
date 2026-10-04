import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP

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
    # « Montant » garde son nom (les lieux lisent déjà ces fichiers) : c'est le net
    # vendu de la ligne (`total_ttc`). HT, TVA et numéro de vente le complètent.
    # / "Montant" keeps its name: the line's net sold. HT, VAT and sale number follow.
    total = Field(column_name=_("Montant"))
    total_ht = Field(column_name=_("Total HT"))
    total_tva = Field(column_name=_("Total TVA"))
    numero_de_vente = Field(column_name=_("N° de vente"))
    # Les moyens nets de la VENTE de la ligne (corrections comprises, sans l'offert),
    # et non le moyen de la ligne : la colonne porte un nom qui le dit.
    # / The net methods of the line's SALE, no longer the line's own method.
    payment_method = Field(column_name=_("Moyens de la vente"))
    status = Field(column_name=_("Product entry status"))
    user_email = Field(column_name=_("User Email"))
    paiement_stripe = Field(column_name=_("Stripe payment"))
    carte = Field(attribute='carte',column_name=_("Carte cashless"))
    wallet = Field(attribute='wallet',column_name=_("Wallet from"))
    credit_note_ref = Field(column_name=_("Credit note ref."))  # Ref. avoir

    def get_export_headers(self, selected_fields=None, *args, **kwargs):
        fields = selected_fields or self.get_export_fields(*args, **kwargs)
        return [f.column_name for f in fields]

    def before_export(self, queryset, *args, **kwargs):
        try:
            config = Configuration.get_solo()
            self._cached_timezone = config.get_tzinfo()
        except Exception as e:
            self._cached_timezone = datetime.timezone.utc
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
            'total_ht',
            'total_tva',
            'numero_de_vente',
            'payment_method',
            'status',
            'user_email',
            'paiement_stripe',
            'carte',
            'wallet',
            'credit_note_ref',
        )
        export_order = ('uuid', 'date','product','qty','amount','vat','total','total_ht','total_tva','numero_de_vente','payment_method','status','user_email','paiement_stripe','carte','wallet','credit_note_ref')

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
        # Le net vendu de la ligne, en euros (part offerte déduite).
        # / The line's net sold, in euros (offered part deducted).
        return line.total_ttc/100

    def dehydrate_total_ht(self, line):
        return line.total_ht/100

    def dehydrate_total_tva(self, line):
        return line.total_tva/100

    def dehydrate_numero_de_vente(self, line):
        # Le numéro de la vente de la ligne ; vide pour une ligne sans vente ou une
        # vente pas encore réglée.
        # / The line's sale number; empty without a sale or before settlement.
        if line.vente_id is None:
            return ""
        if line.vente.numero is None:
            return ""
        return line.vente.numero

    def dehydrate_status(self, line):
        return line.get_status_display()

    def dehydrate_payment_method(self, line):
        # Les moyens nets de la vente de la ligne, corrections comprises, sans l'offert
        # (cellule vide quand il n'y en a aucun).
        # / The net methods of the line's sale (empty cell when there is none).
        return ", ".join(line.moyens_de_paiement_de_sa_vente())

    def dehydrate_user_email(self, line):
        return line.user_email()

    def dehydrate_paiement_stripe(self, line):
        return line.paiement_stripe_uuid()

    def dehydrate_credit_note_ref(self, line):
        if line.credit_note_for_id:
            return str(line.credit_note_for.uuid).partition('-')[0]
        return ""

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