# TiBillet API v2 — Semantic Event API

This API exposes semantic, standards-based representations using schema.org.

Base path (tenant): /api/v2/

Authentication
- Header: `Authorization: Api-Key <your_key>`
- API keys are managed in admin (ExternalApiKey). Ensure the `event` permission is enabled on the key.

Endpoints
- GET /api/v2/events/{uuid}/  → Retrieve a single Event
  - Response JSON-LD (schema.org/Event)
- GET /api/v2/events/ → List all published Events (semantic list)

OpenAPI / Auto‑generated docs (drf-spectacular)
- Schema: GET `/api/schema/` (JSON or YAML via content negotiation)
- Swagger UI: GET `/api/schema/swagger-ui/`
- Redoc UI: GET `/api/schema/redoc/`
- Scope: schema generation is limited to `/api/v2/...` endpoints via `SPECTACULAR_SETTINGS['SCHEMA_PATH_PREFIX'] = r'/api/v2'`.

Export the schema file (with Poetry)
- `poetry run python manage.py spectacular --color --file api_v2/openapi-schema.yaml`
- Add `--validate` to also validate against the OpenAPI spec

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
- Optional header `Idempotency-Key: <string>` — a repeat with the same key (same tenant) returns the stored transaction (200) instead of crediting again (best-effort cache, ~48h TTL).
- Constraints: the asset must be in a refillable category AND must match the key's `gift_asset`; `amount` is a positive integer capped at `10000` (raw unit).
- Response 201 (or 200 on idempotent replay): schema.org/MoneyTransfer
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
- Errors: 403 (key not allowed / asset not authorized for this key), 422 (asset not TNF, or amount above cap), 503 (Fedow unavailable).
- This is distinct from the v1 route `POST /api/wallet/get_stripe_checkout_with_email/`, which creates a **paid** Stripe top-up link.
