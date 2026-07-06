"""
Tests du resolver unifié de gabarits de skin (migration skins, CHANTIER-01).
/ Tests of the unified skin template resolver (skins migration, CHANTIER-01).

LOCALISATION : tests/pytest/test_gabarit_skin.py

gabarit_skin(nom) retourne le chemin du gabarit du skin courant, avec fallback
automatique sur le socle pages/classic/. Le skin est lu sur le singleton
pages.ConfigurationSite du tenant courant.
/ gabarit_skin(nom) returns the current skin's template path, with automatic
fallback to the pages/classic/ base. The skin is read from the tenant's
pages.ConfigurationSite singleton.
"""
import pytest
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def restaurer_skin(tenant):
    """
    Sauvegarde le skin du tenant avant le test et le restaure apres.
    / Saves the tenant's skin before the test and restores it after.
    """
    from pages.models import ConfigurationSite

    with tenant_context(tenant):
        skin_avant = ConfigurationSite.get_solo().skin

    yield

    with tenant_context(tenant):
        config_site = ConfigurationSite.get_solo()
        config_site.skin = skin_avant
        config_site.save()


def _changer_skin(tenant, nouveau_skin):
    """
    Change le skin du tenant (utilitaire de test).
    / Changes the tenant's skin (test helper).
    """
    from pages.models import ConfigurationSite

    config_site = ConfigurationSite.get_solo()
    config_site.skin = nouveau_skin
    config_site.save()


def test_gabarit_skin_reunion_retombe_sur_classic(tenant, restaurer_skin):
    """
    Skin "reunion" (le defaut) : pages/reunion/ n'existe pas, donc gabarit_skin
    retombe toujours sur le socle pages/classic/ (decision 1 du plan).
    / Default skin "reunion": no pages/reunion/ folder, so gabarit_skin always
    falls back to the pages/classic/ base (plan decision 1).
    """
    from pages.services import gabarit_skin

    with tenant_context(tenant):
        _changer_skin(tenant, "reunion")
        assert gabarit_skin("shell.html") == "pages/classic/shell.html"
        assert gabarit_skin("headless.html") == "pages/classic/headless.html"


def test_gabarit_skin_utilise_le_gabarit_du_skin_si_present(tenant, restaurer_skin):
    """
    Skin "faire_festival" : le gabarit existe dans pages/faire_festival/,
    c'est lui qui est retourne (pas le fallback).
    / Skin "faire_festival": the template exists in pages/faire_festival/,
    so it is returned (not the fallback).
    """
    from pages.services import gabarit_skin

    with tenant_context(tenant):
        _changer_skin(tenant, "faire_festival")
        assert gabarit_skin("shell.html") == "pages/faire_festival/shell.html"
        assert gabarit_skin("headless.html") == "pages/faire_festival/headless.html"


def test_gabarit_skin_gabarit_manquant_retombe_sur_classic(tenant, restaurer_skin):
    """
    Skin "faire_festival" mais gabarit absent du skin : fallback sur classic.
    C'est le filet de securite permanent du systeme de skin.
    / Skin "faire_festival" but template missing from the skin: falls back to
    classic. This is the skin system's permanent safety net.
    """
    from pages.services import gabarit_skin

    with tenant_context(tenant):
        _changer_skin(tenant, "faire_festival")
        resultat = gabarit_skin("gabarit-qui-nexiste-pas.html")
        assert resultat == "pages/classic/gabarit-qui-nexiste-pas.html"


def test_les_anciens_squelettes_ont_disparu():
    """
    CHANTIER-08 : les arborescences BaseBillet/templates/{reunion,faire_festival}
    ont ete supprimees. Charger un ancien chemin doit lever TemplateDoesNotExist,
    et les nouveaux squelettes doivent exister avec les blocs du contrat.
    / The legacy skin trees are gone: old paths must raise TemplateDoesNotExist,
    and the new skeletons must exist with the contract blocks.
    """
    from django.template import TemplateDoesNotExist
    from django.template.loader import get_template

    for ancien_chemin in ("reunion/base.html", "faire_festival/base.html"):
        with pytest.raises(TemplateDoesNotExist):
            get_template(ancien_chemin)

    for squelette in ("pages/classic/shell.html", "pages/classic/headless.html",
                      "pages/faire_festival/shell.html",
                      "pages/faire_festival/headless.html"):
        source = get_template(squelette).template.source
        # Les blocs du contrat sont presents (noms FIGES, cf. CONTRAT-DE-SKIN.md).
        # / Contract blocks are present (FROZEN names).
        assert "offcanvas_globaux" in source or "block offcanvas" in source, (
            f"{squelette} doit exposer les blocs offcanvas du contrat"
        )
