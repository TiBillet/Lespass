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
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.components import register_component, BaseComponent
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.decorators import action
from unfold.widgets import (
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
    UnfoldAdminColorInputWidget,
)

from Administration.admin.site import staff_admin_site, sanitize_textfields
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from BaseBillet.models import (
    Configuration,
    Product,
    TicketProduct,
    MembershipProduct,
    POSProduct,
    CategorieProduct,
    Price,
    FormbricksForms,
    ProductFormField,
    Tva,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Palettes de couleurs prédéfinies pour les boutons POS
# Pre-defined color palettes for POS product buttons
# Format : (clé, libellé, couleur_texte_hex, couleur_fond_hex)
# Format : (key, label, text_color_hex, background_color_hex)
# ---------------------------------------------------------------------------

PALETTE_POS = [
    # Classiques N&B / Classic B&W
    ("blanc_classique", _("Blanc classique"), "#000000", "#FFFFFF"),
    ("nuit", _("Nuit"), "#FFFFFF", "#1F2937"),
    # Material — fonds satures, texte blanc (contraste > 4.5:1)
    # / Material — saturated backgrounds, white text (contrast > 4.5:1)
    ("marine", _("Marine"), "#FFFFFF", "#1E40AF"),
    ("emeraude", _("Emeraude"), "#FFFFFF", "#059669"),
    ("violet", _("Violet"), "#FFFFFF", "#7C3AED"),
    ("corail", _("Corail"), "#FFFFFF", "#EF4444"),
    ("ambre", _("Ambre"), "#FFFFFF", "#B45309"),
    ("ardoise", _("Ardoise"), "#FFFFFF", "#475569"),
    # Nouvelles — fonds satures, fort contraste
    # / New — saturated backgrounds, high contrast
    ("foret", _("Foret"), "#FFFFFF", "#166534"),  # Vert profond / Deep green
    ("bordeaux", _("Bordeaux"), "#FFFFFF", "#881337"),  # Rouge vin / Wine red
    ("indigo", _("Indigo"), "#FFFFFF", "#3730A3"),  # Bleu-violet / Blue-violet
    ("ocean", _("Ocean"), "#FFFFFF", "#0E7490"),  # Cyan fonce / Dark cyan
    ("brique", _("Brique"), "#FFFFFF", "#9A3412"),  # Orange brique / Brick orange
    ("prune", _("Prune"), "#FFFFFF", "#6B21A8"),  # Violet fonce / Dark purple
    ("charbon", _("Charbon"), "#F59E0B", "#18181B"),  # Ambre sur noir / Amber on black
    (
        "neon",
        _("Neon"),
        "#10B981",
        "#0F172A",
    ),  # Vert neon sur nuit / Neon green on dark
    # Pastels — fonds doux, texte sombre contraste (contraste > 7:1)
    # / Pastels — soft backgrounds, contrasted dark text (contrast > 7:1)
    ("lavande", _("Lavande"), "#312E81", "#EDE9FE"),
    ("menthe", _("Menthe"), "#064E3B", "#D1FAE5"),
    ("peche", _("Peche"), "#78350F", "#FEF3C7"),
    ("rose", _("Rose"), "#881337", "#FFE4E6"),
    # Nouveaux pastels / New pastels
    ("ciel", _("Ciel"), "#1E3A5F", "#DBEAFE"),  # Bleu ciel / Sky blue
    ("sable", _("Sable"), "#451A03", "#FEF9C3"),  # Jaune sable / Sand yellow
]

# Dictionnaire pour lookup rapide clé → (couleur_texte, couleur_fond)
# Quick lookup dict: key → (text_color, bg_color)
PALETTE_POS_MAP = {
    key: (text_hex, bg_hex) for key, _label, text_hex, bg_hex in PALETTE_POS
}

# ---------------------------------------------------------------------------
# Icones FontAwesome 5 Free (solid) pour les articles POS
# FontAwesome 5 Free (solid) icons for POS items
# Licence : CC BY 4.0 (icones) + SIL OFL 1.1 (polices) + MIT (code)
# Liste complete : https://fontawesome.com/v5/search?m=free&s=solid
# ---------------------------------------------------------------------------

ICON_POS = [
    # Boissons / Drinks
    ("fa-beer", _("Biere")),
    ("fa-wine-glass-alt", _("Vin rouge / rose")),
    ("fa-wine-glass", _("Vin blanc")),
    ("fa-wine-bottle", _("Bouteille vin")),
    ("fa-cocktail", _("Cocktail / bar")),
    ("fa-glass-whiskey", _("Spiritueux / soda")),
    ("fa-glass-cheers", _("Champagne / fete")),
    ("fa-glass-martini-alt", _("Martini / apero")),
    ("fa-coffee", _("Cafe")),
    ("fa-mug-hot", _("The / boisson chaude")),
    ("fa-tint", _("Eau")),
    ("fa-lemon", _("Jus / limonade")),
    ("fa-blender", _("Smoothie / milkshake")),
    ("fa-flask", _("Biere artisanale")),
    ("fa-prescription-bottle", _("Shot / fiole")),
    ("fa-water", _("Eau minerale / source")),
    # Nourriture / Food
    ("fa-utensils", _("Restaurant / plat")),
    ("fa-pizza-slice", _("Pizza")),
    ("fa-hamburger", _("Burger")),
    ("fa-hotdog", _("Hot-dog / foodtruck")),
    ("fa-bread-slice", _("Sandwich / boulangerie")),
    ("fa-cheese", _("Fromage / plateau")),
    ("fa-egg", _("Brunch / petit-dej")),
    ("fa-apple-alt", _("Fruit / bio")),
    ("fa-leaf", _("Salade / vegetal")),
    ("fa-seedling", _("Bio / vegan")),
    ("fa-cookie", _("Dessert / gouter")),
    ("fa-cookie-bite", _("Snack")),
    ("fa-ice-cream", _("Glace")),
    ("fa-drumstick-bite", _("Grill / BBQ")),
    ("fa-fish", _("Poisson / fruits de mer")),
    ("fa-carrot", _("Legume / veggie")),
    ("fa-pepper-hot", _("Epice / piment")),
    ("fa-candy-cane", _("Confiserie / sucre")),
    ("fa-stroopwafel", _("Gaufre / crepe")),
    ("fa-bacon", _("Charcuterie / bacon")),
    ("fa-birthday-cake", _("Gateau d'anniversaire")),
    # Cashless / Monnaie
    ("fa-coins", _("Recharge euros")),
    ("fa-wallet", _("Wallet / solde")),
    ("fa-money-bill-wave", _("Especes")),
    ("fa-credit-card", _("Carte bancaire")),
    ("fa-money-check", _("Cheque")),
    ("fa-euro-sign", _("Euro")),
    ("fa-dollar-sign", _("Dollar")),
    ("fa-pound-sign", _("Livre sterling")),
    ("fa-ruble-sign", _("Rouble")),
    ("fa-lira-sign", _("Lire / livre turque")),
    ("fa-rupee-sign", _("Roupie")),
    ("fa-yen-sign", _("Yen / yuan")),
    ("fa-shekel-sign", _("Shekel")),
    ("fa-won-sign", _("Won")),
    ("fa-gift", _("Recharge cadeau")),
    ("fa-gem", _("Jeton premium")),
    ("fa-clock", _("Recharge temps")),
    # Adhesion / Abonnement
    ("fa-id-card", _("Adhesion / membre")),
    ("fa-user-plus", _("Nouvel adherent")),
    ("fa-users", _("Communaute / asso")),
    ("fa-handshake", _("Partenariat / cooperative")),
    ("fa-heart", _("Don / soutien")),
    ("fa-star", _("Premium / fidelite")),
    # Spectacle / Festival
    ("fa-ticket-alt", _("Billetterie")),
    ("fa-music", _("Concert / musique")),
    ("fa-guitar", _("Live / scene")),
    ("fa-microphone-alt", _("Spectacle / conference")),
    ("fa-theater-masks", _("Theatre")),
    ("fa-campground", _("Festival / camping")),
    ("fa-bus", _("Navette / transport")),
    ("fa-tshirt", _("T-shirt / vetement")),
    ("fa-hat-wizard", _("Chapeau / coiffe")),
    ("fa-socks", _("Chaussettes / accessoire")),
    ("fa-shopping-bag", _("Sac / tote bag")),
    ("fa-book", _("Livre / fanzine")),
    ("fa-compact-disc", _("CD / vinyle")),
    ("fa-palette", _("Art / serigraphie")),
    ("fa-pen-fancy", _("Stylo / papeterie")),
    ("fa-box-open", _("Coffret / lot")),
    ("fa-tag", _("Article / divers")),
    # Lieux / Points de vente
    ("fa-umbrella-beach", _("Terrasse / plage")),
    ("fa-store", _("Boutique / stand")),
    ("fa-store-alt", _("Echoppe / marche")),
    ("fa-door-open", _("Entree / accueil")),
    ("fa-map-marker-alt", _("Lieu / emplacement")),
    ("fa-home", _("Maison / local")),
    ("fa-warehouse", _("Hangar / entrepot")),
    ("fa-truck", _("Foodtruck / camion")),
    ("fa-shuttle-van", _("Navette / van")),
    ("fa-caravan", _("Caravane / roulotte")),
    ("fa-tree", _("Jardin / exterieur")),
    ("fa-fire", _("Feu / barbecue")),
    ("fa-sun", _("Plein air / ete")),
    # Actions / Danger
    ("fa-exclamation-triangle", _("Danger / attention")),
    ("fa-trash-alt", _("Vider / supprimer")),
    ("fa-undo-alt", _("Annuler / remboursement")),
    ("fa-exchange-alt", _("Consigne / echange")),
    ("fa-recycle", _("Consigne retour")),
    ("fa-ban", _("Bloquer / desactiver")),
    ("fa-lock", _("Verrouille")),
    ("fa-check-circle", _("Valide / succes")),
]


# ---------------------------------------------------------------------------
# Widget visuel : sélecteur de palette de couleurs
# Visual widget: color palette picker
# ---------------------------------------------------------------------------


class PalettePickerWidget(forms.Widget):
    """Widget radio visuel qui affiche des swatches de couleur cliquables.
    Visual radio widget displaying clickable color swatches.

    Paramètres / Parameters:
      texte_field : nom du champ HTML couleur texte à mettre à jour au clic
                    name of the HTML text color field to update on click
      fond_field  : nom du champ HTML couleur fond à mettre à jour au clic
                    name of the HTML background color field to update on click

    LOCALISATION : Administration/admin/products.py"""

    def __init__(
        self,
        *args,
        texte_field="couleur_texte_pos",
        fond_field="couleur_fond_pos",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        # Noms des champs couleur à piloter (différent selon le formulaire parent)
        # Names of the color fields to drive (differ depending on the parent form)
        self.texte_field = texte_field
        self.fond_field = fond_field

    def render(self, name, value, attrs=None, renderer=None):
        # Valeur actuelle (peut être None ou une chaîne vide)
        # Current value (can be None or empty string)
        valeur_actuelle = value or ""

        # Rendu via template dédié (résolu via APP_DIRS de Django)
        # Render via dedicated template (resolved via Django's APP_DIRS)
        return mark_safe(
            render_to_string(
                "admin/widgets/palette_picker.html",
                {
                    "widget_name": name,
                    "current_value": valeur_actuelle,
                    "palettes": PALETTE_POS,
                    "texte_field": self.texte_field,
                    "fond_field": self.fond_field,
                },
            )
        )


# ---------------------------------------------------------------------------
# Widget visuel : sélecteur d'icône Material Symbols
# Visual widget: Material Symbols icon picker
# ---------------------------------------------------------------------------


class IconPickerWidget(forms.Widget):
    """Widget radio visuel qui affiche une grille d'icônes cliquables.
    Visual radio widget displaying a clickable icon grid.
    LOCALISATION : Administration/admin/products.py"""

    def render(self, name, value, attrs=None, renderer=None):
        # Valeur actuelle (peut être None ou une chaîne vide)
        # Current value (can be None or empty string)
        valeur_actuelle = value or ""

        # Rendu via template dédié
        # Render via dedicated template
        return mark_safe(
            render_to_string(
                "admin/widgets/icon_picker.html",
                {
                    "widget_name": name,
                    "current_value": valeur_actuelle,
                    "icons": ICON_POS,
                },
            )
        )


class PriceInlineChangeForm(ModelForm):
    # Formulaire inline pour les tarifs (dans ProductAdmin et POSProductAdmin)
    # / Inline form for prices (in ProductAdmin and POSProductAdmin)
    class Meta:
        model = Price
        fields = (
            "name",
            "product",
            "prix",
            "free_price",
            "subscription_type",
            "publish",
        )

    def clean_prix(self):
        cleaned_data = self.cleaned_data
        prix = cleaned_data.get("prix")
        if 0 < prix < 1:
            raise forms.ValidationError(
                _("A rate cannot be between 0€ and 1€"), code="invalid"
            )
        return prix

    def clean_subscription_type(self):
        cleaned_data = self.cleaned_data
        product: Product = cleaned_data.get("product")
        subscription_type = cleaned_data.get("subscription_type")
        if product.categorie_article == Product.ADHESION:
            if subscription_type == Price.NA:
                raise forms.ValidationError(
                    _("A subscription must have a duration"), code="invalid"
                )
        return subscription_type


class PriceInline(TabularInline):
    model = Price
    fk_name = "product"
    form = PriceInlineChangeForm
    extra = 0
    show_change_link = True

    def get_fields(self, request, obj=None):
        # Champs de base pour tous les produits
        # / Base fields for all products
        fields = [
            "name",
            "product",
            "prix",
            "free_price",
            "subscription_type",
            "publish",
        ]

        # Contenance visible uniquement pour les articles POS de type vente
        # / Contenance visible only for POS sale products (methode_caisse=VT)
        if (
            obj
            and hasattr(obj, "methode_caisse")
            and obj.methode_caisse == Product.VENTE
        ):
            fields.insert(4, "contenance")

        return fields

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
            "For Single select (menu), Radio or Multiple select, enter choices separated by commas. Example: Rock, Electro, Jazz"
        ),
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
            opts = self.instance.options if getattr(self, "instance", None) else None
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
    fk_name = "product"
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
            "name",
            "categorie_article",
            "tva",
            "short_description",
            "long_description",
            "img",
            "poids",
            # "option_generale_radio",
            # "option_generale_checkbox",
            "validate_button_text",
            "legal_link",
            "publish",
            "archive",
        )
        help_texts = {
            "img": _("Product image is displayed at a 16/9 ratio."),
        }

    categorie_article = forms.ChoiceField(
        required=False,
        choices=[
            (Product.NONE, _("Select a category")),
            (Product.BILLET, _("Ticket booking")),
            (Product.FREERES, _("Free booking")),
            (Product.ADHESION, _("Subscription or membership")),
        ],
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Product type"),
    )

    def clean_categorie_article(self):
        cleaned_data = self.cleaned_data
        categorie = cleaned_data.get("categorie_article")
        if categorie == Product.NONE:
            raise forms.ValidationError(
                _("Please add at least one category to this product.")
            )

        # Vérification que la clé Stripe est opérationnelle :
        if categorie != Product.FREERES:
            config = Configuration.get_solo()
            if not config.stripe_payouts_enabled:
                raise forms.ValidationError(
                    _(
                        "Your Stripe account is not activated. To create paid items, please go to Settings/Stripe/Onboard."
                    )
                )
        return categorie

    def clean(self):
        # Vérification qu'il existe au moins un tarif si produit payant
        if self.data.get("categorie_article") not in [Product.FREERES, Product.BADGE]:
            try:
                # récupération du dictionnaire data pour vérifier qu'on a bien au moin un tarif dans le inline :
                if int(self.data.getlist("prices-TOTAL_FORMS")[0]) > 0:
                    return super().clean()
                raise forms.ValidationError(
                    _("Please add at least one rate to this product.")
                )
            except Exception:
                raise forms.ValidationError(
                    _("Please add at least one rate to this product.")
                )


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
        (
            _("General"),
            {
                "fields": (
                    "name",
                    "categorie_article",
                    "tva",
                    "img",
                    "poids",
                    "short_description",
                    "long_description",
                    "max_per_user",
                    "validate_button_text",
                    "legal_link",
                    "publish",
                    "archive",
                ),
            },
        ),
    )

    list_display = (
        "name",
        "categorie_article",
        "publish",
        "poids",
    )

    ordering = (
        "categorie_article",
        "poids",
    )
    list_filter = ["publish", "categorie_article", ProductArchiveFilter]
    search_fields = ["name"]

    # Pour les bouton en haut de la vue change
    # chaque decorateur @action génère une nouvelle route
    actions_row = [
        "duplicate_product",
        "archive",
    ]

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
                _(
                    f"Le produit '{produit_original.name}' a été dupliqué avec succès sous le nom '{produit_duplique.name}'"
                ),
            )
        except Exception as erreur:
            # En cas d'erreur, on logue et on informe l'utilisateur
            # In case of error, log it and inform the user
            logger.error(
                f"Erreur lors de la duplication du produit {object_id}: {str(erreur)}"
            )
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
        nouveau_produit.option_generale_radio.set(
            produit_source.option_generale_radio.all()
        )

        # Duplication des options générales (cases à cocher)
        # Duplicate general options (checkboxes)
        nouveau_produit.option_generale_checkbox.set(
            produit_source.option_generale_checkbox.all()
        )

        # 3. DUPLICATION DES TARIFS (Price)
        # 3. DUPLICATION OF PRICES (Price)

        # On parcourt tous les tarifs associés au produit source
        # Loop through all prices associated with the source product
        for tarif_original in produit_source.prices.all():
            # Création d'une copie du tarif
            # Creating a copy of the price
            nouveau_tarif = Price.objects.get(pk=tarif_original.pk)
            nouveau_tarif.pk = (
                None  # Prêt pour une nouvelle insertion / Ready for new insertion
            )
            nouveau_tarif.product = (
                nouveau_produit  # Liaison au nouveau produit / Link to new product
            )
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
            nouveau_formulaire_fb = FormbricksForms.objects.get(
                pk=formulaire_fb_original.pk
            )
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
        return qs.exclude(
            categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON]
        )

    def get_search_results(self, request, queryset, search_term):
        """
        Pour la recherche de produit dans la page Event.
        On est sur un Many2Many, il faut bidouiller la réponde de ce coté
        Le but est que cela n'affiche dans le auto complete fields que les catégories Billets
        """
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )
        if request.headers.get("Referer") and "admin/autocomplete" in request.path:
            referer = request.headers["Referer"]
            logger.info(referer)
            if "event" in referer:
                # Autocomplete depuis EventAdmin : uniquement billets
                queryset = queryset.filter(
                    categorie_article__in=[
                        Product.BILLET,
                        Product.FREERES,
                    ]
                ).exclude(archive=True)
            elif "price" in referer:
                # Autocomplete depuis PriceAdmin (adhesions_obligatoires) : uniquement adhesions
                queryset = queryset.filter(
                    categorie_article=Product.ADHESION,
                    archive=False,
                )
            elif "inventaire/stock" in referer:
                # Autocomplete depuis StockAdmin : uniquement articles de vente (VT)
                # Pas les recharges, adhésions, consignes, etc.
                # / Autocomplete from StockAdmin: only sale articles (VT)
                queryset = queryset.filter(
                    methode_caisse=Product.VENTE,
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
                or "duplicate key value violates unique constraint" in err_str
                and "(categorie_article, name)" in err_str
            ):
                messages.error(
                    request,
                    _(
                        "Un produit avec ce nom existe déjà dans cette catégorie.\n"
                        "Merci de choisir un autre nom pour éviter les doublons."
                    ),
                )
                # Stay on the same page
                return redirect(
                    request.META.get("HTTP_REFERER", reverse("admin:index"))
                )
            # Unknown integrity error: log and re-raise
            logger.error(err)
            raise err
        except Exception as err:
            logger.error(err)
            raise err

    def has_changelist_row_action_permission(
        self, request: HttpRequest, *args, **kwargs
    ):
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
            (Product.BILLET, _("Ticket booking")),
            (Product.FREERES, _("Free booking")),
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
            (Product.ADHESION, _("Subscription or membership")),
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
    inlines = [
        PriceInline
    ]  # Pas de ProductFormFieldInline (champs dynamiques = adhesions)

    list_filter = ["publish"]  # categorie_article inutile, deja filtre

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(categorie_article__in=[Product.BILLET, Product.FREERES])


@admin.register(MembershipProduct, site=staff_admin_site)
class MembershipProductAdmin(ProductAdmin):
    """Vue admin filtree : uniquement les produits adhesion.
    Filtered admin view: only membership products."""

    form = MembershipProductForm
    inlines = [PriceInline, ProductFormFieldInline]

    list_filter = ["publish"]  # categorie_article inutile, deja filtre

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
    Le champ categorie_article est cache (pas pertinent en caisse).
    LOCALISATION : Administration/admin/products.py"""

    class Meta(ProductAdminCustomForm.Meta):
        model = POSProduct

    # En caisse, pas de categorie_article billetterie/adhesion :
    # on cache le champ et on met NONE par defaut.
    # / At POS, no ticket/membership category: hide the field, default to NONE.
    categorie_article = forms.ChoiceField(
        choices=[
            (Product.NONE, _("Select a category")),
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

    # --- Champs d'affichage POS / POS display fields ---

    # Palette de couleurs prédéfinie (champ formulaire uniquement, non sauvegardé directement)
    # Pre-defined color palette (form-only field, not saved directly to the model)
    palette_pos = forms.ChoiceField(
        choices=[("", _("— Aucune palette —"))]
        + [(key, label) for key, label, _t, _b in PALETTE_POS],
        required=False,
        label=_("Color palette"),
        help_text=_(
            "Choisissez une combinaison de couleurs prête à l'emploi. "
            "Elle remplacera les champs couleur ci-dessous. "
            "/ Choose a ready-to-use color combination. It will override the color fields below."
        ),
        widget=PalettePickerWidget(),
    )

    # Couleur du texte avec sélecteur natif (override palette si renseigné manuellement)
    # Text color with native picker (overrides palette if filled manually)
    couleur_texte_pos = forms.CharField(
        max_length=7,
        required=False,
        label=_("POS text color"),
        help_text=_("Par défaut, couleur de la catégorie. / Default: category color."),
        widget=UnfoldAdminColorInputWidget(),
    )

    # Couleur du fond avec sélecteur natif
    # Background color with native picker
    couleur_fond_pos = forms.CharField(
        max_length=7,
        required=False,
        label=_("POS background color"),
        help_text=_("Par défaut, couleur de la catégorie. / Default: category color."),
        widget=UnfoldAdminColorInputWidget(),
    )

    # Icône avec sélecteur visuel Material Symbols
    # Icon with visual Material Symbols picker
    icon_pos = forms.ChoiceField(
        choices=[("", _("— Aucune icône —"))] + list(ICON_POS),
        required=False,
        label=_("POS icon"),
        help_text=_(
            "Si une image produit est définie ci-dessous, elle sera affichée à la place de cette icône. / If a product image is set below, it will be displayed instead of this icon."
        ),
        widget=IconPickerWidget(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        instance = kwargs.get("instance")

        # Pré-sélection de la palette si les couleurs actuelles correspondent à un preset
        # Pre-select the palette if the current colors match a preset
        if instance and instance.couleur_texte_pos and instance.couleur_fond_pos:
            for key, _label, text_hex, bg_hex in PALETTE_POS:
                couleurs_correspondent = (
                    instance.couleur_texte_pos.upper() == text_hex.upper()
                    and instance.couleur_fond_pos.upper() == bg_hex.upper()
                )
                if couleurs_correspondent:
                    self.fields["palette_pos"].initial = key
                    break

        # Help_text TVA dynamique : affiche le taux de la catégorie si disponible
        # Dynamic VAT help_text: shows category rate if available
        if (
            instance
            and getattr(instance, "categorie_pos", None)
            and getattr(instance.categorie_pos, "tva", None)
        ):
            taux = instance.categorie_pos.tva.tva_rate
            self.fields["tva"].help_text = _(
                f"Même TVA que la catégorie ({taux}%) si laissé vide. Surchargeable ici. "
                f"/ Same VAT as category ({taux}%) if left empty. Can be overridden here."
            )
        else:
            self.fields["tva"].help_text = _(
                "Même TVA que la catégorie si laissé vide. / Same VAT as category if left empty."
            )

    def clean_categorie_article(self):
        """Pas de validation de categorie pour les produits POS.
        No category validation for POS products."""
        return self.cleaned_data.get("categorie_article", Product.NONE)

    def clean(self):
        """Applique la palette sélectionnée sur les champs couleur, puis valide.
        Applies the selected palette to the color fields, then validates."""

        # On saute la validation de ProductAdminCustomForm (pas de tarif obligatoire en caisse)
        # Skip ProductAdminCustomForm validation (no mandatory price at POS)
        cleaned = super(ProductAdminCustomForm, self).clean()

        # Décodage de la palette : si une palette est choisie, elle écrase les couleurs
        # Decode palette: if a palette is chosen, it overrides the color fields
        palette_key = cleaned.get("palette_pos")
        if palette_key and palette_key in PALETTE_POS_MAP:
            text_hex, bg_hex = PALETTE_POS_MAP[palette_key]
            cleaned["couleur_texte_pos"] = text_hex
            cleaned["couleur_fond_pos"] = bg_hex

        return cleaned


@admin.register(POSProduct, site=staff_admin_site)
class POSProductAdmin(ProductAdmin):
    """Vue admin filtree : uniquement les produits de caisse (methode_caisse IS NOT NULL).
    Filtered admin view: only POS products (methode_caisse IS NOT NULL).
    LOCALISATION : Administration/admin/products.py"""

    form = POSProductForm
    inlines = [PriceInline]

    fieldsets = (
        (
            _("General"),
            {
                "fields": (
                    "name",
                    "categorie_article",
                    "methode_caisse",
                    "categorie_pos",
                    "tva",
                    "prix_achat",
                ),
            },
        ),
        (
            _("POS display"),
            {
                "fields": (
                    "palette_pos",
                    "couleur_texte_pos",
                    "couleur_fond_pos",
                    "icon_pos",
                    "img",
                    "poids",
                ),
            },
        ),
        # (_('POS options'), {
        #     'fields': (
        #         'fractionne',
        #         'besoin_tag_id',
        #     ),
        # }),
        (
            _("Publication"),
            {
                "fields": (
                    "publish",
                    "archive",
                ),
            },
        ),
    )

    list_display = (
        "name",
        "methode_caisse",
        "categorie_pos",
        "publish",
        "poids",
    )

    list_filter = ["publish", "methode_caisse", "categorie_pos"]
    search_fields = ["name"]

    def get_inlines(self, request, obj):
        # En mode add (pas d'obj) : StockInline pour créer le stock initial
        # En mode change : pas de StockInline (le stock se gère via admin/inventaire/stock/)
        # / In add mode: StockInline for initial stock creation
        # In change mode: no StockInline (stock managed via admin/inventaire/stock/)
        if obj is None:
            from Administration.admin.inventaire import StockInline

            return [StockInline, PriceInline]
        return [PriceInline]

    def get_queryset(self, request):
        # Uniquement les produits avec une methode de caisse definie
        # / Only products with a POS method set
        qs = super().get_queryset(request)
        return qs.filter(methode_caisse__isnull=False)


# ---------------------------------------------------------------------------
# CategorieProduct — categories de produits POS (boissons, nourriture, etc.)
# / POS product categories (drinks, food, etc.)
# ---------------------------------------------------------------------------


class CategorieProductForm(forms.ModelForm):
    """Formulaire pour les catégories de produits POS.
    Ajoute un sélecteur de palette et un sélecteur d'icône visuels,
    identiques à ceux du formulaire POSProduct.
    / Form for POS product categories.
    Adds visual palette and icon pickers, identical to POSProductForm.
    LOCALISATION : Administration/admin/products.py"""

    class Meta:
        model = CategorieProduct
        fields = (
            "name",
            "couleur_texte",
            "couleur_fond",
            "icon",
            "poid_liste",
            "tva",
            "cashless",
        )

    # Palette de couleurs prédéfinie (form-only — pilote couleur_texte + couleur_fond)
    # Pre-defined color palette (form-only — drives couleur_texte + couleur_fond)
    palette = forms.ChoiceField(
        choices=[("", _("— Aucune palette —"))]
        + [(key, label) for key, label, _t, _b in PALETTE_POS],
        required=False,
        label=_("Color palette"),
        help_text=_(
            "Choisissez une combinaison prête à l'emploi. "
            "Elle remplacera les champs couleur ci-dessous. "
            "/ Choose a ready-to-use color combination. It will override the color fields below."
        ),
        # texte_field / fond_field correspondent aux noms de champs du modèle CategorieProduct
        # texte_field / fond_field match the CategorieProduct model field names
        widget=PalettePickerWidget(
            texte_field="couleur_texte", fond_field="couleur_fond"
        ),
    )

    # Couleur du texte avec sélecteur natif
    # Text color with native color picker
    couleur_texte = forms.CharField(
        max_length=7,
        required=False,
        label=_("Text color"),
        help_text=_("Hexadecimal color for the button text (e.g. #FFFFFF)."),
        widget=UnfoldAdminColorInputWidget(),
    )

    # Couleur du fond avec sélecteur natif
    # Background color with native color picker
    couleur_fond = forms.CharField(
        max_length=7,
        required=False,
        label=_("Background color"),
        help_text=_("Hexadecimal color for the button background (e.g. #1E40AF)."),
        widget=UnfoldAdminColorInputWidget(),
    )

    # Icône avec sélecteur visuel Material Symbols
    # Icon with visual Material Symbols picker
    icon = forms.ChoiceField(
        choices=[("", _("— Aucune icône —"))] + list(ICON_POS),
        required=False,
        label=_("Icon"),
        help_text=_(
            "Icône affichée sur le bouton de catégorie dans l'interface caisse. / Icon displayed on the category button in the POS interface."
        ),
        widget=IconPickerWidget(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")

        # Pré-sélection de la palette si les couleurs actuelles correspondent à un preset
        # Pre-select palette if the current colors match a preset
        if instance and instance.couleur_texte and instance.couleur_fond:
            for key, _label, text_hex, bg_hex in PALETTE_POS:
                couleurs_correspondent = (
                    instance.couleur_texte.upper() == text_hex.upper()
                    and instance.couleur_fond.upper() == bg_hex.upper()
                )
                if couleurs_correspondent:
                    self.fields["palette"].initial = key
                    break

    def clean(self):
        """Applique la palette sélectionnée sur les champs couleur.
        Applies the selected palette to the color fields."""
        cleaned = super().clean()

        # Si une palette est choisie, elle écrase les couleurs saisies manuellement
        # If a palette is chosen, it overrides manually entered colors
        palette_key = cleaned.get("palette")
        if palette_key and palette_key in PALETTE_POS_MAP:
            text_hex, bg_hex = PALETTE_POS_MAP[palette_key]
            cleaned["couleur_texte"] = text_hex
            cleaned["couleur_fond"] = bg_hex

        return cleaned


@admin.register(CategorieProduct, site=staff_admin_site)
class CategorieProductAdmin(ModelAdmin):
    """Admin pour les categories de produits POS.
    Admin for POS product categories.
    LOCALISATION : Administration/admin/products.py"""

    compressed_fields = True
    warn_unsaved_form = True
    form = CategorieProductForm

    list_display = ("name", "icon", "tva", "poid_liste", "cashless")
    search_fields = ["name"]
    ordering = ("poid_liste", "name")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "poid_liste",
                    "tva",
                    "cashless",
                ),
            },
        ),
        (
            _("Apparence / Appearance"),
            {
                "fields": (
                    "palette",
                    "couleur_texte",
                    "couleur_fond",
                    "icon",
                ),
            },
        ),
        (
            _("Accounting / Comptabilite"),
            {
                "fields": ("compte_comptable",),
            },
        ),
    )
    autocomplete_fields = ["compte_comptable"]

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
