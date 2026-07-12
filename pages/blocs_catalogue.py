"""
Source UNIQUE du catalogue des champs par type de bloc.
/ SINGLE source of the per-type block field catalogue.

LOCALISATION : pages/blocs_catalogue.py

Utilise par : l'API v2 (validation + endpoint block-types/) et, a terme,
l'admin (conditional_fields derive). Derive de la matrice SPEC.md.
/ Used by: API v2 (validation + block-types endpoint) and, later, the admin.
"""

# Pour chaque type de bloc : la liste des champs modele qu'il utilise.
# / For each block type: the list of model fields it uses.
CHAMPS_PAR_TYPE = {
    # HERO = banniere d'identite pure : titre + sous-titre.
    # L'image de fond est l'image generique du lieu (Configuration.img), lue au
    # rendu -> pas de champ image sur le bloc. Les actions vont dans un bloc CTA.
    # / HERO = pure identity banner: title + subtitle. The background image is the
    # venue's generic image (Configuration.img), read at render time -> no image
    # field on the block. Actions go into a separate CTA block.
    "HERO": ["titre", "sous_titre"],
    "PARAGRAPHE": ["titre", "texte"],
    "IMAGE_TEXTE": ["titre", "texte", "image", "image_position",
                    "bouton_label", "bouton_url"],
    "CTA": ["titre", "sous_titre", "texte",
            "bouton_label", "bouton_url", "bouton2_label", "bouton2_url"],
    "TEMOIGNAGE": ["texte", "auteur_nom", "auteur_role", "auteur_photo"],
    # VIDEO_TEXTE : via l'API, seuls titre + texte sont settables. Le fichier video n'est
    # PAS expose par l'API (pour une video, utiliser le bloc EMBED). Le champ modele `video`
    # reste editable dans l'admin. / Via the API only titre + texte are settable; the video
    # file is NOT exposed by the API (use EMBED for videos). The model field stays admin-editable.
    "VIDEO_TEXTE": ["titre", "texte"],
    "CARTE": ["surtitre", "titre", "badge", "texte", "image",
              "bouton_label", "bouton_url"],
    "IMAGE": ["titre", "image", "affichage_image"],
    "CARTE_LEAFLET": ["titre", "badge", "image", "image_secondaire", "points_gps"],
    "INFOS": ["contenu"],
    "FAQ": ["titre", "texte", "repliable"],
    "EVENEMENTS": ["titre", "nombre_max"],
    "GALERIE": ["titre"],  # les images sont portees par ImageGalerie (cf. Session B)
    "EMBED": ["titre", "embed_url"],
    # MARKDOWN : texte long (article/blog). La source Markdown vit dans `texte`,
    # le rendu HTML est fait au gabarit (filtre rendre_markdown + sanitize nh3).
    # / MARKDOWN: long-form text (article/blog). The Markdown source lives in
    # `texte`; HTML rendering happens in the template (rendre_markdown + nh3).
    "MARKDOWN": ["titre", "texte"],
    # LISTE_SOUS_PAGES : index des sous-pages publiees de la page courante,
    # en cartes (parent = index de blog, enfants = articles). `nombre_max`
    # limite la liste (defaut 6, comme EVENEMENTS).
    # / LISTE_SOUS_PAGES: cards index of the current page's published
    # sub-pages (parent = blog index, children = articles).
    "LISTE_SOUS_PAGES": ["titre", "nombre_max"],
    # IFRAME : contenu integre libre (formulaire, widget) a hauteur fixe. `embed_url`
    # = URL a integrer (rendue seulement si l'hote est autorise cote ROOT), `hauteur_px`
    # = hauteur du cadre. / IFRAME: free embedded content at a fixed height.
    "IFRAME": ["titre", "embed_url", "hauteur_px"],
    # PARTENAIRES : bande de logos. Comme GALERIE, les images sont portees par
    # ImageGalerie (chaque logo a une image + une legende + un lien_url optionnel).
    # / PARTENAIRES: logo strip. Like GALLERY, images are carried by ImageGalerie
    # (each logo has an image + caption + optional lien_url).
    "PARTENAIRES": ["titre"],
    # NEWSLETTER : formulaire d'inscription Ghost. `embed_url` = instance Ghost
    # (data-site), `titre`/`sous_titre` = data-title/description du formulaire.
    # / NEWSLETTER: Ghost signup form. embed_url = Ghost instance (data-site).
    "NEWSLETTER": ["titre", "sous_titre", "embed_url"],
}

# Types dont les images sont portees par ImageGalerie (relation multi-images).
# / Types whose images are carried by ImageGalerie (multi-image relation).
TYPES_AVEC_GALERIE = frozenset({"GALERIE", "PARTENAIRES"})

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
