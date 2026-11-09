# Retour en haut de page après une navigation HTMX / Scroll to top after HTMX navigation

**Date :** 2026-10-22
**Migration :** Non

## Resume / Summary
**Quoi / What :** Après un clic sur un lien qui remplace toute la page en HTMX (`hx-target="body"`), la nouvelle page s'affiche depuis le haut. Les skins `classic` et `V2` font maintenant comme `faire_festival`, qui avait déjà ce script. Les partiels (offcanvas, formulaires) gardent la position de défilement.
Le bouton « En savoir plus » des cartes événement (V2) va plus loin : il fait défiler jusqu'à la bannière de l'événement (`hx-swap="innerHTML show:.event-hero:top"`), sous l'en-tête du lieu.
/ After an HTMX link that replaces the whole body, the new page starts at the top. `classic` and `V2` now match `faire_festival`. Partial swaps keep the scroll position. The V2 event card "En savoir plus" button scrolls to the event banner (htmx `show:` modifier).
**Pourquoi / Why :** Retour utilisateur : sur mobile, « En savoir plus » depuis l'agenda ouvrait la fiche de l'événement tout en bas. On avait l'impression que le lien ne marchait pas. Le navigateur gardait la position de défilement de la liste.
/ User feedback: on mobile, "En savoir plus" opened the event page at the bottom, because the browser kept the list's scroll position.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/shell.html` | Écouteur `htmx:afterSwap` : `window.scrollTo(0, 0)` quand la cible est le `body` |
| `pages/templates/pages/classic/shell.html` | Même écouteur |
| `pages/templates/cotton/V2/event_card.html` | « En savoir plus » : `hx-swap="innerHTML show:.event-hero:top"` |
| `pages/static/V2/css/V2.css` | `.event-hero` : `scroll-margin-top: 5rem` (la bannière s'arrête sous la `.user-bar` collante) |

---

## Comment tester (a la main) / Manual test
### Test 1 — scénario nominal (mobile)
1. Ouvrir l'agenda d'un lieu en skin V2, en vue mobile (DevTools, ~390 px de large).
2. Descendre jusqu'au dernier événement de la liste.
3. Cliquer sur « En savoir plus ».
4. Attendu : la page défile jusqu'à la bannière de l'événement (image et titre visibles), juste sous la barre du haut. L'en-tête du lieu est au-dessus, hors de l'écran.

### Test 2 — même chose en skin classic
Sur un lieu en skin `classic`, cliquer sur un lien qui recharge la page : elle s'affiche depuis le haut (pas de défilement vers la bannière, ce skin n'a pas reçu le `show:`).

### Test 3 — les partiels ne remontent pas
1. Sur une fiche événement, descendre et ouvrir le panneau de réservation, ou déplier « Bénévoles recherchés ».
2. Attendu : la page ne saute pas en haut.

### Test 4 — retour arrière
1. Depuis la fiche, faire « précédent » dans le navigateur.
2. Attendu : l'agenda se recharge (`historyCacheSize: 0`), sans erreur.
