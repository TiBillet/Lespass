"""
Page publique d'un évènement : place et balisage des deux descriptions.
/ Public event page: position and markup of the two descriptions.

LOCALISATION : tests/pytest/test_evenement_rendu_descriptions.py

Code testé / Tested code :
- pages/templates/pages/V2/vues/evenement.html (bloc evenement_description)
- pages/templates/pages/classic/partials/evenement_accordeon.html

Skin V2, ordre attendu dans l'en-tête : description courte, galerie d'images,
description longue. La description longue est du HTML saisi dans l'admin
(paragraphes, listes). Elle doit être dans un <div> : un <p> autour d'elle est
fermé par le navigateur au premier bloc, et la suite du texte perd son style.
/ V2 skin order: short description, gallery, long description. The long
description is block HTML: it must sit in a <div>, never in a <p>.

Le skin est simulé : `BaseBillet.views.get_skin_courant` est patché. Il n'est
jamais lu ni écrit en base.
/ The skin is mocked; it is never read from or written to the database.

Chaque test est marqué `django_db` : transaction annulée à la fin. Les fichiers
image de la galerie sont supprimés à la main (le rollback ne touche pas au disque).
/ Each test is rolled back. Gallery image files are deleted by hand.

Lancer / Run :
    docker exec lespass_django poetry run pytest \
        tests/pytest/test_evenement_rendu_descriptions.py -q
"""

import io
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import tenant_context
from PIL import Image

from fabriques_panier import client_connecte, creer_evenement_avec_tarif

pytestmark = pytest.mark.django_db


# Description longue au format de l'admin : un paragraphe, une liste, un
# paragraphe. C'est le cas qui cassait le rendu (voir le docstring du module).
# / Admin-style long description: paragraph, list, paragraph.
DESCRIPTION_LONGUE_EN_HTML = (
    "<p>Premier paragraphe de la description.</p>"
    "<ul><li>Premier point</li><li>Second point</li></ul>"
    "<p>Dernier paragraphe de la description.</p>"
)
DESCRIPTION_COURTE = "Un résumé de l'évènement en une phrase."

OUVERTURE_DU_DIV_DE_LA_DESCRIPTION_LONGUE = (
    '<div class="event-prose" data-testid="evenement-description-longue">'
)


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """Le lieu `lespass`, Stripe simulé. / The `lespass` venue, Stripe faked."""
    with tenant_context(tenant):
        yield tenant


def _page_de_l_evenement(evenement, skin):
    """
    HTML de la page publique de l'évènement, rendue avec le skin donné.
    / Public event page HTML, rendered with the given skin.
    """
    with patch("BaseBillet.views.get_skin_courant", return_value=skin):
        reponse = client_connecte().get(f"/event/{evenement.slug}/")
    assert reponse.status_code == 200
    return reponse.content.decode()


def _evenement_avec_descriptions(courte, longue):
    """
    Crée un évènement en vente avec ses deux descriptions.
    / Creates an on-sale event with both descriptions.
    """
    evenement = creer_evenement_avec_tarif().evenement
    evenement.short_description = courte
    evenement.long_description = longue
    evenement.save()
    return evenement


def _image_de_galerie():
    """
    Crée une diapositive de galerie (BaseBillet.Carrousel) avec une petite image.
    / Creates a gallery slide with a small image.
    """
    from BaseBillet.models import Carrousel

    tampon = io.BytesIO()
    Image.new("RGB", (200, 100), color=(200, 30, 30)).save(tampon, format="PNG")
    fichier = SimpleUploadedFile(
        "galerie_rendu_descriptions.png", tampon.getvalue(), content_type="image/png"
    )
    return Carrousel.objects.create(img=fichier)


def test_v2_ordre_courte_puis_galerie_puis_longue(lieu):
    """
    Skin V2 avec une galerie : la description courte vient avant les images,
    la description longue après.
    / V2 with a gallery: short description before the images, long one after.
    """
    evenement = _evenement_avec_descriptions(
        DESCRIPTION_COURTE, DESCRIPTION_LONGUE_EN_HTML
    )
    diapositive = _image_de_galerie()
    try:
        evenement.carrousel.add(diapositive)
        html = _page_de_l_evenement(evenement, skin="V2")
    finally:
        # Supprime l'image et ses variations sur le disque.
        # / Deletes the image file and its variations.
        diapositive.delete()

    position_de_la_courte = html.find('data-testid="evenement-description-courte"')
    position_de_la_galerie = html.find('data-testid="evenement-galerie"')
    position_de_la_longue = html.find('data-testid="evenement-description-longue"')

    assert position_de_la_courte != -1, "description courte absente"
    assert position_de_la_galerie != -1, "galerie absente"
    assert position_de_la_longue != -1, "description longue absente"
    assert position_de_la_courte < position_de_la_galerie < position_de_la_longue


def test_v2_la_description_longue_est_entiere_dans_son_div(lieu):
    """
    Skin V2 : tout le HTML de la description longue est juste après l'ouverture
    du <div class="event-prose">, et aucun <p> ne l'entoure.
    / V2: the whole long description sits right inside the event-prose div.
    """
    evenement = _evenement_avec_descriptions(
        DESCRIPTION_COURTE, DESCRIPTION_LONGUE_EN_HTML
    )
    html = _page_de_l_evenement(evenement, skin="V2")

    position_du_div = html.find(OUVERTURE_DU_DIV_DE_LA_DESCRIPTION_LONGUE)
    assert position_du_div != -1, "div de la description longue absent"

    # Entre l'ouverture du <div> et la description, seulement des blancs.
    # / Only whitespace between the div opening and the description.
    texte_apres_le_div = html[
        position_du_div + len(OUVERTURE_DU_DIV_DE_LA_DESCRIPTION_LONGUE) :
    ]
    assert texte_apres_le_div.lstrip().startswith(DESCRIPTION_LONGUE_EN_HTML)

    # La description courte reste un <p> à part, avant la longue.
    # / The short description stays a separate <p>, before the long one.
    assert (
        f'<p class="page-intro" data-testid="evenement-description-courte">'
        f"{DESCRIPTION_COURTE.replace(chr(39), '&#x27;')}</p>"
    ) in html
    assert html.find("evenement-description-courte") < position_du_div


def test_v2_sans_galerie_la_courte_precede_la_longue(lieu):
    """
    Skin V2 sans galerie : les deux descriptions restent dans le bon ordre,
    et la page n'affiche pas de galerie vide.
    / V2 without a gallery: both descriptions in order, no empty gallery.
    """
    evenement = _evenement_avec_descriptions(
        DESCRIPTION_COURTE, DESCRIPTION_LONGUE_EN_HTML
    )
    html = _page_de_l_evenement(evenement, skin="V2")

    assert 'data-testid="evenement-galerie"' not in html
    assert html.find('data-testid="evenement-description-courte"') < html.find(
        'data-testid="evenement-description-longue"'
    )


def test_classic_la_description_longue_n_est_pas_dans_un_p(lieu):
    """
    Skin classic : dans l'accordéon « Schedule », la description longue est
    dans un <div>, jamais dans un <p>.
    / Classic skin: in the "Schedule" accordion, the long description is in a div.
    """
    evenement = _evenement_avec_descriptions(
        DESCRIPTION_COURTE, DESCRIPTION_LONGUE_EN_HTML
    )
    html = _page_de_l_evenement(evenement, skin="reunion")

    assert f"<div>{DESCRIPTION_LONGUE_EN_HTML}</div>" in html
    assert f"<p>{DESCRIPTION_LONGUE_EN_HTML}" not in html
