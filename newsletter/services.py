"""
Orchestration : collecte -> rendu -> depot du brouillon dans Ghost.
/ Orchestration: collect -> render -> drop the draft into Ghost.

LOCALISATION : newsletter/services.py

C'est le SEUL point d'entree de l'admin. Les trois modules qu'il assemble
(collecte, rendu, client_ghost) ne se connaissent pas entre eux.
/ This is the admin's ONLY entry point.
"""

import logging
from datetime import timedelta

from cryptography.fernet import InvalidToken
from django.utils import timezone
from django.utils.translation import gettext as _

from BaseBillet.models import GhostConfig
from newsletter.client_ghost import ErreurGhost, creer_brouillon
from newsletter.collecte import collecter_evenements_du_reseau
from newsletter.rendu import rendre_newsletter_html, titre_de_la_newsletter

logger = logging.getLogger(__name__)


class GhostNonConfigure(Exception):
    """Le tenant n'a pas renseigne son instance Ghost. / No Ghost instance configured."""


class AucunEvenement(Exception):
    """Aucun evenement sur la periode : on ne cree pas de brouillon vide."""


def _journaliser(ghost_config, message):
    """
    Ecrit une ligne horodatee dans GhostConfig.ghost_last_log.
    / Write a timestamped line into GhostConfig.ghost_last_log.

    LOCALISATION : newsletter/services.py

    Le champ est ECRASE, pas complete : c'est ce que fait deja le code Ghost existant
    (GhostConfigAdmin.test_api_ghost_admin_button), on reste coherent.
    / The field is OVERWRITTEN, not appended: consistent with the existing Ghost code.
    """
    ghost_config.ghost_last_log = f"{timezone.now()} - {message}"
    ghost_config.save()


def creer_brouillon_newsletter(nombre_de_jours):
    """
    Fabrique un brouillon de newsletter dans l'instance Ghost du tenant courant.
    / Build a newsletter draft in the current tenant's Ghost instance.

    LOCALISATION : newsletter/services.py

    FLUX :
    1. Lire la config Ghost du tenant (GhostConfig, singleton, cle chiffree)
    2. Collecter les evenements du tenant ET de son reseau federe sur la fenetre
    3. S'il n'y en a aucun : lever AucunEvenement, sans rien poster
    4. Rendre le HTML semantique (conventions kg-* de Ghost)
    5. Deposer le BROUILLON et renvoyer son URL d'edition
    6. Journaliser, succes comme echec

    Le post est cree en status="draft". Il n'est JAMAIS publie ni envoye : l'envoi reste
    un geste humain, dans l'interface de Ghost.
    / The post is a DRAFT. Sending stays a human action, inside Ghost.

    :param nombre_de_jours: la largeur de la fenetre (7 ou 30)
    :return: {"url_edition": str, "nombre_evenements": int}
    :raises GhostNonConfigure: ni URL ni cle renseignees
    :raises AucunEvenement: aucun evenement sur la periode
    :raises ErreurGhost: Ghost injoignable, cle refusee, reponse inattendue
    """
    ghost_config = GhostConfig.get_solo()
    url_instance_ghost = ghost_config.ghost_url

    # La cle en base peut etre stockee EN CLAIR : GhostConfigAdmin.save_model n'appelle
    # set_api_key() (qui chiffre) QUE si le test de connexion a Ghost a reussi. Si le
    # gestionnaire a saisi sa cle alors que Ghost etait injoignable, elle est en base non
    # chiffree, et fernet_decrypt leve InvalidToken. Sans ce garde-fou, l'admin ferait un
    # 500 au lieu d'afficher un message.
    # / The stored key may be UNENCRYPTED: the admin only encrypts it when the Ghost
    # connection test succeeds. fernet_decrypt then raises InvalidToken -> 500 in the admin.
    try:
        cle_admin_ghost = ghost_config.get_api_key()
    except InvalidToken:
        raise GhostNonConfigure(
            _(
                "La clé Admin API enregistrée est illisible. Ressaisissez-la et "
                "enregistrez à nouveau, Ghost étant joignable."
            )
        )

    if not url_instance_ghost or not cle_admin_ghost:
        raise GhostNonConfigure(
            _("L'instance Ghost n'est pas configurée (URL ou clé Admin API manquante).")
        )

    date_debut = timezone.now()
    date_fin = timezone.now() + timedelta(days=nombre_de_jours)

    fiches = collecter_evenements_du_reseau(nombre_de_jours)

    # On ne cree JAMAIS un brouillon vide : ce serait du bruit dans le Ghost du
    # gestionnaire. / We NEVER create an empty draft.
    if not fiches:
        message = _("Aucun événement sur les %(jours)s prochains jours.") % {
            "jours": nombre_de_jours
        }
        _journaliser(ghost_config, message)
        raise AucunEvenement(message)

    contenu_html = rendre_newsletter_html(fiches, date_debut, date_fin)
    titre = titre_de_la_newsletter(date_debut, date_fin)

    try:
        url_edition = creer_brouillon(
            url_instance_ghost=url_instance_ghost,
            cle_admin_ghost=cle_admin_ghost,
            titre=titre,
            contenu_html=contenu_html,
        )
    except ErreurGhost as erreur_ghost:
        # On journalise AVANT de re-lever : ghost_last_log est le seul indice que le
        # gestionnaire aura apres coup. / Log BEFORE re-raising.
        _journaliser(
            ghost_config, f"Erreur - {type(erreur_ghost).__name__} : {erreur_ghost}"
        )
        logger.warning(f"creer_brouillon_newsletter : {erreur_ghost}")
        raise

    _journaliser(
        ghost_config,
        f"Brouillon de newsletter cree ({len(fiches)} evenements) : {url_edition}",
    )

    return {
        "url_edition": url_edition,
        "nombre_evenements": len(fiches),
    }
