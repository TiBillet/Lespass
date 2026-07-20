"""
Arbre du site vitrine « Coopérative Code Commun », migré depuis Docusaurus.
/ Site tree of the "Coopérative Code Commun" showcase, migrated from Docusaurus.

LOCALISATION : pages/fixtures/site_codecommun/manifest.py

Ce fichier ne décrit QUE la structure (quelle page sous quel parent, dans quel
ordre). Les slugs, titres et descriptions des pages de CONTENU (docs, articles)
sont lus dans le frontmatter YAML des fichiers .md par la commande — pas dupliqués
ici. Seules les pages-INDEX de catégorie (qui n'ont pas de .md source) portent
leur slug/titre/description en clair.
/ This file only describes the structure (which page under which parent, in which
order). Content pages' slug/title/description come from the .md frontmatter, read
by the command — not duplicated here. Only the category INDEX pages (which have no
source .md) carry their slug/title/description here.

Hiérarchie APLATIE sur un niveau (le moteur pages ne gère qu'un parent → enfants,
l'URL reste plate /<slug>/). Les catégories Docusaurus imbriquées (Formations/
Python, Formations/Linux) sont fusionnées sous une seule page-index « Formations ».
/ Hierarchy FLATTENED to one level (the pages engine only supports one parent →
children level; the URL stays flat /<slug>/).
"""

# Chaque catégorie = une page-index (parent) + ses enfants (fichiers markdown).
# dossier : sous-dossier des fichiers enfants ("docs" ou "blog").
# enfants : noms de fichiers, DANS L'ORDRE D'AFFICHAGE voulu (position 1, 2, 3...).
# / Each category = one index page (parent) + its children (markdown files).
CATEGORIES = [
    {
        "slug": "presentation",
        "titre": "Présentation",
        "meta_description": "Code Commun : une fabrique à communs numériques. "
        "Notre charte, nos valeurs et notre vision des communs.",
        "position": 1,
        "dossier": "docs",
        "enfants": [
            "charte.md",
            "communs.md",
        ],
    },
    # NB : la catégorie « Créations » (Billetterie/Lèspass, Caisse/LaBoutik, Fedow)
    # n'est PAS chargée depuis le markdown : ses 3 fiches sont FUSIONNÉES en une
    # seule page « TiBillet » (slug /tibillet/, position 2), construite à la main
    # dans la commande (_charger_tibillet). Motif : Lèspass, LaBoutik et Fedow sont
    # les modules d'un même projet TiBillet. / The "Créations" category is merged
    # into a single hand-built "TiBillet" page (see _charger_tibillet).
    # NB : « Services » n'est pas une catégorie à enfants : elle n'a qu'une fiche
    # (sysadmin.md). On l'inline donc en page UNIQUE (slug /services/, position 3),
    # construite dans la commande (_charger_services) — un dropdown à un seul item
    # dans la navbar serait disgracieux. / "Services" holds a single doc, so it is
    # a standalone page (not a one-item dropdown). See _charger_services.
    {
        "slug": "formations",
        "titre": "Formations",
        "meta_description": "Apprenez à coder en Python, à administrer des systèmes "
        "Linux et à collaborer, avec la coopérative Code Commun.",
        "position": 4,
        "dossier": "docs",
        "enfants": [
            "nos_sujets_pref.md",
            "referentiels-python.md",
            "articles-pythons.md",
            "referentiels-linux.md",
            "link_sysadmin.md",
        ],
    },
    {
        "slug": "blog",
        # Libellé court pour la navbar (le moteur utilise le titre comme label).
        # / Short label for the navbar (the engine uses the title as the label).
        "titre": "Blog",
        "meta_description": "Les recettes de la coopérative pour de chouettes "
        "communs numériques.",
        "position": 5,
        "dossier": "blog",
        # Articles du plus récent au plus ancien (position 1 = le plus récent).
        # / Articles newest first (position 1 = newest).
        "enfants": [
            "2024-07-21-petition-ngi.md",
            "2024-05-28-annonce-aap.md",
            "2023-11-19-Python-comprehension-list.md",
            "2023-11-11-Python-unpacking.md",
            "2023-11-08-wildcard.md",
            "2023-10-26-Preambule.md",
            "2023-10-25-Administration_serveur.md",
            "2023-10-15-sametmax.md",
            "2023-10-15-citation-logiciel-libre-et-anarchisme.md",
            "2023-10-14-hypermedia-on-whateveryoulike.md",
            "2023-10-09-First.md",
            "2023-09-05-Federation-Part5.md",
            "2023-07-05-Federation-Part4.md",
            "2023-06-06-Federation-Part3.md",
            "2022-10-10-Federation-Part2.md",
            "2022-10-09-Federation-Part1.md",
            "2022-10-03-RTL-CR.md",
            "2022-09-15-Ecosocialisme_numerique.md",
            "2022-09-01-Lien_utile.md",
        ],
    },
]

# Alias des anciennes pages-index de catégorie Docusaurus (/docs/category/<x>)
# vers le nouveau slug de la page-index. Sert à réécrire les liens internes du
# contenu. / Old Docusaurus category index paths (/docs/category/<x>) mapped to
# the new index page slug, to rewrite internal content links.
CATEGORIES_ALIAS = {
    "la-fabrique-à-commun": "presentation",
    "la-fabrique-a-commun": "presentation",
    # « Créations » n'existe plus comme index : elle renvoie vers la page TiBillet.
    # / "Créations" is no longer an index page: it points to the TiBillet page.
    "créations": "tibillet",
    "creations": "tibillet",
    "services": "services",
    "formations": "formations",
}

# Redirections manuelles de liens internes : anciennes fiches Docusaurus dont la
# page a disparu (fusion) ou changé de slug. Fragment d'ancien chemin -> nouveau
# chemin. La commande couvre les préfixes /docs, /docs/Creations, /blog (relatifs
# et absolus vers codecommun.coop). / Manual internal-link redirects: old Docusaurus
# pages that were merged or renamed. Old path fragment -> new path.
REDIRECTIONS_MANUELLES = {
    # Les 3 fiches Créations fusionnées dans /tibillet/.
    # / The 3 Créations pages merged into /tibillet/.
    "tibillet-ticketing": "/tibillet/",
    "tibillet-laboutik": "/tibillet/",
    "tibillet-fedow": "/tibillet/",
    # La fiche « hebergement » est inlinée dans la page /services/.
    # / The "hebergement" doc is inlined into the /services/ page.
    "hebergement": "/services/",
    # Article de blog renommé pendant la migration. Le slug d'origine finissait
    # par « fedow », ce qu'une route core alors non ancrée capturait (403). Les
    # routes sont ancrées depuis, mais la redirection reste : l'ancienne adresse
    # a circulé. / Blog article renamed during the migration. The redirect stays:
    # the old address has been shared.
    "federation-part5-fedow": "/federation-part5/",
}
