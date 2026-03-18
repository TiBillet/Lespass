import logging
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional, Dict
from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.db import connection
from django.forms import ModelForm
from django.http import HttpRequest
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.components import register_component, BaseComponent
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.decorators import display
from unfold.sections import TemplateSection
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
)

from Administration.admin.site import staff_admin_site
from Administration.importers.membership_importers import (
    MembershipExportResource,
    MembershipImportResource,
)
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from AuthBillet.models import HumanUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import (
    Configuration, Product, Price, Membership, LigneArticle, PaymentMethod
)
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.utils import dround

logger = logging.getLogger(__name__)


class MembershipAddForm(ModelForm):
    '''
    Formulaire d'ajout d'adhésion sur l'interface d'administration.
    '''

    # Un formulaire d'email qui va générer les action get_or_create_user
    email = forms.EmailField(
        required=True,
        widget=UnfoldAdminEmailInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label="Email",
    )

    # Uniquement les tarif Adhésion
    # / Only membership prices
    price = forms.ModelChoiceField(
        queryset=Price.objects.filter(
            product__categorie_article=Product.ADHESION, product__archive=False
        ).select_related('product', 'fedow_reward_asset'),
        # Remplis le champ select avec les objets Price
        # / Fills the select with Price objects
        empty_label=_("Select an subscription"),  # Texte affiché par défaut
        required=True,
        widget=UnfoldAdminSelectWidget(),
        label=_("Subscriptions"),
        help_text=_("Si un déclencheur de tokens est configuré sur le tarif, il sera activé à l'enregistrement du paiement. Une ligne comptable sera aussi créée dans les Ventes."),
    )

    # Fabrication au cas ou = 0
    contribution = forms.FloatField(
        required=False,
        widget=UnfoldAdminTextInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Contribution (€)"),
    )

    payment_method = forms.ChoiceField(
        required=False,
        choices=PaymentMethod.classic(),  # on retire les choix stripe
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Payment method"),
    )

    card_number = forms.CharField(
        required=False,
        min_length=8,
        max_length=8,
        label=_("Card number"),
        # validators=[validate_hex8],
        widget=UnfoldAdminTextInputWidget(),
    )

    class Meta:
        model = Membership
        fields = [
            'last_name',
            'first_name',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Affiche l'info du déclencheur tokens dans le label du select
        # / Shows token trigger info in the select label
        def _label_price_avec_declencheur(price_obj):
            label = str(price_obj)
            if price_obj.fedow_reward_enabled and price_obj.fedow_reward_asset and price_obj.fedow_reward_amount:
                label += f" ⚡ +{price_obj.fedow_reward_amount} {price_obj.fedow_reward_asset.name}"
            return label

        self.fields['price'].label_from_instance = _label_price_avec_declencheur

    def clean_email(self):
        cleaned_data = self.cleaned_data
        email = cleaned_data.get('email')
        user = get_or_create_user(email, send_mail=False)
        self.fedowAPI = FedowAPI()
        self.fedowAPI.wallet.get_or_create_wallet(user)
        self.user_wallet_serialized = self.fedowAPI.wallet.cached_retrieve_by_signature(user).validated_data
        return email

    def clean_card_number(self):
        cleaned_data = self.cleaned_data
        card_number = cleaned_data.get('card_number')
        if card_number:

            # Si clean_email a echoue, le wallet n'existe pas encore — on ne peut pas valider la carte
            # If clean_email failed, the wallet doesn't exist yet — we can't validate the card
            if not hasattr(self, 'user_wallet_serialized'):
                raise forms.ValidationError(_("Please provide a valid email address first."))

            if self.user_wallet_serialized.get('has_user_card'):
                raise forms.ValidationError(_("A card is already linked to this email address."))

            if not re.match(r'^[0-9A-Fa-f]{8}$', card_number):
                raise forms.ValidationError(_("Card number must be exactly 8 hexadecimal characters."))

            fedowApi = FedowAPI()
            card_serialized = fedowApi.NFCcard.card_number_retrieve(card_number)

            if not card_serialized:
                raise forms.ValidationError(_("Unknown card number"))
            if not card_serialized.get('is_wallet_ephemere'):
                raise forms.ValidationError(_("This card is already linked to a user."))

            self.card_serialized = card_serialized
        self.card_number = card_number
        return card_number

    def clean(self):
        # On vérifie que le moyen de paiement est bien entré si > 0
        cleaned_data = self.cleaned_data
        if cleaned_data.get("contribution"):
            if cleaned_data.get("contribution") > 0 and cleaned_data.get("payment_method") == PaymentMethod.FREE:
                raise forms.ValidationError(_("Please add a payment method for the contribution."),
                                            code="invalid")

        if cleaned_data.get("payment_method") != PaymentMethod.FREE:
            if not cleaned_data.get("contribution"):
                raise forms.ValidationError(_("Please fill in the value of the contribution."), code="invalid")
            if not cleaned_data.get("contribution") > 0:
                raise forms.ValidationError(_("Please fill in a positive value of the contribution."), code="invalid")

        return super().clean()

    def save(self, commit=True):
        self.instance: Membership
        # On indique que l'adhésion a été créé sur l'admin
        self.instance.status = Membership.ADMIN

        # Associez l'utilisateur au champ 'user' du formulaire
        email = self.cleaned_data.pop('email')
        user = get_or_create_user(email)

        self.instance.user = user

        # Flotant (FALC) vers Decimal
        contribution = self.cleaned_data.pop('contribution')
        self.instance.contribution_value = dround(Decimal(contribution)) if contribution else 0

        # Mise à jour des dates de contribution :
        self.instance.first_contribution = timezone.localtime()
        self.instance.last_contribution = timezone.localtime()
        # self.instance.set_deadline()

        if self.card_number:
            linked_serialized_card = self.fedowAPI.NFCcard.linkwallet_card_number(user=user,
                                                                                  card_number=self.card_number)

        # Le post save BaseBillet.signals.create_lignearticle_if_membership_created_on_admin s'executera
        # # Création de la ligne Article vendu qui envera à la caisse si besoin
        return super().save(commit=commit)


class MembershipChangeForm(ModelForm):
    # Le formulaire pour changer une adhésion
    class Meta:
        model = Membership
        fields = (
            'last_name',
            'first_name',
            'deadline',
            'commentaire',
        )


class MembershipStatusFilter(admin.SimpleListFilter):
    title = _("Statut d'adhésion (par défaut filtré)")
    parameter_name = "membership_status"

    def lookups(self, request, model_admin):
        return [
            ("valid", _("Valids")),
            ("wa", _("Attente de validation")),
            ("wp", _("Attente de paiement")),
            ("canceled", _("Canceled")),
            ("all", _("Sans distinction")),
        ]

    def queryset(self, request, queryset):
        from django.db.models import Q
        value = self.value()

        # Filtrage par défaut
        if value is None:
            return queryset.exclude(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED])

        if value == "valid":
            # On masque les annulées
            return queryset.exclude(
                Q(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED]) |
                Q(deadline__lt=timezone.localtime()))

        if value == "wa":
            return queryset.filter(status=Membership.ADMIN_WAITING)

        if value == "wp":
            return queryset.filter(status__in=[Membership.WAITING_PAYMENT, Membership.ADMIN_VALID])

        if value == "canceled":
            return queryset.filter(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED])

        if value == "all":
            return queryset
        return queryset


@register_component
class MembershipComponent(BaseComponent):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Les adhésions en cours :
        active_count = Membership.objects.filter(deadline__gte=timezone.localtime()).exclude(
            status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED]).count()
        # Les user qui n'ont pas d'adhésion en cours :
        inactive_count = HumanUser.objects.exclude(
            memberships__deadline__gte=timezone.localtime(),
            memberships__status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED],
        ).distinct().count()

        pending_count = Membership.objects.filter(status=Membership.ADMIN_WAITING).count()

        context["children"] = render_to_string(
            "admin/membership/membership_component.html",
            {
                "type": kwargs.get('type'),
                "active": active_count,
                "inactive": inactive_count,
                "pending": pending_count,
            },
        )
        return context


class MembershipCustomFormSection(TemplateSection):
    template_name = "admin/membership/custom_form_section.html"
    verbose_name = _("Custom form answers")


class LigneArticleInline(TabularInline):
    model = LigneArticle
    fk_name = "membership"
    extra = 0
    show_change_link = True
    can_delete = False
    verbose_name = _("Ventes / Ligne comptables")
    verbose_name_plural = _("Ventes / Ligne comptables")

    fields = (
        "datetime",
        "amount_decimal",
        "qty_decimal",
        "vat",
        "total_decimal",
        "display_status",
        "payment_method",
        "sale_origin",
    )
    readonly_fields = fields

    @display(description=_("Value"))
    def amount_decimal(self, obj):
        return obj.amount_decimal()

    @display(description=_("Quantité"))
    def qty_decimal(self, obj):
        return dround(obj.qty)

    @display(description=_("TVA"))
    def vat(self, obj):
        return obj.vat

    @display(description=_("Total"))
    def total_decimal(self, obj):
        return obj.total_decimal()

    @display(description=_("Statut"), label={None: "danger", True: "success"})
    def display_status(self, instance: LigneArticle):
        return instance.get_status_display()

    def has_view_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Membership, site=staff_admin_site)
class MembershipAdmin(ModelAdmin, ImportExportModelAdmin):
    inlines = [LigneArticleInline]
    # Expandable section to display custom form answers in changelist
    list_sections = [MembershipCustomFormSection]
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    # Ajoute un bloc personnalisé après le formulaire dans la vue change
    change_form_after_template = "admin/membership/custom_form.html"

    resource_classes = [MembershipExportResource, MembershipImportResource]
    export_form_class = ExportForm
    import_form_class = ImportForm

    list_before_template = "admin/membership/membership_list_before.html"  # appelle le MembershipComponent plus haut pour le contexte

    # Formulaire de modification
    form = MembershipChangeForm
    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = MembershipAddForm

    list_display = (
        'email',
        'date_added',
        'first_name',
        'last_name',
        'price',
        'contribution_value',
        # 'options',
        'display_last_contribution',
        'display_deadline',
        'display_is_valid',
        'status',
        'recurrence',
    )

    ordering = ('-date_added',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'card_number', 'last_contribution',
                     'custom_form')
    list_filter = [MembershipStatusFilter, 'price__product', 'last_contribution', 'deadline', ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return (
            qs.select_related('user', 'price', 'price__product')
            .prefetch_related('price__product__form_fields')
        )

    @display(description=_("User"))
    def user_email_link(self, obj):
        if obj.user:
            url = reverse("staff_admin:AuthBillet_humanuser_change", args=[obj.user.pk])
            return format_html(
                '<a href="{}" class="font-medium text-primary-600 underline decoration-primary-500 decoration-2 underline-offset-4 hover:text-primary-800 dark:text-primary-500 dark:decoration-primary-600 dark:hover:text-primary-400">{}</a>',
                url,
                obj.user.email
            )
        return "-"

    @display(description=_("Produit / Tarif"))
    def price_product_display(self, obj: Membership):
        return f"{obj.price.product.name} / {obj.price.name}"

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj:  # On est en train de modifier
            return list(readonly_fields) + ['user_email_link', 'price_product_display']
        return readonly_fields

    ### FORMULAIRES

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_changeform_initial_data(self, request):
        """Prefill the add form with values provided in the query string.

        Supports simple fields and ManyToMany 'option_generale' via repeated
        query params (e.g. ?option_generale=1&option_generale=2).
        """
        initial = super().get_changeform_initial_data(request)
        params = request.GET

        # Simple scalar params that map to form fields
        for key in [
            'email',
            'price',
            'contribution',
            'payment_method',
            'first_name',
            'last_name',
        ]:
            value = params.get(key)
            if value not in [None, ""]:
                initial[key] = value

        return initial

    # Panneau d'actions HTMX affiché AVANT le formulaire dans la vue change
    # / HTMX action panel displayed BEFORE the form in the change view
    change_form_before_template = "admin/membership/actions_panel.html"

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, bool]] = None):
        extra_context = extra_context or {}
        extra_context["show_validation_buttons"] = False

        if object_id:
            try:
                membership = Membership.objects.select_related('user', 'price', 'price__product').get(pk=object_id)
                extra_context['membership'] = membership
                if membership.status == Membership.ADMIN_WAITING:
                    extra_context["show_validation_buttons"] = True

                # URL de renouvellement avec les données pré-remplies
                # / Renewal URL with pre-filled data
                opts = self.model._meta
                url_formulaire_ajout = reverse(f"{self.admin_site.name}:{opts.app_label}_{opts.model_name}_add")
                params_renouvellement = {}
                if getattr(membership, 'user', None) and getattr(membership.user, 'email', None):
                    params_renouvellement['email'] = membership.user.email
                if membership.price_id:
                    params_renouvellement['price'] = membership.price_id
                if membership.contribution_value is not None:
                    params_renouvellement['contribution'] = str(membership.contribution_value)
                if membership.payment_method:
                    params_renouvellement['payment_method'] = membership.payment_method
                if membership.first_name:
                    params_renouvellement['first_name'] = membership.first_name
                if membership.last_name:
                    params_renouvellement['last_name'] = membership.last_name
                extra_context['renouveller_url'] = f"{url_formulaire_ajout}?{urlencode(params_renouvellement, doseq=True)}"

                # Lien de paiement copiable pour les adhésions validées manuellement (état AV)
                # Même URL que celle envoyée par email — la vue gère l'idempotence (pas de double paiement)
                # / Copyable payment link for manually validated memberships (state AV)
                # Same URL as sent by email — the view handles idempotency (no double payment)
                if membership.status in [Membership.ADMIN_VALID, Membership.ADMIN_WAITING]:
                    try:
                        domaine_tenant = connection.tenant.get_primary_domain().domain
                        extra_context['lien_paiement'] = f"https://{domaine_tenant}/memberships/{membership.uuid}/get_checkout_for_membership"
                    except Exception:
                        pass

                # Statuts qui permettent l'ajout d'un paiement hors-ligne (pour conditionnel template)
                # / Statuses that allow offline payment (for template conditional)
                extra_context['statuts_attente_paiement'] = [
                    Membership.WAITING_PAYMENT,
                    Membership.ADMIN_WAITING,
                    Membership.ADMIN_VALID,
                ]

            except Membership.DoesNotExist:
                extra_context["show_validation_buttons"] = False

        return super().changeform_view(request, object_id, form_url, extra_context)

    @display(description=_("Payment"), ordering="last_contribution")
    def display_last_contribution(self, instance: Membership):
        if instance.last_contribution:
            return instance.last_contribution.strftime("%d/%m/%Y")
        return "-"

    @display(description=_("End"), ordering="deadline")
    def display_deadline(self, instance: Membership):
        if instance.deadline:
            return instance.deadline.strftime("%d/%m/%Y")
        return "-"

    @display(description=_("Valid"), boolean=True)
    def display_is_valid(self, instance: Membership):
        return instance.is_valid()

    @display(description=_("Recurence"), ordering="current_iteration")
    def recurrence(self, instance: Membership):
        if instance.max_iteration and instance.current_iteration:
            return f"{instance.current_iteration}/{instance.max_iteration}"
        elif instance.current_iteration:
            return f"{instance.current_iteration}"
        elif instance.stripe_id_subscription:
            return "∞"
        return ""

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False
