# Boutons de catégorie déduits des articles / Category buttons derived from articles

**Date :** 2026-11-24
**Migration :** Oui — `laboutik/0004_pointdevente_sans_categories` (supprime le M2M `PointDeVente.categories` et sa table de liaison).
`docker exec lespass_django poetry run python manage.py migrate_schemas laboutik`

## Resume / Summary
**Quoi / What :** un point de vente ne choisit plus ses catégories. Les boutons de filtre de la caisse viennent des catégories des articles affichés, triés par `poid_liste`. Les articles sans catégorie ont deux boutons de repli : « Adhésions » (adhésions) et « Divers » (le reste), affichés seulement s'ils ont des articles. Le champ « Catégories » disparaît de l'admin et du modèle.
/ A POS no longer picks its categories. Filter buttons come from the displayed articles' categories. Uncategorised articles get "Adhésions" / "Divers" fallback buttons. The field is removed from the admin and the model.

**Pourquoi / Why :** le M2M faisait doublon avec `Product.categorie_pos`. Quand les deux divergeaient, un article n'avait pas de bouton, ou un bouton affichait une grille vide (cas « Billetterie » sur « Accueil Festival », ou « Cashless » pour un caissier sans « mode recharge »).
/ The M2M duplicated `Product.categorie_pos`; mismatches gave missing buttons or empty grids.

Au passage : la description du type « Cashless » dans l'admin ne cite plus le bouton « Recharger » du check carte. Depuis le « mode recharge », il dépend de la carte primaire, pas du type de caisse.
/ Also: the "Cashless" type description no longer mentions the check-card top-up button, which now depends on the primary card's top-up mode.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_construire_donnees_categories(pv, articles, ...)` lit les articles ; `CATEGORIE_ADHESIONS_PAR_DEFAUT` ; « Divers » traduisible (`gettext_lazy`) |
| `laboutik/models.py` | Suppression de `PointDeVente.categories` |
| `laboutik/migrations/0004_pointdevente_sans_categories.py` | `RemoveField` |
| `Administration/admin/laboutik.py` | Champ retiré du fieldset (« Produits ») et de `filter_horizontal` ; description Cashless corrigée |
| `laboutik/management/commands/create_test_pos_data.py` | Plus de `.categories.set(...)`, plus de catégorie « Billetterie » |
| `tests/pytest/test_pos_views_data.py` | Test 6 réécrit + 4 tests (boutons déduits, ordre, repli, tuile masquée) |
| `tests/pytest/test_pos_models.py`, `tests/pytest/test_stock_visuel_pos.py` | Plus d'usage du M2M |

**i18n :** 2 nouvelles chaînes (« Divers », « Adhésions ») + la description Cashless modifiée. Workflow i18n à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — boutons d'un point de vente classique
1. Ouvrir la caisse sur « Bar ».
2. Les boutons à gauche sont « Tous » puis les catégories des articles du Bar, dans l'ordre `poid_liste`.
3. Cliquer sur chaque bouton : aucun n'affiche une grille vide.

### Test 2 — articles sans catégorie
1. Ouvrir la caisse sur « Adhesions » ou « Mix ».
2. Un bouton « Adhésions » regroupe les adhésions sans catégorie de caisse.
3. Un bouton « Divers » regroupe les autres articles sans catégorie (ex. « Machine 3D », « Pin's TiBillet » sur « Mix »).

### Test 3 — billetterie
1. Ouvrir « Accueil Festival ».
2. Plus de bouton « Billetterie » vide. Les événements à venir gardent leurs boutons, après les catégories.

### Test 4 — admin
1. Admin > Points de vente > modifier un point de vente : la section s'appelle « Produits » et ne montre plus « Catégories ».

### Verifs DB
- La table `laboutik_pointdevente_categories` n'existe plus dans les schémas des lieux.
  (En dev, le schéma `test_modele` la garde : ce n'est pas un lieu, `migrate_schemas` ne le touche pas.)
