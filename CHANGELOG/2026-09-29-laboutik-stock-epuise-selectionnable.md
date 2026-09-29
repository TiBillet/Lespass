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

- **Plusieurs lignes du même produit contournaient le blocage.** Stock 100 g bloquant,
  panier 100 g + 100 g : la vente passait et le stock tombait à -100 g.
  `_valider_stock_panier` comparait chaque ligne seule au stock. Elle additionne
  maintenant toutes les lignes d'un même produit (pesées successives, plusieurs
  tarifs), puis compare le total. Une seule erreur par produit.
  Côté pavé numérique, `tarif.js` additionne les champs `weight-<produit>--*` déjà
  dans le panier avant de comparer au stock, et affiche le reste possible.
  `addition.js` ne supprimait jamais les champs `weight-*` (ni au retrait d'une ligne,
  ni au RESET) : c'est corrigé, sinon la garde aurait compté des pesées retirées.
  **Contre-épreuve faite :** le test « 100 g + 100 g » échouait avant la correction.
  / Several lines of the same product bypassed the stock block; now summed per product.

- **Garde au clic pour les articles à l'unité (et les tarifs fixes / prix libre).**
  Stock de 2, vente hors stock interdite : le 3e clic sur la tuile est refusé tout de
  suite. Le message est ensuite demandé au serveur
  (`GET /laboutik/paiement/stock_insuffisant/`, `PaiementViewSet.stock_insuffisant`) :
  popup standard `hx_messages.html` (même style que les autres messages), texte en
  lignes courtes, quantités lisibles, stock relu en base :
  « Biere : stock insuffisant. / Déjà dans le panier : 2 / En stock : 2 /
  Vous ne pouvez plus en ajouter. ». Si le stock en base permet finalement l'ajout
  (badge en retard), popup info « Le stock vient de changer. Touchez à nouveau l'article. »
  `articles.js:verifierStockAvantAjout()` compte ce que le panier demande déjà pour
  le produit, comme le serveur : quantité × contenance du tarif, et pesées. Elle lit
  le stock et l'autorisation sur le badge de la tuile (mis à jour par WebSocket).
  Appelée au clic sur une tuile mono-tarif et dans `tarif.js:addArticleWithPrice()`.
  La garde du pavé (vrac) utilise le même comptage : un tarif fixe du même produit
  déjà au panier est maintenant compté.
  Données ajoutées : `contenance` (tuile et chaque tarif de `data-tarifs`),
  `data-autoriser-hors-stock` sur le badge. Les 4 constructions du dict du badge
  sont remplacées par `wsocket/broadcast.py:donnees_badge_stock(stock)`.
  Le serveur reste autoritaire (`_valider_stock_panier` au clic VALIDER).
  / Click guard for unit, fixed and free-price items; server stays authoritative.
- **Messages de stock plus clairs.** « demande X, reste Y » mélangeait le total du
  panier et la saisie en cours. Partout, les mots sont maintenant « dans le panier »,
  « en stock », « encore possible » : popup de la garde au clic, alerte du pavé vrac
  (`tarif.js`) et message du clic VALIDER (`_formater_erreurs_stock`, une ligne par
  produit : « Cacahuètes : 50 kg dans le panier, 200 g en stock »).
  **Nouvelles chaînes à traduire** (`.po` non modifiés) : « %(nom)s : %(au_panier)s dans
  le panier, %(en_stock)s en stock », « %(nom)s : stock insuffisant. »,
  « Déjà dans le panier : %(quantite)s », « En stock : %(quantite)s »,
  « Vous pouvez encore en ajouter : %(quantite)s », « Vous ne pouvez plus en ajouter. »,
  « Le stock vient de changer. Touchez à nouveau l'article. ».
  / Clearer stock wording everywhere; new strings to translate.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/articles.html` | Badge : `data-stock-bloquant` (sur `stock_bloquant`) + `data-stock-quantite` |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | Ajout de `data-stock-quantite` |
| `laboutik/static/js/articles.js` | Lecture / écriture de `dataset.stockBloquant` |
| `laboutik/static/js/tarif.js` | Garde du pavé : quantité lue sur le badge de la tuile, et ajout de ce qui est déjà au panier |
| `laboutik/static/js/addition.js` | Suppression des champs `weight-*` au retrait d'une ligne et au RESET |
| `tests/e2e/test_tarif_popup.py` | Test : la garde compte ce qui est déjà au panier |
| `laboutik/views.py` | Contrôle du stock dans `moyens_paiement()` et `_payer_par_nfc()` ; `_valider_stock_panier` additionne les lignes d'un même produit |
| `wsocket/broadcast.py` | Nouveau `broadcast_etat_stock(stock)` |
| `inventaire/services.py` | `creer_mouvement` / `ajuster_inventaire` préviennent les caisses (on_commit) |
| `Administration/admin/inventaire.py` | `StockAdmin.save_model` : broadcast à la modification, plus de doublement à la création |
| `controlvanne/billing.py` | Broadcast du stock après un tirage |
| `tests/pytest/test_stock_broadcast_hors_vente.py` | 4 tests : réception, ajustement, modif admin, création admin |
| `tests/pytest/test_stock_negatif.py` | 3 tests : refus à VALIDER, passage si hors stock autorisé, refus NFC |

| `laboutik/serializers.py` | `StockInsuffisantSerializer` (paramètres de la popup de refus) |
| `laboutik/static/css/overlay.css` | `.alerte-messages-texte` : `white-space: pre-line` (messages sur plusieurs lignes) |
| `laboutik/static/js/articles.js` | `contenanceDuTarif`, `quantiteDuProduitDejaAuPanier`, `verifierStockAvantAjout` + appel au clic |
| `tests/e2e/test_garde_stock_au_clic.py` | 5 tests : refus au 3e clic (paramètres envoyés au serveur), autorisé, mise à jour WS, contenance, tarifs additionnés |

### Migration
- **Migration nécessaire / Migration required :** Non / No
