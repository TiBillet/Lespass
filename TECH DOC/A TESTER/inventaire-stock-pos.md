# Inventaire et stock POS

## Ce qui a été fait
Nouvelle app `inventaire` (TENANT_APP) avec gestion de stock optionnelle par produit POS.

### Modifications
| Fichier | Changement |
|---|---|
| `inventaire/models.py` | Stock (OneToOne Product), MouvementStock (journal immutable), 3 unités (UN/CL/GR), 6 types de mouvement |
| `inventaire/services.py` | StockService (décrémentation atomique F()), ResumeStockService (résumé clôture) |
| `inventaire/views.py` | StockViewSet (réception/perte/offert), DebitMetreViewSet (capteur Pi) |
| `inventaire/serializers.py` | 3 serializers DRF |
| `BaseBillet/models.py` | `module_inventaire` sur Configuration, `contenance` sur Price |
| `Administration/admin/inventaire.py` | MouvementStockAdmin (lecture seule) + StockInline |
| `Administration/admin/products.py` | StockInline sur POSProductAdmin + ajustement inventaire |
| `laboutik/views.py` | Décrémentation auto dans `_creer_lignes_articles()` |

## Tests à réaliser

### Test 1 : Activer le module inventaire
1. Aller dans le dashboard admin
2. Activer le toggle "Inventory"
3. Vérifier que la section "Inventaire" apparaît dans la sidebar

### Test 2 : Configurer le stock d'un produit POS
1. Aller dans un produit POS (ex : Bière Pression)
2. Vérifier que l'inline "Stock" apparaît au-dessus des tarifs
3. Créer un Stock : quantité=5000, unité=Centilitres, seuil=500
4. Sauvegarder

### Test 3 : Configurer la contenance des tarifs
1. Sur le même produit, éditer les tarifs
2. Pinte : contenance=50 (cl)
3. Demi : contenance=25 (cl)
4. Sauvegarder

### Test 4 : Vérifier la décrémentation à la vente
1. Ouvrir le POS, vendre 2 pintes
2. Vérifier dans l'admin que le stock a diminué de 100 cl (2 × 50)
3. Vérifier dans "Mouvements de stock" qu'un mouvement VE a été créé

### Test 5 : Ajustement inventaire depuis l'admin
1. Aller sur la fiche du produit POS
2. En bas, le formulaire "Ajustement inventaire" doit afficher le stock actuel
3. Saisir le stock réel (ex : 4500), motif "Inventaire physique"
4. Cliquer "Ajuster"
5. Vérifier que le stock est maintenant 4500 et qu'un mouvement AJ a été créé

### Test 6 : Actions rapides POS (API)
1. Via curl ou Postman, tester les endpoints :
   - `POST /api/inventaire/stock/{pk}/reception/` avec `{"quantite": 3000, "motif": "Fût 30L"}`
   - `POST /api/inventaire/stock/{pk}/perte/` avec `{"quantite": 50, "motif": "Renversé"}`
   - `POST /api/inventaire/stock/{pk}/offert/` avec `{"quantite": 25}`

### Test 7 : Stock bloquant
1. Configurer un produit avec `autoriser_vente_hors_stock=False`
2. Mettre le stock à 0
3. Tenter de vendre → doit échouer avec StockInsuffisant

### Test 8 : Endpoint débit mètre
1. `POST /api/inventaire/debit-metre/` avec `{"product_uuid": "...", "quantite_cl": 850, "capteur_id": "pi-01"}`
2. Vérifier que le stock diminue et qu'un mouvement DM est créé avec motif="pi-01"

## Compatibilité
- Aucun changement sur les produits sans Stock lié (billetterie, adhésions)
- Le branchement dans `_creer_lignes_articles()` utilise un try/except — si l'app inventaire n'est pas installée ou si le produit n'a pas de stock, aucun effet
- 27 tests pytest dédiés, 68 tests POS existants passent (0 régression)
