# Prompt Session 25 — Affichage visuel stock dans le POS

## Contexte : ce qui a été fait (sessions 23-24)

On a créé une app Django `inventaire` (TENANT_APP) pour gérer le stock des produits POS.

### Ce qui existe

**App `inventaire/`** avec :
- `models.py` : `Stock` (OneToOne → Product, related_name=`stock_inventaire`), `MouvementStock` (journal immutable, 6 types : VE/RE/AJ/OF/PE/DM), `UniteStock` (UN/CL/GR), `StockInsuffisant` exception
- `services.py` : `StockService` (décrémentation atomique `F()`, mouvements, ajustement), `ResumeStockService` (résumé clôture)
- `views.py` : `StockViewSet` (réception/perte/offert), `DebitMetreViewSet` (endpoint capteur Pi)
- `serializers.py` : 3 serializers DRF

**Champs ajoutés :**
- `BaseBillet.Configuration.module_inventaire` (BooleanField, toggle dashboard)
- `BaseBillet.Price.contenance` (PositiveIntegerField nullable — quantité consommée par vente en unité du stock, ex : pinte=50cl)

**Admin Unfold :**
- `StockInline` sur `POSProductAdmin` (quantité read-only, help_text "go to Stock movements > Add")
- `MouvementStockAdmin` avec ajout autorisé (formulaire : stock, type, quantité, motif) — le `save_model` passe par `StockService` pour l'atomicité
- Sidebar conditionnelle "Inventaire" si `module_inventaire=True`
- MODULE_FIELDS + carte dashboard

**Branchement POS :**
- Dans `laboutik/views.py`, `_creer_lignes_articles()` (ligne ~2760) : après chaque création de `LigneArticle`, un try/except appelle `StockService.decrementer_pour_vente()` si le produit a un `stock_inventaire`

**Méthodes utiles sur Stock :**
- `stock.est_en_alerte()` → True si `quantite <= seuil_alerte` et `quantite > 0`
- `stock.est_en_rupture()` → True si `quantite <= 0`
- `stock.autoriser_vente_hors_stock` → BooleanField (True par défaut = non bloquant)

**Tests :** 27 tests pytest inventaire, 427 total, 0 régression.

---

## Ce qu'il reste à faire : affichage visuel stock dans le POS

**Spec :** `TECH DOC/Laboutik sessions/Session 03 - Inventaire et stock/SPEC_INVENTAIRE.md` section 7.
**Détail :** `TECH DOC/Laboutik sessions/Session 03 - Inventaire et stock/SESSION_25_AFFICHAGE_VISUEL_POS.md`

### 1. Enrichir les données articles POS

Dans `laboutik/views.py`, trouver `_construire_donnees_articles()`. C'est la fonction qui construit la liste des articles affichés dans le POS.

- Ajouter `select_related('stock_inventaire')` sur la requête Product (éviter N+1)
- Pour chaque article du dict, ajouter :

```python
try:
    stock_du_produit = product.stock_inventaire
    article['stock_quantite'] = stock_du_produit.quantite
    article['stock_unite'] = stock_du_produit.unite
    article['stock_en_alerte'] = stock_du_produit.est_en_alerte()
    article['stock_en_rupture'] = stock_du_produit.est_en_rupture()
    article['stock_bloquant'] = (
        stock_du_produit.est_en_rupture()
        and not stock_du_produit.autoriser_vente_hors_stock
    )
    # Quantité lisible pour l'affichage
    article['stock_quantite_lisible'] = _formater_stock_lisible(
        stock_du_produit.quantite, stock_du_produit.unite
    )
except Stock.DoesNotExist:
    article['stock_quantite'] = None  # Pas de gestion de stock
```

Helper de formatage (au niveau module) :
- `UN` : "3 restants"
- `CL` : "1.5 L" (conversion cl → L si ≥ 100)
- `GR` : "800 g" ou "1.2 kg" si ≥ 1000

### 2. Adapter les templates tuiles articles

Explorer les templates dans `laboutik/templates/laboutik/cotton/` — les tuiles articles sont probablement dans un composant Cotton.

**3 états visuels :**

| État | Condition | Rendu |
|------|-----------|-------|
| **Normal** | `stock_quantite is None` ou au-dessus du seuil | Aucun indicateur, comportement actuel |
| **Alerte** | `stock_en_alerte` | Bordure ou pastille orange + quantité restante lisible |
| **Rupture non bloquante** | `stock_en_rupture` et pas `stock_bloquant` | Pastille rouge, produit reste cliquable |
| **Rupture bloquante** | `stock_bloquant` | Grisé + non cliquable (désactiver le onclick/hx-post) |

### 3. Rafraîchissement après vente

Après chaque vente, le stock du produit a changé. Explorer comment le POS rafraîchit déjà l'affichage (HTMX swap ? WebSocket ?) et s'y brancher pour que la pastille se mette à jour.

### 4. Accessibilité

- `aria-live="polite"` sur la zone de la pastille stock
- `data-testid="stock-badge-alerte"`, `data-testid="stock-badge-rupture"`, etc.

### 5. Règles du projet

- Skill `/djc` pour les conventions (FALC, commentaires bilingues, ViewSet explicite, etc.)
- Skill `/unfold` pour l'admin (mais cette session touche surtout les templates POS)
- Styles inline dans les templates admin Unfold (pas Tailwind custom)
- Templates POS : CSS dans `laboutik/static/css/`, pas de styles inline si possible
- `{% translate %}` pour tout texte visible
- Pas de logique métier côté JS — le serveur calcule l'état, le template affiche

### 6. Tests

- Tests pytest : vérifier que `_construire_donnees_articles()` enrichit bien les articles avec les données stock
- Tests E2E Playwright : vérifier les 3 états visuels (produit normal, alerte, rupture bloquante)
