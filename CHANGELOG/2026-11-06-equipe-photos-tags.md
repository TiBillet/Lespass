# Blocs Équipe et Ressources : une image par élément / Team and Resources blocks: one image per item

**Date :** 2026-11-06
**Migration :** Oui — `pages/migrations/0006_imagegalerie_tags.py` (ajout du champ `ImageGalerie.tags`).
Dépend de `0005_imagegalerie_legende_500` (autre chantier du même jour).
Pas de migration de données : aucun bloc Équipe ni Ressources n'existe en base.
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas pages`

## Resume / Summary
**Quoi / What :** les personnes d'une SECTION en affichage EQUIPE ne sont plus des
lignes de texte dans `Bloc.contenu`. Ce sont les images de l'encart « Images »
(`ImageGalerie`), comme une bande de logos : `legende` = le nom, nouveau champ
`tags` = les badges séparés par des virgules, `image` = la photo, facultative. La
photo est recadrée en rond ; sans photo, l'initiale du nom s'affiche.
/ EQUIPE people are now the block's `ImageGalerie` rows: caption = name, new
`tags` field = comma-separated badges, optional photo cropped round, initial as
fallback.

Même chose pour une SECTION en affichage RESSOURCES : `legende` = le titre,
`tags` = les badges, `lien_url` = le lien du titre (facultatif), `image` = une
vignette carrée (facultative ; sans vignette, l'icône document en V2). La
description libre d'une ressource et le rôle libre d'une personne disparaissent :
ils s'écrivent maintenant en tags.
/ Same for RESSOURCES: caption = title, tags = badges, optional link, optional
square thumbnail (document icon as fallback). Free-text description (resources)
and role (team) are gone: they are now written as tags.

**Pourquoi / Why :** `contenu` ne contient que du texte, il ne pouvait pas porter
de photo. `ImageGalerie` avait déjà l'upload, les variations et le tri par
glisser-déposer.
/ `contenu` is text-only and could not hold a photo; `ImageGalerie` already had
upload, variations and drag-and-drop sorting.

Correction au passage : l'aperçu en direct de l'admin cherchait les images déjà
enregistrées sous `images_galerie-N-id`, alors que le formset poste
`images_galerie-N-uuid`. Les images enregistrées n'étaient donc jamais
retrouvées dans l'aperçu.
/ Also fixed: the live preview looked up saved gallery rows by `-id` instead of
`-uuid`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/models.py` | `ImageGalerie.tags` + méthode `liste_des_tags()` |
| `pages/migrations/0006_imagegalerie_tags.py` | Ajout de la colonne `tags` |
| `pages/blocs_catalogue.py` | EQUIPE et RESSOURCES dans `AFFICHAGES_AVEC_GALERIE`, retirés des tables de `contenu` ; nouvelle constante `AFFICHAGES_SECTION_EN_GALERIE` |
| `pages/admin.py` | Encart Images : colonnes selon le bloc (EQUIPE : tags sans lien ; RESSOURCES : tags et lien ; ailleurs : lien sans tags) |
| `pages/admin_apercu.py` | Aperçu : clé `-uuid`, tags lus, personne sans photo gardée |
| `pages/templates/pages/{V2,classic}/partials/bloc_section_equipe.html` | Lecture de la galerie, photo ronde ou initiale, tags en badges |
| `pages/templates/pages/{V2,classic}/partials/bloc_section_ressources.html` | Lecture de la galerie, vignette carrée ou icône document, lien du titre, tags en badges |
| `pages/static/V2/css/V2.css`, `pages/static/pages/css/tb-blocs.css` | Avatar rond et vignette carrée (`aspect-ratio: 1 / 1` + `object-fit: cover`) |
| `api_v2/serializers.py` | SECTION EQUIPE / RESSOURCES : `image` = liste d'`ImageObject` (`caption`, `keywords`, `url`, `contentUrl` facultative), en lecture et en création |
| `pages/management/commands/charger_site_lespass.py` | Démo : 3 personnes avec photo, 1 sans ; 3 ressources avec vignette, 3 sans, 1 avec lien |
| `pages/editeur_items.py`, `pages/admin_widgets.py`, `admin/pages/widgets/ligne_cartes.html` | Commentaires : l'éditeur de lignes ne sert plus à EQUIPE ni à RESSOURCES |
| `TECH_DOC/SKILLS/tibillet-api/` | Recettes « Section Équipe » et « Section Ressources » |
| `tests/pytest/test_pages_equipe.py`, `tests/pytest/test_pages_ressources.py` | Nouveaux : rendu, admin, API |
| `tests/pytest/test_pages_admin_apercu.py`, `tests/pytest/test_pages.py` | Aperçu EQUIPE ; EQUIPE et RESSOURCES ne lisent plus `contenu` |

---

## Comment tester (a la main) / Manual test

### Test 1 — la démo
1. Reconstruire la page : `docker exec lespass_django poetry run python /DjangoFiles/manage.py charger_site_lespass`
   (attention : reconstruit tout le site de démo et force le skin V2).
2. Ouvrir https://lespass.tibillet.localhost/qui-sommes-nous/, section « Le collectif ».
3. Attendu : Awa, Naïm, Sofia ont une photo ronde ; Théo a un rond avec « T » ;
   chacun a deux badges.

### Test 2 — l'admin
1. Ouvrir la fiche du bloc Équipe dans l'admin.
2. Attendu : pas d'éditeur « Éléments de la section » ; l'encart Images montre
   Image, Légende, Tags (pas de Lien).
3. Ajouter une ligne avec un nom et des tags, sans fichier → l'aperçu montre
   l'initiale. Enregistrer → même rendu sur le site.
4. Réordonner les lignes par glisser-déposer → l'ordre suit sur le site.

### Test 3 — les ressources
1. Même page, section « Les ressources ».
2. Attendu : Café, Coworking, Ateliers ont une vignette carrée ; les trois
   autres ont l'icône document ; « Le journal du lieu » est un lien (nouvel
   onglet) ; chaque ressource a ses badges.
3. Dans l'admin, la fiche du bloc Ressources : l'encart Images montre Image,
   Légende, Tags et Lien.

### Test 4 — cas limites
- Tags « a, , b ,» → deux badges seulement.
- Bloc GRILLE ou BANDE_LOGOS : l'encart montre toujours le Lien, pas les Tags.

### Verifs automatiques
`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_pages_equipe.py /DjangoFiles/tests/pytest/test_pages_ressources.py -q`
