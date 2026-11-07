# API v2 : le PATCH d'un bloc refuse les images en JSON / API v2: block PATCH refuses JSON images

**Date :** 2026-11-07
**Migration :** Non

## Resume / Summary
**Quoi / What :** `PATCH /api/v2/blocs/{uuid}/` renvoie un 400 quand une image arrive autrement qu'en fichier multipart : URL ou liste dans `image`, ou `image_secondaire` / `auteur_photo` dans `additionalProperty`. Avant, la valeur etait ignoree et la reponse 200 faisait croire que l'image avait change. La doc (OpenAPI, `api_v2/GUIDELINES.md`, skill `tibillet-api`) annoncait « memes formats que POST » : elle dit maintenant « images en multipart uniquement au PATCH ».
/ `PATCH /api/v2/blocs/{uuid}/` returns 400 when an image is sent other than as a multipart file. It used to be silently ignored with a 200. Docs updated accordingly.

**Pourquoi / Why :** plus d'ignorance silencieuse. Le choix « multipart uniquement » evite que le serveur contacte une URL fournie par le client. Le chantier 09 (`CHANGELOG/2026-11-07-api-pages-images-sans-telechargement.md`) a ensuite retire le telechargement par URL de toute l'API pages.
/ No more silent ignore. Multipart-only keeps the server from fetching client URLs; chantier 09 then removed URL download from the whole pages API.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `BlocViewSet.partial_update` : 400 si `image` est present sans fichier joint, ou si `additionalProperty` porte `image_secondaire` / `auteur_photo` |
| `api_v2/openapi-schema.yaml` | `patchBloc` : description FR/EN, schema JSON propre au PATCH (sans `image`), exemples de requete et de 400 |
| `api_v2/GUIDELINES.md` | Images par URL : creation seulement ; PATCH = multipart |
| `TECH_DOC/SKILLS/tibillet-api/SKILL.md`, `references/recettes.md` | Meme precision + exemple `curl -F image=@...` |
| `tests/pytest/test_pages_api.py` | 3 tests : URL, liste, `auteur_photo` en JSON -> 400, rien telecharge ni enregistre |

---

## Comment tester (a la main) / Manual test

### Test 1 — image par URL refusee
1. Prendre l'uuid d'un bloc IMAGES et une cle API avec le droit `page`.
2. `curl -sk -X PATCH "https://lespass.tibillet.localhost/api/v2/blocs/<uuid>/" -H "Authorization: Api-Key <cle>" -H "Content-Type: application/json" -d '{"headline":"x","image":"https://exemple.org/photo.png"}'`
3. Attendu : 400 `{"image": ["Les images s'envoient en fichier : en multipart sur le bloc, ou par POST /api/v2/blocs/{uuid}/images/ ..."]}`. Le titre n'a pas change.

### Test 2 — multipart toujours accepte
1. `curl -sk -X PATCH "https://lespass.tibillet.localhost/api/v2/blocs/<uuid>/" -H "Authorization: Api-Key <cle>" -F image=@photo.png`
2. Attendu : 200, l'image du bloc a change sur la page publique.

### Test 3 — photo d'auteur en JSON refusee
1. Sur un bloc SECTION en affichage CITATION : PATCH JSON avec `additionalProperty: [{"name": "auteur_photo", "value": "https://..."}]`.
2. Attendu : 400 avec la cle `auteur_photo`.

### Tests automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -q -k patch_bloc_json`
