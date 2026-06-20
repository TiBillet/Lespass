"""
Backend d'impression Sunmi Cloud (HTTPS HMAC).
Envoie les donnees ESC/POS a l'API Sunmi Cloud via une requete signee.
/ Sunmi Cloud printing backend (HTTPS HMAC).
Sends ESC/POS data to the Sunmi Cloud API via a signed request.

LOCALISATION : laboutik/printing/sunmi_cloud.py

FLUX :
1. can_print() verifie que le SN et les credentials Sunmi sont configures
2. print_ticket() construit les octets ESC/POS via le builder factorise
3. Cree un SunmiCloudPrinter avec les credentials du tenant
4. Charge les octets dans le buffer et appelle pushContent()

DEPENDENCIES :
- laboutik.models.LaboutikConfiguration (credentials Fernet)
- laboutik.printing.escpos_builder (construction ESC/POS)
- laboutik.printing.sunmi_cloud_printer (envoi HTTPS HMAC)
"""
import logging
import uuid as uuid_module

from django.utils import timezone

from laboutik.printing.base import PrinterBackend
from laboutik.printing.escpos_builder import build_escpos_from_ticket_data
from laboutik.printing.sunmi_cloud_printer import SunmiCloudPrinter

logger = logging.getLogger(__name__)


class SunmiCloudBackend(PrinterBackend):
    """
    Backend pour les imprimantes Sunmi Cloud (type SC).
    Communique via l'API HTTPS de Sunmi avec signature HMAC SHA256.
    Les credentials (app_id, app_key) sont globales par tenant,
    stockees chiffrees dans LaboutikConfiguration.
    / Backend for Sunmi Cloud printers (type SC).
    Communicates via Sunmi's HTTPS API with HMAC SHA256 signature.
    Credentials (app_id, app_key) are global per tenant,
    stored encrypted in LaboutikConfiguration.

    LOCALISATION : laboutik/printing/sunmi_cloud.py
    """

    def can_print(self, printer):
        """
        Verifie que l'imprimante a un numero de serie
        et que les credentials Sunmi sont configurees pour ce tenant.
        / Checks that the printer has a serial number
        and that Sunmi credentials are configured for this tenant.
        """
        # Verifier le numero de serie de l'imprimante
        # / Check the printer serial number
        if not printer.sunmi_serial_number:
            return (False, "Numero de serie Sunmi manquant sur l'imprimante.")

        # Verifier les credentials globales du tenant
        # / Check global tenant credentials
        from laboutik.models import LaboutikConfiguration
        config = LaboutikConfiguration.get_solo()

        app_id = config.get_sunmi_app_id()
        if not app_id:
            return (False, "Sunmi App ID non configure dans la configuration LaBoutik.")

        app_key = config.get_sunmi_app_key()
        if not app_key:
            return (False, "Sunmi App Key non configuree dans la configuration LaBoutik.")

        return (True, None)

    def print_ticket(self, printer, ticket_data):
        """
        Construit les octets ESC/POS et les envoie via l'API Sunmi Cloud.
        / Builds ESC/POS bytes and sends them via the Sunmi Cloud API.
        """
        # Recuperer les credentials du tenant
        # / Get tenant credentials
        from laboutik.models import LaboutikConfiguration
        config = LaboutikConfiguration.get_solo()
        app_id = config.get_sunmi_app_id()
        app_key = config.get_sunmi_app_key()
        serial_number = printer.sunmi_serial_number

        # Construire les octets ESC/POS depuis le ticket_data
        # / Build ESC/POS bytes from ticket_data
        escpos_bytes = build_escpos_from_ticket_data(printer.dots_per_line, ticket_data)

        # Creer le client Sunmi Cloud pour l'envoi
        # / Create the Sunmi Cloud client for sending
        client = SunmiCloudPrinter(
            dots_per_line=printer.dots_per_line,
            app_id=app_id,
            app_key=app_key,
            printer_sn=serial_number,
        )

        # Charger les octets dans le buffer du client
        # (on n'utilise pas les methodes append* du client ici,
        # car le builder a deja construit les octets)
        # / Load bytes into the client buffer
        client.appendRawData(escpos_bytes)

        # Generer un trade_no unique (obligatoire, Sunmi deduplique sur ce champ)
        # / Generate a unique trade_no (mandatory, Sunmi deduplicates on this field)
        trade_no = f"{serial_number}_{uuid_module.uuid4().hex[:16]}"

        # Envoyer le ticket via l'API Sunmi Cloud
        # / Send the ticket via the Sunmi Cloud API
        try:
            client.pushContent(
                trade_no=trade_no,
                sn=serial_number,
                count=1,
            )
            logger.info(
                f"[PRINT] Sunmi Cloud OK — printer={printer.name} "
                f"trade_no={trade_no}"
            )
            return {"ok": True}
        except Exception as exc:
            error_message = f"Erreur API Sunmi Cloud : {exc}"
            logger.error(f"[PRINT] {error_message}")
            return {"ok": False, "error": error_message}

    def print_test(self, printer):
        """
        Imprime un ticket de test sur l'imprimante Sunmi Cloud.
        / Prints a test ticket on the Sunmi Cloud printer.
        """
        now = timezone.now()
        ticket_data = {
            "header": {
                "title": "TEST IMPRESSION",
                "subtitle": printer.name,
                "date": now.strftime("%d/%m/%Y %H:%M"),
            },
            "articles": [],
            "total": {},
            "qrcode": None,
            "footer": ["Impression de test OK"],
        }
        return self.print_ticket(printer, ticket_data)
