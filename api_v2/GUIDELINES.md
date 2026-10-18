# TiBillet API v2 — Semantic Open Data Guidelines

These guidelines define how to build the v2 API with a strong focus on semantic, standards-based open data.

- Django REST Framework using ViewSets
  - Use plain `viewsets.ViewSet` (NOT ModelViewSet / ReadOnlyModelViewSet: too much hidden magic, see root `GUIDELINES.md`). Write `list()`, `retrieve()`, `create()`… explicitly, and use `@action()` for extra routes. Expose only necessary actions.
  - Validation: prefer `serializers.Serializer`; `ModelSerializer` is tolerated in `api_v2/` only (root `GUIDELINES.md`).
  - Use routers to build URLs.
- REST philosophy
  - Resources-centered; nouns for endpoints; HTTP verbs for actions.
  - Use proper HTTP status codes and content negotiation.
  - Immutable identifiers; representations may evolve.
- Semantic variable names only
  - Choose domain names that map to schema.org types/properties where possible (e.g., name, description, startDate, endDate, location).
- API keys and permissions (granular)
  - Authentication by API key sent in header: `Authorization: Api-Key <key>`.
  - Granular authorization per resource/action with custom DRF permission classes defined in this folder.
  - Keys must be manageable from Django admin.
  - Most permissions are booleans on `ExternalApiKey` mapped by basename in `api_permissions()`. Exception — the wallet-refill route: `api_permissions()["walletrefill"] = bool(self.gift_asset_id)`. The `gift_asset` FK (limited to the non-fiat categories in `AssetFedowPublic.REFILLABLE_CATEGORIES`: `TNF`/`TIM`/`FID`/`BDG`) acts as BOTH the on/off switch and the per-key asset restriction. The view re-checks that the requested asset is in a refillable category and equals the key's `gift_asset`.
- Testing strategy
  - Use Poetry to run tests: `poetry install` then `poetry run pytest`.
  - Example: `poetry run pytest -q tests/pytest/test_events_list.py`.
  - Unit/integration tests run with plain pytest (not Django `manage.py test`).
  - Prefer black-box HTTP calls against a dev hostname like `lespass.tibillet.localhost`.
  - Keep tests in standalone Python scripts under `tests/` or project-level `tests/` executed by `pytest`.
- Documentation
  - Keep Markdown documentation in this `api_v2` folder close to the code (this file plus additional docs as needed).
  - OpenAPI doc is maintained manually in `api_v2/openapi-schema.yaml` (drf-spectacular is not used).
  - Update the YAML when endpoints or payloads change.

Image uploads (security)
- For Event and PostalAddress create endpoints, image uploads are accepted via multipart/form-data using fields `img` and `sticker_img`.
- The serializers perform strict validation using Pillow: only `image/*` content-types are accepted and files must open/verify as images. Non-images are rejected with 400.
- Example (multipart): see `openapi-schema.yaml` for `POST /api/v2/events/` and `POST /api/v2/postal-addresses/`.

PostalAddress endpoints (schema.org/PostalAddress)
- Base path: /api/v2/postal-addresses/
- Authentication: header `Authorization: Api-Key <your_key>` (same permission toggle as `event`)
- Representations use schema.org names (streetAddress, addressLocality, etc.).

Endpoints
- GET /api/v2/postal-addresses/ → list addresses (wrapped in `{ "results": [...] }` when not paginated)
- GET /api/v2/postal-addresses/{id}/ → retrieve one address by numeric id
- POST /api/v2/postal-addresses/ → create a new address
- DELETE /api/v2/postal-addresses/{id}/ → delete an address

Example create payload
```json
{
  "@type": "PostalAddress",
  "name": "Test Address",
  "streetAddress": "123 Rue de Test",
  "addressLocality": "Testville",
  "addressRegion": "TV",
  "postalCode": "99999",
  "addressCountry": "FR",
  "geo": {"latitude": 43.7, "longitude": 7.25}
}
```

Linking an address to an Event
- POST /api/v2/events/{uuid}/link-address/
  - Body options:
    - `{ "postalAddressId": 123 }` to link an existing address; or
    - a schema.org/PostalAddress object (same as above) to create & link in one call.
  - Response: updated Event (schema.org/Event) with `location.address` populated.

Notes
- For now the PostalAddress id (numeric) is not included in the schema.org representation. Use list filters or keep ids on client side if you need later deletion.
- Semantic output
  - Represent data using schema.org types/terms whenever possible (JSON-LD or schema.org-like JSON fields).
  - For `Event` use https://schema.org/Event (e.g., `@context`, `@type`, `name`, `description`, `startDate`, `endDate`, `location`, `offers`).

Schema.org mapping (Event)
- Incoming (POST /api/v2/events/) and outgoing (list/retrieve) use schema.org names:
  - @type (schema.org subtype, e.g., MusicEvent) → internal category mapping
  - additionalType (human-readable label, e.g., Concert, Festival, Volunteering) → internal category mapping
  - Rule: when the resolved category is ACTION (Volunteering), superEvent (UUID of parent) is required
  - maximumAttendeeCapacity ↔︎ Event.jauge_max
  - offers.eligibleQuantity.maxValue ↔︎ Event.max_per_user
  - disambiguatingDescription ↔︎ Event.short_description
  - description ↔︎ Event.long_description
  - sameAs (canonical external URL) and/or url ↔︎ Event.full_url (presence of `sameAs` implies external)
  - eventStatus: `https://schema.org/EventScheduled` when published; `https://schema.org/EventCancelled` when unpublished
  - audience: `{ "@type": "Audience", "audienceType": "private" }` when private; omitted when public
  - keywords: array of strings ↔︎ Tag names (created if missing)
  - image: array of URLs (main and sticker) — accepted but currently ignored at creation time
  - offers.returnPolicy.merchantReturnDays ↔︎ Event.refund_deadline
  - additionalProperty (PropertyValue[]):
    - `{ name: "optionsRadio", value: ["OptionName", ...] }` ↔︎ link `options_radio` by name
    - `{ name: "optionsCheckbox", value: ["OptionName", ...] }` ↔︎ link `options_checkbox` by name
    - `{ name: "customConfirmationMessage", value: "..." }` ↔︎ Event.custom_confirmation_message

Examples
- Minimal create:
```json
{
  "@context": "https://schema.org",
  "@type": "Event",
  "name": "API v2 — Test create",
  "startDate": "2025-11-12T18:00:00Z"
}
```
- Extended create:
```json
{
  "@context": "https://schema.org",
  "@type": "Event",
  "name": "Concert",
  "startDate": "2025-12-20T19:00:00Z",
  "maximumAttendeeCapacity": 250,
  "disambiguatingDescription": "Soirée funk",
  "description": "Une soirée funk mémorable",
  "eventStatus": "https://schema.org/EventScheduled",
  "audience": {"@type":"Audience","audienceType":"private"},
  "keywords": ["Funk","Live"],
  "sameAs": "https://example.org/external-event",
  "offers": {
    "eligibleQuantity": {"maxValue": 4},
    "returnPolicy": {"merchantReturnDays": 7}
  },
  "additionalProperty": [
    {"@type":"PropertyValue","name":"optionsRadio","value":["Salle"]},
    {"@type":"PropertyValue","name":"customConfirmationMessage","value":"Merci pour votre réservation !"}
  ]
}
```

Usage notes
- Endpoints
  - GET /api/v2/events/ → returns a list wrapped as `{ "results": [Event, ...] }` when not paginated.
  - GET /api/v2/events/{uuid}/ → retrieve a single event by its UUID.
  - POST /api/v2/events/ → create a new Event with a minimal schema.org/Event payload (see examples above). Response 201 with the schema.org/Event representation (including `identifier`).
  - DELETE /api/v2/events/{uuid}/ → delete an Event by UUID. Response 204 on success.
- Authentication
  - Send header: `Authorization: Api-Key <your_key>`
- Running tests (Poetry)
  - `poetry install`
  - `poetry run pytest -qs tests/pytest`
  - Tests are ordered to run in the following sequence for Event CRUD: create → list → retrieve → delete. A `conftest.py` hook enforces this order.
  - The create test also stores the created `identifier` and `name` in pytest cache; subsequent tests read from this cache to make assertions independent of demo data.



---

## Running tests with Poetry and API key

You can pass the API key (and optionally the base URL) directly via pytest CLI flags.

Examples:

- `poetry run pytest -qs tests/pytest --api-key <YOUR_KEY>`
- `poetry run pytest -qs tests/pytest --api-key <YOUR_KEY> --api-base-url https://lespass.tibillet.localhost`

Notes:
- The `--api-key` and `--api-base-url` flags are injected into environment variables `API_KEY` and `API_BASE_URL` by a session fixture in `tests/pytest/conftest.py`.
- Tests also honor pre-set environment variables if you prefer `export API_KEY=...`.

---

## Skill agent IA — `TECH_DOC/SKILLS/tibillet-api/`

Le skill qui apprend a un agent (Claude Code) a piloter cette API vit dans
**`TECH_DOC/SKILLS/tibillet-api/`**, avec tous les autres skills du projet
(voir `TECH_DOC/SKILLS/README.md`).

**Le skill est loin du code qu'il decrit : c'est a toi d'y penser. Si tu modifies le
mapping semantique, les permissions ou le catalogue de blocs, mets le skill a jour dans
le MEME commit.** Un skill qui ment est pire que pas de skill : l'agent le croit.

`.claude/` n'est jamais committe (outillage local). Chaque dev cree donc le lien une
fois, depuis la racine du depot :

```bash
mkdir -p .claude/skills
ln -sfn "$(pwd)/TECH_DOC/SKILLS/tibillet-api" .claude/skills/tibillet-api
```

Le lien doit etre **absolu** (`$(pwd)/...`) : un lien relatif n'est pas resolu de facon
fiable par le chargeur de skills. Relancer Claude Code apres creation du lien.

**Jamais de cle API en clair** dans ce dossier : il est versionne. Les scripts lisent
la cle depuis l'environnement (`$TIBILLET_API_KEY`). Pour obtenir une cle de dev :
`python TECH_DOC/SKILLS/tibillet-api/scripts/creer_cle_api.py --tenant lespass --perms page`.

---

## Pages API (schema.org/WebPage)

### Permission

La clé API (`ExternalApiKey`) doit avoir le booléen **`page`** coché dans l'admin.
Ce droit ouvre à la fois les routes `/api/v2/pages/` et `/api/v2/blocs/`.
Sans ce droit : 403.

_The API key (`ExternalApiKey`) must have the `page` boolean enabled in the admin.
This single permission covers both `/api/v2/pages/` and `/api/v2/blocs/` routes._

### Endpoints

| Méthode | URL | Rôle | Réponse |
|---|---|---|---|
| GET | `/api/v2/pages/` | Liste des pages du tenant | 200 `{"results":[WebPage,...]}` |
| POST | `/api/v2/pages/` | Crée une page + ses blocs (nested `hasPart`), **atomique** | 201 WebPage |
| GET | `/api/v2/pages/block-types/` | **Catalogue** des types de blocs et champs autorisés | 200 `{"blockTypes":[...]}` |
| GET | `/api/v2/pages/{uuid}/` | Détail (lookup par **uuid OU slug**) | 200 WebPage / 404 |
| PATCH | `/api/v2/pages/{uuid}/` | Édite les **méta** de la page (titre, slug, publie, SEO…) | 200 WebPage |
| DELETE | `/api/v2/pages/{uuid}/` | Supprime la page (cascade blocs) | 204 |
| POST | `/api/v2/pages/{uuid}/blocs/` | Ajoute **un** bloc (JSON ou multipart) | 201 WebPageElement |
| PATCH | `/api/v2/blocs/{uuid}/` | Édite un bloc (JSON ou multipart) | 200 WebPageElement |
| DELETE | `/api/v2/blocs/{uuid}/` | Supprime un bloc | 204 |

### Mapping Page → WebPage (schema.org)

```
@context  = "https://schema.org"
@type     = "WebPage"
identifier = uuid
name       = titre
url        = "/<slug>/"
description = meta_description
isPartOf   = WebPage minimal {identifier, url, name} si la page a un parent ; absent sinon
hasPart    = [WebPageElement, ...]
additionalProperty = PropertyValue[] : slug, position, publie,
                     est_accueil, noindex, meta_title
```

#### Sous-pages (champ `isPartOf`)

`isPartOf` expose la page parente en **sortie** (objet WebPage minimal : `@type`, `identifier`, `url`, `name`).
En **entrée** (POST / PATCH), `isPartOf` accepte un **uuid ou slug** de la page parente.

Règles (validées par `Page.clean()` via `full_clean()`) :
- Un seul niveau de hiérarchie (la page parente ne peut pas elle-même avoir un parent).
- La page d'accueil (`est_accueil=True`) ne peut pas être sous-page.
- Une page ayant des enfants ne peut pas devenir sous-page.

Violation → **400** avec le message d'erreur du modèle.

**En PATCH** : `isPartOf: ""` (chaîne vide) ou `isPartOf: null` retire le parent (la page redevient top-level).

Exemple création avec parent :
```json
POST /api/v2/pages/
{
  "name": "Sous-page",
  "isPartOf": "slug-du-parent",
  "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "ma-sous-page"}],
  "hasPart": []
}
```

Exemple sortie avec parent :
```json
{
  "@type": "WebPage",
  "identifier": "...",
  "name": "Sous-page",
  "isPartOf": {
    "@type": "WebPage",
    "identifier": "...",
    "url": "/slug-du-parent/",
    "name": "Page parente"
  }
}
```

### Mapping Bloc → WebPageElement (schema.org)

```
@type              = "WebPageElement"
identifier         = uuid
additionalType     = type_bloc   ← champ pivot (ex: "HERO", "GALERIE"…)
headline           = titre
alternativeHeadline = sous_titre
text               = texte HTML nettoyé par nh3
image              = URL (string) ou ImageObject[] pour GALERIE / PARTENAIRES
position           = ordre dans la page
additionalProperty = PropertyValue[] pour tout le reste (voir ci-dessous)
```

Champs portés par `additionalProperty` (PropertyValue[]) :
`surtitre`, `badge`, `image_secondaire`, `image_position`,
`bouton_label`, `bouton_url`, `bouton2_label`, `bouton2_url`,
`auteur_nom`, `auteur_role`, `auteur_photo`,
`points_gps`, `contenu`, `nombre_max`, `repliable`, `embed_url`, `hauteur_px`.
(`video` n'est PAS settable via l'API — cf. § Vidéo. Un `video` en additionalProperty
est silencieusement ignoré.)

Format PropertyValue : `{"@type":"PropertyValue","name":"<clé>","value":<valeur>}`.
`value` accepte string, nombre, booléen, liste ou objet JSON.

### Les types de blocs (additionalType)

`HERO`, `PARAGRAPHE`, `IMAGE_TEXTE`, `CTA`, `TEMOIGNAGE`, `VIDEO_TEXTE`,
`CARTE`, `IMAGE`, `CARTE_LEAFLET`, `INFOS`, `FAQ`, `EVENEMENTS`, `GALERIE`, `EMBED`,
`MARKDOWN`, `LISTE_SOUS_PAGES`, `IFRAME`, `PARTENAIRES`, `NEWSLETTER`.

- **`IFRAME`** : contenu intégré libre. `embed_url` (rendu seulement si l'hôte est
  autorisé par le superadmin ROOT) + `hauteur_px`.
- **`NEWSLETTER`** : formulaire d'inscription Ghost. `embed_url` = instance Ghost
  (data-site), `headline`/`alternativeHeadline` = titre/description du formulaire.
- **`PARTENAIRES`** : bande de logos (images via ImageObject[], cf. § Images).

Les champs autorisés par type sont donnés par `GET /api/v2/pages/block-types/`
(source unique : `pages/blocs_catalogue.py`) — **toujours** interroger cet endpoint
plutôt que coder la liste en dur.

### Images

**Par URL (JSON)** — champ `image` = URL `http`/`https` → téléchargée par le serveur
(validation Pillow, ≤ 10 Mo).
Pour **GALERIE** et **PARTENAIRES** : `image` = liste d'ImageObject
`[{"@type":"ImageObject","contentUrl":"https://...","caption":"..."}]`.
Pour **PARTENAIRES**, la clé optionnelle `"url"` rend le logo cliquable (nouvel onglet) :
`{"@type":"ImageObject","contentUrl":"https://…/logo.png","caption":"Partenaire","url":"https://partenaire.exemple/"}`
(les schémas dangereux sont neutralisés côté serveur).

**Upload multipart** (`POST /api/v2/pages/{uuid}/blocs/` ou `PATCH /api/v2/blocs/{uuid}/`) :
champs fichier `image`, `image_secondaire`, `auteur_photo` en `multipart/form-data`.

**Vidéo** : utiliser le bloc **EMBED** (`embed_url` = URL YouTube/Vimeo/PeerTube, rendu en iframe).
L'upload de fichier vidéo n'est **pas exposé** par l'API pour éviter d'héberger des fichiers lourds.
Le champ modèle `video` reste accessible via l'admin Django.

### Sécurité

- **Anti-SSRF** : une URL vers un hôte interne/privé/loopback est refusée (400).
  Les schémas non `http`/`https` sont également refusés.
- **Neutralisation des champs lien** (`bouton_url`, `bouton2_url`, `embed_url`) :
  les schémas dangereux (`javascript:`, `data:`, `vbscript:`) sont vidés
  silencieusement à la création/édition (pas d'erreur, champ vide).
- **Sanitisation HTML** : `text` (WYSIWYG) est nettoyé par nh3 (whitelist de balises),
  rendu sûr côté serveur.
- **Slug réservé** : `admin`, `event`, `api`, etc. sont refusés à la création/édition (400).
- **Création atomique** : une erreur dans un bloc (URL image invalide, slug réservé)
  annule toute la création — pas d'enregistrement partiel.
- **Isolation multi-tenant** : chaque clé ne voit que les pages de son propre tenant.

### Exemple de payload — création nested

```json
POST /api/v2/pages/
{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "name": "Accueil",
  "additionalProperty": [
    {"@type": "PropertyValue", "name": "slug",   "value": "accueil"},
    {"@type": "PropertyValue", "name": "publie", "value": true}
  ],
  "hasPart": [
    {
      "additionalType": "HERO",
      "headline": "Bienvenue",
      "image": "https://exemple.fr/hero.jpg",
      "additionalProperty": [
        {"@type": "PropertyValue", "name": "bouton_label", "value": "Voir l'agenda"},
        {"@type": "PropertyValue", "name": "bouton_url",   "value": "/event/"}
      ]
    },
    {
      "additionalType": "PARAGRAPHE",
      "headline": "À propos",
      "text": "<p>Un lieu culturel <strong>coopératif</strong>.</p>"
    }
  ]
}
```

### Tests automatisés

```bash
docker exec -e API_KEY=dummy lespass_django poetry run pytest tests/pytest/test_pages_api.py -v
```

Tests (`tests/pytest/test_pages_api.py`) : CRUD page, catalogue block-types, ajout/édition/
suppression bloc, images par URL, upload multipart, anti-SSRF, neutralisation XSS dans les
champs lien, isolation tenant, slug réservé, atomicité, et création des blocs IFRAME
(hauteur_px), NEWSLETTER (embed_url) et PARTENAIRES (logos cliquables `url`).

Comptabilité — closures, entries, chart of accounts (spec `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-comptables/CHANTIER-06-A-api-comptable.md`)
- Read by an accounting software (Dolibarr, Paheko…) every night. Read-only (`GET` only).
- Permission: `ExternalApiKey.comptabilite` ("Comptabilité (lecture)"), mapped on basenames `closure` and `account`. The key alone is enough (`SemanticApiKeyPermission`, no "creator is still admin" check): the software runs at night without a human.
- **Exception to schema.org (deliberate)**: schema.org has no type for an accounting entry. Entries use the **French FEC column names** (`JournalCode`, `EcritureNum`, `CompteNum`, `Debit`, `Credit`…), the standard every French accounting software knows. Envelope fields are simple English camelCase.
- Amounts are **whole cents** (integers). Dates are ISO. No `ValidDate` in the JSON: entries arrive unlocked in the software (Dolibarr locks an entry whose ValidDate is filled).
- Entries are recomputed at every call with the venue's current chart of accounts: the software must import each closure **once** (keep its `uuid`).

Endpoints
- `GET /api/v2/closures/?after_number=<n>` → `{"results": [...]}`: the daily (J) closures to import, with sales, without the "reprise" J, numbered above `n`, by number. Not paginated. Cursor = the `number` of the last imported closure (never a date: the automatic J can be created late but dated earlier). `after_number` not a non-negative integer → 400.
- `GET /api/v2/closures/{uuid}/entries/` → `{"closure", "number", "accountingDate", "currency": "EUR", "amountUnit": "cent", "entries": [{"JournalCode", "JournalLib", "EcritureNum", "EcritureDate", "PieceRef", "PieceDate", "EcritureLib", "lines": [{"CompteNum", "CompteLib", "Debit", "Credit"}]}]}`.
- `GET /api/v2/closures/{uuid}/fec/` → the FEC file (`text/plain`, attachment), byte for byte the admin "FEC" button.
- `GET /api/v2/closures/{uuid}/sales/?after_number=<n>&limit=<m>` → `{"closure", "number", "accountingDate", "currency", "amountUnit", "results", "nextAfterNumber"}` (spec `CHANTIER-06-D-ventes.md`): the J's settled euro sales, split by TiBillet (`comptabilite/ventes_a_facturer.py`) into `orderedItem` (invoice lines at the sold price, `priceIdentifier` = the Dolibarr product's `ref_ext`), `invoicePayments`, `transfers` (top-ups, card emptyings) and `variousPayments` (offered top-ups, gift tokens taken back, payment gaps). Per account it equals the FEC. The key needs `comptabilite` **and** `sale` (`CleAvecLeDroitDesVentes`): `customer` publishes the buyer's uuid and **e-mail only**. Cursor = sale number; `limit` 1 to 1000 (default 500); `nextAfterNumber` null on the last page. Sales with nothing to write are skipped. 409 `unbalanced_entry` when a sale's payments do not cover its items.
- `GET /api/v2/accounts/` → `{"results": [{"accountNumber", "name", "active"}]}`: every account of the venue (inactive ones too: still used by exports), by number. Loads the default chart if the venue has none.

Refusals: `{"detail": sentence, "code": code}`
- 404 `not_exportable`: unknown uuid, weekly/monthly/yearly closure, J without sales, "reprise" J (same go-live rule as the admin FEC button, `comptabilite.tasks.refus_du_fec_avant_la_mise_en_service`). The software forgets it.
- 409 `missing_account` (an account or a journal is missing in the chart) or 409 `unbalanced_entry` (data altered after settlement; logged as an exception). The software retries later.

Tests: `tests/pytest/test_api_v2_comptabilite.py`, `tests/pytest/test_api_v2_ventes_comptables.py`, `tests/pytest/test_ventes_a_facturer.py` (dedicated schemas).

Catalogue for an accounting software — `GET /api/v2/products/?accounting=true` (spec `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-comptables/CHANTIER-06-C-catalogue.md`)
- Read every night by Dolibarr in "items and sales" mode (TiBillet is only a sales front; Dolibarr keeps the books from its own invoices). No new route: the products route, its permission unchanged (`product` right). Dolibarr's key has the `product` AND `comptabilite` rights.
- Every product (published or not, archived or not), every price (archived included), sorted by name then uuid, **rendered in French** whatever `Accept-Language` (the ETag must not depend on the client).
- Accounting properties in `additionalProperty` (schema.org `PropertyValue`): `productType`, `posCategory`, `vatRate` / `vatRateError`, `accountingAccount` / `accountingAccountError`, `forAccountingSync`, `archived`; per offer `archived`, `soldByWeightOrVolume`. The rules live in `laboutik/plan_comptable.py` (`taux_de_tva_du_produit`, `compte_pour_produit`, `est_une_vente_pour_la_comptabilite`), shared with the register and the FEC — never copied here.
- `ETag` = sha256 of the rendered JSON; `If-None-Match` equal (weak `W/` accepted) → 304 without body.

Tests: `tests/pytest/test_api_v2_catalogue_comptable.py` (dedicated schema).

Bénévolat — tasks, plannings, needs, sign-ups (spec `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` §6 bis, light version)
- Permission: `ExternalApiKey.volunteering` ("Bénévolat"), mapped on the four basenames `volunteertask`, `volunteerplanning`, `volunteerneed`, `volunteersignup`. Without it: 403. Code: `api_v2/views_benevolat.py`, `api_v2/serializers_benevolat.py`.
- `identifier` = the uuid, everywhere. A planning is also found by its slug (`/api/v2/volunteer-plannings/bar-novembre/`), like pages.
- Mapping:
  - `TacheBenevole` → `DefinedTerm` (`name`, `description`). DELETE of a task still used by a need → 409.
  - `PlanningBenevole` → `EventSeries`. Writable: `name`, `description`, and in `additionalProperty`: `slug`, `published`, `delaiDesinscriptionHeures`. **Read-only** (set in the admin): `requiredMembershipPlans` (uuids of membership products), `closingCalendar` (Calendar id). Counters `placesCouvertes`, `placesSouhaitees`, `renforts`, `creneauxVides` (upcoming needs). `subEvent` (its needs) on retrieve only. Reserved slugs: `besoin`, `desistement`.
  - `BesoinBenevole` → `Event` with `additionalType: "Volunteering"`, `superEvent` (planning), `about` (task), `remainingAttendeeCapacity`, `attendee` (first names only), `additionalProperty`: `nombreSouhaite`, `nombreInscrits`, `renforts`, `fermeture` (closure label or null).
  - `InscriptionBenevole` → `RsvpAction` with `object` (the need), `agent` (`email`, `givenName`, `familyName`: the key belongs to the venue team), `startTime`, `additionalProperty`: `inscritPar`, `rappelEnvoyeLe`.
- Dates of a need: the model stores day + local hours without timezone. `startDate` = a date only (whole day, no `endDate`) or a datetime (`endDate` required). No offset = venue local time; with an offset = converted to the venue timezone. The end is the same day (after the start) or the next day (before the start, e.g. 21:00 → 00:00); otherwise 400. Output carries the venue offset (`2026-11-06T21:00:00+01:00`). A need on a closed day is accepted, with `fermeture` filled.
- Sign-up creation = the team sign-up rules: account created if missing (inactive, attached to the venue, no login mail), first/last name written only if empty; missing in the account AND in the request → 400 and nothing is created; planning published and need not past, else 400; no membership check; `inscritPar` = the key's user. **201** when created, **200** with the existing sign-up when replayed. On creation the person gets "L'équipe t'a inscrit·e" with the signed "Je ne peux plus venir" link. DELETE: anytime, no mail. No PATCH.
- Lists are wrapped in `{"results": [...]}`, not paginated. Needs: `?planning=`, `?task=`, `?dateFrom=`, `?dateTo=` (past needs included). Sign-ups: `?need=`, `?planning=`.
- Not in the API (light version, D24): repeating needs (admin only), sign-up filters by email or date, writing memberships or closing calendar.

Tests: `tests/pytest/test_benevolat_api.py`.
