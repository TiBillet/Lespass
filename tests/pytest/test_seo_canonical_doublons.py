"""
SEO — canonical sans parametres, noindex des copies, fiches evenement federees.
/ SEO — canonical without query parameters, noindex copies, federated event pages.

LOCALISATION : tests/pytest/test_seo_canonical_doublons.py

Spec : TECH_DOC/SESSIONS/SEO/CHANTIER-09-canonical-doublons.md

En dev, `should_noindex()` renvoie toujours True (DEBUG) : toutes les pages y
sont deja en noindex. Les tests qui lisent la balise robots le neutralisent
pour observer le comportement de production.
/ In dev, should_noindex() is always True: robots tests patch it to observe the
production behaviour.
"""

import re
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db

HOTE = "https://lespass.tibillet.localhost"
SKINS = ["V2", "classic", "faire_festival"]


def _balise(html, motif):
    """
    Rend la valeur d'une balise du <head> (canonical, og:url, robots).
    / Returns the value of a <head> tag.
    """
    trouve = re.search(motif, html)
    assert trouve, f"balise introuvable : {motif}"
    return trouve.group(1)


def _canonical(html):
    return _balise(html, r'<link rel="canonical" href="([^"]*)"')


def _og_url(html):
    return _balise(html, r'<meta property="og:url" content="([^"]*)"')


def _robots(html):
    return _balise(html, r'<meta name="robots" content="([^"]*)"')


@pytest.fixture
def evenement_publie(tenant):
    """
    Un evenement publie du lieu lespass (base dev).
    / A published event of the lespass venue (dev database).
    """
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement = Event.objects.filter(published=True).exclude(slug="").first()
    assert evenement is not None, "la base dev n'a aucun evenement publie"
    return evenement


@pytest.mark.parametrize("skin", SKINS)
def test_le_canonical_de_l_accueil_ignore_les_parametres_d_url(api_client, skin):
    """
    /?utm_source=... ne cree pas une page canonique de plus : canonical et
    og:url valent l'adresse sans parametres.
    / Tracked links do not create a new canonical page.
    """
    with patch("BaseBillet.views.get_skin_courant", return_value=skin):
        reponse = api_client.get("/?utm_source=newsletter&utm_medium=email")
    html = reponse.content.decode()

    assert _canonical(html) == f"{HOTE}/"
    assert _og_url(html) == f"{HOTE}/"


def test_l_agenda_filtre_par_tag_pointe_vers_l_agenda(api_client):
    """
    /event/?tag=... a pour canonical /event/ (pas une page par filtre).
    / A tag-filtered agenda canonicalises to /event/.
    """
    with patch("BaseBillet.views.get_skin_courant", return_value="V2"):
        reponse = api_client.get("/event/?tag=concert")
    assert _canonical(reponse.content.decode()) == f"{HOTE}/event/"


def test_l_agenda_en_iframe_est_en_noindex(api_client):
    """
    /event/embed/ (agenda pose en iframe chez un lieu) est une copie de /event/.
    / The embedded agenda is a copy of /event/: noindex.
    """
    with patch("TiBillet.seo_indexing.should_noindex", return_value=False):
        with patch("BaseBillet.views.get_skin_courant", return_value="V2"):
            reponse_agenda = api_client.get("/event/")
            reponse_iframe = api_client.get("/event/embed/")

    assert _robots(reponse_agenda.content.decode()) == "index, follow"
    assert _robots(reponse_iframe.content.decode()) == "noindex, nofollow"


def test_l_apercu_d_un_skin_est_en_noindex(api_client):
    """
    ?skin_preview=<skin> rend la meme page avec un autre habillage : noindex.
    / A skin preview renders the same page in another skin: noindex.
    """
    with patch("TiBillet.seo_indexing.should_noindex", return_value=False):
        with patch("BaseBillet.views.get_skin_courant", return_value="V2"):
            reponse = api_client.get("/?skin_preview=reunion")
    assert _robots(reponse.content.decode()) == "noindex, nofollow"


@pytest.mark.parametrize("skin", SKINS)
def test_une_fiche_evenement_federee_pointe_vers_le_lieu_d_origine(
    api_client, evenement_publie, skin
):
    """
    Un evenement d'un lieu federe, affiche ici, est une copie :
    - canonical et og:url = son adresse sur le lieu d'origine (event.full_url) ;
    - noindex ;
    - pas de JSON-LD Event (organizer et location y seraient ceux du lieu qui
      affiche la page).
    / A federated copy points to its origin, is noindex and has no Event JSON-LD.
    """
    adresse_d_origine = "https://lieu-voisin.tibillet.localhost/event/concert-voisin/"
    evenement_publie.full_url = adresse_d_origine
    evenement_publie.img = evenement_publie.get_img()

    # Le slug demande n'existe pas ici : la vue cherche chez les lieux federes.
    # / The requested slug does not exist here: the view looks in federated venues.
    with patch("TiBillet.seo_indexing.should_noindex", return_value=False):
        with patch("BaseBillet.views.get_skin_courant", return_value=skin):
            with patch(
                "BaseBillet.views.EventMVT.federated_events_get",
                return_value=evenement_publie,
            ):
                reponse = api_client.get("/event/pytest-copie-federee/")
    html = reponse.content.decode()

    assert reponse.status_code == 200
    assert _canonical(html) == adresse_d_origine
    assert _og_url(html) == adresse_d_origine
    assert _robots(html) == "noindex, follow"
    assert '"@type": "Event"' not in html


def test_une_fiche_evenement_locale_garde_son_canonical_et_son_json_ld(
    api_client, evenement_publie
):
    """
    Un evenement du lieu : canonical sur lui-meme (sans parametres), indexable,
    JSON-LD Event present avec une url sans parametres.
    / A local event: self canonical without query, indexable, Event JSON-LD.
    """
    adresse_locale = f"{HOTE}/event/{evenement_publie.slug}/"
    with patch("TiBillet.seo_indexing.should_noindex", return_value=False):
        with patch("BaseBillet.views.get_skin_courant", return_value="V2"):
            reponse = api_client.get(f"/event/{evenement_publie.slug}/?utm_source=x")
    html = reponse.content.decode()

    assert reponse.status_code == 200
    assert _canonical(html) == adresse_locale
    assert _robots(html) == "index, follow"
    assert '"@type": "Event"' in html
    # Le client de test n'est pas en HTTPS : build_absolute_uri y rend http://.
    # On verifie le chemin, et l'absence de parametres.
    # / The test client is not HTTPS: check the path and the missing query.
    chemin_local = f"/event/{evenement_publie.slug}/"
    assert re.search(
        rf'"url": "https?://lespass\.tibillet\.localhost{re.escape(chemin_local)}"',
        html,
    )
    assert "utm_source" not in html
