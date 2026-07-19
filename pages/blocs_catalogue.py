"""
Source UNIQUE du catalogue des blocs : champs et affichages par type.
/ SINGLE source of the block catalogue: fields and displays per type.

LOCALISATION : pages/blocs_catalogue.py

Utilise par : `Bloc.clean()` (validation type x affichage), l'API v2 (validation
+ endpoint block-types/) et l'admin (conditional_fields).
/ Used by: `Bloc.clean()` (type x affichage validation), the v2 API (validation +
block-types endpoint) and the admin (conditional_fields).

LE CATALOGUE EST ORGANISE PAR INTENTION, PAS PAR RENDU.
Sept types repondent chacun a une phrase que se dit la personne qui construit
la page : « j'ecris du texte », « je mets quelque chose en avant », « je montre
des images », « j'integre un truc externe », « je montre ou c'est », « je reponds
a des questions », « je liste des choses automatiquement ».

La variation VISUELLE a l'interieur d'un type est portee par le champ
`affichage` (cf. AFFICHAGES_PAR_TYPE). Regle non negociable : **jamais un
nouveau TYPE pour une variation purement visuelle**. Un type repond a une
question (« qu'est-ce que je veux dire ? »), un affichage a une autre
(« sous quelle forme ? ») — les melanger fait exploser le catalogue.
/ THE CATALOGUE IS ORGANISED BY INTENT, NOT BY RENDERING. The visual variation
inside a type is carried by `affichage`. Never add a TYPE for a visual
variation: a type answers "what am I saying?", an affichage "in what shape?".
"""

# Pour chaque type de bloc : la liste des champs modele qu'il utilise.
# Les types a plusieurs rendus declarent `affichage` en tete : c'est un
# champ comme un autre pour l'API, dont la valeur est ensuite validee
# contre AFFICHAGES_PAR_TYPE.
# / For each block type: the list of model fields it uses. Multi-rendering
# types declare `affichage` first: an ordinary field for the API, whose
# value is then validated against AFFICHAGES_PAR_TYPE.
CHAMPS_PAR_TYPE = {
    # TEXTE = le bloc de contenu par defaut. Le champ `texte` contient du
    # **Markdown**, et rien d'autre. Un seul format de stockage veut dire un
    # seul pipeline de securite : pas de clean_html a l'enregistrement, un
    # sanitize nh3 au rendu. Ne jamais y stocker de HTML deja nettoye : le
    # pipeline dependrait alors de ce qu'on a mis dans le champ.
    # / TEXTE = the default content block. `texte` holds **Markdown**, nothing
    # else: one storage format means one security pipeline (no clean_html on
    # save, nh3 sanitize at render). Never store pre-sanitised HTML here.
    "TEXTE": ["titre", "texte"],

    # SECTION = « je mets quelque chose en avant ». Un titre, un texte, un
    # media, des boutons ; l'affichage decide de la forme (banniere, carte,
    # appel a l'action, citation, texte a cote d'une image ou d'une video).
    # / SECTION = "I highlight something". Title, text, media, buttons; the
    # affichage decides the shape.
    "SECTION": [
        "affichage",
        "titre", "sous_titre", "badge", "texte", "image", "video",
        "bouton_label", "bouton_url", "bouton2_label", "bouton2_url",
        "auteur_nom", "auteur_role", "auteur_photo",
        # `contenu` ne sert qu'a l'affichage MEDIA_ET_CARTES : il porte les
        # sous-cartes de la section, en DONNEES TEXTE. Une sous-carte n'est pas
        # un bloc : elle vit a l'interieur de la colonne de sa section, la ou
        # une liste de blocs ne saurait la placer.
        # / `contenu` only serves the MEDIA_ET_CARTES display: it carries the
        # section's sub-cards as TEXT DATA. A sub-card is not a block: it lives
        # inside its section's column, where a flat block list cannot put it.
        "contenu",
    ],

    # IMAGES : c'est l'AFFICHAGE qui dit ou vivent les fichiers.
    # Choix explicite, jamais devine a partir du contenu du bloc.
    #   - PLEINE_LARGEUR / VIGNETTE_TITRE : une seule image -> champ `image`,
    #     qui porte les grandes variations (jusqu'a 1920 px).
    #   - GRILLE / BANDE_LOGOS : plusieurs images -> relation ImageGalerie,
    #     dont les variations plafonnent a 480 px (suffisant pour des
    #     vignettes et des logos).
    # Tout faire passer par ImageGalerie obligerait a regenerer toutes ses
    # variations pour afficher une photo en pleine largeur sans la degrader.
    # / The AFFICHAGE says where the files live: single image -> `image` field
    # (large variations); several -> ImageGalerie (480 px max, fine for
    # thumbnails and logos).
    "IMAGES": ["affichage", "titre", "image"],

    # INTEGRATION : contenu venu d'AILLEURS, donc toujours une URL. Les trois
    # affichages ne sont pas cosmetiques : ils choisissent trois PIPELINES DE
    # SECURITE distincts (whitelist video codee / whitelist ROOT + sandbox /
    # script Ghost). Le pipeline se lit dans `affichage`, jamais dans l'URL.
    # / INTEGRATION: content from ELSEWHERE, always a URL. The three affichages
    # pick three distinct SECURITY PIPELINES — read from `affichage`, never
    # inferred from the URL.
    "INTEGRATION": ["affichage", "titre", "sous_titre", "embed_url", "hauteur_px"],

    # LIEU : la carte des points GPS ET les infos pratiques a cote, dans UN
    # SEUL bloc. Les deux moities forment un ensemble a l'ecran : les separer
    # en deux blocs obligerait a les maintenir voisins pour que la mise en page
    # tienne.
    # / LIEU: the GPS map AND the practical info beside it, in ONE block. Both
    # halves read as a single unit on screen.
    "LIEU": ["titre", "badge", "image", "image_secondaire", "points_gps", "contenu"],

    "FAQ": ["titre", "texte"],

    # LISTE : `source` choisit une REQUETE (pas un rendu, donc ce n'est pas un
    # affichage). `page_source` n'apparait PAS ici : c'est une cle etrangere,
    # elle demande un traitement dedie dans l'API (cf. CHAMPS_RELATION).
    # / LISTE: `source` picks a QUERY (not a rendering, hence not an affichage).
    # `page_source` is NOT listed here: it is a foreign key needing dedicated
    # API handling (see CHAMPS_RELATION).
    "LISTE": ["titre", "source", "nombre_max"],
}

# Pour chaque type : les affichages autorises. Un type absent ou a tuple vide
# n'a qu'un seul rendu et laisse `affichage` vide.
# Django ne sait pas conditionner des choices par la valeur d'un autre champ :
# le modele porte l'UNION des valeurs, et c'est `Bloc.clean()` qui refuse un
# affichage etranger au type. Sans lui, un SECTION accepterait BANDE_LOGOS et
# le rendu chercherait un gabarit qui n'existe pas.
# / For each type: the allowed affichages. A missing or empty entry means the
# type has a single rendering. Django cannot condition choices on another
# field, so `Bloc.clean()` enforces this table.
AFFICHAGES_PAR_TYPE = {
    "TEXTE": (),
    "SECTION": (
        "BANNIERE",
        "TEXTE_IMAGE_GAUCHE",
        "TEXTE_IMAGE_DROITE",
        "TEXTE_VIDEO",
        "MEDIA_ET_CARTES",
        "CARTE",
        "APPEL_ACTION",
        "CITATION",
    ),
    "IMAGES": ("PLEINE_LARGEUR", "VIGNETTE_TITRE", "GRILLE", "BANDE_LOGOS"),
    "INTEGRATION": ("VIDEO", "WIDGET", "NEWSLETTER"),
    "LIEU": (),
    "FAQ": (),
    "LISTE": (),
}

# Pour un couple (type, affichage) : les champs que son gabarit rend REELLEMENT.
# CHAMPS_PAR_TYPE donne l'UNION des champs d'un type — necessaire a l'API, qui
# valide au niveau du type. Cette table-ci resserre au niveau de l'affichage,
# pour que le formulaire de l'admin ne propose pas de remplir un champ que le
# rendu ignorera : une image posee sur une CITATION, ou deux boutons sur une
# BANNIERE, disparaissent en silence — l'utilisateur ne comprend pas pourquoi.
# Un affichage absent de cette table affiche tous les champs de son type.
# / For a (type, affichage) pair: the fields its template ACTUALLY renders.
# CHAMPS_PAR_TYPE is the UNION of a type's fields — needed by the API, which
# validates at type level. This table narrows it down per affichage, so the
# admin form never offers a field the rendering will ignore: an image set on a
# CITATION, or two buttons on a BANNIERE, vanish silently. An affichage missing
# from this table shows every field of its type.
CHAMPS_PAR_AFFICHAGE = {
    "SECTION": {
        # L'image de fond vient de la Configuration du tenant, pas du bloc.
        # / The background image comes from the tenant Configuration.
        "BANNIERE": ["titre", "sous_titre"],
        "TEXTE_IMAGE_GAUCHE": [
            "titre", "texte", "image", "bouton_label", "bouton_url",
        ],
        "TEXTE_IMAGE_DROITE": [
            "titre", "texte", "image", "bouton_label", "bouton_url",
        ],
        "TEXTE_VIDEO": ["titre", "texte", "video"],
        "MEDIA_ET_CARTES": [
            "titre", "texte", "image", "video", "contenu",
            # Les deux gabarits rendent un bouton sous les sous-cartes.
            # / Both templates render a button below the sub-cards.
            "bouton_label", "bouton_url",
        ],
        "CARTE": [
            "titre", "sous_titre", "badge", "texte", "image",
            "bouton_label", "bouton_url",
        ],
        "APPEL_ACTION": [
            "titre", "sous_titre", "texte",
            "bouton_label", "bouton_url", "bouton2_label", "bouton2_url",
        ],
        "CITATION": ["texte", "auteur_nom", "auteur_role", "auteur_photo"],
    },
    "IMAGES": {
        # Une seule image : le champ `image` du bloc.
        # / A single image: the block's `image` field.
        "PLEINE_LARGEUR": ["titre", "image"],
        "VIGNETTE_TITRE": ["titre", "image"],
        # Plusieurs images : la relation ImageGalerie (l'inline), pas `image`.
        # / Several images: the ImageGalerie relation (the inline), not `image`.
        "GRILLE": ["titre"],
        "BANDE_LOGOS": ["titre"],
    },
    "INTEGRATION": {
        "VIDEO": ["titre", "embed_url"],
        "WIDGET": ["titre", "embed_url", "hauteur_px"],
        "NEWSLETTER": ["titre", "sous_titre", "embed_url"],
    },
}

# Couples (type, affichage) dont les images vivent dans l'inline ImageGalerie.
# Sert a n'afficher cet inline que la ou il sera lu.
# / (type, affichage) pairs whose images live in the ImageGalerie inline. Used
# to show that inline only where it will be read.
AFFICHAGES_AVEC_GALERIE = frozenset({("IMAGES", "GRILLE"), ("IMAGES", "BANDE_LOGOS")})

# Affichage pose d'office quand la personne n'en choisit pas. Un bloc sans
# affichage explicite doit quand meme s'afficher : on prend le plus neutre.
# / Affichage applied when none is chosen: a block must always render.
AFFICHAGE_PAR_DEFAUT = {
    "SECTION": "BANNIERE",
    "IMAGES": "PLEINE_LARGEUR",
    "INTEGRATION": "VIDEO",
}

# Types dont les images sont portees par ImageGalerie (relation multi-images).
# / Types whose images are carried by ImageGalerie (multi-image relation).
TYPES_AVEC_GALERIE = frozenset({"IMAGES"})

# Les codes de type, dans l'ordre du catalogue.
# / The type codes, in catalogue order.
TYPES_BLOC = list(CHAMPS_PAR_TYPE.keys())

# Union de tous les champs : whitelist pour additionalProperty (securite : on ne
# laisse JAMAIS setattr un champ hors de cette liste, ex. page/uuid/position).
# / Union of all fields: whitelist for additionalProperty (never setattr outside).
CHAMPS_BLOC_AUTORISES = frozenset(
    champ for champs in CHAMPS_PAR_TYPE.values() for champ in champs
)

# Champs FICHIER : ne se settent JAMAIS via additionalProperty (string arbitraire =
# corruption). Ils passent par URL (telechargement) ou upload multipart.
# / FILE fields: never set via additionalProperty. They go through URL download or
# multipart upload.
CHAMPS_FICHIER = frozenset({"image", "image_secondaire", "video", "auteur_photo"})

# Champs IMAGE telechargeables par URL distante (pas la video : multipart only).
# / IMAGE fields downloadable from a remote URL (not video: multipart only).
CHAMPS_IMAGE_URL = frozenset({"image", "image_secondaire", "auteur_photo"})

# Champs RELATION (cles etrangeres) : hors de CHAMPS_PAR_TYPE, donc hors de
# CHAMPS_BLOC_AUTORISES. Les y remettre casserait l'API des deux cotes : un
# `setattr(bloc, "page_source", "<uuid en texte>")` leve un ValueError (500 au
# lieu de 400), et un `getattr` renvoie une instance Page non serialisable en
# JSON, ce qui fait planter la lecture de TOUTE page contenant un tel bloc.
# Ces champs demandent une resolution explicite (uuid ou slug -> instance)
# dans les serializers.
# / RELATION fields (foreign keys): kept out of CHAMPS_BLOC_AUTORISES. A raw
# setattr would raise ValueError (500 instead of 400), and getattr would return
# a non-JSON-serialisable Page instance, breaking the read of EVERY page holding
# such a block. They need explicit uuid/slug resolution in the serializers.
CHAMPS_RELATION = frozenset({"page_source"})
