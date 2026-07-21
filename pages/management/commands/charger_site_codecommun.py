"""
Charge le site vitrine de la « Coopérative Code Commun » dans le moteur pages
(blocs), migré depuis l'ancien site Docusaurus (docs + blog + accueil).
/ Loads the "Coopérative Code Commun" showcase website into the pages engine
(blocks), migrated from the old Docusaurus site (docs + blog + home).

LOCALISATION : pages/management/commands/charger_site_codecommun.py

Usage :
    python manage.py charger_site_codecommun --schema=codecommun
    python manage.py charger_site_codecommun --schema=codecommun --no-home

Ce que fait la commande, dans le contexte d'UN tenant :
 1. ACCUEIL — reconstruit À LA MAIN en blocs (le React de l'ancienne home ne se
    convertit pas tout seul) : HERO + section coopérative + 4 cartes logiciels +
    bande de partenaires.
 2. DOCS & BLOG — pour chaque fichier markdown du manifeste : une Page + un bloc
    MARKDOWN. Les catégories deviennent des pages-index avec un bloc
    LISTE_SOUS_PAGES. Le blog est une page ordinaire : ses articles sont ses
    sous-pages, listees par un bloc LISTE.
 3. IMAGES du markdown — chaque `![légende](/img/…)` est UPLOADÉE dans le media du
    tenant comme ImageGalerie du bloc, puis réécrite en `![légende](galerie:N)`
    (mécanisme natif du moteur, cf. templatetag rendre_bloc_markdown). Les images
    externes (http…) sont laissées telles quelles.
 4. LIENS internes — /docs/<x> et /blog/<x> (y compris en absolu vers
    codecommun.coop) sont réécrits vers /<slug>/ (le moteur sert tout à plat).

Le contenu source (markdown + images) est BUNDLÉ dans le repo sous
pages/fixtures/site_codecommun/ : la commande est donc relançable en prod, sans
dépendre d'un dossier externe.
/ Source content (markdown + images) is BUNDLED under pages/fixtures/
site_codecommun/, so the command is replayable in prod without any external path.
"""

import datetime
import re
from pathlib import Path

import yaml
from django.core.files import File
from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Customers.models import Client

# Dossier des fixtures bundlées (markdown + images).
# / Bundled fixtures folder (markdown + images).
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "site_codecommun"
DOSSIER_IMG = FIXTURES / "img"

# Extensions bitmap : les SEULES que StdImageField/Pillow sait redimensionner.
# Un SVG casserait la génération des variations -> on le saute (log + on laisse la
# référence markdown telle quelle). / Bitmap extensions only: the only ones Pillow
# can resize. An SVG would break variation generation -> we skip it.
EXTENSIONS_BITMAP = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Repère une image markdown : ![légende](url). La légende peut être vide.
# / Matches a markdown image: ![caption](url). Caption may be empty.
REGEX_IMAGE_MARKDOWN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)")

# Liste noire : illustrations d'ambiance du blog (décoratives), écartées à la
# demande du mainteneur. On ne garde que les images DESCRIPTIVES (schémas,
# captures, logos). Ces chemins ne sont ni uploadés (og:image), ni rendus dans le
# corps (la référence markdown est retirée). / Blocklist: decorative "mood"
# illustrations of the blog. Only DESCRIPTIVE images (diagrams, screenshots, logos)
# are kept. These paths are neither uploaded (og:image) nor rendered in the body.
IMAGES_A_IGNORER = frozenset(
    {
        "/img/blog/python-gen.jpg",
        "/img/blog/python-unboxing.jpg",
        "/img/blog/anar-libre.png",
        "/img/blog/hypermedia/original.png",
        "/img/federons/decollage.jpg",
        "/img/federons/design_head.jpg",
        "/img/federons/fedow_logo.jpg",
        "/img/blog/cod-ensamb/2023-10-26/congratulations.png",
    }
)


class Command(BaseCommand):
    help = (
        "Charge le site vitrine Code Commun (migré de Docusaurus) via le moteur pages."
    )

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="codecommun")
        # --no-home : ne pas (re)construire la page d'accueil (utile si le tenant a
        # déjà une home qu'on ne veut pas écraser). / Skip (re)building the home page.
        parser.add_argument(
            "--no-home",
            action="store_false",
            dest="home",
            help="Ne pas (re)construire la page d'accueil.",
        )

    def handle(self, *args, **options):
        from pages.fixtures.site_codecommun.manifest import CATEGORIES

        schema = options["schema"]
        try:
            tenant = Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            self.stderr.write(f"Tenant introuvable : {schema}")
            return

        with tenant_context(tenant):
            # Passe 1 : lire tous les frontmatters pour connaître l'ensemble des
            # slugs (nécessaire pour réécrire les liens internes du contenu).
            # / Pass 1: read all frontmatters to know every slug (needed to
            # rewrite internal content links).
            pages_prevues = self._preparer(CATEGORIES)
            remplacements_liens = self._construire_remplacements_liens(pages_prevues)

            # Passe 2 : construire l'accueil, la page TiBillet (fusion Créations),
            # puis chaque catégorie + ses enfants.
            # / Pass 2: build the home, the TiBillet page (merged Créations), then
            # each category + its children.
            if options["home"]:
                self._charger_accueil()
            self._charger_tibillet()
            self._charger_services(remplacements_liens)
            for categorie in CATEGORIES:
                self._charger_categorie(categorie, pages_prevues, remplacements_liens)

        # +2 pages hors catégories : TiBillet et Services (inlinées).
        # / +2 pages outside categories: TiBillet and Services (inlined).
        nb = len(pages_prevues) + len(CATEGORIES) + 2 + (1 if options["home"] else 0)
        self.stdout.write(
            self.style.SUCCESS(f"Site Code Commun chargé sur '{schema}' (~{nb} pages).")
        )

    # ==================================================================
    # PASSE 1 — préparation : frontmatter de chaque fichier de contenu.
    # / PASS 1 — preparation: each content file's frontmatter.
    # ==================================================================
    def _preparer(self, categories):
        """
        Retourne un dict fichier -> métadonnées (slug, titre, description, image,
        corps markdown, dossier), pour toutes les pages de contenu du manifeste.
        / Returns a dict file -> metadata for every content page in the manifest.
        """
        pages_prevues = {}
        for categorie in categories:
            for fichier in categorie["enfants"]:
                chemin = FIXTURES / categorie["dossier"] / fichier
                frontmatter, corps = self._lire_markdown(chemin)
                pages_prevues[fichier] = {
                    "slug": frontmatter.get("slug") or Path(fichier).stem,
                    "titre": frontmatter.get("title") or Path(fichier).stem,
                    "description": frontmatter.get("description") or "",
                    "image": frontmatter.get("image") or "",
                    "corps": corps,
                    "dossier": categorie["dossier"],
                }
        return pages_prevues

    def _lire_markdown(self, chemin):
        """
        Sépare le frontmatter YAML (entre deux lignes « --- ») du corps markdown.
        / Splits the YAML frontmatter (between two "---" lines) from the body.
        """
        texte = chemin.read_text(encoding="utf-8")
        lignes = texte.split("\n")
        if lignes and lignes[0].strip() == "---":
            # On cherche la ligne « --- » de fermeture. / Find the closing "---".
            for index in range(1, len(lignes)):
                if lignes[index].strip() == "---":
                    frontmatter = yaml.safe_load("\n".join(lignes[1:index])) or {}
                    corps = "\n".join(lignes[index + 1 :]).strip()
                    return frontmatter, corps
        # Pas de frontmatter : tout le fichier est du corps.
        # / No frontmatter: the whole file is body.
        return {}, texte.strip()

    # ==================================================================
    # PASSE 2 — construction d'une catégorie (page-index + enfants).
    # / PASS 2 — building a category (index page + children).
    # ==================================================================
    def _charger_categorie(self, categorie, pages_prevues, remplacements_liens):
        from pages.models import Bloc

        # 1 — La page-index de la catégorie (parent des enfants).
        # / The category index page (parent of the children).
        index = self._page_propre(
            slug=categorie["slug"],
            titre=categorie["titre"],
            position=categorie["position"],
            meta_description=categorie["meta_description"],
        )

        # Menu lateral : sur une page-index et ses enfants, l'arbre de la
        # categorie se deplie dans la marge gauche (et se replie en burger sur
        # mobile), au lieu de charger la navbar d'un menu deroulant profond.
        # C'est la navigation d'un site de documentation.
        # / Side menu: on an index page and its children, the category tree
        # unfolds in the left margin (burger on mobile) instead of loading the
        # navbar with a deep dropdown. This is documentation-site navigation.
        from pages.models import Page

        Page.objects.filter(pk=index.pk).update(affichage_nav=Page.SIDEBAR)

        # Un bloc LISTE affiche les enfants publiés en cartes.
        # nombre_max large pour tout montrer (le blog a 19 articles).
        # / A LISTE block shows published children as cards.
        Bloc.objects.create(
            page=index,
            type_bloc=Bloc.LISTE, source=Bloc.SOUS_PAGES,
            position=1,
            titre=categorie["titre"],
            nombre_max=50,
        )

        # 2 — Les pages enfants (dans l'ordre du manifeste = position 1, 2, 3...).
        # / The child pages (manifest order = position 1, 2, 3...).
        for position, fichier in enumerate(categorie["enfants"], start=1):
            self._charger_page_markdown(
                pages_prevues[fichier],
                parent=index,
                position=position,
                remplacements_liens=remplacements_liens,
                date_publication=self._date_publication(fichier),
            )

    def _date_publication(self, fichier):
        """
        Date de parution lue dans le PRÉFIXE du nom de fichier (AAAA-MM-JJ,
        convention Docusaurus pour le blog). Retourne un datetime tz-aware (midi
        UTC), ou None si le nom n'a pas ce préfixe (pages docs).
        / Publication date read from the filename prefix (YYYY-MM-DD, Docusaurus
        blog convention). Returns a tz-aware datetime, or None for docs pages.
        """
        try:
            annee, mois, jour = (int(part) for part in fichier[:10].split("-"))
            return datetime.datetime(
                annee, mois, jour, 12, 0, tzinfo=datetime.timezone.utc
            )
        except (ValueError, TypeError):
            return None

    def _charger_page_markdown(
        self, infos, parent, position, remplacements_liens, date_publication=None
    ):
        """
        Crée une Page de contenu + son unique bloc MARKDOWN, en traitant les images
        (upload + réécriture galerie:N) et les liens internes.
        / Creates a content Page + its single MARKDOWN block, processing images
        (upload + galerie:N rewrite) and internal links.
        """
        from pages.models import Bloc

        page = self._page_propre(
            slug=infos["slug"],
            titre=infos["titre"],
            position=position,
            meta_description=infos["description"][:250],
            parent=parent,
        )

        # Image sociale (frontmatter) -> champ image de la Page (carte sociale, SEO).
        # On saute les illustrations d'ambiance de la liste noire.
        # / Social image (frontmatter) -> Page.image field. Blocklisted mood
        # illustrations are skipped.
        if (
            infos["image"].startswith("/img/")
            and infos["image"] not in IMAGES_A_IGNORER
        ):
            self._poser_fichier(
                page, "image", DOSSIER_IMG / infos["image"][len("/img/") :]
            )

        # Le bloc MARKDOWN porte le corps. On le crée D'ABORD (les ImageGalerie ont
        # besoin d'un bloc parent), puis on traite les images, puis on enregistre le
        # texte réécrit. / The MARKDOWN block carries the body. Create it FIRST
        # (ImageGalerie need a parent block), then process images, then save text.
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.TEXTE, position=1)
        corps = self._traiter_images(bloc, infos["corps"])
        corps = self._reecrire_liens(corps, remplacements_liens)
        bloc.texte = corps
        bloc.save(update_fields=["texte"])

        # Date de parution : created_at et updated_at sont des champs auto
        # (auto_now_add / auto_now), impossibles à fixer via save(). On force la
        # VRAIE date par un update(), qui les contourne. Sans lui, la page
        # porterait sa date d'import. Les deux champs reçoivent la même date pour
        # ne pas afficher un « mis à jour le » trompeur.
        # / Publication date: created_at and updated_at are auto fields, unsettable
        # via save(). We force the REAL date with an update() that bypasses them.
        # Without it the page would carry its import date. Both get the same date
        # so no misleading "updated on" shows.
        if date_publication:
            from pages.models import Page

            Page.objects.filter(pk=page.pk).update(
                created_at=date_publication, updated_at=date_publication
            )

    # ==================================================================
    # SERVICES — page UNIQUE (une seule fiche : sysadmin.md). Inlinée en page de
    # 1er niveau plutôt qu'en catégorie, pour éviter un dropdown à un seul item.
    # / SERVICES — single page (only sysadmin.md). Inlined as a top-level page
    # instead of a category, to avoid a one-item dropdown.
    # ==================================================================
    def _charger_services(self, remplacements_liens):
        frontmatter, corps = self._lire_markdown(FIXTURES / "docs" / "sysadmin.md")
        infos = {
            # Slug et titre imposés (le doc a slug=hebergement, titre trop long) :
            # on veut « Services » dans la navbar et l'URL /services/.
            # / Forced slug and title: we want "Services" in the navbar and /services/.
            "slug": "services",
            "titre": "Services",
            "description": frontmatter.get("description")
            or "Hébergement et administration de vos outils libres par la coopérative.",
            "image": frontmatter.get("image") or "",
            "corps": corps,
        }
        self._charger_page_markdown(
            infos, parent=None, position=3, remplacements_liens=remplacements_liens
        )

    # ==================================================================
    # Helpers partagés.
    # / Shared helpers.
    # ==================================================================
    def _page_propre(
        self,
        slug,
        titre,
        position=0,
        est_accueil=False,
        meta_description="",
        parent=None,
    ):
        """
        Récupère une Page par slug ou la crée, met à jour ses méta, et VIDE ses
        blocs (relance idempotente). / Gets a Page by slug or creates it, updates
        its meta, and CLEARS its blocks (idempotent replay).
        """
        from pages.models import Page

        page, _cree = Page.objects.get_or_create(slug=slug, defaults={"titre": titre})
        page.titre = titre
        page.position = position
        page.publie = True
        page.est_accueil = est_accueil
        page.meta_description = meta_description
        page.parent = parent
        page.save()
        page.blocs.all().delete()
        return page

    def _poser_fichier(self, objet, champ, chemin):
        """
        Uploade un fichier image (bitmap) dans un champ StdImageField. Saute les SVG
        et les fichiers manquants (log). Retourne True si l'upload a eu lieu.
        / Uploads a bitmap image into a StdImageField. Skips SVG and missing files.
        """
        chemin = Path(chemin)
        if not chemin.exists():
            self.stdout.write(f"  ⚠ image introuvable : {chemin.name}")
            return False
        if chemin.suffix.lower() not in EXTENSIONS_BITMAP:
            self.stdout.write(
                f"  ⚠ image non redimensionnable (ignorée) : {chemin.name}"
            )
            return False
        with open(chemin, "rb") as fichier:
            getattr(objet, champ).save(chemin.name, File(fichier), save=True)
        return True

    def _traiter_images(self, bloc, corps):
        """
        Remplace chaque image markdown locale ![alt](/img/…) par une ImageGalerie du
        bloc, réécrite en ![alt](galerie:N). Les images externes (http…) et les
        fichiers absents/SVG sont laissés tels quels.
        / Replaces each local markdown image ![alt](/img/…) by a block ImageGalerie,
        rewritten as ![alt](galerie:N). External/missing/SVG images are left as-is.
        """
        from pages.models import ImageGalerie

        compteur = {"n": 0}

        def remplacer(correspondance):
            alt = correspondance.group("alt")
            url = correspondance.group("url").strip()
            # Un éventuel titre markdown ![alt](url "titre") : on garde l'URL seule.
            # / Drop an optional markdown title ![alt](url "title").
            url = url.split()[0] if " " in url else url
            # Illustration d'ambiance sur liste noire : on RETIRE la référence
            # (chaîne vide) pour ne pas laisser un <img> cassé dans le rendu.
            # / Blocklisted mood illustration: REMOVE the reference (empty string).
            if url in IMAGES_A_IGNORER:
                return ""
            if not url.startswith("/img/"):
                return correspondance.group(0)  # externe -> on laisse / external
            chemin = DOSSIER_IMG / url[len("/img/") :]
            if not chemin.exists() or chemin.suffix.lower() not in EXTENSIONS_BITMAP:
                self.stdout.write(f"  ⚠ image markdown ignorée : {url}")
                return correspondance.group(0)
            compteur["n"] += 1
            image = ImageGalerie.objects.create(
                bloc=bloc,
                position=compteur["n"],
                legende=alt or "",
            )
            self._poser_fichier(image, "image", chemin)
            return f"![{alt}](galerie:{compteur['n']})"

        return REGEX_IMAGE_MARKDOWN.sub(remplacer, corps)

    def _construire_remplacements_liens(self, pages_prevues):
        """
        Construit le dict {ancien chemin -> nouveau chemin} pour réécrire les liens
        internes du contenu (/docs/<slug>, /blog/<slug>, pages-index de catégorie),
        en relatif et en absolu (codecommun.coop). / Builds the {old path -> new
        path} dict to rewrite internal content links, relative and absolute.
        """
        from pages.fixtures.site_codecommun.manifest import (
            CATEGORIES_ALIAS,
            REDIRECTIONS_MANUELLES,
        )

        # Préfixes possibles d'un ancien lien Docusaurus (relatif + absolu). Le
        # segment /Creations couvre les liens du type /docs/Creations/<slug>.
        # / Possible old Docusaurus link prefixes (relative + absolute).
        bases = (
            "/docs/Creations",
            "/docs",
            "/blog",
            "https://codecommun.coop/docs/Creations",
            "https://codecommun.coop/docs",
            "https://codecommun.coop/blog",
        )

        remplacements = {}
        for infos in pages_prevues.values():
            slug = infos["slug"]
            # Seul endroit qui construit une adresse de page sans passer par
            # Page.get_absolute_url() : ici on ne tient qu'une entree du
            # manifeste (un dict), la Page n'existe pas encore en base. Le lien
            # est ensuite fige dans le texte du bloc, donc il faudra rejouer
            # cette commande si la forme des URLs change un jour.
            # / The only place building a page address without
            # Page.get_absolute_url(): we only hold a manifest entry (a dict),
            # the Page does not exist yet. The link is then frozen in the block
            # text, so this command must be replayed if the URL shape changes.
            cible = f"/{slug}/"
            for base in bases:
                # Variantes avec et sans slash final (le / final doit être remplacé
                # AVANT pour éviter un double slash). / With and without trailing slash.
                remplacements[f"{base}/{slug}/"] = cible
                remplacements[f"{base}/{slug}"] = cible

        # Redirections manuelles (fiches fusionnées ou renommées).
        # / Manual redirects (merged or renamed pages).
        for fragment, cible in REDIRECTIONS_MANUELLES.items():
            for base in bases:
                remplacements[f"{base}/{fragment}/"] = cible
                remplacements[f"{base}/{fragment}"] = cible

        # Pages-index de catégorie : /docs/category/<x> -> /<slug-index>/.
        # / Category index pages.
        for ancien, nouveau in CATEGORIES_ALIAS.items():
            cible = f"/{nouveau}/"
            for base in ("/docs/category", "https://codecommun.coop/docs/category"):
                remplacements[f"{base}/{ancien}/"] = cible
                remplacements[f"{base}/{ancien}"] = cible

        return remplacements

    def _reecrire_liens(self, corps, remplacements):
        """
        Applique les remplacements du plus long au plus court (pour ne pas casser un
        chemin plus long par un préfixe). / Applies replacements longest-first.
        """
        for ancien in sorted(remplacements, key=len, reverse=True):
            corps = corps.replace(ancien, remplacements[ancien])
        return corps

    # ==================================================================
    # TIBILLET — page unique fusionnant les 3 fiches Créations (Lèspass,
    # LaBoutik, Fedow), qui sont les modules d'un même projet. La description
    # d'intro s'inspire de la landing du tenant public. / TIBILLET — single page
    # merging the 3 "Créations" pages (they are modules of one project). The intro
    # copy is inspired by the public tenant's landing page.
    # ==================================================================
    def _charger_tibillet(self):
        from pages.models import Bloc, ImageGalerie

        page = self._page_propre(
            slug="tibillet",
            titre="TiBillet",
            position=2,
            meta_description="TiBillet : une boîte à outils libre et fédérée pour "
            "les lieux culturels et associatifs — billetterie, adhésions, caisse "
            "cashless NFC, monnaies locales et temps.",
        )

        # 1 — Intro (inspirée de la landing publique).
        # / Intro (inspired by the public landing).
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.TEXTE,
            position=1,
            titre="TiBillet, une boîte à outils libre et fédérée",
            texte=(
                "TiBillet est né sur le terrain, dans les festivals et les cafés "
                "associatifs de La Réunion. Pas dans un bureau d'études, mais dans "
                "les besoins concrets des lieux qui accueillent du public : vendre "
                "des billets sans frais cachés, gérer les adhésions, encaisser au "
                "bar, et fédérer les agendas entre structures voisines.\n\n"
                "Aujourd'hui c'est une boîte à outils complète — billetterie, "
                "cashless NFC multi-lieux, caisse enregistreuse, monnaie locale, "
                "monnaie temps, budget contributif — pensée pour et par les "
                "associations culturelles. Zéro dark pattern, zéro commission "
                "cachée, code source libre.\n\n"
                "Lèspass, LaBoutik et Fedow ne sont pas trois logiciels séparés : "
                "ce sont les modules d'un même commun numérique, qui s'interopèrent "
                "et se fédèrent. Chaque lieu garde son autonomie (son agenda, sa "
                "caisse, ses adhésions) et choisit avec qui se connecter.\n"
            ),
        )

        # 2 — Module Lèspass (billetterie & adhésions). Image à gauche.
        # / Lèspass module (ticketing & memberships). Image left.
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.SECTION, affichage=Bloc.TEXTE_IMAGE_GAUCHE,
            position=2,
            titre="Lèspass — billetterie & adhésions",
            texte=(
                "<p>Tout type de réservation ou de billetterie, intégré à tout "
                "l'écosystème TiBillet. Réservez une place en monnaie locale, prenez "
                "une demi-journée de fablab en monnaie temps, créez des tarifs "
                "préférentiels pour vos adhérent·es, partagez des abonnements entre "
                "plusieurs lieux.</p>"
                "<ul>"
                "<li>Concerts payants, billets nominatifs ou non, tarifs adhérents.</li>"
                "<li>Inscriptions gratuites, réservations de table avec validation.</li>"
                "<li>Adhésions associatives, abonnements renouvelables, fidélité.</li>"
                "<li>Événements réservés aux adhérent·es ou avec recharge cashless.</li>"
                "</ul>"
            ),
        )
        self._poser_fichier(
            bloc, "image", DOSSIER_IMG / "demo" / "BilletDemo1300Thumb.jpg"
        )

        # 3 — Module LaBoutik (caisse). Image à droite.
        # / LaBoutik module (POS). Image right.
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.SECTION, affichage=Bloc.TEXTE_IMAGE_DROITE,
            position=3,
            titre="LaBoutik — la caisse enregistreuse libre",
            texte=(
                "<p>Une caisse enregistreuse open source qui accepte les espèces, "
                "la carte bancaire, et surtout les cartes de paiement NFC pouvant "
                "héberger monnaies locales et temps.</p>"
                "<p>Pensée d'abord comme un cashless de festival, elle sert "
                "aujourd'hui de caisse pour les cafés associatifs, restaurants et "
                "bars. La carte NFC devient carte d'adhésion, portefeuille fédéré, "
                "carte d'abonnement et de fidélité. Elle intègre la gestion de salle "
                "et la prise de commande : listez les commandes en cours et imprimez "
                "les tickets pour la cuisine !</p>"
            ),
        )
        self._poser_fichier(bloc, "image", DOSSIER_IMG / "demo" / "maq2-420.jpg")

        # 4 — Module Fedow (portefeuille fédéré). Image à gauche.
        # / Fedow module (federated wallet). Image left.
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.SECTION, affichage=Bloc.TEXTE_IMAGE_GAUCHE,
            position=4,
            titre="Fedow — le portefeuille ouvert et fédéré",
            texte=(
                "<p>FEDOW (<em>Federated and Open Wallet</em>) crée et gère des "
                "portefeuilles multi-assets pour un groupement de monnaies locales, "
                "temps ou non fiduciaires, au sein d'un réseau fédéré. Une seule "
                "carte NFC, un portefeuille dématérialisé, utilisables dans "
                "plusieurs lieux associatifs, coopératifs ou commerciaux.</p>"
                "<p>Cashless de festival, monnaie locale à l'échelle d'un "
                "territoire, abonnements communs à plusieurs lieux : Fedow est pensé "
                "comme un outil financier pour l'économie sociale et solidaire. Il "
                "intègre des principes de monnaie fondante dans une chaîne de blocs "
                "par preuve d'autorité — transparente, non spéculative et non "
                "énergivore.</p>"
            ),
        )
        self._poser_fichier(bloc, "image", DOSSIER_IMG / "demo" / "cartes.jpg")

        # 5 — CTA : en savoir plus + contribuer.
        # / CTA: learn more + contribute.
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.SECTION, affichage=Bloc.APPEL_ACTION,
            position=5,
            titre="Un commun numérique en construction",
            texte="<p>Le code est libre — mais ce qui fait un commun, c'est la "
            "communauté qui l'entoure et la gouvernance partagée qui le "
            "pilote. La feuille de route est ouverte : proposez une idée, "
            "suivez un chantier, ou déclarez simplement votre intérêt.</p>",
            bouton_label="Découvrir TiBillet",
            bouton_url="https://tibillet.org/",
            bouton2_label="Contribuer au projet",
            bouton2_url="https://codecommun.tibillet.coop/",
        )

        # 6 — GALERIE : captures d'écran des modules.
        # / GALERIE: module screenshots.
        galerie = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.IMAGES, affichage=Bloc.GRILLE,
            position=6,
            titre="TiBillet en images",
        )
        captures = [
            ("BilletDemo1.jpg", "Billetterie — accueil"),
            ("BilletDemo2.jpg", "Billetterie — événement"),
            ("CashlessDemo.jpg", "LaBoutik — caisse"),
            ("CashlessDemo2.jpg", "LaBoutik — prise de commande"),
            ("BoitierRaff.jpg", "Boîtier de caisse NFC"),
            ("cartes.jpg", "Cartes cashless fédérées"),
        ]
        for position, (fichier, legende) in enumerate(captures, start=1):
            image = ImageGalerie.objects.create(
                bloc=galerie,
                position=position,
                legende=legende,
            )
            self._poser_fichier(image, "image", DOSSIER_IMG / "demo" / fichier)

    # ==================================================================
    # ACCUEIL — reconstruit à la main (l'ancienne home était du React).
    # / HOME — hand-rebuilt (the old home was React).
    # ==================================================================
    def _charger_accueil(self):
        from BaseBillet.models import Configuration
        from pages.models import Bloc, ImageGalerie

        page = self._page_propre(
            slug="accueil",
            titre="Accueil",
            position=0,
            est_accueil=True,
            meta_description="Coopérative Code Commun : fabrique de communs "
            "numériques et de logiciels libres pour coopérer et s'émanciper.",
        )

        # 1 — HERO : bannière d'identité. L'image de fond est l'image générique du
        # lieu (Configuration.img), lue par le gabarit HERO. On y pose la bannière
        # réseau de l'ancien site. / HERO: identity banner; the background is the
        # venue's generic image (Configuration.img), set to the old network banner.
        self._poser_fichier(
            Configuration.get_solo(), "img", DOSSIER_IMG / "network.jpg"
        )
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.SECTION, affichage=Bloc.BANNIERE,
            position=1,
            titre="Fabrique de Communs Numériques",
            sous_titre="Des outils libres pour coopérer et s'émanciper.",
        )

        # 2 — Section coopérative. Le champ `texte` d'un bloc TEXTE contient du
        # MARKDOWN : le gabarit le convertit puis nettoie le HTML produit, ce
        # qui retire les attributs `class` et `style`. La taille de police et
        # l'interligne viennent du CSS (.tb-markdown).
        # / Cooperative section. A TEXTE block's `texte` holds MARKDOWN: the
        # template converts it then sanitizes the produced HTML, stripping
        # `class` and `style`. Font size and line height come from the CSS.
        # Les deux espaces en fin de ligne forcent un retour a la ligne en
        # Markdown. / The two trailing spaces force a line break in Markdown.
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.TEXTE,
            position=2,
            titre="Une fabrique collective",
            texte=(
                "Code Commun est une "
                "**coopérative (SCIC)**.  \n"
                "Nous fabriquons des **logiciels** sous licences **libres**.  \n"
                "Nous formons autant à l'utilisation qu'à la création de ces outils.  \n"
                "Nous travaillons de manière transparente et partagée.\n"
            ),
        )

        # 3 — Teaser des SERVICES : ce que la coopérative fait POUR le visiteur
        # (et non seulement les produits qu'elle publie). Chemin vers /services/.
        # / Service teaser: what the cooperative does FOR the visitor.
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.SECTION, affichage=Bloc.APPEL_ACTION,
            position=3,
            titre="Ce qu'on fait pour vous",
            texte=(
                "<p>Développement sur mesure, hébergement de logiciels libres, "
                "installation de Ghost, formation et animation de projets "
                "numériques : la coopérative vous accompagne de l'idée à la mise "
                "en service — vous restez maîtres de vos outils et de vos données.</p>"
            ),
            bouton_label="Découvrir nos services",
            bouton_url="/services/",
        )

        # 4 — Titre de la vitrine logiciels (badge de section).
        # / Software showcase heading.
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.TEXTE,
            position=4,
            titre="Nous maintenons et contribuons à :",
        )

        # 4-7 — Cartes logiciels (image + description + bouton « Découvrir »).
        # / Software cards (image + description + "Découvrir" button).
        # Cartes des logiciels maintenus par la cooperative. Les titres portent
        # le domaine (.coop / .org) : c'est aussi l'identifiant que les gens
        # tapent dans leur navigateur. Ordre = importance decroissante.
        # / Software cards. Titles carry the domain (.coop / .org), which is
        # also what people type in their browser.
        logiciels = [
            (
                "TiBillet.coop",
                "kit/logos/png/monochrome.png",
                "https://tibillet.coop",
                "Tibillet est une suite d'outils pour faciliter nos organisations "
                "collectives : système de caisse, adhésions/abonnement, monnaie "
                "temps/locales, billetterie, cashless, agenda fédéré, Sécurité "
                "Sociale Alimentaire... Une solution complète et libre.",
            ),
            (
                "OpenBadge.coop",
                "badge_blanc.png",
                "https://openbadge.coop",
                "Plateforme complète de gestion de badges numériques ouverts (Open "
                "Badges). Valorisons collectivement nos savoirs-faire et tout ce qui "
                "relève de l'expérience humaine !",
            ),
            (
                "Hypostasia.org",
                "hypostasia.png",
                "https://hypostasia.org",
                "Un outil libre pour lire, extraire et débattre collectivement d'un "
                "texte. Importez un PDF, un audio ou une page web, Hypostasia en "
                "extrait le contenu et ouvre la discussion.",
            ),
            (
                "Formations",
                "Graphical_codecommun270.png",
                "/formations/",
                "Apprenez à coder, à administrer des systèmes Linux et à collaborer.",
            ),
        ]
        for position, (titre, image, lien, description) in enumerate(
            logiciels, start=5
        ):
            bloc = Bloc.objects.create(
                page=page,
                type_bloc=Bloc.SECTION, affichage=Bloc.CARTE,
                position=position,
                titre=titre,
                texte=f"<p>{description}</p>",
                bouton_label="Découvrir",
                bouton_url=lien,
            )
            self._poser_fichier(bloc, "image", DOSSIER_IMG / image)

        # 9 — CTA de CONTACT : le chemin de conversion vers la coopérative (une
        # landing de boîte de dev doit dire « parlons de votre projet »).
        # / Contact CTA: the conversion path to the cooperative.
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.SECTION, affichage=Bloc.APPEL_ACTION,
            position=9,
            titre="Un projet numérique ? Discutons-en",
            texte=(
                "<p>Une idée, un besoin, une envie de coopérer ? Écrivez-nous, ou "
                "rejoignez l'espace contributif de la coopérative.</p>"
            ),
            # ?contact=1 ouvre le panneau offcanvas « Contact et support » (mécanisme
            # de la navbar classic), plutôt qu'un mailto qui force le client mail.
            # / ?contact=1 opens the "Contact and support" offcanvas panel.
            bouton_label="Nous contacter",
            bouton_url="?contact=1",
            bouton2_label="Espace contributif",
            bouton2_url="https://codecommun.tibillet.coop/",
        )

        # 10 — Titre partenaires. / Partners heading.
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.TEXTE,
            position=10,
            titre="Nos partenaires",
            texte="Ils nous soutiennent et construisent avec nous.\n",
        )

        # 11 — PARTENAIRES : on réutilise la liste CANONIQUE de la landing publique
        # (seo.views.CONTRIBUTEURS = source unique de vérité, partagée avec le tenant
        # public). Les logos sont servis depuis seo/static/contributeurs/, résolus
        # par le finder staticfiles. Un logo SVG est écarté AVANT création (Pillow
        # ne redimensionne pas un SVG -> pas d'ImageGalerie sans image).
        # / PARTENAIRES: reuse the CANONICAL list of the public landing
        # (seo.views.CONTRIBUTEURS, single source of truth). Logos come from
        # seo/static/contributeurs/, resolved by the staticfiles finder. An SVG logo
        # is skipped BEFORE creation (Pillow can't resize SVG).
        from django.contrib.staticfiles import finders

        from seo.views import CONTRIBUTEURS

        # Pas de titre ici : le bloc TEXTE juste au-dessus porte deja
        # « Nos partenaires ». Le repeter afficherait deux fois le meme titre,
        # l'un sous l'autre. / No title here: the TEXTE block above already
        # carries "Nos partenaires"; repeating it would show it twice.
        partenaires = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.IMAGES, affichage=Bloc.BANDE_LOGOS,
            position=11,
        )
        position_logo = 0
        for contributeur in CONTRIBUTEURS:
            chemin_logo = finders.find(contributeur["logo"])
            if (
                not chemin_logo
                or Path(chemin_logo).suffix.lower() not in EXTENSIONS_BITMAP
            ):
                self.stdout.write(
                    f"  ⚠ logo partenaire ignoré (introuvable/SVG) : "
                    f"{contributeur['logo']}"
                )
                continue
            position_logo += 1
            logo = ImageGalerie.objects.create(
                bloc=partenaires,
                position=position_logo,
                legende=contributeur["nom"],
                lien_url=contributeur["url"],
            )
            self._poser_fichier(logo, "image", chemin_logo)
