# Planning bénévoles : alignement optique des pastilles et des boutons / Volunteer planning: optical alignment of pills and buttons

**Date :** 2026-10-19
**Migration :** Non

## Resume / Summary
**Quoi / What :** Les prénoms dans les pastilles, et le texte des boutons et des badges du planning bénévoles, sont centrés à l'œil (et non plus seulement par la boîte). Toutes les pastilles ont la même hauteur (24 px). Dans une case « Couvert », les pastilles de prénom redeviennent visibles (fond blanc). La légende utilise la même taille de pastille que la grille.
/ Pill, button and badge text is now optically centred; all pills share one height; first-name pills are visible again in covered needs; the legend uses the grid's pill size.

**Pourquoi / Why :** La police Luciole réserve une grande zone de jambages sous la ligne d'écriture : le texte tombait 2 à 4 px trop haut. Seule la pastille « libre » avait une bordure, d'où trois hauteurs différentes. Dans une case couverte, la pastille avait le même fond que la case.
/ Luciole's descender zone pushed the ink 2–4 px too high; only "libre" had a border; pill and covered-need backgrounds were identical.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/static/booking/css/benevolat.css` | Jetons de hauteur (`--bv-haut-*`), fond de pastille en jeton (`--bv-fond-pastille`), contour transparent sur toutes les pastilles, légende en `baseline`, bloc `@supports (text-box: …)` pour le centrage optique (même règle que `.ink-center-fix` du skin V2) |

---

## Comment tester (a la main) / Manual test

### Test 1 — pastilles
1. Ouvrir `https://lespass.tibillet.localhost/booking/benevolat/festival/` (Chrome ou Safari récents).
2. Dans une case avec un prénom et une place « libre » : les deux pastilles ont la même hauteur, le texte est au milieu (pas collé en haut).
3. Dans une case « Couvert » (fond gris) : les prénoms sont dans des pastilles blanches bien visibles.
4. S'inscrire sur un créneau : la pastille noire « moi » a la même hauteur que les autres.

### Test 2 — boutons et badges
1. « Je viens », « Je viens aussi », « Semaine précédente / suivante », badges « Couvert » et « Ouvert à tout compte connecté » : le texte est centré verticalement.
2. Mobile (375 px) : les boutons de semaine passent sur deux lignes, le texte reste centré.

### Test 3 — navigateur sans `text-box` (Firefox)
1. Ouvrir la même page dans Firefox : la mise en page est identique à avant (centrage par la boîte), rien ne casse.
