"""
kiosk/admin.py — Enregistrement des modeles kiosk dans Unfold.
kiosk/admin.py — Registration of kiosk models in Unfold admin.

PaymentsIntent est en lecture seule : ce sont des traces d'evenements Stripe, jamais
modifiees a la main.

Le TPE lui-meme n'est PAS ici : il est porte par laboutik.Terminal, et son admin est
dans Administration/admin/laboutik.py. Un lecteur de carte bancaire n'est pas reserve
aux bornes libre-service — une caisse LaBoutik peut en avoir un.

PaymentsIntent is read-only: traces of Stripe events, never edited by hand.
The card reader itself lives on laboutik.Terminal (admin in Administration/admin/laboutik.py):
a card reader is not kiosk-only, a LaBoutik cash register may have one too.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from kiosk.models import PaymentsIntent


@admin.register(PaymentsIntent, site=staff_admin_site)
class PaymentsIntentAdmin(ModelAdmin):
    """Admin en lecture seule pour les intentions de paiement Stripe.
    Read-only admin for Stripe payment intents."""

    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("datetime", "amount", "terminal", "card", "status")
    list_select_related = ("terminal", "card")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
