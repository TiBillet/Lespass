"""
Test DB-only — redirection des anciens liens de la doc Docusaurus v2 → doc v3.
/ DB-only test — redirect old Docusaurus v2 docs links to the v3 docs.

L'ancienne doc (Docusaurus) etait servie sur tibillet.org avec des chemins
/docs/..., /fr/..., /en/..., /roadmap/, /search/, /cgucgv/. Ces chemins n'existent
plus dans Lespass. La fonction `url_doc_v3_pour_chemin_herite` (utilisee par
CanonicalDomainRedirectMiddleware sur le tenant ROOT) calcule vers quelle page de
la doc v3 rediriger, ou None si ce n'est pas un ancien lien de doc.
/ The old Docusaurus docs lived on tibillet.org. This pure function maps a legacy
path to its v3 docs URL, or None when the path is a normal Lespass route.

On teste la fonction PURE directement : pas de DB, pas de navigateur, deterministe.
/ We test the PURE function directly: no DB, no browser, deterministic.

Run: docker exec lespass_django poetry run pytest \
        tests/pytest/test_middleware_doc_redirect.py -q
"""
import pytest

from Customers.middleware import (
    URL_DOC_V3,
    URL_DOC_V3_CGU,
    URL_DOC_V3_DEMO,
    url_doc_v3_pour_chemin_herite,
)


# Cas de correspondance PRECISE : page de demonstration (EN et FR).
# / PRECISE match: demonstration page (EN and FR).
@pytest.mark.parametrize(
    "chemin",
    [
        "/docs/presentation/demonstration/",
        "/docs/presentation/demonstration",  # sans slash final / no trailing slash
        "/fr/docs/presentation/demonstration/",
        "/FR/Docs/Presentation/Demonstration/",  # casse melangee / mixed case
    ],
)
def test_page_demonstration_redirige_vers_demo_v3(chemin):
    # La page de demonstration v2 doit pointer sur la demo v3 precise.
    # / The v2 demonstration page must point to the precise v3 demo page.
    assert url_doc_v3_pour_chemin_herite(chemin) == URL_DOC_V3_DEMO


# Cas de correspondance PRECISE : CGU / CGV (EN et FR).
# / PRECISE match: terms and conditions (EN and FR).
@pytest.mark.parametrize(
    "chemin",
    [
        "/cgucgv/",
        "/cgucgv",
        "/fr/cgucgv/",
    ],
)
def test_cgucgv_redirige_vers_cgu_v3(chemin):
    # L'ancienne page CGU/CGV doit pointer sur la page CGU/CGV de la doc v3.
    # / The old CGU/CGV page must point to the v3 CGU/CGV page.
    assert url_doc_v3_pour_chemin_herite(chemin) == URL_DOC_V3_CGU


# Cas de PREFIXE herite sans equivalent precis : retombe sur la racine v3.
# / Legacy PREFIX without precise mapping: falls back to the v3 homepage.
@pytest.mark.parametrize(
    "chemin",
    [
        "/docs/",
        "/docs/category/api/",
        "/fr/",
        "/fr/docs/install/docker_install/",
        "/en/",
        "/en/docs/presentation/introduction/",
        "/roadmap/",
        "/search/",
        # request.path ne contient JAMAIS la query string (c'est get_full_path()
        # qui l'inclut), donc on teste bien un chemin nu comme en production.
        # / request.path NEVER holds the query string, so we test a bare path
        # exactly like in production.
        "/docs",  # sans slash final / no trailing slash
        "/fr",  # home FR de l'ancienne doc / old docs FR home
        "/en",
    ],
)
def test_prefixe_herite_retombe_sur_racine_v3(chemin):
    # Tout chemin de doc sans mapping precis renvoie vers l'accueil de la doc v3.
    # / Any docs path without precise mapping points to the v3 docs homepage.
    assert url_doc_v3_pour_chemin_herite(chemin) == URL_DOC_V3


# Cas des ROUTES LESPASS NORMALES : la fonction ne doit JAMAIS rediriger.
# / NORMAL LESPASS ROUTES: the function must NEVER redirect.
@pytest.mark.parametrize(
    "chemin",
    [
        "/",  # home Lespass / Lespass home
        "/explorer/",
        "/lieux/",
        "/evenements/",
        "/recherche/",
        "/onboard/identity/",
        "/event/abc-123/",
        "/api/v2/events/",
        "/french-quarter/",  # ne doit PAS matcher le prefixe /fr / must NOT match /fr
        "/english/",  # ne doit PAS matcher le prefixe /en / must NOT match /en
    ],
)
def test_routes_lespass_normales_ne_redirigent_pas(chemin):
    # Une vraie route Lespass n'est jamais confondue avec un ancien lien de doc.
    # / A real Lespass route is never mistaken for an old docs link.
    assert url_doc_v3_pour_chemin_herite(chemin) is None
