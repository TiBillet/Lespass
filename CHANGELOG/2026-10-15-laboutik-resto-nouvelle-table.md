# LaBoutik : la tuile « Nouvelle table » crée et choisit la table / "New table" tile creates and selects the table

**Date :** 2026-10-15
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- La modale « Nouvelle table » poste vers la nouvelle route
  `POST /laboutik/caisse/ajouter_table/` (`CaisseViewSet.ajouter_table`). La vue crée la
  `Table` (libre, `ephemere=True`) puis redirige en GET vers `point_de_vente` avec
  `id_table` : la table est choisie et l'écran « Commande table X » s'ouvre.
  - Nom vide → « Table N » (premier numéro libre).
  - Nom déjà pris → la table existante est reprise avec son statut ; archivée, elle
    revient dans la grille.
- Le bouton **Tables** de l'en-tête affiche le nom de la table choisie (`nom_table`
  ajouté au contexte de `point_de_vente`). Un clic ramène à la grille pour choisir ou
  créer une autre table.
- Le script `addTable()` (champ caché `nouvelle_table` dans le panier, lu par aucune
  vue) est supprimé.

/ The "new table" modal POSTs to the new ajouter_table route, which creates the table
and redirects with id_table. The header button shows the selected table.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Nouvelle action `ajouter_table` ; `point_de_vente` : `nom_table` dans le contexte |
| `laboutik/templates/cotton/tables_definition.html` | Modale en vrai formulaire, `addTable()` retiré |
| `laboutik/templates/cotton/header.html` | Bouton Tables : nom de la table choisie |
| `laboutik/static/css/restaurant_interface.css` | Style de l'aide du champ |
| `tests/pytest/test_resto_touches_et_tables.py` | +4 tests |

---

## Comment tester (a la main) / Manual test

1. Ouvrir un PV resto (`service_direct = False`, `accepte_commandes = True`).
2. « Nouvelle table » → saisir « Terrasse 4 » → « Créer et choisir » → spinner, écran de
   vente, bouton en-tête « Terrasse 4 ».
3. Cliquer ce bouton → la grille montre « Terrasse 4 — Libre ». Choisir une autre
   table ou en créer une autre.
4. Nouvelle table avec un nom vide → « Table N ». Même nom qu'une table existante →
   aucune nouvelle table, l'existante est choisie.
5. Recharger la page après la création → pas de doublon (redirection GET).
