# API v2 pages : les images s'envoient en fichier, le serveur ne télécharge plus rien / API v2 pages: images are uploaded, the server downloads nothing

**Date :** 2026-11-07
**Migration :** Non
**Spec :** `TECH_DOC/SESSIONS/PAGES/CHANTIER-09-images-sans-telechargement.md`

## Resume / Summary
**Quoi / What :**
- Le serveur ne télécharge plus aucune image depuis une URL. `telecharger_et_valider_image` et le contrôle anti-SSRF `_hote_est_interne` sont supprimés.
- Une image envoyée autrement qu'en fichier (URL, liste avec `contentUrl`, dict, texte à la place du fichier) renvoie un **400** qui dit quoi faire, à la création comme au PATCH.
- Nouvel endpoint **`POST /api/v2/blocs/{uuid}/images/`** (multipart) : ajoute une image à la fin de la galerie d'un bloc (IMAGES en grille ou bande de logos, SECTION Équipe ou Ressources, TEXTE). Réponse : un `ImageObject` avec `galerieReference` (`galerie:N`).
- Validation d'un fichier image durcie, pour toute l'API v2 (events et adresses compris) : format réel JPEG, PNG, GIF ou WebP ; au plus 50 mégapixels ; une « bombe de décompression » donne un 400 au lieu d'un 500.
- Les fichiers des blocs reçoivent un nom choisi par le serveur (`<hex>.<extension du format réel>`).
- Ajout d'un bloc en multipart : un fichier refusé ne laisse plus de bloc orphelin (transaction).
- Bloc TEXTE : les images externes du markdown ne sont plus importées, le texte est gardé tel quel.
- Doc remise à jour sur le catalogue réel des blocs (skill `tibillet-api`, OpenAPI, `api_v2/GUIDELINES.md`) : elle citait encore les 19 anciens types (HERO, PARAGRAPHE, GALERIE, IFRAME…), refusés par l'API depuis juillet 2026, des champs disparus (`surtitre`, `image_position`, `repliable`) et le mode blog (`est_blog`), retiré. La table des 8 types et de leurs affichages est ajoutée. Chaque exemple JSON de la doc a été créé pour de vrai, dans une transaction annulée.
- Admin des clés API : l'encart « Besoin d'aide ? » (liste et formulaire) explique l'usage d'une clé et donne les liens du contrat OpenAPI (`.yaml` brut, à donner à un agent) et du skill `tibillet-api`.

/ The server no longer downloads images from URLs; any non-file image is a 400. New multipart endpoint to add one image to a block's gallery. Stricter image validation (real format, 50 Mpx, decompression bomb → 400) for the whole API v2. Server-chosen file names. No orphan block on a refused multipart file.

**Pourquoi / Why :** le téléchargement par URL était le code le plus risqué de l'API. La revue de sécurité a montré que le contrôle anti-SSRF n'était pas étanche (l'hôte vérifié pouvait différer de l'hôte contacté), que la durée et le nombre de téléchargements n'étaient pas bornés, et que la validation des fichiers laissait passer des images énormes en pixels et des noms de fichiers choisis par le client. Supprimer le téléchargement retire toute cette surface ; le client envoie lui-même les octets.
/ URL download was the riskiest code of the API (leaky SSRF guard, unbounded downloads). Removing it removes that surface.

**⚠️ Changement d'API / API change :** les clients qui envoyaient des URL d'image (agents, scripts) reçoivent maintenant un 400. Nouvelle recette : créer le bloc en JSON, puis envoyer chaque image en fichier (voir le skill `tibillet-api`, `references/recettes.md` §4).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/serializers.py` | `_validate_uploaded_image` durcie (renvoie l'extension réelle) ; `nommer_le_fichier_image_cote_serveur` ; suppression du téléchargement ; `BlocCreateSerializer.validate` en liste blanche ; `ImageDeGalerieCreateSerializer` ; `PageCreateSerializer` sans phase de téléchargement |
| `api_v2/views.py` | `_refuser_les_images_envoyees_sans_fichier` (PATCH et ajout multipart) ; transaction dans `ajouter_bloc` ; renommage des fichiers ; action `BlocViewSet.ajouter_image` |
| `pages/blocs_catalogue.py` | Commentaires de `CHAMPS_FICHIER` / `CHAMPS_IMAGE_URL` |
| `api_v2/openapi-schema.yaml` | POST page / bloc, PATCH bloc, nouvel endpoint, schémas `WebPageElementCreate` et `ImageObject` |
| `api_v2/GUIDELINES.md` | §Images, §Sécurité, validation des images |
| `TECH_DOC/SKILLS/tibillet-api/` | `SKILL.md` et `references/recettes.md` : recettes en deux temps |
| `tests/pytest/test_pages_api.py`, `test_pages_equipe.py` | Tests du téléchargement retirés ; tests du nouveau comportement |
| `TECH_DOC/SESSIONS/PAGES/` | `CHANTIER-09-…md`, `INDEX.md` |
| `Administration/admin_tenant.py`, `Administration/admin/help_messages_dictionnary.py` | `ExternalApiKeyAdmin` + `HelpDisplayMixin`, entrée d'aide `CLE_API` (liens .yaml et skill) |
| `tests/pytest/test_admin_cle_api_aide.py` | Les deux liens sont sur la liste et sur le formulaire de création |

---

## Comment tester (a la main) / Manual test

Prérequis : une clé API avec le droit `page` (`K="Api-Key <cle>"`), `H=lespass.tibillet.localhost`, une page existante (`<PAGE_UUID>`), une image `photo.png`.

### Test 1 — une URL d'image est refusée
1. `curl -sk -X POST "https://$H/api/v2/pages/<PAGE_UUID>/blocs/" -H "Authorization: $K" -H "Content-Type: application/json" -d '{"additionalType":"IMAGES","image":"https://exemple.org/a.png"}'`
2. Attendu : 400 `{"image": ["Les images s'envoient en fichier : ..."]}`, aucun bloc ajouté.

### Test 2 — galerie en deux temps
1. Créer un bloc : `-d '{"additionalType":"IMAGES","headline":"Galerie","additionalProperty":[{"name":"affichage","value":"GRILLE"}]}'` → noter `identifier`.
2. `curl -sk -X POST "https://$H/api/v2/blocs/<BLOC_UUID>/images/" -H "Authorization: $K" -F image=@photo.png -F caption="Salle"` deux fois.
3. Attendu : 201, `galerieReference` vaut `galerie:1` puis `galerie:2`, `contentUrl` finit par `<hex>.png`.
4. Ouvrir la page publique : la grille montre les deux images.

### Test 3 — image d'un article
1. Créer un bloc TEXTE avec `"text":"Intro\n\n![une photo](galerie:1)"`.
2. Envoyer `photo.png` sur `/api/v2/blocs/<BLOC_UUID>/images/`.
3. Attendu : la page publique affiche l'image dans le texte.

### Test 4 — fichier refusé, pas de bloc orphelin
1. Multipart sur `/api/v2/pages/<PAGE_UUID>/blocs/` avec `-F additionalType=IMAGES -F image=@scan.tiff`.
2. Attendu : 400, et la page n'a pas de bloc en plus (`GET /api/v2/pages/<PAGE_UUID>/`).

### Test 5 — events : effet de la validation durcie
1. Créer un event avec une image JPEG classique (`img`) : 201, comme avant.
2. Avec un TIFF : 400.

### Test 6 — aide de l'admin des clés API
1. Admin → Clés API : cliquer sur « Besoin d'aide ? Cliquer ici ! ».
2. Attendu : le texte d'usage et deux liens (contrat .yaml brut, skill tibillet-api) ; ils ouvrent les fichiers sur GitHub.
3. Même encart sur « Ajouter une clé ».

### Tests automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py tests/pytest/test_pages_equipe.py tests/pytest/test_pages_ressources.py tests/pytest/test_event_images.py tests/pytest/test_postal_address_images.py -q`
