# Recettes API v2 — curl canoniques par domaine

Exemples concrets pour aller vite. **Le corps exact des ressources non-pages vit dans
`api_v2/openapi-schema.yaml`** — ces recettes donnent le squelette + où lire les champs.

Conventions de ces exemples :
- `K='Api-Key xxxx.yyyy'` (clé obtenue via `scripts/creer_cle_api.py`).
- `H=lespass.tibillet.localhost` (l'hôte = le tenant). `curl -k` en dev (cert auto-signé).

```bash
K='Api-Key xxxx.yyyy'; H='lespass.tibillet.localhost'
```

## Carte des endpoints (source : openapi-schema.yaml)

| Domaine | Endpoint | Perm. clé |
|---|---|---|
| Events | `GET/POST /api/v2/events/`, `GET .../{uuid}/`, `.../{uuid}/link-address/`, `.../{uuid}/link-product/` | `event` |
| Adresses | `GET/POST /api/v2/postal-addresses/` | `event` |
| Products | `GET/POST /api/v2/products/`, `GET .../{uuid}/` | `product` |
| Memberships | `GET/POST /api/v2/memberships/` | `membership` |
| Reservations | `GET/POST /api/v2/reservations/` | `reservation` |
| Sales | `GET /api/v2/sales/` | `sale` |
| Crowds | `GET/POST /api/v2/initiatives/`, `.../budget-items/`, `.../votes/`, `.../participations/` | `crowd` |
| Wallet | `POST /api/v2/wallet-refills/` | `walletrefill` (gift_asset) |
| **Pages** | `GET/POST /api/v2/pages/`, `GET .../{uuid}/`, `POST .../{uuid}/blocs/`, `PATCH/DELETE /api/v2/blocs/{uuid}/` | `page` |
| **Catalogue blocs** | `GET /api/v2/pages/block-types/` | `page` |
| Bénévolat | `GET/POST /api/v2/volunteer-tasks/`, `…/volunteer-plannings/` (uuid ou slug), `…/volunteer-needs/`, `…/volunteer-signups/` ; `GET/PATCH/DELETE …/{uuid}/` (pas de PATCH d'inscription) | `volunteering` |

---

## Pages & blocs (le domaine le mieux outillé)

### 1. Catalogue des types de blocs (À FAIRE EN PREMIER)
```bash
curl -sk -H "Authorization: $K" "https://$H/api/v2/pages/block-types/"
# -> {"blockTypes":[{"type":"SECTION","label":"...","fields":["affichage","titre",...]}, ...]}
# Les AFFICHAGES de chaque type ne sont pas dans cette réponse : voir SKILL.md (table des types).
```

### 2. Créer une page ENTIÈRE avec ses blocs (POST imbriqué `hasPart`)
Le plus efficace : page + blocs en une requête.
```bash
curl -sk -X POST "https://$H/api/v2/pages/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{
    "@context":"https://schema.org","@type":"WebPage","name":"Accueil",
    "additionalProperty":[
      {"@type":"PropertyValue","name":"slug","value":"accueil"},
      {"@type":"PropertyValue","name":"publie","value":true}
    ],
    "hasPart":[
      {"additionalType":"SECTION","headline":"Bienvenue","alternativeHeadline":"Un lieu coopératif",
       "additionalProperty":[{"name":"affichage","value":"BANNIERE"}]},
      {"additionalType":"TEXTE","headline":"À propos","text":"Bonjour **ici**."},
      {"additionalType":"INTEGRATION","headline":"Nos news",
       "additionalProperty":[{"name":"affichage","value":"NEWSLETTER"},
                             {"name":"embed_url","value":"https://ghost.exemple.coop/"}]}
    ]
  }'
```

### 3. Ajouter un bloc à une page existante
```bash
curl -sk -X POST "https://$H/api/v2/pages/<PAGE_UUID>/blocs/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{
    "additionalType":"INTEGRATION","headline":"Le plan",
    "additionalProperty":[
      {"name":"affichage","value":"WIDGET"},
      {"name":"embed_url","value":"https://www.openstreetmap.org/export/embed.html?bbox=..."},
      {"name":"hauteur_px","value":420}
    ]
  }'
```

### 4. Bloc avec images (galerie, bande de logos) — en deux temps
Le serveur ne télécharge **aucune URL** : une image s'envoie en fichier. On crée le
bloc en JSON, puis on envoie **chaque image** par `POST /api/v2/blocs/{uuid}/images/`.
```bash
# 1. Le bloc (bande de logos ; GRILLE pour une galerie photo)
BLOC=$(curl -sk -X POST "https://$H/api/v2/pages/<PAGE_UUID>/blocs/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{
    "additionalType":"IMAGES","headline":"Ils nous soutiennent",
    "additionalProperty":[{"name":"affichage","value":"BANDE_LOGOS"}]
  }' | jq -r .identifier)
# 2. Un appel par logo. `url` rend le logo cliquable (schéma dangereux vidé).
curl -sk -X POST "https://$H/api/v2/blocs/$BLOC/images/" -H "Authorization: $K" \
  -F image=@logo-a.png -F caption="Coop A" -F url=https://a.exemple/
```
La réponse est l'`ImageObject` créé ; `galerieReference` (`galerie:N`) sert à appeler
l'image dans le markdown d'un bloc TEXTE : `![légende](galerie:N)`.
Image trouvée sur le web : la télécharger soi-même (`curl -o`), puis l'envoyer.
Fichier accepté : JPEG, PNG, GIF ou WebP, ≤ 10 Mo, ≤ 50 mégapixels.

### 4 bis. Section Équipe (une `ImageObject` par personne)
`SECTION` en affichage `EQUIPE` : `image` = liste d'`ImageObject`, une par personne,
**sans `contentUrl`** (une URL renvoie un 400). `caption` = le nom, `keywords` = les
badges (texte « a, b » ou liste). Sans photo, le site affiche l'initiale du nom.
```bash
curl -sk -X POST "https://$H/api/v2/pages/<PAGE_UUID>/blocs/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{
    "additionalType":"SECTION",
    "additionalProperty":[{"name":"affichage","value":"EQUIPE"}],
    "image":[
      {"@type":"ImageObject","caption":"Awa Diallo","keywords":"Coordination, Salariée"},
      {"@type":"ImageObject","caption":"Théo Marchand","keywords":["Vie associative","Bénévole"]}
    ]
  }'
```
Pour ajouter une personne **avec sa photo** au bloc existant :
`curl -sk -X POST "https://$H/api/v2/blocs/<BLOC_UUID>/images/" -H "Authorization: $K" -F image=@awa.jpg -F caption="Awa Diallo" -F keywords="Coordination"`.

### 4 ter. Section Ressources (une `ImageObject` par ressource)
Même forme que l'Équipe, avec `affichage` = `RESSOURCES`. `caption` = le titre,
`keywords` = les badges, `url` = le lien du titre (facultatif, `http…` ou `/…`). La
vignette est **facultative** (sans vignette, le site affiche une icône document) et
s'envoie, comme une photo d'Équipe, par `POST /api/v2/blocs/{uuid}/images/`.
Exemple d'élément : `{"@type":"ImageObject","caption":"Le journal du lieu","keywords":"Page","url":"/journal/"}`

### 5. Éditer / supprimer un bloc
```bash
curl -sk -X PATCH  "https://$H/api/v2/blocs/<BLOC_UUID>/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{"headline":"Titre corrigé"}'
# Changer l'image : en fichier, multipart (une URL renvoie un 400).
curl -sk -X PATCH  "https://$H/api/v2/blocs/<BLOC_UUID>/" -H "Authorization: $K" \
  -F image=@photo.png
curl -sk -X DELETE "https://$H/api/v2/blocs/<BLOC_UUID>/" -H "Authorization: $K"
```

---

## Events

Corps sémantique `schema.org/Event` (sous-types `MusicEvent`, etc.). Champs complets :
`openapi-schema.yaml` → `POST /api/v2/events/` (name, startDate, endDate,
maximumAttendeeCapacity, description, keywords, img en multipart…).
```bash
curl -sk -X POST "https://$H/api/v2/events/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{
    "@context":"https://schema.org","@type":"MusicEvent",
    "name":"Concert de test","startDate":"2025-12-20T19:00:00Z"
  }'
```
Lier une adresse / un produit (tarif) à un event : `POST .../{uuid}/link-address/`,
`POST .../{uuid}/link-product/` (voir OpenAPI).

## Products, Memberships, Reservations, Crowds, Wallet-refills

Même principe : corps JSON-LD sémantique, champs exacts dans l'OpenAPI à la section de
l'endpoint. **Lire la section avant de composer le corps** (ne pas deviner les noms de
champs). Repères :
- **Products** : `POST /api/v2/products/` (openapi l.598).
- **Memberships** : `POST /api/v2/memberships/` (l.749).
- **Reservations** : `POST /api/v2/reservations/` ; liste des inscrits d'un événement
  `GET /api/v2/reservations/?event=<uuid>` (l.777).
- **Crowds/initiatives** : `POST /api/v2/initiatives/` + sous-ressources budget-items /
  votes / participations (l.268+).
- **Wallet-refills** : `POST /api/v2/wallet-refills/` (l.985) — nécessite une clé avec
  `gift_asset` défini ; recharge UNIQUEMENT cet asset.
- **Bénévolat** : section « Bénévolat » de `api_v2/GUIDELINES.md` et chemins
  `/api/v2/volunteer-*` de l'OpenAPI. Ordre : tâche → planning → besoins → inscriptions.

---

## Vérifier le résultat

Toujours contrôler le **code HTTP** et relire la ressource :
```bash
curl -sk -o /dev/null -w "HTTP %{http_code}\n" ...        # 201 créé / 400 corps / 403 perm
curl -sk -H "Authorization: $K" "https://$H/api/v2/pages/accueil/"   # relecture (uuid OU slug)
```
