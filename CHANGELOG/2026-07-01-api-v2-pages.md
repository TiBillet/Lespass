# API v2 — Pages et Blocs (`/api/v2/pages/`, `/api/v2/blocs/`)

## Ce qui a été fait

Routes API v2 permettant de créer, lire, modifier et supprimer des **pages publiques**
composées de **blocs de contenu** (constructeur de pages par blocs).

Deux groupes de routes :
- `/api/v2/pages/` — CRUD de pages, catalogue des types de blocs, ajout de blocs
- `/api/v2/blocs/{uuid}/` — édition et suppression d'un bloc individuel

La création de page est **atomique** : si un bloc échoue (URL image invalide, slug
réservé, etc.), toute la création est annulée sans enregistrement partiel.

### Permission requise

La clé API (`ExternalApiKey`) doit avoir le booléen **`page`** coché dans l'admin
Django. Ce droit unique couvre toutes les routes pages ET blocs. Sans ce droit : 403.

### Sécurité intégrée

- **Anti-SSRF** : les URL images pointant vers des hôtes internes/privés/loopback
  sont rejetées (400).
- **Neutralisation XSS** dans les champs lien (`bouton_url`, `bouton2_url`,
  `embed_url`) : les schémas dangereux (`javascript:`, `data:`, `vbscript:`) sont
  vidés silencieusement.
- **Sanitisation HTML** : le champ `text` est nettoyé par `nh3` (whitelist de balises).
- **Slug réservé** : `admin`, `event`, `api`, etc. sont refusés (400).
- **Isolation tenant** : chaque clé ne voit que les pages de son propre schéma.

### Modifications

| Fichier | Changement |
|---|---|
| `pages/models.py` | Modèles `Page` + `Bloc` avec leurs champs |
| `pages/blocs_catalogue.py` | Source unique des 14 types et leurs champs autorisés |
| `api_v2/serializers.py` | `WebPageSerializer`, `WebPageElementSerializer`, `WebPageCreateSerializer` |
| `api_v2/views.py` | `PageViewSet`, `BlocViewSet` (CRUD + images URL/multipart + anti-SSRF) |
| `api_v2/urls.py` | Routes `pages`, `pages/{uuid}/blocs`, `blocs` |
| `api_v2/openapi-schema.yaml` | Paths + schemas WebPage, WebPageElement, WebPageCreate, WebPagePatch, WebPageElementCreate, BlockType, ImageObject |
| `api_v2/GUIDELINES.md` | Section « Pages API » |

### Tests automatisés

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -q
```

29 tests : CRUD page, catalogue block-types, ajout/édition/suppression bloc,
images par URL, upload multipart (images uniquement), anti-SSRF, neutralisation XSS,
isolation tenant, slug réservé, atomicité, vérification que l'upload vidéo est ignoré,
sous-pages via `isPartOf` (création avec parent par slug, parent introuvable → 400,
hiérarchie deux niveaux refusée → 400, PATCH retire le parent).

**Vidéo** : l'upload de fichier vidéo n'est **pas exposé** par l'API. Pour intégrer
une vidéo, utiliser le bloc **EMBED** avec `embed_url` (YouTube, Vimeo, PeerTube —
rendu en iframe côté front). Le champ modèle `video` reste éditable depuis l'admin.

---

## Tests manuels

### Prérequis : créer une clé API avec permission `page`

1. Aller dans l'admin Django : `https://lespass.tibillet.localhost/admin/`
2. Sidebar → **Api keys** → **Ajouter une Api key**
3. Remplir le nom (ex. `test-pages`), cocher **Page** dans les permissions.
4. Sauvegarder → **copier la clé affichée** (elle n'est visible qu'une seule fois).
5. Exporter la clé dans le shell :
   ```bash
   export CLE="<la-cle-copiee>"
   export BASE="https://lespass.tibillet.localhost"
   ```

---

### Scénario 1 — Catalogue des types de blocs

```bash
curl -sk -H "Authorization: Api-Key $CLE" $BASE/api/v2/pages/block-types/ | python3 -m json.tool
```

Attendu : 200 avec `{"blockTypes":[{"type":"HERO","label":"...","fields":[...]},...]}`
et les 14 types : HERO, PARAGRAPHE, IMAGE_TEXTE, CTA, TEMOIGNAGE, VIDEO_TEXTE,
CARTE, IMAGE, CARTE_LEAFLET, INFOS, FAQ, EVENEMENTS, GALERIE, EMBED.

---

### Scénario 2 — Créer une page avec deux blocs (création atomique)

```bash
curl -sk -X POST $BASE/api/v2/pages/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "@context": "https://schema.org",
    "@type": "WebPage",
    "name": "Test API pages",
    "additionalProperty": [
      {"@type": "PropertyValue", "name": "slug",   "value": "test-api-pages"},
      {"@type": "PropertyValue", "name": "publie", "value": true}
    ],
    "hasPart": [
      {
        "additionalType": "HERO",
        "headline": "Bienvenue",
        "image": "https://picsum.photos/1200/400",
        "additionalProperty": [
          {"@type": "PropertyValue", "name": "bouton_label", "value": "Voir l'\''agenda"},
          {"@type": "PropertyValue", "name": "bouton_url",   "value": "/event/"}
        ]
      },
      {
        "additionalType": "PARAGRAPHE",
        "headline": "À propos",
        "text": "<p>Un lieu culturel <strong>coopératif</strong>.</p>"
      }
    ]
  }' | python3 -m json.tool
```

Attendu : 201 avec l'objet WebPage (identifier, name, url, hasPart avec 2 blocs).
Noter l'`identifier` (UUID) de la page et des blocs.

```bash
export PAGE_UUID="<uuid-page>"
export BLOC_UUID="<uuid-premier-bloc>"
```

---

### Scénario 3 — Lister les pages

```bash
curl -sk -H "Authorization: Api-Key $CLE" $BASE/api/v2/pages/ | python3 -m json.tool
```

Attendu : 200 avec `{"results":[...]}` contenant la page créée.

---

### Scénario 4 — Détail d'une page par UUID

```bash
curl -sk -H "Authorization: Api-Key $CLE" $BASE/api/v2/pages/$PAGE_UUID/ | python3 -m json.tool
```

Attendu : 200 WebPage avec `hasPart` incluant les blocs.

### Scénario 4b — Détail par slug

```bash
curl -sk -H "Authorization: Api-Key $CLE" $BASE/api/v2/pages/test-api-pages/ | python3 -m json.tool
```

Attendu : même résultat que par UUID.

---

### Scénario 5 — Modifier les méta de la page (PATCH)

```bash
curl -sk -X PATCH $BASE/api/v2/pages/$PAGE_UUID/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test API pages (renommée)",
    "additionalProperty": [
      {"@type": "PropertyValue", "name": "noindex", "value": true}
    ]
  }' | python3 -m json.tool
```

Attendu : 200 WebPage avec `name` mis à jour et `noindex=true` dans `additionalProperty`.

---

### Scénario 6 — Ajouter un bloc (JSON)

```bash
curl -sk -X POST $BASE/api/v2/pages/$PAGE_UUID/blocs/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "additionalType": "CTA",
    "headline": "Rejoignez-nous",
    "alternativeHeadline": "Devenez membre",
    "additionalProperty": [
      {"@type": "PropertyValue", "name": "bouton_label", "value": "S'\''inscrire"},
      {"@type": "PropertyValue", "name": "bouton_url",   "value": "/memberships/"}
    ]
  }' | python3 -m json.tool
```

Attendu : 201 WebPageElement avec `additionalType: "CTA"`.

---

### Scénario 7 — Ajouter un bloc GALERIE (liste ImageObject[])

```bash
curl -sk -X POST $BASE/api/v2/pages/$PAGE_UUID/blocs/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "additionalType": "GALERIE",
    "headline": "Notre galerie",
    "image": [
      {"@type": "ImageObject", "contentUrl": "https://picsum.photos/800/600?random=1", "caption": "Image 1"},
      {"@type": "ImageObject", "contentUrl": "https://picsum.photos/800/600?random=2", "caption": "Image 2"}
    ]
  }' | python3 -m json.tool
```

Attendu : 201 WebPageElement avec `image` contenant une liste d'ImageObject.

---

### Scénario 8 — Ajouter un bloc par upload multipart

```bash
curl -sk -X POST $BASE/api/v2/pages/$PAGE_UUID/blocs/ \
  -H "Authorization: Api-Key $CLE" \
  -F "additionalType=IMAGE" \
  -F "headline=Photo depuis le disque" \
  -F "image=@/tmp/test-image.jpg" | python3 -m json.tool
```

Attendu : 201 WebPageElement avec `image` = URL du fichier stocké sur le serveur.

---

### Scénario 9 — Modifier un bloc (PATCH)

```bash
curl -sk -X PATCH $BASE/api/v2/blocs/$BLOC_UUID/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "headline": "Bienvenue (modifié)",
    "additionalProperty": [
      {"@type": "PropertyValue", "name": "badge", "value": "Nouveau"}
    ]
  }' | python3 -m json.tool
```

Attendu : 200 WebPageElement avec le titre mis à jour.

---

### Scénario 10 — Supprimer un bloc

```bash
curl -sk -X DELETE $BASE/api/v2/blocs/$BLOC_UUID/ \
  -H "Authorization: Api-Key $CLE" -o /dev/null -w "%{http_code}\n"
```

Attendu : 204.
Vérifier que le bloc a disparu : `GET /api/v2/pages/$PAGE_UUID/` → `hasPart` ne le contient plus.

---

### Scénario 11 — Test sécurité : XSS dans bouton_url (javascript:)

```bash
curl -sk -X POST $BASE/api/v2/pages/$PAGE_UUID/blocs/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "additionalType": "CTA",
    "headline": "Test XSS",
    "additionalProperty": [
      {"@type": "PropertyValue", "name": "bouton_label", "value": "Cliquer"},
      {"@type": "PropertyValue", "name": "bouton_url",   "value": "javascript:alert(1)"}
    ]
  }' | python3 -m json.tool
```

Attendu : 201, mais dans la réponse le champ `bouton_url` est **vide** (neutralisé).
Vérifier dans `additionalProperty` que `bouton_url` a `value: ""` ou est absent.

Tester également `data:text/html,<script>...` et `vbscript:MsgBox` → même comportement.

---

### Scénario 12 — Test sécurité : SSRF (image vers hôte interne)

```bash
curl -sk -X POST $BASE/api/v2/pages/$PAGE_UUID/blocs/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "additionalType": "IMAGE",
    "headline": "Test SSRF",
    "image": "http://127.0.0.1/secret"
  }' -o /dev/null -w "%{http_code}\n"
```

Attendu : **400**. Tester aussi `http://localhost/`, `http://192.168.1.1/`,
`http://169.254.169.254/` (metadata AWS) → 400 dans tous les cas.

---

### Scénario 13 — Slug réservé refusé

```bash
curl -sk -X POST $BASE/api/v2/pages/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "@type": "WebPage",
    "name": "Test slug réservé",
    "additionalProperty": [
      {"@type": "PropertyValue", "name": "slug", "value": "admin"}
    ]
  }' | python3 -m json.tool
```

Attendu : 400 avec un message indiquant que le slug est réservé.
Tester aussi `event`, `api`, `my_account` → 400.

---

### Scénario 14 — Sans clé API (403)

```bash
curl -sk $BASE/api/v2/pages/ -o /dev/null -w "%{http_code}\n"
```

Attendu : 403.

---

### Scénario 15 — Vérification du rendu public

Après création de la page `test-api-pages` avec des blocs publiés :

```bash
curl -sk https://lespass.tibillet.localhost/test-api-pages/ | grep -i "bienvenue"
```

Attendu : la page HTML contient le contenu du bloc HERO (titre "Bienvenue…").
Vérification visuelle : ouvrir `https://lespass.tibillet.localhost/test-api-pages/`
dans Chrome → la page s'affiche avec les blocs empilés dans l'ordre.

---

### Scénario 16 — Créer une sous-page via isPartOf

```bash
# Créer la page parente
curl -sk -X POST $BASE/api/v2/pages/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Page parente",
    "additionalProperty": [
      {"@type": "PropertyValue", "name": "slug", "value": "page-parente"},
      {"@type": "PropertyValue", "name": "publie", "value": true}
    ],
    "hasPart": []
  }' | python3 -m json.tool

# Créer la sous-page en référençant le parent par son slug
curl -sk -X POST $BASE/api/v2/pages/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sous-page",
    "isPartOf": "page-parente",
    "additionalProperty": [
      {"@type": "PropertyValue", "name": "slug", "value": "sous-page"},
      {"@type": "PropertyValue", "name": "publie", "value": true}
    ],
    "hasPart": []
  }' | python3 -m json.tool
```

Attendu : 201 avec `isPartOf: { "@type": "WebPage", "name": "Page parente", ... }`.

Tester aussi `isPartOf` = UUID (au lieu du slug) → même résultat.

Tenter un parent inexistant (`isPartOf: "slug-qui-nexiste-pas"`) → 400.

Tenter deux niveaux (sous-page d'une sous-page) → 400 (un seul niveau autorisé).

Pour retirer le parent (PATCH) :

```bash
export SOUS_PAGE_UUID="<uuid-sous-page>"
curl -sk -X PATCH $BASE/api/v2/pages/$SOUS_PAGE_UUID/ \
  -H "Authorization: Api-Key $CLE" \
  -H "Content-Type: application/json" \
  -d '{"isPartOf": ""}' | python3 -m json.tool
```

Attendu : 200 et `isPartOf` absent de la réponse (page redevenue top-level).

---

### Nettoyage — Supprimer la page de test

```bash
curl -sk -X DELETE $BASE/api/v2/pages/$PAGE_UUID/ \
  -H "Authorization: Api-Key $CLE" -o /dev/null -w "%{http_code}\n"
```

Attendu : 204. Tous les blocs sont supprimés en cascade.
