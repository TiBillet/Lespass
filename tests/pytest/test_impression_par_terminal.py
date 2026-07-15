"""
Tests du routage de l'impression par TERMINAL (et non plus par point de vente).
/ Tests of print routing by TERMINAL (no longer by point of sale).

LOCALISATION : tests/pytest/test_impression_par_terminal.py

CE QUE CES TESTS PROTEGENT :
En festival, une vingtaine de tablettes encaissent sur le MEME point de vente (« Bar »),
et chacune a sa propre imprimante. Tant que l'imprimante etait portee par le point de
vente, les vingt tablettes s'abonnaient au meme canal WebSocket et chaque ticket sortait
vingt fois. L'imprimante est desormais portee par le Terminal.

Voir TECH_DOC/SESSIONS/IMPRESSION/SPEC.md.

PIEGE MULTI-TENANT :
On utilise tenant_context(), jamais schema_context() : schema_context pose un FakeTenant,
et TermUser.save() lit connection.tenant pour poser client_source.
"""
import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from BaseBillet.models import LaBoutikAPIKey
from Customers.models import Client as TenantClient
from discovery.models import PairingDevice
from laboutik.models import Printer, Terminal
from laboutik.views import imprimante_du_terminal


@pytest.fixture
def tenant_lespass():
    """Le tenant de test / The test tenant."""
    return TenantClient.objects.get(schema_name='lespass')


def _creer_terminal(nom_du_terminal, printer=None):
    """
    Cree un TermUser et son Terminal, comme le fait l'appairage.
    / Creates a TermUser and its Terminal, the way pairing does.

    A appeler DANS un tenant_context.
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


@pytest.mark.django_db
def test_deux_terminaux_du_meme_point_de_vente_ont_chacun_leur_imprimante(tenant_lespass):
    """
    LE test qui prouve la correction : deux terminaux qui encaissent sur le meme point de
    vente ont chacun LEUR imprimante. C'est exactement le cas du festival (vingt tablettes
    sur le point de vente « Bar »).
    / THE test that proves the fix: two terminals on the same point of sale each get THEIR
    own printer.
    """
    with tenant_context(tenant_lespass):
        imprimante_du_bar = Printer.objects.create(
            name="Imprimante Bar", printer_type=Printer.MOCK,
        )
        imprimante_de_la_buvette = Printer.objects.create(
            name="Imprimante Buvette", printer_type=Printer.MOCK,
        )

        user_bar, _terminal_bar = _creer_terminal("Caisse Bar", imprimante_du_bar)
        user_buvette, _terminal_buvette = _creer_terminal(
            "Caisse Buvette", imprimante_de_la_buvette,
        )

        # Chacun sort son ticket sur SON imprimante, pas sur celle de l'autre.
        # / Each one prints on ITS OWN printer, not the other's.
        assert imprimante_du_terminal(user_bar) == imprimante_du_bar
        assert imprimante_du_terminal(user_buvette) == imprimante_de_la_buvette


@pytest.mark.django_db
def test_plusieurs_terminaux_peuvent_partager_une_imprimante(tenant_lespass):
    """
    Plusieurs terminaux peuvent pointer la MEME imprimante : un Raspberry Pi qui imprime
    sur une imprimante cloud, ou une tablette Sunmi qui imprime sur l'imprimante integree
    d'une autre tablette Sunmi.
    / Several terminals may share ONE printer.
    """
    with tenant_context(tenant_lespass):
        imprimante_partagee = Printer.objects.create(
            name="Imprimante du comptoir", printer_type=Printer.MOCK,
        )

        user_a, _terminal_a = _creer_terminal("Sunmi A", imprimante_partagee)
        user_b, _terminal_b = _creer_terminal("Raspberry Pi", imprimante_partagee)

        assert imprimante_du_terminal(user_a) == imprimante_partagee
        assert imprimante_du_terminal(user_b) == imprimante_partagee

        # La relation inverse dit qui imprime sur cette imprimante.
        # / The reverse relation tells who prints on this printer.
        assert imprimante_partagee.terminaux.count() == 2


@pytest.mark.django_db
def test_pas_d_imprimante_pour_un_utilisateur_anonyme():
    """
    Un utilisateur non authentifie n'a pas d'imprimante. Ce n'est pas une erreur : on
    n'imprime pas, c'est tout. Ce cas arrive par le chemin d'authentification Api-Key.
    / An anonymous user has no printer. Not an error: we simply don't print.
    """
    assert imprimante_du_terminal(AnonymousUser()) is None
    assert imprimante_du_terminal(None) is None


@pytest.mark.django_db
def test_pas_d_imprimante_pour_un_humain_en_session_admin(tenant_lespass):
    """
    Un humain connecte dans un navigateur n'est pas un terminal : il n'a pas de Terminal,
    donc pas d'imprimante. C'est voulu — une imprimante appartient a un appareil, pas a un
    navigateur.
    / A human logged in a browser is not a terminal: no Terminal, hence no printer.
    """
    with tenant_context(tenant_lespass):
        humain = TibilletUser.objects.create(
            email=f"humain-{uuid.uuid4().hex[:6]}@example.com",
            username=f"humain-{uuid.uuid4().hex[:6]}",
        )

        # getattr sur une relation inverse OneToOne absente renvoie bien None,
        # il ne leve pas. C'est ce sur quoi repose imprimante_du_terminal().
        # / getattr on a missing reverse OneToOne returns None, it does not raise.
        assert imprimante_du_terminal(humain) is None


@pytest.mark.django_db
def test_pas_d_imprimante_si_le_terminal_n_en_a_pas(tenant_lespass):
    """
    Un terminal fraichement appaire n'a pas encore d'imprimante : le gestionnaire doit la
    lui choisir dans l'admin.
    / A freshly paired terminal has no printer yet.
    """
    with tenant_context(tenant_lespass):
        user_sans_imprimante, _terminal = _creer_terminal("Caisse sans imprimante")
        assert imprimante_du_terminal(user_sans_imprimante) is None


@pytest.mark.django_db
def test_pas_d_imprimante_si_elle_est_desactivee(tenant_lespass):
    """
    Une imprimante desactivee n'imprime pas. Le decochage de `active` dans l'admin doit
    suffire a la mettre hors service, sans avoir a la detacher du terminal.
    / A deactivated printer does not print.
    """
    with tenant_context(tenant_lespass):
        imprimante_en_panne = Printer.objects.create(
            name="Imprimante en panne", printer_type=Printer.MOCK, active=False,
        )
        user, _terminal = _creer_terminal("Caisse", imprimante_en_panne)

        assert imprimante_du_terminal(user) is None


@pytest.mark.django_db
def test_le_point_de_vente_ne_porte_plus_d_imprimante():
    """
    Le champ `printer` a disparu de PointDeVente. Ce test fait echouer la suite si
    quelqu'un le reintroduit : ce serait ramener le bug des vingt tickets.
    / The `printer` field is gone from PointDeVente. This test fails if it comes back.
    """
    from laboutik.models import PointDeVente

    noms_des_champs = [champ.name for champ in PointDeVente._meta.get_fields()]
    assert "printer" not in noms_des_champs


@pytest.mark.django_db
def test_l_appairage_remplit_le_terminal_qui_l_attendait(tenant_lespass):
    """
    Le terminal existe AVANT l'appairage. Le claim ne le cree pas : il le REMPLIT, en lui
    posant le compte qui lui manquait pour travailler.
    / The terminal exists BEFORE pairing. The claim does not create it, it FILLS it in.
    """
    from discovery.services import fabriquer_le_code_pin_d_appairage
    from discovery.views import _remplir_le_terminal

    with tenant_context(tenant_lespass):
        # Le gestionnaire declare l'appareil. Cette creation fabrique le code PIN.
        # / The manager declares the device. This creation issues the PIN.
        terminal = Terminal.objects.create(
            name="Caisse du chapiteau",
            terminal_role=TibilletUser.ROLE_LABOUTIK,
        )
        appairage = fabriquer_le_code_pin_d_appairage(terminal)

        assert terminal.est_appaire() is False
        assert terminal.code_pin_en_attente() == appairage.pin_code

        # L'appareil tape le code.
        # / The device types the PIN.
        api_key, tireuse_uuid = _remplir_le_terminal(appairage)

        assert api_key
        assert tireuse_uuid is None  # ce n'est pas une tireuse / not a tap

        terminal.refresh_from_db()
        assert terminal.est_appaire() is True
        assert terminal.term_user.terminal_role == TibilletUser.ROLE_LABOUTIK

        # Le terminal est joignable depuis le compte : c'est ce dont depend
        # imprimante_du_terminal().
        # / The Terminal is reachable from the account.
        assert terminal.term_user.terminal == terminal


@pytest.mark.django_db
def test_revoquer_un_terminal_coupe_ses_deux_acces(tenant_lespass):
    """
    Revoquer un terminal doit agir sur DEUX leviers : desactiver le compte ET revoquer la
    cle API. Desactiver le compte seul ne suffit pas — la cle est stockee sur l'appareil,
    il suffirait de reactiver le compte pour qu'il se reconnecte tout seul.
    / Revoking a terminal must pull BOTH levers: deactivate the account AND revoke the key.
    """
    from Administration.admin.laboutik import TerminalAdmin
    from Administration.admin.site import staff_admin_site
    from discovery.services import fabriquer_le_code_pin_d_appairage
    from discovery.views import _remplir_le_terminal

    with tenant_context(tenant_lespass):
        terminal = Terminal.objects.create(
            name="Caisse a revoquer",
            terminal_role=TibilletUser.ROLE_LABOUTIK,
        )
        appairage = fabriquer_le_code_pin_d_appairage(terminal)
        _remplir_le_terminal(appairage)

        terminal.refresh_from_db()
        assert terminal.term_user.is_active is True

        cle_avant = LaBoutikAPIKey.objects.get(user=terminal.term_user)
        assert cle_avant.revoked is False

        # On appelle l'action d'admin comme le ferait le gestionnaire.
        # / Call the admin action the way a manager would.
        admin_des_terminaux = TerminalAdmin(Terminal, staff_admin_site)

        class RequeteFactice:
            """Le message_user() de l'admin a besoin d'une requete. / Admin needs a request."""
            def __init__(self):
                self._messages = []

        requete = RequeteFactice()
        admin_des_terminaux.message_user = lambda *args, **kwargs: None
        admin_des_terminaux.revoquer_les_terminaux(
            requete, Terminal.objects.filter(pk=terminal.pk),
        )

        terminal.term_user.refresh_from_db()
        cle_apres = LaBoutikAPIKey.objects.get(pk=cle_avant.pk)

        assert terminal.term_user.is_active is False
        assert cle_apres.revoked is True
