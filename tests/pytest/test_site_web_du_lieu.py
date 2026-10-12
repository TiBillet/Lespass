"""
Le site web d'un lieu n'est jamais le site du projet TiBillet.
/ A venue's website is never TiBillet's own site.

LOCALISATION : tests/pytest/test_site_web_du_lieu.py

Beaucoup de lieux ont tibillet.org comme site web : saisi dans le formulaire
Stripe, puis recopie a la creation du lieu. On ne l'affiche pas en public.

Les tests tournent sur la base dev : la Configuration est modifiee par update()
et remise en etat a la fin.
/ Dev database: Configuration changed with update() and restored.
"""

import json
import re
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db

SITE_DU_PROJET = "https://tibillet.org/"
SITE_DU_LIEU = "https://site-du-lieu.example/"


@pytest.mark.parametrize(
    "adresse, attendu",
    [
        ("https://tibillet.org/", True),
        ("http://www.tibillet.org", True),
        ("tibillet.org", True),
        ("https://TIBILLET.COOP/a-propos", True),
        ("https://tibillet.re", True),
        ("https://la-filature.tibillet.coop/", False),
        ("https://tibillet.org.exemple.fr/", False),
        ("https://site-du-lieu.example/", False),
        (None, False),
        ("", False),
    ],
)
def test_reconnaitre_le_site_du_projet_tibillet(adresse, attendu):
    from BaseBillet.models import est_un_site_du_projet_tibillet

    assert est_un_site_du_projet_tibillet(adresse) is attendu


@pytest.fixture
def site_web_du_lieu(tenant):
    """
    Rend une fonction qui change le site web du lieu, puis le restaure.
    / Returns a function that changes the venue website, then restores it.
    """
    from BaseBillet.models import Configuration

    with tenant_context(tenant):
        site_d_origine = Configuration.get_solo().site_web

    def changer(adresse):
        with tenant_context(tenant):
            Configuration.objects.update(site_web=adresse)
            Configuration.clear_cache()

    yield changer

    with tenant_context(tenant):
        Configuration.objects.update(site_web=site_d_origine)
        Configuration.clear_cache()


def _accueil_v2(api_client):
    with patch("BaseBillet.views.get_skin_courant", return_value="V2"):
        return api_client.get("/").content.decode()


def _liens_same_as(html):
    liens = []
    for bloc in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    ):
        donnees = json.loads(bloc)
        for noeud in donnees.get("@graph", [donnees]):
            if noeud.get("@type") == "Organization":
                liens.extend(noeud.get("sameAs", []))
    return liens


def test_le_site_du_projet_n_est_pas_affiche_dans_l_en_tete(
    api_client, site_web_du_lieu
):
    site_web_du_lieu(SITE_DU_PROJET)
    html = _accueil_v2(api_client)

    assert 'data-testid="tenant-header-site-web"' not in html
    assert SITE_DU_PROJET not in _liens_same_as(html)


def test_le_vrai_site_du_lieu_reste_affiche(api_client, site_web_du_lieu):
    site_web_du_lieu(SITE_DU_LIEU)
    html = _accueil_v2(api_client)

    lien = re.search(r'<a class="place-id__site" href="([^"]*)"', html)
    assert lien is not None and lien.group(1) == SITE_DU_LIEU
    assert SITE_DU_LIEU in _liens_same_as(html)


@pytest.mark.parametrize(
    "adresse, url_attendue",
    [(SITE_DU_PROJET, None), (SITE_DU_LIEU, SITE_DU_LIEU)],
    ids=["site-du-projet", "site-du-lieu"],
)
def test_l_organisateur_des_evenements_de_l_api(
    tenant, site_web_du_lieu, adresse, url_attendue
):
    from ApiBillet.serializers import EventSerializer

    site_web_du_lieu(adresse)
    with tenant_context(tenant):
        organisateur = EventSerializer().get_organizer(None)

    assert organisateur.get("url") == url_attendue
