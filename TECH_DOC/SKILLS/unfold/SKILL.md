---
name: unfold
description: >
  Guide de référence opérationnel pour créer et modifier des vues admin Django
  Unfold dans le projet Lespass. Utiliser ce skill dès qu'on touche à
  Administration/admin_tenant.py, qu'on crée un ModelAdmin, une inline, une
  action, un filtre, une section, un composant, un template before/after, ou
  qu'on configure la sidebar. Déclencher aussi pour : "ajoute un admin", "crée
  une vue admin", "modifie l'affichage dans l'admin", "ajoute une action", "filtre
  custom", "section dans l'admin", "widget Unfold", "conditional_fields",
  "dashboard module". Ne pas attendre que l'utilisateur cite explicitement
  "Unfold" — appliquer ce skill pour tout travail dans Administration/.
---

# Skill : Django Unfold Admin — Lespass

Guide de référence opérationnel. Patterns réellement utilisés dans le projet,
avec exemples tirés du code.

Fichier principal : `Administration/admin_tenant.py` (~5900 lignes)
Doc officielle locale : `Administration/Unfold_docs/django-unfold/docs/`
Projet exemple : `Administration/Unfold_docs/formula/`

---

## 1. Setup du site admin custom

```python
# admin_tenant.py
from unfold.sites import UnfoldAdminSite

class StaffAdminSite(UnfoldAdminSite):
    ...

staff_admin_site = StaffAdminSite(name="staff_admin")

# Toujours enregistrer sur ce site
@admin.register(MyModel, site=staff_admin_site)
class MyModelAdmin(ModelAdmin):
    ...
```

**Permissions** — les 4 methodes sont **OBLIGATOIRES** sur chaque ModelAdmin.
Sans override, Django tombe sur son systeme de permissions par defaut (`user.has_perm()`)
qui ne correspond pas au modele du projet. Toujours utiliser `TenantAdminPermissionWithRequest` :

```python
def has_view_permission(self, request, obj=None):
    return TenantAdminPermissionWithRequest(request)

def has_add_permission(self, request):
    return TenantAdminPermissionWithRequest(request)

def has_change_permission(self, request, obj=None):
    return TenantAdminPermissionWithRequest(request)

def has_delete_permission(self, request, obj=None):
    return TenantAdminPermissionWithRequest(request)
```

Adapter selon le contexte : `return False` pour les singletons (add), les documents
immuables (change, delete), les donnees en lecture seule (add, change, delete).

---

## 2. Patron standard d'un ModelAdmin

```python
from unfold.admin import ModelAdmin, TabularInline  # PAS les imports Django standard

@admin.register(MyModel, site=staff_admin_site)
class MyModelAdmin(ModelAdmin):
    compressed_fields = True    # TOUJOURS
    warn_unsaved_form = True    # TOUJOURS

    list_display = ["field_a", "field_b", "display_status"]
    list_filter = ["field_a", MyCustomFilter]
    search_fields = ["field_a", "field_b"]

    fieldsets = (
        (_("Section title"), {
            "fields": ("field_a", "field_b"),
            "classes": ("tab",),   # Optionnel : affiche dans un onglet
        }),
    )

    def save_model(self, request, obj, form, change):
        sanitize_textfields(obj)   # Si TextField / WysiwygWidget
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
```

---

## 3. Widgets Unfold disponibles

Déclarés via `formfield_overrides` ou directement dans le formulaire :

```python
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.widgets import (
    UnfoldAdminColorInputWidget,
    UnfoldAdminTextInputWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminCheckboxSelectMultiple,
    UnfoldBooleanSwitchWidget,
    UnfoldAdminRadioSelectWidget,
    UnfoldAdminEmailInputWidget,
)

class MyModelAdmin(ModelAdmin):
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }
```

`UnfoldAdminTextInputWidget` accepte `prefix_icon` et `suffix_icon` (Material Symbols).

---

## 4. Templates before/after

```python
class MyModelAdmin(ModelAdmin):
    list_before_template = "admin/mymodel/list_before.html"        # Avant la liste
    change_form_before_template = "admin/mymodel/form_before.html" # Dans le formulaire, avant les champs
    change_form_after_template = "admin/mymodel/form_after.html"   # Après le formulaire
```

Dossier : `Administration/templates/admin/<model_name>/`

Dans les templates : toujours `{% load unfold %}` en tête.

Exemples réels : `CheckStripe` (list_before), wallet info (change_form_after),
custom form answers (change_form_after dans `ReservationAdmin`).

---

## 5. Sections (list_sections)

Blocs supplémentaires affichés sous la fiche de détail.

```python
from unfold.sections import TableSection, TemplateSection

class MyTableSection(TableSection):
    related_name = "related_set"   # Nom du related_manager sur l'objet
    fields = ["field_a", "field_b", "custom_method"]
    height = 240

    def custom_method(self, instance):
        return instance.some_value

class MyTemplateSection(TemplateSection):
    template_name = "admin/mymodel/section.html"

class MyModelAdmin(ModelAdmin):
    list_sections = [MyTableSection, MyTemplateSection]
    list_sections_classes = "lg:grid-cols-2"   # Layout CSS des sections
```

Exemples réels : `EventPricesSummaryTable`, `MembershipCustomFormSection`.

---

## 6. Composants (@register_component)

Pour des blocs réutilisables injectés dans les templates before/after.

```python
from unfold.components import BaseComponent, register_component
from django.template.loader import render_to_string

@register_component
class MyComponent(BaseComponent):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["children"] = render_to_string(
            "admin/mymodel/component.html",
            {"data": ...},
        )
        return context
```

Dans le template before :
```html
{% load unfold %}
{% component "unfold/components/card.html" %}
    {% component "unfold/components/title.html" with component_class="MyComponent" %}{% endcomponent %}
{% endcomponent %}
```

Exemples réels : `CheckStripeComponent`, `MembershipComponent`.

---

## 7. Actions (@action)

4 emplacements : `actions_list`, `actions_row`, `actions_detail`, `actions_submit_line`.

```python
from unfold.decorators import action

class MyModelAdmin(ModelAdmin):
    actions_row = ["my_action"]

    @action(
        description=_("My Action"),
        url_path="my-action",
        permissions=["my_action"],
    )
    def my_action(self, request, object_id):
        obj = get_object_or_404(MyModel, pk=object_id)
        # ... logique ...
        return redirect(request.META["HTTP_REFERER"])

    def has_my_action_permission(self, request, object_id=None):
        return TenantAdminPermissionWithRequest(request)
```

**Signatures selon l'emplacement :**
- `actions_list` → `(self, request)`
- `actions_row` / `actions_detail` → `(self, request, object_id)`
- `actions_submit_line` → `(self, request, obj)` (instance déjà sauvegardée)

---

## 8. @display decorator

```python
from unfold.decorators import display

@display(
    description=_("Status"),
    label={"ACTIVE": "success", "INACTIVE": "danger", "PENDING": "warning"},
)
def display_status(self, obj):
    return obj.status

@display(description=_("Valid"), boolean=True)
def is_valid(self, obj):
    return obj.deadline >= timezone.now().date()

@display(description=_("Header"), header=True)
def display_header(self, obj):
    # Retourne [titre, sous-titre, initiales, image_url_ou_None]
    return [obj.name, obj.email, "AB", None]
```

Variants de label : `"success"`, `"danger"`, `"warning"`, `"info"`, `"primary"`.

---

## 9. Inlines (TabularInline Unfold)

```python
from unfold.admin import TabularInline

class MyInline(TabularInline):
    model = MyRelatedModel
    fk_name = "parent"
    extra = 0
    show_change_link = True
    ordering_field = "order"     # Active le drag-and-drop
    hide_ordering_field = True   # Cache le champ order dans l'interface
    tab = True                   # Affiche dans un onglet séparé

    def has_delete_permission(self, request, obj=None):
        return False
```

---

## 10. Formulaires : add vs change

```python
class MyModelAdmin(ModelAdmin):
    form = MyChangeForm     # Formulaire pour modifier un objet existant
    add_form = MyAddForm    # Formulaire pour créer un nouvel objet

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            return self.add_form
        return super().get_form(request, obj, **kwargs)
```

Exemples réels : `MembershipAdmin`, `GhostConfigAdmin`, `ReservationAdmin`.

---

## 11. Formulaires proxy (TicketProduct, MembershipProduct, POSProduct)

Pattern : hériter de `ProductAdminCustomForm`, cacher/restreindre `categorie_article`.

```python
class MembershipProductForm(ProductAdminCustomForm):
    class Meta(ProductAdminCustomForm.Meta):
        model = MembershipProduct

    categorie_article = forms.ChoiceField(
        choices=[(Product.ADHESION, _("Membership"))],
        widget=forms.HiddenInput(),
        initial=Product.ADHESION,
    )
```

---

## 12. Filtres custom (SimpleListFilter)

```python
class MyFilter(admin.SimpleListFilter):
    title = _("My filter")
    parameter_name = "my_param"

    def lookups(self, request, model_admin):
        return [("yes", _("Yes")), ("no", _("No"))]

    def queryset(self, request, queryset):
        if self.value() is None:       # Comportement par défaut (aucun filtre sélectionné)
            return queryset.filter(active=True)
        if self.value() == "yes":
            return queryset.filter(some_field=True)
        return queryset.filter(some_field=False)
```

Exemples réels : `ProductArchiveFilter`, `MembershipStatusFilter`, `EventFutureFilter`.

---

## 13. URLs custom + vues HTMX

```python
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

class MyModelAdmin(ModelAdmin):
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "my-view/",
                self.admin_site.admin_view(self.my_view),
                name="myapp_mymodel_my_view",
            ),
            path(
                "my-post/",
                self.admin_site.admin_view(
                    csrf_protect(require_POST(self.my_post_view))
                ),
                name="myapp_mymodel_my_post",
            ),
        ]
        return custom_urls + urls

    def my_post_view(self, request):
        # ... logique ...
        response = HttpResponse("")
        response["HX-Refresh"] = "true"   # Force reload de la page Unfold
        return response
```

Exemple réel : `module_toggle_modal` + `module_toggle` dans `ConfigurationAdmin`.

---

## 14. conditional_fields

Affiche/cache des champs selon la valeur d'un autre champ (Alpine.js).

```python
class MyModelAdmin(ModelAdmin):
    conditional_fields = {
        "iteration": "recurring_payment == true",  # Expression Alpine.js
        "commitment": "iteration > 0",
    }
```

Exemple réel : `PriceAdmin`.

---

## 15. Import/Export

```python
from import_export.admin import ImportExportModelAdmin
from unfold.contrib.import_export.forms import ExportForm, ImportForm

class MyModelAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_classes = [MyExportResource]
    export_form_class = ExportForm
    import_form_class = ImportForm
```

---

## 16. Sidebar navigation (get_sidebar_navigation)

Fonction `get_sidebar_navigation(request)` définie dans `admin_tenant.py`.
Référencée dans `settings.py` :
```python
"navigation": "Administration.admin_tenant.get_sidebar_navigation"
```

Pattern conditionnel module :
```python
def get_sidebar_navigation(request):
    config = Configuration.get_solo()
    items = []
    if config.module_adhesion:
        items.append({
            "title": _("Memberships"),
            "icon": "card_membership",
            "link": reverse_lazy("staff_admin:basebillet_membershipproduct_changelist"),
        })
    return [{"title": _("Section"), "items": items}]
```

---

## 17. MODULE_FIELDS + Dashboard modules

```python
MODULE_FIELDS = {
    "module_billetterie": {"name": _("Event ticketing"), "icon": "confirmation_number"},
    "module_adhesion":    {"name": _("Memberships"),     "icon": "card_membership"},
    "module_caisse":      {"name": _("POS / Cashless"),  "icon": "point_of_sale"},
    ...
}
```

- `dashboard_callback(request, context)` → injecte les modules dans le contexte
- `ConfigurationAdmin.module_toggle()` → bascule un module via HTMX POST (whitelist `field_name`)
- Template dashboard : `Administration/templates/admin/dashboard.html`
- Template modal : `Administration/templates/admin/dashboard_module_modal.html`

---

## 18. Patterns avancés fréquents

### SingletonModelAdmin
```python
from solo.admin import SingletonModelAdmin

@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    # ... fieldsets, formfield_overrides, etc.
```
→ Exemples réels : `ConfigurationAdmin`, `BrevoConfigAdmin`, `CrowdConfigAdmin`.

### Injecter du contexte dans changeform_view / changelist_view
```python
def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
    extra_context = extra_context or {}
    extra_context["object_id"] = object_id
    if object_id:
        obj = MyModel.objects.get(pk=object_id)
        extra_context["some_data"] = compute_data(obj)
    return super().changeform_view(request, object_id, form_url, extra_context)

def changelist_view(self, request, extra_context=None):
    extra_context = extra_context or {}
    extra_context["invitations"] = MyModel.objects.filter(pending=True)
    return super().changelist_view(request, extra_context=extra_context)
```
→ Exemples réels : `HumanUserAdmin`, `AssetAdmin`.

### Rediriger après sauvegarde (response_change)
```python
def response_change(self, request, obj):
    self.message_user(request, _("Saved."), messages.SUCCESS)
    return redirect(reverse("staff_admin:myapp_parent_change", args=[obj.parent.pk]))
```
→ Exemple réel : `PriceAdmin` redirige vers le produit parent.

### Piège M2M — save_related (CRITIQUE)
Ne jamais faire `obj.m2m.add()` dans `save_model()` — Django l'écrase ensuite.
Utiliser `save_related()` APRÈS `super()` :
```python
def save_related(self, request, form, formsets, change):
    super().save_related(request, form, formsets, change)
    obj = form.instance
    # Ajouter/protéger des M2M ICI, après le super()
    obj.m2m_field.add(some_obj)
```
→ Exemple réel : `AssetAdmin.save_related` (protection pending_invitations), `FederationAdmin.save_related` (ajout créateur).

### get_readonly_fields / get_fields dynamiques
```python
def get_readonly_fields(self, request, obj=None):
    ro = list(super().get_readonly_fields(request, obj))
    if obj is not None:   # mode change (pas add)
        ro += ["name", "currency_code"]
    return ro

def get_fields(self, request, obj=None):
    fields = list(super().get_fields(request, obj))
    if obj and not is_origin(obj):
        fields.remove("pending_invitations")
    return fields
```
→ Exemple réel : `AssetAdmin` (champs en readonly après création).

### raw_id_fields — éviter les gros selects
```python
class ContributionInline(TabularInline):
    raw_id_fields = ("contributor",)   # Saisie par ID, pas de select 200k users
```
→ Utiliser pour les FK vers `TibilletUser` ou toute table avec >1000 entrées.

### re_path dans get_urls (pour les UUIDs)
```python
from django.urls import re_path

def get_urls(self):
    urls = super().get_urls()
    custom_urls = [
        re_path(
            r'^accept_invitation/(?P<asset_pk>.+)/$',
            self.admin_site.admin_view(csrf_protect(require_POST(self.accept_invitation))),
            name='myapp-accept-invitation',
        ),
    ]
    return custom_urls + urls
```
→ Exemple réel : `AssetAdmin` (UUIDs dans les URLs).

### HttpResponseClientRedirect (django-htmx)
```python
from django_htmx.http import HttpResponseClientRedirect

def my_post_view(self, request):
    # ... logique ...
    return HttpResponseClientRedirect(request.META["HTTP_REFERER"])
    # Alternative : HttpResponse("") avec response["HX-Refresh"] = "true"
```
- `HttpResponseClientRedirect(url)` : redirige vers une URL spécifique (HTMX)
- `HX-Refresh: true` : force un reload complet de la page courante

### RootPermissionWithRequest
En plus de `TenantAdminPermissionWithRequest`, il existe `RootPermissionWithRequest`
pour les sections réservées aux super-admins (tenants root) :
```python
from ApiBillet.permissions import RootPermissionWithRequest

def has_view_permission(self, request, obj=None):
    return RootPermissionWithRequest(request)
```
→ Utilisé pour `WaitingConfiguration`, `Client`, et `login_as_user`.

---

## 19. Sidebar — structure complète d'un item

```python
{
    "title": _("Mon titre"),
    "icon": "dashboard",                            # Material Symbols
    "link": reverse_lazy("staff_admin:app_model_changelist"),
    "permission": "ApiBillet.permissions.TenantAdminPermissionWithRequest",  # STRING importable
    "badge": "Administration.admin_tenant.my_badge_callback",  # STRING importable, optionnel
}
```

Structure d'une **section** :
```python
{
    "title": _("Ma section"),
    "separator": True,       # Ligne séparatrice au-dessus
    "collapsible": True,     # Permettre de replier
    "items": [...],
}
```

Badge callback (retourne une string) :
```python
def adhesion_badge_callback(request):
    count = Membership.objects.filter(last_contribution__gte=timezone.localtime() - timedelta(days=7)).count()
    return f"+ {count}"
```

`environment_callback` dans settings.py :
```python
def environment_callback(request):
    if settings.DEBUG:
        return [_("Development"), "primary"]
    return [_("Production"), "primary"]
```

---

## 20. Autocomplete

**Prérequis** : le ModelAdmin cible doit avoir `search_fields` défini.

```python
# Sur le ModelAdmin cible (doit avoir search_fields)
@admin.register(Product, site=staff_admin_site)
class ProductAdmin(ModelAdmin):
    search_fields = ['name']   # REQUIS pour que autocomplete_fields fonctionne

# Sur le ModelAdmin qui utilise l'autocomplete
class EventAdmin(ModelAdmin):
    autocomplete_fields = ['products']
```

**Filtrer les résultats selon le contexte (referer)** — `get_search_results` :
```python
def get_search_results(self, request, queryset, search_term):
    queryset, use_distinct = super().get_search_results(request, queryset, search_term)
    if "admin/autocomplete" in request.path:
        referer = request.headers.get('Referer', '')
        if "event" in referer:
            queryset = queryset.filter(categorie_article__in=[Product.BILLET, Product.FREERES])
        elif "price" in referer:
            queryset = queryset.filter(categorie_article=Product.ADHESION, archive=False)
    return queryset, use_distinct
```
→ Exemple réel : `ProductAdmin.get_search_results`.

**Unfold utilise Tom Select** (pas select2). Sélecteurs Playwright :
```typescript
await page.getByRole('searchbox').fill('mon terme');
await page.getByRole('option', { name: /Mon Option/ }).click();
```

---

## 21. Code FALC — Facile À Lire et Comprendre

Ce projet est un **commun numérique coopératif**. Le code doit être lisible par des développeurs non-experts. Voir aussi le skill `stack-ccc` pour les règles générales.

### Règles dans admin_tenant.py

**Commentaires bilingues FR + résumé EN sur une ligne :**
```python
# Récupération du produit original depuis la base de données
# Retrieve the original product from the database
produit_original = get_object_or_404(Product, pk=object_id)

# On parcourt tous les tarifs associés au produit source
# Loop through all prices associated with the source product
for tarif_original in produit_source.prices.all():
```

**Noms de variables explicites, pas de raccourcis :**
```python
# Bien :
produit_duplique = self._duplicate_product(produit_original)
tarif_original = Price.objects.get(pk=tarif_source.pk)

# Pas bien :
d = self._dup(p)
t = Price.objects.get(pk=ts.pk)
```

**Pas de sur-ingénierie :**
- Pas de méthode helper pour une opération utilisée une seule fois
- Pas d'abstraction "au cas où"
- 3 lignes similaires > 1 abstraction prématurée
- Si le plan ne le mentionne pas, ne pas le faire

**`help_text` avec `_()`** sur tous les champs de formulaire non évidents :
```python
price = forms.ModelChoiceField(
    queryset=Price.objects.filter(...),
    help_text=_("Si un déclencheur de tokens est configuré sur le tarif, il sera activé à l'enregistrement."),
)
```

**Logs en français, strings user-facing avec `_()`** :
```python
logger.info(f"Asset créé chez fedow {asset} : {created}")   # FR, pas traduit
messages.success(request, _("Asset créé avec succès."))      # traduit
```

---

## 22. Conventions projet — non négociables

| Règle | Détail |
|-------|--------|
| Import ModelAdmin | `from unfold.admin import ModelAdmin, TabularInline` (jamais Django standard) |
| Permissions | Les 4 `has_*_permission` OBLIGATOIRES sur chaque ModelAdmin. `TenantAdminPermissionWithRequest(request)` partout |
| Save model | `sanitize_textfields(obj)` si TextField/WysiwygWidget |
| Git | Jamais de `git commit` depuis Claude Code |
| Icônes | Material Symbols (ex: `"dashboard"`, `"people"`, `"edit"`) |
| Variants badge | `"success"`, `"danger"`, `"warning"`, `"info"`, `"primary"` |
| `compressed_fields` | `True` sur tous les ModelAdmin |
| `warn_unsaved_form` | `True` sur tous les ModelAdmin |
| Commentaires | FR + résumé EN une ligne (FALC) |
| Variables | Noms explicites, pas de raccourcis |

---

## 23. Piège critique : Unfold wrappe TOUTES les méthodes d'un ModelAdmin

**Unfold scanne toutes les méthodes** de la classe admin via son décorateur `@action`.
Toute méthode définie dans la classe — même un simple helper privé comme `_euros()` ou
`_ecrire_rapport()` — peut être wrappée par le système d'actions d'Unfold si elle se
trouve à proximité d'un `@action` ou si le cache de méthodes est mal résolu.

### Symptômes

- `AttributeError: 'int' object has no attribute 'user'` — Unfold passe `object_id` ou
  une valeur métier au lieu de `request` comme premier argument.
- `'ClotureCaisseAdmin' object has no attribute 'has_custom_actions_row_permission'` — Unfold
  cherche une permission method pour un helper qui n'est pas une action.
- `TypeError: action.<locals>.decorator.<locals>.inner() missing 1 required positional argument: 'request'`
  — un helper est appelé mais Unfold intercepte l'appel.

### Solution : sortir les helpers de la classe

Les fonctions utilitaires (conversion centimes→euros, écriture rapport structuré, etc.)
doivent être définies **HORS de la classe ModelAdmin**, au niveau du module :

```python
# BON — helper au niveau module, Unfold ne le touche pas
def _euros(centimes):
    if centimes is None:
        return 0.0
    return round(centimes / 100, 2)

def _ecrire_rapport_csv_excel(writer, cloture, rapport):
    e = _euros
    # ... logique d'export ...

@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    def exporter_csv(self, request, object_id):
        # Appeler le helper module-level
        _ecrire_rapport_csv_excel(CsvWriterAdapter(), cloture, rapport)
```

```python
# MAUVAIS — helper dans la classe, Unfold le wrappe
class ClotureCaisseAdmin(ModelAdmin):
    def _euros(self, centimes):  # ← Unfold va intercepter cet appel
        return round(centimes / 100, 2)
```

### Autre piège : `@admin.register` s'applique sur la première définition qui suit

Si une fonction module-level est définie **entre** `@admin.register(Model, site=...)` et
`class MonAdmin(ModelAdmin):`, le décorateur s'applique sur la fonction au lieu de la classe.

```python
# MAUVAIS — @admin.register décore _euros au lieu de MonAdmin
@admin.register(MyModel, site=staff_admin_site)

def _euros(centimes):  # ← C'est cette fonction qui reçoit le décorateur !
    return round(centimes / 100, 2)

class MonAdmin(ModelAdmin):  # ← Jamais enregistré !
    ...

# BON — helpers AVANT le décorateur, classe JUSTE APRÈS
def _euros(centimes):
    return round(centimes / 100, 2)

@admin.register(MyModel, site=staff_admin_site)
class MonAdmin(ModelAdmin):
    ...
```

### Vue détail custom : `change_form_before_template` + `fieldsets = ()`

Pour remplacer le formulaire standard par une vue custom (rapport, dashboard, etc.) :

```python
@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    fieldsets = ()  # Vide — tout est dans le template before
    change_form_before_template = "admin/cloture/rapport_before.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            obj = get_object_or_404(ClotureCaisse, pk=object_id)
            extra_context["rapport"] = calculer_rapport(obj)
        return super().changeform_view(request, object_id, form_url, extra_context)
```

Le template `rapport_before.html` doit cacher les fieldsets Unfold résiduels :
```html
{% load i18n %}
<style>
    .aligned, fieldset.module, .submit-row { display: none !important; }
</style>
<!-- Contenu du rapport ici -->
```

### Exports sans `actions_row` : utiliser `get_urls()`

Les `actions_row` d'Unfold ont des problèmes de permission (`has_custom_actions_row_permission`
reçoit parfois `object_id` au lieu de `request`). Pour les exports (CSV, PDF, Excel),
utiliser `get_urls()` + boutons dans le template :

```python
def get_urls(self):
    from django.urls import path
    urls = super().get_urls()
    custom_urls = [
        path('<path:object_id>/exporter-csv/',
             self.admin_site.admin_view(self.exporter_csv),
             name='myapp_mymodel_exporter_csv'),
    ]
    return custom_urls + urls

def exporter_csv(self, request, object_id):
    # ... logique d'export (pas de @action) ...
```

Template (URLs relatives depuis `/change/`) :
```html
<a href="../exporter-csv/">CSV</a>
<a href="../exporter-pdf/">PDF</a>
```