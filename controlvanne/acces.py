"""
Règle d'accès aux écrans kiosk des tireuses, commune au HTTP et au WebSocket.
/ Access rule for tap kiosk screens, shared by HTTP and WebSocket.

LOCALISATION : controlvanne/acces.py

Utilisée par :
- _verifier_authentification_kiosk (controlvanne/viewsets.py) : pages
  /controlvanne/kiosk/ et /controlvanne/kiosk/<uuid>/ ;
- PanelConsumer.connect (controlvanne/consumers.py) : WebSocket /ws/rfid/...
Une seule règle : la page et son WebSocket laissent passer les mêmes personnes
(audit 2026-09-26, point 1.1).
/ One rule: the page and its WebSocket let the same people in.

Module séparé de viewsets.py pour que consumers.py n'importe pas toute l'API.
/ Separate module so consumers.py does not import the whole API.
"""


def peut_voir_les_kiosks(session, utilisateur, lieu):
    """
    Vrai si ce visiteur a le droit de voir les écrans kiosk de ce lieu.
    / True if this visitor may see this venue's kiosk screens.

    Deux cas autorisés :
    1. Session kiosk : le Pi s'est authentifié avec sa clé API (AuthKioskView),
       puis Chromium a reçu une session marquée controlvanne_authenticated.
       Le cookie de session est propre à chaque domaine, donc à chaque lieu.
    2. Admin du lieu connecté (debug, simulateur DEMO).
    Le jeton à usage unique (?kiosk_token=) n'est pas traité ici : il n'existe
    qu'en HTTP (_verifier_authentification_kiosk).
    / 1. Kiosk session. 2. Logged-in venue admin. The one-time token is HTTP only.

    ATTENTION : fonction SYNCHRONE, elle fait des requêtes en base (lecture de
    la session, is_tenant_admin). Depuis du code async, l'appeler via
    database_sync_to_async, après avoir rétabli le lieu (connection.set_tenant).
    / SYNC function (DB queries): call it through database_sync_to_async.

    :param session: SessionBase — session Django du visiteur (peut être None)
    :param utilisateur: TibilletUser ou AnonymousUser (peut être None)
    :param lieu: Client — le lieu (tenant) de la page ou du WebSocket
    :return: bool
    """
    session_kiosk = session is not None and session.get("controlvanne_authenticated")
    if session_kiosk:
        return True

    utilisateur_connecte = utilisateur is not None and utilisateur.is_authenticated
    if utilisateur_connecte:
        return utilisateur.is_tenant_admin(lieu)

    return False
