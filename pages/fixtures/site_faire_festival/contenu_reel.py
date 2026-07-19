"""
Contenu REEL du site Faire Festival (www.fairefestival.fr).
/ REAL content of the Faire Festival website.

LOCALISATION : pages/fixtures/site_faire_festival/contenu_reel.py

C'est ce fichier qu'on charge pour reconstruire le site du festival avec le
moteur de pages :

    manage.py charger_site_faire_festival --contenu=reel --schema=<tenant>

/ This is the file to load when rebuilding the festival's website with the
pages engine.

PROVENANCE. Textes, images et enchainement des blocs releves sur
www.fairefestival.fr, pages `/`, `/le-faire-festival/` et `/infos-pratiques/`.
Rien n'a ete invente ni reformule : ce qui est ecrit ici est ce que le site
publie.
/ PROVENANCE. Texts, images and block order read from the live site, pages `/`,
`/le-faire-festival/` and `/infos-pratiques/`. Nothing was invented or reworded.

CE QUI DIFFERE DE `contenu_demo.py`. La demo est un SUR-ENSEMBLE : elle ajoute
une galerie, une bande de logos, une newsletter, un agenda, une citation, une
page « Notre demarche » et une video, pour montrer tous les blocs du moteur. Le
vrai site n'a que TROIS pages et ne les utilise pas. Ce fichier suit le site,
pas la vitrine du moteur.
/ WHAT DIFFERS FROM `contenu_demo.py`. The demo is a SUPERSET: it adds blocks to
showcase every block type. The real site has only THREE pages.

SEULE INFIDELITE CONNUE : la banniere d'accueil de la prod porte un badge de
dates (`dateaccueil.webp`) que le bloc SECTION/BANNIERE ne sait pas afficher —
il ne prend pas d'image secondaire. Ecarte volontairement.
/ ONLY KNOWN INFIDELITY: the production home banner carries a date badge that
the SECTION/BANNIERE block cannot display. Left out on purpose.

FORMAT : voir l'en-tete de `contenu_demo.py`.
"""

# Section « Le Faire Festival, c'est quoi ? » de l'accueil : deux paragraphes.
# / Home page's "Le Faire Festival, c'est quoi ?" section: two paragraphs.
ACCUEIL_PRESENTATION = (
    "<p>FabLabs et Espace du FAIRE…. Bienvenue dans le FAIRE Festival, trois "
    "jours pour FAIRE ensemble. Un festival géant avec des ateliers, rencontres, "
    "conférences, animations, stands, démonstrations, une exposition, une "
    "boutique et un SuperLab…</p>"
    "<p>Pour aller plus loin dans la fabrication partagée et distribuée. Trois "
    "jours de rencontres entre le public, les Espaces et Communautés du Faire et "
    "les entreprises pour se rencontrer, se comprendre, expérimenter et faire "
    "ensemble dans un espace accessible à tous·tes.</p>"
)

# Page « Le Faire Festival » — les trois sections illustrees, dans l'ordre.
# / "Le Faire Festival" page — the three illustrated sections, in order.
FESTIVAL_PROGRAMME = (
    "<p>Le Faire Festival est la grande rencontre des espaces du Faire et des "
    "makers en France ! Les 28, 29 et 30 mai, nous transformons La Cité à "
    "Toulouse, lieu de l'innovation toulousaine, en un immense espace de "
    "rencontre avec une programmation géante (ateliers, conférences, rencontres, "
    "soirées...). Le mot d'ordre ? Apprendre, créer, réparer et surtout, "
    "partager. Cette année, nous mettons d'ailleurs à l'honneur les 'tutos' et "
    "la documentation : parce que faire, c'est bien, mais transmettre comment "
    "faire, c'est encore mieux ! Le Faire Festival est un événement citoyen, "
    "indépendant et unique, porté par une communauté de makers, d'artisans, de "
    "bénévoles et de curieux qui partagent l'envie de fabriquer, transmettre et "
    "expérimenter ensemble pour contribuer à changer nos façons de produire et "
    "consommer.</p>"
    "<p>*Nous utilisons volontairement certains mots anglais comme 'maker', "
    "'FabLab' ou 'workshop', car ils font partie de la culture internationale de "
    "la fabrication partagée. Le mot 'maker' désigne une personne qui fabrique "
    "par elle-même, avec les autres, dans une logique de partage, "
    "d'expérimentation et d'apprentissage collectif.</p>"
    "<p>Vous pouvez construire votre propre programme en piochant parmi nos 22 "
    "thématiques (textile, réparation, bois, terre...). Au programme pour le "
    "grand public :</p>"
    "<ul>"
    "<li>→ Participez à des dizaines d'ateliers pratiques pour apprendre un "
    "nouveau savoir-faire, utiliser des outils manuels ou des machines "
    "numériques (imprimantes 3D, découpeuses laser…).</li>"
    "<li>→ Assistez à nos grands incontournables comme la course de robots, nos "
    "défilés de mode engagés, et flânez dans nos différents marchés de créateurs "
    "et créatrices.</li>"
    "<li>→ Rencontrez des artisans, makers, inventeur·rice·s, écoutez des "
    "conférences passionnantes et découvrez des solutions concrètes pour rendre "
    "notre monde plus durable et solidaire.</li>"
    "</ul>"
)

FESTIVAL_COLLECTIF = (
    "<p>Le Faire Festival est le fruit d'une véritable dynamique collective.</p>"
    "<p>Pour garantir son ancrage local, l'événement est conçu et pensé en "
    "étroite collaboration avec le RoseLab et des dizaines de personnes à "
    "Toulouse, plus de 110 tiers-lieux de fabrication partout en France, à "
    "l'échelle régionale avec la Rosêe, le réseau des tiers-lieux d'Occitanie, "
    "et au niveau national avec France Tiers-Lieux, ANTL et RFFLabs. C'est la "
    "force de cette coopération qui donne vie au festival.</p>"
)

FESTIVAL_LIEU = (
    "<p>Le cœur du festival bat à La Cité (55 avenue Louis Breguet, 31400 "
    "Toulouse), un lieu emblématique dédié à l'innovation collaborative en "
    "Occitanie.</p>"
    "<p>Le festival s'étend également hors des murs lors de nos soirées festives "
    "dans des lieux emblématiques de la ville, comme cette année avec les "
    "Imbriqués ou la clôture du festival dans un lieu incontournable de la "
    "sphère culturelle toulousaine, le musée des Abattoirs.</p>"
)

# Foire aux questions — une entree par question, dans l'ordre du site.
# / FAQ — one entry per question, in the site's order.
FAQ = [
    (
        "→ POUVEZ-VOUS NOUS PRÉSENTER LE FAIRE FESTIVAL ?",
        "<p>Le Faire Festival est un festival pour FAIRE ensemble. Autour de la "
        "matière et de la matérialité, les FabLabs, Espaces et Communautés du "
        "Faire, le grand public se retrouvent pour partager des savoir-faire, "
        "découvrir des machines et outils, expérimenter des techniques, "
        "rencontrer des partenaires et d'autres lieux de fabrication...</p>"
        "<p>Open Source, collectif et évolutif comme tout prototype, ce festival "
        "de fabrication partagée et distribuée donne la possibilité de :</p>"
        "<ul>"
        "<li>→ Faire découvrir la fabrication au plus grand nombre.</li>"
        "<li>→ Partager, mutualiser, expérimenter le Faire (techniques, outils, "
        "machines, savoir-faire, matières).</li>"
        "<li>→ Produire des communs de fabrication (matériauthèque, guide "
        "d'animation...).</li>"
        "<li>→ Repenser le lien entre production et consommation pour contribuer "
        "à changer le monde.</li>"
        "</ul>"
        "<p>Trois jours pour presque tout fabriquer ensemble !</p>",
    ),
    (
        "→ EXPLIQUEZ-NOUS CETTE TENDANCE DES 'ESPACES DU FAIRE' ?",
        "<p>Un Espace du Faire est un FabLab (Laboratoire de fabrication), une "
        "Manufacture, un HackerSpace, un Atelier de bricoleurs, un MakerSpace, "
        "un Espace de couture partagé, un Tiers-Lieu de fabrication... c'est un "
        "lieu qui partage des outils, machines et savoir-faire ouvert à tous les "
        "publics (artisans, citoyen.ne.s, salarié.e.s, étudiant.e.s...) pour "
        "fabriquer localement tout en étant globalement connecté.</p>"
        "<p>Il mutualise des outils et savoir-faire de la fabrication "
        "artisanale, conventionnelle, industrielle et numérique pour passer "
        "rapidement de l'idée à l'objet et pour presque tout concevoir, "
        "fabriquer et réparer. Il permet de produire des communs par la "
        "documentation et le faire ensemble.</p>",
    ),
    (
        "→ QUI SONT LES MAKERS ?",
        "<p>Pour commencer, les Makers (du verbe Make = Faire en anglais) sont "
        "littéralement des « faiseurs ». Ils conçoivent, fabriquent, ou réparent "
        "toutes sortes d'objets. Un.e Maker est une personne qui fabrique par "
        "elle-même et avec les autres dans les loisirs créatifs (DIY), "
        "l'artisanat, la réparation, la bricole, l'industrie...</p>"
        "<p>pour se réapproprier la production pour consommer différemment. Sans "
        "limites, les Makers fabriquent ensemble et contribuent à avoir une "
        "société plus circulaire, plus durable, plus locale tout en étant "
        "globalement connecté, plus inclusive, plus accessible en participant "
        "aux changements climatiques et sociales !</p>",
    ),
    (
        "→ POUVEZ-VOUS NOUS EN DIRE PLUS SUR QUI PORTE LE FAIRE FESTIVAL ?",
        "<p>Le Faire Festival est un événement open source et collectif coporté "
        "par le RedLab (Réseau des Labs d'Occitanie), le RoseLab et le "
        "Laboratoire Organique de Lustar (deux Espaces du Faire occitans) "
        "regroupés dans la Manufacture Distribuée.</p>"
        "<p>Il a lieu à Toulouse à La Cité, cœur de l'innovation collaborative "
        "et durable, avec la collaboration des réseaux Tiers-Lieux/Makers comme "
        "la Rosée, le RFFLabs, l'Association Nationale des Tiers-Lieux et avec "
        "le soutien de La Région Occitanie et de Toulouse Métropole. Plus que "
        "des acteur.rice.s, c'est un commun qui appartient à toutes et à "
        "tous.</p>",
    ),
    (
        "→ QUI SONT LES PARTICIPANT·E·S DU FAIRE FESTIVAL ?",
        "<p>Littéralement, tout le monde. La Fabrication, le Faire Ensemble, Les "
        "Espaces du Faire sont partout et touchent tout le monde. Ce Festival de "
        "3 jours est à la fois un salon professionnel pour ceux.celles qui ont "
        "fait de la fabrication leurs métiers (jeudi, vendredi) et à la fois un "
        "moment de partage pour le grand public pour découvrir, expérimenter et "
        "presque tout fabriquer (samedi).</p>"
        "<p>Simplement, c'est un festival pour FABRIQUER et FAIRE ENSEMBLE !</p>",
    ),
    (
        "→ COMMENT POUVONS-NOUS CONTRIBUER AU FAIRE FESTIVAL ?",
        "<p>Le Faire Festival appartient à toutes et à tous. Tout le monde peut "
        "contribuer de différentes façons :</p>"
        "<p>En devenant bénévoles : aidez-nous à penser, concevoir, et organiser "
        "le plus grand festival de fabrication. Que ce soit en amont ou pendant "
        "le festival, nous avons besoin de vous !</p>"
        "<p>En relayant et diffusant le Faire Festival sur vos réseaux sociaux, "
        "newsletter.</p>"
        "<p>En participant à un de nos Labs Distribués.</p>"
        "<p>L'équipe du Faire Festival reste disponible sur l'adresse mail "
        "contact@fairefestival.fr pour répondre à toutes vos questions !</p>",
    ),
]


PAGES = [
    {
        "slug": "accueil",
        "titre": "Faire Festival",
        "position": 0,
        "est_accueil": True,
        "meta_description": (
            "Le Faire Festival : trois jours de fabrication partagée à La Cité, "
            "Toulouse, les 28, 29 et 30 mai."
        ),
        # Image d'identite du lieu, lue par la banniere du skin.
        # / Venue identity image, read by the skin's banner.
        "config_image": "logopage.webp",
        "blocs": [
            {
                "type": "SECTION",
                "affichage": "BANNIERE",
                "titre": "Faire Festival",
                "sous_titre": (
                    "Le grand rendez-vous toulousain pour réinventer notre façon "
                    "de produire, de consommer et de transmettre !"
                ),
            },
            {
                "type": "SECTION",
                "affichage": "MEDIA_ET_CARTES",
                "titre": "Le Faire Festival, c'est quoi ?",
                "texte": ACCUEIL_PRESENTATION,
                "video": "motion-table.mp4",
                "contenu": [
                    {
                        "titre": "JOUR 01",
                        "badge": "",
                        "texte": "Entre Espaces\nCommunautés du Faire\net Entreprises",
                    },
                    {
                        "titre": "JOUR 02",
                        "badge": "",
                        "texte": "Entre Espaces\nCommunautés du Faire\net Entreprises",
                    },
                    {
                        "titre": "JOUR 03",
                        "badge": "gratuit",
                        "texte": "Entre Grand Public,\nEspaces et\nCommunautés du Faire",
                    },
                ],
                "bouton_label": "En savoir plus sur le Faire Festival",
                "bouton_url": "/le-faire-festival/",
            },
            # Image-titre DESSINEE, d'ou VIGNETTE_TITRE : en pleine largeur elle
            # serait etiree. / DRAWN title image, hence VIGNETTE_TITRE.
            {
                "type": "IMAGES",
                "affichage": "VIGNETTE_TITRE",
                "image": "Fichier-14.png",
            },
            # Les trois cartes d'orientation. Le bouton « Billetterie » mene aux
            # ADHESIONS, et c'est voulu : le pass d'un festival est techniquement
            # une adhesion de trois jours. Ne pas « corriger » vers /event/.
            # / The "Billetterie" button leads to MEMBERSHIPS on purpose: a
            # festival pass is technically a three-day membership.
            {
                "type": "SECTION",
                "affichage": "CARTE",
                "texte": (
                    "Rendez-vous sur l'onglet billetterie et prenez vos billets "
                    "à prix libre !"
                ),
                "bouton_label": "Billetterie",
                "bouton_url": "/memberships/",
                "image": "photo_tutos-09.webp",
            },
            {
                "type": "SECTION",
                "affichage": "CARTE",
                "texte": "Accédez aux différents événements classés par 22 thématiques !",
                "bouton_label": "Programmation",
                "bouton_url": "/event/",
                "image": "photo_tutos-08.webp",
            },
            {
                "type": "SECTION",
                "affichage": "CARTE",
                "texte": "Venez profiter les 28, 29 et 30 mai lors du Faire Festival !",
                "bouton_label": "Infos pratiques",
                "bouton_url": "/infos-pratiques/",
                "image": "photo_tutos-07.webp",
            },
        ],
    },
    {
        "slug": "le-faire-festival",
        "titre": "Le Faire Festival",
        "position": 1,
        "meta_description": (
            "Le Faire Festival : la grande rencontre des espaces du Faire et des "
            "makers en France, à La Cité, Toulouse."
        ),
        "blocs": [
            {
                "type": "IMAGES",
                "affichage": "PLEINE_LARGEUR",
                "titre": "Le Faire Festival",
                "image": "Fichier-18.png",
            },
            {
                # Bloc TEXTE : son champ contient du MARKDOWN, pas du HTML.
                # / TEXTE block: its field holds MARKDOWN, not HTML.
                "type": "TEXTE",
                "titre": (
                    "Le grand rendez-vous toulousain pour réinventer notre façon "
                    "de produire, de consommer et de transmettre !"
                ),
                "texte": (
                    "Le Faire Festival invite tou·te·s les citoyen·ne·s, "
                    "artisan·e·s, créatif·ve·s, associations, fablabs, ateliers "
                    "et collectifs à imaginer et partager leurs savoir-faire. "
                    "Notre objectif ? Mettre en lumière toutes les façons de "
                    "documenter : guides, vidéos, pas-à-pas, ateliers de "
                    "transmission, protocoles ouverts... en bref, tout ce qui "
                    "permet d'apprendre en faisant !\n"
                ),
            },
            {
                "type": "SECTION",
                "affichage": "TEXTE_IMAGE_GAUCHE",
                "texte": FESTIVAL_PROGRAMME,
                "image": "Fichier-15.webp",
            },
            {
                "type": "SECTION",
                "affichage": "TEXTE_IMAGE_DROITE",
                "texte": FESTIVAL_COLLECTIF,
                "image": "Fichier-16.webp",
            },
            {
                "type": "SECTION",
                "affichage": "TEXTE_IMAGE_GAUCHE",
                "texte": FESTIVAL_LIEU,
                "image": "Fichier-17.webp",
            },
        ],
    },
    {
        "slug": "infos-pratiques",
        "titre": "Infos pratiques",
        "position": 2,
        "meta_description": (
            "Horaires, accès et foire aux questions du Faire Festival, à La Cité, "
            "55 avenue Louis Breguet, Toulouse."
        ),
        "blocs": [
            # UN SEUL bloc LIEU porte les deux moities : les infos pratiques a
            # gauche, le logo et les reperes a droite. Les separer donnerait deux
            # sections a moitie vides.
            # / ONE LIEU block carries both halves: practical info on the left,
            # logo and markers on the right.
            {
                "type": "LIEU",
                "titre": "Accéder au Faire Festival",
                "badge": "LA CITÉ — 55 AVENUE LOUIS BREGUET, 31400 TOULOUSE",
                "image": "logo.webp",
                "image_secondaire": "datehorizon.png",
                "contenu": [
                    {
                        "type": "para",
                        "texte": "Bienvenue dans le FAIRE Festival, trois jours pour FAIRE ensemble.",
                    },
                    {"type": "badge", "texte": "Horaires"},
                    {"type": "horaire", "texte": "JEUDI & VENDREDI 09h → 21h"},
                    {"type": "horaire", "texte": "SAMEDI 10h → 19h"},
                    {"type": "badge", "texte": "Adresse"},
                    {
                        "type": "adresse",
                        "texte": "La Cité\n55 avenue Louis Breguet\n31400 Toulouse",
                    },
                    {
                        "type": "accessibilite",
                        "texte": "LE FAIRE FESTIVAL EST ACCESSIBLE AUX PERSONNES À MOBILITÉ RÉDUITE.",
                    },
                    {
                        "type": "transport",
                        "titre": "VOITURE",
                        "lignes": [
                            "À 5 min des 2 périphériques",
                            "A620 – sortie 20 Complexe scientifique",
                            "A61 – sortie 18 Montaudran",
                        ],
                    },
                    {
                        "type": "transport",
                        "titre": "BUS",
                        "lignes": [
                            "Ligne L9 L'union/Saint Orens - Arrêt Tahiti - 10 min. à pied",
                            "Ligne 37 Jolimont/Ramonville - Arrêt Bréguet - 3min. à pied",
                            "Ligne L8 Marengo SNCF/Gonin - Arrêt Aude - 15 min. à pied",
                        ],
                    },
                    {
                        "type": "transport",
                        "titre": "TRAIN",
                        "lignes": ["À 5 mn à pied de l'arrêt TER Montaudran"],
                    },
                ],
                "points_gps": [
                    {"lat": 43.5686, "lng": 1.4820, "label": "La Cité — Faire Festival"}
                ],
            },
            {
                "type": "IMAGES",
                "affichage": "PLEINE_LARGEUR",
                "image": "plan-festival.webp",
            },
            {"type": "TEXTE", "titre": "Foire aux questions"},
        ]
        # Une question = un bloc FAQ. Les blocs FAQ voisins se rangent en deux
        # colonnes par le CSS. / One question = one FAQ block; neighbouring FAQ
        # blocks lay out in two columns through the CSS.
        + [
            {"type": "FAQ", "titre": question, "texte": reponse}
            for question, reponse in FAQ
        ],
    },
]
