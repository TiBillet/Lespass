# Design — FutProductAdmin + ameliorations Stock/help texts

Date : 2026-04-07
Statut : VALIDE (brainstorming termine)

---

## 1. Contexte

Le proxy `FutProduct(Product)` existe dans `BaseBillet/models.py` (categorie `FUT = "U"`)
mais aucun admin n'est enregistre. On ne peut ni creer ni modifier un produit de type fut.

La spec `SPEC_CONTROLVANNE.md` section 2.3 prevoit un `FutProductAdmin` avec formulaire
restreint. En parallele, des ameliorations sur le `StockInline` et les help texts de
`poids_mesure`/`contenance` sont necessaires.

---

## 2. Changements

### 2.1 StockInline — quantite editable a la creation

**Fichier :** `Administration/admin/inventaire.py`

**Actuel :** `readonly_fields = ("quantite",)` en dur.

**Apres :** `get_readonly_fields()` dynamique :
- Mode **add** (`obj is None`) : pas de readonly → `quantite` editable
- Mode **change** : `quantite` readonly (modifiable uniquement via mouvements de stock)

`extra = 0` et `max_num = 1` restent inchanges. Un article peut ne pas avoir de stock.

### 2.2 StockAdmin — unite modifiable en mode change

**Fichier :** `Administration/admin/inventaire.py`

**Actuel :** `get_readonly_fields()` renvoie `["lien_vers_pos_product", "quantite", "unite"]`
en mode change.

**Apres :** renvoie `["lien_vers_pos_product", "quantite"]` — l'unite est modifiable
en cas d'erreur. La quantite reste readonly (circuit mouvements).

### 2.3 Help text `poids_mesure` enrichi

**Fichier :** `BaseBillet/models.py` (champ `Price.poids_mesure`, ligne ~1570)

**Actuel :**
```
"If checked, the cashier enters the weight or volume at each sale.
The price is per kg (for grams) or per liter (for centiliters)."
```

**Apres :**
```
"If checked, the cashier enters the weight or volume at each sale.
The price is per kg (grams) or per liter (centiliters).
Stock is decremented by the exact quantity entered."
```

**Traduction FR (locale/fr/LC_MESSAGES/django.po) :**
```
"Si coche, le caissier saisit le poids ou le volume a chaque vente.
Le prix est au kg (grammes) ou au litre (centilitres).
Le stock est decremente de la quantite exacte saisie."
```

### 2.4 Help text `contenance` enrichi

**Fichier :** `BaseBillet/models.py` (champ `Price.contenance`, ligne ~1607)

**Actuel :**
```
"Quantite consommee par unite vendue, dans l'unite du stock.
Ex : pinte=50 (cl), demi=25 (cl), portion=150 (g).
Vide = 1 unite par defaut."
```

**Apres :**
```
"Stock quantity consumed per unit sold (in stock unit).
Use this when selling by unit but decrementing stock by weight/volume.
E.g.: pint=50 (cl), half=25 (cl), portion=150 (g).
Empty = 1 unit. Incompatible with 'Sale by weight/volume'
(where the cashier enters the exact quantity)."
```

**Traduction FR :**
```
"Quantite de stock consommee par unite vendue (dans l'unite du stock).
Utilisez ce champ quand on vend a l'unite mais qu'on decremente le stock
en poids/volume. Ex : pinte=50 (cl), demi=25 (cl), portion=150 (g).
Vide = 1 unite. Incompatible avec 'Vente au poids/volume'
(ou le caissier saisit la quantite exacte)."
```

### 2.5 FutProductForm

**Fichier :** `Administration/admin/products.py`

Herite de `ProductAdminCustomForm`. Meme pattern que `POSProductForm`.

**Champs :**
- `categorie_article` : cache (`HiddenInput`), force a `Product.FUT`
- `name`, `short_description`, `long_description` (infos biere : brasseur, type, degre)
- `img` (upload image/logo)
- `palette_pos` : `PalettePickerWidget` (meme que POS)
- `couleur_texte_pos` : `UnfoldAdminColorInputWidget`
- `couleur_fond_pos` : `UnfoldAdminColorInputWidget`
- `icon_pos` : `IconPickerWidget`

**`clean()` :** saute la validation `ProductAdminCustomForm` (pas de tarif obligatoire),
applique la palette sur les champs couleur.

### 2.6 FutPriceInline

**Fichier :** `Administration/admin/products.py`

Copie de `POSPriceInline` :
- `fields = ("name", "prix", "poids_mesure", "contenance", ("publish", "order"))`
- `inline_conditional_fields = {"contenance": "poids_mesure == false"}`
- Media JS : `admin/js/inline_conditional_fields.js`

### 2.7 FutProductAdmin

**Fichier :** `Administration/admin/products.py`

Herite de `ProductAdmin`. Enregistre sur `staff_admin_site`.

- `form = FutProductForm`
- `inlines = [FutPriceInline]`
- `compressed_fields = True`
- `warn_unsaved_form = True`
- `list_filter = ["publish"]`
- `get_inlines()` : ajoute `StockInline` en mode add (`obj is None`)
- `get_queryset()` : filtre `categorie_article=Product.FUT`
- `save_related()` : si un Price a `poids_mesure=True` et pas de Stock,
  auto-cree avec `UniteStock.CL` (centilitres, pas GR comme POS)
- Les 4 `has_*_permission` avec `TenantAdminPermissionWithRequest`
- `changeform_view()` : collecte les regles conditionnelles des inlines (meme pattern POS)

### 2.8 Sidebar — entree "Produits fut"

**Fichier :** `Administration/admin_tenant.py` (fonction `get_sidebar_navigation`)

Entree dans la section "Tireuses", conditionnelle sur `config.module_tireuse` :
```python
{
    "title": _("Keg products"),
    "icon": "sports_bar",
    "link": reverse_lazy("staff_admin:BaseBillet_futproduct_changelist"),
}
```

---

## 3. Fichiers modifies

| Fichier | Changement |
|---------|-----------|
| `Administration/admin/inventaire.py` | StockInline: quantite editable en add. StockAdmin: unite modifiable en change |
| `BaseBillet/models.py` | Help texts enrichis pour `poids_mesure` et `contenance` |
| `Administration/admin/products.py` | +FutProductForm, +FutPriceInline, +FutProductAdmin |
| `Administration/admin_tenant.py` | Sidebar entree "Produits fut" conditionnel module_tireuse |
| `locale/fr/LC_MESSAGES/django.po` | Traductions FR des nouveaux help texts |
| `locale/en/LC_MESSAGES/django.po` | Traductions EN |

## 4. Pas de migration

- `FutProduct` est un proxy (zero migration, deja en base)
- Les help texts ne generent pas de migration (sauf si `makemigrations` les detecte,
  auquel cas on genere une migration triviale)

## 5. Tests

- Verifier creation d'un FutProduct dans l'admin (formulaire complet)
- Verifier que le queryset ne montre que les produits FUT
- Verifier StockInline en mode add : quantite editable
- Verifier StockAdmin en mode change : unite modifiable
- Verifier save_related : auto-creation Stock en CL si poids_mesure
