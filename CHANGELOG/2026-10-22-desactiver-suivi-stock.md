# Mettre en pause le suivi du stock d'un produit / Pause stock tracking for a product

**Date :** 2026-10-22
**Migration :** Oui — `inventaire/migrations/0002_stock_suivi_actif.py`
(`docker exec lespass_django poetry run python manage.py migrate_schemas --executor=standard`)

## Resume / Summary
**Quoi / What :** La case « Suivre le stock » reste affichée sur la fiche d'un produit de caisse
ou d'un fût, même quand le stock existe. La décocher met le suivi en pause (nouveau champ
`Stock.suivi_actif`). En pause, le produit se vend comme s'il n'avait pas de stock : pas de
décompte, pas de pastille sur la tuile, pas de blocage en rupture. Le Stock et ses mouvements
sont conservés. Recocher réactive le suivi, avec la quantité laissée telle quelle.
/ The "Track stock" switch stays on the product page once a stock exists. Unchecking it pauses
tracking (new `Stock.suivi_actif` field): no decrement, no tile badge, no out-of-stock blocking.
History is kept; re-checking resumes tracking with the quantity left as it was.

**Pourquoi / Why :** Une fois le stock créé, il n'existait aucun moyen d'arrêter de le suivre
(la suppression d'un Stock est interdite, pour la traçabilité).
/ Once a stock existed, there was no way to stop tracking it (deleting a Stock is forbidden).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `inventaire/models.py` | Champ `Stock.suivi_actif` + helper `stock_suivi_du_produit()` |
| `inventaire/migrations/0002_stock_suivi_actif.py` | AddField (défaut True) |
| `Administration/admin/stock_fiche_produit.py` | Case toujours affichée, sauvegarde du suivi, message à la réactivation, panneau « en pause », badge « — », filtre « Non suivi » |
| `Administration/admin/inventaire.py` | `suivi_actif` dans la liste (éditable + filtre) et la fiche Stock |
| `laboutik/views.py` | Tuile, garde panier, décrémentations, badge en retard et panel : stock en pause ignoré |
| `controlvanne/billing.py` | Tirage : pas de décompte si le suivi est en pause |
| `inventaire/views.py` | Débit mètre refusé (400) si le suivi est en pause |
| `wsocket/broadcast.py`, `laboutik/templates/laboutik/partial/hx_stock_badge.html` | Badge temps réel vide (sans `data-stock-*`) quand le suivi est en pause |
| `tests/pytest/test_stock_fiche_produit.py` | Tests 17 à 22 |
| `tests/e2e/test_admin_stock_fiche_produit.py` | Case visible + masquage des réglages au décochage |

---

## Comment tester (a la main) / Manual test
### Test 1 — mettre en pause
1. Admin > Caisse > un produit avec stock (ex : 10 pièces) > section Stock.
2. La case « Suivre le stock » est cochée. La décocher : unité, seuil et vente hors stock se cachent.
3. Enregistrer. Dans la liste, la colonne Stock affiche « — ». Le filtre « État du stock > Non suivi » montre le produit.
4. Rouvrir la fiche : le panneau d'opérations affiche « Suivi en pause… ».

### Test 2 — vente pendant la pause
1. Mettre le stock à 0 avec « Autoriser vente hors stock » décoché, puis mettre le suivi en pause.
2. Sur une caisse ouverte : la tuile n'est plus grisée, pas de pastille « Épuisé ».
3. Vendre l'article : la vente passe, aucun mouvement « Vente » dans le journal du stock.

### Test 3 — réactiver
1. Recocher « Suivre le stock » et enregistrer.
2. Message : « Suivi du stock réactivé… faites un ajustement d'inventaire si besoin. »
3. La quantité est celle d'avant la pause. La pastille revient sur la tuile.

### Test 4 — liste des stocks
1. Admin > Inventaire > Stocks : colonne « Suivi actif » éditable et filtre « Suivi actif ».

### Verifs DB / Playwright
- `docker exec lespass_django poetry run python manage.py tenant_command shell -s lespass -c "from inventaire.models import Stock; print(Stock.objects.filter(suivi_actif=False).count())"`
- Pytest : `tests/pytest/test_stock_fiche_produit.py` (classe `TestSuiviDuStockEnPause`).
- E2E : `tests/e2e/test_admin_stock_fiche_produit.py::test_champs_stock_visibles_quand_le_produit_a_deja_un_stock`.
