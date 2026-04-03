# Session 25 — Affichage visuel stock dans le POS

> Prérequis : Sessions 23-24 terminées (app inventaire, modèles, services, admin, API).

## Objectif

Rendre l'état du stock visible directement dans l'interface POS :
- Pastille orange quand le stock est sous le seuil d'alerte
- Pastille rouge quand le stock est à zéro ou négatif
- Produit grisé et non cliquable si stock bloquant (`autoriser_vente_hors_stock=False`) et stock ≤ 0
- Quantité restante affichée en unité lisible (L, kg, pièces)

## Travail à faire

### 1. Enrichir les données articles POS

Dans `laboutik/views.py`, dans `_construire_donnees_articles()` :
- Ajouter `select_related('stock_inventaire')` sur la requête Product
- Pour chaque article, ajouter dans le dict :
  - `stock_quantite` : quantité actuelle (ou None si pas de Stock)
  - `stock_unite` : unité (UN/CL/GR)
  - `stock_en_alerte` : booléen
  - `stock_en_rupture` : booléen
  - `stock_bloquant` : rupture ET pas autorisé hors stock
  - `stock_quantite_lisible` : texte formaté ("1.5 L", "800 g", "3 restants")

### 2. Adapter les templates tuiles articles

Localiser le template des tuiles POS (probablement dans `laboutik/templates/laboutik/cotton/`).

Ajouter un rendu conditionnel :

| État | Condition | Rendu |
|------|-----------|-------|
| Normal | `stock_quantite > seuil` ou pas de stock | Aucun indicateur |
| Alerte | `stock_en_alerte` | Bordure/pastille orange + quantité |
| Rupture non bloquante | `stock_en_rupture` et pas bloquant | Pastille rouge, cliquable |
| Rupture bloquante | `stock_bloquant` | Grisé + barré, non cliquable |

### 3. Rafraîchissement après vente

Après chaque vente, le POS doit mettre à jour l'affichage du produit concerné.
Explorer le mécanisme existant (HTMX swap ou WebSocket) pour s'y brancher.

### 4. Accessibilité

- `aria-live="polite"` sur la zone quantité
- `data-testid` sur les pastilles stock

### 5. Tests

- Tests E2E Playwright : vérifier les 3 états visuels
- Vérifier que les produits sans stock ne sont pas affectés

## Fichiers à explorer avant de commencer

- `laboutik/views.py` : `_construire_donnees_articles()` — comment les articles sont construits
- Templates POS : `laboutik/templates/laboutik/cotton/` — tuiles articles
- `laboutik/static/css/` — styles existants des tuiles
- Mécanisme de rafraîchissement post-vente (HTMX ou WebSocket)

## Spec de référence

`TECH DOC/Laboutik sessions/Session 03 - Inventaire et stock/SPEC_INVENTAIRE.md` — Section 7.
