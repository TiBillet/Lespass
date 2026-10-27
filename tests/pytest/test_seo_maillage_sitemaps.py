"""
SEO : liens entre lieux et sitemaps (chantier 11).
/ SEO: links between venues and sitemaps (chantier 11).

LOCALISATION : tests/pytest/test_seo_maillage_sitemaps.py

Spec : TECH_DOC/SESSIONS/SEO/AUDIT-ACCUEIL-V2/RECAP.md (chantier 11).

Les tests tournent sur la base dev, dans une transaction annulee a la fin
(pytest.mark.django_db) : les evenements et les pages crees disparaissent.
Le cache memcached, lui, n'est pas annule : on neutralise son ecriture.
/ Tests run on the dev database inside a rolled-back transaction. Memcached
is not rolled back: its writes are neutralised.
"""

import re
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import identifiant_unique, taches_celery_enregistrees

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Sitemap des evenements d'un lieu / Venue events sitemap
# ---------------------------------------------------------------------------
def test_le_sitemap_des_evenements_reprend_l_agenda_du_lieu(tenant):
    """
    Dedans : a venir, non federable, passe recent.
    Dehors : archive, action benevole, passe depuis plus de 6 mois.
    / In: upcoming, non-federable, recent past. Out: archived, action, old past.
    """
    from BaseBillet.models import Event
    from BaseBillet.sitemap import EventSitemap

    maintenant = timezone.now()
    suffixe = identifiant_unique()

    def evenement(nom, decalage_en_jours, **champs):
        champs.setdefault("published", True)
        return Event.objects.create(
            name=f"TEST_sitemap {nom} {suffixe}",
            datetime=maintenant + timedelta(days=decalage_en_jours),
            **champs,
        )

    with tenant_context(tenant), taches_celery_enregistrees():
        attendus = [
            evenement("a venir", 10),
            evenement("non federable", 10, private=True),
            evenement("passe recent", -30),
        ]
        exclus = [
            evenement("archive", 10, archived=True),
            evenement("action", 10, categorie=Event.ACTION),
            evenement("passe ancien", -300),
            evenement("non publie", 10, published=False),
        ]

        pk_du_sitemap = set(EventSitemap().items().values_list("pk", flat=True))

    for evenement_attendu in attendus:
        assert evenement_attendu.pk in pk_du_sitemap, evenement_attendu.name
    for evenement_exclu in exclus:
        assert evenement_exclu.pk not in pk_du_sitemap, evenement_exclu.name


def test_le_sitemap_des_evenements_n_a_pas_de_lastmod(tenant):
    """
    L'evenement n'a pas de date de modification : pas de <lastmod> du tout.
    / Event has no modification date: no <lastmod> at all.
    """
    from BaseBillet.sitemap import EventSitemap

    with tenant_context(tenant):
        urls = EventSitemap().get_urls(protocol="https")

    assert urls, "Le lieu dev doit avoir au moins un evenement dans le sitemap."
    for url in urls:
        assert url["lastmod"] is None


# ---------------------------------------------------------------------------
# « Autour de nous » au sitemap / "Around us" in the sitemap
# ---------------------------------------------------------------------------
def _sections_du_sitemap(tenant, lieux_entrants_du_cache, afficher_lieux_entrants=True):
    """
    Sections du sitemap statique, sans FederatedPlace et sans tag de federation.
    / Static sitemap sections, without FederatedPlace nor federation tag.
    """
    from BaseBillet.models import FederatedPlace
    from BaseBillet.sitemap import StaticViewSitemap

    faux_manager = MagicMock()
    faux_manager.exists.return_value = False
    faux_manager.filter.return_value.exists.return_value = False

    with tenant_context(tenant):
        cache_entrants = {"by_tenant": {str(tenant.uuid): lieux_entrants_du_cache}}
        with (
            patch.object(FederatedPlace, "objects", faux_manager),
            patch("BaseBillet.models.FederationConfiguration.get_solo") as faux_fed,
            patch("BaseBillet.models.Configuration.get_solo") as fausse_config,
            patch("seo.views_common.get_seo_cache", return_value=cache_entrants),
        ):
            fausse_config.return_value.module_federation = True
            # Un attribut de MagicMock est toujours « vrai » : sans ces deux lignes,
            # les sections booking calculeraient les plannings avec un faux fuseau.
            # / A MagicMock attribute is always truthy: switch the booking sections off.
            fausse_config.return_value.module_booking = False
            fausse_config.return_value.module_benevolat = False
            faux_fed.return_value.afficher_lieux_entrants = afficher_lieux_entrants
            faux_fed.return_value.tags_federation.all.return_value = []
            return StaticViewSitemap().items()


def test_autour_de_nous_sort_du_sitemap_sans_aucun_voisin(tenant):
    """
    Option « lieux entrants » active mais personne ne nous declare -> page vide.
    / Incoming option on but nobody declares us -> empty page, out of the sitemap.
    """
    assert "federation-list" not in _sections_du_sitemap(tenant, [])


def test_un_lieu_entrant_suffit_a_declarer_autour_de_nous(tenant):
    assert "federation-list" in _sections_du_sitemap(tenant, ["uuid-d-un-voisin"])


def test_les_lieux_entrants_ne_comptent_pas_si_l_option_est_coupee(tenant):
    sections = _sections_du_sitemap(
        tenant, ["uuid-d-un-voisin"], afficher_lieux_entrants=False
    )
    assert "federation-list" not in sections


# ---------------------------------------------------------------------------
# Sitemaps de tibillet.coop / tibillet.coop sitemaps
# ---------------------------------------------------------------------------
def test_les_sitemaps_racine_n_ont_pas_de_lastmod():
    """
    Ni l'index (481 lieux) ni le sitemap des pages racine : aucune date fiable.
    / Neither the index nor the root pages sitemap: no reliable date.
    """
    from seo.views import sitemap_index_view, sitemap_root_view

    requete = RequestFactory().get("/sitemap.xml", HTTP_HOST="tibillet.localhost")
    index_des_lieux = {"tenants": [{"domain": "un-lieu.example"}]}
    with patch("seo.views.get_seo_cache", return_value=index_des_lieux):
        index = sitemap_index_view(requete).content.decode()
    pages_racine = sitemap_root_view(requete).content.decode()

    assert "<loc>https://un-lieu.example/sitemap.xml</loc>" in index
    assert "<lastmod>" not in index
    assert "<lastmod>" not in pages_racine


def _sitemap_racine_apres_recombinaison(tenant, **resume_du_lieu):
    """
    Modifie le resume SEO du lieu, recombine, et rend (domaines du sitemap
    racine, domaines des lieux de la carte).
    / Changes the venue SEO summary, recombines, returns both domain lists.
    """
    from seo.models import SEOCache
    from seo.tasks import rebuild_seo_aggregates

    fragment = SEOCache.objects.get(cache_type=SEOCache.TENANT_SUMMARY, tenant=tenant)
    donnees = dict(fragment.data)
    for cle, valeur in resume_du_lieu.items():
        if valeur is None:
            donnees.pop(cle, None)
        else:
            donnees[cle] = valeur
    fragment.data = donnees
    fragment.save()

    with patch("seo.services.set_memcached_l1"):
        rebuild_seo_aggregates(force=True)

    sitemap = SEOCache.objects.get(cache_type=SEOCache.SITEMAP_INDEX, tenant=None)
    lieux = SEOCache.objects.get(cache_type=SEOCache.AGGREGATE_LIEUX, tenant=None)
    return (
        {t["domain"] for t in sitemap.data["tenants"]},
        {lieu["domain"] for lieu in lieux.data["lieux"]},
    )


def test_un_lieu_a_l_accueil_vide_sort_du_sitemap_racine_mais_reste_sur_la_carte(
    tenant,
):
    domaine = tenant.get_primary_domain().domain
    domaines_sitemap, domaines_carte = _sitemap_racine_apres_recombinaison(
        tenant, accueil_sans_contenu=True, event_count=0, product_count=1
    )
    assert domaine not in domaines_sitemap
    assert domaine in domaines_carte


@pytest.mark.parametrize(
    "resume_du_lieu",
    [
        {"accueil_sans_contenu": True, "event_count": 2, "product_count": 1},
        {"accueil_sans_contenu": False, "event_count": 0, "product_count": 1},
        {"accueil_sans_contenu": None, "event_count": 0, "product_count": 1},
    ],
    ids=["accueil-vide-mais-evenements", "accueil-rempli", "fragment-ancien-sans-cle"],
)
def test_un_lieu_reste_dans_le_sitemap_racine(tenant, resume_du_lieu):
    domaine = tenant.get_primary_domain().domain
    domaines_sitemap, _ = _sitemap_racine_apres_recombinaison(tenant, **resume_du_lieu)
    assert domaine in domaines_sitemap


def test_une_page_d_accueil_cms_publiee_n_est_pas_un_accueil_vide(tenant):
    """
    Le resume SEO du lieu : accueil par defaut vide, mais page d'accueil CMS
    publiee -> l'accueil n'est pas vide.
    / Empty default home but a published CMS home -> not empty.
    """
    from BaseBillet.models import Configuration
    from pages.models import Page
    from seo.services import build_tenant_config_data

    with tenant_context(tenant):
        Configuration.objects.update(module_pages=True)
        Configuration.clear_cache()
        Page.objects.filter(est_accueil=True).update(publie=False)

    with patch("TiBillet.seo_indexing.accueil_par_defaut_est_vide", return_value=True):
        sans_page = build_tenant_config_data(tenant)["accueil_sans_contenu"]
        with tenant_context(tenant):
            accueil = Page.objects.filter(est_accueil=True).first()
            if accueil is None:
                Page.objects.create(
                    titre="Accueil (test)",
                    slug=f"accueil-{identifiant_unique()}",
                    est_accueil=True,
                    publie=True,
                )
            else:
                Page.objects.filter(pk=accueil.pk).update(publie=True)
        avec_page = build_tenant_config_data(tenant)["accueil_sans_contenu"]

    with tenant_context(tenant):
        Configuration.clear_cache()

    assert sans_page is True
    assert avec_page is False


# ---------------------------------------------------------------------------
# Liens HTML vers les voisins / HTML links to neighbours
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("skin", ["V2", "reunion"])
def test_autour_de_nous_lie_les_voisins_en_html(tenant, api_client, skin):
    """
    Avant le JavaScript, la liste #explorer-list contient un <a href> par voisin,
    et pas de lien vers le lieu courant.
    / Before JS, #explorer-list holds one <a href> per neighbour, none to self.
    """
    voisins = [
        {
            "tenant_id": "uuid-voisin",
            "name": "Le Voisin",
            "domain": "voisin.example",
            "locality": "Lyon",
        },
        {"tenant_id": str(tenant.uuid), "name": "Moi", "domain": "moi.example"},
    ]
    with (
        patch(
            "seo.services.build_explorer_data_for_tenants",
            return_value={"points": [], "tenants": voisins},
        ),
        patch("BaseBillet.views.get_skin_courant", return_value=skin),
    ):
        html = api_client.get("/federation/").content.decode()

    # Le bon gabarit a bien ete rendu (V2 : around-layout ; classic : non).
    # / The right template was rendered.
    assert ("around-layout" in html) == (skin == "V2")

    liste = re.search(
        r'data-testid="reseau-liste-lieux-html">(.*?)</ul>', html, re.S
    ).group(1)
    assert '<a href="https://voisin.example/">Le Voisin</a> — Lyon' in liste
    assert "moi.example" not in liste
