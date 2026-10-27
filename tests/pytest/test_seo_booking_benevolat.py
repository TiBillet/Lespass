"""
SEO des pages ressources et bénévolat : cartes de partage, JSON-LD et sitemap.
/ SEO of the resources and volunteering pages: social cards, JSON-LD and sitemap.

LOCALISATION : tests/pytest/test_seo_booking_benevolat.py

Code testé / Tested code :
- booking/templates/booking/views/resources_list.html, resource.html
- booking/templates/booking/benevolat/liste.html, planning.html
- pages/templatetags/pages_tags.py : jsonld_fil_ariane
- booking/views.py : texte_brut_d_un_texte_riche
- booking/sitemap.py : RessourceSitemap, PlanningSitemap
- BaseBillet/sitemap.py : StaticViewSitemap (booking-list, benevolat-liste)

Les blocs og_* et twitter_* du shell valent ceux de l'ACCUEIL tant qu'une page
ne les surcharge pas. Chaque test vérifie donc que la page partage SES infos.
Chaque test est marqué `django_db` : transaction annulée à la fin. Les fichiers
image, eux, ne sont pas annulés : on les efface à la main.
/ Shell og_*/twitter_* blocks default to the HOME ones. Each test is rolled back;
image files are not, so they are deleted by hand.

Lancer / Run : make test ARGS="tests/pytest/test_seo_booking_benevolat.py"
"""

import copy
import datetime
import io
import json
import re
from html.parser import HTMLParser
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context
from PIL import Image

from fabriques_panier import creer_ressource_avec_tarif, identifiant_unique

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les tâches et signaux activent la langue du lieu sans la remettre (tests/PIEGES.md).
    / Tasks and signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


def navigateur():
    """Client anonyme sur le lieu `lespass`, en français. / Anonymous client on `lespass`."""
    return Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr")


class _LecteurDesMetas(HTMLParser):
    """
    Lit les balises <meta> (name ou property) et les blocs JSON-LD d'une page.
    / Reads the <meta> tags and JSON-LD blocks of a page.
    """

    def __init__(self):
        super().__init__()
        self.metas = {}
        self.blocs_json_ld = []
        self._dans_un_json_ld = False

    def handle_starttag(self, tag, attributs):
        attributs = dict(attributs)
        if tag == "meta":
            cle = attributs.get("property") or attributs.get("name")
            if cle:
                self.metas[cle] = attributs.get("content", "")
        if tag == "script" and attributs.get("type") == "application/ld+json":
            self._dans_un_json_ld = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._dans_un_json_ld = False

    def handle_data(self, donnees):
        if self._dans_un_json_ld:
            self.blocs_json_ld.append(json.loads(donnees))


def lire_la_page(adresse):
    """
    GET la page, vérifie le 200, et rend ses metas et ses blocs JSON-LD.
    / GETs the page, checks the 200, returns its metas and JSON-LD blocks.
    """
    reponse = navigateur().get(adresse)
    assert reponse.status_code == 200, f"{adresse} -> {reponse.status_code}"
    lecteur = _LecteurDesMetas()
    lecteur.feed(reponse.content.decode())
    return lecteur


def bloc_json_ld_du_type(lecteur, type_schema):
    """Le premier bloc JSON-LD de ce @type, ou None. / First JSON-LD block of this @type."""
    for bloc in lecteur.blocs_json_ld:
        if bloc.get("@type") == type_schema:
            return bloc
    return None


def fichier_image(nom):
    """Une petite image PNG en mémoire. / A small in-memory PNG image."""
    tampon = io.BytesIO()
    Image.new("RGB", (1300, 700), color=(30, 120, 200)).save(tampon, format="PNG")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/png")


def planning_avec_un_besoin_a_venir(description=""):
    """
    Un planning publié qui a un besoin dans 3 jours : la liste le montre en carte.
    / A published planning with a need in 3 days. Call inside a tenant_context.
    """
    from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

    identifiant = identifiant_unique()
    planning = PlanningBenevole.objects.create(
        name=f"TEST_seo planning {identifiant}",
        slug=f"test-seo-planning-{identifiant}",
        description=description,
        published=True,
    )
    tache = TacheBenevole.objects.create(name=f"TEST_seo tache {identifiant}")
    BesoinBenevole.objects.create(
        planning=planning,
        tache=tache,
        date=timezone.localdate() + datetime.timedelta(days=3),
        heure_debut=datetime.time(18, 0),
        heure_fin=datetime.time(21, 0),
        nombre_souhaite=2,
    )
    return planning


def configuration_avec_les_modules_booking():
    """
    Une COPIE de la configuration, modules booking et bénévolat allumés. Elle n'est
    jamais écrite en base : la configuration réelle reste celle du lieu.
    / A COPY of the configuration with both modules on; never saved.
    """
    from BaseBillet.models import Configuration

    configuration_modifiee = copy.copy(Configuration.get_solo())
    configuration_modifiee.module_booking = True
    configuration_modifiee.module_benevolat = True
    return configuration_modifiee


# ---------------------------------------------------------------------------
# Page d'une ressource / Resource page
# ---------------------------------------------------------------------------
def test_la_page_d_une_ressource_partage_son_nom_et_son_image(tenant):
    """
    og:title et twitter:title = nom de la ressource ; og:image et twitter:image =
    la carte de partage (1200x630) de SON image, pas celle du lieu.
    / Shares the resource name and its own social card image.
    """
    with tenant_context(tenant):
        ressource = creer_ressource_avec_tarif(prix="12.00").ressource
        ressource.img = fichier_image("ressource_seo.png")
        ressource.save()
        try:
            from BaseBillet.models import Configuration

            nom_du_lieu = Configuration.get_solo().organisation
            lecteur = lire_la_page(f"/booking/{ressource.pk}/resource/")
            carte_de_partage = ressource.img.social_card.url
        finally:
            ressource.img.delete(save=False)

    assert lecteur.metas["og:title"] == f"{ressource.name} | {nom_du_lieu}"
    assert lecteur.metas["twitter:title"] == f"{ressource.name} | {nom_du_lieu}"
    assert lecteur.metas["og:image"].endswith(carte_de_partage)
    assert lecteur.metas["twitter:image"].endswith(carte_de_partage)
    assert lecteur.metas["og:image:alt"] == ressource.name


def test_la_page_d_une_ressource_a_un_fil_d_ariane_et_pas_de_product(tenant):
    """
    Fil d'Ariane à 3 maillons (Accueil > Ressources > la ressource) quand la liste
    existe (au moins deux ressources). Pas de JSON-LD Product : le tarif est horaire,
    souvent multiple, et absent de la page avant le clic sur un créneau.
    / 3-crumb breadcrumb when the list exists; no Product JSON-LD.
    """
    with tenant_context(tenant):
        ressource = creer_ressource_avec_tarif(prix="12.50").ressource
        creer_ressource_avec_tarif()
        lecteur = lire_la_page(f"/booking/{ressource.pk}/resource/")

    assert bloc_json_ld_du_type(lecteur, "Product") is None

    fil_ariane = bloc_json_ld_du_type(lecteur, "BreadcrumbList")
    noms_des_maillons = [maillon["name"] for maillon in fil_ariane["itemListElement"]]
    assert len(noms_des_maillons) == 3
    assert noms_des_maillons[-1] == ressource.name
    assert fil_ariane["itemListElement"][1]["item"].endswith("/booking/")


def test_une_ressource_sans_description_a_son_nom_en_meta_description(tenant):
    """
    Sans description, la meta description vaut le nom de la ressource : une meta
    vide est pire que pas de meta.
    / No description: the meta description is the resource name, never empty.
    """
    with tenant_context(tenant):
        ressource = creer_ressource_avec_tarif().ressource
        lecteur = lire_la_page(f"/booking/{ressource.pk}/resource/")

    assert not ressource.description
    assert lecteur.metas["description"] == ressource.name
    assert lecteur.metas["og:description"] == ressource.name


def test_le_texte_brut_ne_colle_pas_les_paragraphes():
    """
    Une espace remplace chaque fin de paragraphe et chaque <br> : sans elle,
    « …prises.</p><p>Réservez… » donnerait « prises.Réservez ». Les entités sont
    remises (&amp; -> &).
    / A space replaces each paragraph end and <br>; entities are unescaped.
    """
    from booking.views import texte_brut_d_un_texte_riche

    texte_riche = "<p>Six prises.</p><p>Thé &amp; café<br>offerts</p>"
    assert texte_brut_d_un_texte_riche(texte_riche) == "Six prises. Thé & café offerts"
    assert texte_brut_d_un_texte_riche(None) == ""


# ---------------------------------------------------------------------------
# Liste des ressources / Resources list
# ---------------------------------------------------------------------------
def test_la_liste_des_ressources_partage_son_propre_titre(tenant):
    """
    og:title = nom de la page Ressources, pas « Accueil ». Deux ressources au moins :
    avec une seule, la liste redirige vers sa page.
    / og:title is the Resources page name, not "Home".
    """
    with tenant_context(tenant):
        from BaseBillet.models import Configuration

        from django.utils.text import Truncator

        from booking.views import texte_brut_d_un_texte_riche

        creer_ressource_avec_tarif()
        creer_ressource_avec_tarif()
        config = Configuration.get_solo()
        nom_de_la_page = config.booking_menu_name or "Ressources"
        # Le texte d'introduction de la page (en texte brut, 20 mots), sinon la phrase
        # par défaut. / The page intro text, else the default sentence.
        description_attendue = (
            Truncator(
                texte_brut_d_un_texte_riche(config.description_booking_page)
            ).words(20)
            or "Réservez une ressource en ligne."
        )
        lecteur = lire_la_page("/booking/")

    assert lecteur.metas["og:title"] == f"{nom_de_la_page} | {config.organisation}"
    assert lecteur.metas["twitter:title"] == f"{nom_de_la_page} | {config.organisation}"
    assert lecteur.metas["description"] == description_attendue
    assert lecteur.metas["og:description"] == description_attendue
    assert lecteur.metas["twitter:description"] == description_attendue
    assert bloc_json_ld_du_type(lecteur, "BreadcrumbList") is not None


# ---------------------------------------------------------------------------
# Bénévolat / Volunteering
# ---------------------------------------------------------------------------
def test_la_page_d_un_planning_partage_son_nom_et_sa_presentation(tenant):
    """
    og:title = nom du planning ; description = sa présentation (meta, og, twitter).
    / og:title is the planning name; description is its presentation.
    """
    presentation = "Le bar tourne grâce aux bénévoles. Un créneau, une soirée !"
    with tenant_context(tenant):
        from BaseBillet.models import Configuration

        planning = planning_avec_un_besoin_a_venir(description=presentation)
        nom_du_lieu = Configuration.get_solo().organisation
        lecteur = lire_la_page(f"/booking/benevolat/{planning.slug}/")

    assert lecteur.metas["og:title"] == f"{planning.name} | {nom_du_lieu}"
    assert lecteur.metas["twitter:title"] == f"{planning.name} | {nom_du_lieu}"
    assert lecteur.metas["description"] == presentation
    assert lecteur.metas["og:description"] == presentation
    assert lecteur.metas["twitter:description"] == presentation

    fil_ariane = bloc_json_ld_du_type(lecteur, "BreadcrumbList")
    assert fil_ariane["itemListElement"][-1]["name"] == planning.name


def test_le_fil_d_ariane_d_un_planning_saute_la_liste_qui_redirige(tenant):
    """
    Avec un seul planning à venir, /booking/benevolat/ redirige vers lui : le fil
    d'Ariane du planning n'a pas de maillon « Bénévolat » (Accueil > le planning).
    / A single upcoming planning: the list redirects, so no list crumb.
    """
    with tenant_context(tenant):
        planning = planning_avec_un_besoin_a_venir()
        with mock.patch(
            "booking.views_benevolat.plannings_publies_avec_des_besoins_a_venir",
            return_value=[planning],
        ):
            lecteur = lire_la_page(f"/booking/benevolat/{planning.slug}/")

    fil_ariane = bloc_json_ld_du_type(lecteur, "BreadcrumbList")
    noms_des_maillons = [maillon["name"] for maillon in fil_ariane["itemListElement"]]
    assert len(noms_des_maillons) == 2
    assert noms_des_maillons[-1] == planning.name


def test_la_liste_des_plannings_partage_son_propre_titre(tenant):
    """
    og:title = nom de la page Bénévolat, pas « Accueil ». Deux plannings à venir au
    moins : avec un seul, la liste redirige vers sa page.
    / og:title is the Volunteering page name, not "Home".
    """
    with tenant_context(tenant):
        from BaseBillet.models import Configuration

        from django.utils.text import Truncator

        from booking.views import texte_brut_d_un_texte_riche

        planning_avec_un_besoin_a_venir()
        planning_avec_un_besoin_a_venir()
        config = Configuration.get_solo()
        nom_de_la_page = config.benevolat_menu_name or "Bénévolat"
        # Le texte d'introduction de la page (en texte brut, 20 mots), sinon la phrase
        # affichée sous le titre. / The page intro text, else the default sentence.
        description_attendue = Truncator(
            texte_brut_d_un_texte_riche(config.description_benevolat_page)
        ).words(20) or (
            "Les coups de main dont le lieu a besoin. "
            "Choisis un planning, puis une case : c'est noté."
        )
        lecteur = lire_la_page("/booking/benevolat/")

    assert lecteur.metas["og:title"] == f"{nom_de_la_page} | {config.organisation}"
    assert lecteur.metas["twitter:title"] == f"{nom_de_la_page} | {config.organisation}"
    assert lecteur.metas["description"] == description_attendue
    assert lecteur.metas["og:description"] == description_attendue
    assert lecteur.metas["twitter:description"] == description_attendue


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------
def test_le_sitemap_declare_chaque_ressource(tenant):
    """
    Module booking allumé : chaque ressource a son adresse dans le sitemap.
    Éteint : aucune.
    / Module on: every resource is declared. Off: none.
    """
    from BaseBillet.models import Configuration
    from booking.sitemap import RessourceSitemap

    with tenant_context(tenant):
        ressource = creer_ressource_avec_tarif().ressource
        configuration_allumee = configuration_avec_les_modules_booking()
        configuration_eteinte = copy.copy(configuration_allumee)
        configuration_eteinte.module_booking = False

        sitemap = RessourceSitemap()
        with mock.patch.object(
            Configuration, "get_solo", return_value=configuration_allumee
        ):
            adresses_module_allume = [sitemap.location(r) for r in sitemap.items()]
        with mock.patch.object(
            Configuration, "get_solo", return_value=configuration_eteinte
        ):
            adresses_module_eteint = [sitemap.location(r) for r in sitemap.items()]

    assert f"/booking/{ressource.pk}/resource/" in adresses_module_allume
    assert adresses_module_eteint == []


def test_le_sitemap_declare_chaque_planning_publie_avec_un_besoin_a_venir(tenant):
    """
    Module bénévolat allumé : chaque planning PUBLIÉ avec un besoin à venir est
    déclaré. Pas déclarés : un planning non publié (404 pour le public), un planning
    publié sans besoin à venir (page quasi vide). Module éteint : aucun.
    / Module on: published plannings with an upcoming need only. Off: none.
    """
    from BaseBillet.models import Configuration
    from booking.models import PlanningBenevole
    from booking.sitemap import PlanningSitemap

    with tenant_context(tenant):
        planning_publie = planning_avec_un_besoin_a_venir()
        identifiant = identifiant_unique()
        planning_non_publie = PlanningBenevole.objects.create(
            name=f"TEST_seo brouillon {identifiant}",
            slug=f"test-seo-brouillon-{identifiant}",
            published=False,
        )
        planning_sans_besoin = PlanningBenevole.objects.create(
            name=f"TEST_seo sans besoin {identifiant}",
            slug=f"test-seo-sans-besoin-{identifiant}",
            published=True,
        )
        configuration_allumee = configuration_avec_les_modules_booking()
        configuration_eteinte = copy.copy(configuration_allumee)
        configuration_eteinte.module_benevolat = False

        sitemap = PlanningSitemap()
        with mock.patch.object(
            Configuration, "get_solo", return_value=configuration_allumee
        ):
            adresses_module_allume = [sitemap.location(p) for p in sitemap.items()]
        with mock.patch.object(
            Configuration, "get_solo", return_value=configuration_eteinte
        ):
            adresses_module_eteint = [sitemap.location(p) for p in sitemap.items()]

    assert f"/booking/benevolat/{planning_publie.slug}/" in adresses_module_allume
    assert (
        f"/booking/benevolat/{planning_non_publie.slug}/" not in adresses_module_allume
    )
    assert (
        f"/booking/benevolat/{planning_sans_besoin.slug}/" not in adresses_module_allume
    )
    assert adresses_module_eteint == []


def test_le_sitemap_declare_les_pages_liste_du_booking(tenant):
    """
    Deux ressources et deux plannings à venir : les deux pages liste sont déclarées.
    / Two resources and two upcoming plannings: both list pages are declared.
    """
    from BaseBillet.models import Configuration
    from BaseBillet.sitemap import StaticViewSitemap

    with tenant_context(tenant):
        creer_ressource_avec_tarif()
        creer_ressource_avec_tarif()
        planning_avec_un_besoin_a_venir()
        planning_avec_un_besoin_a_venir()

        sitemap = StaticViewSitemap()
        with mock.patch.object(
            Configuration,
            "get_solo",
            return_value=configuration_avec_les_modules_booking(),
        ):
            adresses = [sitemap.location(page) for page in sitemap.items()]

    assert "/booking/" in adresses
    assert "/booking/benevolat/" in adresses


def test_aucune_page_ne_partage_le_titre_de_l_accueil(tenant):
    """
    Garde-fou : le titre de l'accueil (« Accueil | lieu ») ne doit apparaître sur
    aucune des quatre pages. C'est la valeur du shell quand un gabarit oublie un bloc.
    / Safety net: no page may share the home title, the shell's default.
    """
    with tenant_context(tenant):
        ressource = creer_ressource_avec_tarif().ressource
        creer_ressource_avec_tarif()
        planning = planning_avec_un_besoin_a_venir()
        planning_avec_un_besoin_a_venir()
        adresses = [
            "/booking/",
            f"/booking/{ressource.pk}/resource/",
            "/booking/benevolat/",
            f"/booking/benevolat/{planning.slug}/",
        ]
        for adresse in adresses:
            lecteur = lire_la_page(adresse)
            for cle in ("og:title", "twitter:title"):
                assert not re.match(r"^(Accueil|Home) \|", lecteur.metas[cle]), (
                    f"{adresse} {cle}"
                )
