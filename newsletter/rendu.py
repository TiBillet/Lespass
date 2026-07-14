"""
Fabrique le HTML de la newsletter a partir des fiches d'evenements.
/ Build the newsletter HTML from event fiches.

LOCALISATION : newsletter/rendu.py

Ce module ne touche NI la base NI Ghost. Il transforme des dicts en HTML.
/ This module touches NEITHER the database NOR Ghost.

POURQUOI PAS DE STYLE INLINE :
L'apparence de la newsletter (couleurs, polices, forme des boutons, en-tete, pied de
page) est pilotee par les REGLAGES DE DESIGN NEWSLETTER de l'instance Ghost. On emet
du HTML SEMANTIQUE aux conventions kg-*, que Ghost reconvertit en cartes natives.
Verifie en reel sur une instance Ghost 6.52.
Voir TECH_DOC/SESSIONS/NEWSLETTER/SPEC.md §4.
/ Styling is Ghost's job, via its newsletter design settings.
"""

from django.template.loader import render_to_string
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from newsletter.collecte import HAUTEUR_IMAGE_POUR_EMAIL, LARGEUR_IMAGE_POUR_EMAIL

GABARIT_DE_LA_NEWSLETTER = "newsletter/email_evenements.html"


def titre_de_la_newsletter(date_debut, date_fin):
    """
    Compose le titre du brouillon. / Compose the draft's title.

    LOCALISATION : newsletter/rendu.py

    C'est un BROUILLON : le gestionnaire le reecrira s'il veut.
    / It's a DRAFT: the manager will rewrite it if they want to.

    :param date_debut: datetime du debut de la fenetre
    :param date_fin: datetime de la fin de la fenetre
    :return: le titre (str)
    """
    return _("Agenda du %(debut)s au %(fin)s") % {
        "debut": date_format(date_debut, "DATE_FORMAT"),
        "fin": date_format(date_fin, "DATE_FORMAT"),
    }


def rendre_newsletter_html(fiches, date_debut, date_fin):
    """
    Rend le corps HTML de la newsletter. / Render the newsletter's HTML body.

    LOCALISATION : newsletter/rendu.py

    Chaque evenement devient une CARTE PRODUCT de Ghost (image + titre + infos + bouton),
    suivie de sa description longue en paragraphes normaux. Les evenements sont separes
    par un <hr>, que Ghost transforme en carte divider.
    / Each event becomes a Ghost PRODUCT CARD, followed by its long description.

    :param fiches: la liste des fiches (cf. newsletter.collecte)
    :param date_debut: datetime du debut de la fenetre
    :param date_fin: datetime de la fin de la fenetre
    :return: le HTML (str), sans aucun attribut style=
    """
    contexte = {
        "fiches": fiches,
        "date_debut_affichee": date_format(date_debut, "DATE_FORMAT"),
        "date_fin_affichee": date_format(date_fin, "DATE_FORMAT"),
        # Ghost lit width/height sur l'image de la carte pour eviter le "layout shift".
        # / Ghost reads width/height on the card image to avoid layout shift.
        "largeur_image": LARGEUR_IMAGE_POUR_EMAIL,
        "hauteur_image": HAUTEUR_IMAGE_POUR_EMAIL,
    }

    return render_to_string(GABARIT_DE_LA_NEWSLETTER, contexte)
