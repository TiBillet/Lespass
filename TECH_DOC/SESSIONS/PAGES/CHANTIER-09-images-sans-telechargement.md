# Chantier 09 — API v2 pages : les images s'envoient, le serveur ne télécharge plus rien

**Statut :** codé le 2026-11-07 (non commité), spec relue par Fable
**Date :** 2026-11-07
**Hub :** [INDEX.md](./INDEX.md)
**Origine :** bug « PATCH bloc avec `image` en JSON ignoré » (corrigé le 2026-11-07 :
le PATCH refuse les images en JSON, 400), puis revue de sécurité défensive du
téléchargement par URL (agent Fable, même jour).

## 1. Intention

Aujourd'hui, à la création d'un bloc par l'API v2, le client peut donner une **URL**
d'image. Le serveur la **télécharge** lui-même (`telecharger_et_valider_image`,
`api_v2/serializers.py:156`). C'est pratique pour un script, mais c'est le code le plus
risqué de l'API :

- le serveur contacte une adresse choisie par le client ;
- le contrôle anti-SSRF (`_hote_est_interne`) n'est pas étanche : l'hôte vérifié n'est pas
  forcément l'hôte contacté (deux parseurs d'URL, deux résolutions DNS, proxy
  d'environnement suivi, plage `100.64.0.0/10` oubliée) ;
- la durée d'un téléchargement n'est pas bornée de bout en bout, et le nombre d'URL par
  requête non plus. Une page avec plusieurs images part déjà en 500 au bout d'environ 30 s.

Ce chantier **supprime le téléchargement par URL**. Une image arrive toujours **en fichier**
(multipart) : c'est le client qui envoie les octets. Pour que les galeries restent
possibles par l'API, il ajoute **un endpoint multipart qui ajoute une image à un bloc**.

Il corrige aussi deux faiblesses qui touchent **tous** les envois de fichiers, URL ou pas :
la validation Pillow ne regarde ni le format réel ni les dimensions, et le nom du fichier
enregistré est choisi par le client.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Le serveur de l'API pages ne contacte plus jamais une URL fournie par le client.
- Toute image envoyée autrement qu'en fichier est **refusée par un 400 explicite**. Jamais
  ignorée en silence.
- On peut toujours remplir par l'API : une image simple, une galerie IMAGES (grille, bande
  de logos), une SECTION Équipe ou Ressources avec photos, et les images d'un article
  (bloc TEXTE, `![légende](galerie:N)`).
- Un fichier image accepté est un vrai JPEG, PNG, GIF ou WebP, de taille raisonnable en
  pixels. Il est enregistré sous un nom choisi par le serveur.

**Non-objectifs**
- Pas de modification ni de suppression d'une image de galerie par l'API. On ajoute
  seulement. Pour corriger : l'admin, ou supprimer et recréer le bloc. (Suite possible :
  `DELETE /api/v2/blocs/{uuid}/images/{image_uuid}/`.)
- Pas de throttle DRF dans ce chantier (réglage à part, déjà commenté dans les settings).
- Pas de changement de l'admin Unfold : il envoie déjà des fichiers.
- Pas de changement des endpoints events et adresses, sauf l'effet de la validation
  d'image durcie (§4, décision D3).
- Pas de ré-encodage des images (contre les fichiers polyglottes) : le nom serveur et la
  liste blanche de formats suffisent pour ce chantier. À rediscuter si besoin.
- `video` reste ignorée en silence (multipart retiré dans `ajouter_bloc`, `continue` dans
  `additionalProperty`) : même famille que le bug d'origine, mais l'API n'accepte aucune
  vidéo par conception (bloc INTEGRATION). Suite possible : un 400 explicite.
- Les 3 messages d'erreur anglais existants de `_validate_uploaded_image` ne changent pas
  (events et adresses les renvoient déjà). Seuls les nouveaux messages sont en français.

**Anti-objectifs (ce serait un échec, même si ça marche)**
- Garder un chemin, même caché, où le serveur télécharge une URL de l'API pages.
- Ignorer en silence une image envoyée sous une mauvaise forme (le bug d'origine).
- Casser le rendu des pages existantes : les blocs et images déjà en base ne changent pas.

## 3. Ce qui existe et qu'on touche

| Élément | Où | Ce qu'il fait aujourd'hui |
|---|---|---|
| `_hote_est_interne` | `api_v2/serializers.py:~131` | Contrôle anti-SSRF |
| `telecharger_et_valider_image` | `api_v2/serializers.py:156` | Télécharge une URL, renvoie un `ContentFile` |
| `_validate_uploaded_image` | `api_v2/serializers.py:85` | Vérifie type déclaré, taille ≤ 10 Mo, `Image.open().verify()` |
| `BlocCreateSerializer._pre_telecharger_images` | `api_v2/serializers.py:~2290` | Phase 1 : télécharge `image` (URL ou liste), `image_secondaire`, `auteur_photo`, les images du markdown TEXTE |
| `BlocCreateSerializer._persister` | `api_v2/serializers.py:~2420` | Phase 2 : crée le bloc et ses `ImageGalerie` |
| `PageCreateSerializer.create` | `api_v2/serializers.py:~2622` | Appelle la phase 1 de chaque bloc de `hasPart`, puis la phase 2 en transaction |
| `_appliquer_fichiers_multipart` | `api_v2/views.py:161` | Pose `image`, `image_secondaire`, `auteur_photo` depuis `request.FILES` |
| `PageViewSet.ajouter_bloc` | `api_v2/views.py:~1426` | `POST /pages/{uuid}/blocs/`, JSON ou multipart ; en multipart, retire les champs fichier de `request.data` |
| `BlocViewSet.partial_update` | `api_v2/views.py:1464` | PATCH ; refuse déjà `image` sans fichier joint (400) |
| `ImageGalerie` | `pages/models.py:1238` | Image d'un bloc : `image` (facultative), `legende`, `lien_url` (validateur anti-schéma dangereux), `tags`, `position` |
| `rendre_bloc_markdown` | `pages/templatetags/pages_tags.py:680` | Résout `galerie:N` par le **rang d'affichage** (1 = première image), pas par la valeur de `position` |

Seul `api_v2/serializers.py:176` appelle `requests.get` dans `api_v2/`. Aucune commande de
gestion ni aucun script du dépôt n'envoie d'URL d'image à l'API (vérifié par recherche).
Les utilisateurs connus : le skill `tibillet-api` et les agents qui construisent des sites.

## 4. Décisions

- **D1 — Plus aucun téléchargement.** `telecharger_et_valider_image` et `_hote_est_interne`
  sont supprimées, ainsi que l'import de `requests` dans `api_v2/serializers.py` s'il ne
  sert plus ailleurs dans ce fichier.
- **D2 — Les refus ont lieu avant toute écriture.** Pour un bloc seul : dans `is_valid()`.
  Pour les blocs de `hasPart` : dans la boucle de `PageCreateSerializer.create()`, qui
  précède la création de la `Page` (et la vue enveloppe `save()` dans `transaction.atomic()`).
  Il n'y a plus de réseau, donc plus de « phase 1 hors transaction ».
- **D3 — La validation durcie s'applique à tous les appelants de
  `_validate_uploaded_image`**, y compris `img` et `sticker_img` des events et des
  adresses (`serializers.py:544, 786`). C'est la même fonction : la durcir pour les pages
  seulement créerait deux règles pour la même chose. Effet visible : un TIFF, un PSD ou une
  image de plus de 50 Mpx sont refusés partout dans l'API v2. L'admin n'est pas concerné.
- **D4 — Formats acceptés : JPEG, PNG, GIF, WebP.** Pillow identifie certaines photos
  d'appareil comme `MPO` (JPEG multi-image) : `MPO` est accepté et enregistré en `.jpg`.
  (stdimage enregistre alors ses variations au format MPO, relu comme un JPEG, mais sans
  l'optimisation qu'il réserve au format JPEG : acceptable.)
- **D5 — Limite de 50 mégapixels.** Une photo de téléphone en 48 Mpx passe. Au-delà, les 7
  variations calculées par stdimage dans la requête décodent trop de mémoire. Pillow ne lève
  `DecompressionBombError` qu'au-delà de 178 Mpx, et cette exception **n'hérite pas
  d'`OSError`** : elle est attrapée explicitement (400, pas 500).
- **D6 — Nom de fichier choisi par le serveur** : `uuid4().hex` + extension du format
  **réel**. Le nom envoyé par le client n'est jamais gardé. Appliqué aux fichiers des
  **pages** (bloc et galerie). Les events et adresses gardent leur nommage actuel (hors
  périmètre ; signalé comme suite). `upload_to` est une chaîne : sans renommage, Django
  garderait le nom client nettoyé. stdimage nomme les variations `<hex>.med.png`, etc.
  Dans `api_v2/views.py`, `uuid` est importé sous le nom `uuid_module`.
- **D7 — Nouvel endpoint `POST /api/v2/blocs/{uuid}/images/`** (multipart), action du
  `BlocViewSet` : même clé, même droit `page` (la permission se lit par basename `bloc`).
- **D8 — Une seule règle pour les images sans fichier**, dans un petit helper de
  `api_v2/views.py` utilisé par le PATCH et par `ajouter_bloc` en multipart. Il remplace le
  test écrit en ligne dans `partial_update`.
- **D9 — Markdown d'un bloc TEXTE** : les images `![alt](https://…)` ne sont plus
  importées. Le texte est gardé tel quel, et l'image reste servie par le site d'origine
  (comme aujourd'hui quand un téléchargement échoue). Pour héberger l'image sur le lieu :
  l'envoyer par l'endpoint D7, puis écrire `![alt](galerie:N)`.

## 5. Le design, lot par lot

### Lot A — Validation d'un fichier image (`api_v2/serializers.py`)

`_validate_uploaded_image(file_obj)` garde ses contrôles actuels (type déclaré `image/*`,
taille ≤ 10 Mo) et ajoute, dans le même `try` Pillow :

```python
# Formats acceptes, et l'extension a donner au fichier enregistre.
# / Accepted formats, and the extension given to the stored file.
EXTENSION_PAR_FORMAT_IMAGE_ACCEPTE = {
    "JPEG": ".jpg", "MPO": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp",
}
NOMBRE_MAX_DE_PIXELS_PAR_IMAGE = 50_000_000
```

- `Image.open(...)` : lire `image.format` et `image.size` (en-tête seulement, rien n'est
  décodé), refuser un format absent du dictionnaire, refuser `largeur * hauteur` au-delà
  de la limite, puis `verify()`.
- `except (UnidentifiedImageError, OSError, Image.DecompressionBombError)` → 400.
- La fonction **renvoie l'extension** (`".png"`…). Les appelants actuels ignorent la valeur
  de retour : rien ne casse.
- Les messages d'erreur, nouveaux ou repris, sont en français dans `_()`.

`_appliquer_fichiers_multipart` (`api_v2/views.py:161`) renomme le fichier :

```python
extension_du_format_reel = _validate_uploaded_image(fichier)
fichier.name = uuid.uuid4().hex + extension_du_format_reel
```

### Lot B — L'endpoint `POST /api/v2/blocs/{uuid}/images/`

Ajoute **une** image à la galerie d'un bloc (`ImageGalerie`). Multipart.

| Champ | Obligatoire | Va dans |
|---|---|---|
| `image` (fichier) | oui pour IMAGES et TEXTE ; non pour SECTION Équipe/Ressources | `ImageGalerie.image` |
| `caption` | non | `legende` (≤ 500) |
| `url` | non | `lien_url` (≤ 500) |
| `keywords` | non (texte « a, b ») | `tags` (≤ 200) |

**Blocs acceptés** : ceux qui **affichent** une galerie, c'est-à-dire les couples de
`AFFICHAGES_AVEC_GALERIE` (IMAGES en GRILLE ou BANDE_LOGOS, SECTION en EQUIPE ou
RESSOURCES), et TEXTE (pour `galerie:N`). Un bloc IMAGES en PLEINE_LARGEUR est refusé : sa
galerie ne serait jamais affichée. Tout autre bloc → 400 qui le dit.

**Validation** : un `serializers.Serializer` explicite (`ImageDeGalerieCreateSerializer`),
contexte `{"bloc": bloc}`. Le fichier passe par `_validate_uploaded_image` (lot A) et reçoit
un nom serveur (D6). Un `url` à schéma dangereux est **vidé**, comme partout ailleurs dans
l'API (`url_a_schema_dangereux`, règle des liens du projet) : une seule règle pour les
liens. `full_clean()` de l'`ImageGalerie` est appelé avant le `save()` (il borne aussi
`legende` ≤ 500 et `tags` ≤ 200) et son erreur est traduite en 400. Une `image` envoyée en
texte (pas en fichier) → 400 (D8).

**Position** : l'image s'ajoute **à la fin** : `position = (position max existante, ou -1) + 1`.

**Réponse 201** : l'image créée, en `ImageObject` :

```json
{"@type": "ImageObject", "identifier": "<uuid>", "contentUrl": "/media/…/<hex>.png",
 "caption": "…", "url": "…", "keywords": "…", "position": 4,
 "galerieReference": "galerie:3"}
```

`position` est la valeur brute du champ, comme ailleurs dans l'API. `galerieReference`
donne la référence à écrire dans `![légende](galerie:N)` pour un bloc TEXTE : `N` est le
**rang** de l'image (1 = première), calculé par `bloc.images_galerie.count()` après
l'insertion, puisque l'image est ajoutée à la fin.

### Lot C — Suppression du téléchargement

**`BlocCreateSerializer`** :
- `_pre_telecharger_images` est **supprimée**, ainsi que la coupure phase 1 / phase 2.
  `_persister(validated_data, page)` lit lui-même la liste des éléments d'une SECTION
  Équipe/Ressources. `create()` appelle `_persister` sous `transaction.atomic()`.
- Nouveau `validate(attrs)`, écrit en **liste blanche** (une liste noire laisserait passer
  un dict en silence) :
  - `image` absent, `None` ou `""` → rien (compatibilité) ;
  - `image` = liste, pour une SECTION Équipe/Ressources, dont chaque élément est un objet
    et dont **aucun** élément ne porte `contentUrl` → accepté ;
  - **toute autre valeur** de `image` (chaîne, dict, liste pour IMAGES ou un autre type,
    élément avec `contentUrl`) → 400 : « les images s'envoient en fichier : multipart, ou
    `POST /api/v2/blocs/{uuid}/images/` » ;
  - dans `additionalProperty`, **toute valeur non vide** d'un champ de `CHAMPS_IMAGE_URL`,
    quel que soit son type → 400, même message.
- `_persister` : le texte d'un bloc TEXTE est gardé tel quel (D9). Les éléments
  Équipe/Ressources sont créés sans image, liens dangereux vidés (inchangé).

**`PageCreateSerializer.create`** : la boucle valide chaque bloc (`is_valid`) avant la
création de la `Page`, puis appelle `bloc_ser._persister(bloc_ser.validated_data, page)`.
Les commentaires « pré-téléchargement / I/O réseau » disparaissent.

**`PageViewSet.ajouter_bloc`** (multipart) :
- avant de retirer les champs fichier de `request.data`, appel du helper D8. Un
  `-F image=https://…` en texte est refusé (400) au lieu d'être retiré en silence ;
- `ser.save()`, `_appliquer_fichiers_multipart` et `bloc.save()` sont enveloppés dans
  `transaction.atomic()`. Sans cela, un fichier refusé (TIFF, > 50 Mpx) laisse un bloc
  orphelin en base avec un 400 (`ATOMIC_REQUESTS` n'est pas activé).

**`BlocViewSet.partial_update`** : le test en ligne est remplacé par le helper D8, qui
couvre les trois champs (`image`, `image_secondaire`, `auteur_photo`) au premier niveau.
Le refus dans `additionalProperty` reste.

**Code supprimé** : `_hote_est_interne`, `telecharger_et_valider_image`, et les imports
devenus morts dans `api_v2/serializers.py` (à vérifier un par un : `requests`, `socket`,
`ipaddress`, `urlparse`, `ContentFile`), l'import local `re as _re_md` du markdown.

`CHAMPS_IMAGE_URL` (`pages/blocs_catalogue.py:342`) garde sa valeur et son nom (importé
par `api_v2/serializers.py` et `api_v2/views.py`). Son commentaire et celui de
`CHAMPS_FICHIER` (l. 334-337) ne parlent plus de téléchargement.

### Lot D — Documentation

- `api_v2/openapi-schema.yaml` :
  - `WebPageElementCreate.image` : plus d'URL ; liste d'`ImageObject` **sans `contentUrl`**,
    pour Équipe/Ressources seulement ;
  - `POST /api/v2/pages/` et `POST /api/v2/pages/{uuid}/blocs/` : descriptions et 400 ;
  - nouvel endpoint `POST /api/v2/blocs/{uuid}/images/` (requête multipart, réponse 201,
    400, exemple `curl`) ;
  - `patchBloc` : déjà à jour, vérifier la cohérence.
- `api_v2/GUIDELINES.md` §Images, §Sécurité (retirer « anti-SSRF », qui n'a plus d'objet),
  l. 32-34 (events : formats acceptés et 50 Mpx, effet D3) et l. ~383.
- OpenAPI, autres passages repérés par la relecture : l. ~1681-1689, ~1814, ~3328-3332.
- Skill `TECH_DOC/SKILLS/tibillet-api/` : `SKILL.md` (§3 Images, et l. 95-96 « images du
  markdown importées ») et `references/recettes.md`
  (§4, 4 bis, 4 ter : galerie, équipe, ressources) avec la recette en deux temps
  (créer en JSON, puis envoyer les images).
- `CHANGELOG/2026-11-07-api-pages-images-sans-telechargement.md`.
- `INDEX.md` : ligne du chantier 09.

## 6. Les tests (`tests/pytest/test_pages_api.py`)

Aucun appel réseau. Les fichiers sont fabriqués en mémoire avec Pillow (`_png_bytes()`
existe déjà).

**Lot A**
- un PNG valide passe et la fonction renvoie `".png"` ;
- un TIFF valide est refusé ;
- un PNG dont l'en-tête annonce 8000×8000 (64 Mpx) est refusé (400), sans 500 ;
- un PNG dont l'en-tête annonce 20000×20000 est refusé en 400 (`DecompressionBombError`,
  levée par `Image.open`) ;
- un MPO (`save(buf, "MPO", append_images=[…])`) est accepté et renvoie `".jpg"` ;
- fabrication sans mémoire : un PNG 1×1 dont on réécrit largeur et hauteur dans le chunk
  IHDR, CRC recalculé (69 octets ; `Image.open` ne lit que l'en-tête) ;
- PATCH multipart d'une image nommée `photo.php` : le fichier enregistré finit par `.png` et
  son nom ne contient pas `photo`.

**Lot B**
- ajout d'une image à un bloc IMAGES en GRILLE : 201, `ImageGalerie` créée, rang = 1, puis 2 ;
- `url` à schéma dangereux : 400, aucune image créée ;
- bloc d'un type sans galerie (ex. FAQ) : 400 ;
- SECTION Équipe sans fichier, avec `caption` et `keywords` : 201 ;
- bloc IMAGES sans fichier : 400 ;
- bloc TEXTE : l'image ajoutée est résolue par `rendre_bloc_markdown` via `galerie:1`.

**Lot C**
- création (POST page, POST bloc JSON) avec `image` en URL : 400, rien n'est créé ;
- page avec `hasPart` dont un bloc IMAGES porte une liste : 400, ni page ni bloc créés ;
- SECTION Équipe avec un élément portant `contentUrl` : 400 ;
- SECTION Équipe sans `contentUrl` : 201, éléments créés (non-régression) ;
- `auteur_photo` dans `additionalProperty` à la création : 400 ;
- bloc TEXTE avec `![x](https://exemple.org/a.png)` : 201, texte gardé tel quel, aucune
  `ImageGalerie` ;
- multipart `POST /pages/{uuid}/blocs/` avec `image` en texte : 400 ;
- multipart `POST /pages/{uuid}/blocs/` avec un TIFF : 400 **et aucun bloc créé** ;
- `image` en dict (`{"contentUrl": …}`) à la création : 400 ;
- `auteur_photo` en dict ou en liste dans `additionalProperty` : 400 ;
- un espion sur `socket.getaddrinfo` (ou l'absence de `requests` dans le module) prouve
  qu'aucune connexion sortante n'est tentée pendant ces tests.

**Tests existants à réécrire ou supprimer** (ils simulent le téléchargement) :
`test_bloc_image_par_url_ok`, `test_telecharger_image_bloque_ssrf_loopback`,
`test_bloc_create_image_secondaire_url_dangereuse_leve_400`,
`test_bloc_galerie_cree_et_expose_imageobjects`, `test_telecharger_image_refuse_corps_trop_gros`,
`test_page_nested_galerie_url_dangereuse_ne_cree_rien`,
`test_bloc_images_bande_logos_cree_logos_cliquables`,
`test_bloc_texte_importe_images_et_preserve_source`, `test_bloc_texte_image_morte_garde_url`,
`tests/pytest/test_pages_equipe.py::test_api_equipe_cree_les_personnes_avec_et_sans_photo_et_les_expose`
(envoie un `contentUrl`), et les 3 tests PATCH du 2026-11-07 dont l'aide
`_espionner_les_telechargements` remplace `api_v2.serializers.requests.get` (cet attribut
disparaît avec D1 : à remplacer par un espion sur `socket.getaddrinfo`). Chaque test supprimé est remplacé par un test du nouveau
comportement, ou justifié dans le journal.

**Vérification par mutation** : chaque nouveau test est vu échouer sur une mutation
volontaire (ex. retirer le refus de `contentUrl`) avant d'être gardé.

**Commande** : `test_pages_api.py` entier, puis tous les tests qui touchent `api_v2`
(events, adresses : effet de D3), puis `manage.py check`. Suite complète : sur accord du
mainteneur (d'autres agents utilisent la même base).

## 7. Risques

- **Clients externes qui envoient des URL** (agents, scripts hors dépôt) : ils reçoivent un
  400 qui dit quoi faire. C'est voulu, mais c'est un changement d'API. Le CHANGELOG et le
  skill le disent clairement.
- **D3 sur les events et adresses** : un client qui envoyait un TIFF ou une image géante
  reçoit maintenant un 400. Peu probable, et c'était déjà dangereux.
- **Rang `galerie:N`** : si quelqu'un réordonne les images dans l'admin, les références
  d'un article bougent. C'est le comportement actuel de l'admin, inchangé.

## 8. Ce qui reste au mainteneur

- Relire, commiter (messages proposés dans le rapport final).
- Lancer le workflow i18n : nouvelles chaînes dans `api_v2/serializers.py` et `api_v2/views.py`.
- Prévenir les utilisateurs connus de l'API (agents qui construisent des sites).

## Journal

- 2026-11-07 : spec écrite.
- 2026-11-07 : relue par Fable. Intégré : B1 (`atomic` dans `ajouter_bloc`), B2 (liste
  blanche dans `validate`), B3 (tests cassés nommés), M1 (D2 reformulée), M2 (liens vidés,
  une seule règle), M3 (plus de phase 1), M4 (imports morts), M5-M7 (détails D4/D6),
  M6 (`galerieReference`), M8 (tailles de test), M9 (messages anglais inchangés),
  M10 (oublis doc), M11 (`video` en non-objectif), M12 (`image` vide ignoré).
- 2026-11-07 : codé. Lots A à D faits. Écart avec la spec : l'endpoint d'images accepte
  les couples de `AFFICHAGES_AVEC_GALERIE` plutôt que tout le type IMAGES (§5 lot B mis à
  jour). Tests : `test_pages_api.py`, `test_pages_equipe.py`, `test_pages_ressources.py`,
  events et adresses (images, création) : 101 passed. Mutations vérifiées : transaction
  de `ajouter_bloc`, `except DecompressionBombError`.
- 2026-11-07 : doc du skill `tibillet-api`, OpenAPI et `api_v2/GUIDELINES.md` remises sur
  le catalogue réel (8 types + affichages ; anciens types, champs disparus et `est_blog`
  retirés). Les 12 exemples JSON de la doc créés pour de vrai (transaction annulée) : OK.
  `evals/evals.json` du skill : l'éval n'attend plus d'images téléchargées par URL.
