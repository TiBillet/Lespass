# Technical

## Scope

- The specified software is the `booking` Django app: the reservation
  of shared resources, and the volunteer planning (`benevolat`).
- It runs inside Lespass, a multi-tenant Django project
  (`django-tenants`): each place is a tenant, and `booking` data lives
  in the tenant's schema.
- The rest of Lespass is the environment of `booking`. The
  specification states only what `booking` uses of it, e.g. products,
  prices and payment (`BaseBillet`, `PaiementStripe`), users
  (`AuthBillet`).
- Shared files that an increment may change:
  - the admin of `booking`, in `Administration/` (e.g.
    `Administration/admin/resources.py`,
    `Administration/admin/benevolat.py`);
  - the URL mount point, `TiBillet/urls_tenants.py`;
  - the code of other apps that calls `booking`, e.g. the cart and
    orders in `BaseBillet/`.

## Stack and conventions

- The stack and conventions are those of Lespass, in `GUIDELINES.md`
  at the repository root: Django, DRF `ViewSet` controllers,
  `Serializer` validation, HTMX and Bootstrap, French source text for
  translations.

## Test and quality policy

- Tests of `booking` behavior go in `booking/tests/`, with its own
  fixtures in `booking/tests/conftest.py`.
- Behavior that only a browser can observe goes in `tests/e2e/`, under
  an existing family marker of `pytest.ini` (e.g. `benevolat`,
  `billetterie`).
- Tests run in the Docker container:
  - the check of a phase:
    `docker exec lespass_django poetry run pytest booking/tests/`, and
    the files of `tests/pytest/` and `tests/e2e/` that test the area
    the increment changes (`make test` would need the live server);
  - the full suite, `make test`, is run by the human, not by the agent.

## Documents

- `booking/spec/` is the specification.
- `booking/doc/` holds earlier notes, read as input when specifying an
  area. It is deleted once its content is specified or dropped.
