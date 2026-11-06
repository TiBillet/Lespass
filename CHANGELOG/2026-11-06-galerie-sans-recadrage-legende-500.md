# Grille d'images sans recadrage, légende à 500 caractères / Image grid without cropping, 500-char caption

**Date :** 2026-11-06
**Migration :** Oui — `pages/migrations/0005_imagegalerie_legende_tags.py` (partagée avec le
chantier EQUIPE : elle porte aussi l'ajout de `ImageGalerie.tags`)
(`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas pages`)

## Resume / Summary
**Quoi / What :** Le bloc IMAGES en affichage GRILLE affiche chaque image dans son propre
format (plus de cadre 4:3 avec `object-fit: cover`). La légende d'une image de galerie
(`ImageGalerie.legende`) passe de 200 à 500 caractères.
/ The IMAGES block in GRILLE display shows each image in its own ratio (no more 4:3 frame
with `object-fit: cover`). The gallery image caption goes from 200 to 500 characters.

**Pourquoi / Why :** Les logos carrés d'une grille (page « Les occupant·es » de la
Filature) étaient rognés. Les légendes servent aussi de courte présentation sous un logo,
et 200 caractères coupaient ces textes.
/ Square logos in a grid were cropped. Captions also serve as a short presentation under
a logo, and 200 characters cut these texts.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/static/pages/css/tb-blocs.css` | `.tb-galerie__image` : `height: auto`, plus d'`aspect-ratio` ni d'`object-fit` |
| `pages/models.py` | `ImageGalerie.legende` : `max_length` 200 → 500 |
| `pages/migrations/0005_imagegalerie_legende_tags.py` | AlterField de `legende` (+ AddField `tags` du chantier EQUIPE) |

---

## Comment tester (a la main) / Manual test

### Test 1 — logos carrés entiers
1. Ouvrir une page avec un bloc IMAGES en affichage GRILLE contenant des logos carrés
   (ex. `https://la-filature.tibillet.coop/les-occupant-e-s/` une fois déployé).
2. Vérifier que chaque logo est affiché en entier (pas de bord rogné).

### Test 2 — photos de formats différents
1. Créer un bloc IMAGES GRILLE avec une photo paysage et une photo portrait.
2. Vérifier qu'aucune n'est rognée. Les cases ont alors des hauteurs différentes :
   c'est attendu.

### Test 3 — légende longue
1. Dans l'admin d'un bloc IMAGES, saisir une légende de 300 caractères sur une image.
2. Enregistrer : pas d'erreur, la légende complète s'affiche sous l'image.

### Verifs DB
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py showmigrations pages
```
