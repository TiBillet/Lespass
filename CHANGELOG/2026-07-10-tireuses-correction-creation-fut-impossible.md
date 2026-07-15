# Tireuses : correction création d'un fût impossible / Taps: fix keg creation impossible (issue #445)

**Date :** 2026-07-10
**Migration :** Oui / Yes — `AlterField` sur `Product.categorie_article` et `ProductSold.categorie_article` (changement de `choices` uniquement, aucun SQL sur la colonne). À générer par le mainteneur.

**Quoi / What :** la création d'un fût (`/admin/BaseBillet/futproduct/add/`) échouait systématiquement
avec le message générique « Corrigez l'erreur ci-dessous », sans détail, quels que soient les champs saisis.

**Pourquoi / Why :** `FutProductForm` force `categorie_article = Product.FUT` (`"U"`) via un `HiddenInput`,
mais la valeur `FUT` était **commentée** dans `CATEGORIE_ARTICLE_CHOICES` (`BaseBillet/models.py`). À la
validation, `ModelForm._post_clean()` → `full_clean()` rejetait `"U"` comme choix invalide. L'erreur était
attachée au champ `categorie_article`, rendu en `HiddenInput` → invisible → seul le message générique
s'affichait.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | Réactivation du choix `(FUT, _("Keg (connected tap)"))` dans `CATEGORIE_ARTICLE_CHOICES` |
