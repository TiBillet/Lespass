import logging

from django import forms
from django.contrib import admin, messages
from django.db import connection
from django.forms import ModelForm, HiddenInput
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from BaseBillet.models import Product, Price, PromotionalCode
from Customers.models import Client
from fedow_public.models import AssetFedowPublic as Asset, AssetFedowPublic

logger = logging.getLogger(__name__)


@admin.register(PromotionalCode, site=staff_admin_site)
class PromotionalCodeAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = (
        "name",
        "product",
        "discount_rate",
        "is_active",
        "usage_count",
        "usage_limit",
        "remaining_uses",
        "date_created",
    )

    fields = (
        "name",
        "product",
        "discount_rate",
        "is_active",
        "usage_limit",
        "usage_count",
    )

    readonly_fields = ("usage_count",)

    list_filter = ["is_active", "product"]
    search_fields = ["name", "product__name"]
    ordering = ("-date_created",)

    # pas d'auto complete sinon le formfield_for_foreignkey ne fonctionne pas, il faudra passer par le get_search_results coté ProductAdmin
    # autocomplete_fields = ['product']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if (
            db_field.name == "product"
        ):  # Replace 'user_field' with your actual field name
            kwargs["queryset"] = Product.objects.filter(
                archive=False, categorie_article=Product.BILLET
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @display(description=_("Remaining uses"))
    def remaining_uses(self, obj):
        remaining = obj.remaining_uses()
        if remaining is None:
            return _("Unlimited")
        return remaining

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class PriceChangeForm(ModelForm):
    # Le formulaire pour changer un prix lorsque l'on clic sur modification
    class Meta:
        model = Price
        fields = (
            "name",
            "product",
            "prix",
            "free_price",
            "contenance",
            "subscription_type",
            "recurring_payment",
            "iteration",
            "order",
            "publish",
            "max_per_user",
            "stock",
            "adhesions_obligatoires",
            # topup when paid :
            "fedow_reward_enabled",
            "fedow_reward_asset",
            "fedow_reward_amount",
        )

    def clean_recurring_payment(self):
        cleaned_data = self.cleaned_data  # récupère les donnée au fur et a mesure des validation, attention a l'ordre des fields
        recurring_payment = cleaned_data.get("recurring_payment")
        if recurring_payment:
            data = self.data  # récupère les data sans les avoir validé

            if hasattr(self.instance, "product"):
                categorie_product = self.instance.product.categorie_article
            elif self.cleaned_data.get("product"):
                categorie_product = self.cleaned_data["product"].categorie_article
            else:
                raise forms.ValidationError(_("No product ?"), code="invalid")

            if categorie_product:
                if categorie_product != Product.ADHESION:
                    raise forms.ValidationError(
                        _(
                            "A recurring payment plan must have a membership-type product."
                        ),
                        code="invalid",
                    )

            if data.get("subscription_type") not in [
                Price.DAY,
                Price.WEEK,
                Price.MONTH,
                Price.CAL_MONTH,
                Price.YEAR,
            ]:
                raise forms.ValidationError(
                    _(
                        "A recurring payment must have a membership term. Re-enter the term just above."
                    ),
                    code="invalid",
                )

        return recurring_payment

    def clean_prix(self):
        cleaned_data = self.cleaned_data
        prix = cleaned_data.get("prix")
        if 0 < prix < 1:
            raise forms.ValidationError(
                _("A rate cannot be between 0€ and 1€"), code="invalid"
            )

        return prix

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On cache les options réservés aux adhésions
        try:
            instance: Price = kwargs.get("instance")
            if instance.product.categorie_article != Product.ADHESION:
                self.fields["subscription_type"].widget = HiddenInput()
                self.fields["recurring_payment"].widget = HiddenInput()
                self.fields["iteration"].widget = HiddenInput()
                self.fields["manual_validation"].widget = HiddenInput()
                self.fields[
                    "product"
                ].widget = HiddenInput()  # caché sauf si bouton + en haut a droite
                # Filtrage des produits : uniquement des produits adhésions.
                # Possible facilement car Foreign Key (voir get_search_results dans ProductAdmin)
                self.fields["adhesions_obligatoires"].queryset = Product.objects.filter(
                    categorie_article=Product.ADHESION,
                    archive=False,
                )
                # Pas de bouton "+" pour creer un produit depuis ce champ
                # / No "add" button to create a product from this field
                self.fields["adhesions_obligatoires"].widget.can_add_related = False
            elif (
                instance.product.categorie_article == Product.ADHESION
            ):  # si c'est un produit qui n'est pas l'adhésion
                self.fields[
                    "product"
                ].widget = HiddenInput()  # caché sauf si bouton + en haut a droite
                self.fields[
                    "adhesions_obligatoires"
                ].widget = forms.MultipleHiddenInput()

        except AttributeError as e:
            # NoneType' object has no attribute 'product
            logger.info(f"Formulaire add : {e} ")
        except Exception as e:
            logger.error(f"Error in PriceChangeForm __init__ : {e}")
            raise e

        client: Client = connection.tenant
        # Limit the Asset choices to local tokens, time, and fidelity
        self.fields["fedow_reward_asset"].queryset = AssetFedowPublic.objects.filter(
            category__in=[
                Asset.TOKEN_LOCAL_FIAT,
                Asset.TOKEN_LOCAL_NOT_FIAT,
                Asset.TIME,
                Asset.FIDELITY,
            ],
            archive=False,
            origin=client,
        )

        # Improve display label: show name, currency and category
        def _label(obj):
            try:
                return (
                    f"{obj.name} ({obj.currency_code}) - {obj.get_category_display()}"
                )
            except Exception:
                return str(obj)

        self.fields["fedow_reward_asset"].label_from_instance = _label


@admin.register(Price, site=staff_admin_site)
class PriceAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    form = PriceChangeForm
    autocomplete_fields = ["adhesions_obligatoires"]

    conditional_fields = {
        "iteration": "recurring_payment == true",
        "commitment": "iteration > 0",
    }

    fieldsets = (
        (
            _("General"),
            {
                "fields": (
                    "name",
                    "product",
                    ("prix", "free_price"),
                    "subscription_type",
                    ("recurring_payment", "iteration", "commitment"),
                    "manual_validation",
                    "order",
                    "max_per_user",
                    "stock",
                    "adhesions_obligatoires",
                    "publish",
                ),
                "classes": ["tab"],
            },
        ),
        (
            _("Triggers"),
            {
                "fields": (
                    "fedow_reward_enabled",
                    "reward_on_ticket_scanned",
                    "fedow_reward_asset",
                    "fedow_reward_amount",
                ),
                "classes": ["tab"],
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        # Ajouter le champ contenance uniquement pour les tarifs
        # d'articles POS de type vente (methode_caisse=VT).
        # / Add contenance field only for POS sale product prices.
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj and obj.product and obj.product.methode_caisse == Product.VENTE:
            general_fields = list(fieldsets[0][1]["fields"])
            # Insérer contenance juste après le prix
            # / Insert contenance right after price
            prix_index = next(
                (
                    i
                    for i, f in enumerate(general_fields)
                    if f == ("prix", "free_price") or f == "prix"
                ),
                None,
            )
            if prix_index is not None and "contenance" not in general_fields:
                general_fields.insert(prix_index + 1, "contenance")
                fieldsets[0] = (
                    fieldsets[0][0],
                    {**fieldsets[0][1], "fields": tuple(general_fields)},
                )
        return fieldsets

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        # Breadcrumb : afficher "Produits > [nom du produit]" au lieu de "Tarifs > [nom du tarif]"
        extra_context = extra_context or {}
        if object_id:
            price = Price.objects.select_related("product").filter(pk=object_id).first()
            if price:
                extra_context["opts"] = Product._meta
                extra_context["original"] = price.product
        return super().changeform_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        # Après sauvegarde d'un tarif, rediriger vers la page du produit parent avec un message de succès
        # / After saving a price, redirect to the parent product page with a success message
        self.message_user(
            request,
            _('The price "%(name)s" was changed successfully.') % {"name": obj},
            messages.SUCCESS,
        )
        product_url = reverse(
            "staff_admin:BaseBillet_product_change", args=[obj.product.pk]
        )
        return redirect(product_url)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
