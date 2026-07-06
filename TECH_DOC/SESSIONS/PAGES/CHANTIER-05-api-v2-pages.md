# CHANTIER 05 — API v2 pour l'app `pages` (fabriquer un site via API)

> Spec de design validée avec le mainteneur le 2026-06-30. Vague 4 (API).
> Lire d'abord `SPEC.md` (modèles Page/Bloc) et `ETAT-REPRISE.md` (état du moteur).
> Prérequis api_v2 : `api_v2/GUIDELINES.md`, `api_v2/views.py`, `api_v2/permissions.py`.

## 1. Besoin

Permettre de **fabriquer un site web de A à Z via l'API v2** : créer des pages,
empiler tous les types de blocs, éditer, supprimer — sans passer par l'admin
Unfold. Cible immédiate : un client HTTP / un agent. Cible ultérieure (hors de
ce chantier) : un **MCP** qui s'appuie sur cette API.

Une **nouvelle permission** sur les clés API ouvre la création de **tous** les
blocs possibles.

## 2. Décisions validées (mainteneur, 2026-06-30)

| Décision | Choix retenu |
|---|---|
| **Format payload** | **schema.org / JSON-LD strict** (cohérent avec Event/Product) |
| **Mode de création** | **Nested + endpoints séparés** : page+blocs d'un coup ET édition bloc par bloc |
| **Images** | **Par URL** (création nested JSON) **ET upload multipart** (édition bloc) |
| **Types de blocs** | **Les 14** d'emblée (y compris GALERIE, EVENEMENTS, CARTE_LEAFLET, INFOS) |
| **Catalogue** | **Oui** : endpoint `block-types/` décrivant types + champs (pour le futur MCP) |
| **Mapping champs exotiques** | **`additionalProperty` fourre-tout typé** (pas de mapping sémantique fin) |
| **Config site (skin)** | **Hors périmètre** de ce chantier |

## 3. Permission (clé API)

Un **seul booléen** `page` sur `ExternalApiKey` (`BaseBillet/models.py`) ouvre
pages ET blocs.

```python
# BaseBillet/models.py — ExternalApiKey
page = models.BooleanField(default=False, verbose_name=_("Pages / Site web"))

def api_permissions(self):
    return {
        ...
        "page": self.page,
        "bloc": self.page,   # même droit pour les deux basenames
    }
```

- **Migration** `BaseBillet` : add field `page` (default False).
- **Admin** `ExternalApiKeyAdmin` (`Administration/admin_tenant.py:137`) :
  ajouter `'page'` dans `list_display` et dans `fields` (nouveau couple, ex.
  `('page', )` ou regroupé).

> ⚠️ `ExternalApiKey` vit dans `BaseBillet` (TENANT_APP). La migration est
> tenant-only — pas de dépendance croisée avec `pages`.

## 4. Endpoints (router api_v2)

`basename` = clé du mapping `api_permissions()` (mécanisme `SemanticApiKeyPermission`).

| Méthode | URL | basename | Rôle |
|---|---|---|---|
| GET | `/api/v2/pages/` | page | liste des pages du tenant |
| GET | `/api/v2/pages/{uuid}/` | page | détail (lookup **uuid OU slug**) |
| POST | `/api/v2/pages/` | page | crée page **+ tous ses blocs** (nested `hasPart`) |
| PATCH | `/api/v2/pages/{uuid}/` | page | édite **méta** page (titre, slug, publie, SEO…) |
| DELETE | `/api/v2/pages/{uuid}/` | page | supprime la page (cascade blocs) |
| GET | `/api/v2/pages/block-types/` | page | **catalogue** des 14 types + champs autorisés |
| POST | `/api/v2/pages/{uuid}/blocs/` | page | ajoute **un** bloc à la page (multipart possible) |
| PATCH | `/api/v2/blocs/{uuid}/` | bloc | édite un bloc (multipart possible) |
| DELETE | `/api/v2/blocs/{uuid}/` | bloc | supprime un bloc |

- `viewsets.ViewSet` explicites (méthodes nommées `list`/`retrieve`/`create`/
  `partial_update`/`destroy` + `@action`), comme le reste d'api_v2.
- `lookup_field = "uuid"` ; `parser_classes = (MultiPartParser, FormParser, JSONParser)`.
- **PATCH page = méta seulement.** Les blocs se gèrent par leurs endpoints
  dédiés (pas de remplacement de `hasPart` via PATCH page — évite l'ambiguïté
  « patch partiel vs remplacement total »).
- `block-types/` est une `@action(detail=False, methods=["get"])` sur le PageViewSet.

### Découverte enchaînée (intérêt du nested)
Les 3 modèles ont un `uuid` en PK. Une création nested renvoie chaque bloc avec
son `identifier` (uuid) → l'agent peut créer une page d'un coup puis cibler
`PATCH /api/v2/blocs/{uuid}/` sans relire la page.

## 5. Mapping schema.org (JSON-LD)

### Page → `WebPage`
| schema.org | source modèle |
|---|---|
| `@type` | `"WebPage"` |
| `identifier` | `uuid` |
| `name` | `titre` |
| `url` | `/<slug>/` |
| `description` | `meta_description` |
| `hasPart` | tableau de blocs (`WebPageElement`) |
| `additionalProperty[]` | `slug`, `position`, `publie`, `est_accueil`, `noindex`, `meta_title`, image de partage (URL) |

### Bloc → `WebPageElement`
| schema.org | source modèle |
|---|---|
| `@type` | `"WebPageElement"` |
| `identifier` | `uuid` |
| `additionalType` | `type_bloc` (HERO, PARAGRAPHE, …) — **pivot**, comme `Event.additionalType` |
| `headline` | `titre` |
| `alternativeHeadline` | `sous_titre` |
| `text` | `texte` (sanitizé) |
| `image` | `image` (URL en sortie) ; **GALERIE** → `ImageObject[]` (`contentUrl` + `caption`) |
| `additionalProperty[]` | **tout le reste** : `surtitre`, `badge`, `image_secondaire`, `video`, `image_position`, `bouton_label/url`, `bouton2_label/url`, `auteur_nom/role/photo`, `points_gps`, `contenu`, `nombre_max`, `repliable`, `embed_url` |

**`additionalProperty` fourre-tout typé** (pattern déjà utilisé par `Event`) :
```json
{"@type": "PropertyValue", "name": "<champ_modele>", "value": <valeur>}
```
- `name` = **nom exact du champ modèle** (`surtitre`, `points_gps`…) → l'agent
  remplit en se calant sur le catalogue (§7).
- `value` accepte string, nombre, booléen, liste/objet JSON (pour `points_gps`,
  `contenu`).

> Choix assumé : 4 propriétés standard + `additionalType` + `additionalProperty`.
> On n'invente pas 30 équivalents schema.org bancals. Honnête et extensible.

## 6. Images

- **Création nested (JSON)** : les champs image acceptent une **URL distante**.
  Le serveur télécharge (`requests.get`, timeout) puis **valide avec Pillow**
  (content-type `image/*`, ouverture/verify, taille max) — réutilise la
  validation stricte d'`EventCreateSerializer`. Rejet → 400.
- **Édition bloc (`POST /pages/{uuid}/blocs/`, `PATCH /blocs/{uuid}/`)** :
  **multipart/form-data** accepté pour upload de fichiers (`image`,
  `image_secondaire`, `auteur_photo`, `video`), via `request.FILES` (pattern
  EventViewSet).
- **GALERIE** : en nested, liste d'images par URL (`ImageObject[]` →
  `ImageGalerie`) ; upload multipart de plusieurs fichiers = itération suivante
  si besoin (documenter la limite).

## 7. Catalogue des types de blocs — `GET /api/v2/pages/block-types/`

But : permettre à un agent / au futur MCP de **découvrir** quels champs
remplir pour chaque type, sans lire le code.

Réponse (exemple) :
```json
{
  "blockTypes": [
    {
      "type": "HERO",
      "label": "Hero (bannière d'ouverture)",
      "fields": ["titre", "sous_titre", "image", "image_secondaire",
                 "bouton_label", "bouton_url", "bouton2_label", "bouton2_url"]
    },
    {
      "type": "FAQ",
      "label": "Question / réponse",
      "fields": ["titre", "texte", "repliable"]
    }
  ]
}
```
- Source de vérité des champs par type : **la matrice** (réutiliser/centraliser
  celle qui pilote `conditional_fields` dans `pages/admin.py`). Si elle n'est pas
  déjà exposée comme structure Python réutilisable, l'extraire en constante dans
  `pages/` (ex. `pages.blocs_catalogue.CHAMPS_PAR_TYPE`) et l'importer côté admin
  ET côté API → une seule source.
- `label` ← `get_type_bloc_display()` (i18n).

## 8. Sécurité (réutilise l'existant)

- `texte` → `sanitize_textfields` / `clean_html` (comme `BlocAdmin.save_model`).
  **Appliqué dans le serializer/viewset**, jamais stocké brut.
- `slug` → `valider_slug_non_reserve` (via `Page.full_clean()` ou appel direct du
  validateur) → 400 si réservé.
- `embed_url` → whitelist déjà appliquée **au rendu** (tag `embed_iframe`). Rien à
  ajouter à la création ; documenter que les hôtes non autorisés sont ignorés à
  l'affichage.
- **Isolation tenant** native (table par schéma, dual-list). Test cross-tenant
  obligatoire.
- Permission : `SemanticApiKeyPermission` (basename `page`/`bloc`). Sans le
  booléen `page` → 403.

## 9. Fichiers touchés

| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | + champ `page` sur `ExternalApiKey` + `api_permissions()` |
| `BaseBillet/migrations/0xxx_apikey_page.py` | add field `page` (tenant-only) |
| `Administration/admin_tenant.py` | `ExternalApiKeyAdmin` : `page` dans `list_display` + `fields` |
| `pages/blocs_catalogue.py` (neuf) | constante `CHAMPS_PAR_TYPE` (source unique matrice) |
| `pages/admin.py` | importer la matrice centralisée (pas de duplication) |
| `api_v2/serializers.py` | `PageSchemaSerializer`, `PageCreateSerializer`, `BlocSchemaSerializer`, `BlocCreateSerializer` + helper `additionalProperty` (lecture/écriture) + helper image-par-URL |
| `api_v2/views.py` | `PageViewSet`, `BlocViewSet` |
| `api_v2/urls.py` | register `pages` (basename `page`), `blocs` (basename `bloc`) |
| `api_v2/openapi-schema.yaml` | endpoints + payloads (maintenu manuellement) |
| `api_v2/GUIDELINES.md` | section mapping pages |
| `CHANGELOG.md` | entrée bilingue |
| `A TESTER et DOCUMENTER/api-v2-pages.md` | scénarios de test manuels |

## 10. Tests (pytest DB-only — `tests/pytest/test_pages_api.py`)

1. Création **nested** complète (page + plusieurs types de blocs) → 201, blocs créés, `identifier` présent.
2. Catalogue `block-types/` → 14 types, champs cohérents avec la matrice.
3. Ajout d'un bloc via `POST /pages/{uuid}/blocs/` → 201.
4. `PATCH /blocs/{uuid}/` (méta + un champ exotique via additionalProperty) → 200, valeur persistée.
5. `DELETE /blocs/{uuid}/` → 204.
6. `PATCH /pages/{uuid}/` méta (titre, publie) → 200.
7. **Permission refusée** : clé sans `page=True` → 403 sur create page ET bloc.
8. **Slug réservé** (`admin`, `event`…) → 400.
9. **Sanitize HTML** : `texte` avec `<script>` → nettoyé en base.
10. **Image par URL** (mock `requests.get` + image Pillow valide) → champ image rempli ; URL non-image → 400.
11. **Isolation cross-tenant** : clé du tenant A ne voit pas / ne modifie pas les pages du tenant B.

> Pièges multi-tenant : `tenant_context(tenant)` pour tout `create()` accédant au
> tenant ; `ExternalApiKey` est tenant-scoped. Cf. `tests/PIEGES.md`.

## 11. Découpage (sessions)

- **Session A** — Permission + socle CRUD page/bloc plats :
  champ `page` + migration + admin ; serializers Page/Bloc (champs plats + 4
  propriétés standard + additionalProperty) ; PageViewSet + BlocViewSet (sans
  catalogue) ; routes ; tests 1,3-9. Vérif `manage.py check` + pytest.
- **Session B** — Images (URL + multipart), catalogue `block-types/`, types
  structurés (GALERIE/EVENEMENTS/CARTE_LEAFLET/INFOS via additionalProperty +
  ImageObject) ; tests 2,10,11 ; openapi + GUIDELINES + CHANGELOG + fiche A TESTER.

## 12. Hors périmètre (notés pour plus tard)

- **MCP** (deuxième temps, s'appuie sur cette API).
- Exposition de `ConfigurationSite` (skin) via API.
- Upload multipart de plusieurs fichiers galerie en un appel.
- Mapping schema.org sémantique fin (on reste sur additionalProperty).

## 13. Contraintes projet

- i18n : libellés `_()` source **FR** ; makemessages/compilemessages = mainteneur.
- **Aucune opération git** par l'assistant. `ruff format` uniquement sur fichiers neufs.
- FALC : code verbeux, commentaires bilingues FR/EN.
