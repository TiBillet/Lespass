# Photos de téléphone : miniatures redressées (EXIF) / Phone photos: thumbnails follow EXIF orientation

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Les miniatures fabriquées par django-stdimage (thumbnail, crop, hdr, fhd…) appliquent désormais l'orientation EXIF de la photo. Une commande `regenerer_variations_exif` refabrique les miniatures des photos déjà en base (passage à blanc par défaut, `--appliquer` pour écrire).
/ stdimage thumbnails now apply the photo's EXIF orientation. A `regenerer_variations_exif` command rebuilds thumbnails of photos already stored (dry run by default, `--appliquer` to write).

**Pourquoi / Why :** Un téléphone enregistre les pixels du capteur et une étiquette « Orientation ». stdimage 6.0.2 redimensionne les pixels bruts et enregistre la miniature sans l'étiquette : l'original s'affiche droit, mais toutes les miniatures affichées sur le site sortent couchées (vu sur la galerie de l'UPop Villeurbanne). Le bug touche tous les StdImageField, qu'ils soient remplis par l'admin, l'API v2 ou un script.
/ stdimage resized raw sensor pixels and dropped the tag, so every displayed thumbnail of a phone photo was rotated.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/images_orientation.py` | **Nouveau.** `process_variation_avec_orientation_exif` : `ImageOps.exif_transpose` avant le redimensionnement stdimage (recopie du `format`, perdu par la copie Pillow) |
| `BaseBillet/apps.py` | `ready()` branche la version EXIF sur `StdImageFieldFile.process_variation` (un seul point pour tout le projet, aucune migration) |
| `pages/management/commands/regenerer_variations_exif.py` | **Nouveau.** Parcourt les StdImageField des TENANT_APPS, lieu par lieu, et refabrique les miniatures des originaux dont l'orientation ≠ 1 |
| `tests/pytest/test_images_orientation_exif.py` | **Nouveau.** 3 tests : orientation 6 → portrait ; format conservé pour la sauvegarde ; orientation 1 inchangée (vérifiés par mutation) |

---

## Comment tester (a la main) / Manual test

### Test 1 — nouvelle photo
1. Dans l'admin d'un lieu, ajouter à un bloc IMAGES (affichage GRILLE) une photo prise téléphone en main verticale.
2. Ouvrir la page publique : la vignette est droite (avant : couchée sur le côté).

### Test 2 — réparer les photos existantes
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py regenerer_variations_exif --tenant le-coeur-en-or`
   → liste les photos à redresser (`orientation=6`, `3`…), n'écrit rien.
2. Même commande avec `--appliquer` → « N redressees ».
3. Recharger `/la-vie-de-l-upop/` sur `le-coeur-en-or` : les 5 photos de « Une journée de partage » sont droites (le four à pain et la pizza étaient couchés / à l'envers).

### Production
- Lancer d'abord à blanc, puis `--appliquer`, **un lieu après l'autre** (`--tenant <schema>`), ou `--tous` en dehors des heures chargées : la commande relit chaque original.
- UPop Villeurbanne : `--tenant <schema du lieu> --appliquer` après déploiement.
- La commande est rejouable : l'original garde son EXIF, un second passage refabrique des miniatures identiques.

### Verifs automatiques
- `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_images_orientation_exif.py -q`
