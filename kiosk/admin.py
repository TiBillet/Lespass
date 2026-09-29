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
from unfold.admin import StackedInline
# ModelAdmin vient de Administration/admin/base.py : c'est le ModelAdmin
# d'Unfold plus le placeholder de recherche tire de search_fields.
# / Project ModelAdmin: Unfold's, plus the search placeholder.
from Administration.admin.base import ModelAdmin

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from Administration.admin.laboutik import TerminalAdmin, TerminalForm
from kiosk.models import Borne, PaymentsIntent, ReglagesBorne


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


@admin.register(ReglagesBorne, site=staff_admin_site)
class ReglagesBorneAdmin(ModelAdmin):
    """Services proposes par chaque borne. Normalement changes depuis la borne
    elle-meme (carte primaire -> configuration), mais corrigeables ici.
    / Services offered by each kiosk. Normally changed on the kiosk itself
    (primary card -> configuration), but editable here."""

    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("terminal", "recharge_active")
    list_select_related = ("terminal",)
    readonly_fields = ("terminal",)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    # Les reglages naissent a la premiere ouverture de la borne (get_or_create).
    # / Settings are created on the kiosk's first opening.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


# --- Bornes : la liste du module Kiosk ---
# / Kiosks: the Kiosk module's list


class BorneForm(TerminalForm):
    """
    Formulaire d'une borne. C'est celui d'un terminal, sans le choix du role.
    / Kiosk form: the terminal form, without the role choice.

    LOCALISATION : kiosk/admin.py

    Le role est toujours « Kiosk » : BorneAdmin.save_model() le pose.
    On ne le montre donc pas.
    / The role is always "Kiosk", set by BorneAdmin.save_model().
    """

    class Meta(TerminalForm.Meta):
        model = Borne
        fields = ["name", "printer", "archived"]

    def __init__(self, *args, **kwargs):
        # On saute TerminalForm.__init__ : il regle le champ terminal_role,
        # qui n'est pas dans ce formulaire.
        # / Skip TerminalForm.__init__: it tunes terminal_role, absent here.
        super(TerminalForm, self).__init__(*args, **kwargs)


class ReglagesBorneInline(StackedInline):
    """
    Les services de la borne, affiches dans la fiche de la borne.
    / The kiosk's services, shown inside the kiosk's page.

    LOCALISATION : kiosk/admin.py

    Un seul bloc par borne (OneToOne). Il remplace l'ancienne page
    « Réglages des bornes » de la sidebar.
    / One block per kiosk. Replaces the former "Kiosk settings" sidebar page.
    """

    model = ReglagesBorne
    fk_name = "terminal"
    extra = 1
    max_num = 1
    can_delete = False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Borne, site=staff_admin_site)
class BorneAdmin(TerminalAdmin):
    """
    Les bornes libre-service du lieu : creation, appairage, reglages.
    / The venue's self-service kiosks: creation, pairing, settings.

    LOCALISATION : kiosk/admin.py

    Herite de TerminalAdmin : meme colonne « Etat » (code PIN), memes actions
    (revoquer, nouveau code PIN), meme fabrication du code a la creation.

    Differences :
    - la liste ne montre que les terminaux de role « Kiosk » (BorneManager) ;
    - le role n'est pas demande : il est pose a « Kiosk » a l'enregistrement ;
    - les reglages de la borne sont un bloc de la fiche (ReglagesBorneInline).
    / Inherits TerminalAdmin. Kiosk-role only, role forced, settings inline.
    """

    form = BorneForm
    inlines = [ReglagesBorneInline]

    list_display = (
        "name", "etat_de_l_appairage", "printer", "lecteur_de_carte", "archived",
    )
    list_filter = ["archived"]

    def save_model(self, request, obj, form, change):
        """
        Pose le role « Kiosk » avant l'enregistrement, puis laisse TerminalAdmin
        fabriquer le code PIN.
        / Sets the "Kiosk" role, then lets TerminalAdmin issue the PIN.
        """
        from AuthBillet.models import TibilletUser

        borne_vient_d_etre_creee = not change
        if borne_vient_d_etre_creee:
            obj.terminal_role = TibilletUser.ROLE_KIOSQUE
        super().save_model(request, obj, form, change)
