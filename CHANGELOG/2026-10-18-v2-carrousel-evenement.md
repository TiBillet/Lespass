# Galerie d'images sur la fiche événement V2 / Image gallery on the V2 event page

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** la fiche événement du skin V2 affiche les images du carrousel de l'événement (champ `Event.carrousel`) juste sous le titre. Aucune image n'est rognée : scène à ratio fixe, image entière (`contain`), bandes vides remplies par la même image floutée. / The V2 event page shows the event's carousel images right below the title, never cropped: fixed-ratio stage, contained image, blurred copy behind.
**Pourquoi / Why :** les images saisies dans l'admin n'apparaissaient pas en V2, et `commun/partials/picture.html` (object-fit cover) aurait recadré les affiches. / Admin-set images were missing in V2, and picture.html (cover) would crop posters.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/partials/evenement_galerie.html` | Nouveau : carrousel Bootstrap, image entière + fond flouté ; si 2+ images : flèches, pastilles de position, défilement auto 5 s, glissement au doigt (script d'initialisation, valable aussi après une navigation HTMX) |
| `pages/templates/pages/V2/vues/evenement.html` | Inclusion de la galerie sous le `<h1>` du bandeau |
| `pages/static/V2/css/V2.css` | Styles `.galerie*` : scène 3/2 (4/3 sur téléphone) plafonnée à 70vh, fond flouté, flèches et pastilles de position |

---

## Comment tester (a la main) / Manual test
### Test 1 — événement avec plusieurs images
1. Sur un tenant en skin V2, ouvrir `/event/what-the-funk-spectacle-payant-270424-2200-afa300b9/`.
2. La galerie est juste sous le titre, avant la description.
3. Image paysage : entière, bandes floues sur les côtés si l'écran est bas.
4. Flèche droite : l'affiche portrait s'affiche entière, bandes floues de chaque côté, la page ne saute pas.
5. En bas de l'image, une pastille par image ; celle de l'image courante est pleine. Cliquer une pastille affiche son image.
6. Sans toucher à rien, l'image change toutes les 5 secondes. Souris posée sur l'image : pause.
7. Arriver sur la fiche depuis l'agenda (clic « En savoir plus », navigation HTMX) : le défilement automatique marche aussi.
8. Système réglé sur « réduire les animations » : pas de défilement automatique.

### Test 2 — une seule image / aucune image
1. Une seule image : pas de flèches, pas de pastilles, pas de défilement.
2. Aucune image : pas de galerie, pas d'espace vide.

### Test 3 — téléphone (375 px)
1. La scène passe en 4/3, pas de défilement horizontal de la page, les flèches restent cliquables.
2. Glisser l'image du doigt vers la gauche / la droite change d'image (le glissement n'existe que sur écran tactile).

### Test 4 — image avec lien
1. Une image avec un lien (champ « Link URL ») s'ouvre dans un nouvel onglet.
