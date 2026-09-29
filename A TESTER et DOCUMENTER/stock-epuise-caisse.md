# Stock épuisé en caisse : blocage, erreur au bon moment, mise à jour en direct

## Ce qui a été fait
Voir `CHANGELOG/2026-09-29-laboutik-stock-epuise-selectionnable.md`.

## Préparation
Dans l'admin : un produit « VT » avec un Stock, quantité 2,
**vente hors stock : bloquée**. Un produit vrac (poids/mesure) avec un Stock
en grammes, bloqué lui aussi. Ouvrir le même PV sur **deux onglets** (poste A et poste B).

## Tests à réaliser

### Test 1 : article épuisé non sélectionnable
1. Stock à 0 (panel stock → ajustement 0).
2. Recharger la caisse : la tuile est grisée, badge « Épuisé ».
3. Cliquer la tuile → **rien n'est ajouté au panier**.

### Test 2 : mise à jour en direct après une vente (WebSocket)
1. Stock à 2. Poste A : vendre 2 articles en espèces.
2. Sur **A et B**, sans recharger : badge « Épuisé » + tuile grisée.
3. Cliquer la tuile sur B → rien n'est ajouté.
4. Réception de +5 dans le panel stock → la tuile redevient cliquable sur A et B.

### Test 3 : erreur au clic VALIDER
1. Stock à 1. Poste A : mettre 1 article au panier (ne pas valider).
2. Poste B : vendre 1 article (stock à 0).
3. Poste A : VALIDER → message « Stock insuffisant — vente refusée » **avant**
   l'écran des moyens de paiement.

### Test 4 : paiement cashless (NFC)
1. Même préparation que le test 3, puis payer par carte cashless sur A.
2. Refus « Stock insuffisant », carte non débitée.

### Test 5 : vrac (pavé numérique)
1. Stock vrac 500 g. Vendre 400 g sur le poste B.
2. Poste A (sans recharger) : ouvrir le pavé, saisir 300 g → alerte
   « 100g disponibles » (avant : 500g, valeur figée au chargement).

### Test 6 : vente hors stock autorisée (non-régression)
1. Passer le stock en « Autorisée », stock 0.
2. La tuile n'est pas grisée. La vente passe, avec l'alerte « Stock négatif ».

### Test 7 : réception depuis l'admin
1. Stock à 0, bloqué. La caisse est ouverte : tuile grisée « Épuisé ».
2. Admin → Inventaire → Stock → fiche du produit → bouton « Réception » +5.
3. Sur la caisse, sans recharger : le badge disparaît, la tuile redevient cliquable.
4. Refaire avec « Ajustement » à 0 : la tuile redevient grisée.

### Test 8 : modification de la fiche stock dans l'admin
1. Stock à 0, bloqué, caisse ouverte (tuile grisée).
2. Admin : cocher « vente hors stock autorisée » (fiche ou liste) et enregistrer.
3. Sur la caisse, sans recharger : la tuile n'est plus grisée (badge « Épuisé » conservé).

### Test 9 : création d'un stock dans l'admin
1. Admin → Stock → Ajouter, quantité 10.
2. Vérifier : quantité 10 (et pas 20), un mouvement « Stock initial » +10.

### Test 10 : tirage à une tireuse
1. Produit fût avec stock, caisse ouverte sur un PV qui montre ce produit.
2. Faire un tirage : le badge de stock de la tuile suit (alerte / épuisé).

## Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_negatif.py tests/pytest/test_stock_visuel_pos.py tests/pytest/test_stock_broadcast_hors_vente.py -v
```

## Compatibilité
Aucune migration. Pas de nouvelle chaîne traduisible (on réutilise
`_formater_erreurs_stock`).
