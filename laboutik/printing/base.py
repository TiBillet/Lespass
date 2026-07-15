"""
Interface de base pour les backends d'impression (pattern Strategy).
Chaque backend concret herite de PrinterBackend et implemente les 3 methodes.
/ Base interface for printing backends (Strategy pattern).
Each concrete backend inherits from PrinterBackend and implements the 3 methods.

LOCALISATION : laboutik/printing/base.py

Pas de ABC/metaclass — simple classe avec NotImplementedError.
C'est plus lisible et plus FALC.
/ No ABC/metaclass — simple class with NotImplementedError.
More readable and more FALC.
"""


def nom_du_groupe_websocket(schema_name, printer_uuid):
    """
    Le nom du canal Redis d'une imprimante Sunmi Inner.
    / The Redis channel name of a Sunmi Inner printer.

    LOCALISATION : laboutik/printing/base.py

    LE NOM DU LIEU EST DANS LE CANAL, ET C'EST INDISPENSABLE.
    Redis est partage par TOUS les lieux. Un canal qui ne porterait que l'identifiant de
    l'imprimante mettrait dans le meme canal une imprimante du lieu A et une imprimante du
    lieu B — il suffirait de connaitre un identifiant pour ecouter les tickets d'un autre
    lieu. Le nom du schema cloisonne les canaux.
    / The venue name belongs IN the channel: Redis is shared by ALL venues.

    Les deux bouts de la chaine appellent cette fonction — celui qui ECOUTE
    (wsocket/consumers.py : PrinterConsumer) et celui qui ENVOIE
    (laboutik/printing/sunmi_inner.py). S'ils calculaient le nom chacun de leur cote, une
    divergence rendrait l'impression muette, sans erreur.
    / BOTH ends call this function. Computing the name separately would silently break
    printing.

    :param schema_name: le nom du schema du tenant (ex: "lespass")
    :param printer_uuid: l'identifiant de l'imprimante (str ou UUID)
    :return: le nom du canal Redis (str)
    """
    return f"printer-{schema_name}-{printer_uuid}"


class PrinterBackend:
    """
    Interface pour les backends d'impression.
    Chaque type d'imprimante (Sunmi Cloud, Sunmi Inner) implemente cette interface.
    / Interface for printing backends.
    Each printer type (Sunmi Cloud, Sunmi Inner) implements this interface.

    LOCALISATION : laboutik/printing/base.py
    """

    def can_print(self, printer):
        """
        Verifie que l'imprimante est joignable et prete a imprimer.
        Retourne (True, None) si OK, ou (False, "message d'erreur") sinon.
        / Checks that the printer is reachable and ready to print.
        Returns (True, None) if OK, or (False, "error message") otherwise.

        :param printer: Instance de laboutik.models.Printer
        :return: tuple (bool, str ou None)
        """
        raise NotImplementedError(
            "Les sous-classes doivent implementer can_print(). "
            "/ Subclasses must implement can_print()."
        )

    def print_ticket(self, printer, ticket_data):
        """
        Envoie les donnees du ticket a l'imprimante.
        Retourne {"ok": True} en cas de succes, {"ok": False, "error": "..."} sinon.
        / Sends ticket data to the printer.
        Returns {"ok": True} on success, {"ok": False, "error": "..."} otherwise.

        :param printer: Instance de laboutik.models.Printer
        :param ticket_data: bytes — donnees ESC/POS a envoyer
        :return: dict avec "ok" (bool) et optionnellement "error" (str)
        """
        raise NotImplementedError(
            "Les sous-classes doivent implementer print_ticket(). "
            "/ Subclasses must implement print_ticket()."
        )

    def print_test(self, printer):
        """
        Imprime une page de test sur l'imprimante.
        Retourne {"ok": True} en cas de succes, {"ok": False, "error": "..."} sinon.
        / Prints a test page on the printer.
        Returns {"ok": True} on success, {"ok": False, "error": "..."} otherwise.

        :param printer: Instance de laboutik.models.Printer
        :return: dict avec "ok" (bool) et optionnellement "error" (str)
        """
        raise NotImplementedError(
            "Les sous-classes doivent implementer print_test(). "
            "/ Subclasses must implement print_test()."
        )
