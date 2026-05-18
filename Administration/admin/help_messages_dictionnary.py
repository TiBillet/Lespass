from django.utils.translation import gettext_lazy as _


# Pour modifier le texte et l'url de l'affichage d'aide sur une page :
# il faut trouver la 'clé' ('ADHESION_PRODUIT' est une clé par exemple) qui correspond à la page recherchée
# et modifier son 'help_text' et 'help_url'.

HELP_MESSAGES_DICT = {
    "ADHESION_PRODUIT":{
        "help_text":_("On this page you can consult the list of your adhesion products, create and edit them."),
        "help_url":_("https://tibillet.github.io/documentation_v3/guide-des-lieux/billetterie-agenda-lespass/creer-des-adhesions-et-leurs-tarifs/creer-un-produit-adhesion/")
    },
    "ADHESION":{
        "help_text":_("On this page you can consult the list of your adhesion and create those manually if needed."),
        "help_url":_("https://tibillet.github.io/documentation_v3/guide-des-lieux/billetterie-agenda-lespass/creer-des-adhesions-et-leurs-tarifs/creer-une-adhesion-sur-place/")
    }
}