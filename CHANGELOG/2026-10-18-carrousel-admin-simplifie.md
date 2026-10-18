# Galerie d'images d'évènement simplifiée / Simplified event image gallery

**Date :** 2026-10-18
**Migration :** Oui — `BaseBillet/migrations/0234_carrousel_nom_facultatif.py` (SQL vide : `blank`, `default` et `validators` ne vivent que dans Django). `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas`

## Resume / Summary
**Quoi / What :**
- Une diapositive (`Carrousel`) ne demande plus que le fichier image : le nom devient facultatif et sert de texte alternatif (alt) ; plus de taille minimale (720×135 retiré).
- Admin Carrousel : seuls image, nom et poids sont affichés ; recherche aussi sur le nom de fichier. « Ajouter au carrousel de l'agenda » (défaut passé à Faux) et « URL du lien » restent en base, masqués et inutilisés.
- Fiche évènement : le champ « Galerie d'images » montre en miniatures les seules images de l'évènement (décocher = retirer). Le champ « Ajouter des images » accepte plusieurs fichiers ; chacun devient une diapositive rattachée à l'évènement. Plus d'autocomplétion ni de popup « + ».
- Galerie V2 de la page évènement : `object-fit: scale-down`. Une petite image garde sa taille naturelle (nette) sur le fond flouté ; une grande est réduite comme avant. Texte alternatif : le nom de la diapositive, sinon le nom de l'évènement.
- Envoi multiple plafonné à 20 images ; l'erreur d'un fichier invalide donne son nom.
- **Le carrousel de l'agenda est supprimé** (V2 et classic) : plus de `carrousel_event_list` dans le contexte, bloc `agenda_carrousel` laissé vide (contrat de skin), partial `pages/V2/partials/carrousel_evenements.html` supprimé. Le lien des diapositives (`link`) n'est plus affiché nulle part. Les champs `on_event_list_page` et `link` restent en base, inutilisés.

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
| `pages/static/V2/css/V2.css` | `.galerie__image` : `object-fit: scale-down` ; `.galerie__lien` supprimé |
| `pages/templates/pages/V2/partials/evenement_galerie.html` | Plus de lien sur les diapositives ; alt de repli = nom de l'évènement |
| `BaseBillet/views.py` | `get_context` : `carrousel_event_list` retiré |
| `pages/templates/pages/{V2,classic}/vues/agenda.html` | Bloc `agenda_carrousel` vide |
| `pages/templates/pages/V2/partials/carrousel_evenements.html` | Supprimé (ne servait qu'à l'agenda) |
| `pages/templates/pages/classic/partials/carrousel_evenements.html` | Plus de lien ; alt de repli (sert encore à l'accordéon d'évènement classic) |
| `Administration/admin/dashboard.py` | Description du Carrousel : « Les images des galeries d'évènements. » |
| `tests/pytest/test_admin_galerie_evenement.py` | Nouveau : 8 tests (liste limitée, évènement neuf, envoi multiple, retrait, fichier refusé, plafond, nom du fichier fautif, petite image) |

Une image décochée reste dans l'admin Carrousel.
Nouvelles chaînes traduisibles (msgid FR) : le help_text du nom, « Galerie d'images », « Décochez une image… », « Ajouter des images », son help_text, « Aucune image dans la galerie pour l'instant. » → workflow i18n à lancer.
`V2.css` est servi depuis `www/static` : `collectstatic` nécessaire pour voir le changement.

---

## Comment tester (a la main) / Manual test
### Test 1 — ajout d'images depuis un évènement
1. Admin → Évènements → ouvrir un évènement sans image de galerie : « Aucune image dans la galerie pour l'instant. »
2. « Ajouter des images » : choisir 3 fichiers d'un coup (dont un petit, ex. 300×200) → Enregistrer.
3. Rouvrir la fiche : 3 miniatures cochées.
4. Page publique de l'évènement (skin V2) : les 3 images défilent ; la petite reste nette, centrée sur le fond flouté.
5. L'agenda (V2 et classic) n'a plus de carrousel en tête, même pour les anciennes diapositives cochées « agenda ».

### Test 2 — retrait
1. Décocher une miniature → Enregistrer : elle disparaît de la fiche et de la page publique.
2. Admin → Carrousel : la diapositive existe toujours (nom du fichier si sans nom).

### Test 3 — validation
1. « Ajouter des images » avec un fichier .txt → erreur sur ce champ, avec le nom du fichier ; rien n'est enregistré.
2. Plus de 20 fichiers d'un coup → « Au plus 20 images par envoi. »

### Test 4 — admin Carrousel
1. Ajouter une diapositive : seuls Fichier image (obligatoire), Nom de la diapositive (aide « texte alternatif… ») et Poids.
2. Liste : nom (ou nom du fichier), poids éditable, évènements liés.

### Verifs automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_admin_galerie_evenement.py -q` (8 tests, vérifiés par mutation sauf « évènement neuf », qui garde le cas `_state.adding`).
