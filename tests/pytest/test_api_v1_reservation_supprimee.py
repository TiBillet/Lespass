"""
Test DB-only : l'API v1 de reservation n'existe plus.
/ DB-only test: the v1 reservation API no longer exists.

LOCALISATION : tests/pytest/test_api_v1_reservation_supprimee.py

La route `/api/reservations/` (API v1) a ete supprimee. L'API v2
(`/api/v2/reservations/`) la remplace. Un appel doit donc repondre 404.
/ The v1 route was removed; the v2 API replaces it. A call must answer 404.

Run: docker exec lespass_django poetry run pytest \
        tests/pytest/test_api_v1_reservation_supprimee.py -q
"""
import pytest
from rest_framework.test import APIClient

HOST = "lespass.tibillet.localhost"


# Reutiliser la DB dev. / Reuse the dev DB.
@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


def test_post_api_v1_reservations_repond_404():
    # Un POST sur l'ancienne route v1 ne trouve plus aucune vue.
    # / A POST on the old v1 route finds no view anymore.
    client = APIClient()
    reponse = client.post(
        "/api/reservations/",
        data={"email": "test@example.org"},
        format="json",
        HTTP_HOST=HOST,
    )
    assert reponse.status_code == 404


def test_get_api_v1_reservations_repond_404():
    # Un GET sur la liste v1 ne trouve plus aucune vue.
    # / A GET on the v1 list finds no view anymore.
    client = APIClient()
    reponse = client.get("/api/reservations/", HTTP_HOST=HOST)
    assert reponse.status_code == 404
