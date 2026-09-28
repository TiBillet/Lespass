"""
Groupes Channels des écrans kiosk, nommés PAR LIEU, et envoi vers ces groupes.
/ Channels groups for kiosk screens, named PER VENUE, and sending to them.

LOCALISATION : controlvanne/groupes_ws.py

POURQUOI : Redis est partagé par tous les lieux (TiBillet/settings.py,
CHANNEL_LAYERS, sans préfixe). L'ancien groupe « rfid_state.all » était donc
COMMUN à tous les lieux : un kiosk « liste » d'un lieu recevait les badges des
autres lieux (prénom, UID, solde). Audit 2026-09-26, point 1.2.
/ Redis is shared by all venues: the old "rfid_state.all" group leaked badges
between venues.

Noms des groupes (lettres, chiffres, « - », « _ », « . » ; 100 caractères max) :
- rfid_state.<uuid du lieu>.all              → toutes les tireuses du lieu (liste)
- rfid_state.<uuid du lieu>.<uuid tireuse>   → une seule tireuse (écran du Pi)
/ Group names: per-venue "all" group, and per-tap group.

Utilisé par :
- PanelConsumer.connect (consumers.py) : abonnement ;
- _push_ws_kiosk (viewsets.py), demander_rechargement_des_kiosks et
  pousser_snapshot_apres_commit (signals.py) : envoi via pousser_aux_kiosks.
Aucun import de viewsets / signals / consumers ici : pas d'import circulaire.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connection

PREFIXE_DES_GROUPES = "rfid_state"


def groupe_de_la_tireuse(uuid_du_lieu, uuid_de_la_tireuse):
    """
    Groupe d'UNE tireuse (écran du Pi posé dessus).
    / Group of ONE tap (screen of its Pi).
    """
    return f"{PREFIXE_DES_GROUPES}.{uuid_du_lieu}.{str(uuid_de_la_tireuse).lower()}"


def groupe_de_tout_le_lieu(uuid_du_lieu):
    """
    Groupe de TOUTES les tireuses d'un lieu (page liste des tireuses).
    / Group of ALL taps of a venue (tap list page).
    """
    return f"{PREFIXE_DES_GROUPES}.{uuid_du_lieu}.all"


def uuid_du_lieu_courant():
    """
    UUID du lieu (tenant) de la connexion en cours.
    / UUID of the current connection's venue (tenant).

    Dans une requête HTTP, connection.tenant est le vrai lieu (Client).
    Sous schema_context (scripts, tests), c'est un FakeTenant sans uuid :
    on retrouve alors le lieu par le nom du schéma.
    / Under schema_context, connection.tenant is a FakeTenant without uuid:
    the venue is then found by its schema name.

    :return: UUID du lieu, ou None si on est sur le schéma public
    """
    uuid_du_lieu = getattr(connection.tenant, "uuid", None)
    if uuid_du_lieu is not None:
        return uuid_du_lieu

    from Customers.models import Client

    lieu = Client.objects.filter(schema_name=connection.schema_name).first()
    if lieu is None:
        return None
    return lieu.uuid


def pousser_aux_kiosks(uuid_de_la_tireuse, payload, uuid_du_lieu):
    """
    Envoie un message à l'écran de la tireuse ET à la liste des tireuses du lieu.
    / Sends a message to the tap's screen AND to the venue's tap list.

    Le message est reçu par PanelConsumer.state_update (consumers.py), qui le
    transmet tel quel à ecran_tireuse.js.
    / Received by PanelConsumer.state_update, forwarded to ecran_tireuse.js.

    uuid_du_lieu est passé par l'appelant (et pas relu ici) : les envois partent
    souvent dans un transaction.on_commit, et l'appelant fixe le lieu au moment
    où l'événement a lieu.
    / uuid_du_lieu is given by the caller: sends often run in on_commit.

    :param uuid_de_la_tireuse: UUID de la tireuse
    :param payload: dict — message (format : controlvanne/ws_payloads.py)
    :param uuid_du_lieu: UUID du lieu (voir uuid_du_lieu_courant)
    """
    channel_layer = get_channel_layer()
    if not channel_layer or uuid_du_lieu is None:
        return

    message = {"type": "state_update", "payload": payload}
    async_to_sync(channel_layer.group_send)(
        groupe_de_la_tireuse(uuid_du_lieu, uuid_de_la_tireuse), message
    )
    async_to_sync(channel_layer.group_send)(
        groupe_de_tout_le_lieu(uuid_du_lieu), message
    )
