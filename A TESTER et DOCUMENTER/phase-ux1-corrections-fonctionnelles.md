# Phase UX 1 — Corrections fonctionnelles (Session 1)

**Branche** : `integration_laboutik`
**Date** : 2026-03-16
**Audit FALC** : conforme (stack-ccc)

## Fichiers modifies

| Fichier | Modification |
|---------|-------------|
| `laboutik/static/js/articles.js` | `articlesDisplayCategory()` implemente (filtre par classe CSS `cat-<uuid>`) |
| `laboutik/templates/cotton/categories.html` | Highlight categorie active (classe `.category-item-selected`, bordure + fond) |
| `laboutik/templates/cotton/bt/paiement.html` | `floatformat:2` + `tabular-nums` sur le total |
| `laboutik/templates/laboutik/partial/hx_confirm_payment.html` | Suppression `uuid_transaction` affiche en clair |
| `laboutik/templates/laboutik/partial/hx_card_feedback.html` | `floatformat:2` + `tabular-nums` sur les soldes |

## Scenarios de test manuel

### 1. Filtre par categorie

1. Ouvrir `https://lespass.tibillet.localhost/laboutik/caisse/point_de_vente/`
2. Cliquer sur **Bar** dans la sidebar
   - **Attendu** : seuls les articles de la categorie Bar sont visibles (Biere, Coca, Eau, Jus, Limonade)
3. Cliquer sur **Snacks**
   - **Attendu** : seuls Chips, Cacahuetes, Cookies sont visibles
4. Cliquer sur **Vins & Spiritueux**
   - **Attendu** : seuls Vin rouge, Vin blanc, Pastis sont visibles
5. Cliquer sur **Tous**
   - **Attendu** : tous les articles sont visibles (y compris Recharges et Adhesions)

### 2. Highlight categorie active

1. Cliquer sur une categorie
   - **Attendu** : la categorie cliquee a un fond legerement plus clair et une bordure gauche verte
2. Cliquer sur une autre categorie
   - **Attendu** : l'ancienne perd le highlight, la nouvelle le gagne
3. "Tous" doit etre highlight par defaut au chargement

### 3. Formatage du total (2 decimales)

1. Ajouter des articles au panier pour un total de 6,50 EUR
2. Cliquer VALIDER
   - **Attendu** : l'ecran des moyens de paiement affiche "6,50 EUR" (pas "6,5 EUR")
3. Tester avec un total rond (ex: 11,00 EUR)
   - **Attendu** : "11,00 EUR" (pas "11,0 EUR")

### 4. UUID masque sur confirmation especes

1. Ajouter des articles, cliquer VALIDER, choisir ESPECE
   - **Attendu** : l'ecran de confirmation N'affiche PAS "uuid_transaction = ..."
   - **Attendu** : le texte "Confirmez le paiement par espece" et le champ "somme donnee" sont visibles

### 5. Formatage soldes retour carte

1. Cliquer CHECK CARTE, scanner une carte (bouton simulation)
   - **Attendu** : les soldes s'affichent avec 2 decimales (ex: "0,00" au lieu de "0,0")
   - **Attendu** : les chiffres utilisent `tabular-nums` (alignement propre)

## Tests automatises

- **pytest** : 46 tests verts (non-regression confirmee)
- **Playwright** : test de filtre categorie a ecrire dans une session ulterieure

## Issues pre-existantes (hors scope)

- `categories.html:25` : classe `.active` inutilisee en CSS
- `categories.html:126` : typo `.categorie-nom` vs `.category-nom`
- `categories.html:43` : commentaire FR seul (pas bilingue)
