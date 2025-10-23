# TiBillet API v2 — Semantic Open Data Guidelines

These guidelines define how to build the v2 API with a strong focus on semantic, standards-based open data.

- Django REST Framework using ViewSets
  - Prefer ModelViewSet or ReadOnlyModelViewSet; expose only necessary actions.
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
