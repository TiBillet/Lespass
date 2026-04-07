# FutProductAdmin + ameliorations Stock/help texts — Plan d'implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre la creation et modification de produits de type FUT dans l'admin Unfold, ameliorer le StockInline et les help texts poids_mesure/contenance.

**Architecture:** Proxy admin FutProductAdmin (meme pattern que POSProductAdmin), corrections sur StockInline/StockAdmin, enrichissement des help texts. Zero migration (proxy + help_text).

**Tech Stack:** Django 4.x, django-unfold, django-tenants, django-solo

**Spec de reference :** `docs/superpowers/specs/2026-04-07-futproduct-admin-stock-improvements-design.md`

---

## Vue d'ensemble des taches

| Tache | Description | Fichiers principaux |
|-------|-------------|---------------------|
| 1 | StockInline : quantite editable en mode add | `Administration/admin/inventaire.py` |
| 2 | StockAdmin : unite modifiable en mode change | `Administration/admin/inventaire.py` |
| 3 | Help texts poids_mesure et contenance enrichis | `BaseBillet/models.py` |
| 4 | FutProductForm + FutPriceInline + FutProductAdmin | `Administration/admin/products.py` |
| 5 | Sidebar "Produits fut" conditionnelle | `Administration/admin/dashboard.py` |
| 6 | Traductions FR/EN | `locale/fr/LC_MESSAGES/django.po`, `locale/en/LC_MESSAGES/django.po` |
| 7 | Verification manuelle | navigateur |

---

### Tache 1 : StockInline — quantite editable en mode add

**Fichiers :**
- Modifier : `Administration/admin/inventaire.py:78-91`

- [ ] **Step 1 : Remplacer readonly_fields statique par get_readonly_fields dynamique**

Dans `Administration/admin/inventaire.py`, remplacer le bloc `StockInline` (lignes 78-91) :

```python
class StockInline(TabularInline):
    model = Stock
    extra = 0
    max_num = 1
    fields = ("quantite", "unite", "seuil_alerte", "autoriser_vente_hors_stock")

    def get_readonly_fields(self, request, obj=None):
        # En mode add (obj=None) : quantite editable pour saisir le stock initial
        # En mode change : quantite readonly (modifiable via mouvements de stock)
        # / In add mode: quantite editable for initial stock entry
        # In change mode: quantite read-only (modified via stock movements)
        if obj is None:
            return []
        return ("quantite",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "quantite" and field is not None:
            field.help_text = _(
                "Initial stock quantity (in stock unit). "
                "After creation, modify via Inventory > Stock movements."
            )
        return field

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)
```

- [ ] **Step 2 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues.`

---

### Tache 2 : StockAdmin — unite modifiable en mode change

**Fichiers :**
- Modifier : `Administration/admin/inventaire.py:227-234`

- [ ] **Step 1 : Retirer unite des readonly en mode change**

Dans `StockAdmin.get_readonly_fields()` (ligne 227-234), remplacer :

```python
    def get_readonly_fields(self, request, obj=None):
        # En mode change : article (lien) et quantite sont en lecture seule
        # L'unite reste modifiable en cas d'erreur de saisie initiale
        # / In change mode: article (link) and quantity are read-only
        # Unit remains editable in case of initial input error
        if obj is not None:
            return ["lien_vers_pos_product", "quantite"]
        return []
```

- [ ] **Step 2 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues.`

---

### Tache 3 : Help texts poids_mesure et contenance enrichis

**Fichiers :**
- Modifier : `BaseBillet/models.py:1567-1574` (poids_mesure)
- Modifier : `BaseBillet/models.py:1603-1612` (contenance)

- [ ] **Step 1 : Enrichir le help_text de poids_mesure**

Dans `BaseBillet/models.py`, remplacer le bloc `poids_mesure` (lignes 1567-1574) :

```python
    poids_mesure = models.BooleanField(
        default=False,
        verbose_name=_("Sale by weight/volume"),
        help_text=_(
            "If checked, the cashier enters the weight or volume at each sale. "
            "The price is per kg (grams) or per liter (centiliters). "
            "Stock is decremented by the exact quantity entered."
        ),
    )
```

- [ ] **Step 2 : Enrichir le help_text de contenance**

Dans `BaseBillet/models.py`, remplacer le bloc `contenance` (lignes 1603-1612) :

```python
    contenance = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Contenance"),
        help_text=_(
            "Stock quantity consumed per unit sold (in stock unit). "
            "Use this when selling by unit but decrementing stock by weight/volume. "
            "E.g.: pint=50 (cl), half=25 (cl), portion=150 (g). "
            "Empty = 1 unit. Incompatible with 'Sale by weight/volume' "
            "(where the cashier enters the exact quantity)."
        ),
    )
```

- [ ] **Step 3 : Verifier que makemigrations ne genere rien (ou juste une migration triviale help_text)**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
```

Si une migration est generee (Django detecte les help_text), la creer :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet --name update_help_texts_poids_contenance
```

- [ ] **Step 4 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

### Tache 4 : FutProductForm + FutPriceInline + FutProductAdmin

**Fichiers :**
- Modifier : `Administration/admin/products.py` (import ligne 27 + nouveau bloc avant ligne 1484)
- Modifier : `BaseBillet/models.py` (import — `FutProduct` deja dans le fichier, mais verifier l'import dans products.py)

- [ ] **Step 1 : Ajouter l'import FutProduct**

Dans `Administration/admin/products.py`, ligne 27-38, ajouter `FutProduct` dans l'import :

```python
from BaseBillet.models import (
    Configuration,
    Product,
    TicketProduct,
    MembershipProduct,
    POSProduct,
    FutProduct,
    CategorieProduct,
    Price,
    FormbricksForms,
    ProductFormField,
    Tva,
)
```

- [ ] **Step 2 : Ajouter FutProductForm**

Inserer avant la ligne 1484 (commentaire `CategorieProduct`) :

```python
# ---------------------------------------------------------------------------
# FutProduct — proxy pour les produits de type fut (tireuses connectees)
# Meme pattern que POSProductAdmin avec couleurs, icone, image.
# / Keg products proxy admin. Same pattern as POS proxy admin.
# ---------------------------------------------------------------------------


class FutProductForm(ProductAdminCustomForm):
    """Formulaire produit pour les futs de tireuse.
    Le champ categorie_article est cache et force a FUT.
    Memes champs visuels que POSProductForm (palette, couleurs, icone).
    / Product form for beer kegs.
    categorie_article is hidden and forced to FUT.
    Same visual fields as POSProductForm (palette, colors, icon).
    LOCALISATION : Administration/admin/products.py"""

    class Meta(ProductAdminCustomForm.Meta):
        model = FutProduct

    # Categorie forcee a FUT — cachee dans le formulaire
    # / Category forced to FUT — hidden in the form
    categorie_article = forms.ChoiceField(
        choices=[
            (Product.FUT, _("Keg (connected tap)")),
        ],
        widget=forms.HiddenInput(),
        label=_("Product type"),
        initial=Product.FUT,
    )

    # --- Champs d'affichage POS / POS display fields ---

    # Palette de couleurs predefinie (champ formulaire uniquement, non sauvegarde directement)
    # / Pre-defined color palette (form-only field, not saved directly to the model)
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

    # Couleur du texte avec selecteur natif
    # / Text color with native picker
    couleur_texte_pos = forms.CharField(
        max_length=7,
        required=False,
        label=_("POS text color"),
        help_text=_("Par défaut, couleur de la catégorie. / Default: category color."),
        widget=UnfoldAdminColorInputWidget(),
    )

    # Couleur du fond avec selecteur natif
    # / Background color with native picker
    couleur_fond_pos = forms.CharField(
        max_length=7,
        required=False,
        label=_("POS background color"),
        help_text=_("Par défaut, couleur de la catégorie. / Default: category color."),
        widget=UnfoldAdminColorInputWidget(),
    )

    # Icone avec selecteur visuel Material Symbols
    # / Icon with visual Material Symbols picker
    icon_pos = forms.ChoiceField(
        choices=[("", _("— Aucune icône —"))] + list(ICON_POS),
        required=False,
        label=_("POS icon"),
        help_text=_(
            "Si une image produit est définie ci-dessous, elle sera affichée à la place de cette icône. "
            "/ If a product image is set below, it will be displayed instead of this icon."
        ),
        widget=IconPickerWidget(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        instance = kwargs.get("instance")

        # Pre-selection de la palette si les couleurs actuelles correspondent a un preset
        # / Pre-select the palette if the current colors match a preset
        if instance and instance.couleur_texte_pos and instance.couleur_fond_pos:
            for key, _label, text_hex, bg_hex in PALETTE_POS:
                couleurs_correspondent = (
                    instance.couleur_texte_pos.upper() == text_hex.upper()
                    and instance.couleur_fond_pos.upper() == bg_hex.upper()
                )
                if couleurs_correspondent:
                    self.fields["palette_pos"].initial = key
                    break

    def clean_categorie_article(self):
        """Pas de validation de categorie pour les futs.
        No category validation for keg products."""
        return self.cleaned_data.get("categorie_article", Product.FUT)

    def clean(self):
        """Applique la palette selectionnee sur les champs couleur, puis valide.
        Applies the selected palette to the color fields, then validates."""

        # On saute la validation de ProductAdminCustomForm (pas de tarif obligatoire)
        # / Skip ProductAdminCustomForm validation (no mandatory price)
        cleaned = super(ProductAdminCustomForm, self).clean()

        # Decodage de la palette : si une palette est choisie, elle ecrase les couleurs
        # / Decode palette: if a palette is chosen, it overrides the color fields
        palette_key = cleaned.get("palette_pos")
        if palette_key and palette_key in PALETTE_POS_MAP:
            text_hex, bg_hex = PALETTE_POS_MAP[palette_key]
            cleaned["couleur_texte_pos"] = text_hex
            cleaned["couleur_fond_pos"] = bg_hex

        return cleaned
```

- [ ] **Step 3 : Ajouter FutPriceInline**

Juste apres `FutProductForm` :

```python
class FutPriceInline(BasePriceInline):
    """Inline tarifs pour les produits fut.
    Ajoute contenance (volume par vente) et poids_mesure (vente au poids/volume).
    Champs conditionnels : contenance cache si poids_mesure coche.
    / Price inline for keg products.
    Adds contenance (volume per sale) and poids_mesure (weight/volume sales).
    Conditional fields: contenance hidden if poids_mesure checked.
    LOCALISATION : Administration/admin/products.py"""

    fields = ("name", "prix", "poids_mesure", "contenance", ("publish", "order"))

    # Champs conditionnels : contenance cache si poids_mesure coche
    # (la quantite est saisie a chaque vente, pas fixe).
    # / Conditional fields: contenance hidden if poids_mesure checked
    # (quantity is entered at each sale, not fixed).
    inline_conditional_fields = {
        "contenance": "poids_mesure == false",
    }

    class Media:
        js = ("admin/js/inline_conditional_fields.js",)
```

- [ ] **Step 4 : Ajouter FutProductAdmin**

Juste apres `FutPriceInline` :

```python
@admin.register(FutProduct, site=staff_admin_site)
class FutProductAdmin(ProductAdmin):
    """Vue admin filtree : uniquement les produits de type fut (tireuses).
    Filtered admin view: only keg products (connected taps).
    LOCALISATION : Administration/admin/products.py"""

    compressed_fields = True
    warn_unsaved_form = True
    form = FutProductForm
    inlines = [FutPriceInline]
    change_form_after_template = "admin/product/inline_conditional_fields.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        # Collecte les regles conditionnelles de chaque inline qui en declare
        # / Collect conditional rules from each inline that declares them
        extra_context = extra_context or {}
        regles_conditionnelles = {}
        for inline_class in self.get_inlines(request, None):
            regles_inline = getattr(inline_class, "inline_conditional_fields", None)
            if regles_inline:
                prefixe = inline_class.model._meta.model_name + "s"
                regles_conditionnelles[prefixe] = regles_inline
        if regles_conditionnelles:
            extra_context["inline_conditional_rules"] = json.dumps(
                regles_conditionnelles
            )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_related(self, request, form, formsets, change):
        """Apres sauvegarde des inlines : si un tarif a poids_mesure=True
        et que le produit n'a pas de Stock, en creer un vide en centilitres.
        Si le Stock existe mais est en unite UN (pieces), avertir.
        / After saving inlines: if a price has poids_mesure=True
        and the product has no Stock, create an empty one in centiliters.
        If Stock exists but uses UN (pieces), warn."""
        super().save_related(request, form, formsets, change)
        produit = form.instance

        # Verifier si un tarif poids_mesure existe pour ce produit
        # / Check if a weight-based price exists for this product
        a_tarif_poids = produit.prices.filter(poids_mesure=True).exists()
        if not a_tarif_poids:
            return

        # Verifier si le produit a deja un Stock
        # / Check if the product already has a Stock
        from inventaire.models import Stock, UniteStock

        try:
            stock_existant = produit.stock_inventaire
            # Verifier que l'unite n'est pas UN (pieces)
            # / Check that the unit is not UN (pieces)
            if stock_existant.unite == UniteStock.UN:
                messages.warning(
                    request,
                    _(
                        "Warning: the stock unit is 'Pieces' (UN). "
                        "Weight/volume sales require grams (GR) or centiliters (CL). "
                        "Please change the unit in the stock settings."
                    ),
                )
        except Exception:
            # Pas de stock → en creer un vide en centilitres (futs = liquides)
            # / No stock → create an empty one in centiliters (kegs = liquids)
            Stock.objects.create(
                product=produit,
                quantite=0,
                unite=UniteStock.CL,
                seuil_alerte=0,
                autoriser_vente_hors_stock=True,
            )
            messages.info(
                request,
                _(
                    "Stock automatically created in centiliters (quantity=0). "
                    "Remember to add stock via a reception."
                ),
            )

    fieldsets = (
        (
            _("General"),
            {
                "fields": (
                    "name",
                    "categorie_article",
                    "short_description",
                    "long_description",
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
                ),
            },
        ),
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
        "short_description",
        "publish",
    )

    list_filter = ["publish"]
    search_fields = ["name"]

    def get_inlines(self, request, obj):
        # En mode add (pas d'obj) : StockInline pour creer le stock initial
        # En mode change : pas de StockInline (le stock se gere via admin/inventaire/stock/)
        # / In add mode: StockInline for initial stock creation
        # In change mode: no StockInline (stock managed via admin/inventaire/stock/)
        if obj is None:
            from Administration.admin.inventaire import StockInline

            return [StockInline, FutPriceInline]
        return [FutPriceInline]

    def get_queryset(self, request):
        # Uniquement les produits de type FUT
        # / Only keg products
        qs = super().get_queryset(request)
        return qs.filter(categorie_article=Product.FUT)
```

- [ ] **Step 5 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues.`

---

### Tache 5 : Sidebar — entree "Produits fut" dans la section Tireuses

**Fichiers :**
- Modifier : `Administration/admin/dashboard.py:341-420`

- [ ] **Step 1 : Ajouter l'entree "Produits fut" en 2e position dans la section Tireuses**

Dans `Administration/admin/dashboard.py`, dans le bloc `if configuration.module_tireuse:` (ligne 341),
ajouter un item apres le premier ("Taps", ligne 348-355) :

```python
                    {
                        "title": _("Keg products"),
                        "icon": "sports_bar",
                        "link": reverse_lazy(
                            "staff_admin:BaseBillet_futproduct_changelist"
                        ),
                        "permission": admin_permission,
                    },
```

Inserer entre l'item "Taps" (ligne 348-355) et l'item "Flow meters" (ligne 356-363).

- [ ] **Step 2 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues.`

---

### Tache 6 : Traductions FR/EN

**Fichiers :**
- Modifier : `locale/fr/LC_MESSAGES/django.po`
- Modifier : `locale/en/LC_MESSAGES/django.po`

- [ ] **Step 1 : Extraire les nouvelles chaines**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

- [ ] **Step 2 : Remplir les traductions FR**

Ouvrir `locale/fr/LC_MESSAGES/django.po` et remplir les `msgstr` pour les nouvelles chaines :

| msgid (EN) | msgstr (FR) |
|-----------|-------------|
| `"Initial stock quantity (in stock unit). After creation, modify via Inventory > Stock movements."` | `"Quantite initiale du stock (dans l'unite du stock). Apres creation, modifier via Inventaire > Mouvements de stock."` |
| `"If checked, the cashier enters the weight or volume at each sale. The price is per kg (grams) or per liter (centiliters). Stock is decremented by the exact quantity entered."` | `"Si coche, le caissier saisit le poids ou le volume a chaque vente. Le prix est au kg (grammes) ou au litre (centilitres). Le stock est decremente de la quantite exacte saisie."` |
| `"Stock quantity consumed per unit sold (in stock unit). Use this when selling by unit but decrementing stock by weight/volume. E.g.: pint=50 (cl), half=25 (cl), portion=150 (g). Empty = 1 unit. Incompatible with 'Sale by weight/volume' (where the cashier enters the exact quantity)."` | `"Quantite de stock consommee par unite vendue (dans l'unite du stock). Utilisez ce champ quand on vend a l'unite mais qu'on decremente le stock en poids/volume. Ex : pinte=50 (cl), demi=25 (cl), portion=150 (g). Vide = 1 unite. Incompatible avec 'Vente au poids/volume' (ou le caissier saisit la quantite exacte)."` |
| `"Stock automatically created in centiliters (quantity=0). Remember to add stock via a reception."` | `"Stock cree automatiquement en centilitres (quantite=0). Pensez a ajouter du stock via une reception."` |
| `"Keg products"` | `"Produits fut"` |
| `"Keg (connected tap)"` | `"Fut (tireuse connectee)"` |

Verifier aussi les `msgstr` existants modifies (ancien help_text poids_mesure/contenance) et supprimer les flags `#, fuzzy` si presents.

- [ ] **Step 3 : Compiler les traductions**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

---

### Tache 7 : Verification manuelle

- [ ] **Step 1 : Lancer le serveur**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

- [ ] **Step 2 : Verifier FutProductAdmin**

Naviguer vers `https://lespass.tibillet.localhost/admin/BaseBillet/futproduct/add/` :
- Le formulaire affiche les champs : name, short_description, long_description, palette, couleurs, icone, img, publish, archive
- Le StockInline apparait avec le bouton "Ajouter" (extra=0, max_num=1)
- La quantite est editable dans le StockInline
- L'inline Price affiche les champs : name, prix, poids_mesure, contenance, publish, order
- La contenance se cache quand poids_mesure est coche

- [ ] **Step 3 : Verifier StockAdmin**

Naviguer vers un Stock existant (`/admin/inventaire/stock/<uuid>/change/`) :
- L'unite est modifiable (pas readonly)
- La quantite reste readonly

- [ ] **Step 4 : Verifier la sidebar**

Dans la section "Tireuses" de la sidebar :
- L'entree "Produits fut" apparait avec l'icone sports_bar
- Elle mene vers la changelist FutProduct

- [ ] **Step 5 : Verifier le PointDeVente**

Naviguer vers un PointDeVente existant :
- Les FutProducts crees apparaissent dans le filter_horizontal "Products"
