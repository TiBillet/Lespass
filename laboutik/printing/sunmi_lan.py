"""
Backend d'impression Sunmi LAN (HTTP direct sur le reseau local).
Envoie les donnees ESC/POS directement a l'imprimante via HTTP POST,
sans authentification, sans passer par le cloud Sunmi.
/ Sunmi LAN printing backend (direct HTTP on local network).
Sends ESC/POS data directly to the printer via HTTP POST,
no authentication, no Sunmi cloud relay.

LOCALISATION : laboutik/printing/sunmi_lan.py

FLUX :
1. can_print() verifie que l'adresse IP est configuree
2. print_ticket() construit les octets ESC/POS via le builder factorise
3. Envoie les octets en hex via POST http://<ip>/cgi-bin/print.cgi

PREREQUIS :
- L'imprimante et le serveur doivent etre sur le meme sous-reseau
- Pas besoin de compte partenaire Sunmi ni de credentials
- Double-clic sur le bouton de couplage de l'imprimante pour connaitre son IP
"""
import logging

import requests
from django.utils import timezone

from laboutik.printing.base import PrinterBackend
from laboutik.printing.escpos_builder import build_escpos_from_ticket_data

logger = logging.getLogger(__name__)


class SunmiLanBackend(PrinterBackend):
    """
    Backend pour les imprimantes Sunmi en reseau local (type LN).
    Communique via HTTP POST direct sur l'IP de l'imprimante.
    Pas d'authentification, pas de signature HMAC.
    / Backend for Sunmi printers on local network (type LN).
    Communicates via direct HTTP POST to the printer's IP address.
    No authentication, no HMAC signature.

    LOCALISATION : laboutik/printing/sunmi_lan.py
    """

    def can_print(self, printer):
        """
        Verifie que l'adresse IP de l'imprimante est configuree.
        / Checks that the printer IP address is configured.
        """
        if not printer.ip_address:
            return (False, "Adresse IP manquante sur l'imprimante.")
        return (True, None)

    def print_ticket(self, printer, ticket_data):
        """
        Construit les octets ESC/POS et les envoie directement a l'imprimante
        via HTTP POST sur le reseau local.
        / Builds ESC/POS bytes and sends them directly to the printer
        via HTTP POST on the local network.
        """
        # Construire les octets ESC/POS depuis le ticket_data
        # / Build ESC/POS bytes from ticket_data
        escpos_bytes = build_escpos_from_ticket_data(printer.dots_per_line, ticket_data)

        # Envoyer les octets en hexadecimal a l'imprimante
        # / Send hex-encoded bytes to the printer
        url = f"http://{printer.ip_address}/cgi-bin/print.cgi"

        try:
            response = requests.post(
                url=url,
                data=escpos_bytes.hex(),
                timeout=10,
            )

            if response.status_code == 200:
                logger.info(
                    f"[PRINT] LAN OK — printer={printer.name} "
                    f"ip={printer.ip_address}"
                )
                return {"ok": True}
            else:
                error_message = (
                    f"Reponse HTTP {response.status_code} "
                    f"depuis {printer.ip_address}"
                )
                logger.error(f"[PRINT] LAN erreur — {error_message}")
                return {"ok": False, "error": error_message}

        except requests.ConnectionError:
            error_message = (
                f"Imprimante {printer.name} injoignable a {printer.ip_address}. "
                f"Verifier que l'imprimante est allumee et sur le meme sous-reseau."
            )
            logger.error(f"[PRINT] LAN connexion echouee — {error_message}")
            return {"ok": False, "error": error_message}

        except requests.Timeout:
            error_message = (
                f"Timeout apres 10s vers {printer.ip_address}."
            )
            logger.error(f"[PRINT] LAN timeout — {error_message}")
            return {"ok": False, "error": error_message}

        except Exception as exc:
            error_message = f"Erreur LAN : {exc}"
            logger.error(f"[PRINT] {error_message}")
            return {"ok": False, "error": error_message}

    def print_test(self, printer):
        """
        Imprime un ticket de test sur l'imprimante LAN.
        / Prints a test ticket on the LAN printer.
        """
        now = timezone.now()
        ticket_data = {
            "header": {
                "title": "TEST IMPRESSION LAN",
                "subtitle": printer.name,
                "date": now.strftime("%d/%m/%Y %H:%M"),
            },
            "articles": [],
            "total": {},
            "qrcode": None,
            "footer": [
                f"IP: {printer.ip_address}",
                "Impression de test OK",
            ],
        }
        return self.print_ticket(printer, ticket_data)
