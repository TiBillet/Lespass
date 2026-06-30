# TiBillet API v2 — Semantic Event API

This API exposes semantic, standards-based representations using schema.org.

Base path (tenant): /api/v2/

Authentication
- Header: `Authorization: Api-Key <your_key>`
- API keys are managed in admin (ExternalApiKey). Ensure the `event` permission is enabled on the key.

Endpoints
- GET /api/v2/events/{id}/  → Retrieve a single Event
  - `{id}` accepts **either** the Event UUID **or** the front-end slug
    (e.g. `my-event-260620-0900-7d51dee7`), whose last 8 hex characters are the
    start of the UUID. Mirrors the front controller (`EventMVT.retrieve`):
    valid UUID → direct lookup; otherwise `uuid__startswith=<last 8 hex>`, then a
    `slug__startswith` fallback.
  - No `published` filter on retrieve (same behaviour as the front): an
    unpublished Event is retrievable by its UUID/slug.
  - Returns 404 (not 500) when the identifier matches no Event.
  - Response JSON-LD (schema.org/Event)
  - Note: `DELETE /api/v2/events/{uuid}/` and `POST /api/v2/events/{uuid}/link-address/`
    remain UUID-only (a non-UUID returns 404).
- GET /api/v2/events/ → List all published Events (semantic list)

OpenAPI / Auto‑generated docs (drf-spectacular)
- Schema: GET `/api/schema/` (JSON or YAML via content negotiation)
- Swagger UI: GET `/api/schema/swagger-ui/`
- Redoc UI: GET `/api/schema/redoc/`
- Scope: schema generation is limited to `/api/v2/...` endpoints via `SPECTACULAR_SETTINGS['SCHEMA_PATH_PREFIX'] = r'/api/v2'`.

Export the schema file (with Poetry)
- `poetry run python manage.py spectacular --color --file api_v2/openapi-schema.yaml`
- Add `--validate` to also validate against the OpenAPI spec

Lint the schema (yamllint)
- `api_v2/openapi-schema.yaml` is maintained **by hand**, so lint it to catch
  syntax / indentation / duplicate-key bugs (e.g. an over-indented child key).
- `docker exec lespass_django poetry run yamllint api_v2/openapi-schema.yaml`
- Config: `.yamllint` at the repo root — extends `relaxed`, **structural checks
  only** (`line-length` and `document-start` disabled). Exit code `0` = clean.

Example response
```
{
  "@context": "https://schema.org",
  "@type": "Event",
  "identifier": "7f1c0e5e-...",
  "name": "My Concert",
  "description": "Long description...",
  "startDate": "2025-07-21T19:00:00Z",
  "endDate": "2025-07-21T22:00:00Z",
  "location": {
    "@type": "Place",
    "address": {
      "@type": "PostalAddress",
      "streetAddress": "7 S. Broadway",
      "addressLocality": "Denver",
      "addressRegion": "CO",
      "postalCode": "80209",
      "addressCountry": "US"
    }
  },
  "url": "https://example.com/my-event"
}
```

Testing with pytest
- Prefer black-box tests hitting your dev hostname (e.g., `lespass.tibillet.localhost`).
- Use `requests` to perform HTTP calls and assert on the schema.org fields.

Notes
- Output is intentionally minimal; new properties can be added as needed following schema.org/Event.
- Membership endpoints and finer per-action permissions will follow the same pattern.

Gift token wallet refill
- POST /api/v2/wallet-refills/  → credit non-fiat tokens to a user wallet, from the place wallet, without payment.
- Refillable asset categories (NOT euro-backed): `TNF` (gift / "Cadeau"), `TIM` (time currency), `FID` (loyalty points), `BDG` (clocking/badge). Excluded: fiat (`TLF`, `FED`) and subscription (`SUB`). Canonical list: `AssetFedowPublic.REFILLABLE_CATEGORIES`.
- Permission: the API key must have a `gift_asset` set in the admin. This single field BOTH enables the `walletrefill` permission AND restricts the key to that one asset (no separate checkbox). The admin widget is filtered to the refillable categories.
- Body: `{ "email": "<user email>", "asset": "<asset uuid>", "amount": <int raw unit> }`
- **Required** header `Idempotency-Key: <string>` — this endpoint credits tokens, so the key is mandatory (a missing header returns 400). It is stored in DB on `LigneArticle.idempotency_key` (unique constraint = lock, per-tenant by schema isolation). A repeat with the **same key and same body** returns the stored transaction (208 Already Reported) instead of crediting again. The **same key with a different body** is rejected (409 Conflict). A key whose previous attempt failed on the Fedow side may be retried.
- Constraints: the asset must be in a refillable category AND must match the key's `gift_asset`; `amount` is a positive integer capped at `10000` (raw unit).
- Response 201 (or 208 Already Reported on idempotent replay): schema.org/MoneyTransfer
```json
{
  "@context": "https://schema.org",
  "@type": "MoneyTransfer",
  "identifier": "<fedow tx uuid>",
  "amount": 500,
  "asset": "<gift asset uuid>",
  "recipient": { "@type": "Person", "email": "alice@example.org" }
}
```
- Errors: 400 (invalid payload / missing Idempotency-Key), 403 (key not allowed / asset not authorized for this key), 409 (key reused with a different body, or a refill with this key is already in progress), 422 (asset not TNF, or amount above cap), 503 (Fedow unavailable).
- This is distinct from the v1 route `POST /api/wallet/get_stripe_checkout_with_email/`, which creates a **paid** Stripe top-up link.
