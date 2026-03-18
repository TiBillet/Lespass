import logging

from django.contrib import admin, messages
from django.http import HttpRequest
from django.shortcuts import redirect, get_object_or_404
from django.utils.translation import gettext_lazy as _
from import_export.admin import ExportActionModelAdmin
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RangeDateTimeFilter
from unfold.contrib.import_export.forms import ExportForm
from unfold.decorators import display, action

from Administration.admin.site import staff_admin_site
from Administration.importers.lignearticle_exporter import LigneArticleExportResource
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from BaseBillet.models import (
    Paiement_stripe, LigneArticle, PostalAddress, SaleOrigin
)
from fedow_connect.utils import dround

logger = logging.getLogger(__name__)


@admin.register(Paiement_stripe, site=staff_admin_site)
class PaiementStripeAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_display = (
        'user',
        'order_date',
        'status',
        # 'traitement_en_cours',
        'source_traitement',
        'source',
        'articles',
        'total',
        'uuid_8',
    )
    readonly_fields = list_display
    ordering = ('-order_date',)
    search_fields = ('user__email', 'order_date')
    list_filter = ('status', 'order_date',)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True


@admin.register(LigneArticle, site=staff_admin_site)
class LigneArticleAdmin(ModelAdmin, ExportActionModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_filter = ('status',
                   'pricesold__productsold',
                   ('datetime', RangeDateTimeFilter),
                   )

    list_display = [
        'productsold',
        'user_email',
        'datetime',
        'amount_decimal',
        '_qty',
        'vat',
        'total_decimal',
        'display_status',
        'payment_method',
        'sale_origin',
    ]
    search_fields = ('datetime', 'pricesold__productsold__product__name', 'pricesold__price__name',
                     'paiement_stripe__user__email', 'membership__user__email')
    ordering = ('-datetime',)

    resource_classes = [LigneArticleExportResource]
    export_form_class = ExportForm

    def get_queryset(self, request):
        # Utiliser select_related pour précharger pricesold et productsold
        queryset = super().get_queryset(request)
        return queryset.select_related('pricesold__productsold',
                                       'pricesold__price',
                                       'paiement_stripe',
                                       'paiement_stripe__user',
                                       'membership',
                                       'membership__user',
                                       )

    @display(description=_("Value"))
    def amount_decimal(self, obj):
        return dround(obj.amount)

    @display(description=_("Quantité"))
    def _qty(self, obj):
        return dround(obj.qty)

    @display(description=_("Total"))
    def total_decimal(self, obj: LigneArticle):
        return dround(obj.total())

    @display(description=_("Product"))
    def productsold(self, obj):
        return f"{obj.pricesold.productsold} - {obj.pricesold}"

    # noinspection PyTypeChecker
    @display(description=_("Status"), label={None: "danger", True: "success", "warning": "warning"})
    def display_status(self, instance: LigneArticle):
        status = instance.status
        if status in [LigneArticle.VALID, LigneArticle.FREERES]:
            return True, f"{instance.get_status_display()}"
        if status == LigneArticle.CREDIT_NOTE:
            return "warning", f"{instance.get_status_display()}"
        if instance.credit_notes.exists():
            return "warning", f"{instance.get_status_display()} ⚠"
        return None, f"{instance.get_status_display()}"

    actions_row = ["emettre_avoir"]

    @action(
        description=_("Credit note"),  # Avoir
        url_path="emettre_avoir",
        permissions=["custom_actions_row"],
    )
    def emettre_avoir(self, request, object_id):
        """
        Cree un avoir (ligne negative) pour annuler comptablement cette vente.
        / Creates a credit note (negative line) to cancel this sale.
        """
        ligne_originale = get_object_or_404(
            LigneArticle.objects.select_related('pricesold', 'pricesold__productsold'),
            pk=object_id,
        )

        redirect_url = request.META.get("HTTP_REFERER", "/admin/")

        # Garde : uniquement sur les lignes VALID ou PAID
        if ligne_originale.status not in [LigneArticle.VALID, LigneArticle.PAID]:
            messages.error(request, _("A credit note can only be issued for a confirmed or paid entry."))
            return redirect(redirect_url)

        # Garde : pas d'avoir si un avoir existe deja
        if ligne_originale.credit_notes.exists():
            messages.error(request, _("A credit note already exists for this entry."))
            return redirect(redirect_url)

        # Creer la ligne avoir / Create the credit note line
        avoir = LigneArticle.objects.create(
            pricesold=ligne_originale.pricesold,
            qty=-ligne_originale.qty,
            amount=ligne_originale.amount,
            vat=ligne_originale.vat,
            paiement_stripe=ligne_originale.paiement_stripe,
            membership=ligne_originale.membership,
            payment_method=ligne_originale.payment_method,
            asset=ligne_originale.asset,
            wallet=ligne_originale.wallet,
            sale_origin=SaleOrigin.ADMIN,
            credit_note_for=ligne_originale,
            status=LigneArticle.CREATED,
        )
        # Declenche la machine a etat / Trigger state machine
        avoir.status = LigneArticle.CREDIT_NOTE
        avoir.save()

        messages.success(request, _("Credit note created."))
        return redirect(redirect_url)

    def has_custom_actions_row_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PostalAddress, site=staff_admin_site)
class PostalAddressAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_display = [
        "name",
        "street_address",
        "address_locality",
        "address_region",
        "postal_code",
        "address_country",
        "latitude",
        "longitude",
        "comment",
        "is_main",
    ]

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
