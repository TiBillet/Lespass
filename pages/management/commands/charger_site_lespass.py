"""
Construit une LANDING PAGE UNIQUE de démonstration pour le tenant `lespass` via le
moteur pages (skin classic). Une seule page (l'accueil) qui enchaîne les 7 types
de blocs et leurs affichages dans un flow cohérent — une grande page vitrine.
/ Builds a SINGLE demo LANDING PAGE for the `lespass` tenant via the pages engine
(classic skin). One page (the home) chaining the 7 block types and their displays.

LOCALISATION : pages/management/commands/charger_site_lespass.py

Branché dans les fixtures : appelé par Administration/management/commands/demo_data_v2.py
après le seed du tenant lespass (config + events). Peut aussi être lancé seul :
    python manage.py charger_site_lespass               # tenant "lespass", skin classic
    python manage.py charger_site_lespass --schema=x
    python manage.py charger_site_lespass --no-skin     # ne force pas le skin

Les images sont les belles images génériques du projet (BaseBillet/static/images/
404-N.jpg) UPLOADÉES dans le média du tenant. Le bloc LISTE est dynamique
(vrais events de lespass). La vidéo EMBED est une vidéo PeerTube (videos-libr.es).
"""

import os

from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Customers.models import Client

IMG = "images/"  # 404-N.jpg (belles images génériques du projet)
VIDEO = "faire_festival/image/motion-table.mp4"  # animation abstraite (réutilisée)

# Slugs des anciennes pages secondaires (version multi-pages) : on les supprime
# puisque tout est désormais sur une seule landing.
# / Slugs of the old secondary pages (multi-page version): removed since everything
# is now on a single landing page.
ANCIENNES_PAGES = ["le-lieu", "programmation", "adhesion", "infos-pratiques"]


class Command(BaseCommand):
    help = "Construit une landing page unique de démo pour lespass (tous les blocs, skin classic)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="lespass")
        parser.add_argument(
            "--no-skin",
            action="store_false",
            dest="skin",
            help="Ne pas forcer le skin classic (laisse le skin actuel).",
        )

    def handle(self, *args, **options):
        schema = options["schema"]
        try:
            tenant = Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            self.stderr.write(f"Tenant introuvable : {schema}")
            return
        with tenant_context(tenant):
            from pages.models import Page
            # Nettoyage : on retire les anciennes pages secondaires (multi-pages).
            # / Cleanup: remove the old secondary pages (multi-page version).
            Page.objects.filter(slug__in=ANCIENNES_PAGES).delete()
            self._construire_landing()
            self._construire_sous_menu()
            self._construire_blog()
            # En dernier : ce bloc pointe vers une page construite juste au-dessus.
            # / Last: this block points at a page built just above.
            self._ajouter_les_derniers_articles_a_l_accueil()
            if options["skin"]:
                self._forcer_skin()
        self.stdout.write(
            f"Landing page + sous-menu + blog de démo chargés sur '{schema}'."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _forcer_skin(self):
        from pages.models import ConfigurationSite

        config = ConfigurationSite.get_solo()
        config.skin = "reunion"  # = gabarits classic
        config.save()
        self.stdout.write("  → skin forcé à 'reunion' (classic).")

    def _autoriser_hote_embed(self, hote):
        """
        Ajoute un hôte à la liste blanche GLOBALE des iframes (config ROOT).
        / Adds a host to the GLOBAL iframe whitelist (ROOT config).

        La liste est partagée par tous les tenants (RootConfiguration vit dans
        le schéma public) : on ajoute une ligne sans jamais écraser les hôtes
        déjà autorisés par le mainteneur.
        / The list is shared across tenants, so we append a line and never
        overwrite hosts the maintainer already allowed.
        """
        from django_tenants.utils import schema_context

        from root_billet.models import RootConfiguration

        with schema_context("public"):
            config = RootConfiguration.get_solo()
            hotes = [ligne.strip() for ligne in config.domaines_embed_autorises.splitlines() if ligne.strip()]
            if hote in hotes:
                return
            hotes.append(hote)
            config.domaines_embed_autorises = "\n".join(hotes)
            config.save()
            self.stdout.write(f"  → hôte iframe autorisé : {hote}")

    def _poser_fichier(self, obj, champ, chemin_static):
        chemin = finders.find(chemin_static)
        if not chemin:
            self.stdout.write(f"  ⚠ asset static introuvable : {chemin_static}")
            return
        nom = os.path.basename(chemin_static)
        with open(chemin, "rb") as fichier:
            getattr(obj, champ).save(nom, File(fichier), save=True)

    def _creer_page(self, slug, titre, position, meta_title, meta_description,
                    parent=None, image_partage=None):
        """Crée/récupère une page (publiée, non-accueil), la nettoie de ses blocs."""
        from pages.models import Page

        page, _cree = Page.objects.get_or_create(slug=slug, defaults={"titre": titre})
        page.titre = titre
        page.position = position
        page.publie = True
        page.est_accueil = False
        page.parent = parent
        page.meta_title = meta_title
        page.meta_description = meta_description
        page.save()
        if image_partage:
            self._poser_fichier(page, "image", IMG + image_partage)
        page.blocs.all().delete()
        return page

    # ------------------------------------------------------------------
    # Sous-menu de démo : page parente « À propos » + sous-page « Notre histoire »
    # (image en en-tête → texte brut → vidéo sous le texte).
    # / Demo sub-menu: parent page "À propos" + sub-page "Notre histoire"
    # (header image → plain text → video below the text).
    # ------------------------------------------------------------------
    def _construire_sous_menu(self):
        from pages.models import Bloc

        # --- Page parente « À propos » (top-level → dropdown dans la navbar) ---
        a_propos = self._creer_page(
            "a-propos", "À propos", 1,
            "À propos de Lespass — le projet coopératif",
            "Découvrez le projet coopératif de Lespass : sa raison d'être, son "
            "fonctionnement et son histoire.",
            image_partage="404-6.jpg",
        )
        Bloc.objects.create(
            page=a_propos, type_bloc=Bloc.TEXTE, position=1,
            titre="À propos de Lespass",
            texte=(
                "Lespass est un lieu culturel géré en coopérative d'usage : "
                "adhérent·e·s, bénévoles et salarié·e·s décident ensemble de la "
                "programmation, des tarifs et des grands choix du lieu.\n"
            ),
        )
        b = Bloc.objects.create(
            page=a_propos, type_bloc=Bloc.SECTION, affichage=Bloc.TEXTE_IMAGE_GAUCHE, position=2, titre="Une gouvernance partagée",
            texte=(
                "<p>Une personne, une voix : chaque adhérent·e peut prendre part aux "
                "assemblées et aux commissions. La coopérative appartient à celles et "
                "ceux qui la font vivre.</p>"
            ),
        )
        self._poser_fichier(b, "image", IMG + "404-7.jpg")
        Bloc.objects.create(
            page=a_propos, type_bloc=Bloc.SECTION, affichage=Bloc.APPEL_ACTION, position=3,
            titre="Envie de participer ?",
            sous_titre="Rejoignez la coopérative et prenez part aux décisions.",
            bouton_label="Adhérer", bouton_url="/memberships/",
        )

        # --- Sous-page « Notre histoire » : image en-tête → texte → vidéo ---
        histoire = self._creer_page(
            "notre-histoire", "Notre histoire", 1,
            "Notre histoire — Lespass",
            "L'histoire de Lespass : de l'idée d'un collectif d'habitant·e·s à un "
            "tiers-lieu culturel coopératif.",
            parent=a_propos, image_partage="404-8.jpg",
        )
        # 1 — Image en en-tête.
        b = Bloc.objects.create(
            page=histoire, type_bloc=Bloc.IMAGES, affichage=Bloc.PLEINE_LARGEUR, position=1, titre="Notre histoire",
        )
        self._poser_fichier(b, "image", IMG + "404-8.jpg")
        # 2 — Texte brut.
        Bloc.objects.create(
            page=histoire, type_bloc=Bloc.TEXTE, position=2,
            titre="D'une idée à un lieu",
            texte=(
                "Tout a commencé autour d'une table, avec l'envie d'un groupe "
                "d'habitant·e·s : disposer d'un lieu à soi pour se réunir, créer et "
                "faire vivre la culture localement.\n\n"
                "De réunions en chantiers participatifs, le projet a grandi jusqu'à "
                "ouvrir ses portes : une salle, des ateliers, un café associatif — et "
                "une coopérative pour en prendre soin ensemble.\n"
            ),
        )
        # 3 — Vidéo sous le texte.
        b = Bloc.objects.create(
            page=histoire, type_bloc=Bloc.SECTION, affichage=Bloc.TEXTE_VIDEO, position=3,
            titre="Le lieu en mouvement",
            texte="<p>Quelques images de la vie quotidienne du lieu.</p>",
        )
        self._poser_fichier(b, "video", VIDEO)

    # ------------------------------------------------------------------
    # Journal de démo : une page index portant un bloc LISTE sur ses
    # sous-pages, et 2 sous-pages portant chacune un bloc TEXTE (l'article).
    # / Demo journal: an index page carrying a LISTE block over its sub-pages,
    # and 2 sub-pages each carrying a TEXTE block (the article).
    # ------------------------------------------------------------------
    def _construire_blog(self):
        from pages.models import Bloc

        journal = self._creer_page(
            "journal", "Journal", 2,
            "Journal — les nouvelles du lieu",
            "Les nouvelles du lieu : récits d'ateliers, coulisses et "
            "annonces de la coopérative, publiés au fil de l'eau.",
            image_partage="404-2.jpg",
        )
        Bloc.objects.create(
            page=journal, type_bloc=Bloc.TEXTE, position=1,
            titre="",
            texte="Ce que l'on fabrique, rate et réussit — raconté au fil "
                  "de l'eau par l'équipe et les bénévoles.\n",
        )
        Bloc.objects.create(
            page=journal, type_bloc=Bloc.LISTE, source=Bloc.SOUS_PAGES, position=2,
            titre="Derniers articles", nombre_max=6,
        )

        article_fresque = self._creer_page(
            "atelier-fresque-participative", "Une fresque participative sur le mur du hangar",
            1,
            "Une fresque participative sur le mur du hangar",
            "Trois week-ends, quarante paires de mains et beaucoup de peinture : "
            "récit de la fresque participative du hangar.",
            parent=journal, image_partage="404-3.jpg",
        )
        bloc_fresque = Bloc.objects.create(
            page=article_fresque, type_bloc=Bloc.TEXTE, position=1,
            texte=(
                "Trois week-ends, quarante paires de mains, et un mur de vingt "
                "mètres qui ne ressemble plus à rien de ce qu'il était.\n\n"
                "![La fresque terminée, un samedi de juin](galerie:1)\n\n"
                "## Comment on s'est organisés\n\n"
                "- **Week-end 1** : nettoyage du mur et sous-couche, ouvert à "
                "toutes et tous.\n"
                "- **Week-end 2** : report du dessin à la craie, par carrés "
                "numérotés.\n"
                "- **Week-end 3** : mise en couleur, du sol à la nacelle.\n\n"
                "> « Je n'avais jamais tenu un pinceau plus grand que ma main. "
                "Maintenant il y a un morceau de mur qui est à moi. » — Nadia, "
                "bénévole\n\n"
                "## Ce qu'on referait autrement\n\n"
                "Prévoir plus de bâches. Vraiment. Le reste — la cantine "
                "partagée, les enfants aux pochoirs, la playlist commune — "
                "était parfait.\n\n"
                "Envie de proposer le prochain chantier ? Passez nous voir ou "
                "écrivez-nous depuis la page [contact](/#contact)."
            ),
        )
        # Image d'illustration de l'article, référencée dans le markdown via
        # ![légende](galerie:1). / Article illustration image, referenced in
        # the markdown via ![caption](galerie:1).
        from pages.models import ImageGalerie
        illustration = ImageGalerie.objects.create(
            bloc=bloc_fresque, position=1, legende="La fresque terminée",
        )
        self._poser_fichier(illustration, "image", IMG + "404-5.jpg")

        article_repair = self._creer_page(
            "repair-cafe-bilan-un-an", "Repair café : le bilan après un an",
            2,
            "Repair café : le bilan après un an",
            "127 objets sauvés de la benne en douze rencontres : chiffres et "
            "leçons d'un an de repair café mensuel.",
            parent=journal, image_partage="404-4.jpg",
        )
        Bloc.objects.create(
            page=article_repair, type_bloc=Bloc.TEXTE, position=1,
            texte=(
                "Un samedi par mois depuis un an, l'atelier se remplit de "
                "grille-pain muets, de vélos qui grincent et de lampes "
                "capricieuses. Bilan chiffré de la première saison.\n\n"
                "## Les chiffres\n\n"
                "| | Apportés | Réparés | Taux |\n"
                "|---|---|---|---|\n"
                "| Petit électroménager | 84 | 61 | 73 % |\n"
                "| Vélos | 37 | 34 | 92 % |\n"
                "| Textile | 41 | 32 | 78 % |\n\n"
                "**127 objets** sont repartis en état de marche — autant qui "
                "ne finissent pas à la benne.\n\n"
                "## Ce qui fait que ça marche\n\n"
                "1. Le café est gratuit, la réparation se fait *avec* vous, "
                "jamais à votre place.\n"
                "2. Les pannes reviennent souvent aux mêmes causes : on "
                "affiche désormais les plus courantes à l'entrée.\n"
                "3. Les adhérent·es de la coopérative prêtent l'outillage "
                "spécialisé d'un mois sur l'autre.\n\n"
                "Prochaine session : voir [l'agenda](/event/)."
            ),
        )

    def _ajouter_les_derniers_articles_a_l_accueil(self):
        """
        Pose sur l'accueil un bloc LISTE qui affiche les articles du journal.
        / Adds a LISTE block on the home page showing the journal's articles.

        Ce bloc demontre le champ `page_source` : une LISTE de sous-pages
        affiche par defaut les enfants de SA page, mais l'accueil n'en a pas.
        En pointant le journal, l'accueil relaie ses articles.
        Il se pose apres coup, parce que la page journal n'existe pas encore au
        moment ou la landing est construite.
        / This block demonstrates the `page_source` field: a sub-pages LISTE
        shows its own page's children by default, but the home page has none.
        Pointing at the journal makes the home page relay its articles. It is
        added afterwards because the journal does not exist yet when the landing
        is built.
        """
        from pages.models import Bloc, Page

        accueil = Page.objects.filter(est_accueil=True).first()
        journal = Page.objects.filter(slug="journal").first()
        if accueil is None or journal is None:
            return

        # Le bloc s'insere AVANT le dernier bloc de la page, qui est l'appel a
        # l'action final : une vitrine se termine sur son invitation, pas sur
        # une liste d'articles. On decale donc ce dernier bloc d'un cran.
        # / The block goes in BEFORE the page's last block, the final call to
        # action: a showcase ends on its invitation, not on a list of articles.
        # So we push that last block one step down.
        dernier = accueil.blocs.order_by("-position").first()
        position_du_journal = dernier.position
        dernier.position += 1
        dernier.save(update_fields=["position"])

        Bloc.objects.create(
            page=accueil,
            position=position_du_journal,
            type_bloc=Bloc.LISTE,
            source=Bloc.SOUS_PAGES,
            page_source=journal,
            titre="Le journal du lieu",
            nombre_max=3,
        )

    # ------------------------------------------------------------------
    # La landing unique
    # ------------------------------------------------------------------
    def _construire_landing(self):
        from pages.models import Bloc, ImageGalerie, Page

        page, _cree = Page.objects.get_or_create(
            slug="accueil", defaults={"titre": "Accueil"}
        )
        page.titre = "Accueil"
        page.position = 0
        page.publie = True
        page.est_accueil = True
        page.meta_title = "Lespass — concerts, ateliers et adhésion coopérative"
        page.meta_description = (
            "Lespass, lieu culturel coopératif : programmation de concerts et "
            "d'ateliers, adhésion à prix libre et coopérative ouverte à toutes et tous."
        )
        page.save()
        self._poser_fichier(page, "image", IMG + "404-1.jpg")  # image de partage SEO
        page.blocs.all().delete()

        etat = {"n": 0}

        def suivant():
            etat["n"] += 1
            return etat["n"]

        def bloc(**kwargs):
            return Bloc.objects.create(page=page, position=suivant(), **kwargs)

        def titre_section(texte):
            bloc(type_bloc=Bloc.TEXTE, titre=texte)

        # Fond du HERO : image générale du lieu (Configuration.img), lue au rendu
        # par le template (le HERO n'a plus de champ image propre).
        # / HERO background: the venue's general image (Configuration.img), read at
        # render time by the template (the HERO has no own image field anymore).
        from BaseBillet.models import Configuration
        self._poser_fichier(Configuration.get_solo(), "img", IMG + "404-1.jpg")

        # === 1. HERO — bannière d'identité (titre + sous-titre) ===
        bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.BANNIERE,
            titre="Bienvenue à Lespass",
            sous_titre="Un lieu culturel coopératif : concerts, ateliers, "
                       "résidences et convivialité — porté par ses adhérent·e·s.",
        )

        # === 1bis. CTA — actions (agenda / adhésions) ===
        bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.APPEL_ACTION,
            bouton_label="Voir l'agenda", bouton_url="/event/",
            bouton2_label="Adhérer", bouton2_url="/memberships/",
        )

        # === 2. TEXTE — présentation ===
        bloc(
            type_bloc=Bloc.TEXTE,
            titre="Un lieu qui nous appartient",
            texte=(
                "Lespass est un tiers-lieu culturel géré en coopérative : la "
                "programmation, les tarifs et les choix se décident ensemble. On y "
                "vient pour écouter, apprendre, fabriquer et se rencontrer.\n\n"
                "- Concerts, spectacles et scènes ouvertes\n"
                "- Ateliers, résidences et chantiers participatifs\n"
                "- Un café associatif et un espace de coworking\n"
            ),
        )

        # === 3. EVENEMENTS — agenda dynamique ===
        bloc(
            type_bloc=Bloc.LISTE, source=Bloc.EVENEMENTS,
            titre="Nos prochains rendez-vous", nombre_max=6,
        )

        # === 4. Le lieu (titre de section) ===
        titre_section("Le lieu")

        # === 5. IMAGE ===
        b = bloc(type_bloc=Bloc.IMAGES, affichage=Bloc.PLEINE_LARGEUR, titre="Le lieu")
        self._poser_fichier(b, "image", IMG + "404-6.jpg")

        # === 6-7. IMAGE_TEXTE (alternance G/D) ===
        b = bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.TEXTE_IMAGE_GAUCHE,
            titre="Une salle modulable",
            texte=(
                "<p>Concerts assis ou debout, conférences, projections : la salle "
                "s'adapte. Une régie son et lumière complète permet d'accueillir des "
                "artistes en résidence.</p>"
            ),
            bouton_label="Voir l'agenda", bouton_url="/event/",
        )
        self._poser_fichier(b, "image", IMG + "404-7.jpg")
        b = bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.TEXTE_IMAGE_DROITE,
            titre="Des ateliers ouverts",
            texte=(
                "<p>Bois, sérigraphie, couture, électronique : nos ateliers sont "
                "accessibles aux adhérent·e·s, avec accompagnement. On y répare, on y "
                "crée, on y transmet.</p>"
            ),
        )
        self._poser_fichier(b, "image", IMG + "404-8.jpg")

        # === 7 bis. SECTION composee : media + texte + sous-cartes ===
        # Les sous-cartes vivent dans le champ `contenu` du bloc, en donnees
        # texte : elles se rangent DANS la colonne de la section, la ou des
        # blocs CARTE voisins se rangeraient a cote d'elle.
        # / Composed SECTION: media + text + sub-cards. The sub-cards live in the
        # block's `contenu` field as text data, laid out INSIDE the section's
        # column — where neighbouring CARTE blocks would sit beside it.
        b = bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.MEDIA_ET_CARTES,
            titre="Une semaine à Lespass",
            texte=(
                "Chaque jour a sa couleur : on répare le mardi, on répète le "
                "jeudi, on danse le samedi."
            ),
            contenu=[
                {"titre": "Mardi", "badge": "Atelier",
                 "texte": "Repair café : on démonte, on diagnostique, on répare."},
                {"titre": "Jeudi", "badge": "Répétition",
                 "texte": "La scène est ouverte aux groupes du quartier."},
                {"titre": "Samedi", "badge": "Concert",
                 "texte": "Programmation locale, tarif libre pour les adhérent·e·s."},
            ],
        )
        self._poser_fichier(b, "image", IMG + "404-9.jpg")

        # === 7 ter. IMAGES / VIGNETTE_TITRE : image-titre centree ===
        b = bloc(
            type_bloc=Bloc.IMAGES, affichage=Bloc.VIGNETTE_TITRE,
            titre="Notre affiche de saison",
        )
        self._poser_fichier(b, "image", IMG + "404-10.jpg")

        # === 8. GALERIE ===
        # Images distinctes de celles deja posees plus haut (404-9 sur la section
        # composee, 404-10 sur la vignette-titre) : une galerie qui repete les
        # visuels de la page donne l'impression d'un fonds d'images pauvre.
        # / Images distinct from those used above: a gallery repeating the page's
        # visuals makes the image library look thin.
        galerie = bloc(type_bloc=Bloc.IMAGES, affichage=Bloc.GRILLE, titre="En images")
        for index, (nom, legende) in enumerate([
            ("404-17.jpg", "La salle de concert"),
            ("404-18.jpg", "Le café associatif"),
            ("404-19.jpg", "Un atelier partagé"),
            ("404-20.jpg", "Le coworking"),
        ], start=1):
            img = ImageGalerie.objects.create(bloc=galerie, position=index, legende=legende)
            self._poser_fichier(img, "image", IMG + nom)

        # === 9. VIDEO_TEXTE (suivi d'un PARAGRAPHE -> pas d'absorption de cartes) ===
        b = bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.TEXTE_VIDEO,
            titre="Le lieu en mouvement",
            texte=(
                "<p>Une minute pour ressentir l'ambiance des soirs de concert : "
                "les lumières, la scène, le public.</p>"
            ),
        )
        self._poser_fichier(b, "video", VIDEO)

        # === 10. Activités (titre de section) ===
        titre_section("Trois bonnes raisons de venir")

        # === 11. CARTE x3 -> grille ===
        for nom, surtitre, titre, texte, label, url in [
            ("404-2.jpg", "01", "Apprendre",
             "Des formateur·rice·s passionné·e·s, à votre rythme.", "Les cours", "/event/"),
            ("404-3.jpg", "02", "Fabriquer",
             "Un parc de machines accessible aux membres.", "Le matériel", "/event/"),
            ("404-4.jpg", "03", "Partager",
             "Une communauté qui documente et transmet.", "La communauté", "/federation/"),
        ]:
            c = bloc(
                type_bloc=Bloc.SECTION, affichage=Bloc.CARTE, sous_titre=surtitre, titre=titre, texte=texte,
                bouton_label=label, bouton_url=url,
            )
            self._poser_fichier(c, "image", IMG + nom)

        # === 12. TEMOIGNAGE ===
        b = bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.CITATION,
            texte="J'ai poussé la porte pour un concert, je suis restée pour la "
                  "communauté. Lespass, c'est devenu mon deuxième chez-moi.",
            auteur_nom="Camille Dubreuil", auteur_role="Adhérente depuis 2024",
        )
        self._poser_fichier(b, "auteur_photo", IMG + "404-5.jpg")

        # === 13. EMBED (vidéo PeerTube) ===
        bloc(
            type_bloc=Bloc.INTEGRATION, affichage=Bloc.VIDEO,
            titre="Découvrir le projet en vidéo",
            embed_url="https://videos-libr.es/w/r2XVKcqhLPVBDujoMVrTcF",
        )

        # === 14. Adhésion (titre de section) ===
        titre_section("Soutenir Lespass")

        # === 15. CARTE x4 -> grille (formules d'adhésion) ===
        for nom, surtitre, titre, texte in [
            ("404-13.jpg", "Association", "Adhésion associative",
             "À prix libre (plein, solidaire), pour soutenir le lieu toute l'année."),
            ("404-14.jpg", "Alimentation", "Caisse alimentaire (SSA)",
             "Une cotisation mensuelle à prix libre pour une alimentation choisie."),
            ("404-15.jpg", "Panier", "Panier AMAP",
             "Recevez chaque semaine un panier de producteur·rice·s local·e·s."),
            ("404-16.jpg", "Coopérative", "Parts de coopérative",
             "Devenez sociétaire et participez à la gouvernance du projet."),
        ]:
            c = bloc(
                type_bloc=Bloc.SECTION, affichage=Bloc.CARTE, sous_titre=surtitre, titre=titre, texte=texte,
                bouton_label="Choisir", bouton_url="/memberships/",
            )
            self._poser_fichier(c, "image", IMG + nom)

        # === 16. CTA ===
        bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.APPEL_ACTION,
            titre="Rejoignez la coopérative",
            sous_titre="Toutes les formules sont accessibles en ligne, en quelques clics.",
            bouton_label="Adhérer", bouton_url="/memberships/",
        )

        # === 17. FAQ x3 (accordéon) ===
        for question, reponse in [
            ("Faut-il être adhérent·e pour venir ?",
             "<p>Non, la plupart des événements sont ouverts à tou·te·s. L'adhésion "
             "donne accès à des tarifs réduits et au vote en assemblée.</p>"),
            ("L'adhésion est-elle vraiment à prix libre ?",
             "<p>Oui. Vous choisissez le montant qui vous convient ; un tarif "
             "solidaire est proposé pour les petits budgets.</p>"),
            ("Puis-je résilier à tout moment ?",
             "<p>Les adhésions annuelles courent sur l'année ; les souscriptions "
             "mensuelles peuvent être arrêtées dans le respect de l'engagement initial.</p>"),
        ]:
            bloc(type_bloc=Bloc.FAQ, titre=question, texte=reponse)

        # === 18. Infos pratiques (titre de section) ===
        titre_section("Infos pratiques")

        # === 19. LIEU : infos pratiques et carte côte à côte ===
        # UN SEUL bloc porte les deux colonnes : `contenu` remplit la colonne de
        # gauche, `badge` + `points_gps` la carte de droite. Deux blocs LIEU
        # separes donneraient deux sections a moitie vides.
        # / A SINGLE block carries both columns: `contenu` fills the left one,
        # `badge` + `points_gps` the right-hand map. Two separate LIEU blocks
        # would render as two half-empty sections.
        bloc(
            type_bloc=Bloc.LIEU,
            badge="LESPASS — 12 RUE DE LA COOPÉRATIVE, 69100 VILLEURBANNE",
            points_gps=[{"lat": 45.7719, "lng": 4.8902, "label": "Lespass"}],
            contenu=[
                {"type": "badge", "texte": "Nous trouver"},
                {"type": "para", "texte": "Au cœur de Villeurbanne, accès facile en transports."},
                {"type": "horaire", "texte": "MERCREDI → SAMEDI 14h → 23h"},
                {"type": "badge", "texte": "Adresse"},
                {"type": "adresse", "texte": "Lespass\n12 rue de la Coopérative\n69100 Villeurbanne"},
                {"type": "accessibilite", "texte": "Lieu accessible aux personnes à mobilité réduite."},
                {"type": "transport", "titre": "MÉTRO / TRAM", "lignes": [
                    "Métro A — arrêt République (5 min à pied)",
                    "Tram T3 — arrêt Reconnaissance Balzac (8 min à pied)",
                ]},
                {"type": "transport", "titre": "VÉLO", "lignes": [
                    "Station Vélo'v devant le lieu",
                    "Arceaux de stationnement dans la cour",
                ]},
            ],
        )

        # === 19 bis. INTEGRATION / WIDGET : contenu externe libre ===
        # Un iframe libre n'est rendu que si son HÔTE figure dans la liste
        # blanche globale du ROOT ; sinon le gabarit affiche un message
        # d'indisponibilité. La démo autorise donc `openstreetmap.org`
        # (cf. _autoriser_hote_embed) pour montrer le bloc en fonctionnement
        # plutôt qu'un message d'erreur.
        # / A free iframe only renders if its HOST is in the ROOT global
        # whitelist; otherwise the template shows an unavailability message. The
        # demo therefore whitelists `openstreetmap.org` to show the block
        # working rather than an error.
        self._autoriser_hote_embed("www.openstreetmap.org")
        bloc(
            type_bloc=Bloc.INTEGRATION, affichage=Bloc.WIDGET,
            titre="Nous situer sur la carte",
            embed_url=(
                "https://www.openstreetmap.org/export/embed.html"
                "?bbox=4.878%2C45.766%2C4.902%2C45.778&layer=mapnik"
            ),
            hauteur_px=420,
        )

        # === 20. FAQ x3 ===
        for question, reponse in [
            ("Y a-t-il un bar / une restauration ?",
             "<p>Oui, un café associatif propose boissons et petite restauration les "
             "soirs d'événement.</p>"),
            ("Peut-on privatiser le lieu ?",
             "<p>La salle et les ateliers peuvent être réservés pour des événements "
             "associatifs ou professionnels. Contactez-nous.</p>"),
            ("Comment devenir bénévole ?",
             "<p>Passez nous voir ou écrivez-nous : il y a toujours de quoi "
             "contribuer, selon vos envies et votre temps.</p>"),
        ]:
            bloc(type_bloc=Bloc.FAQ, titre=question, texte=reponse)

        # === 20bis. PARTENAIRES — bande de logos cliquables (nouveau bloc) ===
        # Logos « contributeurs » réutilisés de la landing ROOT (static/contributeurs/).
        # PNG/JPG uniquement : StdImageField génère des variations via Pillow, qui ne
        # sait pas redimensionner un SVG. lien_url renseigné = logo cliquable.
        # / Partner logos reused from the ROOT landing. PNG/JPG only (Pillow can't
        # resize SVG). A set lien_url makes the logo clickable.
        partenaires = bloc(type_bloc=Bloc.IMAGES, affichage=Bloc.BANDE_LOGOS, titre="Ils nous soutiennent")
        for index, (fichier, legende, lien) in enumerate([
            ("ftl.png", "France Tiers-Lieux", "https://francetierslieux.fr"),
            ("coopcircuit-noir.png", "CoopCircuits", "https://coopcircuits.fr"),
            ("jet_brain_beam.png", "JetBrains", "https://www.jetbrains.com"),
            ("france_2030.png", "France 2030", "https://www.info.gouv.fr/france-2030"),
            ("circa.png", "Circa", ""),
            ("Demeter.png", "Demeter", ""),
        ], start=1):
            logo = ImageGalerie.objects.create(
                bloc=partenaires, position=index, legende=legende, lien_url=lien,
            )
            self._poser_fichier(logo, "image", "contributeurs/" + fichier)

        # === 20ter. NEWSLETTER — inscription Ghost (nouveau bloc) ===
        # Formulaire d'inscription à la newsletter TiBillet. Le script Ghost est
        # vendorisé (zéro CDN) ; embed_url = l'instance Ghost (data-site).
        # / Ghost newsletter signup. Vendored script; embed_url = the Ghost instance.
        bloc(
            type_bloc=Bloc.INTEGRATION, affichage=Bloc.NEWSLETTER,
            embed_url="https://ghost.tibillet.coop/",
            titre="Les news de TiBillet",
            sous_titre="La boîte à outils d'organisation collective",
        )

        # === 21. CTA final ===
        bloc(
            type_bloc=Bloc.SECTION, affichage=Bloc.APPEL_ACTION,
            titre="Prêt·e à nous rejoindre ?",
            sous_titre="L'adhésion est à prix libre et ouvre les portes de la coopérative.",
            bouton_label="Adhérer maintenant", bouton_url="/memberships/",
            bouton2_label="Voir l'agenda", bouton2_url="/event/",
        )
