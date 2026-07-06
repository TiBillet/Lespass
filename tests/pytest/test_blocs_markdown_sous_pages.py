"""
Tests des blocs MARKDOWN et LISTE_SOUS_PAGES (CHANTIER-09).
/ Tests of the MARKDOWN and LISTE_SOUS_PAGES blocks (CHANTIER-09).

LOCALISATION : tests/pytest/test_blocs_markdown_sous_pages.py

Pattern : base dev live (pas de rollback). Chaque test cree puis supprime ses
donnees ; slugs prefixes "pytest-" (fixture nettoyer_pages de test_pages).
/ Pattern: live dev DB (no rollback). Each test creates then deletes its data;
"pytest-" slug prefix (nettoyer_pages fixture from test_pages).
"""
import pytest
from django_tenants.utils import tenant_context

from tests.pytest.test_pages import nettoyer_pages  # noqa: F401 (fixture)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Filtre rendre_markdown / rendre_markdown filter
# ---------------------------------------------------------------------------
def test_rendre_markdown_convertit_le_markdown_en_html():
    """Titres, gras et listes Markdown deviennent du HTML — et les titres sont
    DÉMOTÉS d'un niveau (# devient h2) : le h1 appartient à la Page, jamais au
    contenu markdown (audit SEO 2026-07-05)."""
    from pages.templatetags.pages_tags import rendre_markdown

    html = rendre_markdown("# Mon titre\n\nDu **gras** et une liste :\n\n- un\n- deux")
    # '# ' -> h2 (démotion), jamais de h1 dans le contenu markdown.
    # / '# ' -> h2 (demotion), never an h1 inside markdown content.
    assert "<h2>Mon titre</h2>" in html
    assert "<h1>" not in html
    assert "<strong>gras</strong>" in html
    assert "<li>un</li>" in html


def test_rendre_markdown_neutralise_les_xss():
    """Le HTML dangereux injecte dans la source Markdown est neutralise (nh3)."""
    from pages.templatetags.pages_tags import rendre_markdown

    html = rendre_markdown(
        'Avant <script>alert("xss")</script> '
        '<img src="x" onerror="alert(1)"> '
        '[lien](javascript:alert(2)) apres'
    )
    assert "<script" not in html
    assert "onerror" not in html
    assert "javascript:" not in html
    # Le contenu legitime autour survit. / Legit surrounding content survives.
    assert "Avant" in html and "apres" in html


def test_rendre_markdown_texte_vide():
    """Une source vide ou None rend une chaine vide (pas d'erreur)."""
    from pages.templatetags.pages_tags import rendre_markdown

    assert rendre_markdown("") == ""
    assert rendre_markdown(None) == ""


def test_rendre_bloc_markdown_resout_les_references_galerie(tenant, nettoyer_pages):  # noqa: F811
    """Les références ![..](galerie:N) sont résolues vers les images de
    l'inline du bloc ; alt vide -> légende ; référence inconnue -> laissée
    telle quelle (l'auteur voit son erreur)."""
    import base64

    from django.core.files.uploadedfile import SimpleUploadedFile

    from pages.models import Bloc, ImageGalerie, Page
    from pages.templatetags.pages_tags import rendre_bloc_markdown

    # PNG 1x1 valide (le plus petit possible). / Smallest valid 1x1 PNG.
    png_minuscule = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBg"
        "AAAABQABh6FO1AAAAABJRU5ErkJggg=="
    )

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest MD img", slug="pytest-md-img", publie=True)
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.MARKDOWN, position=1,
            texte=(
                "Avant ![La fresque](galerie:1) milieu "
                "![](galerie:2) après ![oubli](galerie:9)"
            ),
        )
        illustration_1 = ImageGalerie.objects.create(bloc=bloc, position=1, legende="Une")
        illustration_1.image.save("pytest-md-1.png", SimpleUploadedFile("p1.png", png_minuscule), save=True)
        illustration_2 = ImageGalerie.objects.create(bloc=bloc, position=2, legende="Fallback légende")
        illustration_2.image.save("pytest-md-2.png", SimpleUploadedFile("p2.png", png_minuscule), save=True)

        html = rendre_bloc_markdown(bloc)

        # Réf 1 : résolue, alt de l'auteur conservé. / Ref 1: resolved, author alt kept.
        assert 'alt="La fresque"' in html and "galerie:1" not in html
        # Réf 2 : alt vide -> légende de l'inline. / Ref 2: empty alt -> caption.
        assert 'alt="Fallback légende"' in html
        # Réf 9 : inconnue -> marqueur texte visible. / Ref 9: visible marker.
        assert "image galerie:9 introuvable" in html

        # Nettoyage des fichiers uploadés. / Uploaded files cleanup.
        for illustration in (illustration_1, illustration_2):
            illustration.image.delete(save=False)


def test_fil_ariane_sans_lien_vers_parent_brouillon(tenant, api_client, nettoyer_pages):  # noqa: F811
    """Un parent DÉPUBLIÉ ne produit ni lien visible ni maillon JSON-LD dans le
    fil d'ariane de sa sous-page (sinon lien → 404)."""
    from pages.models import Page

    with tenant_context(tenant):
        brouillon = Page.objects.create(
            titre="Pytest Parent Brouillon", slug="pytest-parent-brouillon", publie=False
        )
        enfant = Page.objects.create(
            titre="Pytest Enfant Visible", slug="pytest-enfant-visible", publie=True,
            parent=brouillon,
        )

    html = api_client.get("/pytest-enfant-visible/").content.decode()
    # Ni lien visible ni maillon structuré vers le brouillon.
    # / No visible link nor structured crumb to the draft.
    assert 'href="/pytest-parent-brouillon/"' not in html
    assert "Pytest Parent Brouillon" not in html
    # Le fil d'ariane existe quand même (Accueil › page).
    # / The breadcrumb still exists (Home › page).
    assert "tb-fil-ariane" in html

    with tenant_context(tenant):
        # Parent PUBLIÉ : le maillon revient. / PUBLISHED parent: crumb is back.
        brouillon.publie = True
        brouillon.save()
    html = api_client.get("/pytest-enfant-visible/").content.decode()
    assert 'href="/pytest-parent-brouillon/"' in html


# ---------------------------------------------------------------------------
# Tag sous_pages_publiees / sous_pages_publiees tag
# ---------------------------------------------------------------------------
def test_sous_pages_publiees_liste_les_enfants_publies(tenant, nettoyer_pages):  # noqa: F811
    """Seules les sous-pages PUBLIEES sortent, triees par position puis titre,
    et nombre_max est respecte."""
    from pages.models import Page
    from pages.templatetags.pages_tags import sous_pages_publiees

    with tenant_context(tenant):
        parent = Page.objects.create(titre="Blog", slug="pytest-blog", publie=True)
        Page.objects.create(titre="Article B", slug="pytest-art-b", publie=True,
                            parent=parent, position=2)
        Page.objects.create(titre="Article A", slug="pytest-art-a", publie=True,
                            parent=parent, position=1)
        Page.objects.create(titre="Brouillon", slug="pytest-brouillon", publie=False,
                            parent=parent, position=0)

        titres = [p.titre for p in sous_pages_publiees(parent, 6)]
        assert titres == ["Article A", "Article B"]  # brouillon exclu, tri position

        # nombre_max limite la liste. / nombre_max caps the list.
        assert len(sous_pages_publiees(parent, 1)) == 1
        # Page sans parent fourni : liste vide, pas d'erreur.
        assert sous_pages_publiees(None) == []


# ---------------------------------------------------------------------------
# Rendu complet via la vue publique / Full render through the public view
# ---------------------------------------------------------------------------
def test_page_blog_rend_markdown_et_sous_pages(tenant, api_client, nettoyer_pages):  # noqa: F811
    """Une page « blog » (bloc LISTE_SOUS_PAGES) et un article (bloc MARKDOWN)
    se rendent de bout en bout sur /<slug>/."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        # est_blog=True : typage EXPLICITE (le bloc LISTE_SOUS_PAGES est de la
        # présentation pure et ne type rien). / est_blog=True: EXPLICIT typing
        # (the LISTE_SOUS_PAGES block is presentation only, it types nothing).
        index_blog = Page.objects.create(
            titre="Pytest Blog", slug="pytest-blog-index", publie=True, est_blog=True
        )
        Bloc.objects.create(
            page=index_blog, type_bloc=Bloc.LISTE_SOUS_PAGES, position=1,
            titre="Derniers articles", nombre_max=6,
        )
        article = Page.objects.create(
            titre="Pytest Article Un", slug="pytest-article-un", publie=True,
            parent=index_blog, meta_description="Le premier article de test.",
        )
        Bloc.objects.create(
            page=article, type_bloc=Bloc.MARKDOWN, position=1,
            texte="## Sous-titre markdown\n\nParagraphe avec du **gras**.",
        )

    # L'index liste l'article en carte. / The index lists the article card.
    contenu_index = api_client.get("/pytest-blog-index/").content.decode()
    assert "Pytest Article Un" in contenu_index
    assert "/pytest-article-un/" in contenu_index
    assert "Le premier article de test." in contenu_index

    # L'article rend le Markdown en HTML — '##' devient h3 (démotion d'un
    # niveau) et le h1 de la page est le titre de secours de page.html.
    # / The article renders MD as HTML — '##' becomes h3 (one-level demotion)
    # and the page's h1 is page.html's fallback title.
    contenu_article = api_client.get("/pytest-article-un/").content.decode()
    assert "<h3>Sous-titre markdown</h3>" in contenu_article
    assert "<strong>gras</strong>" in contenu_article
    assert contenu_article.count("<h1") == 1  # le titre de secours / fallback title
    assert "Pytest Article Un" in contenu_article

    # SEO article (E-E-A-T) : la sous-page d'un index de blog émet un JSON-LD
    # Article (datePublished + author Organization) et affiche la signature
    # date/auteur ; l'index lui-même reste une WebPage sans signature.
    # / Article SEO (E-E-A-T): a blog-index sub-page emits an Article JSON-LD
    # (datePublished + Organization author) and shows the visible byline;
    # the index itself stays a WebPage without a byline.
    import json as json_lib
    import re as re_lib
    types_articles = []
    for bloc_jsonld in re_lib.findall(
        r'<script type="application/ld\+json">(.*?)</script>', contenu_article, re_lib.S
    ):
        donnees = json_lib.loads(bloc_jsonld)  # doit être du JSON valide / must parse
        for noeud in donnees.get("@graph", [donnees]):
            types_articles.append(noeud.get("@type"))
            if noeud.get("@type") == "Article":
                assert noeud["datePublished"]
                assert noeud["author"]["@type"] == "Organization"
    assert "Article" in types_articles
    assert 'data-testid="page-signature"' in contenu_article
    assert 'data-testid="page-signature"' not in contenu_index
