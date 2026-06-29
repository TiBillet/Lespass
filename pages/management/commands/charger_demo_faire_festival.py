"""
Charge une page d'accueil de demonstration reproduisant la home faire_festival,
via le moteur pages (blocs). Sert a comparer avec la home legacy (le-coeur-en-or).
/ Loads a demo home page reproducing the faire_festival home through the pages
engine (blocks). Used to compare with the legacy home (le-coeur-en-or).

LOCALISATION : pages/management/commands/charger_demo_faire_festival.py

Usage :
    python manage.py charger_demo_faire_festival            # tenant "chantefrein"
    python manage.py charger_demo_faire_festival --schema=mon_tenant

Les images/video du skin faire_festival sont UPLOADEES dans le media du tenant
(vrai moteur d'upload, comme le reste de TiBillet) via _poser_fichier : on lit
l'asset static du skin et on l'enregistre dans le champ image/image_secondaire/
video du bloc (les StdImageField generent leurs variations).
/ The faire_festival skin images/video are UPLOADED into the tenant media (real
upload engine, like the rest of TiBillet) via _poser_fichier: we read the skin's
static asset and save it into the block's image/image_secondaire/video field
(StdImageField generates its variations).
"""

import os

from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Customers.models import Client

# Prefixe des images static du skin faire_festival.
# / Prefix of the faire_festival skin static images.
IMG = "faire_festival/image/"


class Command(BaseCommand):
    help = "Reproduit la home faire_festival via le moteur pages (blocs)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="chantefrein")

    def handle(self, *args, **options):
        schema = options["schema"]
        try:
            tenant = Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            self.stderr.write(f"Tenant introuvable : {schema}")
            return
        with tenant_context(tenant):
            self._charger_accueil()
            self._charger_le_faire_festival()
            self._charger_infos_pratiques()
        self.stdout.write(
            f"Pages faire_festival (accueil + le-faire-festival + infos-pratiques) "
            f"chargees sur '{schema}'."
        )

    # ------------------------------------------------------------------
    # Helper : recupere une Page par slug, ou la cree (puis vide ses blocs).
    # / Helper: get a Page by slug, or create it (then clear its blocks).
    # ------------------------------------------------------------------
    def _page_propre(self, slug, titre, position=0, est_accueil=False, meta_description=""):
        from pages.models import Page

        page, _cree = Page.objects.get_or_create(slug=slug, defaults={"titre": titre})
        page.titre = titre
        page.position = position
        page.publie = True
        page.est_accueil = est_accueil
        page.meta_description = meta_description
        page.save()
        page.blocs.all().delete()
        return page

    # ------------------------------------------------------------------
    # Helper : UPLOAD d'un asset static du skin dans un champ image/fichier du bloc.
    # / Helper: UPLOAD a static skin asset into a block image/file field.
    # ------------------------------------------------------------------
    def _poser_fichier(self, bloc, champ, chemin_static):
        chemin = finders.find(chemin_static)
        if not chemin:
            self.stdout.write(f"  ⚠ asset static introuvable : {chemin_static}")
            return
        nom = os.path.basename(chemin_static)
        with open(chemin, "rb") as fichier:
            getattr(bloc, champ).save(nom, File(fichier), save=True)

    def _charger_le_faire_festival(self):
        """Page « Le Faire Festival » : IMAGE titre + PARAGRAPHE intro + 3 IMAGE_TEXTE."""
        from pages.models import Bloc

        page = self._page_propre(
            "le-faire-festival", "Le Faire Festival", position=1,
            meta_description="Découvrez le Faire Festival : ateliers, conférences et "
            "rencontres entre makers, artisans et grand public à Toulouse, les 28, 29 "
            "et 30 mai 2026.",
        )

        # 1 — Image-titre « Bienvenue au Faire Festival ».
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE, position=1,
            titre="Bienvenue au Faire Festival",
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-18.png")

        # 2 — Intro (sous-titre + description), centree.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.PARAGRAPHE, position=2,
            texte=(
                "<h2 class='fs-3 fw-bold text-center my-3'>Le grand rendez-vous "
                "toulousain pour réinventer notre façon de produire, de consommer "
                "et de transmettre !</h2>"
                "<p class='text-center small fw-bold'>Le Faire Festival invite "
                "tou·te·s les citoyen·ne·s, artisan·e·s, créatif·ve·s, associations, "
                "fablabs, ateliers et collectifs à imaginer et partager leurs "
                "savoir-faire. Notre objectif ? Mettre en lumière toutes les façons "
                "de documenter : guides, vidéos, pas-à-pas, ateliers de transmission, "
                "protocoles ouverts... en bref, tout ce qui permet d'apprendre en faisant !</p>"
            ),
        )

        # 3 — C'est quoi exactement ? (image gauche + texte).
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE_TEXTE, position=3,
            image_position=Bloc.GAUCHE,
            texte=(
                "<p>Le Faire Festival est la grande rencontre des espaces du Faire "
                "et des makers en France ! Les 28, 29 et 30 mai, nous transformons "
                "La Cité à Toulouse, lieu de l'innovation toulousaine, en un immense "
                "espace de rencontre avec une programmation géante (ateliers, "
                "conférences, rencontres, soirées...). Le mot d'ordre ? Apprendre, "
                "créer, réparer et surtout, partager. Cette année, nous mettons "
                "d'ailleurs à l'honneur les 'tutos' et la documentation : parce que "
                "faire, c'est bien, mais transmettre comment faire, c'est encore "
                "mieux ! Le Faire Festival est un événement citoyen, indépendant et "
                "unique, porté par une communauté de makers, d'artisans, de bénévoles "
                "et de curieux qui partagent l'envie de fabriquer, transmettre et "
                "expérimenter ensemble pour contribuer à changer nos façons de "
                "produire et consommer.</p>"
                "<p class='fst-italic small'>*Nous utilisons volontairement certains "
                "mots anglais comme « maker », « FabLab » ou « workshop », car ils "
                "font partie de la culture internationale de la fabrication partagée.</p>"
                "<p>Vous pouvez construire votre propre programme en piochant parmi "
                "nos 22 thématiques (textile, réparation, bois, terre...). Au "
                "programme pour le grand public :</p>"
                "<ul><li>→ Participez à des dizaines d'ateliers pratiques pour "
                "apprendre un nouveau savoir-faire (imprimantes 3D, découpeuses "
                "laser…).</li>"
                "<li>→ Assistez à nos grands incontournables comme la course de "
                "robots, nos défilés de mode engagés, et flânez dans nos marchés de "
                "créateurs et créatrices.</li>"
                "<li>→ Rencontrez des artisans, makers, inventeur·rice·s, écoutez des "
                "conférences passionnantes et découvrez des solutions concrètes pour "
                "rendre notre monde plus durable et solidaire.</li></ul>"
            ),
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-15.webp")

        # 4 — Qui organise ? (texte gauche + image droite).
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE_TEXTE, position=4,
            image_position=Bloc.DROITE,
            texte=(
                "<p>Le Faire Festival est le fruit d'une véritable dynamique "
                "collective.</p>"
                "<p>Pour garantir son ancrage local, l'événement est conçu en étroite "
                "collaboration avec le RoseLab et des dizaines de personnes à "
                "Toulouse, plus de 110 tiers-lieux de fabrication partout en France, "
                "à l'échelle régionale avec la Rosêe, le réseau des tiers-lieux "
                "d'Occitanie, et au niveau national avec France Tiers-Lieux, ANTL et "
                "RFFLabs. C'est la force de cette coopération qui donne vie au "
                "festival.</p>"
            ),
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-16.webp")

        # 5 — Un événement toulousain (image gauche + texte).
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE_TEXTE, position=5,
            image_position=Bloc.GAUCHE,
            texte=(
                "<p>Le cœur du festival bat à La Cité (55 avenue Louis Breguet, "
                "31400 Toulouse), un lieu emblématique dédié à l'innovation "
                "collaborative en Occitanie.</p>"
                "<p>Le festival s'étend également hors des murs lors de nos soirées "
                "festives dans des lieux emblématiques de la ville, comme cette année "
                "avec les Imbriqués ou la clôture du festival au musée des "
                "Abattoirs.</p>"
            ),
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-17.webp")

    def _charger_infos_pratiques(self):
        """Page « Infos pratiques » : bloc INFOS + bloc CARTE_LEAFLET (cote a cote),
        badge « Se reperer », plan, badge « FAQ », puis 6 blocs FAQ (2 colonnes).
        Tout le contenu est du TEXTE (champs / JSON) ; le HTML est dans les templates."""
        from pages.models import Bloc

        page = self._page_propre(
            "infos-pratiques", "Infos pratiques", position=9,
            meta_description="Accès, horaires, plan et FAQ du Faire Festival à La Cité, "
            "Toulouse. Comment venir en voiture, bus ou train.",
        )

        # 1 — Bloc INFOS : colonne d'infos (texte seulement, items typés dans contenu).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.INFOS, position=1,
            contenu=[
                {"type": "badge", "texte": "Infos pratiques"},
                {"type": "para", "texte": "Bienvenue dans le FAIRE Festival, trois jours pour FAIRE ensemble."},
                {"type": "horaire", "texte": "JEUDI & VENDREDI 09h → 21h"},
                {"type": "horaire", "texte": "SAMEDI 10h → 19h"},
                {"type": "badge", "texte": "Accéder au Faire Festival"},
                {"type": "adresse", "texte": "La Cité\n55 avenue Louis Breguet\n31400 Toulouse"},
                {"type": "accessibilite", "texte": "LE FAIRE FESTIVAL EST ACCESSIBLE AUX PERSONNES À MOBILITÉ RÉDUITE."},
                {"type": "transport", "titre": "VOITURE", "lignes": [
                    "À 5 min des 2 périphériques",
                    "A620 – sortie 20 Complexe scientifique",
                    "A61 – sortie 18 Montaudran",
                ]},
                {"type": "transport", "titre": "BUS", "lignes": [
                    "Ligne L9 L'union/Saint Orens - Arrêt Tahiti - 10 min. à pied",
                    "Ligne 37 Jolimont/Ramonville - Arrêt Bréguet - 3 min. à pied",
                    "Ligne L8 Marengo SNCF/Gonin - Arrêt Aude - 15 min. à pied",
                ]},
                {"type": "transport", "titre": "TRAIN", "lignes": [
                    "À 5 mn à pied de l'arrêt TER Montaudran",
                ]},
            ],
        )

        # 2 — Bloc CARTE_LEAFLET : adjacent au bloc INFOS -> rendus cote a cote.
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE_LEAFLET, position=2,
            badge="LA CITÉ - 55 AV. LOUIS BRÉGUET, 31400 TOULOUSE",
            points_gps=[{"lat": 43.5568, "lng": 1.4835, "label": "LA CITÉ"}],
        )
        self._poser_fichier(bloc, "image", IMG + "logo.webp")
        self._poser_fichier(bloc, "image_secondaire", IMG + "datehorizon.png")

        # 3 — Badge « Se repérer dans le festival » (titre rendu en badge par le template).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.PARAGRAPHE, position=3,
            titre="Se repérer dans le festival",
        )

        # 4 — Plan du festival (image pleine largeur : pas de titre).
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE, position=4,
        )
        self._poser_fichier(bloc, "image", IMG + "plan-festival.webp")

        # 5 — Badge « Foire aux questions ».
        Bloc.objects.create(
            page=page, type_bloc=Bloc.PARAGRAPHE, position=5,
            titre="Foire aux questions",
        )

        # 6 — FAQ : 6 blocs (titre = question, texte = reponse riche). Les FAQ
        # consecutives sont regroupees en 2 colonnes par grouper_blocs.
        faqs = [
            ("POUVEZ-VOUS NOUS PRÉSENTER LE FAIRE FESTIVAL ?",
             "<p>Le Faire Festival est un festival pour FAIRE ensemble. Autour de la "
             "matière et de la matérialité, les FabLabs, Espaces et Communautés du Faire "
             "et le grand public se retrouvent pour partager des savoir-faire, découvrir "
             "des machines et outils, expérimenter des techniques...</p>"
             "<p>Open Source, collectif et évolutif comme tout prototype, ce festival "
             "donne la possibilité de :</p>"
             "<ul><li>Faire découvrir la fabrication au plus grand nombre.</li>"
             "<li>Partager, mutualiser, expérimenter le Faire.</li>"
             "<li>Produire des communs de fabrication.</li>"
             "<li>Repenser le lien entre production et consommation.</li></ul>"
             "<p>Trois jours pour presque tout fabriquer ensemble !</p>"),
            ("EXPLIQUEZ-NOUS CETTE TENDANCE DES « ESPACES DU FAIRE » ?",
             "<p>Un Espace du Faire est un FabLab, une Manufacture, un HackerSpace, un "
             "Atelier de bricoleurs, un MakerSpace, un Espace de couture partagé, un "
             "Tiers-Lieu de fabrication... un lieu qui partage des outils, machines et "
             "savoir-faire ouvert à tous les publics.</p>"
             "<p>Il mutualise outils et savoir-faire pour passer rapidement de l'idée à "
             "l'objet, et produit des communs par la documentation et le faire ensemble.</p>"),
            ("QUI SONT LES MAKERS ?",
             "<p>Les Makers (de Make = Faire) sont littéralement des « faiseurs ». Ils "
             "conçoivent, fabriquent ou réparent toutes sortes d'objets, par eux-mêmes et "
             "avec les autres (DIY, artisanat, réparation, industrie...).</p>"
             "<p>Pour se réapproprier la production et consommer différemment, contribuant "
             "à une société plus circulaire, durable, locale, inclusive et accessible !</p>"),
            ("QUI PORTE LE FAIRE FESTIVAL ?",
             "<p>Un événement open source et collectif coporté par le RedLab (Réseau des "
             "Labs d'Occitanie), le RoseLab et le Laboratoire Organique de Lustar, "
             "regroupés dans la Manufacture Distribuée.</p>"
             "<p>Il a lieu à Toulouse à La Cité, avec la collaboration de la Rosée, du "
             "RFFLabs, de l'ANTL, et le soutien de la Région Occitanie et de Toulouse "
             "Métropole. C'est un commun qui appartient à toutes et à tous.</p>"),
            ("QUI SONT LES PARTICIPANT·E·S ?",
             "<p>Littéralement, tout le monde. Ce festival de 3 jours est à la fois un "
             "salon professionnel (jeudi, vendredi) et un moment de partage pour le grand "
             "public (samedi).</p>"
             "<p>Un festival pour FABRIQUER et FAIRE ENSEMBLE !</p>"),
            ("COMMENT CONTRIBUER ?",
             "<p>Le Faire Festival appartient à toutes et à tous. On peut contribuer :</p>"
             "<p><strong>En devenant bénévoles :</strong> aidez-nous à penser, concevoir "
             "et organiser le festival.</p>"
             "<p><strong>En relayant</strong> le Faire Festival sur vos réseaux.</p>"
             "<p><strong>En participant</strong> à un de nos Labs Distribués.</p>"
             "<p>L'équipe reste disponible sur "
             "<a href='mailto:contact@fairefestival.fr'>contact@fairefestival.fr</a>.</p>"),
        ]
        for index, (question, reponse) in enumerate(faqs, start=6):
            Bloc.objects.create(
                page=page, type_bloc=Bloc.FAQ, position=index,
                titre=question, texte=reponse,
            )

    def _charger_accueil(self):
        from pages.models import Bloc

        page = self._page_propre(
            "accueil", "Accueil", position=0, est_accueil=True,
            meta_description="Le Faire Festival : le grand rendez-vous toulousain de la "
            "fabrication partagée, les 28, 29 et 30 mai 2026 à La Cité.",
        )

        # 1 — HERO : logo + badge date + sous-titre (section hero de la maquette).
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.HERO, position=1,
            titre="Faire Festival",
            sous_titre="Le grand rendez-vous toulousain pour réinventer notre façon "
                       "de produire, de consommer et de transmettre !",
        )
        self._poser_fichier(bloc, "image", IMG + "logopage.webp")
        self._poser_fichier(bloc, "image_secondaire", IMG + "dateaccueil.webp")

        # 2 — VIDEO + TEXTE : « Le Faire Festival, c'est quoi ? »
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.VIDEO_TEXTE, position=2,
            titre="Le Faire Festival, c'est quoi ?",
            texte=(
                "<p>FabLabs et Espace du FAIRE... Bienvenue dans le FAIRE Festival, "
                "trois jours pour FAIRE ensemble. Un festival géant avec des ateliers, "
                "rencontres, conférences, animations, stands, démonstrations, une "
                "exposition, une boutique et un SuperLab...</p>"
                "<p>Pour aller plus loin dans la fabrication partagée et distribuée. "
                "Trois jours de rencontres entre le public, les Espaces, et Communautés "
                "du Faire et les entreprises pour se rencontrer, se comprendre, "
                "expérimenter et faire ensemble dans un espace accessible à tous·tes.</p>"
            ),
        )
        self._poser_fichier(bloc, "video", IMG + "motion-table.mp4")

        # 3-5 — Cartes JOUR (regroupees en grille).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=3,
            surtitre="JOUR 01",
            texte="Entre Espaces,<br>Communautés du Faire<br>et Entreprises",
        )
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=4,
            surtitre="JOUR 02",
            texte="Entre Espaces,<br>Communautés du Faire<br>et Entreprises",
        )
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=5,
            surtitre="JOUR 03", badge="gratuit",
            texte="Entre Grand Public,<br>Espaces et<br>Communautés du Faire",
        )

        # 6 — CTA « En savoir plus ».
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CTA, position=6,
            bouton_label="En savoir plus sur le Faire Festival",
            bouton_url="/le-faire-festival/",
        )

        # 7 — IMAGE titre du tuto (« Comment créer son programme »).
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE, position=7,
            titre="Comment créer son programme",
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-14.png")

        # 8-10 — Cartes TUTO (image + texte + bouton), regroupees en grille.
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=8,
            texte="Rendez-vous sur l'onglet billetterie et prenez vos billets à prix libre !",
            bouton_label="Billetterie", bouton_url="/memberships/",
        )
        self._poser_fichier(bloc, "image", IMG + "photo_tutos-09.webp")
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=9,
            texte="Accédez aux différents événements classés par 22 thématiques !",
            bouton_label="Programmation", bouton_url="/event/",
        )
        self._poser_fichier(bloc, "image", IMG + "photo_tutos-08.webp")
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=10,
            texte="Venez profiter les 28, 29 et 30 mai lors du Faire Festival !",
            bouton_label="Infos pratiques", bouton_url="/infos-pratiques/",
        )
        self._poser_fichier(bloc, "image", IMG + "photo_tutos-07.webp")
