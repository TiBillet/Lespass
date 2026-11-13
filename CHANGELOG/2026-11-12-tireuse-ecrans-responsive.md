# Écrans tireuse responsive / Responsive tap screens

**Date :** 2026-11-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** les écrans de la tireuse (page d'une tireuse et page liste) s'adaptent à toutes les tailles d'écran. Le look de la maquette est gardé à l'identique en 1280×800. Sur un petit écran du Pi (800×480, 1024×600), le cadre garde la forme 16/10 et rétrécit. Sur une TV, il grandit. En portrait (Pi tourné, tablette, téléphone), les blocs passent l'un sous l'autre.
/ Tap screens (single tap and list) adapt to every screen size. The mockup look is unchanged at 1280×800. Small Pi screens shrink the 16/10 frame, TVs grow it, portrait screens stack the blocks.

**Pourquoi / Why :** le cadre avait une taille fixe de 1280×800 px. Il débordait sur les petits écrans du Pi et restait petit sur une TV. Rien ne passait en colonne en portrait.
/ The frame had a fixed 1280×800 px size: it overflowed on small Pi screens and nothing stacked in portrait.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/static/controlvanne/css/tireuse.css` | Unité de maquette `--tireuse-u` (calculée sur la largeur du cadre, conteneur CSS). Tailles en `max(plancher, valeur × unité)`. Cadre 16/10 fluide en paysage, plein écran en portrait. Empilement en portrait. Description raccourcie sur écran bas. Page liste : vignettes en conteneur, gouttière fluide. Simulateur DEMO en bas d'écran sur téléphone. |
| `controlvanne/templates/controlvanne/base_tireuse.html` | `tireuse.css?v=6` (force le Chromium du Pi à recharger le CSS) ; commentaire mis à jour. |

Aucun `id`, `data-*` ni `data-testid` renommé : le JS (`ecran_tireuse.js`, `simu_pi.js`) n'est pas touché.

---

## Comment tester (a la main) / Manual test

### Test 1 — la maquette est inchangée en 1280×800
1. Ouvrir `/controlvanne/kiosk/<uuid>/` dans Chrome, mode appareil 1280×800.
2. Passer par toutes les étapes avec le simulateur DEMO : veille → carte posée → débit → retrait (fin) ; carte inconnue (refus).
3. Attendu : même rendu qu'avant (tailles de texte, marges, étiquette à droite, verre à droite).

### Test 2 — petit écran du Pi
1. Mode appareil 800×480 puis 1024×600.
2. Veille : le nom, les pastilles, le prix et « Présentez votre carte » sont visibles. La description est coupée à 4 lignes.
3. Service / tirage : nom, salutation, Prix / Solde / Verres, mode d'emploi, verre et volume visibles. La mention légale est visible en bas, sans défilement.

### Test 3 — portrait
1. Mode appareil 800×1280 (Pi tourné) puis 390×844 (téléphone).
2. Veille : l'étiquette et la brasserie sont au-dessus du nom, en ligne.
3. Service : la salutation est sous le nom, le mode d'emploi au-dessus du verre. Le verre est plus grand.
4. Téléphone : la case « Soit N verres » passe à la ligne. Aucun défilement horizontal.

### Test 4 — grand écran
1. Mode appareil 1920×1080.
2. Le cadre grandit (environ 1728×1080) et garde la forme 16/10. Le texte grandit avec lui.

### Test 5 — page liste
1. Ouvrir `/controlvanne/kiosk/` en 1920, 1280 et 390 de large.
2. Les vignettes se rangent en grille, puis en une colonne sur téléphone. Aucun défilement horizontal.

### Cas limite connu
- Téléphone couché (environ 844×390) : l'écran de service dépasse de quelques dizaines de pixels, la page défile. Ce cas ne concerne pas le Pi (démo seulement).

### Verifs DB / Playwright
- Pas de changement en base.
- Pas de test E2E existant sur ces écrans.
