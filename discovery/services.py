"""
Fabrication des codes PIN d'appairage.
/ Pairing PIN creation.

LOCALISATION : discovery/services.py

POURQUOI UNE FONCTION ET PAS UN SIGNAL :
Un signal post_save sur Terminal fabriquerait un code PIN a chaque fois qu'un Terminal est
cree — y compris dans les tests, qui en creent directement, et sous un FakeTenant ou la cle
etrangere `tenant` du PairingDevice n'existe pas. Il faudrait empiler trois garde-fous pour
le rendre sur, et un lecteur n'aurait aucun moyen de deviner qu'un code PIN nait tout seul.

On appelle donc cette fonction depuis les trois endroits — et seulement ceux-la — ou l'on
veut vraiment faire entrer un appareil :

1. Administration/admin/laboutik.py : quand le gestionnaire cree un terminal ;
2. controlvanne/signals.py : quand il cree une tireuse (elle fabrique son terminal) ;
3. Administration/admin/laboutik.py : l'action « Generer un nouveau code PIN »
   (l'appareil est perdu ou grille, on en appaire un autre).

/ WHY A FUNCTION AND NOT A SIGNAL: a post_save signal would issue a PIN every time a
Terminal is created — including in tests, under a FakeTenant where the `tenant` FK does not
exist. Three guards would be needed, and no reader could guess a PIN is born on its own.
"""
import logging

from django.db import connection

logger = logging.getLogger(__name__)


def fabriquer_le_code_pin_d_appairage(terminal):
    """
    Fabrique le code PIN qui permettra a un appareil de reclamer ce terminal.
    / Issues the PIN that will let a device claim this terminal.

    LOCALISATION : discovery/services.py

    Le code vit dans le schema PUBLIC, jamais dans celui du lieu. C'est indispensable :
    l'appareil qui le tape ne connait pas encore son lieu — il appelle une route publique,
    et c'est le serveur qui lui apprend ou il atterrit.

    Le code porte `cible_uuid` = l'identifiant du terminal a remplir. Ce n'est PAS une cle
    etrangere : elle serait impossible, le terminal vivant dans le schema du lieu et le code
    dans le schema public. Ce pointeur ne vit que le temps de l'appairage — le claim le vide
    des qu'il a pose le compte sur le terminal.

    A appeler DANS un contexte de lieu (tenant_context / requete admin).

    :param terminal: le laboutik.Terminal a appairer
    :return: le PairingDevice cree, ou None si le lieu n'est pas un vrai lieu (cas des tests
             sous FakeTenant, ou la cle etrangere `tenant` ne peut pas etre posee)
    """
    from Customers.models import Client
    from discovery.models import PairingDevice

    # connection.tenant est un FakeTenant sous schema_context() : il n'a pas de ligne en
    # base, la cle etrangere `tenant` du PairingDevice ne peut donc pas pointer dessus.
    # / connection.tenant is a FakeTenant under schema_context(): no DB row to point at.
    lieu_courant = connection.tenant
    if not isinstance(lieu_courant, Client):
        logger.warning(
            "[APPAIRAGE] Pas de code PIN fabrique pour le terminal "
            f"'{terminal.name}' : le lieu courant n'est pas un vrai lieu."
        )
        return None

    appairage = PairingDevice.objects.create(
        name=terminal.name or str(terminal.id),
        tenant=lieu_courant,
        pin_code=PairingDevice.generate_unique_pin(),
        cible_uuid=terminal.id,
        terminal_role=terminal.terminal_role,
    )

    logger.info(
        f"[APPAIRAGE] Code PIN fabrique pour le terminal '{terminal.name}' "
        f"(role={terminal.terminal_role})"
    )
    return appairage
