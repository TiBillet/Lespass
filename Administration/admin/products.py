import json
import logging
import re

from django import forms
from django.contrib import admin, messages
from django.db import models, IntegrityError
from django.forms import ModelForm
from django.http import HttpRequest
from django.shortcuts import redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.components import register_component, BaseComponent
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.decorators import action
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from Administration.admin.site import staff_admin_site, sanitize_textfields
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from BaseBillet.models import (
    Configuration, Product, TicketProduct, MembershipProduct, POSProduct,
    CategorieProduct, Price, FormbricksForms, ProductFormField, Tva,
    PromotionalCode
)

logger = logging.getLogger(__name__)


class PriceInlineChangeForm(ModelForm):
    # Le formulaire pour changer une adhésion
    class Meta:
        model = Price
        fields = (
            'name',
            'product',
            'prix',
            'free_price',
            'subscription_type',
            'publish',
        )

    def clean_prix(self):
        cleaned_data = self.cleaned_data
        prix = cleaned_data.get('prix')
        if 0 < prix < 1:
            raise forms.ValidationError(_("A rate cannot be between 0€ and 1€"), code="invalid")
        return prix

    def clean_subscription_type(self):
        cleaned_data = self.cleaned_data
        product: Product = cleaned_data.get('product')
        subscription_type = cleaned_data.get('subscription_type')
        if product.categorie_article == Product.ADHESION:
            if subscription_type == Price.NA:
                raise forms.ValidationError(_("A subscription must have a duration"), code="invalid")
        return subscription_type


class PriceInline(TabularInline):
    model = Price
    fk_name = 'product'
    form = PriceInlineChangeForm
    # hide_title = True
    # collapsible = True # usefull for StackedInline

    # ordering_field = "weight"
    # max_num = 1
    extra = 0
    show_change_link = True

    # tab = True # don't set to false : comment or the tab title will be visible

    # Surcharger la méthode pour désactiver la suppression
    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class ProductFormFieldInlineForm(ModelForm):
    """
    Inline form that exposes a user-friendly CSV input for options on
    RADIO_SELECT and MULTI_SELECT field types, while storing a JSON list
    in the underlying `options` JSONField.
    """
    options_csv = forms.CharField(
        required=False,
        label=_("Choices"),
        help_text=_(
            'For Single select (menu), Radio or Multiple select, enter choices separated by commas. Example: Rock, Electro, Jazz'),
        widget=UnfoldAdminTextInputWidget(attrs={"placeholder": "Rock, Electro, Jazz"}),
    )

    class Meta:
        model = ProductFormField
        # Exclude the real `options` field from the rendered form; it will be
        # set from `options_csv` in `clean()`/`save()`.
        fields = ("label", "field_type", "required", "help_text", "order")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize CSV proxy from existing JSON list
        try:
            opts = self.instance.options if getattr(self, 'instance', None) else None
            if isinstance(opts, list) and all(isinstance(x, str) for x in opts):
                self.fields["options_csv"].initial = ", ".join(opts)
        except Exception:
            pass

    @staticmethod
    def _parse_csv_or_json(value: str):
        """Parse a CSV string or JSON array into a list of non-empty strings."""
        if value is None:
            return []
        s = str(value).strip()
        if not s:
            return []
        # If JSON-looking, try to parse first
        if s.startswith("[") or s.startswith("{"):
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    res = []
                    for v in data:
                        if v is None:
                            continue
                        sv = str(v).strip()
                        if sv:
                            # Collapse internal multiple spaces
                            sv = re.sub(r"\s+", " ", sv)
                            if sv not in res:
                                res.append(sv)
                    return res
            except Exception:
                # fall back to CSV parsing
                pass
        # CSV path
        parts = [re.sub(r"\s+", " ", p.strip()) for p in s.split(",")]
        res = []
        for p in parts:
            if p and p not in res:
                res.append(p)
        return res

    def clean(self):
        cleaned = super().clean()
        ftype = cleaned.get("field_type")
        csv_val = cleaned.get("options_csv")
        # Manage options list for Single select, Radio and Multi select
        if ftype in (
                ProductFormField.FieldType.SINGLE_SELECT,
                ProductFormField.FieldType.RADIO_SELECT,
                ProductFormField.FieldType.MULTI_SELECT,
        ):
            options_list = self._parse_csv_or_json(csv_val)
            cleaned["options"] = options_list if options_list else None
        else:
            # For non-choice types, clear options to avoid stale data
            cleaned["options"] = None
        return cleaned

    def save(self, commit=True):
        """Ensure the cleaned options are written to the instance even if the
        underlying model field `options` is not rendered in the form/inline.
        """
        instance = super().save(commit=False)
        # Use cleaned_data computed in clean()
        if "options" in self.cleaned_data:
            instance.options = self.cleaned_data.get("options")
        if commit:
            instance.save()
        return instance


class ProductFormFieldInline(TabularInline):
    """Sortable inline for dynamic membership form fields (ProductFormField)."""
    model = ProductFormField
    fk_name = 'product'
    extra = 0
    show_change_link = True

    # Unfold sortable inline settings
    ordering_field = "order"
    hide_ordering_field = True

    # Put inline in its own tab in the Product admin change view
    tab = True

    # Columns in the inline rows (Unfold supports list_display for inlines)
    list_display = ["label", "field_type", "required", "order"]

    # Use custom form with CSV proxy field
    form = ProductFormFieldInlineForm

    # Fields displayed in the inline form (key is auto-generated from label)
    fields = (
        "label",
        "field_type",
        "required",
        "options_csv",
        "help_text",
        "order",
    )

    # Keep JSON widget small for advanced/legacy editing
    formfield_overrides = {
        models.JSONField: {"widget": forms.Textarea(attrs={"rows": 3})}
    }

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class ProductAdminCustomForm(ModelForm):
    class Meta:
        model = Product
        fields = (
            'name',
            'categorie_article',
            'tva',
            'short_description',
            'long_description',
            'img',
            'poids',
            # "option_generale_radio",
            # "option_generale_checkbox",
            "validate_button_text",
            "legal_link",
            'publish',
            'archive',
        )
        help_texts = {
            'img': _('Product image is displayed at a 16/9 ratio.'),
        }

    categorie_article = forms.ChoiceField(
        required=False,
        choices=[
            (Product.NONE, _('Select a category')),
            (Product.BILLET, _('Ticket booking')),
            (Product.FREERES, _('Free booking')),
            (Product.ADHESION, _('Subscription or membership')),
        ],
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Product type"),
    )

    def clean_categorie_article(self):
        cleaned_data = self.cleaned_data
        categorie = cleaned_data.get('categorie_article')
        if categorie == Product.NONE:
            raise forms.ValidationError(_("Please add at least one category to this product."))

        # Vérification que la clé Stripe est opérationnelle :
        if categorie != Product.FREERES:
            config = Configuration.get_solo()
            if not config.stripe_payouts_enabled:
                raise forms.ValidationError(
                    _("Your Stripe account is not activated. To create paid items, please go to Settings/Stripe/Onboard."))
        return categorie

    def clean(self):
        # Vérification qu'il existe au moins un tarif si produit payant
        if self.data.get('categorie_article') not in [Product.FREERES, Product.BADGE]:
            try:
                # récupération du dictionnaire data pour vérifier qu'on a bien au moin un tarif dans le inline :
                if int(self.data.getlist('prices-TOTAL_FORMS')[0]) > 0:
                    return super().clean()
                raise forms.ValidationError(_("Please add at least one rate to this product."))
            except Exception as e:
                raise forms.ValidationError(_("Please add at least one rate to this product."))


@register_component
class CheckStripeComponent(BaseComponent):
    def get_context_data(self, **kwargs):
        config = Configuration.get_solo()
        context = super().get_context_data(**kwargs)
        context["children"] = render_to_string(
            "admin/product/checkstripe_component.html",
            {
                "stripe_payouts_enabled": config.stripe_payouts_enabled,
            },
        )
        return context


@admin.register(Tva, site=staff_admin_site)
class TvaAdmin(ModelAdmin):

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return False


class ProductArchiveFilter(admin.SimpleListFilter):
    title = _("Archivé")
    parameter_name = "archive"

    def lookups(self, request, model_admin):
        return [
            ("yes", _("Archivés")),
            ("all", _("Tous")),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.exclude(archive=True)
        if value == "yes":
            return queryset.filter(archive=True)
        if value == "all":
            return queryset
        return queryset


@admin.register(Product, site=staff_admin_site)
class ProductAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    inlines = [PriceInline, ProductFormFieldInline]

    list_before_template = "admin/product/product_list_before.html"  # appelle le component CheckStripe plus haut pour le contexte

    form = ProductAdminCustomForm

    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
                'categorie_article',
                'tva',
                'img',
                'poids',
                'short_description',
                'long_description',
                'max_per_user',
                'validate_button_text',
                'legal_link',
                'publish',
                'archive',
            ),
        }),
    )

    list_display = (
        'name',
        'categorie_article',
        'publish',
        'poids',
    )

    ordering = ("categorie_article", "poids",)
    list_filter = ['publish', 'categorie_article', ProductArchiveFilter]
    search_fields = ['name']

    # Pour les bouton en haut de la vue change
    # chaque decorateur @action génère une nouvelle route
    actions_row = ["duplicate_product", "archive", ]

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    @action(
        description=_("Duplicate product"),
        url_path="duplicate_product",
        permissions=["changelist_row_action"],
    )
    def duplicate_product(self, request, object_id):
        """
        Action d'administration pour dupliquer un produit.
        Admin action to duplicate a product.
        """
        # Récupération du produit original depuis la base de données
        # Retrieve the original product from the database
        produit_original = get_object_or_404(Product, pk=object_id)

        try:
            # Appel de la méthode de duplication profonde
            # Call the deep duplication method
            produit_duplique = self._duplicate_product(produit_original)

            # Message de succès à l'utilisateur
            # Success message to the user
            messages.success(
                request,
                _(f"Le produit '{produit_original.name}' a été dupliqué avec succès sous le nom '{produit_duplique.name}'")
            )
        except Exception as erreur:
            # En cas d'erreur, on logue et on informe l'utilisateur
            # In case of error, log it and inform the user
            logger.error(f"Erreur lors de la duplication du produit {object_id}: {str(erreur)}")
            messages.error(request, _(f"Erreur lors de la duplication : {str(erreur)}"))

        # Redirection vers la page précédente (la liste des produits)
        # Redirect back to the previous page (product list)
        referer = request.META.get("HTTP_REFERER")
        if referer:
            return redirect(referer)
        else:
            # Fallback to product list if no referer
            return redirect("admin:BaseBillet_product_changelist")

    def _duplicate_product(self, produit_source: Product):
        """
        Méthode d'aide pour réaliser une duplication profonde d'un produit.
        Cela inclut le produit lui-même, ses tarifs, ses champs de formulaires et ses relations.

        Helper method to perform a deep duplication of a product.
        This includes the product itself, its prices, form fields, and relationships.

        Le code est conçu pour être FALC (Facile À Lire et à Comprendre).
        The code is designed to be easy to read and understand (FALC).
        """

        # 1. DUPLICATION DE L'OBJET PRODUIT LUI-MÊME
        # 1. DUPLICATION OF THE PRODUCT OBJECT ITSELF

        # On récupère une instance propre du produit source
        # We fetch a fresh instance of the source product
        nouveau_produit = Product.objects.get(pk=produit_source.pk)

        # En mettant la clé primaire (pk) à None, Django créera un nouvel enregistrement lors du .save()
        # By setting the primary key (pk) to None, Django will create a new record upon .save()
        nouveau_produit.pk = None

        # On change le nom pour indiquer que c'est un duplicata
        # Change the name to indicate it is a duplicate
        nouveau_produit.name = f"{produit_source.name} [DUPLICATA]"

        # Le duplicata ne doit pas être publié par défaut
        # The duplicate should not be published by default
        nouveau_produit.publish = False

        # On s'assure que le duplicata n'est pas archivé
        # Ensure the duplicate is not archived
        nouveau_produit.archive = False

        # Sauvegarde initiale pour générer un nouvel UUID/PK
        # Initial save to generate a new UUID/PK
        nouveau_produit.save()

        # 2. DUPLICATION DES RELATIONS MANY-TO-MANY (M2M)
        # 2. DUPLICATION OF MANY-TO-MANY (M2M) RELATIONSHIPS

        # Duplication des tags
        # Duplicate tags
        nouveau_produit.tag.set(produit_source.tag.all())

        # Duplication des options générales (boutons radio)
        # Duplicate general options (radio buttons)
        nouveau_produit.option_generale_radio.set(produit_source.option_generale_radio.all())

        # Duplication des options générales (cases à cocher)
        # Duplicate general options (checkboxes)
        nouveau_produit.option_generale_checkbox.set(produit_source.option_generale_checkbox.all())

        # 3. DUPLICATION DES TARIFS (Price)
        # 3. DUPLICATION OF PRICES (Price)

        # On parcourt tous les tarifs associés au produit source
        # Loop through all prices associated with the source product
        for tarif_original in produit_source.prices.all():
            # Création d'une copie du tarif
            # Creating a copy of the price
            nouveau_tarif = Price.objects.get(pk=tarif_original.pk)
            nouveau_tarif.pk = None  # Prêt pour une nouvelle insertion / Ready for new insertion
            nouveau_tarif.product = nouveau_produit  # Liaison au nouveau produit / Link to new product
            nouveau_tarif.save()

        # 4. DUPLICATION DES FORMULAIRES DYNAMIQUES (ProductFormField)
        # 4. DUPLICATION OF DYNAMIC FORM FIELDS (ProductFormField)

        # Ces champs sont utilisés pour les formulaires personnalisés lors de l'adhésion
        # These fields are used for custom forms during subscription
        for champ_original in produit_source.form_fields.all():
            nouveau_champ = ProductFormField.objects.get(pk=champ_original.pk)
            nouveau_champ.pk = None
            nouveau_champ.product = nouveau_produit
            nouveau_champ.save()

        # 5. DUPLICATION DES FORMULAIRES FORMBRICKS (FormbricksForms)
        # 5. DUPLICATION OF FORMBRICKS FORMS (FormbricksForms)

        # Si le produit utilise des formulaires Formbricks, on les duplique aussi
        # If the product uses Formbricks forms, we duplicate them as well
        for formulaire_fb_original in produit_source.formbricksform.all():
            nouveau_formulaire_fb = FormbricksForms.objects.get(pk=formulaire_fb_original.pk)
            nouveau_formulaire_fb.pk = None
            nouveau_formulaire_fb.product = nouveau_produit
            nouveau_formulaire_fb.save()

        # Retourne le produit nouvellement créé
        # Returns the newly created product
        return nouveau_produit

    @action(
        description=_("Archive"),
        url_path="archive",
        permissions=["changelist_row_action"],
    )
    def archive(self, request, object_id):
        obj = get_object_or_404(Product, pk=object_id)
        obj.archive = True
        obj.save()
        messages.success(request, _(f"{obj.name} Archived"))
        return redirect(request.META["HTTP_REFERER"])

    def get_queryset(self, request):
        # On retire les recharges cashless et l'article Don
        # Pas besoin de les afficher, ils se créent automatiquement.
        qs = super().get_queryset(request)
        return qs.exclude(categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON])

    def get_search_results(self, request, queryset, search_term):
        """
        Pour la recherche de produit dans la page Event.
        On est sur un Many2Many, il faut bidouiller la réponde de ce coté
        Le but est que cela n'affiche dans le auto complete fields que les catégories Billets
        """
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if request.headers.get('Referer') and "admin/autocomplete" in request.path:
            referer = request.headers['Referer']
            logger.info(referer)
            if "event" in referer:
                # Autocomplete depuis EventAdmin : uniquement billets
                queryset = queryset.filter(categorie_article__in=[
                    Product.BILLET,
                    Product.FREERES,
                ]).exclude(archive=True)
            elif "price" in referer:
                # Autocomplete depuis PriceAdmin (adhesions_obligatoires) : uniquement adhesions
                queryset = queryset.filter(
                    categorie_article=Product.ADHESION,
                    archive=False,
                )
        return queryset, use_distinct

    def save_model(self, request, obj: Product, form, change):
        # Sanitize all TextField inputs to avoid XSS via WysiwYG/TextField
        sanitize_textfields(obj)
        try:
            super().save_model(request, obj, form, change)
        except IntegrityError as err:
            err_str = str(err)
            # Handle unique_together = ("categorie_article", "name") on Product
            if (
                    "BaseBillet_product_categorie_article_name" in err_str
                    or "BaseBillet_product_categorie_article_name_" in err_str
                    or "duplicate key value violates unique constraint" in err_str and "(categorie_article, name)" in err_str
            ):
                messages.error(
                    request,
                    _(
                        "Un produit avec ce nom existe déjà dans cette catégorie.\n"
                        "Merci de choisir un autre nom pour éviter les doublons."
                    ),
                )
                # Stay on the same page
                return redirect(request.META.get("HTTP_REFERER", reverse("admin:index")))
            # Unknown integrity error: log and re-raise
            logger.error(err)
            raise err
        except Exception as err:
            logger.error(err)
            raise err

    def has_changelist_row_action_permission(self, request: HttpRequest, *args, **kwargs):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# ---------------------------------------------------------------------------
# Proxy admins : vues filtrees par type de produit
# Proxy admins: filtered views per product type
#
# Le ProductAdmin original reste enregistre (autocomplete EventAdmin, URLs
# existantes, tests Playwright). Ces proxy admins ajoutent des vues dediees
# dans les sections Billetterie et Adhesion de la sidebar.
# ---------------------------------------------------------------------------


class TicketProductForm(ProductAdminCustomForm):
    """Formulaire produit restreint aux types billetterie.
    Product form restricted to ticket types."""

    class Meta(ProductAdminCustomForm.Meta):
        model = TicketProduct

    categorie_article = forms.ChoiceField(
        choices=[
            (Product.BILLET, _('Ticket booking')),
            (Product.FREERES, _('Free booking')),
        ],
        widget=UnfoldAdminSelectWidget(),
        label=_("Product type"),
    )


class MembershipProductForm(ProductAdminCustomForm):
    """Formulaire produit force en mode adhesion.
    Product form forced to membership mode.
    Le champ categorie_article est cache et pre-rempli."""

    class Meta(ProductAdminCustomForm.Meta):
        model = MembershipProduct

    categorie_article = forms.ChoiceField(
        choices=[
            (Product.ADHESION, _('Subscription or membership')),
        ],
        widget=forms.HiddenInput(),
        label=_("Product type"),
        initial=Product.ADHESION,
    )


@admin.register(TicketProduct, site=staff_admin_site)
class TicketProductAdmin(ProductAdmin):
    """Vue admin filtree : uniquement les produits billetterie (Billet, Reservation gratuite).
    Filtered admin view: only ticket products (Ticket booking, Free booking)."""
    form = TicketProductForm
    inlines = [PriceInline]  # Pas de ProductFormFieldInline (champs dynamiques = adhesions)

    list_filter = ['publish']  # categorie_article inutile, deja filtre

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(categorie_article__in=[Product.BILLET, Product.FREERES])


@admin.register(MembershipProduct, site=staff_admin_site)
class MembershipProductAdmin(ProductAdmin):
    """Vue admin filtree : uniquement les produits adhesion.
    Filtered admin view: only membership products."""
    form = MembershipProductForm
    inlines = [PriceInline, ProductFormFieldInline]

    list_filter = ['publish']  # categorie_article inutile, deja filtre

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(categorie_article=Product.ADHESION)


# ---------------------------------------------------------------------------
# POSProduct — proxy pour les produits de caisse (methode_caisse IS NOT NULL)
# Meme pattern que TicketProductAdmin / MembershipProductAdmin.
# / POS products proxy admin. Same pattern as Ticket/Membership proxy admins.
# ---------------------------------------------------------------------------


class POSProductForm(ProductAdminCustomForm):
    """Formulaire produit pour les articles de caisse.
    Product form for POS items.
    Le champ categorie_article est cache (pas pertinent en caisse)."""

    class Meta(ProductAdminCustomForm.Meta):
        model = POSProduct

    # En caisse, pas de categorie_article billetterie/adhesion :
    # on cache le champ et on met NONE par defaut.
    # / At POS, no ticket/membership category: hide the field, default to NONE.
    categorie_article = forms.ChoiceField(
        choices=[
            (Product.NONE, _('Select a category')),
        ],
        widget=forms.HiddenInput(),
        label=_("Product type"),
        initial=Product.NONE,
        required=False,
    )

    # Methode de caisse : obligatoire pour un produit POS
    # / POS method: required for a POS product
    methode_caisse = forms.ChoiceField(
        choices=Product.METHODE_CAISSE_CHOICES,
        widget=UnfoldAdminSelectWidget(),
        label=_("POS method"),
        help_text=_("Payment/action method at the cash register."),
    )

    def clean_categorie_article(self):
        """Pas de validation de categorie pour les produits POS.
        No category validation for POS products."""
        return self.cleaned_data.get('categorie_article', Product.NONE)

    def clean(self):
        """Pas de validation de tarif obligatoire pour les produits POS.
        No mandatory price validation for POS products."""
        return super(ProductAdminCustomForm, self).clean()


@admin.register(POSProduct, site=staff_admin_site)
class POSProductAdmin(ProductAdmin):
    """Vue admin filtree : uniquement les produits de caisse (methode_caisse IS NOT NULL).
    Filtered admin view: only POS products (methode_caisse IS NOT NULL).
    LOCALISATION : Administration/admin/products.py"""
    form = POSProductForm
    inlines = [PriceInline]  # Pas de ProductFormFieldInline (champs dynamiques = adhesions)

    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
                'categorie_article',
                'methode_caisse',
                'categorie_pos',
                'tva',
            ),
        }),
        (_('POS display'), {
            'fields': (
                'couleur_texte_pos',
                'couleur_fond_pos',
                'icon_pos',
                'groupe_pos',
                'poids',
            ),
        }),
        (_('POS options'), {
            'fields': (
                'fractionne',
                'besoin_tag_id',
            ),
        }),
        (_('Publication'), {
            'fields': (
                'publish',
                'archive',
            ),
        }),
    )

    list_display = (
        'name',
        'methode_caisse',
        'categorie_pos',
        'publish',
        'poids',
    )

    list_filter = ['publish', 'methode_caisse', 'categorie_pos']
    search_fields = ['name']

    def get_queryset(self, request):
        # Uniquement les produits avec une methode de caisse definie
        # / Only products with a POS method set
        qs = super().get_queryset(request)
        return qs.filter(methode_caisse__isnull=False)


# ---------------------------------------------------------------------------
# CategorieProduct — categories de produits POS (boissons, nourriture, etc.)
# / POS product categories (drinks, food, etc.)
# ---------------------------------------------------------------------------

@admin.register(CategorieProduct, site=staff_admin_site)
class CategorieProductAdmin(ModelAdmin):
    """Admin pour les categories de produits POS.
    Admin for POS product categories.
    LOCALISATION : Administration/admin/products.py"""
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ('name', 'icon', 'tva', 'poid_liste', 'cashless')
    search_fields = ['name']
    ordering = ('poid_liste', 'name')

    fieldsets = (
        (None, {
            'fields': (
                'name',
                'icon',
                'couleur_texte',
                'couleur_fond',
                'poid_liste',
                'tva',
                'cashless',
            ),
        }),
    )

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
