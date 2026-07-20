"""
Tests de la migration du site vitrine « Coopérative Code Commun » vers le moteur
pages. / Tests of the "Coopérative Code Commun" showcase migration to the pages engine.

LOCALISATION : tests/pytest/test_site_codecommun.py

Ces tests sont RAPIDES et sans base : ils valident la cohérence des slugs et la
réécriture des liens, PAS le chargement complet (qui uploade ~90 images et se
vérifie à la main, cf. le CHANGELOG). Le test central verrouille l'ancrage des
routes core : un `re_path` privé de son « ^ » capture n'importe quel slug qui
contient son token, et la Page devient introuvable.
/ These tests are FAST and DB-free: they check slug consistency and link
rewriting, NOT the full load. The central test locks down core-route anchoring:
a `re_path` missing its "^" swallows any slug containing its token.
"""

from pages.fixtures.site_codecommun.manifest import CATEGORIES
from pages.management.commands import charger_site_codecommun as module_commande
from pages.models import SLUGS_RESERVES

CommandeSiteCodecommun = module_commande.Command

# Tokens des routes core montées en `re_path` dans TiBillet/urls_tenants.py.
# Ces routes sont ANCRÉES (`^token/`) : un slug qui se termine par l'un d'eux est
# donc parfaitement valide, et c'est exactement ce que verrouille le test
# ci-dessous. / Tokens of the core routes mounted with `re_path`. Those routes
# are ANCHORED, so a slug ending with one of them is perfectly valid — which is
# what the test below locks down.
TOKENS_DE_ROUTES_CORE = (
    "fedow",
    "fwh",
    "api",
    "rss",
    "logout",
    "crowd",
    "contrib",
    "newsletter",
)


def _tous_les_slugs():
    """
    Reconstruit l'ensemble des slugs que la commande va créer : accueil, tibillet
    (fusion), les pages-index de catégorie, et chaque enfant (slug lu dans le
    frontmatter du .md). / Rebuilds every slug the command will create.
    """
    commande = CommandeSiteCodecommun()
    # accueil, tibillet et services sont des pages de 1er niveau construites hors
    # CATEGORIES (fusion / inline). / Home, tibillet and services are top-level
    # pages built outside CATEGORIES.
    slugs = ["accueil", "tibillet", "services"]
    for categorie in CATEGORIES:
        slugs.append(categorie["slug"])
        for fichier in categorie["enfants"]:
            chemin = module_commande.FIXTURES / categorie["dossier"] / fichier
            frontmatter, _corps = commande._lire_markdown(chemin)
            slugs.append(frontmatter.get("slug") or fichier)
    return slugs


def test_tous_les_slugs_sont_uniques():
    """Le moteur sert tout à plat sur /<slug>/ : deux pages ne peuvent pas partager
    un slug. / The engine serves everything flat on /<slug>/: no shared slug."""
    slugs = _tous_les_slugs()
    doublons = {slug for slug in slugs if slugs.count(slug) > 1}
    assert not doublons, f"Slugs en double : {doublons}"


def test_les_routes_core_sont_ancrees_et_ne_capturent_pas_un_slug_de_page():
    """
    Régression : les `re_path` de TiBillet/urls_tenants.py doivent rester
    ancrés par « ^ ».

    Django applique le motif d'un `re_path` avec `re.search()` : sans « ^ », un
    motif comme `r'crowd/'` matche N'IMPORTE OU dans le chemin. « /notre-crowd/ »
    partait alors vers l'app crowds, et « /guide-newsletter/ » renvoyait un 403 —
    la Page devenait introuvable, en silence, sans que rien n'ait prévenu la
    personne qui l'avait créée.

    On vérifie le COMPORTEMENT (où mène l'URL) et non le texte du fichier : c'est
    ce qui compte, et ça reste vrai si les routes sont réorganisées.
    / Regression: the `re_path` routes must stay anchored with "^". Django
    matches them with `re.search()`, so an unanchored pattern captures the path
    anywhere. We assert the BEHAVIOUR (where the URL leads), not the file text.
    """
    from django.test import override_settings
    from django.urls import resolve

    with override_settings(ROOT_URLCONF="TiBillet.urls_tenants"):
        for token in TOKENS_DE_ROUTES_CORE:
            correspondance = resolve(f"/notre-{token}/")
            assert correspondance.func.__module__.startswith("pages."), (
                f"L'URL '/notre-{token}/' est partie vers "
                f"'{correspondance.func.__module__}' au lieu du moteur de pages : "
                f"la route re_path('{token}/') a perdu son « ^ » et capture "
                f"maintenant n'importe quel slug contenant '{token}/'."
            )


def test_aucun_slug_reserve():
    """Aucun slug produit ne doit heurter un slug réservé par le site.
    / No produced slug may collide with a site-reserved slug."""
    slugs = _tous_les_slugs()
    collisions = set(slugs) & SLUGS_RESERVES
    assert not collisions, f"Slugs réservés utilisés : {collisions}"


def test_reecriture_des_liens_internes():
    """
    Les liens Docusaurus internes sont réécrits vers /<slug>/ : les fiches Créations
    fusionnées pointent vers /tibillet/, et l'article Fédération 5 renommé vers
    /federation-part5/. / Internal Docusaurus links are rewritten to /<slug>/.
    """
    commande = CommandeSiteCodecommun()
    # On construit la table de remplacement à partir des slugs réels du site.
    # / Build the replacement table from the real site slugs.
    pages_prevues = {}
    for categorie in CATEGORIES:
        for fichier in categorie["enfants"]:
            chemin = module_commande.FIXTURES / categorie["dossier"] / fichier
            frontmatter, _corps = commande._lire_markdown(chemin)
            pages_prevues[fichier] = {"slug": frontmatter.get("slug") or fichier}
    remplacements = commande._construire_remplacements_liens(pages_prevues)

    # Fiches Créations fusionnées -> /tibillet/ (y compris le segment /Creations).
    # / Merged Créations pages -> /tibillet/.
    assert (
        commande._reecrire_liens(
            "voir [la caisse](https://codecommun.coop/docs/Creations/tibillet-laboutik)",
            remplacements,
        )
        == "voir [la caisse](/tibillet/)"
    )

    # Article de blog renommé (fedow retiré du slug) -> /federation-part5/.
    # / Renamed blog article -> /federation-part5/.
    assert (
        commande._reecrire_liens(
            "cf [FEDOW](/blog/federation-part5-fedow/)",
            remplacements,
        )
        == "cf [FEDOW](/federation-part5/)"
    )

    # Lien vers une page conservée (docs -> slug plat).
    # / Link to a kept page (docs -> flat slug).
    assert (
        commande._reecrire_liens(
            "la [charte](/docs/charte)",
            remplacements,
        )
        == "la [charte](/charte/)"
    )

    # Fiche « hebergement » inlinée dans /services/.
    # / "hebergement" doc inlined into /services/.
    assert (
        commande._reecrire_liens(
            "voir l'[hébergement](/docs/hebergement)",
            remplacements,
        )
        == "voir l'[hébergement](/services/)"
    )
