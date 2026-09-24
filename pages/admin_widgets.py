"""
Widget et champ de formulaire « editeur de lignes » pour l'admin des blocs.
/ "Line editor" widget and form field for the blocks admin.

LOCALISATION : pages/admin_widgets.py

Remplacent la saisie de JSON brut pour `Bloc.contenu` et `Bloc.points_gps`.
Chaque element de la liste devient une ligne de champs, avec des boutons
Ajouter / Monter / Descendre / Supprimer.

FLUX :
1. BlocAdminForm (pages/admin.py) declare un LignesField par editeur
   ("lieu", "cartes", "gps"), comme il le fait deja pour texte_markdown.
2. Le widget rend admin/pages/widgets/editeur_lignes.html, qui inclut une
   ligne par element (gabarit tire de GABARIT_LIGNE_PAR_EDITEUR : ligne_lieu,
   ligne_cartes ou ligne_gps).
3. « + Ajouter » demande une ligne vide au serveur (HTMX, vue
   pages/admin_apercu.py:vue_ligne_vide).
4. A l'envoi, value_from_datadict relit les lignes (editeur_items.py) et
   LignesField.clean les nettoie. BlocAdmin.save_model recopie le resultat
   dans le champ modele selon le type du bloc.
/ Replace raw JSON input. Each list element becomes a line of inputs with
Add / Up / Down / Remove buttons.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from unfold.widgets import BASE_INPUT_CLASSES, SELECT_CLASSES

from pages.blocs_catalogue import CLES_ELEMENT_PAR_AFFICHAGE
from pages.editeur_items import (
    CLES_PAR_EDITEUR,
    NETTOYEUR_PAR_EDITEUR,
    TYPES_ITEM_LIEU,
    lignes_pour_affichage,
    lire_lignes_depuis_post,
)

# Gabarit d'UNE ligne, pour chaque editeur. Ecrit en toutes lettres (et non
# fabrique avec f"ligne_{editeur}.html") pour qu'une recherche du nom de
# fichier mene ici. Deux utilisateurs :
# - EditeurLignesWidget.render (lignes existantes, via editeur_lignes.html) ;
# - pages/admin_apercu.py:vue_ligne_vide (bouton « + Ajouter »).
# / Template of ONE line per editor, spelled out so a file-name search leads
# here. Used by the widget and by the "+ Add" view.
GABARIT_LIGNE_PAR_EDITEUR = {
    "lieu": "admin/pages/widgets/ligne_lieu.html",
    "cartes": "admin/pages/widgets/ligne_cartes.html",
    "gps": "admin/pages/widgets/ligne_gps.html",
}

# Classes des champs : celles d'Unfold, donc presentes dans son CSS.
# / Input classes: Unfold's own, hence present in its CSS bundle.
CLASSES_CHAMP_TEXTE = " ".join(BASE_INPUT_CLASSES)
CLASSES_CHAMP_SELECT = " ".join(SELECT_CLASSES)


def _expressions_des_cles_de_cartes():
    """
    Pour chaque cle d'une sous-carte (titre, texte, badge, url) : l'expression
    Alpine qui ne la montre que pour les affichages dont le gabarit la rend.
    Lu dans CLES_ELEMENT_PAR_AFFICHAGE (pages/blocs_catalogue.py).
    Ex. : badge -> "['MEDIA_ET_CARTES','EQUIPE','RESSOURCES'].includes(affichage)".
    / For each sub-card key: the Alpine expression showing it only for the
    affichages whose template renders it.
    """
    expressions = {}
    for cle in CLES_PAR_EDITEUR["cartes"]:
        affichages_qui_la_rendent = []
        for affichage, cles_rendues in CLES_ELEMENT_PAR_AFFICHAGE.items():
            if cle in cles_rendues:
                affichages_qui_la_rendent.append(affichage)
        liste = ",".join(f"'{affichage}'" for affichage in affichages_qui_la_rendent)
        expressions[cle] = f"typeof affichage !== 'undefined' && [{liste}].includes(affichage)"
    return expressions


# Calcule une fois au chargement : le catalogue ne change pas en cours de route.
# / Computed once at load time: the catalogue does not change at runtime.
EXPRESSIONS_DES_CLES_DE_CARTES = _expressions_des_cles_de_cartes()


def contexte_d_une_ligne(nom_du_champ, editeur, ligne):
    """
    Contexte commun a une ligne, qu'elle soit rendue par le widget ou par la
    vue « ligne vide ».
    / Shared context of one line, rendered by the widget or the empty-line view.
    """
    return {
        "nom": nom_du_champ,
        "editeur": editeur,
        "ligne": ligne,
        "types_item_lieu": TYPES_ITEM_LIEU,
        "classes_champ": CLASSES_CHAMP_TEXTE,
        "classes_select": CLASSES_CHAMP_SELECT,
        "expressions_cles": EXPRESSIONS_DES_CLES_DE_CARTES,
    }


def ligne_vide(editeur):
    """
    Une ligne aux valeurs vides pour cet editeur. Une info pratique de LIEU
    commence en « Paragraphe ».
    / An empty line for this editor. A LIEU item starts as "Paragraph".
    """
    ligne = {}
    for cle in CLES_PAR_EDITEUR[editeur]:
        ligne[cle] = ""
    if editeur == "lieu":
        ligne["type"] = "para"
    return ligne


class EditeurLignesWidget(forms.Widget):
    """
    Affiche une liste d'elements sous forme de lignes de champs.
    / Displays a list of items as lines of inputs.

    :param editeur: "lieu", "cartes" ou "gps" (voir CLES_PAR_EDITEUR).
    """

    def __init__(self, editeur, attrs=None):
        super().__init__(attrs)
        self.editeur = editeur

    def value_from_datadict(self, data, files, name):
        # Les lignes brutes, dans l'ordre du formulaire (pas encore nettoyees).
        # / Raw lines, in form order (not cleaned yet).
        return lire_lignes_depuis_post(data, name, CLES_PAR_EDITEUR[self.editeur])

    def value_omitted_from_data(self, data, files, name):
        # Une liste vide est une vraie valeur (tout a ete supprime).
        # / An empty list is a real value (everything was removed).
        return False

    def render(self, name, value, attrs=None, renderer=None):
        # `value` est soit la valeur en base (liste JSON), soit les lignes
        # renvoyees apres une erreur de validation : dans les deux cas une
        # liste de dicts, que lignes_pour_affichage met au format des champs.
        # / `value` is either the stored JSON list or the lines sent back after
        # a validation error: both are lists of dicts.
        lignes, avertissements = lignes_pour_affichage(value, self.editeur)

        lignes_avec_contexte = []
        for ligne in lignes:
            lignes_avec_contexte.append(contexte_d_une_ligne(name, self.editeur, ligne))

        contexte = {
            "nom": name,
            "editeur": self.editeur,
            "lignes": lignes_avec_contexte,
            "avertissements": avertissements,
            "gabarit_ligne": GABARIT_LIGNE_PAR_EDITEUR[self.editeur],
        }
        return render_to_string("admin/pages/widgets/editeur_lignes.html", contexte)


class LignesField(forms.Field):
    """
    Champ de formulaire qui nettoie les lignes d'un editeur.
    / Form field cleaning an editor's lines.

    La valeur nettoyee est une liste prete a etre stockee dans le JSONField.
    Les erreurs (latitude invalide, type inconnu...) remontent a cote du champ.
    / The cleaned value is a list ready for the JSONField. Errors show next to
    the field.
    """

    def __init__(self, editeur, **kwargs):
        self.editeur = editeur
        kwargs.setdefault("required", False)
        kwargs.setdefault("widget", EditeurLignesWidget(editeur))
        super().__init__(**kwargs)

    def clean(self, value):
        nettoyeur = NETTOYEUR_PAR_EDITEUR[self.editeur]
        if value in (None, ""):
            value = []
        items_propres, erreurs = nettoyeur(value)
        if erreurs:
            raise ValidationError(erreurs)
        return items_propres
