"""
Charge le site vitrine de demonstration du skin faire_festival, via le moteur
pages (blocs). Le contenu est un festival GENERIQUE et fictif : la demo ne met
en scene aucune organisation reelle.
/ Loads the faire_festival skin demo showcase website through the pages engine
(blocks). The content is a GENERIC, fictional festival: the demo depicts no
real organisation.

LOCALISATION : pages/management/commands/charger_demo_faire_festival.py

Usage :
    python manage.py charger_demo_faire_festival            # tenant "festival"
    python manage.py charger_demo_faire_festival --schema=mon_tenant

Les 4 pages couvrent LES 19 types de blocs du catalogue. Le skin faire_festival
ne fournit un gabarit que pour 11 d'entre eux : les 8 autres (EVENEMENTS,
GALERIE, EMBED, MARKDOWN, LISTE_SOUS_PAGES, IFRAME, PARTENAIRES, NEWSLETTER)
retombent sur le socle classic via gabarit_skin(). C'est VOULU : la demo rend
visible ce qui reste a habiller dans le skin.
/ The 4 pages cover ALL 19 block types. The faire_festival skin only provides a
template for 11 of them: the other 8 fall back to the classic base via
gabarit_skin(). This is INTENDED: the demo shows what the skin still lacks.

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

# Logos « contributeurs » de la landing ROOT, reutilises par le bloc PARTENAIRES.
# PNG/JPG uniquement : StdImageField genere ses variations via Pillow, qui ne
# sait pas redimensionner un SVG.
# / ROOT landing "contributor" logos, reused by the PARTENAIRES block. PNG/JPG
# only: Pillow cannot resize an SVG.
LOGOS = "contributeurs/"

# Prefixe des images static du skin faire_festival.
# / Prefix of the faire_festival skin static images.
IMG = "faire_festival/image/"


class Command(BaseCommand):
    help = "Reproduit la home faire_festival via le moteur pages (blocs)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="festival")
        # Par defaut on force le skin faire_festival (mode complet « one-shot »).
        # --no-skin laisse le skin existant intact (charge seulement les pages).
        # / By default we force the faire_festival skin (full one-shot mode).
        # --no-skin keeps the existing skin untouched (only loads the pages).
        parser.add_argument(
            "--no-skin",
            action="store_false",
            dest="skin",
            help="Ne pas forcer le skin 'faire_festival' (laisse le skin actuel).",
        )

    def handle(self, *args, **options):
        schema = options["schema"]
        try:
            tenant = Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            self.stderr.write(f"Tenant introuvable : {schema}")
            return
        # Le bloc IFRAME d'« Infos pratiques » integre un formulaire Framaforms :
        # son hote doit figurer dans la whitelist ROOT, sinon le bloc ne rend rien.
        # / The IFRAME block embeds a Framaforms form: its host must be in the ROOT
        # whitelist, otherwise the block renders nothing.
        self._whitelister_domaine_embed("framaforms.org")

        with tenant_context(tenant):
            self._charger_accueil()
            self._charger_le_faire_festival()
            self._charger_sous_menu()
            self._charger_infos_pratiques()
            if options["skin"]:
                self._forcer_skin()
        self.stdout.write(
            f"Pages faire_festival (accueil + le-faire-festival + sous-menu + "
            f"infos-pratiques) chargees sur '{schema}'."
        )

    # ------------------------------------------------------------------
    # Helper : force le skin 'faire_festival' sur la config du tenant.
    # / Helper: force the 'faire_festival' skin on the tenant config.
    # ------------------------------------------------------------------
    def _forcer_skin(self):
        from pages.models import ConfigurationSite

        config = ConfigurationSite.get_solo()
        config.skin = "faire_festival"
        config.save()
        self.stdout.write("  → skin force a 'faire_festival'.")

    # ------------------------------------------------------------------
    # Helper : autorise un hote dans la whitelist ROOT des blocs IFRAME.
    # / Helper: allow a host in the ROOT whitelist for IFRAME blocks.
    # ------------------------------------------------------------------
    def _whitelister_domaine_embed(self, domaine):
        """
        Ajoute un domaine a la whitelist ROOT des blocs IFRAME (idempotent).
        / Adds a host to the ROOT whitelist for IFRAME blocks (idempotent).

        RootConfiguration est un singleton SHARED (schema public) : la whitelist
        vaut pour TOUS les tenants. On vide le cache django-solo pour qu'elle
        soit immediatement effective.
        / RootConfiguration is a SHARED singleton (public schema): the whitelist
        applies to ALL tenants. We clear the django-solo cache so it takes effect
        immediately.
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
            self.stdout.write(f"  → domaine iframe autorise (ROOT) : {domaine}")

    # ------------------------------------------------------------------
    # Helper : recupere une Page par slug, ou la cree (puis vide ses blocs).
    # / Helper: get a Page by slug, or create it (then clear its blocks).
    # ------------------------------------------------------------------
    def _page_propre(self, slug, titre, position=0, est_accueil=False,
                     meta_description="", parent=None):
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

    # ------------------------------------------------------------------
    # Helper : UPLOAD d'un asset static du skin dans un champ image/fichier
    # d'un objet modèle — un Bloc le plus souvent, mais aussi la Configuration
    # du lieu (ex : config.img pour le HERO). D'où le nom générique.
    # / Helper: UPLOAD a static skin asset into a model object's image/file
    # field — usually a Bloc, but also the venue Configuration (e.g. config.img
    # for the HERO). Hence the generic parameter name.
    # ------------------------------------------------------------------
    def _poser_fichier(self, objet_cible, champ, chemin_static):
        chemin = finders.find(chemin_static)
        if not chemin:
            self.stdout.write(f"  ⚠ asset static introuvable : {chemin_static}")
            return
        nom = os.path.basename(chemin_static)
        with open(chemin, "rb") as fichier:
            getattr(objet_cible, champ).save(nom, File(fichier), save=True)

    def _charger_sous_menu(self):
        """
        Sous-menu de démo : sous-page « Notre démarche » RATTACHÉE à la page
        « Le Festival » (menu déroulant dans la navbar FF). Structure : IMAGE en
        en-tête → texte brut → vidéo → article MARKDOWN. Assets du skin festival.
        / Demo sub-menu: sub-page "Notre démarche" attached to "Le Festival"
        (dropdown in the FF navbar). Layout: header IMAGE → plain text → video →
        MARKDOWN article. Festival-skin assets.
        """
        from pages.models import Bloc, Page

        # La page parente existe déjà (créée par _charger_le_faire_festival, appelé
        # avant dans handle). / The parent page already exists.
        parent = Page.objects.get(slug="le-faire-festival")

        page = self._page_propre(
            "notre-demarche", "Notre démarche", position=1, parent=parent,
            meta_description="La démarche du Festival : documenter, transmettre "
            "et fabriquer ensemble des communs, au-delà de l'objet fini.",
        )

        # 1 — IMAGE en en-tête.
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE, position=1, titre="Notre démarche",
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-16.webp")

        # 2 — Texte brut.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.PARAGRAPHE, position=2,
            texte=(
                "<h2 class='fs-3 fw-bold my-3'>Faire, c'est bien. Transmettre "
                "comment faire, c'est encore mieux.</h2>"
                "<p>Le Festival met à l'honneur la documentation : guides, "
                "vidéos, pas-à-pas, protocoles ouverts... tout ce qui permet "
                "d'apprendre en faisant et de partager les savoir-faire.</p>"
                "<p>Open source, collectif et évolutif comme tout prototype, le "
                "festival produit des communs de fabrication et repense le lien "
                "entre production et consommation.</p>"
            ),
        )

        # 3 — Vidéo sous le texte.
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.VIDEO_TEXTE, position=3,
            titre="En mouvement",
            texte="<p>Un aperçu de l'ambiance des trois jours du festival.</p>",
        )
        self._poser_fichier(bloc, "video", IMG + "motion-table.mp4")

        # 4 — MARKDOWN : texte long (article). Le champ texte est du Markdown, pas
        # du HTML : titres, listes et tableaux sont rendus par le gabarit.
        # Pas de gabarit faire_festival -> socle classic.
        # / MARKDOWN: long-form text (article). The texte field holds Markdown, not
        # HTML. No faire_festival template -> classic base.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.MARKDOWN, position=4,
            texte=(
                "Chaque année, les bénévoles documentent les ateliers pour que "
                "n'importe qui puisse les rejouer chez soi. Voici comment nous "
                "nous y prenons.\n\n"
                "## Trois règles simples\n\n"
                "- **Photographier pendant, pas après** : un pas-à-pas se perd "
                "dès que l'atelier est rangé.\n"
                "- **Écrire pour quelqu'un qui débute** : si une étape suppose "
                "un savoir-faire, elle se découpe en deux.\n"
                "- **Publier même si c'est imparfait** : une fiche incomplète "
                "vaut mieux qu'une fiche jamais écrite.\n\n"
                "## Ce que ça donne\n\n"
                "| Édition | Ateliers | Fiches publiées | Taux |\n"
                "|---|---|---|---|\n"
                "| 2024 | 34 | 12 | 35 % |\n"
                "| 2025 | 41 | 29 | 71 % |\n"
                "| 2026 | 48 | 44 | 92 % |\n\n"
                "Toutes les fiches sont publiées sous licence libre : "
                "reprenez-les, corrigez-les, améliorez-les."
            ),
        )

    def _charger_le_faire_festival(self):
        """
        Page « Le Festival » : IMAGE titre + PARAGRAPHE intro + 3 IMAGE_TEXTE,
        puis GALERIE + TEMOIGNAGE + LISTE_SOUS_PAGES.

        Le slug reste « le-faire-festival » : c'est l'URL publique historique,
        ciblee par les tests E2E et par les CTA des autres pages.
        / The slug stays "le-faire-festival": it is the historical public URL,
        targeted by the E2E tests and by the other pages' CTAs.
        """
        from pages.models import Bloc, ImageGalerie

        page = self._page_propre(
            "le-faire-festival", "Le Festival", position=1,
            meta_description="Découvrez le Festival : ateliers, conférences et "
            "rencontres entre artisans, associations et grand public, du 28 au 30 mai.",
        )

        # 1 — Image-titre « Bienvenue au Festival ».
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE, position=1,
            titre="Bienvenue au Festival",
            affichage_image=Bloc.VIGNETTE_TITRE,  # image-titre dessinée / drawn title-image
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-18.png")

        # 2 — Intro (sous-titre + description), centree.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.PARAGRAPHE, position=2,
            texte=(
                "<h2 class='fs-3 fw-bold text-center my-3'>Le rendez-vous pour "
                "réinventer notre façon de produire, de consommer et de "
                "transmettre !</h2>"
                "<p class='text-center small fw-bold'>Le Festival invite "
                "tou·te·s les citoyen·ne·s, artisan·e·s, créatif·ve·s, associations, "
                "ateliers et collectifs à imaginer et partager leurs "
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
                "<p>Le Festival est la grande rencontre des ateliers partagés et des "
                "artisan·e·s ! Du 28 au 30 mai, nous transformons le parc du festival "
                "en un immense espace de rencontre avec une programmation géante "
                "(ateliers, conférences, rencontres, soirées...). Le mot d'ordre ? "
                "Apprendre, créer, réparer et surtout, partager. Cette année, nous "
                "mettons à l'honneur les tutos et la documentation : parce que "
                "faire, c'est bien, mais transmettre comment faire, c'est encore "
                "mieux ! Le Festival est un événement citoyen et indépendant, porté "
                "par une communauté d'artisan·e·s, de bénévoles et de curieux·ses qui "
                "partagent l'envie de fabriquer, transmettre et expérimenter ensemble "
                "pour contribuer à changer nos façons de produire et consommer.</p>"
                "<p>Vous pouvez construire votre propre programme en piochant parmi "
                "nos thématiques (textile, réparation, bois, terre...). Au "
                "programme pour le grand public :</p>"
                "<ul><li>→ Participez à des dizaines d'ateliers pratiques pour "
                "apprendre un nouveau savoir-faire (imprimantes 3D, découpeuses "
                "laser…).</li>"
                "<li>→ Assistez à nos grands incontournables comme la course de "
                "robots, nos défilés de mode engagés, et flânez dans nos marchés de "
                "créateurs et créatrices.</li>"
                "<li>→ Rencontrez des artisan·e·s, des inventeur·rice·s, écoutez des "
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
                "<p>Le Festival est le fruit d'une véritable dynamique "
                "collective.</p>"
                "<p>Pour garantir son ancrage local, l'événement est conçu en étroite "
                "collaboration avec les ateliers partagés du quartier, les "
                "associations culturelles de la ville et des dizaines de bénévoles. "
                "C'est la force de cette coopération qui donne vie au festival.</p>"
            ),
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-16.webp")

        # 5 — Un événement ancré dans sa ville (image gauche + texte).
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE_TEXTE, position=5,
            image_position=Bloc.GAUCHE,
            texte=(
                "<p>Le cœur du festival bat au parc du festival, un lieu dédié à "
                "l'innovation collaborative et ouvert sur le quartier.</p>"
                "<p>Le festival s'étend également hors les murs lors de nos soirées "
                "festives, accueillies chaque année par un lieu culturel partenaire "
                "de la ville.</p>"
            ),
        )
        self._poser_fichier(bloc, "image", IMG + "Fichier-17.webp")

        # 6 — GALERIE : grille d'images (modele ImageGalerie, plusieurs images
        # pour un bloc). Pas de gabarit faire_festival -> socle classic.
        # / GALERIE: image grid. No faire_festival template -> classic base.
        galerie = Bloc.objects.create(
            page=page, type_bloc=Bloc.GALERIE, position=6, titre="Le festival en images",
        )
        for index, (fichier, legende) in enumerate([
            ("Fichier-15.webp", "Un atelier pratique"),
            ("Fichier-16.webp", "Le marché des créateurs et créatrices"),
            ("Fichier-17.webp", "Une conférence sous le chapiteau"),
            ("photo_tutos-09.webp", "La zone de réparation"),
        ], start=1):
            image = ImageGalerie.objects.create(
                bloc=galerie, position=index, legende=legende,
            )
            self._poser_fichier(image, "image", IMG + fichier)

        # 7 — TEMOIGNAGE : le skin faire_festival fournit son propre gabarit.
        # / TEMOIGNAGE: the faire_festival skin provides its own template.
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.TEMOIGNAGE, position=7,
            texte="Je suis venue pour un atelier de sérigraphie, je suis repartie "
                  "avec un savoir-faire et une bande de copains. Depuis, je suis "
                  "bénévole chaque année.",
            auteur_nom="Camille Dubreuil", auteur_role="Bénévole depuis 2024",
        )
        self._poser_fichier(bloc, "auteur_photo", IMG + "photo_tutos-08.webp")

        # 8 — LISTE_SOUS_PAGES : index des sous-pages publiees de CETTE page.
        # « Notre démarche » lui est rattachee (cf. _charger_sous_menu), la liste
        # n'est donc pas vide. La requete se fait au RENDU : l'ordre de creation
        # des pages n'a pas d'importance.
        # / LISTE_SOUS_PAGES: index of THIS page's published sub-pages. "Notre
        # démarche" is attached to it, so the list is not empty. The query runs at
        # RENDER time: page creation order does not matter.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.LISTE_SOUS_PAGES, position=8,
            titre="À lire aussi", nombre_max=6,
        )

    def _charger_infos_pratiques(self):
        """Page « Infos pratiques » : bloc INFOS + bloc CARTE_LEAFLET (cote a cote),
        badge « Se reperer », plan, badge « FAQ », puis 6 blocs FAQ (2 colonnes).
        Tout le contenu est du TEXTE (champs / JSON) ; le HTML est dans les templates."""
        from pages.models import Bloc

        page = self._page_propre(
            "infos-pratiques", "Infos pratiques", position=9,
            meta_description="Accès, horaires, plan et FAQ du Festival au parc du "
            "festival. Comment venir en voiture, bus ou train.",
        )

        # 1 — Bloc INFOS : colonne d'infos (texte seulement, items typés dans contenu).
        # L'adresse reprend celle du lieu seede par demo_data_v2 (Villeurbanne) :
        # la fiche du tenant et son site vitrine doivent raconter le meme lieu.
        # / The address mirrors the venue seeded by demo_data_v2 (Villeurbanne):
        # the tenant record and its showcase site must describe the same place.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.INFOS, position=1,
            contenu=[
                {"type": "badge", "texte": "Infos pratiques"},
                {"type": "para", "texte": "Bienvenue au Festival, trois jours pour faire ensemble."},
                {"type": "horaire", "texte": "JEUDI & VENDREDI 09h → 21h"},
                {"type": "horaire", "texte": "SAMEDI 10h → 19h"},
                {"type": "badge", "texte": "Accéder au Festival"},
                {"type": "adresse", "texte": "Le parc du festival\n12 rue de la Coopérative\n69100 Villeurbanne"},
                {"type": "accessibilite", "texte": "LE FESTIVAL EST ACCESSIBLE AUX PERSONNES À MOBILITÉ RÉDUITE."},
                {"type": "transport", "titre": "VOITURE", "lignes": [
                    "À 5 min du périphérique",
                    "Sortie « Parc du festival »",
                    "Parking gratuit sur place",
                ]},
                {"type": "transport", "titre": "BUS", "lignes": [
                    "Ligne 1 — Arrêt Les Ateliers - 3 min. à pied",
                    "Ligne 2 — Arrêt Place du Marché - 10 min. à pied",
                ]},
                {"type": "transport", "titre": "TRAIN", "lignes": [
                    "À 15 min à pied de la gare centrale",
                ]},
            ],
        )

        # 2 — Bloc CARTE_LEAFLET : adjacent au bloc INFOS -> rendus cote a cote.
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE_LEAFLET, position=2,
            # Bloc.badge est en max_length=60 : la mention tient dans cette limite.
            # / Bloc.badge is max_length=60: this label fits within that limit.
            badge="LE PARC DU FESTIVAL — 69100 VILLEURBANNE",
            points_gps=[{"lat": 45.7660, "lng": 4.8730, "label": "LE PARC DU FESTIVAL"}],
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
            ("POUVEZ-VOUS NOUS PRÉSENTER LE FESTIVAL ?",
             "<p>Le Festival est un festival pour faire ensemble. Autour de la "
             "matière et de la matérialité, les ateliers partagés, les associations "
             "et le grand public se retrouvent pour partager des savoir-faire, découvrir "
             "des machines et outils, expérimenter des techniques...</p>"
             "<p>Open source, collectif et évolutif comme tout prototype, ce festival "
             "donne la possibilité de :</p>"
             "<ul><li>Faire découvrir la fabrication au plus grand nombre.</li>"
             "<li>Partager, mutualiser, expérimenter le faire.</li>"
             "<li>Produire des communs de fabrication.</li>"
             "<li>Repenser le lien entre production et consommation.</li></ul>"
             "<p>Trois jours pour presque tout fabriquer ensemble !</p>"),
            ("QU'EST-CE QU'UN ATELIER PARTAGÉ ?",
             "<p>Un atelier partagé est un lieu qui met en commun des outils, des "
             "machines et des savoir-faire, ouvert à tous les publics : atelier bois, "
             "espace de couture, salle de réparation, cuisine collective...</p>"
             "<p>Il mutualise outils et savoir-faire pour passer rapidement de l'idée à "
             "l'objet, et produit des communs par la documentation et le faire ensemble.</p>"),
            ("FAUT-IL SAVOIR BRICOLER POUR VENIR ?",
             "<p>Surtout pas. Les ateliers sont pensés pour les débutant·e·s : on vous "
             "montre, vous essayez, vous repartez avec ce que vous avez fabriqué.</p>"
             "<p>Les bénévoles sont là pour accompagner, à votre rythme, sans jargon "
             "et sans prérequis.</p>"),
            ("QUI PORTE LE FESTIVAL ?",
             "<p>Un événement open source et collectif, porté par un collectif "
             "d'associations locales et des ateliers partagés du territoire.</p>"
             "<p>Il est organisé avec la collaboration des associations culturelles de "
             "la ville et le soutien des collectivités locales. C'est un commun qui "
             "appartient à toutes et à tous.</p>"),
            ("QUI SONT LES PARTICIPANT·E·S ?",
             "<p>Littéralement, tout le monde. Ce festival de 3 jours est à la fois un "
             "salon professionnel (jeudi, vendredi) et un moment de partage pour le grand "
             "public (samedi).</p>"
             "<p>Un festival pour fabriquer et faire ensemble !</p>"),
            ("COMMENT CONTRIBUER ?",
             "<p>Le Festival appartient à toutes et à tous. On peut contribuer :</p>"
             "<p><strong>En devenant bénévoles :</strong> aidez-nous à penser, concevoir "
             "et organiser le festival.</p>"
             "<p><strong>En relayant</strong> le Festival sur vos réseaux.</p>"
             "<p><strong>En participant</strong> à un de nos ateliers.</p>"
             "<p>L'équipe reste disponible via le formulaire de contact du site.</p>"),
        ]
        for index, (question, reponse) in enumerate(faqs, start=6):
            Bloc.objects.create(
                page=page, type_bloc=Bloc.FAQ, position=index,
                titre=question, texte=reponse,
            )

        # 12 — EMBED : contenu integre (video PeerTube). Pas de gabarit
        # faire_festival -> socle classic.
        # / EMBED: embedded content (PeerTube video). No faire_festival template.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.EMBED, position=12,
            titre="Découvrir le festival en vidéo",
            embed_url="https://videos-libr.es/w/r2XVKcqhLPVBDujoMVrTcF",
        )

        # 13 — IFRAME : contenu integre libre, a hauteur choisie. On l'illustre
        # par un FORMULAIRE, pas par une carte : le bloc CARTE_LEAFLET ci-dessus
        # fait deja la carte, et le modele decrit IFRAME comme « formulaire,
        # widget ». L'hote est autorise cote ROOT par _whitelister_domaine_embed
        # (appele dans handle) — sans quoi le bloc ne rend rien.
        # / IFRAME: free-height embedded content, illustrated by a FORM rather than
        # a map (the CARTE_LEAFLET block above already covers maps, and the model
        # describes IFRAME as "form, widget"). Host whitelisted at ROOT level.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.IFRAME, position=13,
            titre="Devenir bénévole",
            embed_url="https://framaforms.org/",
            hauteur_px=520,
        )

    def _charger_accueil(self):
        from pages.models import Bloc, ImageGalerie

        page = self._page_propre(
            "accueil", "Accueil", position=0, est_accueil=True,
            meta_description="Le Festival : trois jours de concerts, d'ateliers et de "
            "rencontres, du 28 au 30 mai au parc du festival.",
        )

        # 1 — HERO : image d'identité (config.img) + sous-titre. L'image est posée
        # sur la Configuration du lieu ; le template HERO faire_festival lit
        # config.img. Plus de badge date : le HERO est une bannière d'identité simple.
        # / HERO: identity image (config.img) + subtitle. The image is set on the
        # venue Configuration; the faire_festival HERO template reads config.img.
        # No date badge anymore: the HERO is a simple identity banner.
        from BaseBillet.models import Configuration
        self._poser_fichier(Configuration.get_solo(), "img", IMG + "logopage.webp")

        Bloc.objects.create(
            page=page, type_bloc=Bloc.HERO, position=1,
            titre="Le Festival",
            sous_titre="Trois jours pour fabriquer, apprendre et partager ensemble !",
        )

        # 2 — VIDEO + TEXTE : « Le Festival, c'est quoi ? »
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.VIDEO_TEXTE, position=2,
            titre="Le Festival, c'est quoi ?",
            texte=(
                "<p>Bienvenue au Festival : trois jours pour faire ensemble. Un "
                "festival géant avec des ateliers, des rencontres, des conférences, "
                "des animations, des stands, des démonstrations, une exposition et "
                "une boutique.</p>"
                "<p>Trois jours de rencontres entre le public, les associations, les "
                "ateliers partagés et les artisans, pour se comprendre, expérimenter "
                "et fabriquer ensemble dans un espace accessible à tous·tes.</p>"
            ),
        )
        self._poser_fichier(bloc, "video", IMG + "motion-table.mp4")

        # 3-5 — Cartes JOUR (absorbees par le VIDEO_TEXTE ci-dessus : elles forment
        # la section « video a gauche / cartes a droite », cf. grouper_blocs).
        # / Day cards, absorbed by the VIDEO_TEXTE above into the "video left /
        # cards right" section (see grouper_blocs).
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=3,
            surtitre="JOUR 01",
            texte="Entre ateliers,<br>associations<br>et artisans",
        )
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=4,
            surtitre="JOUR 02",
            texte="Entre ateliers,<br>associations<br>et artisans",
        )
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=5,
            surtitre="JOUR 03", badge="gratuit",
            texte="Entre grand public,<br>ateliers et<br>associations",
        )

        # 6 — CTA « En savoir plus ».
        Bloc.objects.create(
            page=page, type_bloc=Bloc.CTA, position=6,
            bouton_label="En savoir plus sur le Festival",
            bouton_url="/le-faire-festival/",
        )

        # 7 — IMAGE titre du tuto (« Comment créer son programme »).
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.IMAGE, position=7,
            titre="Comment créer son programme",
            affichage_image=Bloc.VIGNETTE_TITRE,  # image-titre dessinée / drawn title-image
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
            texte="Accédez aux différents événements classés par thématique !",
            bouton_label="Programmation", bouton_url="/event/",
        )
        self._poser_fichier(bloc, "image", IMG + "photo_tutos-08.webp")
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.CARTE, position=10,
            texte="Venez profiter du Festival, du 28 au 30 mai !",
            bouton_label="Infos pratiques", bouton_url="/infos-pratiques/",
        )
        self._poser_fichier(bloc, "image", IMG + "photo_tutos-07.webp")

        # 11 — EVENEMENTS : agenda dynamique (liste automatique depuis la
        # billetterie du tenant). Pas de gabarit faire_festival -> socle classic.
        # / EVENEMENTS: dynamic agenda. No faire_festival template -> classic base.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.EVENEMENTS, position=11,
            titre="Nos prochains rendez-vous", nombre_max=6,
        )

        # 12 — PARTENAIRES : bande de logos cliquables. Un lien_url vide rend le
        # logo non cliquable. / PARTENAIRES: clickable logo strip. An empty
        # lien_url makes the logo non-clickable.
        partenaires = Bloc.objects.create(
            page=page, type_bloc=Bloc.PARTENAIRES, position=12,
            titre="Ils soutiennent le Festival",
        )
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
            self._poser_fichier(logo, "image", LOGOS + fichier)

        # 13 — NEWSLETTER : formulaire Ghost. Le script est vendorise (zero CDN) ;
        # embed_url = l'instance Ghost (data-site). Aucune whitelist necessaire.
        # / NEWSLETTER: Ghost signup form. Vendored script; embed_url = the Ghost
        # instance. No whitelist needed.
        Bloc.objects.create(
            page=page, type_bloc=Bloc.NEWSLETTER, position=13,
            embed_url="https://ghost.tibillet.coop/",
            titre="Les news du Festival",
            sous_titre="La programmation et les coulisses, dans votre boîte mail",
        )
