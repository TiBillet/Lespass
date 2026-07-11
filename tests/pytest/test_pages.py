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
        # nombre_max TRES haut : la base dev est VIVANTE et accumule les
        # evenements des suites E2E (200+ futurs observes le 2026-07-05).
        # Avec nombre_max=100, l'evenement du test (+3 jours) se classait
        # au-dela du slice [:100] du tag evenements_a_venir et le test
        # echouait selon l'etat de la base. 32000 = deterministe.
        # / Very high nombre_max: the dev DB is LIVE and accumulates events
        # from the E2E suites (200+ upcoming observed). With nombre_max=100
        # the test event (+3 days) could rank beyond the [:100] slice and the
        # test failed depending on DB state. 32000 = deterministic.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.EVENEMENTS, position=1,
            titre="À venir", nombre_max=32000,
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
    from Administration.utils import url_a_schema_dangereux

    assert url_a_schema_dangereux("javascript:alert(1)") is True
    assert url_a_schema_dangereux("JavaScript:alert(1)") is True
    assert url_a_schema_dangereux("  java\tscript:x") is True  # obfuscation
    assert url_a_schema_dangereux("data:text/html,x") is True
    # URLs légitimes (relatives ou http) -> non dangereuses.
    assert url_a_schema_dangereux("/event/") is False
    assert url_a_schema_dangereux("https://exemple.fr") is False
    assert url_a_schema_dangereux("") is False
    assert url_a_schema_dangereux(None) is False


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


def test_page_hierarchie_un_seul_niveau(tenant, nettoyer_pages):
    """La hiérarchie parent/enfant est limitée à UN niveau (validé par clean)."""
    from pages.models import Page

    with tenant_context(tenant):
        parent = Page.objects.create(titre="Parent", slug="pytest-parent")
        enfant = Page.objects.create(titre="Enfant", slug="pytest-enfant", parent=parent)

        # Un petit-enfant (enfant d'un enfant) est refusé.
        petit = Page(titre="Petit", slug="pytest-petit", parent=enfant)
        with pytest.raises(ValidationError):
            petit.full_clean()

        # Une page qui a déjà des sous-pages ne peut pas devenir elle-même enfant.
        autre = Page.objects.create(titre="Autre", slug="pytest-autre")
        parent.parent = autre
        with pytest.raises(ValidationError):
            parent.full_clean()

        # L'accueil ne peut pas être une sous-page.
        acc = Page(titre="Acc", slug="pytest-acc", est_accueil=True, parent=autre)
        with pytest.raises(ValidationError):
            acc.full_clean()


def test_jsonld_breadcrumb_sous_page(tenant, api_client, nettoyer_pages):
    """Une sous-page émet un BreadcrumbList JSON-LD + un fil d'Ariane visible."""
    from pages.models import Page

    with tenant_context(tenant):
        parent = Page.objects.create(titre="Le lieu pytest", slug="pytest-bc-parent", publie=True)
        Page.objects.create(
            titre="La salle pytest", slug="pytest-bc-enfant", publie=True, parent=parent
        )

    reponse = api_client.get("/pytest-bc-enfant/")
    contenu = reponse.content.decode()
    assert '"BreadcrumbList"' in contenu
    assert "Le lieu pytest" in contenu      # le parent dans le fil d'Ariane
    assert "tb-fil-ariane" in contenu        # fil d'Ariane visible (classic)


def test_navbar_dropdown_sous_pages(tenant, api_client, nettoyer_pages):
    """Une page avec des sous-pages publiées rend un menu déroulant dans la navbar."""
    from pages.models import Page

    with tenant_context(tenant):
        parent = Page.objects.create(titre="Parent nav", slug="pytest-navparent", publie=True)
        Page.objects.create(
            titre="Sous-page nav", slug="pytest-navenfant", publie=True, parent=parent
        )

    reponse = api_client.get("/pytest-navparent/")
    contenu = reponse.content.decode()
    assert "dropdown-menu" in contenu
    assert "Sous-page nav" in contenu        # le libellé de la sous-page dans le menu


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


# ---------------------------------------------------------------------------
# construire_page_accueil (home auto-generee : HERO -> PARAGRAPHE -> CTA)
# / construire_page_accueil (auto home: HERO -> PARAGRAPH -> CTA)
# ---------------------------------------------------------------------------
def test_construire_page_accueil_hero_paragraphe_cta(tenant, nettoyer_pages):
    """
    Home auto : HERO(1) sans image ni boutons, PARAGRAPHE(2) avec la description
    PASSEE (pas celle de config), CTA(3) avec les 2 boutons module-aware.
    / Auto home: HERO(1) with no image/buttons, PARAGRAPH(2) with the PASSED
    description (not config's), CTA(3) with both module-aware buttons.
    """
    from types import SimpleNamespace

    from pages.models import Bloc, Page
    from pages.services import construire_page_accueil

    # Config factice : les deux modules actifs, pas de libelle de menu custom.
    # / Fake config: both modules active, no custom menu labels.
    config = SimpleNamespace(
        organisation="Lieu Pytest",
        short_description="Court pytest",
        long_description="NE DOIT PAS SERVIR",
        module_billetterie=True,
        module_adhesion=True,
        event_menu_name="",
        membership_menu_name="",
    )

    with tenant_context(tenant):
        # On libere l'etat d'accueil pour que la fonction idempotente s'execute.
        # / Free the home state so the idempotent function actually runs.
        homes = list(
            Page.objects.filter(est_accueil=True).values_list("pk", flat=True)
        )
        Page.objects.filter(pk__in=homes).update(est_accueil=False)

        page = None
        try:
            page = construire_page_accueil(
                Page, Bloc, config, description_longue="<p>Ma description longue</p>"
            )
            assert page is not None

            blocs = list(page.blocs.order_by("position"))
            assert [b.type_bloc for b in blocs] == ["HERO", "PARAGRAPHE", "CTA"]

            # HERO : titre + sous-titre, PAS d'image ni de boutons.
            # / HERO: title + subtitle, NO image, NO buttons.
            hero = blocs[0]
            assert hero.titre == "Lieu Pytest"
            assert hero.sous_titre == "Court pytest"
            assert not hero.image
            assert not hero.bouton_label
            assert not hero.bouton2_label

            # PARAGRAPHE : la description PASSEE, pas le long_description de config.
            # / PARAGRAPH: the PASSED description, not config's long_description.
            para = blocs[1]
            assert "Ma description longue" in para.texte
            assert "NE DOIT PAS SERVIR" not in para.texte

            # CTA : agenda en principal, adhesions en second (memes URL que la navbar).
            # / CTA: calendar primary, memberships second (same URLs as the navbar).
            cta = blocs[2]
            assert cta.bouton_url == "/event/"
            assert cta.bouton2_url == "/memberships/"
        finally:
            if page is not None:
                page.delete()


def test_construire_page_accueil_sans_desc_longue_paragraphe_vide(tenant, nettoyer_pages):
    """
    Sans description longue : le bloc PARAGRAPHE est quand meme cree (texte vide),
    pour pouvoir etre rempli plus tard. Un seul module actif (adhesion) : le CTA
    n'a qu'un bouton principal.
    / No long description: the PARAGRAPH block is still created (empty text) so it
    can be filled later. A single active module (membership): CTA has only a
    primary button.
    """
    from types import SimpleNamespace

    from pages.models import Bloc, Page
    from pages.services import construire_page_accueil

    config = SimpleNamespace(
        organisation="X pytest",
        short_description="",
        long_description="hardcode ignore",
        module_billetterie=False,
        module_adhesion=True,
        event_menu_name="",
        membership_menu_name="",
    )

    with tenant_context(tenant):
        homes = list(
            Page.objects.filter(est_accueil=True).values_list("pk", flat=True)
        )
        Page.objects.filter(pk__in=homes).update(est_accueil=False)

        page = None
        try:
            # description_longue="" (chaine vide) = onboarding sans saisie.
            # / empty string = onboarding with no input.
            page = construire_page_accueil(Page, Bloc, config, description_longue="")
            blocs = list(page.blocs.order_by("position"))
            types = [b.type_bloc for b in blocs]
            # Le PARAGRAPHE est present meme vide.
            # / The PARAGRAPH is present even when empty.
            assert types == ["HERO", "PARAGRAPHE", "CTA"]
            assert blocs[1].texte == ""

            # Seul le module adhesion est actif -> bouton principal = adhesions.
            # / Only the membership module is active -> primary button = memberships.
            cta = page.blocs.get(type_bloc="CTA")
            assert cta.bouton_url == "/memberships/"
            assert not cta.bouton2_label
        finally:
            if page is not None:
                page.delete()


# ---------------------------------------------------------------------------
# CHANTIER 06 — Blocs IFRAME + PARTENAIRES
# ---------------------------------------------------------------------------
def test_creation_bloc_iframe(tenant, nettoyer_pages):
    """Un bloc IFRAME se cree avec embed_url + hauteur_px."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Iframe", slug="pytest-iframe")
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.IFRAME,
            embed_url="https://newsletter.ghost.io/abonnement",
            hauteur_px=500,
        )
        assert bloc.type_bloc == "IFRAME"
        assert bloc.hauteur_px == 500


def test_hauteur_px_bornee(tenant, nettoyer_pages):
    """hauteur_px hors bornes (100..4000) est rejetee au full_clean()."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Iframe H", slug="pytest-iframe-h")
        bloc = Bloc(page=page, type_bloc=Bloc.IFRAME, hauteur_px=50)
        with pytest.raises(ValidationError) as exc:
            bloc.full_clean()
        assert "hauteur_px" in exc.value.error_dict


def test_image_galerie_lien_url_ok(tenant, nettoyer_pages):
    """Une ImageGalerie accepte un lien_url http(s) normal."""
    from pages.models import Bloc, ImageGalerie, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Part", slug="pytest-part")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.PARTENAIRES)
        img = ImageGalerie(bloc=bloc, lien_url="https://partenaire.example/", position=1)
        img.full_clean()  # ne leve pas
        img.save()
        assert img.lien_url == "https://partenaire.example/"


def test_image_galerie_lien_url_dangereux_rejete(tenant, nettoyer_pages):
    """lien_url = javascript:... est rejete au full_clean() (anti-XSS)."""
    from pages.models import Bloc, ImageGalerie, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Part X", slug="pytest-part-x")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.PARTENAIRES)
        img = ImageGalerie(bloc=bloc, lien_url="javascript:alert(1)", position=1)
        with pytest.raises(ValidationError):
            img.full_clean()


def test_rootconfig_champ_whitelist(tenant):
    """RootConfiguration porte domaines_embed_autorises (lisible depuis un tenant)."""
    from root_billet.models import RootConfiguration

    with tenant_context(tenant):
        config = RootConfiguration.get_solo()
        assert hasattr(config, "domaines_embed_autorises")


def _set_whitelist_embed(valeur):
    """Pose la whitelist ROOT + vide le cache django-solo (scope par schema)."""
    from django.core.cache import cache
    from root_billet.models import RootConfiguration

    config = RootConfiguration.get_solo()
    config.domaines_embed_autorises = valeur
    config.save()
    cache.clear()


@pytest.fixture
def whitelist_embed(tenant):
    """Sauvegarde/restaure domaines_embed_autorises autour d'un test."""
    from root_billet.models import RootConfiguration

    with tenant_context(tenant):
        avant = RootConfiguration.get_solo().domaines_embed_autorises
    yield
    with tenant_context(tenant):
        _set_whitelist_embed(avant)


def test_iframe_libre_hote_autorise(tenant, whitelist_embed):
    """Hote whiteliste + https -> <iframe> avec le src fourni et la hauteur."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        html = iframe_libre("https://newsletter.ghost.io/abo", 480)
        assert "<iframe" in html
        assert "https://newsletter.ghost.io/abo" in html
        assert 'height="480"' in html
        assert "sandbox=" in html


def test_iframe_libre_hote_refuse(tenant, whitelist_embed):
    """Hote absent de la whitelist -> chaine vide (jamais d'iframe arbitraire)."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        assert iframe_libre("https://evil.example/x", 480) == ""


def test_iframe_libre_refuse_http(tenant, whitelist_embed):
    """Schema http (hote pourtant whiteliste) -> chaine vide."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        assert iframe_libre("http://newsletter.ghost.io/abo", 480) == ""


def test_iframe_libre_url_vide(tenant, whitelist_embed):
    """URL vide/invalide -> chaine vide (pas de crash)."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        assert iframe_libre("", 480) == ""
        assert iframe_libre(None, 480) == ""


def test_iframe_libre_whitelist_normalisee(tenant, whitelist_embed):
    """La whitelist tolere schema/slash/casse/lignes vides."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("  https://Newsletter.Ghost.IO/  \n\n autre.example \n")
        assert "<iframe" in iframe_libre("https://newsletter.ghost.io/abo", 480)
        assert "<iframe" in iframe_libre("https://autre.example/form", 480)


def test_get_inlines_partenaires(tenant, nettoyer_pages):
    """L'inline ImageGalerie apparait pour un bloc PARTENAIRES."""
    from django.test import RequestFactory

    from Administration.admin.site import staff_admin_site
    from pages.admin import BlocAdmin, ImageGalerieInline
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Adm", slug="pytest-adm")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.PARTENAIRES)
        admin = BlocAdmin(Bloc, staff_admin_site)
        request = RequestFactory().get("/")
        inlines = admin.get_inlines(request, bloc)
        assert ImageGalerieInline in inlines


def test_conditional_fields_nouveaux_types():
    """titre visible pour IFRAME/PARTENAIRES ; hauteur_px pour IFRAME."""
    from Administration.admin.site import staff_admin_site
    from pages.admin import BlocAdmin
    from pages.models import Bloc

    admin = BlocAdmin(Bloc, staff_admin_site)
    assert "IFRAME" in admin.conditional_fields["titre"]
    assert "PARTENAIRES" in admin.conditional_fields["titre"]
    assert admin.conditional_fields["hauteur_px"] == "type_bloc == 'IFRAME'"
    assert "IFRAME" in admin.conditional_fields["embed_url"]
    assert "hauteur_px" in admin.fields


def test_rootconfig_admin_superadmin_strict(tenant):
    """RootConfigurationAdmin : perms reservees au superadmin (is_superuser)."""
    from django.test import RequestFactory

    from Administration.admin.site import staff_admin_site
    from Administration.admin_tenant import RootConfigurationAdmin
    from root_billet.models import RootConfiguration

    admin = RootConfigurationAdmin(RootConfiguration, staff_admin_site)
    request = RequestFactory().get("/")

    class _User:
        is_superuser = False
    request.user = _User()
    assert admin.has_view_permission(request) is False
    request.user.is_superuser = True
    assert admin.has_view_permission(request) is True
    assert list(admin.get_fields(request)) == ["domaines_embed_autorises"]


def test_rendu_bloc_iframe(tenant, whitelist_embed, nettoyer_pages):
    """bloc_iframe : hote autorise -> <iframe> ; hote refuse -> message honnete."""
    from django.template.loader import render_to_string

    from pages.models import Bloc, Page

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        page = Page.objects.create(titre="Pytest Rif", slug="pytest-rif")
        bloc_ok = Bloc.objects.create(
            page=page, type_bloc=Bloc.IFRAME,
            embed_url="https://newsletter.ghost.io/abo", hauteur_px=400,
        )
        html_ok = render_to_string("pages/classic/partials/bloc_iframe.html", {"bloc": bloc_ok})
        assert "<iframe" in html_ok
        assert 'data-testid="bloc-iframe"' in html_ok

        bloc_ko = Bloc.objects.create(
            page=page, type_bloc=Bloc.IFRAME,
            embed_url="https://evil.example/x", hauteur_px=400,
        )
        html_ko = render_to_string("pages/classic/partials/bloc_iframe.html", {"bloc": bloc_ko})
        assert "<iframe" not in html_ko
        assert ("hote non autoris" in html_ko.lower()) or ("host" in html_ko.lower())


def test_rendu_bloc_partenaires_lien(tenant, nettoyer_pages):
    """bloc_partenaires : conteneur + testid rendus (logo cliquable teste en Chrome)."""
    from django.template.loader import render_to_string

    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Rpart", slug="pytest-rpart")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.PARTENAIRES)
        html = render_to_string("pages/classic/partials/bloc_partenaires.html", {"bloc": bloc})
        assert 'data-testid="bloc-partenaires"' in html


def test_rendu_bloc_newsletter(tenant, nettoyer_pages):
    """bloc_newsletter : script Ghost VENDORISÉ + data-site = embed_url ; vide si pas d'URL."""
    from django.template.loader import render_to_string

    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest News", slug="pytest-news")
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.NEWSLETTER,
            embed_url="https://ghost.tibillet.coop/",
            titre="Les news de TiBillet",
            sous_titre="La boite a outils d'organisation collective",
        )
        html = render_to_string("pages/classic/partials/bloc_newsletter.html", {"bloc": bloc})
        # Script servi en LOCAL (vendorisé), pas depuis un CDN.
        assert "pages/vendor/ghost/signup-form.min.js" in html
        assert "cdn.jsdelivr.net" not in html
        assert 'data-site="https://ghost.tibillet.coop/"' in html
        assert 'data-testid="bloc-newsletter"' in html

        # Sans URL d'instance -> aucune section rendue.
        bloc_vide = Bloc.objects.create(page=page, type_bloc=Bloc.NEWSLETTER, embed_url="")
        html_vide = render_to_string("pages/classic/partials/bloc_newsletter.html", {"bloc": bloc_vide})
        assert "bloc-newsletter" not in html_vide
