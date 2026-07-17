"""
Tests du controle d'acces au canal WebSocket d'impression.
/ Tests of the print WebSocket channel access control.

LOCALISATION : tests/pytest/test_impression_securite_websocket.py

CE QUE CES TESTS PROTEGENT :
Le canal `ws/printer/<uuid>/` transporte le CONTENU des tickets clients — noms, montants,
articles. Un abonne indesirable les lit en clair.

Avant ce chantier, PrinterConsumer.connect() ne verifiait que « l'utilisateur est
authentifie ». N'importe quel compte pouvait donc rejoindre le canal de n'importe quelle
imprimante — y compris celle d'un AUTRE lieu, puisque le canal Redis ne portait pas le nom
du lieu et que Redis est partage par tous.

Desormais, deux verrous :
1. seul le terminal PROPRIETAIRE de l'imprimante peut s'abonner
   (imprimante_appartient_au_terminal) ;
2. le canal Redis porte le nom du lieu (nom_du_groupe_websocket).

PIEGE MULTI-TENANT :
On utilise tenant_context(), jamais schema_context() : schema_context pose un FakeTenant,
et TermUser.save() lit connection.tenant pour poser client_source.
"""
import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from Customers.models import Client as TenantClient
from laboutik.models import Printer, Terminal
from laboutik.printing.base import nom_du_groupe_websocket
from wsocket.consumers import imprimante_appartient_au_terminal


@pytest.fixture
def tenant_lespass():
    return TenantClient.objects.get(schema_name='lespass')


def _creer_terminal(nom_du_terminal, printer=None):
    """
    Cree un TermUser et son Terminal. A appeler DANS un tenant_context.
    / Creates a TermUser and its Terminal. Call INSIDE a tenant_context.
    """
    email_synthetique = f"{uuid.uuid4()}@terminals.local"
    term_user = TermUser.objects.create(
        email=email_synthetique,
        username=email_synthetique,
        first_name=nom_du_terminal,
        terminal_role=TibilletUser.ROLE_LABOUTIK,
    )
    terminal = Terminal.objects.create(
        name=nom_du_terminal,
        term_user=term_user,
        printer=printer,
    )
    return term_user, terminal


# --- Verrou 1 : seul le proprietaire de l'imprimante peut ecouter ---
# / Lock 1: only the printer's owner may listen


@pytest.mark.django_db
def test_le_terminal_proprietaire_peut_ecouter_son_imprimante(tenant_lespass):
    """
    Le cas nominal : la tablette s'abonne au canal de SON imprimante.
    / The nominal case: the tablet subscribes to ITS OWN printer's channel.
    """
    with tenant_context(tenant_lespass):
        imprimante = Printer.objects.create(
            name="Imprimante de la caisse", printer_type=Printer.MOCK,
        )
        user_du_terminal, _terminal = _creer_terminal("Caisse Bar", imprimante)

        autorise = imprimante_appartient_au_terminal(
            tenant_lespass, user_du_terminal, imprimante.uuid,
        )

    assert autorise is True


@pytest.mark.django_db
def test_un_terminal_ne_peut_pas_ecouter_l_imprimante_d_un_autre(tenant_lespass):
    """
    Un terminal ne peut PAS ecouter le canal d'une imprimante qui n'est pas la sienne.
    Sans ce verrou, la caisse du bar lisait les tickets de la caisse d'a cote.
    / A terminal CANNOT listen to a printer that is not its own.
    """
    with tenant_context(tenant_lespass):
        imprimante_de_l_autre = Printer.objects.create(
            name="Imprimante de la caisse voisine", printer_type=Printer.MOCK,
        )
        sa_propre_imprimante = Printer.objects.create(
            name="Sa propre imprimante", printer_type=Printer.MOCK,
        )
        _creer_terminal("Caisse voisine", imprimante_de_l_autre)
        user_curieux, _terminal = _creer_terminal("Caisse curieuse", sa_propre_imprimante)

        autorise = imprimante_appartient_au_terminal(
            tenant_lespass, user_curieux, imprimante_de_l_autre.uuid,
        )

    assert autorise is False


@pytest.mark.django_db
def test_un_humain_authentifie_ne_peut_pas_ecouter_une_imprimante(tenant_lespass):
    """
    Un compte humain authentifie n'est pas un terminal : il n'a rien a faire sur ce canal.
    C'est le trou principal que ce chantier referme — avant, « authentifie » suffisait.
    / An authenticated human account is not a terminal: it has no business on this channel.
    """
    with tenant_context(tenant_lespass):
        imprimante = Printer.objects.create(
            name="Imprimante de la caisse", printer_type=Printer.MOCK,
        )
        _creer_terminal("Caisse Bar", imprimante)

        humain = TibilletUser.objects.create(
            email=f"humain-{uuid.uuid4().hex[:6]}@example.com",
            username=f"humain-{uuid.uuid4().hex[:6]}",
        )

        autorise = imprimante_appartient_au_terminal(
            tenant_lespass, humain, imprimante.uuid,
        )

    assert autorise is False


@pytest.mark.django_db
def test_un_utilisateur_anonyme_est_refuse(tenant_lespass):
    """Un anonyme est refuse. / An anonymous user is rejected."""
    with tenant_context(tenant_lespass):
        imprimante = Printer.objects.create(
            name="Imprimante", printer_type=Printer.MOCK,
        )

        autorise = imprimante_appartient_au_terminal(
            tenant_lespass, AnonymousUser(), imprimante.uuid,
        )

    assert autorise is False


@pytest.mark.django_db
def test_un_terminal_sans_imprimante_est_refuse(tenant_lespass):
    """
    Un terminal qui n'a pas encore d'imprimante ne peut s'abonner a aucun canal.
    / A terminal with no printer yet cannot subscribe to any channel.
    """
    with tenant_context(tenant_lespass):
        imprimante_d_un_autre = Printer.objects.create(
            name="Imprimante d'un autre", printer_type=Printer.MOCK,
        )
        user_sans_imprimante, _terminal = _creer_terminal("Caisse sans imprimante", None)

        autorise = imprimante_appartient_au_terminal(
            tenant_lespass, user_sans_imprimante, imprimante_d_un_autre.uuid,
        )

    assert autorise is False


@pytest.mark.django_db
def test_un_identifiant_qui_n_est_pas_un_uuid_est_refuse(tenant_lespass):
    """
    Un identifiant malforme dans l'URL est refuse proprement, sans erreur serveur.
    / A malformed identifier in the URL is cleanly rejected, with no server error.
    """
    with tenant_context(tenant_lespass):
        imprimante = Printer.objects.create(
            name="Imprimante", printer_type=Printer.MOCK,
        )
        user_du_terminal, _terminal = _creer_terminal("Caisse", imprimante)

        autorise = imprimante_appartient_au_terminal(
            tenant_lespass, user_du_terminal, "pas-un-uuid",
        )

    assert autorise is False


# --- Verrou 2 : le canal Redis porte le nom du lieu ---
# / Lock 2: the Redis channel carries the venue name


def test_le_canal_redis_porte_le_nom_du_lieu():
    """
    Deux lieux differents ne partagent jamais le meme canal, meme pour un identifiant
    d'imprimante identique. Redis est partage par TOUS les lieux : sans cette separation,
    un abonne du lieu A recevrait les tickets du lieu B.
    / Two venues never share a channel. Redis is shared across ALL venues.
    """
    identifiant_imprimante = uuid.uuid4()

    canal_du_lieu_a = nom_du_groupe_websocket("lespass", identifiant_imprimante)
    canal_du_lieu_b = nom_du_groupe_websocket("festival", identifiant_imprimante)

    assert canal_du_lieu_a != canal_du_lieu_b
    assert "lespass" in canal_du_lieu_a
    assert "festival" in canal_du_lieu_b


def test_l_emetteur_et_le_recepteur_calculent_le_meme_canal():
    """
    Les deux bouts de la chaine doivent nommer le canal de la MEME facon.
    S'ils divergeaient, l'impression deviendrait muette : le ticket partirait dans un canal
    que personne n'ecoute, et aucune erreur ne serait levee.
    / Both ends must name the channel the SAME way, or printing breaks silently.

    Ce test lit leur code source. C'est grossier, mais c'est precisement ce qui rattrape
    quelqu'un qui refabriquerait le nom a la main.
    """
    import inspect

    from laboutik.printing import sunmi_inner
    from wsocket import consumers

    source_de_l_emetteur = inspect.getsource(sunmi_inner.SunmiInnerBackend.print_ticket)
    source_du_recepteur = inspect.getsource(consumers.PrinterConsumer.connect)

    assert "nom_du_groupe_websocket" in source_de_l_emetteur
    assert "nom_du_groupe_websocket" in source_du_recepteur

    # Et surtout : aucun des deux ne fabrique plus le nom a la main.
    # / And above all: neither builds the name by hand anymore.
    assert 'f"printer-{printer.uuid}"' not in source_de_l_emetteur
    assert 'f"printer-{self.printer_uuid}"' not in source_du_recepteur
