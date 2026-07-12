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

---

## Pages & blocs (le domaine le mieux outillé)

### 1. Catalogue des types de blocs (À FAIRE EN PREMIER)
```bash
curl -sk -H "Authorization: $K" "https://$H/api/v2/pages/block-types/"
# -> {"blockTypes":[{"type":"HERO","label":"...","fields":["titre","sous_titre"]}, ...]}
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
      {"additionalType":"HERO","headline":"Bienvenue","alternativeHeadline":"Un lieu coopératif"},
      {"additionalType":"PARAGRAPHE","headline":"À propos","text":"<p>Bonjour <strong>ici</strong>.</p>"},
      {"additionalType":"NEWSLETTER","headline":"Nos news",
       "additionalProperty":[{"name":"embed_url","value":"https://ghost.exemple.coop/"}]}
    ]
  }'
```

### 3. Ajouter un bloc à une page existante
```bash
curl -sk -X POST "https://$H/api/v2/pages/<PAGE_UUID>/blocs/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{
    "additionalType":"IFRAME","headline":"Le plan",
    "additionalProperty":[
      {"name":"embed_url","value":"https://www.openstreetmap.org/export/embed.html?bbox=..."},
      {"name":"hauteur_px","value":420}
    ]
  }'
```

### 4. Bloc avec images (GALERIE / PARTENAIRES)
`image` = liste d'`ImageObject`. Pour PARTENAIRES, la clé `url` rend le logo cliquable.
```bash
curl -sk -X POST "https://$H/api/v2/pages/<PAGE_UUID>/blocs/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{
    "additionalType":"PARTENAIRES","headline":"Ils nous soutiennent",
    "image":[
      {"@type":"ImageObject","contentUrl":"https://exemple.fr/logo-a.png","caption":"Coop A","url":"https://a.exemple/"},
      {"@type":"ImageObject","contentUrl":"https://exemple.fr/logo-b.png","caption":"Asso B"}
    ]
  }'
```
Images par **upload** : `multipart/form-data` sur le même endpoint (champ `image`, etc.).

### 5. Éditer / supprimer un bloc
```bash
curl -sk -X PATCH  "https://$H/api/v2/blocs/<BLOC_UUID>/" -H "Authorization: $K" \
  -H "Content-Type: application/json" -d '{"headline":"Titre corrigé"}'
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
- **Reservations** : `POST /api/v2/reservations/` (l.682).
- **Crowds/initiatives** : `POST /api/v2/initiatives/` + sous-ressources budget-items /
  votes / participations (l.268+).
- **Wallet-refills** : `POST /api/v2/wallet-refills/` (l.985) — nécessite une clé avec
  `gift_asset` défini ; recharge UNIQUEMENT cet asset.

---

## Vérifier le résultat

Toujours contrôler le **code HTTP** et relire la ressource :
```bash
curl -sk -o /dev/null -w "HTTP %{http_code}\n" ...        # 201 créé / 400 corps / 403 perm
curl -sk -H "Authorization: $K" "https://$H/api/v2/pages/accueil/"   # relecture (uuid OU slug)
```
