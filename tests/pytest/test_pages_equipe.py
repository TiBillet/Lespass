"""
Bloc SECTION en affichage EQUIPE : les personnes sont des ImageGalerie.
/ SECTION block in EQUIPE display: people are ImageGalerie rows.

LOCALISATION : tests/pytest/test_pages_equipe.py

Une ImageGalerie = une personne :
- `legende` = le nom ;
- `tags` = les badges, separes par des virgules (ImageGalerie.liste_des_tags) ;
- `image` = la photo, FACULTATIVE. Avec photo : <img> recadree en rond par le
  CSS. Sans photo : l'initiale du nom.

Les tests de rendu n'utilisent PAS la base : un Bloc non enregistre a deja une
pk (uuid par defaut), et la galerie est posee dans le cache de prefetch, comme
le fait l'apercu en direct de l'admin (admin_apercu.py:_reconstruire_la_galerie).
/ Rendering tests use no database: the gallery goes into the prefetch cache,
like the admin live preview does.
"""

import re

import pytest
from django.template.loader import render_to_string
from django_tenants.utils import tenant_context

from pages.models import Bloc, ImageGalerie

GABARITS_EQUIPE = [
    "pages/classic/partials/bloc_section_equipe.html",
    "pages/V2/partials/bloc_section_equipe.html",
]


def _equipe_avec_personnes(personnes):
    """
    Un bloc EQUIPE non enregistre, dont la galerie est `personnes`.
    / An unsaved EQUIPE block whose gallery is `personnes`.
    """
    bloc = Bloc(type_bloc=Bloc.SECTION, affichage=Bloc.EQUIPE)
    galerie = ImageGalerie.objects.none()
    galerie._result_cache = personnes
    galerie._prefetch_done = True
    bloc._prefetched_objects_cache = {"images_galerie": galerie}
    return bloc


def test_liste_des_tags_decoupe_sur_les_virgules_et_ignore_les_vides():
    """« Coordination, , Salariée » donne deux tags, sans espaces autour.
    / Splits on commas, strips, drops empty tags."""
    personne = ImageGalerie(tags=" Coordination, , Salariée ,")

    assert personne.liste_des_tags() == ["Coordination", "Salariée"]


def test_liste_des_tags_vide_sans_tags():
    """Pas de tags : liste vide. / No tags: empty list."""
    assert ImageGalerie(tags="").liste_des_tags() == []


@pytest.mark.parametrize("gabarit", GABARITS_EQUIPE)
def test_equipe_rend_la_photo_quand_elle_existe(gabarit):
    """Avec photo : un <img> de la variation med, alt vide (le nom est a cote).
    / With a photo: an <img> of the med variation, empty alt."""
    personne = ImageGalerie(
        legende="Awa Diallo",
        image="images/pages/galerie/awa.jpg",
    )
    bloc = _equipe_avec_personnes([personne])

    html = render_to_string(gabarit, {"bloc": bloc})

    assert 'data-testid="equipe-membre-photo"' in html
    assert "awa.med.jpg" in html
    assert 'alt=""' in html
    assert 'data-testid="equipe-membre-initiale"' not in html
    assert "Awa Diallo" in html


@pytest.mark.parametrize("gabarit", GABARITS_EQUIPE)
def test_equipe_rend_l_initiale_sans_photo(gabarit):
    """Sans photo : l'initiale du nom, en majuscule, cachee aux lecteurs d'ecran.
    / Without a photo: the name's initial, hidden from screen readers."""
    personne = ImageGalerie(legende="théo Marchand")
    bloc = _equipe_avec_personnes([personne])

    html = render_to_string(gabarit, {"bloc": bloc})

    # L'initiale suit l'attribut data-testid, dans un <span> interne en V2.
    # / The initial follows the data-testid, inside an inner <span> in V2.
    initiale_trouvee = re.search(
        r'data-testid="equipe-membre-initiale">(<span[^>]*>)?T<', html
    )
    assert initiale_trouvee is not None
    assert "<img" not in html


@pytest.mark.parametrize("gabarit", GABARITS_EQUIPE)
def test_equipe_rend_chaque_tag_en_badge_dans_l_ordre(gabarit):
    """Chaque tag devient un badge, dans l'ordre saisi.
    / Each tag becomes a badge, in typed order."""
    personne = ImageGalerie(legende="Awa Diallo", tags="Coordination, Salariée")
    bloc = _equipe_avec_personnes([personne])

    html = render_to_string(gabarit, {"bloc": bloc})

    assert ">Coordination</span>" in html
    assert ">Salariée</span>" in html
    assert html.index(">Coordination</span>") < html.index(">Salariée</span>")


@pytest.mark.parametrize("gabarit", GABARITS_EQUIPE)
def test_equipe_sans_personne_ne_rend_pas_de_liste(gabarit):
    """Galerie vide : pas de <ul> vide. / Empty gallery: no empty list."""
    bloc = _equipe_avec_personnes([])

    html = render_to_string(gabarit, {"bloc": bloc})

    assert "<ul" not in html


def test_admin_equipe_propose_les_tags_et_pas_le_lien():
    """Dans une EQUIPE, l'encart Images montre les tags et cache le lien
    (le gabarit de l'equipe ne le rend pas).
    / In an EQUIPE, the images inline shows tags and hides the link."""
    from Administration.admin.site import staff_admin_site
    from pages.admin import ImageGalerieInline

    inline = ImageGalerieInline(Bloc, staff_admin_site)
    bloc_equipe = Bloc(type_bloc=Bloc.SECTION, affichage=Bloc.EQUIPE)

    champs = inline.get_fields(request=None, obj=bloc_equipe)

    assert "tags" in champs
    assert "lien_url" not in champs


def test_admin_galerie_hors_equipe_garde_le_lien_sans_tags():
    """Une bande de logos garde le lien, et ne propose pas les tags.
    / A logo strip keeps the link and does not offer tags."""
    from Administration.admin.site import staff_admin_site
    from pages.admin import ImageGalerieInline

    inline = ImageGalerieInline(Bloc, staff_admin_site)
    bloc_logos = Bloc(type_bloc=Bloc.IMAGES, affichage=Bloc.BANDE_LOGOS)

    champs = inline.get_fields(request=None, obj=bloc_logos)

    assert "lien_url" in champs
    assert "tags" not in champs


def test_admin_equipe_affiche_l_encart_images():
    """Un bloc EQUIPE enregistre affiche l'encart Images.
    / A saved EQUIPE block shows the images inline."""
    from Administration.admin.site import staff_admin_site
    from pages.admin import BlocAdmin, ImageGalerieInline

    admin = BlocAdmin(Bloc, staff_admin_site)
    bloc_equipe = Bloc(type_bloc=Bloc.SECTION, affichage=Bloc.EQUIPE)

    assert admin.get_inlines(request=None, obj=bloc_equipe) == [ImageGalerieInline]

def test_api_equipe_cree_les_personnes_sans_photo_et_les_expose(tenant):
    """
    API : une SECTION EQUIPE recoit ses personnes dans `image`, sans photo
    (la photo s'envoie ensuite par POST /api/v2/blocs/{uuid}/images/).
    `keywords` (texte ou liste) devient `tags`, et ressort tel quel en lecture.
    / API: EQUIPE people come in `image`, without photo; keywords (text or
    list) becomes tags and is exposed on read.
    """
    from api_v2.serializers import BlocCreateSerializer, BlocSchemaSerializer
    from pages.models import Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Equipe API", slug="pytest-equipe-api")
        try:
            serializer = BlocCreateSerializer(
                data={
                    "additionalType": "SECTION",
                    "additionalProperty": [{"name": "affichage", "value": "EQUIPE"}],
                    "image": [
                        {
                            "@type": "ImageObject",
                            "caption": "Awa Diallo",
                            "keywords": "Coordination, Salariée",
                        },
                        {
                            "@type": "ImageObject",
                            "caption": "Théo Marchand",
                            "keywords": ["Vie associative", "Bénévole"],
                        },
                    ],
                },
                context={"page": page},
            )
            assert serializer.is_valid(), serializer.errors
            bloc = serializer.save()

            personnes = list(bloc.images_galerie.order_by("position"))
            assert [personne.legende for personne in personnes] == [
                "Awa Diallo",
                "Théo Marchand",
            ]
            assert bool(personnes[0].image) is False
            assert personnes[1].tags == "Vie associative, Bénévole"

            sortie = BlocSchemaSerializer(bloc).data
            assert sortie["image"][0]["keywords"] == "Coordination, Salariée"
            assert "contentUrl" not in sortie["image"][0]
        finally:
            page.delete()
