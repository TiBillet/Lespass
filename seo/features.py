"""
Registre de contenu des fonctionnalites ROOT (cartes + pages de detail).
/ Content registry for ROOT features (cards + detail pages).

LOCALISATION : seo/features.py

`FEATURE_DETAILS` est la source unique des fonctionnalites affichees sur la
landing et le hub `/features/`. Chaque entree alimente :
  - la carte (grille de la landing + hub) : `title`, `icon`, `card_desc`,
  - la page de detail indexable `/features/<slug>/` : tout le reste,
  - le JSON-LD `ItemList` (SEO sitelinks) et le sitemap ROOT.

L'ordre des cles = l'ordre d'affichage des cartes (les dicts Python gardent
l'ordre d'insertion). Le texte source est en FRANCAIS ; la traduction anglaise
se fait depuis le francais.

/ `FEATURE_DETAILS` is the single source of truth for the features shown on the
landing and the `/features/` hub. Key order = display order.

Schema d'une entree / Entry schema:
    "slug": {
        "title":            titre court (H1, fil d'Ariane, carte),
        "icon":             classe Bootstrap Icons (ex. "bi-ticket-perforated"),
        "card_desc":        texte court de la carte (grille),
        "tagline":          phrase d'accroche sous le titre (page detail),
        "lead":             paragraphe d'introduction (riche, indexable),
        "page_title":       balise <title> SEO (avec mots-cles, ~50-60 car.),
        "meta_description": meta description SEO (< 160 caracteres),
        "doc_url":          lien profond vers la documentation,
        "sections": [       blocs texte + capture, alternes a l'affichage
            {"heading": ..., "text": ..., "capture_alt": ...},
        ],
    }
"""

from django.utils.translation import gettext_lazy as _

# Racine de la documentation. Les liens profonds sont composes depuis cette base.
# / Documentation root. Deep links are composed from this base.
DOC_BASE = "https://tibillet.github.io/documentation_v3/"


FEATURE_DETAILS = {
    # ----------------------------------------------------------------------
    # ADHESIONS ET ABONNEMENTS / MEMBERSHIPS AND SUBSCRIPTIONS
    # ----------------------------------------------------------------------
    "adhesions": {
        "title": _("Adhésions et abonnements"),
        "icon": "bi-person-check",
        "card_desc": _(
            "Gérez les adhésions à votre association et proposez des abonnements. "
            "Suivez les renouvellements et offrez des avantages exclusifs aux membres."
        ),
        "tagline": _("Gérez vos membres et vos abonnements, sans tableur."),
        "lead": _(
            "TiBillet gère les adhésions de votre association et les abonnements "
            "récurrents. Chaque membre a une fiche, un statut à jour, et accède "
            "automatiquement à ses avantages : tarifs réduits, accès réservés, "
            "monnaie cadeau. Les renouvellements sont suivis, les relances possibles, "
            "et tout reste relié à votre billetterie et à votre caisse."
        ),
        "page_title": _("Adhésions et abonnements en ligne — TiBillet"),
        "meta_description": _(
            "Gérez les adhésions de votre association et les abonnements récurrents : "
            "statut à jour, avantages membres, renouvellements et relances."
        ),
        "doc_url": DOC_BASE + "guide-des-lieux/billetterie-agenda-lespass/creer-des-adhesions-et-leurs-tarifs/",
        "sections": [
            {
                "heading": _("Une adhésion reliée à tout le reste"),
                "text": _(
                    "L'adhésion n'est pas une case isolée : elle débloque des tarifs "
                    "préférentiels en billetterie, des accès au bar, des avantages "
                    "cashless. Le statut d'un membre est vérifié partout, automatiquement."
                ),
                "capture_alt": _(
                    "Fiche d'un membre avec son statut d'adhésion à jour et ses "
                    "avantages associés."
                ),
            },
            {
                "heading": _("Abonnements récurrents et prélèvement"),
                "text": _(
                    "Proposez des cotisations annuelles ou des abonnements mensuels, "
                    "payés en une fois ou prélevés régulièrement (SEPA). TiBillet suit "
                    "les échéances et signale les retards."
                ),
                "capture_alt": _(
                    "Écran de configuration d'un abonnement récurrent avec options de "
                    "prélèvement."
                ),
            },
            {
                "heading": _("Renouvellements et relances"),
                "text": _(
                    "Voyez d'un coup d'œil qui est à jour, qui est en retard, qui "
                    "arrive à échéance. Relancez par email les personnes concernées, "
                    "sans exporter de liste à la main."
                ),
                "capture_alt": _(
                    "Liste des adhérent·es filtrée par statut : à jour, en retard, à "
                    "renouveler."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # BILLETTERIE / TICKETING
    # ----------------------------------------------------------------------
    "billetterie": {
        "title": _("Billetterie"),
        "icon": "bi-ticket-perforated",
        "card_desc": _(
            "Événements gratuits et payants avec prix préférentiels pour les "
            "adhérents. Sans frais cachés, sans commission surprise."
        ),
        "tagline": _("Vendez vos billets sans frais cachés ni commission surprise."),
        "lead": _(
            "La billetterie de TiBillet gère vos événements gratuits et payants, "
            "avec des tarifs préférentiels pour vos adhérent·es. Pas de commission "
            "prélevée sur chaque billet, pas de frais de dossier dissimulés : le prix "
            "affiché est le prix payé. Tout est relié à votre agenda et à votre base "
            "de membres, sur un logiciel libre que personne ne peut fermer."
        ),
        "page_title": _("Billetterie en ligne sans frais cachés — TiBillet"),
        "meta_description": _(
            "Billetterie en ligne libre et coopérative : événements gratuits et "
            "payants, tarifs adhérents, sans frais cachés ni commission."
        ),
        "doc_url": DOC_BASE + "guide-des-lieux/billetterie-agenda-lespass/",
        "sections": [
            {
                "heading": _("Des billets sans frais cachés"),
                "text": _(
                    "Vous fixez vos prix, vous encaissez la totalité. TiBillet ne "
                    "prélève aucune commission par billet. Les seuls frais éventuels "
                    "sont ceux, transparents, de votre prestataire de paiement. Pour "
                    "une association, chaque euro compte : il reste chez vous."
                ),
                "capture_alt": _(
                    "Page de réservation d'un événement avec le détail des tarifs et "
                    "le prix total sans frais ajoutés."
                ),
            },
            {
                "heading": _("Tarifs préférentiels pour les adhérent·es"),
                "text": _(
                    "Proposez un prix réduit aux personnes à jour de cotisation. "
                    "TiBillet vérifie l'adhésion au moment de la réservation : pas "
                    "besoin de gérer des codes promo à la main. Vos membres "
                    "bénéficient automatiquement de leur avantage."
                ),
                "capture_alt": _(
                    "Formulaire de réservation affichant un tarif adhérent réduit "
                    "appliqué automatiquement."
                ),
            },
            {
                "heading": _("Paiement et billets reliés à votre agenda"),
                "text": _(
                    "Chaque vente alimente directement votre programmation et vos "
                    "statistiques. Les billets sont envoyés par email, scannables à "
                    "l'entrée. Et comme vos événements sont structurés pour les "
                    "moteurs de recherche, ils sont trouvés par le public."
                ),
                "capture_alt": _(
                    "Billet électronique avec QR code, prêt à être scanné à l'entrée "
                    "de l'événement."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # AGENDA FEDERE / FEDERATED AGENDA
    # ----------------------------------------------------------------------
    "agenda-federe": {
        "title": _("Agenda fédéré"),
        "icon": "bi-calendar2-week",
        "card_desc": _(
            "Créez un agenda partagé et choisissez les lieux avec qui partager vos "
            "événements. Fédérez votre programmation avec d'autres structures."
        ),
        "tagline": _("Un agenda partagé entre lieux, sans plateforme centrale."),
        "lead": _(
            "L'agenda fédéré relie votre programmation à celle d'autres lieux. Vous "
            "choisissez avec qui partager vos événements et lesquels remontent. Chaque "
            "lieu garde son autonomie — son agenda, sa charte, ses choix — tout en "
            "bénéficiant de la visibilité du réseau. Pas de plateforme centrale qui "
            "décide à votre place."
        ),
        "page_title": _("Agenda culturel fédéré et partagé — TiBillet"),
        "meta_description": _(
            "Un agenda culturel fédéré entre lieux : choisissez vos partenaires, "
            "partagez vos événements, gardez votre autonomie. Sans plateforme centrale."
        ),
        "doc_url": DOC_BASE + "guide-des-lieux/billetterie-agenda-lespass/",
        "sections": [
            {
                "heading": _("Vous choisissez avec qui fédérer"),
                "text": _(
                    "La fédération est un choix, pas une obligation. Vous décidez "
                    "quels lieux voient vos événements et lesquels vous affichez chez "
                    "vous. Une relation de confiance, réversible à tout moment."
                ),
                "capture_alt": _(
                    "Écran de sélection des lieux partenaires avec qui partager "
                    "l'agenda."
                ),
            },
            {
                "heading": _("Une saisie, plusieurs agendas"),
                "text": _(
                    "Créez un événement une fois ; il apparaît sur votre agenda et, "
                    "si vous le souhaitez, sur ceux de vos partenaires. Pas de double "
                    "saisie, pas de copier-coller entre plateformes."
                ),
                "capture_alt": _(
                    "Un même événement visible sur l'agenda de plusieurs lieux "
                    "fédérés."
                ),
            },
            {
                "heading": _("L'autonomie d'abord"),
                "text": _(
                    "Chaque lieu reste maître de son espace : son identité, ses "
                    "tarifs, ses conditions. La fédération ajoute de la visibilité sans "
                    "imposer de règles communes ni de gouvernance centrale."
                ),
                "capture_alt": _(
                    "Deux agendas de lieux distincts partageant certains événements "
                    "en commun."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # CAISSE ENREGISTREUSE / CASH REGISTER (POS)
    # ----------------------------------------------------------------------
    "caisse": {
        "title": _("Caisse enregistreuse"),
        "icon": "bi-shop",
        "card_desc": _(
            "Solution complète pour gérer vos ventes sur place, avec imprimantes de "
            "préparation en cuisine et gestion des stocks."
        ),
        "tagline": _("Encaissez au bar et sur les stands, simplement."),
        "lead": _(
            "La caisse TiBillet gère vos ventes sur place : bar, restauration, "
            "boutique. Elle pilote les imprimantes de préparation en cuisine, suit les "
            "stocks, et accepte espèces, carte bancaire et cashless. Pensée pour le "
            "rythme d'un événement, elle reste rapide même quand la file s'allonge."
        ),
        "page_title": _("Caisse enregistreuse pour lieux culturels — TiBillet"),
        "meta_description": _(
            "Caisse enregistreuse pour bar et restauration : boutons rapides, "
            "impression en cuisine, gestion des stocks, clôture comptable."
        ),
        "doc_url": DOC_BASE + "guide-des-lieux/caisse-cashless-laboutik/",
        "sections": [
            {
                "heading": _("Pensée pour le rush"),
                "text": _(
                    "Boutons clairs, grands, organisés par catégorie : on encaisse "
                    "vite, sans se tromper. Plusieurs points de vente peuvent tourner "
                    "en parallèle sur le même événement."
                ),
                "capture_alt": _(
                    "Interface de caisse avec les articles organisés en boutons par "
                    "catégorie."
                ),
            },
            {
                "heading": _("Cuisine et préparation"),
                "text": _(
                    "Chaque commande part à l'imprimante du bon poste : bar, cuisine, "
                    "planche. Le personnel prépare sans recopier, le service suit le "
                    "rythme."
                ),
                "capture_alt": _(
                    "Ticket de préparation imprimé automatiquement au poste cuisine."
                ),
            },
            {
                "heading": _("Stocks et clôture comptable"),
                "text": _(
                    "Les stocks se décrémentent à chaque vente. En fin de service, la "
                    "clôture donne le détail des recettes par moyen de paiement, prête "
                    "pour la comptabilité."
                ),
                "capture_alt": _(
                    "Écran de clôture de caisse avec le récapitulatif des ventes par "
                    "moyen de paiement."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # CASHLESS ET CARTE NFC / CASHLESS AND NFC CARD
    # ----------------------------------------------------------------------
    "cashless-nfc": {
        "title": _("Cashless et carte NFC"),
        "icon": "bi-credit-card-2-front",
        "card_desc": _(
            "Système cashless comme en festival, avec vérification de l'adhésion sur "
            "la carte. Une seule carte pour plusieurs lieux du réseau."
        ),
        "tagline": _("Une seule carte sans contact pour plusieurs lieux du réseau."),
        "lead": _(
            "Le cashless de TiBillet fonctionne comme en festival : une carte sans "
            "contact rechargée à l'avance, des paiements rapides au bar et sur les "
            "stands. La même carte sert dans plusieurs lieux fédérés, vérifie "
            "l'adhésion, et peut porter plusieurs monnaies — euros, cadeaux, temps — "
            "sur une seule puce."
        ),
        "page_title": _("Cashless et carte NFC multi-lieux — TiBillet"),
        "meta_description": _(
            "Cashless NFC multi-lieux : une carte sans contact pour payer au bar, "
            "vérifier l'adhésion et porter plusieurs monnaies."
        ),
        "doc_url": DOC_BASE + "les-bases-et-valeurs-tibillet/les-bases-du-cashless-tibillet/",
        "sections": [
            {
                "heading": _("Une carte, plusieurs lieux"),
                "text": _(
                    "Grâce à la fédération, une même carte NFC est reconnue dans tous "
                    "les lieux connectés du réseau. Le public n'a plus besoin d'une "
                    "carte par festival ou par bar associatif : il recharge une fois, "
                    "il paie partout où le réseau est présent."
                ),
                "capture_alt": _(
                    "Carte NFC TiBillet approchée d'un terminal de paiement au bar "
                    "d'un lieu culturel."
                ),
            },
            {
                "heading": _("L'adhésion vérifiée sur la carte"),
                "text": _(
                    "La carte porte l'information d'adhésion. Au moment de payer ou "
                    "d'accéder à un espace réservé aux membres, le système vérifie "
                    "directement sur la carte, sans connexion permanente. Pratique "
                    "pour les lieux où le réseau n'est pas toujours fiable."
                ),
                "capture_alt": _(
                    "Écran de caisse affichant le statut d'adhésion lu sur la carte "
                    "NFC d'un·e visiteur·euse."
                ),
            },
            {
                "heading": _("Multi-monnaies : euros, cadeaux, temps"),
                "text": _(
                    "Une seule carte peut contenir plusieurs monnaies : des euros "
                    "pour le bar, une monnaie cadeau pour valoriser les bénévoles, "
                    "une monnaie temps pour l'entraide. Le cashless devient un outil "
                    "d'économie locale, pas seulement un moyen de paiement."
                ),
                "capture_alt": _(
                    "Détail d'une carte montrant plusieurs soldes distincts : euros, "
                    "monnaie cadeau et monnaie temps."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # MONNAIE LOCALE ET TEMPS / LOCAL AND TIME CURRENCY
    # ----------------------------------------------------------------------
    "monnaie-locale-temps": {
        "title": _("Monnaie locale et temps"),
        "icon": "bi-coin",
        "card_desc": _(
            "Monnaie temps, cadeaux et valorisation de bénévoles. Multi-monnaies sur "
            "une seule carte : euros, cadeaux, temps."
        ),
        "tagline": _("Plusieurs monnaies sur une carte : euros, cadeaux, temps."),
        "lead": _(
            "Au-delà de l'euro, TiBillet gère des monnaies dédiées : une monnaie "
            "cadeau pour remercier, une monnaie temps pour valoriser le bénévolat, une "
            "monnaie locale pour faire circuler la valeur dans le réseau. Tout tient "
            "sur la même carte, sans mélanger les comptes. Le cashless devient un "
            "outil d'économie locale et solidaire."
        ),
        "page_title": _("Monnaie locale et monnaie temps — TiBillet"),
        "meta_description": _(
            "Monnaie locale, monnaie temps et monnaie cadeau sur une seule carte : "
            "valorisez les bénévoles et faites circuler la valeur dans le réseau."
        ),
        "doc_url": DOC_BASE + "guide-des-lieux/caisse-cashless-laboutik/guides-pratiques-cas-avances/federation-des-lieux-et-des-monnaies/",
        "sections": [
            {
                "heading": _("Valoriser les bénévoles"),
                "text": _(
                    "Créditez du temps ou des cadeaux aux personnes qui font vivre le "
                    "lieu. Elles dépensent au bar ou ailleurs dans le réseau : une "
                    "reconnaissance concrète, pas une promesse."
                ),
                "capture_alt": _(
                    "Solde de monnaie temps crédité sur la carte d'un·e bénévole."
                ),
            },
            {
                "heading": _("Des comptes séparés, une seule carte"),
                "text": _(
                    "Euros, cadeaux, temps : chaque monnaie a son solde, ses règles, "
                    "sa traçabilité. On ne paie pas une consommation avec du temps "
                    "bénévole par erreur."
                ),
                "capture_alt": _(
                    "Détail d'une carte affichant trois soldes distincts et leurs "
                    "règles d'usage."
                ),
            },
            {
                "heading": _("Une monnaie qui circule dans le réseau"),
                "text": _(
                    "Grâce à la fédération, une monnaie locale peut être acceptée dans "
                    "plusieurs lieux partenaires. La valeur reste dans le réseau plutôt "
                    "que de fuir vers les grandes plateformes."
                ),
                "capture_alt": _(
                    "Une monnaie locale acceptée dans plusieurs lieux fédérés du "
                    "réseau."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # DONNEES OUVERTES / OPEN DATA
    # ----------------------------------------------------------------------
    "donnees-ouvertes": {
        "title": _("Données ouvertes"),
        "icon": "bi-database",
        "card_desc": _(
            "Toutes les données non personnelles de votre lieu sont accessibles par "
            "API, dans un vocabulaire standard (schema.org / JSON-LD), sous licence "
            "ouverte. Vos événements, votre programmation : libres de circuler."
        ),
        "tagline": _("Vos données publiques, libres de circuler, par API."),
        "lead": _(
            "Les données non personnelles de votre lieu — événements, programmation, "
            "informations pratiques — sont accessibles par une API ouverte, dans un "
            "vocabulaire standard (schema.org / JSON-LD), sous licence libre. Vos "
            "événements peuvent alimenter d'autres agendas, des applications tierces, "
            "des moteurs de recherche. Vous restez propriétaire, mais rien n'est "
            "enfermé."
        ),
        "page_title": _("Données ouvertes par API (schema.org) — TiBillet"),
        "meta_description": _(
            "Données ouvertes par API au format schema.org / JSON-LD, sous licence "
            "libre : vos événements et votre programmation, libres de circuler."
        ),
        "doc_url": DOC_BASE + "guide-des-lieux/guide-de-reference-technique/billetterie-agenda-lespass/connecter-et-synchroniser-vos-outils/integration/",
        "sections": [
            {
                "heading": _("Un vocabulaire standard"),
                "text": _(
                    "TiBillet expose ses données en schema.org / JSON-LD, le langage "
                    "que comprennent Google, les agendas culturels et la plupart des "
                    "outils. Pas de format propriétaire à réinventer."
                ),
                "capture_alt": _(
                    "Réponse de l'API d'un événement structurée en JSON-LD schema.org."
                ),
            },
            {
                "heading": _("Interopérable par conception"),
                "text": _(
                    "Une API documentée permet à vos outils — site web, application, "
                    "partenaire — de lire votre programmation en temps réel. "
                    "L'interopérabilité avec un ERP devient possible."
                ),
                "capture_alt": _(
                    "Documentation de l'API listant les points d'accès événements et "
                    "lieux."
                ),
            },
            {
                "heading": _("Sous licence ouverte"),
                "text": _(
                    "Vos données publiques circulent sous licence libre : un autre "
                    "agenda peut les republier, un développeur peut bâtir dessus. La "
                    "donnée culturelle redevient un commun."
                ),
                "capture_alt": _(
                    "Mention de licence ouverte sur les données publiques exposées "
                    "par l'API."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # LOGICIEL LIBRE AGPLV3 / FREE SOFTWARE AGPLV3
    # ----------------------------------------------------------------------
    "logiciel-libre": {
        "title": _("Logiciel libre AGPLv3"),
        "icon": "bi-code-slash",
        "card_desc": _(
            "Le code de TiBillet est publié sous licence AGPLv3. Personne ne peut le "
            "verrouiller, le fermer, le privatiser. C'est la première brique d'un "
            "commun numérique — la coopérative Code Commun fait le reste."
        ),
        "tagline": _("Un code libre que personne ne peut fermer."),
        "lead": _(
            "TiBillet est publié sous licence AGPLv3. Le code source est ouvert, "
            "auditable, modifiable. Personne — pas même nous — ne peut le verrouiller, "
            "le privatiser ou vous enfermer. C'est la première brique d'un commun "
            "numérique ; la coopérative Code Commun, à gouvernance partagée, assure le "
            "reste : la communauté, la maintenance, la direction."
        ),
        "page_title": _("Logiciel libre AGPLv3, commun numérique — TiBillet"),
        "meta_description": _(
            "TiBillet est un logiciel libre sous licence AGPLv3 : code ouvert, "
            "auditable, impossible à verrouiller. Un commun numérique coopératif."
        ),
        "doc_url": DOC_BASE + "les-bases-et-valeurs-tibillet/qui-sommes-nous/philosophie/",
        "sections": [
            {
                "heading": _("AGPLv3 : la liberté garantie"),
                "text": _(
                    "L'AGPLv3 impose que toute version modifiée et servie en ligne "
                    "reste libre. Impossible de prendre le code, de le fermer, et de "
                    "le revendre enfermé. La liberté est contagieuse, par conception."
                ),
                "capture_alt": _(
                    "Dépôt de code source public de TiBillet sous licence AGPLv3."
                ),
            },
            {
                "heading": _("Un commun, pas seulement du code"),
                "text": _(
                    "Un dépôt Git libre ne suffit pas. Inspiré des travaux d'Elinor "
                    "Ostrom, TiBillet est porté par une communauté vivante et une "
                    "gouvernance organisée — la coopérative Code Commun, à trois "
                    "collèges égaux."
                ),
                "capture_alt": _(
                    "Schéma de la gouvernance coopérative à trois collèges de Code "
                    "Commun."
                ),
            },
            {
                "heading": _("Pas de dépendance, pas de rançon"),
                "text": _(
                    "Votre outil ne peut pas être racheté puis verrouillé contre "
                    "vous. Si la coopérative disparaissait, le code resterait libre et "
                    "reprenable. Votre indépendance est structurelle."
                ),
                "capture_alt": _(
                    "Comparaison entre un outil propriétaire fermé et l'outil libre "
                    "TiBillet."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # AGENDA PARTICIPATIF / PARTICIPATORY AGENDA
    # ----------------------------------------------------------------------
    "agenda-participatif": {
        "title": _("Agenda participatif"),
        "icon": "bi-people",
        "card_desc": _(
            "Recevez les propositions d'événements de votre réseau via un formulaire "
            "ouvert. Pour chaque proposition, vous choisissez : publier sur votre "
            "agenda, ou inviter l'organisateur·ice à créer son espace et rejoindre "
            "votre fédération."
        ),
        "tagline": _("Recevez des propositions d'événements, vous décidez."),
        "lead": _(
            "L'agenda participatif ouvre votre programmation aux propositions de votre "
            "réseau, via un formulaire public. Pour chaque proposition reçue, vous "
            "gardez la main : publier l'événement sur votre agenda, ou inviter "
            "l'organisateur·ice à créer son propre espace et à rejoindre votre "
            "fédération. La porte est ouverte, mais c'est vous qui décidez qui entre."
        ),
        "page_title": _("Agenda participatif et propositions — TiBillet"),
        "meta_description": _(
            "Agenda participatif : recevez les propositions d'événements via un "
            "formulaire public et gardez le contrôle éditorial sur ce qui est publié."
        ),
        "doc_url": DOC_BASE + "guide-des-lieux/billetterie-agenda-lespass/",
        "sections": [
            {
                "heading": _("Un formulaire ouvert à tous"),
                "text": _(
                    "N'importe qui peut proposer un événement via un formulaire "
                    "public. Vous recevez la proposition complète sans créer de compte "
                    "à la place du proposant."
                ),
                "capture_alt": _(
                    "Formulaire public de proposition d'événement rempli par un·e "
                    "organisateur·ice."
                ),
            },
            {
                "heading": _("Vous gardez le contrôle éditorial"),
                "text": _(
                    "Rien n'est publié sans votre accord. Pour chaque proposition, "
                    "vous choisissez : publier, refuser, ou demander des précisions. "
                    "Votre agenda reste le vôtre."
                ),
                "capture_alt": _(
                    "File des propositions reçues avec les actions publier ou refuser "
                    "pour chacune."
                ),
            },
            {
                "heading": _("Inviter plutôt que centraliser"),
                "text": _(
                    "Plutôt que de tout héberger, vous pouvez inviter un·e "
                    "organisateur·ice à créer son espace et à rejoindre votre "
                    "fédération. Le réseau grandit par la rencontre, pas par la "
                    "centralisation."
                ),
                "capture_alt": _(
                    "Invitation envoyée à un·e organisateur·ice pour créer son propre "
                    "espace."
                ),
            },
        ],
    },
    # ----------------------------------------------------------------------
    # REFERENCEMENT ET SEO / SEARCH ENGINE OPTIMIZATION
    # ----------------------------------------------------------------------
    "seo": {
        "title": _("Référencement et SEO"),
        "icon": "bi-search",
        "card_desc": _(
            "Chaque page de lieu et chaque événement sont structurés en JSON-LD "
            "(schema.org) pour être correctement indexés par Google, Bing et les "
            "agendas culturels. Sitemap auto-généré, métadonnées propres."
        ),
        "tagline": _("Vos événements trouvés par Google et les agendas."),
        "lead": _(
            "Chaque page de lieu et chaque événement TiBillet est structuré en JSON-LD "
            "(schema.org) pour être correctement compris par Google, Bing et les "
            "agendas culturels. Sitemap généré automatiquement, métadonnées propres, "
            "données ouvertes : votre programmation est trouvée par le public qui la "
            "cherche, sans budget publicitaire."
        ),
        "page_title": _("Référencement et SEO des événements — TiBillet"),
        "meta_description": _(
            "Référencement intégré : événements en JSON-LD schema.org, sitemap "
            "auto-généré, métadonnées propres. Votre programmation trouvée par Google."
        ),
        "doc_url": DOC_BASE + "guide-des-lieux/guide-de-reference-technique/billetterie-agenda-lespass/connecter-et-synchroniser-vos-outils/integration/",
        "sections": [
            {
                "heading": _("Structuré pour les moteurs"),
                "text": _(
                    "Vos événements sortent en JSON-LD schema.org : date, lieu, prix, "
                    "billetterie. Google les comprend et peut les afficher en "
                    "résultats enrichis, pas seulement en lien bleu."
                ),
                "capture_alt": _(
                    "Événement TiBillet affiché en résultat enrichi dans une page de "
                    "résultats Google."
                ),
            },
            {
                "heading": _("Trouvable, par conception"),
                "text": _(
                    "Sitemap auto-généré, balises title et description propres, URLs "
                    "lisibles, fil d'Ariane : les fondamentaux du référencement sont "
                    "là dès le départ, sans plugin ni réglage."
                ),
                "capture_alt": _(
                    "Sitemap XML listant les pages d'un lieu et de ses événements."
                ),
            },
            {
                "heading": _("Une visibilité qui ne s'achète pas"),
                "text": _(
                    "Pas de budget publicitaire à entretenir : votre visibilité vient "
                    "de la qualité technique des pages et du réseau de liens entre "
                    "lieux fédérés. Le référencement comme un commun, partagé."
                ),
                "capture_alt": _(
                    "Réseau de liens entre lieux fédérés renforçant leur référencement "
                    "mutuel."
                ),
            },
        ],
    },
}
