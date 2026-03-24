"""
Module d'impression pour le POS LaBoutik.
Dispatch les impressions vers le bon backend selon le type d'imprimante.
/ Printing module for the LaBoutik POS.
Dispatches print jobs to the correct backend based on printer type.

LOCALISATION : laboutik/printing/__init__.py

FLUX :
1. Le code appelant passe un objet Printer et les donnees du ticket
2. imprimer() cherche le backend correspondant au type d'imprimante
3. Le backend verifie que l'imprimante est joignable (can_print)
4. Le backend envoie les donnees a l'imprimante (print_ticket)

BACKENDS enregistres :
- SC (Sunmi Cloud) : HTTPS HMAC vers l'API Sunmi Cloud
- SI (Sunmi Inner) : JSON via WebSocket (channel layer Redis)
- LN (Sunmi LAN) : HTTP POST direct sur l'IP de l'imprimante
- MK (Mock) : ASCII pretty-print dans la console Celery (dev/test)
"""
import logging

from django.utils.translation import gettext_lazy as _

from laboutik.printing.mock import MockBackend
from laboutik.printing.sunmi_cloud import SunmiCloudBackend
from laboutik.printing.sunmi_inner import SunmiInnerBackend
from laboutik.printing.sunmi_lan import SunmiLanBackend

logger = logging.getLogger(__name__)

# Dictionnaire des backends d'impression enregistres.
# Cle = printer_type (ex: 'SC', 'SI', 'LN', 'MK'), valeur = classe backend.
# / Registered printing backends.
# Key = printer_type (e.g. 'SC', 'SI', 'LN'), value = backend class.
BACKENDS = {
    'SC': SunmiCloudBackend,
    'SI': SunmiInnerBackend,
    'LN': SunmiLanBackend,
    'MK': MockBackend,
}


def imprimer(printer, ticket_data):
    """
    Envoie un ticket a l'imprimante via le bon backend.
    Retourne un dict {"ok": bool, "error": str ou None}.
    / Sends a ticket to the printer via the correct backend.
    Returns a dict {"ok": bool, "error": str or None}.

    LOCALISATION : laboutik/printing/__init__.py

    :param printer: Instance de laboutik.models.Printer
    :param ticket_data: dict avec header, articles, total, qrcode, footer
    :return: dict avec "ok" (bool) et "error" (str ou None)
    """
    # Verifier que le type d'imprimante a un backend enregistre
    # / Check that the printer type has a registered backend
    backend_class = BACKENDS.get(printer.printer_type)
    if backend_class is None:
        error_message = f"Aucun backend pour le type '{printer.get_printer_type_display()}'"
        logger.error(f"[PRINT] {error_message}")
        return {"ok": False, "error": error_message}

    backend = backend_class()

    # Verifier que l'imprimante est joignable
    # / Check that the printer is reachable
    can_print_ok, can_print_error = backend.can_print(printer)
    if not can_print_ok:
        logger.warning(f"[PRINT] Imprimante {printer.name} non joignable : {can_print_error}")
        return {"ok": False, "error": can_print_error}

    # Envoyer le ticket
    # / Send the ticket
    return backend.print_ticket(printer, ticket_data)
