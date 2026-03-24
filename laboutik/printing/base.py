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
