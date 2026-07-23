"""
tests/pytest/test_timezone_middleware.py — Fuseau horaire du lieu par requete.
tests/pytest/test_timezone_middleware.py — Venue timezone, per request.

LOCALISATION : tests/pytest/test_timezone_middleware.py

`Customers.views.TimezoneMiddleware` pose le fuseau du lieu (Configuration.
fuseau_horaire) pendant la requete, puis le relache. Les deux moities comptent :

- PENDANT : les dates s'affichent et se LISENT a l'heure du lieu. Un concert
  a 20h a La Reunion doit s'afficher 20h, y compris sur un ticket imprime ou
  dans un export comptable — des sorties qui n'ont aucun navigateur.
- APRES : le fuseau courant est un etat THREAD-LOCAL et les threads sont
  reutilises. S'il n'est pas relache, il deborde sur ce qui suit dans le meme
  thread. Bug reel constate : `_generer_cloture_agregee` calculait ses bornes
  de dates dans le fuseau de la derniere requete servie au lieu du fuseau
  attendu, et une cloture creee en fin de soiree sortait de la fenetre.

/ The middleware sets the venue timezone during the request, then releases it.
Both halves matter: dates are rendered AND parsed in venue time; and the
current timezone is THREAD-LOCAL state on reused threads, so leaving it set
contaminates whatever runs next in that thread.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_timezone_middleware.py -v
"""

import pytest
from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration
from Customers.models import Client as TenantClient
from Customers.views import TimezoneMiddleware


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


@pytest.fixture(autouse=True)
def fuseau_propre_avant_et_apres():
    """Garantit un fuseau neutre autour de chaque test.

    Sans ca, un test qui echoue en laissant un fuseau actif ferait echouer les
    suivants pour une raison sans rapport — exactement le defaut que ce fichier
    verifie.
    / Guarantees a neutral timezone around each test: a leaked timezone would
    otherwise break the following tests, which is the very defect tested here.
    """
    timezone.deactivate()
    yield
    timezone.deactivate()


def _middleware_qui_observe_le_fuseau():
    """Construit le middleware autour d'une vue qui note le fuseau actif.

    Renvoie (middleware, releve) ou `releve` est un dict rempli au moment ou la
    vue s'execute — c'est-a-dire A L'INTERIEUR de la requete.
    / Builds the middleware around a view that records the active timezone.
    """
    releve = {}

    def vue_qui_note_le_fuseau(request):
        releve["nom_du_fuseau"] = timezone.get_current_timezone_name()
        return HttpResponse("ok")

    return TimezoneMiddleware(vue_qui_note_le_fuseau), releve


@pytest.mark.django_db
def test_le_fuseau_du_lieu_est_actif_pendant_la_requete(tenant):
    """Pendant la requete, le fuseau courant est celui configure sur le tenant.
    / During the request, the current timezone is the tenant's configured one."""
    middleware, releve = _middleware_qui_observe_le_fuseau()

    with tenant_context(tenant):
        fuseau_attendu = Configuration.get_solo().fuseau_horaire
        middleware(RequestFactory().get("/"))

    # Garde : si le lieu etait configure sur le fuseau serveur, ce test passerait
    # meme avec un middleware qui ne fait rien. On refuse ce faux vert.
    # / Guard: if the venue used the server timezone, this test would pass even
    # with a middleware doing nothing. We refuse that false green.
    assert fuseau_attendu != settings.TIME_ZONE, (
        "Le tenant de test doit avoir un fuseau different de settings.TIME_ZONE "
        "pour que ce test prouve quelque chose."
    )
    assert releve["nom_du_fuseau"] == fuseau_attendu


@pytest.mark.django_db
def test_le_fuseau_est_relache_apres_la_requete(tenant):
    """Une fois la reponse rendue, le thread repart sur le fuseau par defaut.

    C'est ce relachement qui empeche une tache lancee ensuite (ou la requete
    suivante servie par ce thread) d'heriter du fuseau du dernier tenant vu.
    / This release prevents a task run afterwards, or the next request on this
    thread, from inheriting the last tenant's timezone.
    """
    middleware, _ = _middleware_qui_observe_le_fuseau()

    with tenant_context(tenant):
        middleware(RequestFactory().get("/"))

    assert timezone.get_current_timezone_name() == settings.TIME_ZONE


@pytest.mark.django_db
def test_le_fuseau_est_relache_meme_si_la_vue_leve(tenant):
    """Une vue qui plante ne doit pas laisser le fuseau derriere elle.

    Sans relachement sur le chemin d'erreur, une seule 500 suffirait a polluer
    le thread pour toutes les requetes suivantes.
    / A crashing view must not leave the timezone behind: without release on the
    error path, a single 500 would pollute the thread for every later request.
    """

    def vue_qui_plante(request):
        raise ValueError("panne simulee dans la vue")

    middleware = TimezoneMiddleware(vue_qui_plante)

    with tenant_context(tenant):
        with pytest.raises(ValueError):
            middleware(RequestFactory().get("/"))

    assert timezone.get_current_timezone_name() == settings.TIME_ZONE


@pytest.mark.django_db
def test_aucun_fuseau_de_lieu_sur_le_schema_public():
    """Sur le schema public, il n'y a pas de lieu : on reste au fuseau par defaut.

    Le schema public n'a pas de table Configuration — le middleware ne doit ni
    activer un fuseau, ni laisser l'erreur remonter.
    / The public schema has no venue and no Configuration table: the middleware
    must neither activate a timezone nor let the error bubble up.
    """
    middleware, releve = _middleware_qui_observe_le_fuseau()

    connection.set_schema_to_public()
    reponse = middleware(RequestFactory().get("/"))

    assert reponse.status_code == 200
    assert releve["nom_du_fuseau"] == settings.TIME_ZONE
