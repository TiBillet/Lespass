# Rapport temps reel — Session en cours

## Ce qui a ete fait
Ajout d'un bouton "Rapport en cours" sur la page admin des clotures de caisse.
Le bouton ouvre un nouvel onglet avec un rapport comptable complet calcule
en temps reel depuis la derniere cloture, via RapportComptableService.

### Modifications
| Fichier | Changement |
|---|---|
| `laboutik/views.py` | Action `rapport_temps_reel` dans CaisseViewSet |
| `Administration/templates/admin/cloture/rapport_temps_reel.html` | Page HTML standalone |
| `Administration/templates/admin/cloture/changelist_before.html` | Bouton vert "Rapport en cours" |
| `Administration/admin/laboutik.py` | URL injectee dans contexte changelist |

## Tests a realiser

### Test 1 : Bouton visible sur la changelist
1. Aller sur /admin/laboutik/cloturecaisse/
2. Verifier qu'un bouton vert "Rapport en cours" apparait a cote des boutons d'export
3. Le bouton doit avoir une icone "monitoring"

### Test 2 : Rapport avec ventes en cours
1. S'assurer qu'il y a des ventes depuis la derniere cloture
2. Cliquer sur "Rapport en cours" (ouvre un nouvel onglet)
3. Verifier : bandeau jaune "Rapport temporaire" en haut
4. Verifier : les 13 sections sont presentes (totaux, detail ventes, TVA, solde caisse, recharges, adhesions, remboursements, habitus, billets, synthese, operateurs, ventilation par PV, infos legales)
5. Verifier : le header affiche la periode (debut session -> maintenant)

### Test 3 : Rapport sans ventes
1. Cloturer la caisse pour que toutes les ventes soient couvertes
2. Cliquer sur "Rapport en cours"
3. Verifier : message "Aucune vente depuis la derniere cloture"

### Test 4 : Impression
1. Ouvrir le rapport en cours
2. Ctrl+P pour imprimer
3. Verifier que le rendu est lisible (pas de coupure de tableau)

## Compatibilite
- Pas de migration necessaire
- Pas d'impact sur les clotures existantes (lecture seule)
- Le rapport n'est pas persiste en base — c'est temporaire
