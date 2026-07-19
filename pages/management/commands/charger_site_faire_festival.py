"""
Construit un site avec le skin faire_festival, a partir d'un contenu declare.
/ Builds a website with the faire_festival skin, from a declared content set.

LOCALISATION : pages/management/commands/charger_site_faire_festival.py

Cette commande sait CONSTRUIRE un site ; elle ne sait pas ce qu'il raconte.
Le contenu vit dans `pages/fixtures/site_faire_festival/` :

    contenu_demo.py   festival generique et fictif (jeu de demonstration)
    contenu_reel.py   le site du vrai festival

/ This command knows HOW to build a website; it does not know what it says.
The content lives in `pages/fixtures/site_faire_festival/`.

Usage :
    python manage.py charger_site_faire_festival                      # demo
    python manage.py charger_site_faire_festival --contenu=reel       # vrai site
    python manage.py charger_site_faire_festival --schema=mon_tenant
    python manage.py charger_site_faire_festival --no-skin            # garde le skin actuel
    python manage.py charger_site_faire_festival --no-purge           # n'efface aucun bloc

PRUDENCE EN PRODUCTION. Par defaut la commande est DESTRUCTIVE : elle vide les
blocs des pages qu'elle touche pour pouvoir etre relancee sans creer de
doublons. Sur un site en ligne, c'est le contenu deja publie qui disparait.
`--no-purge` laisse les blocs existants en place et n'ajoute que les pages
absentes ; `--no-skin` ne touche pas au theme du tenant. Une page d'accueil
deja definie n'est JAMAIS remplacee sans `--forcer-accueil`.
/ CAUTION IN PRODUCTION. By default this command is DESTRUCTIVE: it empties the
blocks of the pages it touches so it can be replayed without creating
duplicates. On a live website that means published content disappears.
`--no-purge` keeps existing blocks; `--no-skin` leaves the theme alone. An
existing home page is NEVER replaced without `--forcer-accueil`.

Les images sont UPLOADEES dans le media du tenant (vrai moteur d'upload, comme
le reste de TiBillet) : on lit l'asset static du skin et on l'enregistre dans le
champ du bloc, qui genere ses variations.
/ Images are UPLOADED into the tenant media: the skin's static asset is read and
saved into the block's field, which generates its variations.
"""

import os

from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Customers.models import Client

# Dossier des images du skin : les noms declares dans le contenu s'y resolvent.
# / The skin's image folder: names declared in the content resolve here.
IMG = "faire_festival/image/"

# Jeux de contenu disponibles pour l'option --contenu.
# / Content sets available through the --contenu option.
CONTENUS = {
    "demo": "pages.fixtures.site_faire_festival.contenu_demo",
    "reel": "pages.fixtures.site_faire_festival.contenu_reel",
}

# Cles du contenu qui designent un fichier, et le champ du bloc ou le poser.
# / Content keys naming a file, and the block field to put it in.
CHAMPS_FICHIER = ("image", "image_secondaire", "video")


class Command(BaseCommand):
    help = "Construit un site avec le skin faire_festival, depuis un contenu declare."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="festival")
        parser.add_argument(
            "--contenu",
            default="demo",
            choices=sorted(CONTENUS),
            help="Jeu de contenu a charger (defaut : demo).",
        )
        parser.add_argument(
            "--no-skin",
            action="store_false",
            dest="skin",
            help="Ne pas forcer le skin 'faire_festival' (laisse le skin actuel).",
        )
        parser.add_argument(
            "--no-purge",
            action="store_false",
            dest="purge",
            help=(
                "Ne pas vider les blocs des pages existantes. A utiliser en "
                "production : sans cette option, le contenu deja publie est efface."
            ),
        )
        parser.add_argument(
            "--forcer-accueil",
            action="store_true",
            help=(
                "Autorise le remplacement d'une page d'accueil deja definie. "
                "Sans cette option, une page d'accueil existante est preservee."
            ),
        )

    def handle(self, *args, **options):
        from importlib import import_module

        schema = options["schema"]
        try:
            tenant = Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            self.stderr.write(f"Tenant introuvable : {schema}")
            return

        module = import_module(CONTENUS[options["contenu"]])
        pages = module.PAGES

        with tenant_context(tenant):
            # Deux passes : toutes les pages d'abord, les blocs ensuite. Une page
            # peut se rattacher a une autre (`parent`) ou pointer vers elle
            # (bouton, bloc LISTE) : si on construisait page par page, la
            # premiere ne trouverait pas la seconde.
            # / Two passes: every page first, then the blocks. A page may attach
            # to another one, so building page by page would fail on the first.
            pages_par_slug = {}
            for donnees in pages:
                pages_par_slug[donnees["slug"]] = self._poser_page(donnees, options)
            for donnees in pages:
                self._poser_les_blocs(pages_par_slug[donnees["slug"]], donnees, options)
            self._rattacher(pages, pages_par_slug)

            if options["skin"]:
                self._forcer_skin()

        self.stdout.write(self.style.SUCCESS(
            f"Site faire_festival (contenu : {options['contenu']}) charge sur "
            f"'{schema}' — {len(pages)} pages."
        ))

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    def _poser_page(self, donnees, options):
        """
        Cree ou met a jour une page, sans son rattachement ni ses blocs.
        / Creates or updates a page, without its parent nor its blocks.
        """
        from pages.models import Page

        page, _cree = Page.objects.get_or_create(
            slug=donnees["slug"], defaults={"titre": donnees["titre"]}
        )
        page.titre = donnees["titre"]
        page.position = donnees.get("position", 0)
        page.publie = True
        page.meta_description = donnees.get("meta_description", "")
        if "affichage_nav" in donnees:
            page.affichage_nav = donnees["affichage_nav"]

        # Une page d'accueil deja en place n'est pas remplacee en silence : sur
        # un site en ligne, c'est la premiere chose que voit le public.
        # / An existing home page is not silently replaced: on a live site it is
        # the first thing the public sees.
        if donnees.get("est_accueil"):
            accueil_existant = (
                Page.objects.filter(est_accueil=True).exclude(pk=page.pk).first()
            )
            if accueil_existant and not options["forcer_accueil"]:
                self.stdout.write(self.style.WARNING(
                    f"  page d'accueil deja definie (/{accueil_existant.slug}/) : "
                    f"/{page.slug}/ est chargee sans la remplacer. "
                    f"Utiliser --forcer-accueil pour l'imposer."
                ))
            else:
                page.est_accueil = True

        page.save()

        if donnees.get("config_image"):
            from BaseBillet.models import Configuration
            self._poser_fichier(Configuration.get_solo(), "img", donnees["config_image"])

        return page

    def _rattacher(self, pages, pages_par_slug):
        """
        Pose les liens parent/enfant, une fois toutes les pages creees.
        / Sets parent/child links, once every page exists.
        """
        for donnees in pages:
            parent = donnees.get("parent")
            if not parent:
                continue
            page = pages_par_slug[donnees["slug"]]
            page.parent = pages_par_slug[parent]
            page.save(update_fields=["parent"])

    # ------------------------------------------------------------------
    # Blocs
    # ------------------------------------------------------------------
    def _poser_les_blocs(self, page, donnees, options):
        from pages.models import Bloc, ImageGalerie

        if options["purge"]:
            page.blocs.all().delete()
        elif page.blocs.exists():
            # Sans purge, une page qui a deja des blocs est laissee telle quelle :
            # y ajouter ceux du contenu produirait un doublon de tout.
            # / Without purge, a page that already has blocks is left as is:
            # adding the content's blocks would duplicate everything.
            self.stdout.write(
                f"  /{page.slug}/ a deja des blocs : laissee intacte (--no-purge)."
            )
            return

        for position, bloc_declare in enumerate(donnees.get("blocs", []), start=1):
            champs = {
                cle: valeur
                for cle, valeur in bloc_declare.items()
                if cle not in CHAMPS_FICHIER and cle not in ("type", "galerie")
            }
            bloc = Bloc.objects.create(
                page=page,
                position=position,
                type_bloc=bloc_declare["type"],
                **champs,
            )
            for champ in CHAMPS_FICHIER:
                if bloc_declare.get(champ):
                    self._poser_fichier(bloc, champ, bloc_declare[champ])
            for rang, image in enumerate(bloc_declare.get("galerie", []), start=1):
                illustration = ImageGalerie.objects.create(
                    bloc=bloc, position=rang, legende=image.get("legende", "")
                )
                self._poser_fichier(illustration, "image", image["fichier"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _forcer_skin(self):
        from pages.models import ConfigurationSite

        config = ConfigurationSite.get_solo()
        config.skin = "faire_festival"
        config.save()
        self.stdout.write("  → skin force a 'faire_festival'.")

    def _poser_fichier(self, objet_cible, champ, nom_asset):
        """
        UPLOAD un asset static du skin dans un champ fichier.
        / UPLOADS a static skin asset into a file field.
        """
        # Un nom simple designe une image du skin ; un nom contenant un « / »
        # est un chemin static complet, pour les images qui vivent ailleurs
        # (les logos de partenaires sont dans `contributeurs/`).
        # / A plain name means a skin image; a name containing a "/" is a full
        # static path, for images living elsewhere (partner logos).
        chemin_static = nom_asset if "/" in nom_asset else IMG + nom_asset
        chemin = finders.find(chemin_static)
        if not chemin:
            self.stdout.write(f"  ⚠ asset static introuvable : {nom_asset}")
            return
        with open(chemin, "rb") as fichier:
            getattr(objet_cible, champ).save(
                os.path.basename(nom_asset), File(fichier), save=True
            )
