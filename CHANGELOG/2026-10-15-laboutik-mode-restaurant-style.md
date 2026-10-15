# LaBoutik : refonte visuelle du mode restaurant / Restaurant mode visual redesign

**Date :** 2026-10-15
**Migration :** Non

## Resume / Summary

**Quoi / What :** Les écrans propres au mode restaurant adoptent le style de la refonte
caisse (jetons OKLCH de `palette.css`, relief « touche », Luciole). (1) Le choix de table
devient une grille plein écran posée sous l'en-tête : tuile par table avec liseré, pastille
**et** libellé de statut (Libre / Occupée / Servie), légende, tuile « Nouvelle table » en
pointillés, pied « Continuer sans table » + « Service direct », message si aucune table.
(2) La modale « Nouvelle table » est restylée (libellé, champ 56 px, focus automatique).
(3) Les zones du bas (actions carte/table, clavier de paiement, voyants) passent en vrais
`<button>`, libellés traduisibles et icônes, au style des touches de la refonte.
HTML + CSS uniquement : aucune vue ni aucun JS modifié.
/ Restaurant-only screens adopt the sales-screen redesign style. Full-screen table
picker grid with status shown as text + colour, restyled "new table" modal, and the
bottom areas rebuilt as real buttons. HTML and CSS only.

**Pourquoi / Why :** Le mode restaurant était resté sur l'ancien style (tuiles grises
90 px, police jamais chargée, statut en couleur seule, `<style>` inline). La modale de
tables bouclait sur `tables_list`, absent du contexte : aucune table ne s'affichait.
Le gabarit lit maintenant `tables`, la variable que la vue fournit.
/ Restaurant mode kept the old style, and the table modal looped over a variable
missing from the context, so no table was ever shown.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/tables_definition.html` | Réécrit : grille plein écran, lit `tables`, attribut `avec_bouton_continuer`, `data-testid` |
| `laboutik/templates/laboutik/views/restaurant_interface.html` | Commentaire de flux FALC |
| `laboutik/templates/laboutik/views/tables.html` | Réutilise le composant (bouton « Continuer » caché) ; retire le markup obsolète |
| `laboutik/templates/cotton/bt/table.html` | Classe `.table-tile`, plus de style inline |
| `laboutik/templates/laboutik/partial/win_bottom_left.html` | `<button>`, icônes, libellés traduits, `data-testid` |
| `laboutik/templates/laboutik/partial/win_bottom_right.html` | Idem ; « OFFIR » → « Offrir » |
| `laboutik/static/css/restaurant_interface.css` | Section « Grille des tables » ; fond `--bg` |
| `laboutik/static/css/win_bottom_left.css`, `win_bottom_right.css` | Réécrits, règles préfixées par l'id de zone |
| `laboutik/static/css/palette.css` | Jetons alias `--table-libre/occupee/servie(-wash)` |
| `laboutik/static/css/views.css` | Retrait des règles `.table-bouton/.table-nom/.table-etat/#tables-container`, plus utilisées |

---

## Comment tester (a la main) / Manual test

Prérequis : un point de vente avec `service_direct = False` et `accepte_commandes = True`
(ex. « Terrasse » de `create_test_pos_data`) et quelques `Table` créées dans l'admin, avec
des statuts différents.

### Test 1 — grille des tables
1. Ouvrir la caisse sur ce point de vente.
2. La grille « Choisir une table » s'affiche sous l'en-tête, avec la légende.
3. Chaque table montre son nom et son statut écrit (Libre / Occupée / Servie).
4. Cliquer une table → spinner → écran « Commande table X ».

### Test 2 — nouvelle table et sortie
1. « Nouvelle table » → la modale s'ouvre, le curseur est dans le champ.
2. Saisir un nom, Valider → la grille disparaît, l'écran de vente est utilisable.
3. Recharger, cliquer « Continuer sans table » → même résultat sans nouvelle table.
4. Recharger, cliquer « Service direct » → écran de vente direct.

### Test 3 — cas limites
- Aucune table : seule la tuile « Nouvelle table » + un message explicatif.
- Largeurs 320 / 375 / 768 / 1280 px : pas de défilement horizontal, boutons du pied
  empilés sous 600 px, noms longs coupés sur deux lignes avec « … ».
- Clavier : Tab parcourt les tuiles, l'anneau de focus bleu est visible.

### Verifs DB / Playwright
- Aucun test E2E ne couvre encore le mode restaurant (tous les PV de test sont en service
  direct). Sélecteurs prêts : `resto-tables-screen`, `resto-table-tile-<uuid>`,
  `resto-table-add`, `resto-add-table-input`, `resto-add-table-submit`, `resto-table-skip`,
  `resto-table-service-direct`.
