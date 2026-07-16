# v1.8 — Modules Groupware + refacto admin + proxies Product / Groupware modules + admin refactor + Product proxies

**Date :** 2026-05-13
**Migration :** Oui (`0204_configuration_module_adhesion_and_more`, `0205_futproduct_membershipproduct_posproduct_and_more`)
**Contributeurs / Contributors :** NothRen (Antoine), JonasFW13 (Jonas)

---

### Vue d'ensemble / Overview

**FR :**
Premiere etape d'integration de la V2 (mono-repo TiBillet/Lespass + LaBoutik + Fedow)
dans la V1 actuelle. On introduit la notion de **Groupware** (activation modulaire par
tenant) et on prepare l'admin pour accueillir les nouveaux types de produits (POS, fut)
sans casser la compatibilite. Refacto majeur de `admin_tenant.py` (~1000 lignes
deplacees) en modules separes. Ajout de proxy models pour separer les vues admin par
type de produit. Fix bug timezone sur les filtres datetime de l'admin (#384).

**EN :**
First step of integrating the V2 mono-repo (TiBillet/Lespass + LaBoutik + Fedow)
into the current V1. Introduces the **Groupware** concept (per-tenant modular activation)
and prepares admin for upcoming product types (POS, keg) without breaking compatibility.
Major refactor of `admin_tenant.py` (~1000 lines moved) into separate modules. Adds proxy
models to split admin views by product type. Fixes timezone bug on admin datetime filters (#384).

---

### 1. Modules Groupware : activation par tenant / Groupware modules: per-tenant activation

**FR :**
Ajout de **9 booleens** `module_*` sur `Configuration` pour activer/desactiver des
sections fonctionnelles par tenant. Les modules deja en production sont actives par
defaut (`module_billetterie`, `module_adhesion`, `module_crowdfunding`,
`module_federation`). Les modules V2 a venir sont desactives par defaut
(`module_monnaie_locale`, `module_caisse`, `module_inventaire`, `module_tireuse`,
`module_booking`).

**Dashboard admin** : nouvelles cartes avec switches HTMX et modal de confirmation.
Apres bascule, `HX-Refresh` recharge la page pour mettre a jour la sidebar.
**Sidebar dynamique** : `get_sidebar_navigation(request)` (callable string) construit
la navigation selon les modules actifs.
**NavBar publique** : les liens `/memberships/`, `/event/`, `/federation/`, `/contrib/`
n'apparaissent dans la barre publique que si le module correspondant est actif (cf.
`BaseBillet/views.py:get_context()`).

**Dependance** : `module_caisse` necessite `module_monnaie_locale`. Validation cote
serveur dans `module_toggle()` qui renvoie un message d'erreur via `django.messages` si
on tente de violer cette regle.

**EN :**
Adds **9 module_* booleans** on `Configuration` to enable/disable functional sections
per tenant. Currently-live modules default to True; upcoming V2 modules default to False.
Admin dashboard gets module cards with HTMX switches and a confirmation modal.
Sidebar is now dynamic (`get_sidebar_navigation` callable). Public navbar links only
show if the matching module is active. `module_caisse` requires `module_monnaie_locale`.

---

### 2. Refacto `admin_tenant.py` : split en modules / `admin_tenant.py` refactor: split into modules

**FR :**
`Administration/admin_tenant.py` faisait ~3000 lignes. On extrait :

- `Administration/admin/site.py` — `StaffAdminSite` + `sanitize_textfields` (utilitaire XSS).
- `Administration/admin/dashboard.py` — `get_sidebar_navigation`, `dashboard_callback`,
  `MODULE_FIELDS`, `_build_modules_context`, `adhesion_badge_callback`, `environment_callback`.
- `Administration/admin/products.py` — `ProductAdmin`, `TicketProductAdmin`,
  `MembershipProductAdmin`, inlines `BasePriceInline`/`TicketPriceInline`/`MembershipPriceInline`,
  `ProductFormFieldInline`, palettes/icones POS (commente, pour V2), validation.
- `Administration/admin/prices.py` — `PriceAdmin`, `PromotionalCodeAdmin`, `PriceChangeForm`.

`admin_tenant.py` re-exporte les noms publics (`get_sidebar_navigation`, etc.) via
`from Administration.admin.dashboard import ...` pour ne rien casser cote `settings.py`
qui pointe encore sur `Administration.admin_tenant.get_sidebar_navigation`.

**EN :**
Splits the ~3000-line `admin_tenant.py` into 4 modules under `Administration/admin/`.
Public names re-exported from the original module to keep `settings.py` references valid.

---

### 3. Proxy models Product : 4 vues admin filtrees / Product proxy models: 4 filtered admin views

**FR :**
Sans toucher a la table `BaseBillet_product`, on cree **4 proxy models** :
- `TicketProduct` — filtre `categorie_article IN ('B', 'F')` (Billet, FreeRes).
- `MembershipProduct` — filtre `categorie_article = 'A'` (Adhesion).
- `POSProduct` — filtre `methode_caisse IS NOT NULL` (V2, admin commente).
- `FutProduct` — filtre `categorie_article = 'U'` (V2, admin commente).

Chaque proxy a son propre `ModelAdmin` avec un formulaire restreint et un `get_queryset`
filtre. La sidebar affiche separement "Ticket products" (section Billetterie) et
"Membership products" (section Adhesions). Le `ProductAdmin` original reste enregistre
pour preserver les autocomplete `EventAdmin` et les URLs existantes.

`MembershipProductAdmin` recupere `ProductFormFieldInline` (formulaires dynamiques pour
adhesions). `TicketProductAdmin` ne l'a pas (champs dynamiques inutiles pour la billetterie).

**EN :**
Adds 4 proxy models filtered by product type. Each has its own admin with a restricted
form and filtered queryset. Original `ProductAdmin` is kept to preserve existing URLs
and autocomplete behavior in `EventAdmin`.

---

### 4. Champs conditionnels dans les inlines / Conditional fields in inlines

**FR :**
Unfold supporte `conditional_fields` au niveau ModelAdmin mais **pas** au niveau inline.
Pour le besoin "afficher `iteration` seulement si `recurring_payment` coche" sur l'inline
`MembershipPriceInline`, on ajoute un systeme generique :

- Chaque `Inline` declare un dict `inline_conditional_fields = {"champ": "expression"}`.
- `MembershipProductAdmin.changeform_view()` collecte ces dicts et les injecte en JSON
  via `extra_context["inline_conditional_rules"]`.
- Template `admin/product/inline_conditional_fields.html` rend le JSON dans
  `<script id="inline-conditional-rules" type="application/json">`.
- JS `Administration/static/admin/js/inline_conditional_fields.js` lit le JSON, ecoute
  les `change`/`input` sur les sources, applique cascade (source cachee = condition fausse),
  anime apparition/disparition, observe les nouvelles lignes inline (MutationObserver).

Expressions supportees : `champ == true`, `champ == false`, `champ > N`.

**EN :**
Generic conditional-field system for Django admin inlines (Unfold doesn't support
`conditional_fields` on inlines). Each inline declares `inline_conditional_fields`,
the changeform view collects them and injects JSON, JS reads the JSON, listens on
sources, handles cascade, animates show/hide, observes new inline rows.

---

### 5. Fix bug timezone sur les filtres datetime admin (#384) / Fix timezone bug on admin datetime filters (#384)

**FR :**
`RangeDateTimeFilter` (Unfold) parsait les bornes saisies dans le filtre admin sans
tenir compte de la timezone du tenant, ce qui entrainait des decalages d'une heure sur
les filtrages d'historique. Nouveau filtre `RangeDateTimeFilterWithTimeZone` qui :

1. Recupere la timezone du tenant via `Configuration.get_solo().get_tzinfo()`.
2. Localise les `datetime` parses avec `new_timezone.localize(...)` avant le filtrage.
3. Retourne `None` proprement en cas d'erreur de parsing.

Applique sur `LigneArticleAdmin` et `LigneArticlePosAdmin`.

**EN :**
Fixes one-hour offset in admin datetime range filters by localizing parsed datetimes
with the tenant's timezone (`Configuration.get_solo().get_tzinfo()`).

---

### 6. Fix divers / Miscellaneous fixes

**FR :**
- **Subscription duration** (commit 32e035e2, NothRen) : interdit la creation d'un
  `Price` avec `recurring_payment=True` mais `subscription_type=NA`. Validation cote
  serveur dans `MembershipPriceInlineForm.clean_subscription_type()`.
- **`SyntaxWarning: "is" with a literal`** (commit 5ddeb7ca, JonasFW13) : remplace
  `field_name is "module_caisse"` par `field_name == "module_caisse"` dans
  `module_toggle()`. Le `is` ne doit pas etre utilise pour comparer des strings.
- **`poids` → "Display order"** (commit 0cce7f1b, NothRen) : renomme le `verbose_name`
  pour clarifier le sens metier ("ordre d'affichage", plus petit = en premier). La colonne
  DB reste `poids`.
- **Doc technique V1-to-V2 + Stripe Checkout fix** (commit 1a3f2c0f, JonasFW13) :
  ajout de `TECH DOC/SESSIONS/M-To-V2/INDEX.md` et
  `Administration/Unfold_docs/stripe-checkout-account-business-name.md`.

**EN :**
- Subscription duration validation: `recurring_payment=True` requires `subscription_type != NA`.
- Replaces `is` with `==` for string comparison (PEP 8).
- Renames `poids` verbose_name to "Display order" for clarity.
- Adds technical migration docs.

---

### 7. NavBar publique conditionnelle / Conditional public navbar

**FR :**
Dans `BaseBillet/views.py:get_context()`, les liens publics `/memberships/`, `/event/`,
`/federation/` et `/contrib/` n'apparaissent dans `main_nav` que si le module correspondant
est actif. Avant : ces liens etaient toujours visibles, meme si la fonctionnalite etait
desactivee (404 a la cle).

**EN :**
Public navbar links are now conditional on the matching module flag.

---

### 8. `DATETIME_INPUT_FORMATS` ajoute aux settings / `DATETIME_INPUT_FORMATS` added to settings

**FR :**
Ajout de plusieurs formats de saisie datetime (FR `dd/mm/yyyy hh:mm`, ISO
`yyyy-mm-dd hh:mm:ss`, etc.) pour que les formulaires admin acceptent les variantes
courantes lors du parsing manuel des dates.

**EN :**
Adds several datetime input formats (FR and ISO variants) for admin form parsing.

---

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | +9 champs `module_*` sur `Configuration`, +4 proxy models (`TicketProduct`, `MembershipProduct`, `POSProduct`, `FutProduct`), +`RECHARGE_CASHLESS_FED` et `FUT` dans `CATEGORIE_ARTICLE_CHOICES`, renommage `poids` verbose_name |
| `BaseBillet/migrations/0204_configuration_module_adhesion_and_more.py` | Migration des 9 booleens `module_*` |
| `BaseBillet/migrations/0205_futproduct_membershipproduct_posproduct_and_more.py` | Migration des 4 proxy models |
| `BaseBillet/views.py` | NavBar publique conditionnelle aux modules dans `get_context()` |
| `Administration/admin_tenant.py` | Refacto majeur (~1000 lignes deplacees), re-export des symboles publics, ajout `module_toggle_modal` / `module_toggle`, dependance `module_caisse` ↔ `module_monnaie_locale`, nouveau `RangeDateTimeFilterWithTimeZone` |
| `Administration/admin/__init__.py` | Nouveau (package) |
| `Administration/admin/site.py` | Nouveau : `StaffAdminSite`, `sanitize_textfields` |
| `Administration/admin/dashboard.py` | Nouveau : `get_sidebar_navigation` (sidebar dynamique), `dashboard_callback`, `MODULE_FIELDS`, `_build_modules_context` |
| `Administration/admin/products.py` | Nouveau : `ProductAdmin` + proxy admins `TicketProductAdmin` / `MembershipProductAdmin`, inlines `BasePriceInline`/`TicketPriceInline`/`MembershipPriceInline`, `ProductFormFieldInline`, code POS commente pour V2 |
| `Administration/admin/prices.py` | Nouveau : `PriceAdmin`, `PromotionalCodeAdmin`, `PriceChangeForm` |
| `Administration/templates/admin/index.html` | `+include "admin/dashboard.html"` (cartes modules) |
| `Administration/templates/admin/dashboard.html` | Nouveau : grille de cartes modules avec switches HTMX |
| `Administration/templates/admin/dashboard_module_modal.html` | Nouveau : modal de confirmation pour bascule module |
| `Administration/templates/admin/product/inline_conditional_fields.html` | Nouveau : injection JSON des regles conditionnelles |
| `Administration/static/admin/js/inline_conditional_fields.js` | Nouveau : 400 lignes JS, gestion cascade + animation + MutationObserver |
| `Administration/static/admin/css/price_inline.css` | Nouveau : style des titres `StackedInline` (scope `#prices-group`) |
| `TiBillet/settings.py` | `SIDEBAR.navigation` → callable string, ancien dump renomme `SIDEBAR-TEMP-OLD` (a supprimer plus tard), `+DATETIME_INPUT_FORMATS` |
| `PaiementStripe/views.py` | Branche `elif 'account or business name'` (fix v1.7.18, deja documente) |
| `VERSION` | `VERSION=1.8`, `MIGRATE=1` |
| `locale/fr/LC_MESSAGES/django.{po,mo}` | +1500 lignes (modules, proxies, validations) |
| `locale/en/LC_MESSAGES/django.{po,mo}` | +1500 lignes |
| `TECH DOC/SESSIONS/M-To-V2/INDEX.md` | Nouveau : doc technique V1-to-V2 |
| `Administration/Unfold_docs/stripe-checkout-account-business-name.md` | Nouveau : explication + fix Stripe Checkout |

### Migration
- **Migration necessaire / Migration required:** Oui — `MIGRATE=1` dans `VERSION`.
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
- Les nouveaux booleens ont des `default` : aucun risque sur les tenants existants. Les
  modules deja en production (`billetterie`, `adhesion`, `crowdfunding`, `federation`)
  sont actives par defaut.

### Compatibilite / Compatibility
- **Coexistence V1/V2** : carte "Caisse V2" du dashboard est grisee si `server_cashless`
  est configure (= ancien tenant en V1). Les modules V2 (`monnaie_locale`, `caisse`,
  `inventaire`, `tireuse`, `booking`) restent desactives.
- **`SIDEBAR-TEMP-OLD`** dans `settings.py` : ancien dump conserve commente pour reference,
  a supprimer apres une periode de stabilisation.
- **Code POS/Fut/Categorie** dans `Administration/admin/products.py` : commente bloc par
  bloc (`FROM V2 : TODO`), reactive quand on integre l'app `laboutik` et `inventaire`.

### i18n
- ~1500 lignes ajoutees/modifiees dans `locale/{fr,en}/LC_MESSAGES/django.po`.
- `compilemessages` deja execute (les `.mo` sont a jour dans le commit).

---
