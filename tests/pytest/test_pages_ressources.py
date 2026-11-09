"""
Bloc SECTION en affichage RESSOURCES : les ressources sont des ImageGalerie.
/ SECTION block in RESSOURCES display: resources are ImageGalerie rows.

LOCALISATION : tests/pytest/test_pages_ressources.py

Une ImageGalerie = une ressource :
- `legende` = le titre ;
- `tags` = les badges, separes par des virgules ;
- `lien_url` = le lien du titre, FACULTATIF (pose seulement s'il commence par
  « http » ou « / ») ;
- `image` = la vignette, FACULTATIVE. Sans vignette : l'icone document (V2).

Les tests de rendu n'utilisent PAS la base : la galerie est posee dans le cache
de prefetch, comme le fait l'apercu en direct de l'admin.
/ Rendering tests use no database: the gallery goes into the prefetch cache.
"""

import pytest
from django.template.loader import render_to_string
from django_tenants.utils import tenant_context

from pages.models import Bloc, ImageGalerie

GABARITS_RESSOURCES = [
    "pages/classic/partials/bloc_section_ressources.html",
    "pages/V2/partials/bloc_section_ressources.html",
]


def _ressources_avec_elements(elements):
    """
    Un bloc RESSOURCES non enregistre, dont la galerie est `elements`.
    / An unsaved RESSOURCES block whose gallery is `elements`.
    """
    bloc = Bloc(type_bloc=Bloc.SECTION, affichage=Bloc.RESSOURCES)
    galerie = ImageGalerie.objects.none()
    galerie._result_cache = elements
    galerie._prefetch_done = True
    bloc._prefetched_objects_cache = {"images_galerie": galerie}
    return bloc


@pytest.mark.parametrize("gabarit", GABARITS_RESSOURCES)
def test_ressources_rend_la_vignette_quand_elle_existe(gabarit):
    """Avec image : un <img> de la variation med, alt vide (le titre est a cote).
    / With an image: an <img> of the med variation, empty alt."""
    ressource = ImageGalerie(
        legende="Café associatif",
        image="images/pages/galerie/cafe.jpg",
    )
    bloc = _ressources_avec_elements([ressource])

    html = render_to_string(gabarit, {"bloc": bloc})

    assert 'data-testid="ressource-element-vignette"' in html
    assert "cafe.med.jpg" in html
    assert 'alt=""' in html
    assert "Café associatif" in html


def test_ressources_v2_rend_l_icone_document_sans_vignette():
    """V2 sans image : l'icone document, cachee aux lecteurs d'ecran.
    / V2 without an image: the document icon, hidden from screen readers."""
    ressource = ImageGalerie(legende="Les statuts")
    bloc = _ressources_avec_elements([ressource])

    html = render_to_string(
        "pages/V2/partials/bloc_section_ressources.html", {"bloc": bloc}
    )

    assert 'data-testid="ressource-element-icone"' in html
    assert "<img" not in html


@pytest.mark.parametrize("gabarit", GABARITS_RESSOURCES)
def test_ressources_rend_le_lien_du_titre(gabarit):
    """Un lien interne rend le titre cliquable, en nouvel onglet.
    / An internal link makes the title clickable, in a new tab."""
    ressource = ImageGalerie(legende="Le journal", lien_url="/journal/")
    bloc = _ressources_avec_elements([ressource])

    html = render_to_string(gabarit, {"bloc": bloc})

    assert 'href="/journal/"' in html
    assert 'target="_blank"' in html


@pytest.mark.parametrize("gabarit", GABARITS_RESSOURCES)
def test_ressources_ne_pose_pas_de_lien_dangereux(gabarit):
    """Un lien javascript: n'est jamais pose, le titre reste affiche.
    / A javascript: link is never rendered; the title stays."""
    ressource = ImageGalerie(legende="Piege", lien_url="javascript:alert(1)")
    bloc = _ressources_avec_elements([ressource])

    html = render_to_string(gabarit, {"bloc": bloc})

    assert "javascript:" not in html
    assert "Piege" in html


@pytest.mark.parametrize("gabarit", GABARITS_RESSOURCES)
def test_ressources_rend_chaque_tag_en_badge(gabarit):
    """Chaque tag devient un badge, dans l'ordre saisi.
    / Each tag becomes a badge, in typed order."""
    ressource = ImageGalerie(legende="Ateliers", tags="Atelier, Accompagnement")
    bloc = _ressources_avec_elements([ressource])

    html = render_to_string(gabarit, {"bloc": bloc})

    assert html.index(">Atelier</span>") < html.index(">Accompagnement</span>")


def test_admin_ressources_propose_les_tags_et_le_lien():
    """Dans des RESSOURCES, l'encart Images montre les tags ET le lien.
    / In RESSOURCES, the images inline shows tags AND the link."""
    from Administration.admin.site import staff_admin_site
    from pages.admin import ImageGalerieInline

    inline = ImageGalerieInline(Bloc, staff_admin_site)
    bloc_ressources = Bloc(type_bloc=Bloc.SECTION, affichage=Bloc.RESSOURCES)

    champs = inline.get_fields(request=None, obj=bloc_ressources)

    assert "tags" in champs
    assert "lien_url" in champs


def test_admin_ressources_affiche_l_encart_images():
    """Un bloc RESSOURCES enregistre affiche l'encart Images.
    / A saved RESSOURCES block shows the images inline."""
    from Administration.admin.site import staff_admin_site
    from pages.admin import BlocAdmin, ImageGalerieInline

    admin = BlocAdmin(Bloc, staff_admin_site)
    bloc_ressources = Bloc(type_bloc=Bloc.SECTION, affichage=Bloc.RESSOURCES)

    assert admin.get_inlines(request=None, obj=bloc_ressources) == [ImageGalerieInline]


def test_api_ressources_cree_les_elements_avec_lien_et_tags(tenant):
    """
    API : une SECTION RESSOURCES recoit ses elements dans `image`, sans
    contentUrl (pas de telechargement). `url` devient le lien, un schema
    dangereux est vide, `keywords` devient `tags`. La lecture les renvoie.
    / API: RESSOURCES items come in `image`. url becomes the link (dangerous
    scheme emptied), keywords becomes tags. Read returns them.
    """
    from api_v2.serializers import BlocCreateSerializer, BlocSchemaSerializer
    from pages.models import Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Ressources API", slug="pytest-ressources-api")
        try:
            serializer = BlocCreateSerializer(
                data={
                    "additionalType": "SECTION",
                    "additionalProperty": [
                        {"name": "affichage", "value": "RESSOURCES"}
                    ],
                    "image": [
                        {
                            "@type": "ImageObject",
                            "caption": "Le journal",
                            "keywords": "Page",
                            "url": "/journal/",
                        },
                        {
                            "@type": "ImageObject",
                            "caption": "Piege",
                            "url": "javascript:alert(1)",
                        },
                    ],
                },
                context={"page": page},
            )
            assert serializer.is_valid(), serializer.errors
            bloc = serializer.save()

            elements = list(bloc.images_galerie.order_by("position"))
            assert elements[0].lien_url == "/journal/"
            assert elements[0].tags == "Page"
            assert elements[1].lien_url == ""

            sortie = BlocSchemaSerializer(bloc).data
            assert sortie["image"][0]["url"] == "/journal/"
            assert sortie["image"][0]["keywords"] == "Page"
            assert "contentUrl" not in sortie["image"][0]
        finally:
            page.delete()
