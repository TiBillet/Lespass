# Couleurs de caisse : palette pastel imposée / POS colors: pastel palette only

**Date :** 2026-10-05
**Migration :** Non

## Resume / Summary
**Quoi / What :** dans l'admin, la couleur de fond d'un article de caisse et d'une catégorie de caisse se choisit maintenant en pastilles, uniquement dans la palette pastel (11 teintes × clair/moyen/soutenu = 33 couleurs, tokens `--color-{teinte}-{100|200|300}`). Les champs « Color palette » et « couleur du texte » disparaissent de ces deux fiches. Le texte est écrit automatiquement : `#1a1a1a` sur une couleur pastel, vide sans couleur. Une ancienne couleur hors palette reste conservée (pastille « Couleur actuelle ») et son texte n'est pas modifié.
/ POS item and POS category background colors are now picked as swatches from the pastel palette only (33 colors). The "Color palette" and "text color" fields are removed; text is set to dark #1a1a1a automatically. An existing out-of-palette color is kept.

**Pourquoi / Why :** des boutons de caisse cohérents et lisibles, comme pour les fûts (palette limitée). / Consistent, readable POS buttons, like keg colors.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `PALETTE_PASTEL_CAISSE`, `COULEUR_TEXTE_SUR_PASTEL`, `codes_de_la_palette_pastel_caisse()`, `couleur_de_texte_pour_un_fond_pastel()`, `_valider_couleur_hexadecimale()` (aussi utilisée par le fût), `CouleurFondPastelWidget` ; `POSProductForm` et `CategorieProductForm` : fond en pastilles, plus de palette ni de couleur texte, texte écrit dans `clean()` ; fieldsets mis à jour |
| `Administration/templates/admin/product/widget_couleur_fond_pastel.html` | Nouveau : pastilles radio sans JS, une colonne par teinte (11 colonnes côte à côte) |
| `tests/pytest/test_admin_couleurs_pastel_caisse.py` | Nouveau : 21 tests (palette, widget, formulaires) |

Hors périmètre : les couleurs posées par le code (`fedow_core/signals.py` `COULEURS_PAR_CATEGORIE` pour les recharges, `create_test_pos_data`) ne sont pas changées. Les fûts gardent leur palette « Létireuz ».

---

## Comment tester (a la main) / Manual test
### Test 1 — article de caisse
1. Admin > Articles de caisse > ajouter ou modifier un article.
2. Section « POS display » : 11 colonnes de 3 pastilles côte à côte (clair en haut, soutenu en bas) + « Aucune ». Plus de « Color palette » ni de « POS text color ».
3. Choisir une pastille (ex. rose moyen), enregistrer.
4. En caisse (LaBoutik) : le bouton a ce fond et un texte foncé.
5. Choisir « Aucune », enregistrer : le bouton reprend la couleur de sa catégorie.

### Test 2 — catégorie de caisse
1. Admin > Catégories de caisse > modifier une catégorie.
2. Section « Apparence » : mêmes pastilles, plus de palette ni de couleur du texte.
3. Choisir une pastille : la catégorie et ses articles sans couleur propre passent en pastel, texte foncé.

### Test 3 — anciennes couleurs
1. Ouvrir un article qui avait un fond foncé (ex. `#1e40af`).
2. Une pastille « Couleur actuelle » est cochée en premier. Enregistrer sans rien changer : couleur et texte identiques.

### Test 4 — fûts inchangés
1. Ouvrir un fût : la palette « Létireuz » (11 couleurs vives) est toujours là.

### Verifs DB / Playwright
- `python -m pytest tests/pytest/test_admin_couleurs_pastel_caisse.py -v`
- Après Test 1 : `Product.objects.get(name="…").couleur_texte_pos == "#1a1a1a"` dans `manage.py tenant_command shell`.
- Playwright possible via les `data-testid` : `caisse-pastilles-fond`, `caisse-pastille-aucune`, `caisse-pastille-actuelle`, `caisse-pastille-{code sans #}`.
