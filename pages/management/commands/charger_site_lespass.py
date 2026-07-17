"""
Construit une LANDING PAGE UNIQUE de démonstration pour le tenant `lespass` via le
moteur pages (skin classic). Une seule page (l'accueil) qui enchaîne LES 14 TYPES
DE BLOCS dans un flow cohérent — une grande page vitrine.
/ Builds a SINGLE demo LANDING PAGE for the `lespass` tenant via the pages engine
(classic skin). One page (the home) chaining ALL 14 BLOCK TYPES in a coherent flow.

LOCALISATION : pages/management/commands/charger_site_lespass.py

Branché dans les fixtures : appelé par Administration/management/commands/demo_data_v2.py
après le seed du tenant lespass (config + events). Peut aussi être lancé seul :
    python manage.py charger_site_lespass               # tenant "lespass", skin classic
    python manage.py charger_site_lespass --schema=x
    python manage.py charger_site_lespass --no-skin     # ne force pas le skin

Les images sont les belles images génériques du projet (BaseBillet/static/images/
404-N.jpg) UPLOADÉES dans le média du tenant. Le bloc EVENEMENTS est dynamique
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
        # Le bloc IFRAME de démo intègre un formulaire Framaforms : on autorise son
        # hôte dans la whitelist ROOT (sinon le tag iframe_libre n'affiche rien).
        # RootConfiguration est SHARED (schéma public) : on l'écrit hors tenant_context.
        # / The demo IFRAME block embeds a Framaforms form: whitelist its host in the
        # ROOT config (otherwise iframe_libre renders nothing). RootConfiguration is
        # SHARED (public schema): written outside tenant_context.
        self._whitelister_domaine_embed("framaforms.org")

        with tenant_context(tenant):
            from pages.models import Page
            # Nettoyage : on retire les anciennes pages secondaires (multi-pages).
            # / Cleanup: remove the old secondary pages (multi-page version).
            Page.objects.filter(slug__in=ANCIENNES_PAGES).delete()
            self._construire_landing()
            self._construire_sous_menu()
            self._construire_blog()
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

    def _whitelister_domaine_embed(self, domaine):
        """
        Ajoute un domaine à la whitelist ROOT des blocs IFRAME (idempotent).
        / Adds a host to the ROOT whitelist for IFRAME blocks (idempotent).

        RootConfiguration est un singleton SHARED (schéma public). On vide le cache
        django-solo pour que la whitelist soit immédiatement effective.
        / RootConfiguration is a SHARED singleton (public schema). We clear the
        django-solo cache so the whitelist takes effect immediately.
        """
        from django.core.cache import cache
        from root_billet.models import RootConfiguration

        config = RootConfiguration.get_solo()
        lignes = [
            ligne.strip()
            for ligne in (config.domaines_embed_autorises or "").splitlines()
            if ligne.strip()
        ]
        if domaine not in lignes:
            lignes.append(domaine)
            config.domaines_embed_autorises = "\n".join(lignes)
            config.save()
            cache.clear()
            self.stdout.write(f"  → domaine iframe autorisé (ROOT) : {domaine}")

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
            page=a_propos, type_bloc=Bloc.PARAGRAPHE, position=1,
            titre="À propos de Lespass",
            texte=(
                "<p>Lespass est un lieu culturel géré en coopérative d'usage : "
                "adhérent·e·s, bénévoles et salarié·e·s décident ensemble de la "
                "programmation, des tarifs et des grands choix du lieu.</p>"
            ),
        )
        b = Bloc.objects.create(
            page=a_propos, type_bloc=Bloc.IMAGE_TEXTE, position=2,
            image_position=Bloc.GAUCHE, titre="Une gouvernance partagée",
            texte=(
                "<p>Une personne, une voix : chaque adhérent·e peut prendre part aux "
                "assemblées et aux commissions. La coopérative appartient à celles et "
                "ceux qui la font vivre.</p>"
            ),
        )
        self._poser_fichier(b, "image", IMG + "404-7.jpg")
        Bloc.objects.create(
            page=a_propos, type_bloc=Bloc.CTA, position=3,
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
            page=histoire, type_bloc=Bloc.IMAGE, position=1, titre="Notre histoire",
        )
        self._poser_fichier(b, "image", IMG + "404-8.jpg")
        # 2 — Texte brut.
        Bloc.objects.create(
            page=histoire, type_bloc=Bloc.PARAGRAPHE, position=2,
            titre="D'une idée à un lieu",
            texte=(
                "<p>Tout a commencé autour d'une table, avec l'envie d'un groupe "
                "d'habitant·e·s : disposer d'un lieu à soi pour se réunir, créer et "
                "faire vivre la culture localement.</p>"
                "<p>De réunions en chantiers participatifs, le projet a grandi jusqu'à "
                "ouvrir ses portes : une salle, des ateliers, un café associatif — et "
                "une coopérative pour en prendre soin ensemble.</p>"
            ),
        )
        # 3 — Vidéo sous le texte.
        b = Bloc.objects.create(
            page=histoire, type_bloc=Bloc.VIDEO_TEXTE, position=3,
            titre="Le lieu en mouvement",
            texte="<p>Quelques images de la vie quotidienne du lieu.</p>",
        )
        self._poser_fichier(b, "video", VIDEO)

    # ------------------------------------------------------------------
    # Blog de démo : page « Journal » (bloc LISTE_SOUS_PAGES) + 2 articles
    # (blocs MARKDOWN). Vitrine du duo de blocs du CHANTIER-09 : le parent est
    # l'index du blog, les sous-pages sont les articles.
    # / Demo blog: "Journal" page (LISTE_SOUS_PAGES block) + 2 articles
    # (MARKDOWN blocks). Showcases the CHANTIER-09 block duo: the parent is
    # the blog index, the sub-pages are the articles.
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
        # Typage explicite : les sous-pages du journal sont des ARTICLES
        # (signature date/auteur, hors dropdown navbar).
        # / Explicit typing: the journal's sub-pages are ARTICLES.
        journal.est_blog = True
        journal.save()
        Bloc.objects.create(
            page=journal, type_bloc=Bloc.PARAGRAPHE, position=1,
            titre="",
            texte="<p>Ce que l'on fabrique, rate et réussit — raconté au fil "
                  "de l'eau par l'équipe et les bénévoles.</p>",
        )
        Bloc.objects.create(
            page=journal, type_bloc=Bloc.LISTE_SOUS_PAGES, position=2,
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
            page=article_fresque, type_bloc=Bloc.MARKDOWN, position=1,
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
            page=article_repair, type_bloc=Bloc.MARKDOWN, position=1,
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
            bloc(type_bloc=Bloc.PARAGRAPHE, titre=texte)

        # Fond du HERO : image générale du lieu (Configuration.img), lue au rendu
        # par le template (le HERO n'a plus de champ image propre).
        # / HERO background: the venue's general image (Configuration.img), read at
        # render time by the template (the HERO has no own image field anymore).
        from BaseBillet.models import Configuration
        self._poser_fichier(Configuration.get_solo(), "img", IMG + "404-1.jpg")

        # === 1. HERO — bannière d'identité (titre + sous-titre) ===
        bloc(
            type_bloc=Bloc.HERO,
            titre="Bienvenue à Lespass",
            sous_titre="Un lieu culturel coopératif : concerts, ateliers, "
                       "résidences et convivialité — porté par ses adhérent·e·s.",
        )

        # === 1bis. CTA — actions (agenda / adhésions) ===
        bloc(
            type_bloc=Bloc.CTA,
            bouton_label="Voir l'agenda", bouton_url="/event/",
            bouton2_label="Adhérer", bouton2_url="/memberships/",
        )

        # === 2. PARAGRAPHE — présentation ===
        bloc(
            type_bloc=Bloc.PARAGRAPHE,
            titre="Un lieu qui nous appartient",
            texte=(
                "<p>Lespass est un tiers-lieu culturel géré en coopérative : la "
                "programmation, les tarifs et les choix se décident ensemble. On y "
                "vient pour écouter, apprendre, fabriquer et se rencontrer.</p>"
                "<ul><li>Concerts, spectacles et scènes ouvertes</li>"
                "<li>Ateliers, résidences et chantiers participatifs</li>"
                "<li>Un café associatif et un espace de coworking</li></ul>"
            ),
        )

        # === 3. EVENEMENTS — agenda dynamique ===
        bloc(
            type_bloc=Bloc.EVENEMENTS,
            titre="Nos prochains rendez-vous", nombre_max=6,
        )

        # === 4. Le lieu (titre de section) ===
        titre_section("Le lieu")

        # === 5. IMAGE ===
        b = bloc(type_bloc=Bloc.IMAGE, titre="Le lieu")
        self._poser_fichier(b, "image", IMG + "404-6.jpg")

        # === 6-7. IMAGE_TEXTE (alternance G/D) ===
        b = bloc(
            type_bloc=Bloc.IMAGE_TEXTE, image_position=Bloc.GAUCHE,
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
            type_bloc=Bloc.IMAGE_TEXTE, image_position=Bloc.DROITE,
            titre="Des ateliers ouverts",
            texte=(
                "<p>Bois, sérigraphie, couture, électronique : nos ateliers sont "
                "accessibles aux adhérent·e·s, avec accompagnement. On y répare, on y "
                "crée, on y transmet.</p>"
            ),
        )
        self._poser_fichier(b, "image", IMG + "404-8.jpg")

        # === 8. GALERIE ===
        galerie = bloc(type_bloc=Bloc.GALERIE, titre="En images")
        for index, (nom, legende) in enumerate([
            ("404-9.jpg", "La salle de concert"),
            ("404-10.jpg", "Le café associatif"),
            ("404-11.jpg", "Un atelier partagé"),
            ("404-12.jpg", "Le coworking"),
        ], start=1):
            img = ImageGalerie.objects.create(bloc=galerie, position=index, legende=legende)
            self._poser_fichier(img, "image", IMG + nom)

        # === 9. VIDEO_TEXTE (suivi d'un PARAGRAPHE -> pas d'absorption de cartes) ===
        b = bloc(
            type_bloc=Bloc.VIDEO_TEXTE,
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
                type_bloc=Bloc.CARTE, surtitre=surtitre, titre=titre, texte=texte,
                bouton_label=label, bouton_url=url,
            )
            self._poser_fichier(c, "image", IMG + nom)

        # === 12. TEMOIGNAGE ===
        b = bloc(
            type_bloc=Bloc.TEMOIGNAGE,
            texte="J'ai poussé la porte pour un concert, je suis restée pour la "
                  "communauté. Lespass, c'est devenu mon deuxième chez-moi.",
            auteur_nom="Camille Dubreuil", auteur_role="Adhérente depuis 2024",
        )
        self._poser_fichier(b, "auteur_photo", IMG + "404-5.jpg")

        # === 13. EMBED (vidéo PeerTube) ===
        bloc(
            type_bloc=Bloc.EMBED,
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
                type_bloc=Bloc.CARTE, surtitre=surtitre, titre=titre, texte=texte,
                bouton_label="Choisir", bouton_url="/memberships/",
            )
            self._poser_fichier(c, "image", IMG + nom)

        # === 16. CTA ===
        bloc(
            type_bloc=Bloc.CTA,
            titre="Rejoignez la coopérative",
            sous_titre="Toutes les formules sont accessibles en ligne, en quelques clics.",
            bouton_label="Adhérer", bouton_url="/memberships/",
        )

        # === 17. FAQ x3 repliable (accordéon) ===
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
            bloc(type_bloc=Bloc.FAQ, repliable=True, titre=question, texte=reponse)

        # === 18. Infos pratiques (titre de section) ===
        titre_section("Infos pratiques")

        # === 19. INFOS + CARTE_LEAFLET (côte à côte) ===
        bloc(
            type_bloc=Bloc.INFOS,
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
        bloc(
            type_bloc=Bloc.CARTE_LEAFLET,
            badge="LESPASS — 12 RUE DE LA COOPÉRATIVE, 69100 VILLEURBANNE",
            points_gps=[{"lat": 45.7719, "lng": 4.8902, "label": "Lespass"}],
        )

        # === 19bis. IFRAME — contenu intégré libre (formulaire) ===
        # Le bloc IFRAME sert à intégrer un contenu externe à hauteur libre. On
        # l'illustre par un FORMULAIRE, pas par une carte : le bloc CARTE_LEAFLET
        # ci-dessus fait déjà la carte, et le modèle décrit IFRAME comme
        # « formulaire, widget ». L'hôte est autorisé côté ROOT via
        # _whitelister_domaine_embed. Pour une autre intégration, remplacer
        # embed_url et autoriser son domaine dans « Configuration racine →
        # Domaines iframe autorisés ».
        # / The IFRAME block embeds free-height external content, illustrated by a
        # FORM rather than a map (CARTE_LEAFLET above already covers maps, and the
        # model describes IFRAME as "form, widget"). Host whitelisted at ROOT level.
        bloc(
            type_bloc=Bloc.IFRAME,
            titre="Proposer un projet",
            embed_url="https://framaforms.org/",
            hauteur_px=520,
        )

        # === 20. FAQ x3 (non repliable) ===
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
        partenaires = bloc(type_bloc=Bloc.PARTENAIRES, titre="Ils nous soutiennent")
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
            type_bloc=Bloc.NEWSLETTER,
            embed_url="https://ghost.tibillet.coop/",
            titre="Les news de TiBillet",
            sous_titre="La boîte à outils d'organisation collective",
        )

        # === 21. CTA final ===
        bloc(
            type_bloc=Bloc.CTA,
            titre="Prêt·e à nous rejoindre ?",
            sous_titre="L'adhésion est à prix libre et ouvre les portes de la coopérative.",
            bouton_label="Adhérer maintenant", bouton_url="/memberships/",
            bouton2_label="Voir l'agenda", bouton2_url="/event/",
        )
