# Masquer le stock sur la tuile de caisse / Hide stock on the POS tile

**Date :** 2026-10-24
**Migration :** Oui — `inventaire/migrations/0002_stock_afficher_en_caisse.py`
(`AddField`, `default=True`). TENANT_APP : `migrate_schemas` sur tous les lieux.

## Resume / Summary

**Quoi / What :** nouveau réglage « Afficher le stock sur la tuile »
(`Stock.afficher_en_caisse`). Décoché, la tuile de caisse n'affiche plus de pastille de
stock (quantité sous le seuil, « Épuisé »), mais le stock est toujours compté. Un article
**bloqué** (rupture + vente hors stock interdite) affiche quand même « Épuisé ». L'alerte
« Stock négatif » de l'écran de fin de vente n'apparaît plus pour un stock masqué.
/ New "Show stock on the tile" setting. Unchecked: no stock badge on the POS tile, stock
still counted. A blocked item still shows "Épuisé". No negative-stock alert after the sale.

**Pourquoi / Why :** un lieu veut compter son stock sans le montrer au caissier.
/ A venue wants to count its stock without showing it to the cashier.

Spec : `TECH_DOC/SESSIONS/INVENTAIRE/CHANTIER-02-afficher-en-caisse.md`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `inventaire/models.py` | champ `Stock.afficher_en_caisse` |
| `inventaire/migrations/0002_stock_afficher_en_caisse.py` | migration |
| `inventaire/services.py` | `creer_stock_initial(afficher_en_caisse=True)` |
| `Administration/admin/stock_fiche_produit.py` | 4ᵉ réglage de la section Stock (création et modification) |
| `Administration/admin/inventaire.py` | `StockAdmin` : colonne éditable dans la liste, champ de la fiche |
| `Administration/templates/admin/inventaire/stock_list_before.html` | texte d'aide |
| `wsocket/broadcast.py` | `donnees_badge_stock` porte `afficher_en_caisse` |
| `laboutik/views.py` | donnée de la tuile ; pas d'alerte « Stock négatif » si masqué (2 chemins de vente) |
| `laboutik/templates/cotton/articles.html` | pastille conditionnée |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | même règle pour le badge WebSocket |
| `tests/pytest/test_stock_visuel_pos.py` | 5 tests de rendu (tuile et badge WebSocket) |
| `tests/pytest/test_stock_fiche_produit.py` | 2 tests (masquer, créer masqué) + champ rendu + tests existants complétés |
| `tests/pytest/test_stock_negatif.py` | 1 test : pas d'alerte, stock décompté |
| `tests/e2e/test_garde_stock_au_clic.py`, `tests/e2e/test_admin_stock_fiche_produit.py` | fabriques et liste des champs conditionnels complétées |

Nouvelles chaînes traduisibles (msgid FR) : « Afficher le stock sur la tuile », deux
textes d'aide, l'aide de « Suivre le stock » et celle de la liste des stocks.
Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — masquer une pastille d'alerte
1. Admin > Produits de caisse > un article avec stock, quantité sous le seuil d'alerte.
2. Section Stock : décocher « Afficher le stock sur la tuile », Enregistrer.
3. Ouvrir la caisse : la tuile n'a plus de pastille orange.
4. Vendre l'article : la vente passe, la quantité baisse dans Inventaire > Stocks.

### Test 2 — article bloqué
1. Même article, quantité 0, « Autoriser vente hors stock » décoché, stock masqué.
2. Caisse : la tuile est grisée et affiche « Épuisé ».

### Test 3 — pas d'alerte « Stock négatif »
1. Article masqué, vente hors stock autorisée, quantité 1.
2. Vendre 2 : l'écran de fin de vente n'affiche pas l'encadré « Stock négatif ».
3. Recocher « Afficher le stock sur la tuile » et revendre : l'encadré revient.

### Test 4 — en direct
1. Caisse ouverte dans un onglet, admin dans un autre.
2. Inventaire > Stocks : décocher la colonne « Afficher le stock sur la tuile » d'un
   article en alerte, Enregistrer.
3. La pastille disparaît de la tuile sans recharger la caisse.

### Verifs DB / tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_visuel_pos.py tests/pytest/test_stock_fiche_produit.py tests/pytest/test_stock_negatif.py -q
docker exec lespass_django poetry run pytest tests/e2e/test_garde_stock_au_clic.py tests/e2e/test_admin_stock_fiche_produit.py -q
```
