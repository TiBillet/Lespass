"""
Tests de la migration du site vitrine « Coopérative Code Commun » vers le moteur
pages. / Tests of the "Coopérative Code Commun" showcase migration to the pages engine.

LOCALISATION : tests/pytest/test_site_codecommun.py

Ces tests sont RAPIDES et sans base : ils valident la cohérence des slugs et la
réécriture des liens, PAS le chargement complet (qui uploade ~90 images et se
vérifie à la main, cf. le CHANGELOG). Le test central verrouille la classe de bug
rencontrée pendant la migration : un slug se terminant par un token de route core
NON ANCRÉE (re_path('fedow/'), re_path('api/')...) est capté par cette route et
renvoie un 403 au lieu de la page. / These tests are FAST and DB-free: they check
slug consistency and link rewriting, NOT the full load. The central test guards the
bug found during migration: a slug ending with an UNANCHORED core-route token
(re_path('fedow/'), ...) is swallowed by that route and returns 403.
"""

from pages.fixtures.site_codecommun.manifest import CATEGORIES
from pages.management.commands import charger_site_codecommun as module_commande
from pages.models import SLUGS_RESERVES

CommandeSiteCodecommun = module_commande.Command

# Tokens des routes core NON ANCRÉES de TiBillet/urls_tenants.py (re_path sans ^).
# Un slug qui se TERMINE par l'un d'eux verrait /<slug>/ capté par la route (la
# route matche « token/ » n'importe où via .search()) -> 403. / Tokens of the
# UNANCHORED core routes: a slug ENDING with one of them would 403.
TOKENS_ROUTES_NON_ANCREES = (
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


def test_aucun_slug_ne_finit_par_un_token_de_route_non_ancree():
    """
    Régression : aucun slug ne doit se terminer par un token de route core non
    ancrée (sinon 403). C'est ce qui bloquait « tibillet-fedow » et
    « federation-part5-fedow » pendant la migration.
    / Regression: no slug may end with an unanchored core-route token (else 403).
    """
    slugs = _tous_les_slugs()
    for slug in slugs:
        for token in TOKENS_ROUTES_NON_ANCREES:
            assert not slug.endswith(token), (
                f"Le slug '{slug}' se termine par '{token}' : la route core "
                f"re_path('{token}/') le capterait -> 403. Renommer le slug."
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
