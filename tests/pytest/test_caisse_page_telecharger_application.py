"""
Tests de la page « Téléchargez l'application » affichée quand l'accès à la caisse est refusé.
/ Tests of the "Download the app" page shown when POS access is denied.

LOCALISATION : tests/pytest/test_caisse_page_telecharger_application.py

RÈGLE TESTÉE (laboutik/views.py, CaisseViewSet.handle_exception)
Quand GET /laboutik/caisse/ est refusé (ni terminal appairé au lieu, ni admin du lieu,
ni clé API), la caisse ne renvoie pas un JSON {"detail": ...}. Elle renvoie une page HTML,
en 403, avec :
- un QR code (SVG) qui pointe vers le téléchargement de l'application Android ;
- un lien cliquable vers ce même téléchargement ;
- le lien vers la documentation.
Les autres routes de la caisse gardent la réponse DRF habituelle.
Un administrateur du lieu ouvre toujours la caisse normalement.
/ A denied GET /laboutik/caisse/ returns an HTML page (403) with a QR code, a download
link and the documentation link. Other POS routes keep the DRF response.

La caisse est activée par `configuration_modifiee()`, jamais enregistrée
(tests/PIEGES.md 13.22). Le client de chaque test est créé dans le test (13.10).

Lancer / Run : make test ARGS="tests/pytest/test_caisse_page_telecharger_application.py"
"""

from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import client_connecte, configuration_modifiee, creer_utilisateur
from laboutik.views import (
    URL_DE_TELECHARGEMENT_APPLICATION_ANDROID,
    URL_DOCUMENTATION_APPLICATION_ANDROID,
)
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

# Page d'accueil de la caisse (laboutik/views.py, CaisseViewSet.list).
# / POS home page.
URL_DE_LA_PAGE_D_ACCUEIL_DE_LA_CAISSE = "/laboutik/caisse/"

# Ouverture de la caisse par carte primaire (laboutik/views.py, CaisseViewSet.carte_primaire).
# / POS opening by primary card.
URL_D_OUVERTURE_DE_LA_CAISSE = "/laboutik/caisse/carte_primaire/"


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les vues activent une langue sans la remettre (tests/PIEGES.md, 10.5).
    / Views activate a language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, caisse activée EN MÉMOIRE uniquement.
    / The `lespass` venue, register switched on in memory only.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            yield SimpleNamespace(tenant=tenant)


def test_visiteur_anonyme_recoit_la_page_de_telechargement_en_html(lieu):
    """
    Un visiteur non connecté, sans clé API, reçoit la page HTML de téléchargement
    en 403, et non le JSON de DRF.
    / An anonymous visitor without API key gets the HTML download page (403), not JSON.
    """
    client_anonyme = client_connecte()

    reponse = client_anonyme.get(URL_DE_LA_PAGE_D_ACCUEIL_DE_LA_CAISSE)

    assert reponse.status_code == 403
    assert reponse["Content-Type"].startswith("text/html")
    contenu_de_la_page = reponse.content.decode()
    assert 'data-testid="laboutik-telecharger-application"' in contenu_de_la_page
    assert "Missing LaBoutik API key" not in contenu_de_la_page


def test_la_page_de_telechargement_contient_le_qrcode_le_lien_et_la_documentation(lieu):
    """
    La page contient le QR code en SVG, le lien cliquable vers le téléchargement,
    et le lien vers la documentation.
    / The page holds the SVG QR code, the clickable download link and the docs link.
    """
    client_anonyme = client_connecte()

    reponse = client_anonyme.get(URL_DE_LA_PAGE_D_ACCUEIL_DE_LA_CAISSE)
    contenu_de_la_page = reponse.content.decode()

    assert "<svg" in contenu_de_la_page
    assert f'href="{URL_DE_TELECHARGEMENT_APPLICATION_ANDROID}"' in contenu_de_la_page
    assert f'href="{URL_DOCUMENTATION_APPLICATION_ANDROID}"' in contenu_de_la_page


def test_utilisateur_connecte_mais_pas_admin_du_lieu_recoit_aussi_la_page(lieu):
    """
    Un utilisateur connecté qui n'est pas admin du lieu (et pas un terminal appairé)
    reçoit lui aussi la page de téléchargement.
    / A logged-in user who is not a venue admin also gets the download page.
    """
    utilisateur_sans_droit_sur_le_lieu = creer_utilisateur()
    client_de_l_utilisateur = client_connecte(utilisateur_sans_droit_sur_le_lieu)

    reponse = client_de_l_utilisateur.get(URL_DE_LA_PAGE_D_ACCUEIL_DE_LA_CAISSE)

    assert reponse.status_code == 403
    assert 'data-testid="laboutik-telecharger-application"' in reponse.content.decode()


def test_administrateur_du_lieu_ouvre_toujours_la_caisse(lieu):
    """
    Un administrateur du lieu voit l'écran d'attente de la carte primaire, pas la page
    de téléchargement.
    / A venue admin still sees the primary card screen, not the download page.
    """
    client_de_l_administrateur = creer_un_administrateur_du_lieu(lieu)

    reponse = client_de_l_administrateur.get(URL_DE_LA_PAGE_D_ACCUEIL_DE_LA_CAISSE)

    assert reponse.status_code == 200
    assert "laboutik-telecharger-application" not in reponse.content.decode()


def test_les_autres_routes_de_la_caisse_gardent_le_refus_drf(lieu):
    """
    Seule la page d'accueil est remplacée. Un POST anonyme sur l'ouverture de la caisse
    garde le refus DRF habituel (JSON avec `detail`).
    / Only the home page is replaced: other routes keep the usual DRF refusal.
    """
    client_anonyme = client_connecte()

    reponse = client_anonyme.post(
        URL_D_OUVERTURE_DE_LA_CAISSE, data={"tag_id": "ABCD1234"}
    )

    assert reponse.status_code == 403
    assert "laboutik-telecharger-application" not in reponse.content.decode()
    assert "detail" in reponse.json()
