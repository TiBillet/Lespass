"""
Test DB-only — API v2 : resolution d'un evenement par uuid OU slug front.
/ DB-only test — API v2: resolve an event by uuid OR front slug.

L'endpoint detail `GET /api/v2/events/{id}/` accepte deux formes d'identifiant :
- un uuid (ex: 7d51dee7-....) ;
- le slug utilise par le controleur front (ex: mon-evenement-260620-0900-7d51dee7),
  dont les 8 derniers caracteres hex sont le debut de l'uuid.
/ The detail endpoint accepts a uuid or the front slug (last 8 hex = uuid start).

Cas d'erreur (issue Sentry 7504311969) : un identifiant qui ne correspond a rien
(slug inconnu, ou chaine arbitraire) doit renvoyer 404, jamais 500.
/ A non-matching identifier must return 404, never 500.

Voir piege 9.76 (tests/PIEGES.md) et EventMVT.retrieve (BaseBillet/views.py).

Run: docker exec -e API_KEY=dummy lespass_django poetry run pytest \
        tests/pytest/test_event_retrieve_invalid_uuid.py -q
"""
import uuid

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

HOST = "lespass.tibillet.localhost"


# Reutiliser la DB dev (pattern V2 onboard). / Reuse the dev DB (V2 onboard pattern).
@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


@pytest.fixture
def event_setup():
    """
    Cree un evenement publie + une cle API (droit `event`), dans une transaction
    annulee a la fin : rien ne reste dans la base dev.
    / Create a published event + an API key (`event` right), in a rolled-back
    transaction: nothing stays in the dev DB.
    """
    from django.db import transaction
    from Customers.models import Client
    from BaseBillet.models import Event, ExternalApiKey
    from rest_framework_api_key.models import APIKey

    tenant = Client.objects.get(schema_name="lespass")
    suffix = uuid.uuid4().hex[:6]

    with tenant_context(tenant):
        with transaction.atomic():
            event = Event.objects.create(
                name=f"Test retrieve slug {suffix}",
                datetime=timezone.now() + timezone.timedelta(days=2),
                published=True,
            )
            api_obj, key_str = APIKey.objects.create_key(name=f"event-{suffix}")
            ExternalApiKey.objects.create(
                name=f"event-{suffix}",
                key=api_obj,
                event=True,
            )
            try:
                yield {"key": key_str, "event": event}
            finally:
                # Annule tout ce qui a ete cree par ce fixture.
                # / Roll back everything created by this fixture.
                transaction.set_rollback(True)


def _get(identifier, key):
    """
    Appelle l'endpoint detail d'un evenement avec une cle API valide.
    / Call the event detail endpoint with a valid API key.

    raise_request_exception = False : on observe le code HTTP renvoye
    (ex. 500 si bug) plutot que de voir l'exception remonter dans le test.
    / Observe the returned HTTP status rather than letting the exception bubble up.
    """
    client = APIClient()
    client.raise_request_exception = False
    return client.get(
        f"/api/v2/events/{identifier}/",
        SERVER_NAME=HOST,
        HTTP_AUTHORIZATION=f"Api-Key {key}",
    )


def test_event_retrieve_par_uuid(event_setup):
    # Acces par uuid : comportement existant. / Lookup by uuid: existing behavior.
    event = event_setup["event"]
    resp = _get(event.uuid, key=event_setup["key"])
    assert resp.status_code == 200
    assert resp.json()["identifier"] == str(event.uuid)


def test_event_retrieve_par_slug_front(event_setup):
    # Acces par le slug du front : les 8 derniers hex = debut de l'uuid.
    # / Lookup by the front slug: last 8 hex = start of the uuid.
    event = event_setup["event"]
    resp = _get(event.slug, key=event_setup["key"])
    assert resp.status_code == 200
    assert resp.json()["identifier"] == str(event.uuid)


def test_event_retrieve_slug_inconnu_renvoie_404(event_setup):
    # Un slug qui ne correspond a aucun evenement -> 404 (jamais 500).
    # / A slug matching no event -> 404 (never 500).
    slug_inexistant = f"evenement-inexistant-{uuid.uuid4().hex[:8]}"
    resp = _get(slug_inexistant, key=event_setup["key"])
    assert resp.status_code == 404


def test_event_retrieve_uuid_inconnu_renvoie_404(event_setup):
    # Un uuid bien forme mais inconnu -> 404 (non-regression).
    # / A well-formed but unknown uuid -> 404 (regression guard).
    resp = _get(uuid.uuid4(), key=event_setup["key"])
    assert resp.status_code == 404
