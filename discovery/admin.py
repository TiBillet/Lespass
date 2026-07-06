from django.contrib import admin
from django.db import connection
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from discovery.models import PairingDevice


@admin.register(PairingDevice, site=staff_admin_site)
class PairingDeviceAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        'name',
        'terminal_role',
        'pin_code_list_display',
        'is_claimed_display',
        'created_at',
    ]

    fields = [
        'name',
        'terminal_role',
        'pin_code_display',
    ]

    readonly_fields = [
        'pin_code_display',
    ]

    def get_readonly_fields(self, request, obj=None):
        # En édition, le rôle ne change plus : un PIN garde le rôle choisi
        # à sa création (le claim s'appuie dessus).
        # / On edit, the role is frozen: a PIN keeps the role chosen at
        # creation time (the claim relies on it).
        if obj is not None:
            return ['pin_code_display', 'terminal_role']
        return ['pin_code_display']

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        # TI (tireuse) exclu de la création manuelle : le PIN d'une tireuse
        # est auto-créé avec sa TireuseBec (admin controlvanne). Un PIN TI
        # sans TireuseBec liée ferait échouer le claim.
        # / TI (tap) excluded from manual creation: a tap PIN is auto-created
        # with its TireuseBec (controlvanne admin). A TI PIN without a linked
        # TireuseBec would make the claim fail.
        if db_field.name == 'terminal_role':
            kwargs['choices'] = [
                choice for choice in db_field.get_choices(include_blank=False)
                if choice[0] != 'TI'
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def pin_code_display(self, obj):
        """Affichage du PIN dans le formulaire de détail.
        PIN display in the detail form."""
        if obj.pk and obj.pin_code:
            if obj.is_claimed:
                return format_html('<span style="color: #999;">{}</span>', _("PIN already used"))
            # Afficher le PIN en gros, lisible, avec espacement
            # Display the PIN large, readable, with spacing
            pin_str = str(obj.pin_code)
            formatted_pin = f"{pin_str[:3]} {pin_str[3:]}"
            return format_html(
                '<span style="font-size: 2em; font-weight: bold; letter-spacing: 0.15em;">{}</span>',
                formatted_pin,
            )
        return _("Save to generate a PIN code. (Use 'Save and continue editing')")

    pin_code_display.short_description = _("PIN code")

    def pin_code_list_display(self, obj):
        """Affichage du PIN dans la liste : vidé si consommé.
        PIN display in list view: cleared if claimed."""
        if obj.pin_code:
            return obj.pin_code
        return "—"

    pin_code_list_display.short_description = _("PIN code")

    @display(boolean=True, description=_("Claimed"))
    def is_claimed_display(self, obj):
        return obj.is_claimed

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Filtrer par le tenant courant (schéma actif)
        # Filter by current tenant (active schema)
        return queryset.filter(tenant=connection.tenant)

    def save_model(self, request, obj, form, change):
        if not change:
            # Assigner le tenant courant et générer un PIN unique
            # Assign current tenant and generate a unique PIN
            obj.tenant = connection.tenant
            obj.pin_code = PairingDevice.generate_unique_pin()
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
