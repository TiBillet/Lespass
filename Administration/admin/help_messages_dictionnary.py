from django.utils.translation import gettext_lazy as _


# Pour modifier le texte et l'url de l'affichage d'aide sur une page :
# il faut trouver la 'clé' ('ADHESION_PRODUIT' est une clé par exemple) qui correspond à la page recherchée
# et modifier son 'help_text' et 'help_url'.

DEFAULT_URL_TEXTE = _("Documentation complète")

# Liens de la documentation de l'API v2, montres sur l'admin des cles API.
# Ce sont les fichiers du depot public, sur la branche deployee (main).
# Le .yaml BRUT (raw) se donne tel quel a un agent : c'est le contrat de l'API.
# Le skill tibillet-api est le guide pour agent : recettes curl et pieges.
# / API v2 documentation links shown on the API key admin: files of the public
# repository, on the deployed branch (main).
LIENS_DOCUMENTATION_API_V2 = [
    {
        "texte": _("Contrat de l'API v2 (fichier OpenAPI .yaml, version brute à donner à un agent)"),
        "url": "https://raw.githubusercontent.com/TiBillet/Lespass/main/api_v2/openapi-schema.yaml",
    },
    {
        "texte": _("Guide pour agent : skill tibillet-api (recettes, pièges)"),
        "url": "https://github.com/TiBillet/Lespass/tree/main/TECH_DOC/SKILLS/tibillet-api",
    },
]

TEXTE_AIDE_CLE_API = _(
    "Une clé API donne accès à l'API v2 de ce lieu : https://<votre-domaine>/api/v2/, "
    "avec l'en-tête « Authorization: Api-Key <clé> ». Cochez seulement les droits utiles. "
    "La clé n'est affichée qu'une fois, à la création : copiez-la tout de suite. "
    "Pour confier un travail à un agent (script ou IA), donnez-lui la clé, le contrat "
    "de l'API (.yaml) et le skill tibillet-api ci-dessous."
)

HELP_MESSAGES_DICT = {
    "ADHESION_PRODUIT":{
        "list_help_text":_("Sur cette page vous pouvez consulter la liste de vos produits d'adhésion, les créer et les éditer"),
        "list_help_url":[
            {
                "texte":DEFAULT_URL_TEXTE,
                "url":"https://tibillet.github.io/documentation_v3/guide-des-lieux/billetterie-agenda-lespass/creer-des-adhesions-et-leurs-tarifs/creer-un-produit-adhesion/"
            }
        ],
        "changeform_help_text" : _("Sur cette page vous pouvez créer un produit d'adhésion. Attention pour ajouter un prix il faut vous ajouter un compte stripe"),
        "changeform_help_url" : [
            {
                "texte":"Créer un produit adhésion",
                "url":"https://tibillet.github.io/documentation_v3/guide-des-lieux/billetterie-agenda-lespass/creer-des-adhesions-et-leurs-tarifs/creer-un-produit-adhesion/"
            },
            {
                "texte":"Créer son compte stripe",
                "url":"https://tibillet.github.io/documentation_v3/guide-des-lieux/billetterie-agenda-lespass/gerer-ses-ventes-avec-stripe/creer-un-compte-stripe/"
            }
        ]
    },
    "ADHESION":{
        "list_help_text":_("Sur cette page vous pouvez consulter la liste de vos adhésion et en créer manuellement au besoin."),
        "list_help_url":[
            {
                "texte": DEFAULT_URL_TEXTE,
                "url":"https://tibillet.github.io/documentation_v3/guide-des-lieux/billetterie-agenda-lespass/creer-des-adhesions-et-leurs-tarifs/creer-une-adhesion-sur-place/"
            }
        ],
        "changeform_help_text":_("Sur cette page vous pouvez créer manuellement des adhésion."),
        "changeform_help_url":[
            {
                "texte": DEFAULT_URL_TEXTE,
                "url":"https://tibillet.github.io/documentation_v3/guide-des-lieux/billetterie-agenda-lespass/creer-des-adhesions-et-leurs-tarifs/creer-une-adhesion-sur-place/"
            }
        ]
    },
    "CLE_API": {
        "list_help_text": TEXTE_AIDE_CLE_API,
        "list_help_url": LIENS_DOCUMENTATION_API_V2,
        "changeform_help_text": TEXTE_AIDE_CLE_API,
        "changeform_help_url": LIENS_DOCUMENTATION_API_V2,
    },
}