# Admin : gérer le stock depuis la fiche produit de caisse, et le voir dans la liste

**Date :** 2026-09-29
**Migration :** Non / No
**Plan :** options A (sans onglets) et B du plan « Stock dans l'admin Produits de caisse ».

## Résumé / Summary

**Quoi / What :**

- **A — Section « Stock » dans la fiche produit de caisse et dans la fiche fût.**
  Nouvelle section en bas de la fiche (pas d'onglets, à la demande du mainteneur).
  - Produit sans stock : case « Suivre le stock », quantité de départ, unité,
    seuil d'alerte, vente hors stock. À l'enregistrement, le stock est créé par
    `StockService.creer_stock_initial` : stock à 0, puis mouvement Réception
    « Stock initial ». La quantité de départ apparaît donc dans le journal.
  - Produit avec stock : réglages (unité, seuil, vente hors stock), enregistrés
    avec le bouton Enregistrer du produit, **sans jamais réécrire la quantité**
    (`update_fields`), puis caisses prévenues par WebSocket. En dessous, le même
    panneau d'opérations que la fiche Stock (Réception, Ajustement, Offert,
    Perte/casse + derniers mouvements), qui part tout de suite en HTMX.
  - Les champs Quantité / Motif du panneau n'appartiennent à aucun formulaire
    (`form="stock-operations-hors-formulaire"`) : Entrée ne soumet pas le produit,
    et ils ne sont pas envoyés avec lui. L'événement `input` est arrêté sur le
    conteneur (phase de capture) : taper une quantité ne déclenche plus l'alerte
    « modifications non enregistrées » d'Unfold (vrai aussi sur la fiche Stock).
  - Le panneau affiche maintenant le stock actuel et son état (OK / Stock bas / Épuisé).
  - L'inline `StockInline` (page d'ajout) est supprimé : la section Stock le remplace.
    Il laissait entrer la quantité de départ **sans mouvement** dans le journal.
  - `StockAdmin.save_model` passe aussi par `creer_stock_initial` (une seule logique).
  - Fiche Stock : le nom de l'article renvoie vers la section Stock de sa fiche
    (fiche fût pour un fût).
  - Le lien « Voir tous les mouvements » n'est plus écrit en dur (`{% url %}`).
- **B — Colonne « Stock » et filtre « État du stock » dans les listes Produits de caisse et Fûts.**
  Badge coloré (rouge Épuisé, orange sous le seuil, vert OK, « — » si non suivi).
  Un clic ouvre la fiche sur l'ancre `#section-stock`. Tri par quantité.
  Filtre Épuisé / Stock bas / OK / Non suivi. `select_related("stock_inventaire")`
  pour éviter une requête par ligne. Pas d'édition de quantité dans la liste :
  chaque changement reste un mouvement tracé.

**Pourquoi / Why :** modifier le stock sans quitter les produits de caisse, et voir
d'un coup d'œil ce qui manque.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/stock_fiche_produit.py` | **Nouveau.** Mixin de formulaire (champs `stock_*`), fieldset, panneau, sauvegarde, badge de liste, `EtatStockFilter` |
| `Administration/admin/products.py` | `POSProductForm` / `FutProductForm` héritent du mixin ; `POSProductAdmin` / `FutProductAdmin` : `get_fieldsets`, `get_readonly_fields`, `save_model`, colonne + filtre, `select_related` ; `get_inlines` (StockInline) retiré |
| `Administration/admin/inventaire.py` | `StockInline` supprimé ; `StockAdmin.save_model` via `creer_stock_initial` ; lien article → `#section-stock` |
| `inventaire/services.py` | Nouveau `StockService.creer_stock_initial` |
| `Administration/templates/admin/inventaire/stock_actions.html` | Script : l'alerte « non enregistré » ignore le panneau |
| `Administration/templates/admin/inventaire/stock_actions_partial.html` | Stock actuel + état, champs hors formulaire, CSRF conditionnel, lien via `{% url %}` |
| `tests/pytest/test_stock_fiche_produit.py` | **Nouveau.** 14 tests (service, sauvegarde, rendu fiche / ajout, POST de création, badge, filtre, select_related) |
| `tests/e2e/test_admin_stock_fiche_produit.py` | **Nouveau.** 3 tests (réception sans recharger, Entrée + pas d'alerte, badge → ancre) |

### Traductions
Nouveaux textes en `_()` / `{% translate %}` (msgid en français). Les fichiers `.po`
n'ont pas été modifiés : à faire par le mainteneur.

### Migration
- **Migration nécessaire / Migration required :** Non / No
