# laboutik : popup tarif sur petit écran, catégories, bouton Vider / laboutik: rate popup on small screens, categories, Empty button

**Date :** 2026-09-29
**Migration :** Non / No

## Résumé / Summary

**Quoi / What :** la popup de choix du tarif tient dans l'écran du téléphone et couvre aussi les
catégories. Les catégories sont plus larges sur téléphone. Le bouton Vider passe de l'en-tête du
panier à la rangée d'actions. / The rate popup fits phone screens and covers the categories;
wider categories on phones; the Empty button moves to the actions row.

**Pourquoi / Why :** sur téléphone, le haut et le bas de la popup étaient coupés (titre, croix,
« Ajouter »). Toucher le voile faisait planter `manageKey()`. / On phones the popup was clipped
top and bottom, and tapping its veil threw in `manageKey()`.

### Popup tarif
- Voile en grille `minmax(0, 1fr)` : la boîte reste dans le voile et défile à l'intérieur.
- ≤ 1022 px : popup en `position: fixed`, du header jusqu'au panier replié, sur toute la largeur.
- Paysage (hauteur ≤ 500 px) : plein écran (`inset: 0`).
- Focus réactivé sur le premier tarif à l'ouverture (Échap ferme de nouveau la popup).
- `articles.js` : garde contre un parent `null` quand le clic vient du voile déjà retiré.

### Catégories
- `--cat-width` passe de 64 à 84 px sous 600 px de large.

### Bouton Vider
- Déplacé dans la rangée d'actions, à gauche de CHECK CARTE.
- Tuile en colonne à largeur fixe (76 px, 68 px entre 1023 et 1199 px, CHECK CARTE aussi) :
  l'état armé « Confirmer » n'élargit plus la rangée, VALIDER ne déborde plus du panneau.
- Bordure transparente au repos : plus de décalage de 2 px au premier article.
- `:focus-visible` (anneau `--nfc`) sur Vider, CHECK CARTE et VALIDER.
- `min-width: 0` sur VALIDER : il peut rétrécir plutôt que sortir du panneau.

## Fichiers / Files

| Fichier | Changement |
|---|---|
| `laboutik/static/css/tarif.css` | Pistes de grille, media query ≤ 1022 px, `inset: 0` en paysage |
| `laboutik/static/js/tarif.js` | Focus sur le premier tarif |
| `laboutik/static/js/articles.js` | Garde `if (!ele) return` |
| `laboutik/static/css/sizes.css` | `--cat-width` 84 px sous 600 px |
| `laboutik/templates/cotton/addition.html` | Vider retiré de l'en-tête |
| `laboutik/templates/cotton/addition_footer.html` | Vider dans la rangée d'actions |
| `laboutik/static/css/addition.css` | Tuile Vider, bordure, focus, `min-width: 0`, tuiles 68 px en panneau étroit |
| `tests/e2e/test_tarif_popup.py` | 3 tests de placement de la popup |

## Déploiement
- `collectstatic`.

## À tester
Voir `A TESTER et DOCUMENTER/popup-tarif-petit-ecran.md` (test 6 pour le bouton Vider).
