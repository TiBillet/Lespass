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
  - Auto-generated API docs use drf-spectacular (OpenAPI 3):
    - Endpoints (tenant scope):
      - Schema JSON/YAML: `/api/schema/` (content-negotiates application/vnd.oai.openapi;format=json|yaml)
      - Swagger UI: `/api/schema/swagger-ui/`
      - Redoc: `/api/schema/redoc/`
    - Scope: the schema generation is restricted to API v2 paths (`/api/v2/...`) via
      `SPECTACULAR_SETTINGS['SCHEMA_PATH_PREFIX'] = r'/api/v2'` to keep docs focused and avoid
      legacy endpoints that are not DRF-generic views.
    - Generate/export the schema file locally with Poetry:
      - `poetry run python manage.py spectacular --color --file api_v2/openapi-schema.yaml`
      - Optionally validate: add `--validate`
    - Offline/static UI (optional): install sidecar
      - `poetry add drf-spectacular[sidecar]`
      - In settings, set `SWAGGER_UI_DIST/REDOC_DIST` to `SIDECAR` (already supported by drf-spectacular)
- Semantic output
  - Represent data using schema.org types/terms whenever possible (JSON-LD or schema.org-like JSON fields).
  - For `Event` use https://schema.org/Event (e.g., `@context`, `@type`, `name`, `description`, `startDate`, `endDate`, `location`, `offers`).
