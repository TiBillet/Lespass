# Galerie d'images d'évènement simplifiée / Simplified event image gallery

**Date :** 2026-10-18
**Migration :** Oui — `BaseBillet/migrations/0234_carrousel_nom_facultatif.py` (SQL vide : `blank`, `default` et `validators` ne vivent que dans Django). `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas`

## Resume / Summary
**Quoi / What :**
- Une diapositive (`Carrousel`) ne demande plus que le fichier image : le nom devient facultatif et sert de texte alternatif (alt) ; plus de taille minimale (720×135 retiré).
- Admin Carrousel : seuls image, nom et poids sont affichés. « Ajouter au carrousel de l'agenda » (défaut passé à Faux) et « URL du lien » restent en base, masqués.
- Fiche évènement : le champ « Galerie d'images » montre en miniatures les seules images de l'évènement (décocher = retirer). Le champ « Ajouter des images » accepte plusieurs fichiers ; chacun devient une diapositive rattachée à l'évènement. Plus d'autocomplétion ni de popup « + ».
- Galerie V2 de la page évènement : `object-fit: scale-down`. Une petite image garde sa taille naturelle (nette) sur le fond flouté ; une grande est réduite comme avant.

/ A slide only requires the image file (optional name used as alt text, no minimum size). Carrousel admin shows image, name, weight only. The event form shows the event's own images as thumbnails (uncheck to remove) plus a multiple-file upload. V2 gallery uses `scale-down` so small images are never upscaled.

**Pourquoi / Why :** ajouter des images à un évènement demandait des champs inutiles, et la liste many-to-many affichait toutes les images du lieu.
/ Adding images required useless fields, and the many-to-many list showed every image of the venue.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Carrousel` : `name` facultatif + help_text alt, `on_event_list_page` défaut `False`, plus de `MinSizeValidator`, `__str__` retombe sur le nom du fichier |
| `BaseBillet/migrations/0234_carrousel_nom_facultatif.py` | Migration (no-op SQL) |
| `Administration/admin_tenant.py` | `CarrouselAdmin` réduit ; `GalerieCarrouselWidget`, `PlusieursImagesInput`, `PlusieursImagesField` ; `EventForm` (galerie + `galerie_nouvelles_images`) ; `EventAdmin` : champ ajouté au fieldset, `carrousel` retiré de `autocomplete_fields`, création des diapositives dans `save_related` |
| `Administration/templates/admin/event/widget_galerie_carrousel.html` | Nouveau : miniatures + cases à cocher |
| `pages/static/V2/css/V2.css` | `.galerie__image` : `object-fit: scale-down` |
| `pages/templates/pages/V2/partials/evenement_galerie.html` | Commentaire d'en-tête à jour |
| `tests/pytest/test_admin_galerie_evenement.py` | Nouveau : 5 tests (liste limitée, envoi multiple, retrait, fichier refusé, petite image) |

Non modifié : les diapositives existantes gardent leurs valeurs (carrousel de l'agenda et liens toujours affichés). Une image décochée reste dans l'admin Carrousel.
Nouvelles chaînes traduisibles (msgid FR) : le help_text du nom, « Galerie d'images », « Décochez une image… », « Ajouter des images », son help_text, « Aucune image dans la galerie pour l'instant. » → workflow i18n à lancer.
`V2.css` est servi depuis `www/static` : `collectstatic` nécessaire pour voir le changement.

---

## Comment tester (a la main) / Manual test
### Test 1 — ajout d'images depuis un évènement
1. Admin → Évènements → ouvrir un évènement sans image de galerie : « Aucune image dans la galerie pour l'instant. »
2. « Ajouter des images » : choisir 3 fichiers d'un coup (dont un petit, ex. 300×200) → Enregistrer.
3. Rouvrir la fiche : 3 miniatures cochées.
4. Page publique de l'évènement (skin V2) : les 3 images défilent ; la petite reste nette, centrée sur le fond flouté.
5. Elles n'apparaissent PAS dans le carrousel de l'agenda.

### Test 2 — retrait
1. Décocher une miniature → Enregistrer : elle disparaît de la fiche et de la page publique.
2. Admin → Carrousel : la diapositive existe toujours (nom du fichier si sans nom).

### Test 3 — validation
1. « Ajouter des images » avec un fichier .txt → erreur sur ce champ, rien n'est enregistré.

### Test 4 — admin Carrousel
1. Ajouter une diapositive : seuls Fichier image (obligatoire), Nom de la diapositive (aide « texte alternatif… ») et Poids.
2. Liste : nom (ou nom du fichier), poids éditable, évènements liés.

### Verifs automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_admin_galerie_evenement.py -q` (5 tests, vérifiés par mutation).
