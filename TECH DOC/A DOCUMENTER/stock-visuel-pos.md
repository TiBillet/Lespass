# Affichage visuel stock dans le POS

## Ce qui a été fait

Pastille stock sur les tuiles articles du POS, avec mise à jour temps réel via WebSocket.

### Modifications
| Fichier | Changement |
|---|---|
| `laboutik/views.py` | Helper `_formater_stock_lisible()`, enrichissement `_construire_donnees_articles()` avec données stock, broadcast WS dans `_creer_lignes_articles()` |
| `laboutik/templates/cotton/articles.html` | Pastille stock + classe `article-bloquant` |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | Template OOB swap WebSocket |
| `laboutik/static/css/articles.css` | Styles 3 états (alerte, rupture, bloquant) |
| `laboutik/static/js/articles.js` | Blocage clic sur articles bloquants |
| `wsocket/broadcast.py` | `broadcast_stock_update()` |
| `wsocket/consumers.py` | Handler `stock_update()` |

## Tests à réaliser

### Test 1 : Produit sans gestion de stock
1. Ouvrir le POS sur un point de vente
2. Vérifier qu'un produit sans Stock lié n'a aucun badge
3. Vérifier qu'il est cliquable normalement

### Test 2 : Produit en alerte stock
1. Dans l'admin > Stock, créer un Stock pour un produit avec seuil_alerte=5, quantité=3
2. Ouvrir le POS → la tuile du produit a une pastille orange "3"
3. Vendre ce produit → la pastille se met à jour (quantité diminue)

### Test 3 : Produit en rupture non bloquante
1. Dans l'admin, créer un Stock avec quantité=0, autoriser_vente_hors_stock=True
2. Ouvrir le POS → pastille rouge "Épuisé"
3. Le produit reste cliquable (on peut quand même vendre)

### Test 4 : Produit en rupture bloquante
1. Dans l'admin, créer un Stock avec quantité=0, autoriser_vente_hors_stock=False
2. Ouvrir le POS → tuile grisée, pastille rouge "Épuisé"
3. Cliquer sur la tuile → rien ne se passe (non cliquable)

### Test 5 : Mise à jour temps réel (WebSocket)
1. Ouvrir le POS dans 2 onglets (ou 2 caisses)
2. Vendre un produit avec stock depuis l'onglet 1
3. L'onglet 2 voit le badge stock se mettre à jour automatiquement

### Test 6 : Transition d'état après ventes successives
1. Créer un Stock : quantité=6, seuil_alerte=5, autoriser_vente_hors_stock=False
2. Vendre 1 → pastille orange "5" apparaît (alerte)
3. Vendre encore 5 → pastille rouge "Épuisé" + tuile grisée (rupture bloquante)
4. Tenter de cliquer → non cliquable

## Tests automatisés

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_visuel_pos.py -v
```

14 tests : 10 unitaires (formatage), 3 intégration (données articles), 1 broadcast.

## Compatibilité

- Aucune migration nécessaire
- Les produits sans Stock ne sont pas affectés (aucun badge)
- Le broadcast réutilise le group Redis existant `laboutik-jauges-{schema}` — pas de nouveau group
