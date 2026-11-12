# Grille des tables : un seul bouton « Continuer sans table » / Table grid: only "Continue without a table"

**Date :** 2026-11-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Le bouton « Service direct » quitte l'écran de choix de table du mode restaurant. Seul
« Continuer sans table » reste, en bouton principal (vert). Le paramètre GET `force_service_direct` de
`point_de_vente` n'existe plus. / The "Direct service" button is removed from the restaurant table grid;
"Continue without a table" is now the only (primary) action. The `force_service_direct` GET parameter is gone.

**Pourquoi / Why :** Les deux boutons vendaient de la même façon : sans table, VALIDER et le paiement suivent
le même chemin. « Service direct » faisait donc doublon. Il ouvrait en plus un écran sans la zone
d'alertes d'impression. / Both buttons sold the same way; "Direct service" was a duplicate and its screen lacked
the printing alerts area.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/tables_definition.html` | Retrait du lien « Service direct ». « Continuer sans table » passe en `--primaire`. Commentaire FLUX à jour |
| `laboutik/static/css/restaurant_interface.css` | Retrait de `.tables-foot-bt--secondaire`, qui ne sert plus |
| `laboutik/views.py` | `point_de_vente` : retrait de `force_service_direct`. Seul `pv.service_direct` choisit l'écran de vente directe |
| `laboutik/templates/laboutik/views/tables.html` | Commentaire à jour : sans le bouton continuer, il ne reste que les tuiles |
| `tests/pytest/test_resto_addition_table.py` | 2 tests : un seul bouton dans le pied de la grille ; `force_service_direct` ignoré |

---

## Comment tester (a la main) / Manual test
### Test 1 — scenario nominal
1. Ouvrir un point de vente avec `service_direct=False` (données `create_test_pos_data`).
2. Vérifier que la grille des tables n'a qu'un bouton en bas, « Continuer sans table », en vert.
3. Cliquer dessus : la grille disparaît.
4. Ajouter un article, cliquer sur VALIDER, payer en espèces. Après le succès, le panier se vide et la grille
   ne revient pas.
5. Cliquer sur « Tables » dans le header : la grille revient.

### Test 2 — cas limites
- Ajouter `&force_service_direct=true` à la main dans l'URL : l'écran restaurant s'affiche quand même, avec la grille.
- Un point de vente avec `service_direct=True` ouvre toujours l'écran de vente directe, sans grille.

### Verifs DB / Playwright
- Pas de changement en base.
- `docker exec lespass_django poetry run pytest tests/pytest/test_resto_addition_table.py -v`
