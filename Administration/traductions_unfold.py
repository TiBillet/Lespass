"""
Chaines de texte de l'admin Unfold, a traduire dans notre propre .po.
/ Unfold admin strings, declared so they get translated in our own .po.

LOCALISATION : Administration/traductions_unfold.py

POURQUOI CE FICHIER EXISTE :
Le paquet django-unfold n'a aucune traduction francaise.
Ses textes s'affichent donc en anglais dans l'admin.
Notre dossier locale/ est prioritaire (LOCALE_PATHS dans TiBillet/settings.py).
On peut donc traduire ces textes dans locale/fr/LC_MESSAGES/django.po.

Mais makemessages ne lit que le code du projet, jamais site-packages.
Ce fichier recopie les textes d'Unfold pour que makemessages les trouve.
Sans lui, les traductions ajoutees a la main passent en obsolete (#~).

CE FICHIER N'EST IMPORTE NULLE PART. Il ne sert qu'a makemessages.

CONTRAINTES :
- Chaque texte doit etre IDENTIQUE au texte d'Unfold (espaces, ponctuation).
  Un seul caractere different, et la traduction ne s'applique plus.
- On ne liste que les textes qu'aucun catalogue installe ne traduit deja
  (l'admin Django traduit deja "Add", "Delete", "History", etc.).
- On ne liste que les contribs Unfold presents dans INSTALLED_APPS.
  Si un contrib est ajoute (guardian, simple_history...), ajouter ses textes ici.
- Apres une mise a jour d'Unfold, verifier que les textes existent toujours
  dans site-packages/unfold (ripgrep sur chaque texte).

Version d'Unfold de reference : django-unfold 0.89.0
"""

from django.utils.translation import gettext_noop, ngettext_lazy


# Barre de recherche, palette de commandes et liste des applications
# / Search bar, command palette and app list
TEXTES_RECHERCHE_ET_NAVIGATION = [
    gettext_noop("Search apps and models..."),
    gettext_noop("Type to search"),
    gettext_noop("Recent searches"),
    gettext_noop("No recent searches"),
    gettext_noop("No results matching your query"),
    gettext_noop("Loading more results..."),
    gettext_noop("All applications"),
    gettext_noop("Return to site"),
]

# Liste des objets (changelist) : filtres, actions, resultats vides
# / Object list (changelist): filters, actions, empty results
TEXTES_LISTE_DES_OBJETS = [
    gettext_noop("Apply Filters"),
    gettext_noop("Hide counts"),
    gettext_noop("Show counts"),
    gettext_noop("Reset filters"),
    gettext_noop("No results found"),
    gettext_noop(
        "This page yielded into no results. Create a new item or reset your filters."
    ),
    gettext_noop("Select all rows"),
    gettext_noop("Select all objects on this page for an action"),
    gettext_noop("Select record"),
    gettext_noop("Select action"),
    gettext_noop("Select action to run"),
    gettext_noop("Run"),
    gettext_noop("More actions"),
    gettext_noop("Expand row"),
]

# Filtres avances (unfold.contrib.filters)
# / Advanced filters (unfold.contrib.filters)
TEXTES_FILTRES = [
    gettext_noop("From"),
    gettext_noop("To"),
    gettext_noop("Date from"),
    gettext_noop("Date to"),
    gettext_noop("Not enough data."),
]

# Formulaires, champs et widgets
# / Forms, fields and widgets
TEXTES_FORMULAIRES = [
    gettext_noop("Select value"),
    gettext_noop("Select currency"),
    gettext_noop("Choose file to upload"),
    gettext_noop("Click to download"),
    gettext_noop("Image preview"),
    gettext_noop("Record picture"),
    gettext_noop("Toggle password visibility"),
    gettext_noop("True"),
    gettext_noop("False"),
    gettext_noop("Add new item"),
    gettext_noop("This item will be deleted."),
    gettext_noop("Click to cancel"),
    gettext_noop("You can not create nested object without parent"),
    gettext_noop("Dataset not found. No action performed."),
]

# Editeur de texte riche (unfold.contrib.forms, barre d'outils WYSIWYG)
# / Rich text editor toolbar (unfold.contrib.forms)
TEXTES_EDITEUR_DE_TEXTE = [
    gettext_noop("Paragraph"),
    gettext_noop("Underlined"),
    gettext_noop("Bold"),
    gettext_noop("Italic"),
    gettext_noop("Strike"),
    gettext_noop("Link"),
    gettext_noop("Unlink"),
    gettext_noop("Enter an URL"),
    gettext_noop("Heading"),
    gettext_noop("Quote"),
    gettext_noop("Unordered list"),
    gettext_noop("Ordered list"),
    gettext_noop("Indent increase"),
    gettext_noop("Indent decrease"),
    gettext_noop("Undo"),
    gettext_noop("Redo"),
]

# Comptes utilisateurs, connexion et theme
# / User accounts, login and theme
TEXTES_COMPTES_ET_THEME = [
    gettext_noop(
        "After you've created a user, you’ll be able to edit more user options."
    ),
    gettext_noop(
        "Raw passwords are not stored, so there is no way to see this "
        "user’s password, but you can change the password using "
        '<a href="{}" class="text-primary-600 dark:text-primary-500">this form</a>.'
    ),
    gettext_noop("You have been successfully logged out from the administration"),
    gettext_noop("Light"),
    gettext_noop("Dark"),
    gettext_noop("System"),
]

# Export (unfold.contrib.import_export)
# / Export (unfold.contrib.import_export)
TEXTES_EXPORT = [
    gettext_noop("This exporter will export the following fields"),
]

# Textes au pluriel, issus de {% blocktranslate count %} sans "trimmed".
# Les sauts de ligne et les espaces font partie du texte : NE PAS les retoucher.
# Ils doivent rester identiques a l'indentation des gabarits Unfold.
# / Plural strings from untrimmed blocktranslate: whitespace is part of the msgid.
TEXTES_AU_PLURIEL = [
    # unfold/templates/unfold/helpers/command_results.html
    ngettext_lazy(
        "\n                Found %(counter)s result in %(time)s seconds\n            ",
        "\n                Found %(counter)s results in %(time)s seconds\n            ",
    ),
    # unfold/contrib/import_export/templates/admin/import_export/export.html
    ngettext_lazy(
        "\n                    Export %(len)s selected item.\n                ",
        "\n                    Export %(len)s selected items.\n                ",
    ),
]
