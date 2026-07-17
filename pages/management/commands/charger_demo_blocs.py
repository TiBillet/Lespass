"""
Charge une page d'accueil de DEMO contenant TOUS les types de blocs, pour faire
la revue visuelle du skin "classic". Couvre les 11 types de bloc et les 5 types
de groupe (solo, grille, section_video, faq, section_carte).
/ Loads a DEMO home page containing EVERY block type, to visually review the
"classic" skin. Covers the 11 block types and the 5 group types.

LOCALISATION : pages/management/commands/charger_demo_blocs.py

Usage :
    python manage.py charger_demo_blocs                 # tenant "festival", skin classic
    python manage.py charger_demo_blocs --schema=mon_tenant
    python manage.py charger_demo_blocs --no-skin       # ne force pas le skin

Les images/video sont UPLOADEES dans le media du tenant (vrai moteur d'upload)
via _poser_fichier : on lit l'asset static et on l'enregistre dans le champ du
bloc (les StdImageField generent leurs variations).
/ Images/video are UPLOADED into the tenant media via _poser_fichier.
"""

import os

from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Customers.models import Client

# Prefixe des images static reutilisees pour la demo.
# / Prefix of the static images reused for the demo.
IMG = "faire_festival/image/"


class Command(BaseCommand):
    help = "Charge une page d'accueil de demo avec tous les types de blocs (skin classic)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="festival")
        # Par defaut on force le skin "reunion" (= gabarits classic) pour la revue.
        # --no-skin laisse le skin existant intact.
        # / By default we force the "reunion" skin (= classic templates) for the
        # review. --no-skin keeps the existing skin untouched.
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
            self._charger_accueil_demo()
            self._charger_groupement_demo()
            if options["skin"]:
                self._forcer_skin()
        self.stdout.write(
            f"Pages de demo (tous les blocs + cas limites de groupement) "
            f"chargees sur '{schema}'."
        )

    # ------------------------------------------------------------------
    # Helper : force le skin "reunion" (gabarits classic) sur le tenant.
    # / Helper: force the "reunion" skin (classic templates) on the tenant.
    # ------------------------------------------------------------------
    def _forcer_skin(self):
        from pages.models import ConfigurationSite

        config = ConfigurationSite.get_solo()
        config.skin = "reunion"
        config.save()
        self.stdout.write("  → skin force a 'reunion' (classic).")

    # ------------------------------------------------------------------
    # Helper : UPLOAD d'un asset static dans un champ image/fichier du bloc.
    # / Helper: UPLOAD a static asset into a block image/file field.
    # ------------------------------------------------------------------
    def _poser_fichier(self, bloc, champ, chemin_static):
        chemin = finders.find(chemin_static)
        if not chemin:
            self.stdout.write(f"  ⚠ asset static introuvable : {chemin_static}")
            return
        nom = os.path.basename(chemin_static)
        with open(chemin, "rb") as fichier:
            getattr(bloc, champ).save(nom, File(fichier), save=True)

    def _charger_groupement_demo(self):
        """
        2e page : CAS LIMITES du groupement (grouper_blocs). Chaque cas est précédé
        d'un PARAGRAPHE-titre qui sert d'étiquette pour la revue visuelle.
        / 2nd page: grouping EDGE CASES. Each case is preceded by a PARAGRAPH-title
        used as a label for the visual review.
        """
        from pages.models import Bloc, Page

        page, _cree = Page.objects.get_or_create(
            slug="demo-groupement", defaults={"titre": "Démo — groupement"}
        )
        page.titre = "Démo — groupement de blocs"
        page.position = 1
        page.publie = True
        page.est_accueil = False
        page.meta_description = (
            "Page de démonstration des cas limites de groupement des blocs "
            "(grille de 1, INFOS seul, carte seule, FAQ impaire…)."
        )
        page.save()
        page.blocs.all().delete()

        pos = 0

        def suivant():
            nonlocal pos
            pos += 1
            return pos

        def etiquette(texte):
            Bloc.objects.create(
                page=page, type_bloc=Bloc.PARAGRAPHE, position=suivant(), titre=texte,
            )

        def une_carte(titre, texte):
            b = Bloc.objects.create(
                page=page, type_bloc=Bloc.CARTE, position=suivant(),
                surtitre="Atelier", titre=titre, texte=texte,
            )
            self._poser_fichier(b, "image", IMG + "photo_tutos-07.webp")

        # CAS 1 — Grille de 1 (une seule CARTE).
        etiquette("Cas : grille d'une seule carte")
        une_carte("Carte unique", "Une carte seule ne doit pas s'étirer sur toute la largeur.")

        # CAS 2 — Grille de 2 (deux CARTE consécutives).
        etiquette("Cas : grille de deux cartes")
        une_carte("Première carte", "Deux cartes côte à côte.")
        une_carte("Deuxième carte", "La grille s'équilibre.")

        # CAS 3 — INFOS SEUL (sans carte Leaflet à la suite) -> bloc solo.
        etiquette("Cas : bloc INFOS seul (sans carte)")
        Bloc.objects.create(
            page=page, type_bloc=Bloc.INFOS, position=suivant(),
            contenu=[
                {"type": "badge", "texte": "Horaires"},
                {"type": "horaire", "texte": "MARDI → SAMEDI 10h → 19h"},
                {"type": "adresse", "texte": "La Cité\n55 avenue Louis Breguet\n31400 Toulouse"},
            ],
        )

        # CAS 4 — CARTE_LEAFLET SEULE (sans INFOS avant) -> bloc solo.
        etiquette("Cas : carte Leaflet seule (sans INFOS)")
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE_LEAFLET, position=suivant(),
            badge="LA CITÉ — TOULOUSE",
            points_gps=[{"lat": 43.5568, "lng": 1.4835, "label": "La Cité"}],
        )

        # CAS 5 — VIDEO_TEXTE SEULE (sans cartes ni CTA à la suite).
        etiquette("Cas : vidéo + texte seule (sans cartes ni CTA)")
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.VIDEO_TEXTE, position=suivant(),
            titre="Vidéo sans cartes",
            texte="<p>Une section vidéo qui n'absorbe aucune carte ni bouton.</p>",
        )
        self._poser_fichier(b, "video", IMG + "motion-table.mp4")

        # CAS 6 — FAQ IMPAIRE (3 questions) -> équilibrage 2 colonnes.
        etiquette("Cas : FAQ impaire (3 questions)")
        for i in range(1, 4):
            Bloc.objects.create(
                page=page, type_bloc=Bloc.FAQ, position=suivant(),
                titre=f"Question impaire n°{i} ?",
                texte=f"<p>Réponse à la question {i}. Le découpage en deux colonnes "
                      f"doit rester équilibré avec un nombre impair.</p>",
            )

        # CAS 7 — FAQ REPLIABLE (accordéon <details>).
        etiquette("Cas : FAQ repliable (accordéon)")
        for i in range(1, 4):
            Bloc.objects.create(
                page=page, type_bloc=Bloc.FAQ, position=suivant(),
                repliable=True,
                titre=f"Question repliable n°{i} ?",
                texte=f"<p>Réponse {i}, repliée par défaut, qui s'ouvre au clic "
                      f"(accordéon natif, accessible, sans JavaScript).</p>",
            )

    def _charger_accueil_demo(self):
        from pages.models import Bloc, ImageGalerie, Page

        page, _cree = Page.objects.get_or_create(
            slug="accueil", defaults={"titre": "Accueil"}
        )
        page.titre = "Démo — tous les blocs"
        page.position = 0
        page.publie = True
        page.est_accueil = True
        page.meta_title = "Démo des blocs TiBillet — thème classic"
        page.meta_description = (
            "Page de démonstration présentant tous les types de blocs du moteur "
            "de pages TiBillet, rendus avec le thème classic."
        )
        page.save()
        # Image de partage SEO (og:image) de la page.
        # / Page SEO share image (og:image).
        self._poser_fichier(page, "image", IMG + "logopage.webp")
        page.blocs.all().delete()

        pos = 0

        def suivant():
            nonlocal pos
            pos += 1
            return pos

        # Fond du HERO : image générale du lieu (Configuration.img), lue au rendu
        # (le HERO n'a plus de champ image propre).
        # / HERO background: the venue's general image (Configuration.img).
        from BaseBillet.models import Configuration
        self._poser_fichier(Configuration.get_solo(), "img", IMG + "fond.png")

        # 1 — HERO (solo) : bannière d'identité (titre + sous-titre).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.HERO, position=suivant(),
            titre="La Cité des Faiseuses",
            sous_titre="Un tiers-lieu coopératif pour fabriquer, apprendre et "
                       "transmettre — au cœur de la ville.",
        )

        # 1bis — CTA (solo) : actions (agenda / adhésions).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CTA, position=suivant(),
            bouton_label="Voir l'agenda", bouton_url="/event/",
            bouton2_label="Adhérer", bouton2_url="/memberships/",
        )

        # 2 — PARAGRAPHE (solo) : titre + texte riche (paragraphes + liste).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.PARAGRAPHE, position=suivant(),
            titre="Notre raison d'être",
            texte=(
                "<p>Nous croyons qu'apprendre à faire soi-même change le rapport au "
                "monde. Chaque semaine, des dizaines de personnes se retrouvent ici "
                "pour réparer, coudre, souder, imprimer en 3D et partager leurs "
                "savoir-faire.</p>"
                "<p>Notre lieu est ouvert à toutes et à tous, débutant·e·s comme "
                "expert·e·s. On y vient pour :</p>"
                "<ul><li>apprendre une nouvelle technique ;</li>"
                "<li>réparer plutôt que jeter ;</li>"
                "<li>rencontrer une communauté curieuse et bienveillante.</li></ul>"
            ),
        )

        # 3 — IMAGE_TEXTE (solo) : image à gauche + texte + bouton.
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE_TEXTE, position=suivant(),
            image_position=Bloc.GAUCHE,
            titre="Des ateliers toute l'année",
            texte=(
                "<p>De la menuiserie à l'électronique, nos ateliers couvrent plus de "
                "vingt thématiques. Inscrivez-vous à la séance qui vous tente : le "
                "matériel et l'accompagnement sont fournis.</p>"
            ),
            bouton_label="Découvrir les ateliers", bouton_url="/event/",
        )
        self._poser_fichier(b, "image", IMG + "Fichier-15.webp")

        # 4 — IMAGE_TEXTE (solo) : image à droite + texte (alternance).
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE_TEXTE, position=suivant(),
            image_position=Bloc.DROITE,
            titre="Un projet coopératif",
            texte=(
                "<p>Le lieu est porté par une coopérative d'usage : les membres "
                "décident ensemble de la programmation, des tarifs et des "
                "investissements. Adhérer, c'est prendre part à l'aventure.</p>"
            ),
        )
        self._poser_fichier(b, "image", IMG + "Fichier-16.webp")

        # 5 — IMAGE (solo) : image seule, centrée (image-titre de section).
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE, position=suivant(),
            titre="Galerie",
        )
        self._poser_fichier(b, "image", IMG + "Fichier-14.png")

        # 6-9 — SECTION_VIDEO : VIDEO_TEXTE + 2 CARTE + CTA (groupe composé).
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.VIDEO_TEXTE, position=suivant(),
            titre="Le lieu en mouvement",
            texte=(
                "<p>Une minute pour ressentir l'ambiance : machines qui tournent, "
                "mains qui s'activent, idées qui circulent.</p>"
            ),
        )
        self._poser_fichier(b, "video", IMG + "motion-table.mp4")
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=suivant(),
            surtitre="Atelier", titre="Découpe laser",
            texte="Prototypez vos idées en quelques minutes.",
        )
        self._poser_fichier(b, "image", IMG + "photo_tutos-07.webp")
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=suivant(),
            surtitre="Atelier", titre="Couture",
            texte="Réparez et transformez vos vêtements.",
        )
        self._poser_fichier(b, "image", IMG + "photo_tutos-08.webp")
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CTA, position=suivant(),
            bouton_label="Voir tout le programme", bouton_url="/event/",
        )

        # 10 — PARAGRAPHE (solo) : sert de séparateur (titre de section).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.PARAGRAPHE, position=suivant(),
            titre="Trois bonnes raisons de venir",
        )

        # 11-13 — GRILLE : 3 CARTE consécutives autonomes.
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=suivant(),
            surtitre="01", titre="Apprendre",
            texte="Des formateur·rice·s passionné·e·s, à votre rythme.",
            bouton_label="Les cours", bouton_url="/event/",
        )
        self._poser_fichier(b, "image", IMG + "photo_tutos-09.webp")
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=suivant(),
            surtitre="02", titre="Fabriquer", badge="accès libre",
            texte="Un parc de machines accessible aux membres.",
            bouton_label="Le matériel", bouton_url="/event/",
        )
        self._poser_fichier(b, "image", IMG + "Fichier-17.webp")
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=suivant(),
            surtitre="03", titre="Partager",
            texte="Une communauté qui documente et transmet.",
            bouton_label="La communauté", bouton_url="/event/",
        )
        self._poser_fichier(b, "image", IMG + "Fichier-18.png")

        # 14 — TEMOIGNAGE (solo) : citation + auteur + photo.
        b = Bloc.objects.create(
            page=page, type_bloc=Bloc.TEMOIGNAGE, position=suivant(),
            texte="J'ai poussé la porte un samedi par curiosité. Six mois plus tard, "
                  "j'anime mon propre atelier. Ce lieu a changé ma vie.",
            auteur_nom="Camille Dubreuil",
            auteur_role="Membre depuis 2024",
        )
        self._poser_fichier(b, "auteur_photo", IMG + "f.png")

        # 14b — EVENEMENTS (solo) : liste dynamique des prochains évènements.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.EVENEMENTS, position=suivant(),
            titre="Nos prochains rendez-vous",
            nombre_max=3,
        )

        # 14c — GALERIE (solo) : plusieurs images en grille (modèle ImageGalerie).
        galerie = Bloc.objects.create(
            page=page, type_bloc=Bloc.GALERIE, position=suivant(),
            titre="En images",
        )
        for index, (nom, legende) in enumerate([
            ("photo_tutos-07.webp", "Atelier découpe"),
            ("photo_tutos-08.webp", "Atelier couture"),
            ("photo_tutos-09.webp", "Apprentissage"),
            ("Fichier-17.webp", "Le lieu"),
        ], start=1):
            img = ImageGalerie.objects.create(bloc=galerie, position=index, legende=legende)
            self._poser_fichier(img, "image", IMG + nom)

        # 14d — EMBED (solo) : vidéo YouTube (hôte en liste blanche).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.EMBED, position=suivant(),
            titre="En vidéo",
            embed_url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
        )

        # 15 — CTA (solo) : titre + sous-titre + 2 boutons.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CTA, position=suivant(),
            titre="Prêt·e à nous rejoindre ?",
            sous_titre="L'adhésion est à prix libre. Premier atelier offert.",
            bouton_label="Adhérer maintenant", bouton_url="/memberships/",
            bouton2_label="Nous écrire", bouton2_url="/contact/",
        )

        # 16-19 — FAQ : 4 questions consécutives (rendues en 2 colonnes).
        faqs = [
            ("Faut-il être membre pour venir ?",
             "<p>Non. La plupart des ateliers sont ouverts à tou·te·s. L'adhésion "
             "donne accès libre aux machines et à des tarifs réduits.</p>"),
            ("Quels sont les horaires ?",
             "<p>Du mardi au samedi, de 10h à 19h. Les ateliers du soir vont "
             "parfois jusqu'à 21h.</p>"),
            ("Le matériel est-il fourni ?",
             "<p>Oui, pour tous les ateliers encadrés. Vous repartez avec vos "
             "réalisations.</p>"),
            ("Comment réserver ?",
             "<p>Directement en ligne depuis l'agenda, ou sur place à l'accueil.</p>"),
        ]
        for question, reponse in faqs:
            Bloc.objects.create(
                page=page, type_bloc=Bloc.FAQ, position=suivant(),
                titre=question, texte=reponse,
            )

        # 20-21 — SECTION_CARTE : INFOS + CARTE_LEAFLET (côte à côte).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.INFOS, position=suivant(),
            contenu=[
                {"type": "badge", "texte": "Nous trouver"},
                {"type": "para", "texte": "Au cœur du quartier, accès facile en transports."},
                {"type": "horaire", "texte": "MARDI → SAMEDI 10h → 19h"},
                {"type": "badge", "texte": "Adresse"},
                {"type": "adresse", "texte": "La Cité\n55 avenue Louis Breguet\n31400 Toulouse"},
                {"type": "accessibilite", "texte": "Lieu accessible aux personnes à mobilité réduite."},
                {"type": "transport", "titre": "BUS", "lignes": [
                    "Ligne 37 — arrêt Bréguet (3 min à pied)",
                    "Ligne L9 — arrêt Tahiti (10 min à pied)",
                ]},
                {"type": "transport", "titre": "TRAIN", "lignes": [
                    "TER — arrêt Montaudran (5 min à pied)",
                ]},
            ],
        )
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE_LEAFLET, position=suivant(),
            badge="LA CITÉ — 55 AV. LOUIS BRÉGUET, 31400 TOULOUSE",
            points_gps=[{"lat": 43.5568, "lng": 1.4835, "label": "La Cité"}],
        )
