"""
kiosk/admin.py — Enregistrement des modeles kiosk dans Unfold.
kiosk/admin.py — Registration of kiosk models in Unfold admin.

Les modeles sont enregistres sur staff_admin_site (le site admin Unfold du projet).
Terminal est editable par l'admin. PaymentsIntent est en lecture seule : ce sont
des traces d'evenements Stripe, jamais modifiees a la main. StripeLocation n'est
PAS dans l'admin : elle est creee automatiquement par get_primary_location() lors
du premier appairage d'un TPE (meme comportement que LaBoutik).

Models are registered on staff_admin_site (the project's Unfold admin site).
Terminal is editable by admin. PaymentsIntent is read-only: these are traces of
Stripe events, never edited manually. StripeLocation is NOT in the admin: it is
created automatically by get_primary_location() on the first terminal pairing.
"""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminSelectWidget

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from kiosk.models import Terminal, PaymentsIntent


class TermUserChoiceField(forms.ModelChoiceField):
    """Affiche le nom de la borne plutot que son email synthetique.
    / Shows the kiosk device name instead of its synthetic email."""

    def label_from_instance(self, term_user):
        # first_name porte le nom saisi a l'appairage (PairingDevice.name).
        # Les bornes appairees avant cette version n'en ont pas : on retombe
        # sur l'email synthetique pour rester identifiable.
        # / first_name holds the name entered at pairing time. Devices paired
        # before this version have none: fall back to the synthetic email.
        if term_user.first_name:
            return term_user.first_name
        return term_user.email


class TerminalForm(forms.ModelForm):
    class Meta:
        model = Terminal
        fields = ["name", "type", "registration_code", "term_user", "archived"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le FK cible TibilletUser : on restreint le choix aux bornes appairees
        # avec le role Kiosk (KI). Les caisses LaBoutik (LB) et les tireuses (TI)
        # ne pilotent pas de TPE Stripe et n'ont rien a faire dans cette liste.
        # / FK targets TibilletUser: restrict choices to devices paired with the
        # Kiosk role (KI). LaBoutik POS (LB) and taps (TI) drive no Stripe reader.
        from AuthBillet.models import TermUser, TibilletUser
        bornes_kiosk = TermUser.objects.filter(
            terminal_role=TibilletUser.ROLE_KIOSQUE,
        ).order_by("first_name", "email")

        # Si aucune borne n'est appairée en rôle Kiosque, le select serait vide sans
        # explication. On l'indique dans le help_text plutôt que de laisser l'admin
        # chercher pourquoi la liste ne contient rien.
        # / If no device is paired with the Kiosk role, the select would be silently
        # empty. Say so in the help_text instead of leaving the admin puzzled.
        aucune_borne_appairee = not bornes_kiosk.exists()
        if aucune_borne_appairee:
            aide = _(
                "Aucune borne appairée en rôle Kiosque. "
                "Créez d'abord un code PIN d'appairage (rôle « Kiosque ») dans « Appairage de terminal », "
                "puis appairez la borne."
            )
        else:
            aide = _("La borne Android qui pilotera ce TPE. Une borne ne peut piloter qu'un seul TPE.")

        self.fields["term_user"] = TermUserChoiceField(
            queryset=bornes_kiosk,
            required=False,
            label=_("Borne (terminal appairé)"),
            help_text=aide,
            empty_label=_("— Aucune borne —"),
            widget=UnfoldAdminSelectWidget(),
        )

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

    def _post_clean(self):
        # L'appairage Stripe se fait ICI, pas dans save_model : un code d'enregistrement
        # refuse par Stripe doit invalider le formulaire (l'admin voit l'erreur sous le
        # champ et rien n'est enregistre), au lieu de creer un TPE orphelin sans stripe_id.
        # _post_clean est le moment ou Django a fini de reporter cleaned_data sur
        # self.instance : get_stripe_id() y lit un name et un registration_code a jour.
        # / Stripe pairing happens HERE, not in save_model: a registration code rejected by
        # Stripe must invalidate the form (error shown under the field, nothing saved),
        # instead of creating an orphan terminal with no stripe_id. _post_clean is when
        # Django has finished copying cleaned_data onto self.instance.
        super()._post_clean()

        deja_en_erreur = bool(self.errors)
        if deja_en_erreur:
            return

        # get_stripe_id() ne fait rien si le TPE est deja appaire (stripe_id rempli).
        # / get_stripe_id() is a no-op if the terminal is already paired.
        try:
            self.instance.get_stripe_id()
        except Exception as erreur_stripe:
            self.add_error("registration_code", _("Échec de l'appairage du TPE Stripe : %(err)s") % {
                "err": erreur_stripe,
            })


@admin.register(Terminal, site=staff_admin_site)
class TerminalAdmin(ModelAdmin):
    """Admin pour les terminaux Stripe (TPE physiques ou virtuels).
    Admin for Stripe terminals (physical or virtual card readers)."""

    compressed_fields = True
    warn_unsaved_form = True
    form = TerminalForm
    list_display = ("name", "type", "nom_de_la_borne", "archived")
    list_select_related = ("term_user",)
    list_filter = ("archived", "type")

    @admin.display(description=_("Borne (terminal appairé)"), ordering="term_user__first_name")
    def nom_de_la_borne(self, obj):
        """Nom de la borne appairee, ou rien si le TPE n'est lie a aucune borne.
        / Paired kiosk device name, or nothing if the terminal is unpaired."""
        if not obj.term_user:
            return "-"
        if obj.term_user.first_name:
            return obj.term_user.first_name
        return obj.term_user.email

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
