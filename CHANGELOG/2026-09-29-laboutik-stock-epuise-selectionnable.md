# laboutik : article épuisé encore vendable, erreur de stock trop tardive, stock figé après une vente ou une réception admin

**Date :** 2026-09-29
**Migration :** Non / No

## Résumé / Summary

**Quoi / What :** trois bugs de stock sur la caisse V2.

- **Un article épuisé restait sélectionnable.** Le badge « Épuisé » s'affichait,
  mais le clic n'était jamais bloqué. En HTML, `data-stock-bloquant` se lit
  `dataset.stockBloquant` en JS. `articles.js` lisait `dataset.stock_bloquant`
  (donc `data-stock_bloquant`), qui n'existait pas sur la tuile. En plus, le
  badge initial utilisait `data-stock_bloquant` calculé sur la *rupture*
  (sans tenir compte de « vente hors stock autorisée »), alors que le badge
  WebSocket utilisait `data-stock-bloquant`. Après chaque message WebSocket,
  `syncStockBloquantApresWebSocket` ne voyait donc jamais le blocage et
  **retirait** la classe `article-bloquant`. Tout est aligné sur
  `data-stock-bloquant` / `dataset.stockBloquant`.
  / Blocking attribute name mismatch (`data-stock-bloquant` vs `dataset.stock_bloquant`).
- **L'erreur « stock insuffisant » arrivait après le choix du moyen de paiement.**
  `_valider_stock_panier` n'était appelée que dans `payer()` (espèces, CB, chèque).
  Elle est maintenant aussi appelée dans `moyens_paiement()` (clic VALIDER).
  Elle reste dans `payer()`, car un autre poste peut vendre le dernier article
  entre les deux clics.
  **Le paiement NFC ne vérifiait pas le stock du tout** : garde ajoutée au début
  de `_payer_par_nfc`, avant tout débit.
  / Stock check now also on VALIDER, and added to the NFC path (was missing).
- **Stock figé après une vente.** Le broadcast WebSocket existait déjà
  (`_creer_lignes_articles` → `transaction.on_commit` → `broadcast_stock_update`
  → groupe `laboutik-jauges-{schema}` → OOB swap de `#stock-badge-<uuid>`).
  Mais (1) le bug d'attribut ci-dessus annulait le blocage à chaque message, et
  (2) la garde du pavé numérique (vrac) lisait `stock_disponible`, figé dans
  `data-tarifs` au chargement de la page. Le badge porte maintenant
  `data-stock-quantite` (mis à jour par le WebSocket), et `tarif.js` lit cette
  valeur en priorité.
  / Stock was already pushed by WebSocket; the badge now carries the live quantity for the numpad guard.

- **Stock rechargé depuis l'admin : caisses pas prévenues.** Seules les ventes
  en caisse et le panel stock de la caisse envoyaient le badge par WebSocket.
  Désormais `StockService.creer_mouvement` et `ajuster_inventaire` préviennent
  toutes les caisses après commit (`broadcast_etat_stock`, nouveau dans
  `wsocket/broadcast.py`). Cela couvre les boutons de la fiche stock admin, l'API
  `StockViewSet`, le débit mètre et le panel caisse (dont le broadcast en double a
  été retiré). `StockAdmin.save_model` prévient aussi les caisses quand la fiche
  est modifiée (vente hors stock, seuil, y compris via `list_editable`). Les
  tirages des tireuses (`controlvanne/billing.py`) préviennent aussi les caisses.
  / Admin restock, API, flow meter and tap sales now notify POS terminals.
- **Création d'un stock dans l'admin : quantité doublée.** `save_model` enregistrait
  le stock avec la quantité saisie, puis le mouvement « Stock initial » l'ajoutait
  une seconde fois (`F("quantite") + delta`) : 10 saisis → 20 en stock. Le stock est
  maintenant enregistré à 0, puis le mouvement apporte la quantité.
  **Contre-épreuve faite :** le test échouait (`assert 20 == 10`) avant la correction.
  / Admin stock creation doubled the typed quantity.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/articles.html` | Badge : `data-stock-bloquant` (sur `stock_bloquant`) + `data-stock-quantite` |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | Ajout de `data-stock-quantite` |
| `laboutik/static/js/articles.js` | Lecture / écriture de `dataset.stockBloquant` |
| `laboutik/static/js/tarif.js` | Garde du pavé : quantité lue sur le badge de la tuile |
| `laboutik/views.py` | Contrôle du stock dans `moyens_paiement()` et `_payer_par_nfc()` |
| `wsocket/broadcast.py` | Nouveau `broadcast_etat_stock(stock)` |
| `inventaire/services.py` | `creer_mouvement` / `ajuster_inventaire` préviennent les caisses (on_commit) |
| `Administration/admin/inventaire.py` | `StockAdmin.save_model` : broadcast à la modification, plus de doublement à la création |
| `controlvanne/billing.py` | Broadcast du stock après un tirage |
| `tests/pytest/test_stock_broadcast_hors_vente.py` | 4 tests : réception, ajustement, modif admin, création admin |
| `tests/pytest/test_stock_negatif.py` | 3 tests : refus à VALIDER, passage si hors stock autorisé, refus NFC |

### Migration
- **Migration nécessaire / Migration required :** Non / No
