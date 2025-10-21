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
  - Unit/integration tests run with plain pytest (not Django `manage.py test`).
  - Prefer black-box HTTP calls against a dev hostname like `lespass.tibillet.localhost`.
  - Keep tests in standalone Python scripts under `tests/` or project-level `tests/` executed by `pytest`.
- Documentation
  - Keep Markdown documentation in this `api_v2` folder close to the code (this file plus additional docs as needed).
- Semantic output
  - Represent data using schema.org types/terms whenever possible (JSON-LD or schema.org-like JSON fields).
  - For `Event` use https://schema.org/Event (e.g., `@context`, `@type`, `name`, `description`, `startDate`, `endDate`, `location`, `offers`).
