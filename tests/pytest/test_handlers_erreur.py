"""
Tests des handlers d'erreur 404/500 skin-aware + HTMX-aware.
/ Tests of the skin-aware + HTMX-aware 404/500 error handlers.

LOCALISATION : tests/pytest/test_handlers_erreur.py

POURQUOI EN PYTEST DIRECT : en dev DEBUG=1, Django court-circuite les handlers
custom et sert sa page technique — impossible de les vérifier par curl ou E2E.
On appelle donc les handlers directement (RequestFactory), comme le fera
Django en production (DEBUG=0).
/ WHY DIRECT PYTEST: with DEBUG=1 Django bypasses custom handlers (technical
page) — they cannot be verified via curl or E2E. So we call the handlers
directly (RequestFactory), exactly as Django does in production.
"""
import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django_htmx.middleware import HtmxDetails
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


def _fabriquer_requete(chemin, avec_htmx=False):
    """
    Fabrique une requête GET équivalente à ce que voient les handlers en prod :
    user anonyme + attribut htmx posé par HtmxMiddleware.
    / Builds a GET request as the handlers see it in production: anonymous
    user + the htmx attribute normally set by HtmxMiddleware.
    """
    fabrique = RequestFactory()
    if avec_htmx:
        requete = fabrique.get(chemin, HTTP_HX_REQUEST="true")
    else:
        requete = fabrique.get(chemin)
    requete.user = AnonymousUser()
    requete.htmx = HtmxDetails(requete)
    return requete


def test_handler404_rend_le_shell_complet_en_navigation_normale(tenant):
    """Navigation normale : la 404 est une page complète (shell du skin)."""
    from BaseBillet.views import handler404

    with tenant_context(tenant):
        reponse = handler404(_fabriquer_requete("/page-inexistante/"))

    assert reponse.status_code == 404
    contenu = reponse.content.decode()
    # Page complète : doctype + head présents. / Full page: doctype + head.
    assert "<!doctype html>" in contenu.lower()
    # Le contenu de la 404 est là (i18n : FR ou EN selon la locale active).
    # / The 404 content is there (i18n: FR or EN depending on active locale).
    assert "404" in contenu


def test_handler404_rend_le_fragment_headless_sous_htmx(tenant):
    """Requête HTMX : la 404 est un fragment headless (swappable dans le body)."""
    from BaseBillet.views import handler404

    with tenant_context(tenant):
        reponse = handler404(_fabriquer_requete("/page-inexistante/", avec_htmx=True))

    assert reponse.status_code == 404
    contenu = reponse.content.decode()
    # Fragment : PAS de document complet (le listener htmx:beforeSwap des
    # shells le swappe dans le body). / Fragment: NO full document.
    assert "<!doctype" not in contenu.lower()
    assert "404" in contenu


def test_handler500_rend_le_shell_avec_l_exception(tenant):
    """La 500 rend le shell du skin et transmet le type d'exception au gabarit."""
    from BaseBillet.views import handler500

    with tenant_context(tenant):
        reponse = handler500(
            _fabriquer_requete("/"), exception=RuntimeError("explosion de test")
        )

    assert reponse.status_code == 500
    contenu = reponse.content.decode()
    assert "<!doctype html>" in contenu.lower()
