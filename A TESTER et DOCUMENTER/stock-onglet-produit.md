# Section Stock dans la fiche produit de caisse (option A, sans onglets)

## Ce qui a été fait
Voir `CHANGELOG/2026-09-29-admin-stock-dans-la-fiche-produit.md`.

En bref : une section « Stock » en bas des fiches Produit de caisse et Fût.
Réglages enregistrés avec le produit, opérations (réception, ajustement, offert,
perte) immédiates en HTMX. Code : `Administration/admin/stock_fiche_produit.py`.

## Tests à réaliser

### Test 1 : créer un produit avec son stock
1. Admin > Caisse & Restaurant > Produits de caisse > Ajouter.
2. Nom, méthode Vente, prix d'achat. Section Stock : cocher « Suivre le stock »,
   quantité de départ 24, seuil 6. Enregistrer.
3. Rouvrir le produit : section Stock avec « Stock actuel : 24 pièces · OK ».
4. Inventaire > Mouvements de stock : 1 mouvement Réception « Stock initial » de +24.

### Test 2 : produit créé sans suivi
1. Créer un produit, case « Suivre le stock » décochée.
2. Aucun stock créé (liste : colonne Stock = « — »).
3. Rouvrir : la case est proposée. La cocher + 10, enregistrer → stock à 10, 1 mouvement.

### Test 3 : opérations depuis la fiche
1. Produit avec stock. Quantité 10, Réception.
2. Message vert, « Stock actuel » mis à jour **sans recharger la page**.
3. Taper une quantité puis **Entrée** : rien n'est envoyé, on reste sur la fiche.
4. Taper une quantité, puis cliquer sur un lien du menu :
   **pas** d'alerte « modifications non enregistrées ».
5. Changer le nom du produit puis quitter : l'alerte apparaît toujours (non-régression).

### Test 4 : réglages sans toucher à la quantité
1. Fiche produit avec stock 10 ouverte. Sur la caisse, vendre 1 article (stock 9).
2. Sur la fiche (sans recharger), changer le seuil d'alerte et enregistrer.
3. Le stock vaut toujours 9 (pas de retour à 10), aucun nouveau mouvement.
4. Décocher « Autoriser vente hors stock » avec un stock à 0 : la tuile caisse
   passe en bloquée sans recharger (WebSocket).

### Test 5 : fûts
1. Fûts > Ajouter : l'unité proposée par défaut est Centilitres.
2. Même comportement que les produits de caisse.

### Test 6 : lien retour depuis la fiche Stock
1. Inventaire > Stocks > un article : le nom de l'article ouvre la fiche produit
   directement sur la section Stock (fiche fût pour un fût).

## Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_fiche_produit.py -v
docker exec lespass_django poetry run pytest tests/e2e/test_admin_stock_fiche_produit.py -v -s
```

## Compatibilité
- Aucune migration. Les stocks existants s'affichent tels quels.
- `StockInline` n'existe plus : la page d'ajout utilise la section Stock.
- Pour arrêter de suivre le stock d'un produit, il n'y a toujours pas de bouton
  (un stock supprimé effacerait son journal) : comportement inchangé.
