from django.utils.translation import gettext_lazy as _


# Pour modifier le texte et l'url de l'affichage d'aide sur une page :
# il faut trouver la 'clé' ('ADHESION_PRODUIT' est une clé par exemple) qui correspond à la page recherchée
# et modifier son 'help_text' et 'help_url'.

DEFAULT_URL_TEXTE = _("Documentation complète")

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
    }
}