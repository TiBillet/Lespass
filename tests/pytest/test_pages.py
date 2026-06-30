"""
Tests de l'app pages (modeles, vue publique, admin).
/ Tests of the pages app (models, public view, admin).

LOCALISATION : tests/pytest/test_pages.py
Pattern : base dev live (pas de rollback). Chaque test cree puis supprime ses
donnees ; les pages de test ont un slug prefixe "pytest-". Une fixture restaure
l'etat de la page d'accueil (est_accueil) apres les tests qui y touchent.
/ Pattern: live dev DB (no rollback). Each test creates then deletes its data;
test pages use a "pytest-" slug prefix. A fixture restores the home page state
(est_accueil) after tests that touch it.
"""
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def nettoyer_pages(tenant):
    """
    Supprime les pages de test (slug "pytest-...") apres le test et restaure
    l'etat est_accueil existant (pour ne pas casser la page d'accueil du dev).
    / Deletes test pages after the test and restores the existing est_accueil
    state (so the dev home page is not broken).
    """
    from pages.models import Page

    with tenant_context(tenant):
        accueil_avant = list(
            Page.objects.filter(est_accueil=True).values_list("pk", flat=True)
        )

    yield

    with tenant_context(tenant):
        Page.objects.filter(slug__startswith="pytest-").delete()
        # On remet l'etat d'avant : seules les pages d'accueil d'origine sont cochees.
        # / Restore the prior state: only the original home pages stay checked.
        Page.objects.exclude(pk__in=accueil_avant).filter(est_accueil=True).update(
            est_accueil=False
        )
        if accueil_avant:
            Page.objects.filter(pk__in=accueil_avant).update(est_accueil=True)


# ---------------------------------------------------------------------------
# Modeles / Models
# ---------------------------------------------------------------------------
def test_creation_page_et_str(tenant, nettoyer_pages):
    """On peut creer une Page et son __str__ contient le titre."""
    from pages.models import Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Accueil", slug="pytest-accueil")
        assert "Pytest Accueil" in str(page)
        assert "brouillon" in str(page)  # publie=False par defaut


def test_slug_reserve_est_rejete(tenant):
    """Un slug reserve (ex: 'event') leve une ValidationError au full_clean()."""
    from pages.models import Page

    with tenant_context(tenant):
        page = Page(titre="Collision", slug="event")
        with pytest.raises(ValidationError):
            page.full_clean()


def test_blocs_ordonnes_par_position(tenant, nettoyer_pages):
    """Les blocs d'une page sont retournes dans l'ordre croissant de position."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Ordre", slug="pytest-ordre")
        Bloc.objects.create(page=page, type_bloc=Bloc.CTA, position=3)
        Bloc.objects.create(page=page, type_bloc=Bloc.HERO, position=1)
        Bloc.objects.create(page=page, type_bloc=Bloc.PARAGRAPHE, position=2)

        positions = list(page.blocs.values_list("position", flat=True))
        assert positions == [1, 2, 3]


def test_grouper_blocs_section_carte():
    """Un bloc INFOS suivi d'un CARTE_LEAFLET forme un groupe section_carte
    (infos a gauche, carte a droite)."""
    from pages.models import Bloc
    from pages.services import grouper_blocs

    blocs = [
        Bloc(type_bloc=Bloc.INFOS),
        Bloc(type_bloc=Bloc.CARTE_LEAFLET),
        Bloc(type_bloc=Bloc.PARAGRAPHE),
    ]
    groupes = grouper_blocs(blocs)
    assert groupes[0]["type"] == "section_carte"
    assert groupes[0]["info"].type_bloc == "INFOS"
    assert groupes[0]["carte"].type_bloc == "CARTE_LEAFLET"
    # Le PARAGRAPHE qui suit reste un bloc seul.
    assert groupes[1]["type"] == "solo"


def test_grouper_blocs_faq_deux_colonnes():
    """Des blocs FAQ consecutifs sont regroupes (rendus en 2 colonnes)."""
    from pages.models import Bloc
    from pages.services import grouper_blocs

    blocs = [Bloc(type_bloc=Bloc.FAQ), Bloc(type_bloc=Bloc.FAQ), Bloc(type_bloc=Bloc.FAQ)]
    groupes = grouper_blocs(blocs)
    assert len(groupes) == 1
    assert groupes[0]["type"] == "faq"
    assert len(groupes[0]["blocs"]) == 3


def test_grouper_blocs_regroupe_cartes_consecutives():
    """grouper_blocs regroupe les CARTE consecutives, isole les autres blocs."""
    from pages.models import Bloc
    from pages.services import grouper_blocs

    blocs = [
        Bloc(type_bloc=Bloc.HERO),
        Bloc(type_bloc=Bloc.CARTE),
        Bloc(type_bloc=Bloc.CARTE),
        Bloc(type_bloc=Bloc.CTA),
        Bloc(type_bloc=Bloc.CARTE),
    ]
    groupes = grouper_blocs(blocs)
    types = [g["type"] for g in groupes]
    # HERO seul, [CARTE, CARTE] en grille, CTA seul, [CARTE] en grille.
    assert types == ["solo", "grille", "solo", "grille"]
    assert len(groupes[1]["blocs"]) == 2
    assert len(groupes[3]["blocs"]) == 1


def test_grouper_blocs_section_video_absorbe_cartes_et_cta():
    """Un VIDEO_TEXTE absorbe les CARTE suivantes + un CTA en une section_video."""
    from pages.models import Bloc
    from pages.services import grouper_blocs

    blocs = [
        Bloc(type_bloc=Bloc.VIDEO_TEXTE),
        Bloc(type_bloc=Bloc.CARTE),
        Bloc(type_bloc=Bloc.CARTE),
        Bloc(type_bloc=Bloc.CTA),
        Bloc(type_bloc=Bloc.IMAGE),
    ]
    groupes = grouper_blocs(blocs)
    assert groupes[0]["type"] == "section_video"
    assert len(groupes[0]["cartes"]) == 2
    assert groupes[0]["cta"] is not None
    # L'IMAGE qui suit n'est PAS absorbee : groupe solo separe.
    assert groupes[1]["type"] == "solo"


def test_templates_bloc_fallback_classic():
    """templates_bloc renvoie le gabarit du skin courant PUIS le fallback classic."""
    from pages.models import Bloc
    from pages.templatetags.pages_tags import templates_bloc

    bloc = Bloc(type_bloc=Bloc.HERO)
    resultat = templates_bloc({"skin_courant": "faire_festival"}, bloc)
    assert resultat == [
        "pages/faire_festival/partials/bloc_hero.html",
        "pages/classic/partials/bloc_hero.html",
    ]


def test_une_seule_page_accueil(tenant, nettoyer_pages):
    """Cocher est_accueil sur une page decoche les autres (une seule a la fois)."""
    from pages.models import Page

    with tenant_context(tenant):
        page_a = Page.objects.create(
            titre="A", slug="pytest-a", est_accueil=True
        )
        page_b = Page.objects.create(
            titre="B", slug="pytest-b", est_accueil=True
        )

        page_a.refresh_from_db()
        page_b.refresh_from_db()

        assert page_b.est_accueil is True
        assert page_a.est_accueil is False


# ---------------------------------------------------------------------------
# Vue publique / Public view
# ---------------------------------------------------------------------------
def test_page_publiee_est_rendue(tenant, api_client, nettoyer_pages):
    """Une page publiee est servie sur /<slug>/ avec ses blocs."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(
            titre="Page Rendue Pytest", slug="pytest-rendue", publie=True
        )
        Bloc.objects.create(
            page=page, type_bloc=Bloc.HERO, position=1, titre="Mon Hero Pytest"
        )

    reponse = api_client.get("/pytest-rendue/")
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "Page Rendue Pytest" in contenu
    assert "Mon Hero Pytest" in contenu


def test_meta_seo_titre_et_noindex(tenant, api_client, nettoyer_pages):
    """meta_title remplace le <title> et noindex force robots=noindex,nofollow."""
    from pages.models import Page

    with tenant_context(tenant):
        Page.objects.create(
            titre="Titre navigation",
            slug="pytest-seo",
            publie=True,
            meta_title="Titre SEO distinct",
            noindex=True,
        )

    reponse = api_client.get("/pytest-seo/")
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    # Le <title> reprend meta_title (pas le titre de navigation).
    assert "Titre SEO distinct" in contenu
    # noindex demande explicitement par la page.
    assert "noindex, nofollow" in contenu


def test_jsonld_faqpage(tenant, api_client, nettoyer_pages):
    """Une page avec des blocs FAQ emet un JSON-LD WebPage + FAQPage."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Aide", slug="pytest-jsonld", publie=True)
        Bloc.objects.create(
            page=page, type_bloc=Bloc.FAQ, position=1,
            titre="Une question pytest ?", texte="<p>Une reponse pytest.</p>",
        )

    reponse = api_client.get("/pytest-jsonld/")
    contenu = reponse.content.decode()
    assert 'application/ld+json' in contenu
    assert '"FAQPage"' in contenu
    assert "Une question pytest ?" in contenu
    # Le HTML de la reponse est strippe dans le JSON-LD.
    assert "Une reponse pytest." in contenu


def test_sitemap_inclut_pages_publiees(tenant, api_client, nettoyer_pages):
    """Le sitemap liste les pages publiees, exclut brouillon, noindex et accueil."""
    from pages.models import Page

    with tenant_context(tenant):
        Page.objects.create(titre="Visible", slug="pytest-sitemap-ok", publie=True)
        Page.objects.create(titre="Brouillon", slug="pytest-sitemap-draft", publie=False)
        Page.objects.create(
            titre="Cachee", slug="pytest-sitemap-noindex", publie=True, noindex=True
        )

    reponse = api_client.get("/sitemap.xml")
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "pytest-sitemap-ok" in contenu
    assert "pytest-sitemap-draft" not in contenu
    assert "pytest-sitemap-noindex" not in contenu


def test_bloc_evenements_liste_les_a_venir(tenant, api_client, nettoyer_pages):
    """Le bloc EVENEMENTS liste les évènements à venir, jamais les passés."""
    import uuid as uuidlib

    from django.utils import timezone

    from BaseBillet.models import Event
    from pages.models import Bloc, Page

    marqueur = uuidlib.uuid4().hex[:6]
    with tenant_context(tenant):
        Event.objects.create(
            name=f"Evenement futur {marqueur}",
            datetime=timezone.now() + timezone.timedelta(days=3),
        )
        Event.objects.create(
            name=f"Evenement passe {marqueur}",
            datetime=timezone.now() - timezone.timedelta(days=3),
        )
        page = Page.objects.create(titre="Agenda", slug="pytest-evts", publie=True)
        Bloc.objects.create(
            page=page, type_bloc=Bloc.EVENEMENTS, position=1,
            titre="À venir", nombre_max=100,
        )

    try:
        reponse = api_client.get("/pytest-evts/")
        contenu = reponse.content.decode()
        assert "bloc-evenements-liste" in contenu
        assert f"Evenement futur {marqueur}" in contenu
        assert f"Evenement passe {marqueur}" not in contenu
    finally:
        # Base dev live : on supprime les évènements créés.
        # / Live dev DB: delete the events we created.
        with tenant_context(tenant):
            Event.objects.filter(name__endswith=marqueur).delete()


def test_embed_iframe_whitelist():
    """Le tag embed_iframe n'accepte QUE les hôtes en liste blanche (sécurité)."""
    from pages.templatetags.pages_tags import embed_iframe

    # YouTube autorisé -> iframe reconstruit en youtube-nocookie.
    youtube = embed_iframe("https://www.youtube.com/watch?v=aqz-KE-bpKQ")
    assert "youtube-nocookie.com/embed/aqz-KE-bpKQ" in youtube
    assert "<iframe" in youtube
    # youtu.be aussi.
    assert "youtube-nocookie.com/embed/abc123" in embed_iframe("https://youtu.be/abc123")
    # Vimeo autorisé (identifiant numérique).
    assert "player.vimeo.com/video/12345" in embed_iframe("https://vimeo.com/12345")
    # PeerTube : instance AUTORISÉE -> embed reconstruit sur le même hôte.
    peertube = embed_iframe("https://framatube.org/w/abc123")
    assert "framatube.org/videos/embed/abc123" in peertube
    # PeerTube : instance NON autorisée -> rien (fédération non whitelistée).
    assert embed_iframe("https://peertube-pirate.example/w/abc123") == ""
    # Hôtes NON autorisés -> chaîne vide (jamais d'iframe arbitraire).
    assert embed_iframe("https://evil.example.com/x") == ""
    assert embed_iframe("https://notyoutube.com/watch?v=x") == ""
    # Schémas dangereux -> rien.
    assert embed_iframe("javascript:alert(1)") == ""
    assert embed_iframe("data:text/html,<script>alert(1)</script>") == ""
    assert embed_iframe("") == ""
    assert embed_iframe(None) == ""


def test_url_schema_dangereux():
    """L'admin neutralise les URLs à schéma dangereux (anti-XSS au clic)."""
    from pages.admin import _url_a_schema_dangereux

    assert _url_a_schema_dangereux("javascript:alert(1)") is True
    assert _url_a_schema_dangereux("JavaScript:alert(1)") is True
    assert _url_a_schema_dangereux("  java\tscript:x") is True  # obfuscation
    assert _url_a_schema_dangereux("data:text/html,x") is True
    # URLs légitimes (relatives ou http) -> non dangereuses.
    assert _url_a_schema_dangereux("/event/") is False
    assert _url_a_schema_dangereux("https://exemple.fr") is False
    assert _url_a_schema_dangereux("") is False
    assert _url_a_schema_dangereux(None) is False


def test_bloc_galerie_et_faq_repliable(tenant, api_client, nettoyer_pages):
    """La galerie rend sa section ; une FAQ repliable rend un <details>."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Médias", slug="pytest-media", publie=True)
        Bloc.objects.create(page=page, type_bloc=Bloc.GALERIE, position=1, titre="Galerie")
        Bloc.objects.create(
            page=page, type_bloc=Bloc.FAQ, position=2, repliable=True,
            titre="Repliable ?", texte="<p>Oui.</p>",
        )

    reponse = api_client.get("/pytest-media/")
    contenu = reponse.content.decode()
    assert "tb-bloc--galerie" in contenu
    # FAQ repliable -> accordéon natif <details>.
    assert "<details" in contenu


def test_page_non_publiee_renvoie_404(tenant, api_client, nettoyer_pages):
    """Une page en brouillon renvoie 404 pour un visiteur non administrateur."""
    from pages.models import Page

    with tenant_context(tenant):
        Page.objects.create(
            titre="Brouillon Pytest", slug="pytest-brouillon", publie=False
        )

    reponse = api_client.get("/pytest-brouillon/")
    assert reponse.status_code == 404


def test_route_event_non_masquee_par_le_catch_all(api_client):
    """La route specifique /event/ reste prioritaire sur l'attrape-tout /<slug>/."""
    reponse = api_client.get("/event/")
    assert reponse.status_code == 200


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def test_bloc_admin_a_des_conditional_fields():
    """BlocAdmin declare les regles conditionnelles attendues (natif Unfold)."""
    from pages.admin import BlocAdmin

    regles = BlocAdmin.conditional_fields
    # image_position visible uniquement pour le bloc Image + texte
    assert "IMAGE_TEXTE" in regles["image_position"]
    # auteur_nom visible uniquement pour le temoignage
    assert "TEMOIGNAGE" in regles["auteur_nom"]
    # sous_titre partage par Hero et CTA (test du .includes)
    assert "HERO" in regles["sous_titre"] and "CTA" in regles["sous_titre"]


def test_changelist_pages_accessible_admin(admin_client):
    """La liste des pages est accessible dans l'admin Unfold."""
    url = reverse("staff_admin:pages_page_changelist")
    reponse = admin_client.get(url)
    assert reponse.status_code == 200


def test_texte_du_bloc_est_nettoye(tenant):
    """sanitize_textfields (clean_html) retire les balises dangereuses du texte."""
    from Administration.admin.site import sanitize_textfields
    from pages.models import Bloc

    bloc = Bloc(
        type_bloc=Bloc.PARAGRAPHE,
        texte="<p>Bonjour</p><script>alert('xss')</script>",
    )
    sanitize_textfields(bloc)
    assert "<script>" not in bloc.texte
    assert "Bonjour" in bloc.texte
