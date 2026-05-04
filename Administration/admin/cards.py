"""
Administration/admin/cards.py — Admin Unfold pour CarteCashless et Detail.
Administration/admin/cards.py — Unfold admin for CarteCashless and Detail.

Filtre par detail.origine == tenant courant pour les non-superusers.
Creation et suppression reservees aux superusers.
Refund : integre dans change_form_before_template (panel + modal HTMX).
"""
import uuid as uuid_module

from django import forms
from django.contrib import admin
from django.db import connection

from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminTextInputWidget, UnfoldAdminUUIDInputWidget

from Administration.admin.site import staff_admin_site
from Administration import views_cards
from ApiBillet.permissions import TenantAdminPermissionWithRequest

from QrcodeCashless.models import CarteCashless, Detail


# ---------------------------------------------------------------------------
# Helpers module-level (jamais dans une classe ModelAdmin Unfold !)
# Module-level helpers (NEVER inside a ModelAdmin class with Unfold!)
# Cf. tests/PIEGES.md "Ne JAMAIS definir de methodes helper dans un ModelAdmin Unfold"
# ---------------------------------------------------------------------------

def _user_link(carte: CarteCashless) -> str:
    if carte.user is None:
        return format_html('<span style="opacity:0.5">{}</span>', _("(anonyme)"))
    return format_html('{}', carte.user.email)


def _detail_origine(carte: CarteCashless) -> str:
    if carte.detail is None or carte.detail.origine is None:
        return "—"
    return carte.detail.origine.name


def _wallet_status(carte: CarteCashless) -> str:
    if carte.user is not None:
        return _("Identifiée")
    if carte.wallet_ephemere is not None:
        return _("Anonyme (éphémère)")
    return _("Vierge")


def _detail_nb_cartes(detail: Detail) -> int:
    return CarteCashless.objects.filter(detail=detail).count()


# ---------------------------------------------------------------------------
# Formulaire d'ajout CarteCashless (superuser only)
# CarteCashless add form (superuser only)
#
# tag_id, number et uuid sont editable=False sur le modele : par defaut
# l'admin Django les ignore. On les reinjecte dans un ModelForm dedie pour
# permettre leur saisie en mode ADD. En mode CHANGE, le form par defaut
# reprend le relais (via ModelAdmin.form vs add_form).
#
# tag_id, number and uuid are editable=False on the model: Django admin
# ignores them by default. We reinject them via a dedicated ModelForm
# to allow input in ADD mode only.
# ---------------------------------------------------------------------------

class CarteCashlessAddForm(forms.ModelForm):
    """
    Saisie manuelle du tag_id (obligatoire). Number et uuid optionnels :
    si vides, generes automatiquement.

    Manual input of tag_id (required). Number and uuid optional:
    if empty, auto-generated.

    Note : tag_id, number et uuid sont editable=False sur le modele, donc
    Django interdit de les inclure via Meta.fields. On les reinjecte dans
    __init__ et on override save() pour creer l'objet manuellement.

    Note: tag_id, number and uuid are editable=False on the model, so Django
    forbids including them via Meta.fields. We reinject them in __init__
    and override save() to create the object manually.
    """

    class Meta:
        model = CarteCashless
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tag_id"] = forms.CharField(
            max_length=8,
            required=True,
            label=_("Tag NFC"),
            widget=UnfoldAdminTextInputWidget(
                attrs={"placeholder": "ex : A49E8E2A"},
            ),
            help_text=_(
                "Identifiant NFC grave dans la carte (8 caracteres hex, majuscules)."
            ),
        )
        self.fields["number"] = forms.CharField(
            max_length=8,
            required=False,
            label=_("Numero imprime"),
            widget=UnfoldAdminTextInputWidget(
                attrs={"placeholder": _("Auto-genere si vide")},
            ),
            help_text=_(
                "Numero visible imprime sur la carte. Si vide : genere depuis "
                "les 8 premiers caracteres du QR code."
            ),
        )
        self.fields["uuid"] = forms.UUIDField(
            required=False,
            label=_("UUID (QR code)"),
            widget=UnfoldAdminUUIDInputWidget(
                attrs={"placeholder": _("Auto-genere si vide")},
            ),
            help_text=_(
                "UUID du QR code scannable. Si vide : genere automatiquement."
            ),
        )

    def clean_tag_id(self):
        tag_id = self.cleaned_data["tag_id"].upper()
        # Unicite : pas d'autre carte avec le meme tag_id.
        # Uniqueness: no other card has the same tag_id.
        if CarteCashless.objects.filter(tag_id=tag_id).exists():
            raise forms.ValidationError(
                _("Une carte avec ce Tag NFC existe deja.")
            )
        return tag_id

    def clean(self):
        cleaned_data = super().clean()

        # Generer l'UUID si absent.
        # Generate UUID if missing.
        if not cleaned_data.get("uuid"):
            cleaned_data["uuid"] = uuid_module.uuid4()

        # Generer le number depuis les 8 premiers chars hex de l'UUID si absent.
        # Generate number from first 8 hex chars of UUID if missing.
        if not cleaned_data.get("number"):
            uuid_hex = str(cleaned_data["uuid"]).replace("-", "")
            cleaned_data["number"] = uuid_hex[:8].upper()

        # Verifier l'unicite du number et de l'uuid (puisque Django ne le fait
        # pas automatiquement — les champs ne viennent pas du ModelForm).
        # Check uniqueness of number and uuid (Django does not do it
        # automatically — fields do not come from ModelForm).
        if CarteCashless.objects.filter(number=cleaned_data["number"]).exists():
            self.add_error("number", _("Ce numero imprime est deja utilise."))
        if CarteCashless.objects.filter(uuid=cleaned_data["uuid"]).exists():
            self.add_error("uuid", _("Cet UUID est deja utilise."))

        return cleaned_data

    def save(self, commit=True):
        # On passe par super().save(commit=False) pour beneficier de
        # l'attachement de save_m2m (Django admin l'appelle ensuite dans
        # save_related). On assigne les 3 champs sur l'instance cree vide
        # (Meta.fields = (), donc aucun champ n'est peuple automatiquement).
        # Use super().save(commit=False) to get save_m2m attached
        # (Django admin calls it afterwards in save_related). We assign the
        # 3 fields on the empty instance (Meta.fields = (), so nothing is
        # populated automatically).
        instance = super().save(commit=False)
        instance.tag_id = self.cleaned_data["tag_id"]
        instance.number = self.cleaned_data["number"]
        instance.uuid = self.cleaned_data["uuid"]
        if commit:
            instance.save()
            self.save_m2m()
        return instance


# ---------------------------------------------------------------------------
# CarteCashlessAdmin
# ---------------------------------------------------------------------------

@admin.register(CarteCashless, site=staff_admin_site)
class CarteCashlessAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = (
        "tag_id",
        "number",
        "user_link",
        "detail_origine",
        "wallet_status",
    )
    search_fields = ("tag_id", "number", "user__email")
    list_filter = ("detail__origine",)

    # Formulaire custom uniquement en mode ADD (tag_id + number + uuid saisissables).
    # En mode CHANGE, get_form() retombe sur le form par defaut.
    # Custom form only in ADD mode (tag_id + number + uuid editable).
    # In CHANGE mode, get_form() falls back to the default form.
    add_form = CarteCashlessAddForm

    def get_form(self, request, obj=None, **kwargs):
        # En mode ADD : on court-circuite le factory Django (modelform_factory
        # crasherait sur les champs editable=False) et on retourne directement
        # notre form custom.
        # In ADD mode: short-circuit Django's factory (modelform_factory would
        # crash on editable=False fields) and return our custom form directly.
        if obj is None:
            return self.add_form
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            # Mode ADD : 3 champs saisissables uniquement.
            # ADD mode: only 3 editable fields.
            return ((None, {"fields": ("tag_id", "number", "uuid")}),)
        return super().get_fieldsets(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            # Mode ADD : tout saisissable (geré par CarteCashlessAddForm).
            # ADD mode: all editable (handled by CarteCashlessAddForm).
            return ()
        # Mode CHANGE : tous les champs en lecture seule.
        # CHANGE mode: all fields read-only (form is purely informational).
        return [field.name for field in self.model._meta.fields]

    change_form_before_template = "admin/cards/refund_before.html"

    def user_link(self, obj):
        return _user_link(obj)
    user_link.short_description = _("Utilisateur·ice")

    def detail_origine(self, obj):
        return _detail_origine(obj)
    detail_origine.short_description = _("Lieu d'origine")

    def wallet_status(self, obj):
        return _wallet_status(obj)
    wallet_status.short_description = _("Statut")

    # --- Permissions : 4 methodes obligatoires ---
    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # --- Filtre tenant ---
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("user", "detail__origine")
        if request.user.is_superuser:
            return qs
        return qs.filter(detail__origine_id=connection.tenant.pk)

    # --- URLs custom : endpoints HTMX pour refund ---
    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:pk>/refund-panel/",
                self.admin_site.admin_view(
                    views_cards.CardRefundViewSet.as_view({"get": "panel"})
                ),
                name="QrcodeCashless_cartecashless_refund_panel",
            ),
            path(
                "<uuid:pk>/refund-modal/",
                self.admin_site.admin_view(
                    views_cards.CardRefundViewSet.as_view({"get": "modal"})
                ),
                name="QrcodeCashless_cartecashless_refund_modal",
            ),
            path(
                "<uuid:pk>/refund-confirm/",
                self.admin_site.admin_view(
                    views_cards.CardRefundViewSet.as_view({"post": "confirm"})
                ),
                name="QrcodeCashless_cartecashless_refund_confirm",
            ),
        ]
        return custom_urls + super().get_urls()


# ---------------------------------------------------------------------------
# DetailAdmin (inchange)
# ---------------------------------------------------------------------------

@admin.register(Detail, site=staff_admin_site)
class DetailAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("slug", "base_url", "origine", "generation", "nb_cartes")
    search_fields = ("slug", "base_url")
    list_filter = ("origine", "generation")
    readonly_fields = ("uuid",)

    def nb_cartes(self, obj):
        return _detail_nb_cartes(obj)
    nb_cartes.short_description = _("Nombre de cartes")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("origine")
        if request.user.is_superuser:
            return qs
        return qs.filter(origine_id=connection.tenant.pk)
