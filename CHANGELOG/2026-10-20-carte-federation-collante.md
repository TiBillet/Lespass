# Carte « Autour de nous » : tient dans l'écran et reste collée / Network map fits the screen and stays pinned

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :** Skin V2, page `/federation/`, sur desktop (≥ 992 px) : le panneau carte fait la hauteur de l'écran (moins la barre utilisateur) et reste collé pendant que la liste défile. Mobile et tablette inchangés.
/ V2 skin, `/federation/`, desktop: the map panel fits the viewport and sticks while the list scrolls. Mobile and tablet unchanged.
**Pourquoi / Why :** La carte prenait la hauteur de la liste (`height: 100%` dans la grille) : avec beaucoup de lieux, elle devenait très étirée.
/ The map took the list's height and became very stretched.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/static/V2/css/V2.css` | `#explorer-root .map-panel` en `position: sticky`, `top: 5rem`, hauteur `100dvh - 5rem - gap`, dans le `@media (min-width: 62rem)` |

---

## Comment tester (a la main) / Manual test
### Test 1 — desktop
1. Tenant en skin V2, ouvrir `https://lespass.tibillet.localhost/federation/` sur un écran ≥ 992 px.
2. La carte tient dans l'écran (pas de bas coupé).
3. Faire défiler la liste : la carte reste collée sous la barre utilisateur, puis se décroche à la fin de la liste.

### Test 2 — mobile (< 992 px)
1. Ouvrir la même page en vue mobile (DevTools, 390 px).
2. La liste s'affiche seule, le bouton flottant « Carte » est visible.
3. Clic sur « Carte » : la liste disparaît, la carte s'affiche sous la recherche (comportement identique à avant).
