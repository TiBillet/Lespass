"""
Tests du WebSocket des écrans kiosk (PanelConsumer) : accès et groupes par lieu.
/ Tests for the kiosk screens WebSocket: access control and per-venue groups.

LOCALISATION : tests/pytest/test_controlvanne_ws.py

Couvre l'audit du 2026-09-26 :
- point 1.1 : la connexion est refusée si le visiteur n'est ni un kiosk, ni un
  admin du lieu (même règle que la page, controlvanne/acces.py) ;
- point 1.2 : les groupes Channels sont nommés par lieu
  (controlvanne/groupes_ws.py). Un message d'un autre lieu n'arrive jamais.

PIÈGES (tests/PIEGES.md, 9.43 et 9.44) :
- chaque test async porte @pytest.mark.asyncio ;
- WebsocketCommunicator ne passe ni par le URLRouter ni par les middlewares :
  url_route, tenant, session et user sont posés à la main dans le scope.
Channel layer en mémoire (override_settings) : pas besoin de Redis.
/ Each async test has @pytest.mark.asyncio; the scope is built by hand;
in-memory channel layer.
"""

import uuid

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings
from django_tenants.utils import tenant_context

from controlvanne.consumers import PanelConsumer
from controlvanne.groupes_ws import pousser_aux_kiosks

CANAL_EN_MEMOIRE = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
NOM_TIREUSE_WS = "Tireuse websocket test"


# ─────────────────────────────────────────────────────────────────────
# Fixtures (synchrones : les requêtes en base se font hors de la boucle async)
# / Fixtures (sync: DB queries happen outside the async loop)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def tireuse_ws(tenant):
    """Une tireuse du lieu lespass, supprimée après le test. / A tap, deleted after."""
    with tenant_context(tenant):
        from controlvanne.models import TireuseBec
        from laboutik.models import PointDeVente, Terminal

        TireuseBec.objects.filter(nom_tireuse=NOM_TIREUSE_WS).delete()
        PointDeVente.objects.filter(name=NOM_TIREUSE_WS).delete()
        Terminal.objects.filter(name=NOM_TIREUSE_WS).delete()
        tireuse = TireuseBec.objects.create(nom_tireuse=NOM_TIREUSE_WS, enabled=True)
    yield tireuse
    with tenant_context(tenant):
        TireuseBec.objects.filter(pk=tireuse.pk).delete()
        PointDeVente.objects.filter(name=NOM_TIREUSE_WS).delete()
        Terminal.objects.filter(name=NOM_TIREUSE_WS).delete()


@pytest.fixture
def session_kiosk(tenant):
    """
    Session marquée kiosk, comme après AuthKioskView / ?kiosk_token=.
    Renvoie une SessionStore NON chargée (elle se charge dans le consumer).
    / Kiosk-marked session. Returns an unloaded SessionStore.
    """
    from django.contrib.sessions.backends.db import SessionStore

    with tenant_context(tenant):
        session_enregistree = SessionStore()
        session_enregistree["controlvanne_authenticated"] = True
        session_enregistree.save()
    return SessionStore(session_key=session_enregistree.session_key)


@pytest.fixture
def session_vide():
    """Session sans marque kiosk. / Session without kiosk mark."""
    from django.contrib.sessions.backends.db import SessionStore

    return SessionStore()


@pytest.fixture
def admin_d_un_autre_lieu():
    """Compte connecté qui n'administre PAS lespass. / Logged-in non-admin of lespass."""
    from AuthBillet.models import TibilletUser

    email = "test-ws-admin-autre-lieu@example.org"
    compte, _created = TibilletUser.objects.get_or_create(
        email=email, defaults={"username": email}
    )
    compte.is_active = True
    compte.save()
    compte.client_admin.clear()
    return compte


async def _ouvrir_le_websocket(lieu, slug, session, utilisateur):
    """
    Ouvre /ws/rfid/<slug>/ avec un scope construit à la main.
    / Opens the WebSocket with a hand-built scope.

    :return: (communicator, connecté ou non)
    """
    chemin = "/ws/rfid/all/" if slug == "all" else f"/ws/rfid/{slug}/"
    communicator = WebsocketCommunicator(PanelConsumer.as_asgi(), chemin)
    arguments_de_route = {} if slug == "all" else {"slug": slug}
    communicator.scope["url_route"] = {"kwargs": arguments_de_route}
    communicator.scope["tenant"] = lieu
    communicator.scope["session"] = session
    communicator.scope["user"] = utilisateur
    connecte, _code = await communicator.connect()
    return communicator, connecte


# ─────────────────────────────────────────────────────────────────────
# Point 1.1 — contrôle d'accès / Access control
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_01_anonyme_est_refuse(tenant, session_vide):
    """Ni session kiosk ni compte : refusé. / Anonymous: refused."""
    with override_settings(CHANNEL_LAYERS=CANAL_EN_MEMOIRE):
        communicator, connecte = await _ouvrir_le_websocket(
            tenant, "all", session_vide, AnonymousUser()
        )
        assert connecte is False
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_02_lieu_inconnu_est_refuse(session_kiosk):
    """Domaine inconnu (scope["tenant"] = None) : refusé, même avec une session kiosk."""
    with override_settings(CHANNEL_LAYERS=CANAL_EN_MEMOIRE):
        communicator, connecte = await _ouvrir_le_websocket(
            None, "all", session_kiosk, AnonymousUser()
        )
        assert connecte is False
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_03_session_kiosk_est_acceptee(tenant, session_kiosk):
    """Session kiosk : acceptée. / Kiosk session: accepted."""
    with override_settings(CHANNEL_LAYERS=CANAL_EN_MEMOIRE):
        communicator, connecte = await _ouvrir_le_websocket(
            tenant, "all", session_kiosk, AnonymousUser()
        )
        assert connecte is True
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_04_admin_du_lieu_est_accepte(tenant, session_vide, admin_user):
    """Admin du lieu connecté : accepté. / Venue admin: accepted."""
    with override_settings(CHANNEL_LAYERS=CANAL_EN_MEMOIRE):
        communicator, connecte = await _ouvrir_le_websocket(
            tenant, "all", session_vide, admin_user
        )
        assert connecte is True
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_05_admin_d_un_autre_lieu_est_refuse(
    tenant, session_vide, admin_d_un_autre_lieu
):
    """Compte connecté mais pas admin de CE lieu : refusé."""
    with override_settings(CHANNEL_LAYERS=CANAL_EN_MEMOIRE):
        communicator, connecte = await _ouvrir_le_websocket(
            tenant, "all", session_vide, admin_d_un_autre_lieu
        )
        assert connecte is False
        await communicator.disconnect()


@pytest.mark.asyncio
async def test_06_slug_invalide_ou_tireuse_inconnue_est_refuse(tenant, session_kiosk):
    """Slug qui n'est pas un UUID, ou UUID d'aucune tireuse du lieu : refusé."""
    with override_settings(CHANNEL_LAYERS=CANAL_EN_MEMOIRE):
        for slug_refuse in ["pas-un-uuid", str(uuid.uuid4())]:
            communicator, connecte = await _ouvrir_le_websocket(
                tenant, slug_refuse, session_kiosk, AnonymousUser()
            )
            assert connecte is False, slug_refuse
            await communicator.disconnect()


# ─────────────────────────────────────────────────────────────────────
# Point 1.2 — groupes par lieu / Per-venue groups
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_07_liste_recoit_son_lieu_et_pas_les_autres(
    tenant, session_kiosk, tireuse_ws
):
    """
    La page liste reçoit les messages de SON lieu, jamais ceux d'un autre lieu.
    C'était la fuite de l'ancien groupe commun « rfid_state.all ».
    / The list page gets its venue's messages, never another venue's.
    """
    with override_settings(CHANNEL_LAYERS=CANAL_EN_MEMOIRE):
        communicator, connecte = await _ouvrir_le_websocket(
            tenant, "all", session_kiosk, AnonymousUser()
        )
        assert connecte is True

        # Message d'un autre lieu (même UUID de tireuse, lieu différent)
        # / Message from another venue
        await sync_to_async(pousser_aux_kiosks)(
            tireuse_ws.uuid, {"message": "autre lieu"}, uuid.uuid4()
        )
        assert await communicator.receive_nothing(timeout=0.3)

        # Message de ce lieu / Message from this venue
        await sync_to_async(pousser_aux_kiosks)(
            tireuse_ws.uuid, {"message": "ce lieu"}, tenant.uuid
        )
        message_recu = await communicator.receive_json_from(timeout=2)
        assert message_recu == {"message": "ce lieu"}

        await communicator.disconnect()


@pytest.mark.asyncio
async def test_08_ecran_d_une_tireuse_recoit_ses_messages(
    tenant, session_kiosk, tireuse_ws
):
    """L'écran d'une tireuse de ce lieu est accepté et reçoit ses messages."""
    with override_settings(CHANNEL_LAYERS=CANAL_EN_MEMOIRE):
        communicator, connecte = await _ouvrir_le_websocket(
            tenant, str(tireuse_ws.uuid), session_kiosk, AnonymousUser()
        )
        assert connecte is True

        # État initial envoyé à la connexion / Initial state sent on connect
        etat_initial = await communicator.receive_json_from(timeout=2)
        assert etat_initial["tireuse_bec_uuid"] == str(tireuse_ws.uuid)

        await sync_to_async(pousser_aux_kiosks)(
            tireuse_ws.uuid, {"kiosk_reload": True}, tenant.uuid
        )
        assert await communicator.receive_json_from(timeout=2) == {"kiosk_reload": True}

        await communicator.disconnect()
