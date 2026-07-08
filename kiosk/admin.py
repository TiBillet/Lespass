"""
kiosk/admin.py — Enregistrement des modeles kiosk dans Unfold.
kiosk/admin.py — Registration of kiosk models in Unfold admin.

Les modeles sont enregistres sur staff_admin_site (le site admin Unfold du projet).
StripeLocation et Terminal sont editables par l'admin. PaymentsIntent est en
lecture seule : ce sont des traces d'evenements Stripe, jamais modifiees a la main.

Models are registered on staff_admin_site (the project's Unfold admin site).
StripeLocation and Terminal are editable by admin. PaymentsIntent is read-only:
these are traces of Stripe events, never edited manually.
"""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from kiosk.models import StripeLocation, Terminal, PaymentsIntent


@admin.register(StripeLocation, site=staff_admin_site)
class StripeLocationAdmin(ModelAdmin):
    """Admin pour les lieux (locations) Stripe Terminal.
    Admin for Stripe Terminal locations."""

    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("name", "stripe_id", "is_primary_location")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class TerminalForm(forms.ModelForm):
    class Meta:
        model = Terminal
        fields = ["name", "type", "registration_code", "term_user", "archived"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le FK cible TibilletUser : on restreint le choix aux TermUser (bornes).
        # / FK targets TibilletUser: restrict choices to TermUser (bornes).
        from AuthBillet.models import TermUser
        self.fields["term_user"].queryset = TermUser.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        terminal_type = cleaned_data.get("type")
        registration_code = cleaned_data.get("registration_code")
        stripe_id = self.instance.stripe_id if self.instance and self.instance.pk else None
        if terminal_type == Terminal.STRIPE_WISEPOS and not registration_code and not stripe_id:
            raise ValidationError({
                "registration_code": _(
                    "Le code d'enregistrement ne peut pas être vide pour un terminal STRIPE_WISEPOS non appairé.")
            })
        return cleaned_data


@admin.register(Terminal, site=staff_admin_site)
class TerminalAdmin(ModelAdmin):
    """Admin pour les terminaux Stripe (TPE physiques ou virtuels).
    Admin for Stripe terminals (physical or virtual card readers)."""

    compressed_fields = True
    warn_unsaved_form = True
    form = TerminalForm
    list_display = ("name", "type", "term_user", "archived")
    list_select_related = ("term_user",)
    list_filter = ("archived", "type")

    def save_model(self, request, obj, form, change):
        # Appairage : crée le reader Stripe si besoin. En DEMO on saute l'appel réseau ;
        # sinon on capture l'échec en message admin plutôt qu'un 500.
        # / Pairing: create the Stripe reader if needed. Skip network in DEMO;
        # otherwise surface failures as an admin message instead of a 500.
        from django.conf import settings
        from django.contrib import messages
        if not settings.DEMO:
            try:
                obj.get_stripe_id()
            except Exception as e:
                messages.error(request, _("Échec de l'appairage du TPE Stripe : %(err)s") % {"err": e})
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


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
