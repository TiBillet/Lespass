# Accueil par défaut V2 : hero du lieu, pas de carte vide / V2 default home: venue hero, no empty map

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** L'accueil par défaut du skin V2 (affiché quand le lieu n'a pas de page d'accueil CMS publiée) ouvre sur un hero : image du lieu en fond, nom du lieu en titre, description courte en sous-titre. Sans coordonnées GPS, le panneau carte n'est plus affiché et le texte prend toute la largeur.
/ The V2 default home opens with a hero (venue image, name, short description). Without GPS coordinates, the map panel is hidden and the text takes the full width.
**Pourquoi / Why :** En prod (codecommun), l'accueil par défaut n'avait pas de hero, contrairement à une page d'accueil CMS (claf). Un lieu sans adresse affichait une carte vide (fond quadrillé et repère au milieu de rien).
/ The default home had no hero, unlike a CMS home page; a venue without address showed an empty map.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/vues/accueil.html` | Hero (balisage du bloc HERO du CMS, dans `.tb-jetons`) ; description courte déplacée dans le hero ; panneau carte seulement si latitude ET longitude ; classe `venue-brief--sans-carte` sinon |
| `pages/static/V2/css/V2.css` | `.venue-brief--sans-carte` (une colonne) ; titre de bloc V2 étendu à `.tb-jetons .tb-bloc__titre` |

---

## Comment tester (a la main) / Manual test
### Test 1 — hero
1. Lieu en skin V2 sans page d'accueil CMS publiée (ou `/?skin_preview=V2` sur un lieu sans page d'accueil).
2. `/` ouvre sur l'image du lieu, avec une carte blanche à gauche : nom du lieu, description courte.
3. Sans image du lieu : hero sobre centré sur fond teinté.

### Test 2 — lieu sans adresse GPS
1. Lieu sans adresse (ou adresse sans latitude/longitude), cas de codecommun.
2. Plus de panneau « Où l'on est ». La description longue et le contact prennent toute la largeur.

### Test 3 — lieu avec adresse GPS
1. La carte Leaflet s'affiche toujours à droite, comme avant.
