"""
SEO de l'accueil par defaut : titre, description, accueil vide, sitemap, JSON-LD.
/ Default home SEO: title, description, empty home, sitemap, JSON-LD.

LOCALISATION : tests/pytest/test_seo_accueil.py

Spec : TECH_DOC/SESSIONS/SEO/AUDIT-ACCUEIL-V2/RECAP.md (chantier 10).

Les tests tournent sur la base dev : ceux qui modifient la Configuration du lieu
passent par update() (aucun signal) et la remettent en etat dans un finally.
/ Tests run on the dev database: config changes use update() and are restored.
"""

import json
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db

SKINS_AVEC_ACCUEIL_PAR_DEFAUT = ["V2", "reunion"]


# ---------------------------------------------------------------------------
# Regle « accueil vide » / "Empty home" rule
# ---------------------------------------------------------------------------
def _config(img=None, long_description=None):
    return SimpleNamespace(img=img, long_description=long_description)


def test_un_accueil_sans_evenement_ni_image_ni_description_est_vide():
    from TiBillet.seo_indexing import accueil_par_defaut_est_vide

    assert accueil_par_defaut_est_vide(_config(), il_y_a_des_evenements=False)


def test_le_texte_de_bienvenue_ne_compte_pas_comme_une_description():
    from TiBillet.seo_indexing import accueil_par_defaut_est_vide

    texte_de_creation = (
        "<div><strong>Bienvenue dans votre nouvel espace !</strong></div>"
    )
    assert accueil_par_defaut_est_vide(
        _config(long_description=texte_de_creation), il_y_a_des_evenements=False
    )


@pytest.mark.parametrize(
    "config, il_y_a_des_evenements",
    [
        (_config(), True),
        (_config(img="images/lieu.jpg"), False),
        (_config(long_description="<p>Tiers-lieu associatif.</p>"), False),
    ],
    ids=["un-evenement", "une-image", "une-description"],
)
def test_un_seul_contenu_suffit_pour_que_l_accueil_ne_soit_pas_vide(
    config, il_y_a_des_evenements
):
    from TiBillet.seo_indexing import accueil_par_defaut_est_vide

    assert not accueil_par_defaut_est_vide(config, il_y_a_des_evenements)


# ---------------------------------------------------------------------------
# Rendu de l'accueil / Home rendering
# ---------------------------------------------------------------------------
@pytest.fixture
def configuration_du_lieu(tenant):
    """
    Rend une fonction qui modifie la Configuration du lieu, puis la restaure.
    / Returns a function that changes the venue Configuration, then restores it.
    """
    from BaseBillet.models import Configuration

    valeurs_d_origine = {}

    def modifier(**champs):
        with tenant_context(tenant):
            configuration = Configuration.get_solo()
            for nom in champs:
                valeurs_d_origine.setdefault(nom, getattr(configuration, nom))
            Configuration.objects.filter(pk=configuration.pk).update(**champs)
            Configuration.clear_cache()

    yield modifier

    if valeurs_d_origine:
        with tenant_context(tenant):
            configuration = Configuration.get_solo()
            Configuration.objects.filter(pk=configuration.pk).update(
                **valeurs_d_origine
            )
            Configuration.clear_cache()


def _accueil(api_client, skin):
    with patch("BaseBillet.views.get_skin_courant", return_value=skin):
        return api_client.get("/").content.decode()


@pytest.mark.parametrize("skin", SKINS_AVEC_ACCUEIL_PAR_DEFAUT)
def test_le_titre_de_l_accueil_est_le_nom_du_lieu_et_sa_ville(tenant, api_client, skin):
    """
    <title> = « nom — ville », sans « Accueil » et sans le nom repete en suffixe.
    / <title> = "name — city", no "Home", no repeated name suffix.
    """
    from BaseBillet.models import Configuration

    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        nom = configuration.organisation
        ville = configuration.postal_address.address_locality

    titre = re.search(r"<title>([^<]*)</title>", _accueil(api_client, skin)).group(1)
    assert titre == f"{nom} — {ville}"


@pytest.mark.parametrize("skin", SKINS_AVEC_ACCUEIL_PAR_DEFAUT)
def test_sans_description_courte_la_meta_description_vaut_le_nom_et_pas_none(
    tenant, api_client, configuration_du_lieu, skin
):
    from BaseBillet.models import Configuration

    configuration_du_lieu(short_description=None)
    with tenant_context(tenant):
        nom = Configuration.get_solo().organisation

    html = _accueil(api_client, skin)
    description = re.search(r'<meta name="description" content="([^"]*)"', html).group(
        1
    )
    assert description == nom
    assert 'content="None"' not in html


def test_un_accueil_vide_est_en_noindex_follow(api_client):
    with patch("TiBillet.seo_indexing.should_noindex", return_value=False):
        with patch(
            "TiBillet.seo_indexing.accueil_par_defaut_est_vide", return_value=True
        ):
            html_vide = _accueil(api_client, "V2")
        with patch(
            "TiBillet.seo_indexing.accueil_par_defaut_est_vide", return_value=False
        ):
            html_rempli = _accueil(api_client, "V2")

    robots = r'<meta name="robots" content="([^"]*)"'
    assert re.search(robots, html_vide).group(1) == "noindex, follow"
    assert re.search(robots, html_rempli).group(1) == "index, follow"


def test_le_json_ld_du_lieu_est_valide_avec_apostrophe_et_saut_de_ligne(
    api_client, configuration_du_lieu
):
    """
    Une description avec apostrophe et saut de ligne donne un JSON valide, sans
    entite HTML ; le site web du lieu est dans sameAs.
    / Apostrophe and newline give valid JSON, no HTML entity; website in sameAs.
    """
    configuration_du_lieu(
        short_description="L'atelier du lieu\nouvert à tous",
        site_web="https://site-du-lieu.example/",
    )
    html = _accueil(api_client, "V2")

    blocs_json_ld = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    organisations = []
    for bloc in blocs_json_ld:
        donnees = json.loads(bloc)
        for noeud in donnees.get("@graph", [donnees]):
            if noeud.get("@type") == "Organization":
                organisations.append(noeud)

    assert len(organisations) == 1
    organisation = organisations[0]
    assert organisation["description"] == "L'atelier du lieu\nouvert à tous"
    assert "https://site-du-lieu.example/" in organisation["sameAs"]
    # Dans un <script>, une entite HTML n'est jamais decodee : elle serait lue
    # telle quelle. (Dans un attribut, comme la meta description, c'est normal.)
    # / Inside a <script>, HTML entities are never decoded.
    for bloc in blocs_json_ld:
        assert "&#x27;" not in bloc


# ---------------------------------------------------------------------------
# Sitemap / Sitemap
# ---------------------------------------------------------------------------
def test_un_accueil_vide_sort_du_sitemap(tenant):
    from BaseBillet.sitemap import StaticViewSitemap
    from pages.models import Page

    with tenant_context(tenant):
        # Precondition : pas de page d'accueil CMS publiee (elle remplirait "/").
        # / Precondition: no published CMS home page.
        assert not Page.objects.filter(est_accueil=True, publie=True).exists()

        with patch(
            "TiBillet.seo_indexing.accueil_par_defaut_est_vide", return_value=True
        ):
            pages_si_vide = StaticViewSitemap().items()
        with patch(
            "TiBillet.seo_indexing.accueil_par_defaut_est_vide", return_value=False
        ):
            pages_si_rempli = StaticViewSitemap().items()

    assert "index" not in pages_si_vide
    assert "index" in pages_si_rempli
