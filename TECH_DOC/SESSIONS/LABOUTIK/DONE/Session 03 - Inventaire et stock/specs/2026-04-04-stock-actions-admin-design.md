# Formulaire d'actions stock dans l'admin Stock — Design

## Objectif

Permettre au caissier de gérer le stock directement depuis la fiche Stock dans l'admin Unfold : réception, ajustement, offert, perte/casse. Chaque action est un formulaire HTMX qui appelle un ViewSet via `StockService`. L'historique des mouvements est traçable via la vue "Mouvements de stock".

## Architecture

```
Stock changeform (Unfold admin)
  └── change_form_after_template: "admin/inventaire/stock_actions.html"
        ├── Texte d'aide dépliable (explique les 4 actions)
        ├── Input quantité (nombre positif, requis)
        ├── Input motif (texte, optionnel)
        ├── 4 boutons colorés (hx-post vers StockActionViewSet)
        ├── Lien vers les mouvements de cet article (filtré)
        └── 5 derniers mouvements en aperçu
              │
              ▼ hx-post
        StockActionViewSet.create()
        → StockService.creer_mouvement() / ajuster_inventaire()
        → Réponse HTML partielle (feedback + formulaire rechargé)
```

## Fichiers

| Fichier | Action | Rôle |
|---------|--------|------|
| `inventaire/views.py` | Modifier | Ajouter `StockActionViewSet` |
| `TiBillet/urls_tenants.py` | Modifier | Route POST `/admin/inventaire/stock/<uuid>/action/` |
| `Administration/templates/admin/inventaire/stock_actions.html` | Créer | Template after : formulaire + aide + aperçu mouvements |
| `Administration/templates/admin/inventaire/stock_actions_partial.html` | Créer | Partial HTMX renvoyé après action (feedback + formulaire) |
| `Administration/templates/admin/inventaire/mouvements_list_before.html` | Créer | Template before sur MouvementStockAdmin : aide sur le filtre |
| `Administration/admin/inventaire.py` | Modifier | `StockAdmin.change_form_after_template` + contexte, `MouvementStockAdmin.list_before_template` |
| `Administration/admin/products.py` | Modifier | Retirer `StockInline` du changeform POSProduct (garder sur add) |
| `TECH DOC/A DOCUMENTER/inventaire-actions-stock.md` | Créer | Documentation technique et utilisateur |

## Formulaire (template after sur Stock changeform)

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Opérations de stock — {nom du produit}             │
│                                                     │
│  ▸ Aide (dépliable)                                │
│  ┌─────────────────────────────────────────────────┐│
│  │ • Réception : ajoute du stock après livraison   ││
│  │ • Ajustement : remplace la quantité actuelle    ││
│  │   par le stock réel compté (inventaire)         ││
│  │ • Offert : retire du stock. Attention : cette   ││
│  │   action n'apparaît PAS dans les ventes ni les  ││
│  │   rapports comptables. Pour offrir un produit   ││
│  │   avec traçabilité comptable, utilisez le POS.  ││
│  │ • Perte/casse : retire du stock (casse, périmé) ││
│  │                                                 ││
│  │ Chaque action est tracée dans les mouvements    ││
│  │ de stock (voir le lien ci-dessous).             ││
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  Quantité : [_______]                               │
│  Motif :    [_______________________] (optionnel)   │
│                                                     │
│  [🟢 Réception] [🟡 Ajustement] [🔵 Offert] [🔴 Perte]│
│                                                     │
│  ── 5 derniers mouvements ──                        │
│  • 03/04 -2 UN (Vente)                             │
│  • 03/04 +10 UN (Réception) — "Livraison Metro"   │
│  • 02/04 -1 UN (Offert) — "Client fidèle"         │
│                                                     │
│  → Voir tous les mouvements de cet article          │
└─────────────────────────────────────────────────────┘
```

### Comportement

- Styles inline (contrainte Unfold — pas de classes Tailwind custom)
- Chaque bouton fait un `hx-post` vers `/admin/inventaire/stock/{uuid}/action/` avec `type_mouvement` dans un hidden ou dans `hx-vals`
- `hx-target` = le conteneur du formulaire entier (`#stock-actions-container`)
- `hx-swap="innerHTML"` — le partial renvoyé contient le feedback + le formulaire rechargé
- `aria-live="polite"` sur la zone de feedback
- Le lien "Voir tous les mouvements" pointe vers `/admin/inventaire/mouvementstock/?stock__uuid__exact={uuid}`
- Les 5 derniers mouvements donnent du contexte immédiat

### Feedback après action

Le partial `stock_actions_partial.html` contient :
- Un bandeau de succès (vert, inline styles) avec le résumé de l'action : "Réception +10 Pièces. Stock actuel : 25 Pièces"
- Le formulaire rechargé (inputs vidés, mouvements mis à jour)
- En cas d'erreur (validation) : bandeau rouge + formulaire avec les erreurs

## ViewSet

```python
class StockActionViewSet(viewsets.ViewSet):
    """
    Endpoint pour les actions manuelles de stock depuis l'admin.
    POST /admin/inventaire/stock/<uuid>/action/
    """
    permission_classes = [HasAdminAccess]

    def create(self, request, stock_uuid=None):
        # 1. Récupérer le Stock
        # 2. Valider avec StockActionSerializer (type_mouvement, quantite, motif)
        # 3. Dispatcher vers StockService selon type_mouvement :
        #    - AJ → StockService.ajuster_inventaire(stock_reel=quantite)
        #    - RE/OF/PE → StockService.creer_mouvement(type, quantite)
        # 4. Relire le stock (refresh_from_db)
        # 5. Rendre le partial HTML avec feedback + formulaire rechargé
```

Le serializer valide :
- `type_mouvement` : ChoiceField limité à RE/AJ/OF/PE
- `quantite` : IntegerField, min_value=0
- `motif` : CharField, required=False

## POSProduct — retirer l'inline en mode change

Dans `POSProductAdmin.get_inlines()` : inclure `StockInline` uniquement si `obj is None` (mode add). En mode change, le stock se gère depuis la page Stock dédiée.

## MouvementStockAdmin — template before aide

Ajouter `list_before_template = "admin/inventaire/mouvements_list_before.html"` sur `MouvementStockAdmin`.

Contenu du template :

```
┌─────────────────────────────────────────────────────┐
│  ℹ️ Par défaut, seuls les mouvements manuels sont   │
│  affichés (réception, ajustement, offert, perte).   │
│  Les ventes et débits mètre (automatiques) sont     │
│  masqués. Utilisez le filtre "Type de mouvement"    │
│  → "Tout afficher" pour voir l'historique complet.  │
│                                                     │
│  Chaque mouvement est créé automatiquement lors     │
│  d'une opération de stock (vente POS, réception     │
│  dans la fiche Stock, etc.). Ce journal est en      │
│  lecture seule.                                     │
└─────────────────────────────────────────────────────┘
```

## Distinction offert admin vs offert POS

- **Offert via cette page admin** : retire du stock uniquement. Pas de `LigneArticle`, pas de trace comptable. Utiliser pour les pertes non comptabilisées, dégustations internes, etc.
- **Offert via le POS** : crée une `LigneArticle` avec `methode_caisse="OF"`, apparaît dans les rapports comptables et la clôture de caisse. Utiliser pour les offerts clients traçables.

Le texte d'aide dans le template explique cette distinction.

## Traçabilité

Toute action (réception, ajustement, offert, perte) crée un `MouvementStock` visible dans la liste des mouvements. Le lien "Voir tous les mouvements de cet article" depuis la fiche Stock permet de consulter l'historique filtré.

## Documentation

`TECH DOC/A DOCUMENTER/inventaire-actions-stock.md` :
- **Section technique** : architecture, fichiers modifiés, ViewSet, serializer, template, flux HTMX
- **Section utilisateur** : comment faire une réception, un ajustement, un offert, une perte. Explication de la différence offert admin vs offert POS. Comment consulter l'historique.
- **Scénarios de test** : 6 scénarios manuels (réception, ajustement hausse/baisse, offert, perte, consultation historique)

## Tests

- Test pytest : `StockActionViewSet` — 4 types d'action + validation erreur
- Pas de test E2E pour cette itération (template admin Unfold)

## Hors scope

- Pas de modification du formulaire add de MouvementStockAdmin (on le garde tel quel, il reste accessible)
- Pas de suppression de MouvementStockAdmin (reste en lecture seule)
- Pas de modification du broadcast WebSocket (déjà en place depuis la session stock visuel)
