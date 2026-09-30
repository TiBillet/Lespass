"""
Déclarer une carte primaire à l'ancien Fedow, ou l'en retirer.
/ Declare a primary card to the old Fedow, or withdraw it.

LOCALISATION : laboutik/carte_primaire_ancien_fedow.py

Le système est hybride : la MÊME carte primaire sert au Fedow local et à l'ancien Fedow.
L'ancien Fedow refuse un vidage signé par une carte qu'il ne connaît pas comme carte
primaire du lieu (« Primary card must be in place primary cards »). Une carte primaire
est donc déclarée là-bas à sa création, et retirée à sa suppression, comme dans
LaBoutik V1. Seulement si le lieu est relié à l'ancien Fedow.
/ The same primary card serves both Fedow servers: it is declared to the old Fedow when
created, and withdrawn when deleted, only when the venue is linked.

APPELS EXPLICITES, JAMAIS PAR UN SIGNAL. Qui appelle :
- l'admin des cartes primaires (Administration/admin/laboutik.py) : le formulaire
  d'ajout déclare, la suppression (unitaire ou groupée) retire ;
- la commande `create_test_pos_data`, quand elle crée la carte primaire du simulateur ;
- la commande de rattrapage `declarer_cartes_primaires_ancien_fedow`.
Une carte primaire écrite par l'ORM (tests, « vider et délier » à la caisse) ne part pas
vers l'ancien Fedow. Pour « vider et délier », c'est voulu : le VOID de l'ancien Fedow
retire déjà lui-même le lien primaire, et un appel réseau dans la transaction du vidage
local l'annulerait s'il échouait, alors que l'ancien Fedow a déjà vidé la carte.
/ Explicit calls only, never a signal.

Les deux fonctions sont synchrones : l'appelant voit l'échec tout de suite.
/ Both functions are synchronous: the caller sees the failure right away.
"""

import logging

from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig

logger = logging.getLogger(__name__)


def declarer_la_carte_primaire_a_l_ancien_fedow(carte):
    """
    Déclare la carte comme carte primaire du lieu sur l'ancien Fedow.
    / Declares the card as a primary card of the venue on the old Fedow.

    FLUX :
    1. Lieu non relié à l'ancien Fedow : rien à faire (le client n'est pas créé).
    2. On lit d'abord la carte sur l'ancien Fedow. Une carte qu'il ne connaît pas lève
       `CarteInconnueDeFedow` (réponse 404). Sans cette lecture, `card/set_primary`
       répondrait une erreur 500 impossible à distinguer d'une panne.
    3. On la déclare (`card/set_primary`, `delete=False`) : 200 déclarée, 208 déjà
       déclarée.

    :param carte: CarteCashless de la carte primaire
    :return: True si la carte a été déclarée, False si le lieu n'est pas relié
    :raises CarteInconnueDeFedow: l'ancien Fedow ne connaît pas la carte
    :raises Exception: l'ancien Fedow refuse ou ne répond pas (le code est dans le message)
    """
    lieu_relie_a_l_ancien_fedow = FedowConfig.get_solo().can_fedow()
    if not lieu_relie_a_l_ancien_fedow:
        return False

    client_de_l_ancien_fedow = FedowAPI()
    client_de_l_ancien_fedow.NFCcard.retrieve(carte.tag_id)
    client_de_l_ancien_fedow.NFCcard.set_primary(carte.tag_id, delete=False)
    logger.info(f"Carte primaire {carte.tag_id} déclarée à l'ancien Fedow.")
    return True


def retirer_la_carte_primaire_de_l_ancien_fedow(carte):
    """
    Retire la carte des cartes primaires du lieu sur l'ancien Fedow.
    / Withdraws the card from the venue's primary cards on the old Fedow.

    Lieu non relié : rien à faire (le client n'est pas créé).
    Réponse attendue : 205. Une carte inconnue de l'ancien Fedow donne une erreur 500.
    / Unlinked venue: nothing to do. Expected answer: 205.

    :param carte: CarteCashless de la carte primaire
    :return: True si la carte a été retirée, False si le lieu n'est pas relié
    :raises Exception: l'ancien Fedow refuse ou ne répond pas (le code est dans le message)
    """
    lieu_relie_a_l_ancien_fedow = FedowConfig.get_solo().can_fedow()
    if not lieu_relie_a_l_ancien_fedow:
        return False

    client_de_l_ancien_fedow = FedowAPI()
    client_de_l_ancien_fedow.NFCcard.set_primary(carte.tag_id, delete=True)
    logger.info(f"Carte primaire {carte.tag_id} retirée de l'ancien Fedow.")
    return True
