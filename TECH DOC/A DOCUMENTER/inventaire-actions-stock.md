# Gestion de stock — Actions manuelles depuis l'admin

## 1. Documentation technique

### Architecture

```
Stock changeform (Unfold admin)
  └── change_form_after_template: stock_actions.html
        ├── Texte d'aide dépliable
        ├── Input quantité + motif
        ├── 4 boutons (hx-post)
        └── Aperçu 5 derniers mouvements
              │
              ▼ hx-post /admin/inventaire/stock/<uuid>/action/
        stock_action_view() dans inventaire/views.py
        → StockActionSerializer (validation DRF)
        → StockService.creer_mouvement() ou ajuster_inventaire()
        → Partial HTML renvoyé (stock_actions_partial.html)
```

### Fichiers

| Fichier | Rôle |
|---------|------|
| `inventaire/views.py` | `stock_action_view()` — vue Django qui reçoit le POST HTMX, valide, appelle StockService, rend le partial |
| `inventaire/serializers.py` | `StockActionSerializer` — valide type_mouvement (RE/AJ/OF/PE), quantite (>=0), motif (optionnel) |
| `inventaire/services.py` | `StockService` — update atomique F(), création MouvementStock |
| `Administration/admin/inventaire.py` | `StockAdmin` — change_form_after_template, changeform_view (contexte), get_urls (route action) |
| `Administration/admin/inventaire.py` | `MouvementStockAdmin` — list_before_template (aide filtre), filtre TypeMouvementFilter |
| `Administration/templates/admin/inventaire/stock_actions.html` | Template wrapper (conteneur #stock-actions-container) |
| `Administration/templates/admin/inventaire/stock_actions_partial.html` | Partial HTMX : formulaire + feedback + aide + aperçu mouvements |
| `Administration/templates/admin/inventaire/mouvements_list_before.html` | Bandeau d'aide au-dessus de la liste des mouvements |

### Flux d'une action

1. Le caissier est sur la fiche Stock d'un article
2. Il saisit une quantité et un motif (optionnel)
3. Il clique sur un des 4 boutons (Réception, Ajustement, Offert, Perte)
4. Le bouton fait un `hx-post` vers `/admin/inventaire/stock/<uuid>/action/` avec `type_mouvement`, `quantite`, `motif`
5. `stock_action_view()` valide avec `StockActionSerializer`
6. Selon le type :
   - **AJ** : `StockService.ajuster_inventaire(stock_reel=quantite)` — remplace le stock
   - **RE/OF/PE** : `StockService.creer_mouvement(type, quantite)` — ajoute ou retire
7. Le stock est relu depuis la DB (`refresh_from_db`)
8. Le partial HTML est renvoyé avec un bandeau de succès + formulaire rechargé

### Route admin

La route est enregistrée via `StockAdmin.get_urls()` (pas via le router DRF). Elle bénéficie de `admin_site.admin_view()` qui vérifie l'authentification admin et le CSRF.

### Distinction offert admin vs offert POS

| | Offert admin (cette page) | Offert POS (bouton dans la caisse) |
|---|---|---|
| Effet sur le stock | Retire du stock | Retire du stock |
| LigneArticle créée | Non | Oui |
| Apparaît dans les ventes | Non | Oui |
| Apparaît dans les rapports comptables | Non | Oui |
| Apparaît dans la clôture de caisse | Non | Oui |
| Mouvement de stock créé | Oui (type OF) | Oui (type VE, via vente) |
| Cas d'usage | Dégustations internes, pertes non comptabilisées | Offerts clients traçables |

### Filtre mouvements

Le filtre `TypeMouvementFilter` masque par défaut les types automatiques (VE=vente, DM=débit mètre). Le bandeau `mouvements_list_before.html` explique ce comportement.

---

## 2. Documentation utilisateur

### Accéder à la gestion de stock

1. Aller dans **Admin → Inventaire → Stocks**
2. Cliquer sur le nom de l'article à gérer

### Les 4 actions

#### Réception (bouton vert)
**Quand :** Vous recevez une livraison.
**Exemple :** Vous recevez 24 bières → Quantité = 24 → Bouton "Réception"
**Résultat :** Le stock passe de 20 à 44.

#### Ajustement (bouton orange)
**Quand :** Vous faites un inventaire physique et le stock réel est différent du stock système.
**Exemple :** Vous comptez 18 bières alors que le système affiche 20 → Quantité = 18 → Bouton "Ajustement"
**Résultat :** Le stock passe de 20 à 18. Le système crée un mouvement de -2.

#### Offert (bouton bleu)
**Quand :** Vous offrez un produit en interne (dégustation, cadeau équipe).
**Exemple :** Vous offrez 2 bières pour une dégustation → Quantité = 2 → Bouton "Offert"
**Résultat :** Le stock passe de 20 à 18.

**Attention :** Cette action **n'apparaît PAS** dans les ventes ni dans les rapports comptables. Pour offrir un produit à un client avec traçabilité comptable, utilisez le bouton "Offrir" dans le POS (point de vente).

#### Perte/casse (bouton rouge)
**Quand :** Un produit est cassé, périmé ou perdu.
**Exemple :** 3 bouteilles cassées → Quantité = 3 → Bouton "Perte/casse"
**Résultat :** Le stock passe de 20 à 17.

### Consulter l'historique

Chaque action crée automatiquement un mouvement de stock traçable.

- Depuis la fiche Stock : les 5 derniers mouvements sont affichés en bas du formulaire
- Lien "Voir tous les mouvements de cet article" → ouvre la liste complète filtrée
- Depuis **Admin → Inventaire → Mouvements de stock** : tous les mouvements de tous les articles

### Le filtre des mouvements

Par défaut, la liste des mouvements ne montre que les actions manuelles (réception, ajustement, offert, perte). Les ventes automatiques (depuis le POS) et les débits mètre (depuis le capteur) sont masqués.

Pour voir tout l'historique : utiliser le filtre "Type de mouvement" → "Tout afficher".

### Paramétrer un article

Depuis **Admin → Inventaire → Stocks**, vous pouvez modifier directement dans la liste :
- **Seuil d'alerte** : le POS affiche une pastille orange quand le stock descend sous ce seuil
- **Autoriser vente hors stock** : si décoché, le produit est grisé et non cliquable dans le POS quand le stock est à 0

---

## 3. Scénarios de test manuels

### Test 1 : Réception
1. Aller sur Admin → Inventaire → Stocks → cliquer sur un article
2. Saisir Quantité = 10, Motif = "Livraison Metro"
3. Cliquer "Réception"
4. Vérifier : bandeau vert, stock augmenté de 10, mouvement visible en bas

### Test 2 : Ajustement à la hausse
1. Stock actuel = 20
2. Saisir Quantité = 25
3. Cliquer "Ajustement"
4. Vérifier : stock = 25, mouvement +5 créé

### Test 3 : Ajustement à la baisse
1. Stock actuel = 20
2. Saisir Quantité = 15
3. Cliquer "Ajustement"
4. Vérifier : stock = 15, mouvement -5 créé

### Test 4 : Offert
1. Saisir Quantité = 2, Motif = "Dégustation"
2. Cliquer "Offert"
3. Vérifier : stock diminué de 2, mouvement type OF
4. Vérifier : aucune LigneArticle créée (pas de trace comptable)

### Test 5 : Perte/casse
1. Saisir Quantité = 3, Motif = "Casse"
2. Cliquer "Perte/casse"
3. Vérifier : stock diminué de 3, mouvement type PE

### Test 6 : Historique filtré
1. Cliquer "Voir tous les mouvements de cet article"
2. Vérifier : la liste est filtrée sur cet article
3. Le filtre par défaut masque les ventes auto

### Test 7 : POSProduct sans StockInline en mode change
1. Aller sur Admin → POS products → modifier un produit existant
2. Vérifier : pas de section "Stock" dans le formulaire
3. Aller sur Admin → POS products → ajouter un nouveau produit
4. Vérifier : la section "Stock" est présente (inline pour créer le stock initial)

```bash
# Tests automatisés
docker exec lespass_django poetry run pytest tests/pytest/test_stock_actions_admin.py -v
```
