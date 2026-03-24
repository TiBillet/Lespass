# -*- coding: utf-8 -*-
"""
Bibliotheque ESC/POS pour imprimantes Sunmi Cloud.
Construit des donnees binaires ESC/POS (texte, QR code, barcode, colonnes)
et les envoie a l'API Sunmi Cloud via HTTPS avec signature HMAC SHA256.
/ ESC/POS library for Sunmi Cloud printers.
Builds ESC/POS binary data (text, QR code, barcode, columns)
and sends them to the Sunmi Cloud API via HTTPS with HMAC SHA256 signature.

LOCALISATION : laboutik/printing/sunmi_cloud_printer.py

Copie nettoyee de OLD_REPOS/LaBoutik/epsonprinter/sunmi_cloud_printer.py.
Supprime : numpy, PIL, images (diffuseDither, thresholdDither, convertToGray, appendImage).
Garde : HMAC, ESC/POS texte, QR code, barcode, colonnes, page mode.

FLUX D'UTILISATION :
1. Creer une instance SunmiCloudPrinter(dots_per_line, app_id, app_key, printer_sn)
2. Construire le ticket avec les methodes append* / set* / lineFeed / cutPaper
3. Envoyer avec pushContent(trade_no, sn, count)
4. Appeler clear() pour reinitialiser le buffer
"""
import hashlib
import hmac
import json
import logging
import random
import time

import requests

logger = logging.getLogger(__name__)

# --- Constantes d'alignement ---
# / Alignment constants
ALIGN_LEFT: int = 0
ALIGN_CENTER: int = 1
ALIGN_RIGHT: int = 2

# --- Position du texte lisible sous le code-barres ---
# / Human-readable text position for barcodes
HRI_POS_ABOVE: int = 1
HRI_POS_BELOW: int = 2

# --- Flags pour l'impression en colonnes ---
# / Flags for column printing
COLUMN_FLAG_BW_REVERSE: int = 1 << 0
COLUMN_FLAG_BOLD: int = 1 << 1
COLUMN_FLAG_DOUBLE_H: int = 1 << 2
COLUMN_FLAG_DOUBLE_W: int = 1 << 3


def unicode_to_utf8(unicode_code_point: int) -> bytes:
    """
    Convertit un code point Unicode en octets UTF-8.
    Utilisee en interne pour appendUnicode().
    / Converts a Unicode code point to UTF-8 bytes.
    Used internally by appendUnicode().

    :param unicode_code_point: Code point Unicode (int)
    :return: Octets UTF-8
    """
    if unicode_code_point <= 0x7f:
        n = unicode_code_point & 0x7f
        return n.to_bytes(1, 'big')
    if 0x80 <= unicode_code_point <= 0x7ff:
        n = (((unicode_code_point >> 6) & 0x1f) | 0xc0) << 8
        n |= (((unicode_code_point) & 0x3f) | 0x80)
        return n.to_bytes(2, 'big')
    if 0x800 <= unicode_code_point <= 0xffff:
        n = (((unicode_code_point >> 12) & 0x0f) | 0xe0) << 16
        n |= (((unicode_code_point >> 6) & 0x3f) | 0x80) << 8
        n |= (((unicode_code_point) & 0x3f) | 0x80)
        return n.to_bytes(3, 'big')
    if 0x010000 <= unicode_code_point <= 0x10ffff:
        n = (((unicode_code_point >> 18) & 0x07) | 0xf0) << 24
        n |= (((unicode_code_point >> 12) & 0x3f) | 0x80) << 16
        n |= (((unicode_code_point >> 6) & 0x3f) | 0x80) << 8
        n |= (((unicode_code_point) & 0x3f) | 0x80)
        return n.to_bytes(4, 'big')
    return b''


class SunmiCloudPrinter:
    """
    Constructeur de donnees ESC/POS pour imprimantes Sunmi Cloud.
    Accumule les commandes dans un buffer binaire (_orderData),
    puis envoie le tout via pushContent() a l'API Sunmi Cloud.
    / ESC/POS data builder for Sunmi Cloud printers.
    Accumulates commands in a binary buffer (_orderData),
    then sends everything via pushContent() to the Sunmi Cloud API.

    LOCALISATION : laboutik/printing/sunmi_cloud_printer.py
    """

    def __init__(self, dots_per_line: int, app_id: str, app_key: str, printer_sn: str) -> None:
        """
        Initialise l'imprimante avec ses parametres de connexion.
        / Initializes the printer with its connection parameters.

        :param dots_per_line: Nombre de dots par ligne (384 pour 80mm, 240 pour 57mm)
        :param app_id: Identifiant de l'application Sunmi Cloud
        :param app_key: Cle de l'application Sunmi Cloud (pour la signature HMAC)
        :param printer_sn: Numero de serie de l'imprimante
        """
        self._DOTS_PER_LINE: int = dots_per_line
        self._charHSize: int = 1
        self._asciiCharWidth: int = 12
        self._cjkCharWidth: int = 24
        self._orderData: bytes = b''
        self._columnSettings: list = []

        self._app_id: str = app_id
        self._app_key: str = app_key
        self._printer_sn: str = printer_sn

        if not self._app_id or not self._app_key:
            raise ValueError(
                "app_id et app_key sont obligatoires. "
                "/ app_id and app_key are required."
            )
        if not self._printer_sn:
            raise ValueError(
                "printer_sn est obligatoire. "
                "/ printer_sn is required."
            )

        random.seed()

    @property
    def DOTS_PER_LINE(self) -> int:
        return self._DOTS_PER_LINE

    @property
    def orderData(self) -> bytes:
        return self._orderData

    def clear(self) -> None:
        """Reinitialise le buffer de donnees. / Resets the data buffer."""
        self._orderData = b''

    def widthOfChar(self, c: int) -> int:
        """
        Retourne la largeur en dots d'un caractere Unicode.
        Utilise en interne pour le calcul des colonnes.
        / Returns the width in dots of a Unicode character.
        Used internally for column width calculation.
        """
        if 0x00020 <= c <= 0x0036f:
            return self._asciiCharWidth
        if 0x0ff61 <= c <= 0x0ff9f:
            return self._cjkCharWidth // 2
        if (c == 0x02010) or \
           (0x02013 <= c <= 0x02016) or \
           (0x02018 <= c <= 0x02019) or \
           (0x0201c <= c <= 0x0201d) or \
           (0x02025 <= c <= 0x02026) or \
           (0x02030 <= c <= 0x02033) or \
           (c == 0x02035) or \
           (c == 0x0203b):
            return self._cjkCharWidth
        if (0x01100 <= c <= 0x011ff) or \
           (0x02460 <= c <= 0x024ff) or \
           (0x025a0 <= c <= 0x027bf) or \
           (0x02e80 <= c <= 0x02fdf) or \
           (0x03000 <= c <= 0x0318f) or \
           (0x031a0 <= c <= 0x031ef) or \
           (0x03200 <= c <= 0x09fff) or \
           (0x0ac00 <= c <= 0x0d7ff) or \
           (0x0f900 <= c <= 0x0faff) or \
           (0x0fe30 <= c <= 0x0fe4f) or \
           (0x1f000 <= c <= 0x1f9ff):
            return self._cjkCharWidth
        if (0x0ff01 <= c <= 0x0ff5e) or \
           (0x0ffe0 <= c <= 0x0ffe5):
            return self._cjkCharWidth
        return self._asciiCharWidth

    # --- Signature HMAC et envoi HTTP ---
    # / HMAC signature and HTTP sending

    def generateSign(self, body: str, timestamp: str, nonce: str) -> str:
        """
        Genere la signature HMAC SHA256 pour l'API Sunmi Cloud.
        / Generates the HMAC SHA256 signature for the Sunmi Cloud API.
        """
        msg: str = body + self._app_id + timestamp + nonce
        return hmac.new(
            key=self._app_key.encode('utf-8'),
            msg=msg.encode('utf-8'),
            digestmod=hashlib.sha256,
        ).hexdigest()

    def httpPost(self, path: str, body: dict) -> str:
        """
        Envoie une requete POST signee a l'API Sunmi Cloud.
        / Sends a signed POST request to the Sunmi Cloud API.

        :param path: Chemin de l'endpoint (ex: '/v2/printer/open/open/device/pushContent')
        :param body: Dictionnaire du corps de la requete
        :return: Texte de la reponse HTTP
        """
        url: str = 'https://openapi.sunmi.com' + path
        timestamp: str = str(int(time.time()))
        nonce: str = '{:06d}'.format(random.randint(0, 999999))
        body_data: str = json.dumps(obj=body, ensure_ascii=False)

        headers = {
            'Sunmi-Appid': self._app_id,
            'Sunmi-Timestamp': timestamp,
            'Sunmi-Nonce': nonce,
            'Sunmi-Sign': self.generateSign(body_data, timestamp, nonce),
            'Source': 'openapi',
            'Content-Type': 'application/json',
        }

        response = requests.post(url=url, data=body_data.encode('utf-8'), headers=headers)
        logger.info(f"[SUNMI] Reponse API : {response.text}")
        return response.text

    # --- Commandes de gestion de l'imprimante ---
    # / Printer management commands

    def bindShop(self, sn: str, shop_id: int) -> None:
        """Associe une imprimante a un magasin. / Binds a printer to a shop."""
        self.httpPost('/v2/printer/open/open/device/bindShop', {'sn': sn, 'shop_id': shop_id})

    def unbindShop(self, sn: str, shop_id: int) -> None:
        """Dissocie une imprimante d'un magasin. / Unbinds a printer from a shop."""
        self.httpPost('/v2/printer/open/open/device/unbindShop', {'sn': sn, 'shop_id': shop_id})

    def onlineStatus(self, sn: str) -> None:
        """Verifie le statut en ligne de l'imprimante. / Checks the printer's online status."""
        self.httpPost('/v2/printer/open/open/device/onlineStatus', {'sn': sn})

    def clearPrintJob(self, sn: str) -> None:
        """Annule tous les travaux d'impression en attente. / Clears all pending print jobs."""
        self.httpPost('/v2/printer/open/open/device/clearPrintJob', {'sn': sn})

    def pushVoice(self, sn: str, content: str, cycle: int = 1, interval: int = 2, expire_in: int = 300) -> None:
        """Envoie une notification vocale a l'imprimante. / Sends a voice notification to the printer."""
        body = {
            'sn': sn,
            'content': content,
            'cycle': cycle,
            'interval': interval,
            'expire_in': expire_in,
        }
        self.httpPost('/v2/printer/open/open/device/pushVoice', body)

    def pushContent(self, trade_no: str, sn: str, count: int, order_type: int = 1, media_text: str = '', cycle: int = 1) -> None:
        """
        Envoie le contenu du buffer a l'imprimante Sunmi Cloud.
        C'est la methode principale pour imprimer un ticket.
        / Sends the buffer content to the Sunmi Cloud printer.
        This is the main method to print a ticket.

        :param trade_no: Identifiant unique de la commande (pour le suivi)
        :param sn: Numero de serie de l'imprimante
        :param count: Nombre de copies
        :param order_type: Type de commande (1 = normal)
        :param media_text: Texte media (optionnel)
        :param cycle: Nombre de cycles (optionnel)
        """
        body = {
            'trade_no': trade_no,
            'sn': sn,
            'order_type': order_type,
            'content': self._orderData.hex(),
            'count': count,
            'media_text': media_text,
            'cycle': cycle,
        }
        self.httpPost('/v2/printer/open/open/device/pushContent', body)

    def printStatus(self, trade_no: str) -> None:
        """Verifie le statut d'un travail d'impression. / Checks a print job status."""
        self.httpPost('/v2/printer/open/open/ticket/printStatus', {'trade_no': trade_no})

    def newTicketNotify(self, sn: str) -> None:
        """Notifie l'imprimante d'un nouveau ticket. / Notifies the printer of a new ticket."""
        self.httpPost('/v2/printer/open/open/ticket/newTicketNotify', {'sn': sn})

    ##################################################
    # Commandes ESC/POS de base
    # / Basic ESC/POS Commands
    ##################################################

    def appendRawData(self, data: bytes) -> None:
        """Ajoute des donnees brutes au buffer. / Appends raw data to the buffer."""
        self._orderData += data

    def appendUnicode(self, unicode_code_point: int, count: int) -> None:
        """Ajoute un caractere Unicode repete N fois. / Appends a Unicode character repeated N times."""
        if count > 0:
            self._orderData += unicode_to_utf8(unicode_code_point) * count

    def appendText(self, text: str) -> None:
        """Ajoute du texte au buffer. / Appends text to the buffer."""
        self._orderData += text.encode(encoding='utf-8', errors='ignore')

    def lineFeed(self, n: int = 1) -> None:
        """[LF] Imprime le buffer et avance de N lignes. / Prints buffer and feeds N lines."""
        if n > 0:
            self._orderData += b'\x0a' * n

    def restoreDefaultSettings(self) -> None:
        """[ESC @] Restaure les parametres par defaut. / Restores default settings."""
        self._charHSize = 1
        self._orderData += b'\x1b\x40'

    def restoreDefaultLineSpacing(self) -> None:
        """[ESC 2] Restaure l'interligne par defaut. / Restores default line spacing."""
        self._orderData += b'\x1b\x32'

    def setLineSpacing(self, n: int) -> None:
        """[ESC 3] Definit l'interligne (0-255). / Sets line spacing (0-255)."""
        if 0 <= n <= 255:
            self._orderData += b'\x1b\x33' + n.to_bytes(1, 'little')

    def setPrintModes(self, bold: bool, double_h: bool, double_w: bool) -> None:
        """
        [ESC !] Definit les modes d'impression (gras, double hauteur, double largeur).
        / Sets print modes (bold, double height, double width).
        """
        n = 0
        if bold:
            n |= 8
        if double_h:
            n |= 16
        if double_w:
            n |= 32
            self._charHSize = 2
        else:
            self._charHSize = 1
        self._orderData += b'\x1b\x21' + n.to_bytes(1, 'little')

    def setCharacterSize(self, h: int, w: int) -> None:
        """[GS !] Definit la taille des caracteres (1-8). / Sets character size (1-8)."""
        n = 0
        if 1 <= h <= 8:
            n |= (h - 1)
        if 1 <= w <= 8:
            n |= (w - 1) << 4
            self._charHSize = w
        self._orderData += b'\x1d\x21' + n.to_bytes(1, 'little')

    def horizontalTab(self, n: int) -> None:
        """[HT] Insere N tabulations horizontales. / Inserts N horizontal tabs."""
        if n > 0:
            self._orderData += b'\x09' * n

    def setAbsolutePrintPosition(self, n: int) -> None:
        """[ESC $] Position absolue d'impression (0-65535). / Sets absolute print position."""
        if 0 <= n <= 65535:
            self._orderData += b'\x1b\x24' + n.to_bytes(2, 'little')

    def setRelativePrintPosition(self, n: int) -> None:
        """[ESC \\] Position relative d'impression. / Sets relative print position."""
        if -32768 <= n <= 32767:
            self._orderData += b'\x1b\x5c' + n.to_bytes(2, 'little')

    def setAlignment(self, n: int) -> None:
        """[ESC a] Alignement (0=gauche, 1=centre, 2=droite). / Sets alignment (0=left, 1=center, 2=right)."""
        if 0 <= n <= 2:
            self._orderData += b'\x1b\x61' + n.to_bytes(1, 'little')

    def setUnderlineMode(self, n: int) -> None:
        """[ESC -] Mode soulignement (0=off, 1=fin, 2=epais). / Sets underline mode."""
        if 0 <= n <= 2:
            self._orderData += b'\x1b\x2d' + n.to_bytes(1, 'little')

    def setBlackWhiteReverseMode(self, enabled: bool) -> None:
        """[GS B] Mode inverse noir/blanc. / Black-white reverse mode."""
        if enabled:
            self._orderData += b'\x1d\x42\x01'
        else:
            self._orderData += b'\x1d\x42\x00'

    def setUpsideDownMode(self, enabled: bool) -> None:
        """[ESC {] Mode impression renversee. / Upside down printing mode."""
        if enabled:
            self._orderData += b'\x1b\x7b\x01'
        else:
            self._orderData += b'\x1b\x7b\x00'

    def cutPaper(self, full_cut: bool) -> None:
        """[GS V m] Coupe le papier (complete ou partielle). / Cuts paper (full or partial)."""
        if full_cut:
            self._orderData += b'\x1d\x56\x30'
        else:
            self._orderData += b'\x1d\x56\x31'

    def postponedCutPaper(self, full_cut: bool, n: int) -> None:
        """
        [GS V m n] Coupe differee apres n lignes de dots supplementaires.
        / Postponed cut after n additional dot lines.
        """
        if 0 <= n <= 255:
            if full_cut:
                self._orderData += b'\x1d\x56\x61'
            else:
                self._orderData += b'\x1d\x56\x62'
            self._orderData += n.to_bytes(1, 'little')

    ##################################################
    # Commandes proprietaires Sunmi
    # / Sunmi Proprietary Commands
    ##################################################

    def setCjkEncoding(self, n: int) -> None:
        """
        Definit l'encodage CJK (actif quand UTF-8 est desactive).
        0=GB18030, 1=BIG5, 11=Shift_JIS, 21=KS C 5601, 128=desactive, 255=defaut.
        / Sets CJK encoding (effective when UTF-8 mode is disabled).
        """
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x01' + n.to_bytes(1, 'little')

    def setUtf8Mode(self, n: int) -> None:
        """Active/desactive le mode UTF-8 (0=off, 1=on, 255=defaut). / Sets UTF-8 mode."""
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x03' + n.to_bytes(1, 'little')

    def setHarfBuzzAsciiCharSize(self, n: int) -> None:
        """Definit la taille des caracteres latins en police vectorielle. / Sets Latin char size for vector font."""
        if 0 <= n <= 255:
            self._asciiCharWidth = n
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x0a' + n.to_bytes(1, 'little')

    def setHarfBuzzCjkCharSize(self, n: int) -> None:
        """Definit la taille des caracteres CJK en police vectorielle. / Sets CJK char size for vector font."""
        if 0 <= n <= 255:
            self._cjkCharWidth = n
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x0b' + n.to_bytes(1, 'little')

    def setHarfBuzzOtherCharSize(self, n: int) -> None:
        """Definit la taille des autres caracteres en police vectorielle. / Sets other char size for vector font."""
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x0c' + n.to_bytes(1, 'little')

    def selectAsciiCharFont(self, n: int) -> None:
        """
        Selectionne la police pour les caracteres latins.
        0=bitmap, 1=vectorielle, >=128=police custom.
        / Selects font for Latin characters.
        """
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x14' + n.to_bytes(1, 'little')

    def selectCjkCharFont(self, n: int) -> None:
        """Selectionne la police pour les caracteres CJK. / Selects font for CJK characters."""
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x15' + n.to_bytes(1, 'little')

    def selectOtherCharFont(self, n: int) -> None:
        """Selectionne la police pour les autres caracteres. / Selects font for other characters."""
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x16' + n.to_bytes(1, 'little')

    def setPrintDensity(self, n: int) -> None:
        """Definit la densite d'impression (0-255). / Sets print density."""
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x02\x00\x07' + n.to_bytes(1, 'little')

    def setPrintSpeed(self, n: int) -> None:
        """Definit la vitesse d'impression (0-255). / Sets print speed."""
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x02\x00\x08' + n.to_bytes(1, 'little')

    def setCutterMode(self, n: int) -> None:
        """
        Definit le mode de coupe.
        0=selon commande, 1=partielle toujours, 2=complete toujours, 3=jamais.
        / Sets cutter mode. 0=per command, 1=always partial, 2=always full, 3=never.
        """
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x02\x00\x10' + n.to_bytes(1, 'little')

    def clearPaperNotTakenAlarm(self) -> None:
        """Efface l'alarme 'papier non retire'. / Clears paper-not-taken alarm."""
        self._orderData += b'\x1d\x28\x54\x01\x00\x04'

    ##################################################
    # Impression en colonnes
    # / Column Printing
    ##################################################

    def setupColumns(self, columns: tuple) -> None:
        """
        Configure les colonnes pour printInColumns().
        Chaque colonne est un tuple (largeur_dots, alignement, flags).
        / Sets up columns for printInColumns().
        Each column is a tuple (width_dots, alignment, flags).

        :param columns: Tuple de tuples (width, alignment, flags)
        """
        self._columnSettings = []
        remain: int = self._DOTS_PER_LINE
        for col in columns:
            width: int = col[0]
            alignment: int = col[1]
            flag: int = col[2]
            if width == 0 or width > remain:
                width = remain
            self._columnSettings.append((width, alignment, flag))
            remain -= width
            if remain == 0:
                return

    def printInColumns(self, texts: tuple) -> None:
        """
        Imprime du texte en colonnes selon la configuration de setupColumns().
        Gere le retour a la ligne automatique si le texte depasse la largeur de la colonne.
        / Prints text in columns as configured by setupColumns().
        Handles automatic line wrapping if text exceeds column width.

        :param texts: Tuple de chaines de caracteres, une par colonne
        """
        if not self._columnSettings or not texts:
            return

        strcur: list = []
        strrem: list = []
        strwidth: list = []
        num_of_columns: int = min(len(self._columnSettings), len(texts))

        for i in range(num_of_columns):
            strcur.append('')
            strrem.append(texts[i])
            strwidth.append(0)

        while True:
            done = True
            pos = 0

            for i in range(num_of_columns):
                width = self._columnSettings[i][0]
                alignment = self._columnSettings[i][1]
                flag = self._columnSettings[i][2]

                if not strrem[i]:
                    pos += width
                    continue

                done = False
                strcur[i] = ''
                strwidth[i] = 0
                j = 0
                while j < len(strrem[i]):
                    c = ord(strrem[i][j])
                    if c == ord('\n'):
                        j += 1
                        break
                    else:
                        w = self.widthOfChar(c) * self._charHSize
                        if flag & COLUMN_FLAG_DOUBLE_W:
                            w *= 2
                        if strwidth[i] + w > width:
                            break
                        else:
                            strcur[i] += chr(c)
                            strwidth[i] += w
                    j += 1
                if j < len(strrem[i]):
                    strrem[i] = strrem[i][j:]
                else:
                    strrem[i] = ''

                if alignment == 1:
                    self.setAbsolutePrintPosition(pos + (width - strwidth[i]) // 2)
                elif alignment == 2:
                    self.setAbsolutePrintPosition(pos + (width - strwidth[i]))
                else:
                    self.setAbsolutePrintPosition(pos)
                if flag & COLUMN_FLAG_BW_REVERSE:
                    self.setBlackWhiteReverseMode(True)
                if flag & (COLUMN_FLAG_BOLD | COLUMN_FLAG_DOUBLE_H | COLUMN_FLAG_DOUBLE_W):
                    bold = True if flag & COLUMN_FLAG_BOLD else False
                    double_h = True if flag & COLUMN_FLAG_DOUBLE_H else False
                    double_w = True if flag & COLUMN_FLAG_DOUBLE_W else False
                    self.setPrintModes(bold, double_h, double_w)
                self.appendText(strcur[i])
                if flag & (COLUMN_FLAG_BOLD | COLUMN_FLAG_DOUBLE_H | COLUMN_FLAG_DOUBLE_W):
                    self.setPrintModes(False, False, False)
                if flag & COLUMN_FLAG_BW_REVERSE:
                    self.setBlackWhiteReverseMode(False)
                pos += width

            if not done:
                self.lineFeed()
            else:
                break

    ##################################################
    # Code-barres et QR code
    # / Barcode & QR Code
    ##################################################

    def appendBarcode(self, hri_pos: int, height: int, module_size: int, barcode_type: int, text: str) -> None:
        """
        Ajoute un code-barres au buffer.
        / Appends a barcode to the buffer.

        :param hri_pos: Position du texte lisible (HRI_POS_ABOVE ou HRI_POS_BELOW)
        :param height: Hauteur en dots (1-255)
        :param module_size: Taille du module (1-6)
        :param barcode_type: Type de code-barres (ex: 73 = Code128)
        :param text: Contenu du code-barres
        """
        text_length = len(text)

        if text_length == 0:
            return
        if text_length > 255:
            text_length = 255
        if height < 1:
            height = 1
        elif height > 255:
            height = 255
        if module_size < 1:
            module_size = 1
        elif module_size > 6:
            module_size = 6

        hri_pos &= 3

        self._orderData += b'\x1d\x48' + hri_pos.to_bytes(1, 'little')
        self._orderData += b'\x1d\x66\x00'
        self._orderData += b'\x1d\x68' + height.to_bytes(1, 'little')
        self._orderData += b'\x1d\x77' + module_size.to_bytes(1, 'little')
        self._orderData += b'\x1d\x6b' + barcode_type.to_bytes(1, 'little') + text_length.to_bytes(1, 'little')
        self._orderData += text.encode(encoding='utf-8', errors='ignore')

    def appendQRcode(self, module_size: int, ec_level: int, text: str) -> None:
        """
        Ajoute un QR code au buffer.
        / Appends a QR code to the buffer.

        :param module_size: Taille du module (1-16 dots)
        :param ec_level: Niveau de correction d'erreur (0=L, 1=M, 2=Q, 3=H)
        :param text: Contenu du QR code
        """
        content = text.encode(encoding='utf-8', errors='ignore')
        text_length = len(content)

        if text_length == 0:
            return
        if text_length > 65535:
            text_length = 65535
        if module_size < 1:
            module_size = 1
        elif module_size > 16:
            module_size = 16
        if ec_level < 0:
            ec_level = 0
        elif ec_level > 3:
            ec_level = 3

        ec_level += 48
        text_length += 3

        self._orderData += b'\x1d\x28\x6b\x04\x00\x31\x41\x00\x00'
        self._orderData += b'\x1d\x28\x6b\x03\x00\x31\x43' + module_size.to_bytes(1, 'little')
        self._orderData += b'\x1d\x28\x6b\x03\x00\x31\x45' + ec_level.to_bytes(1, 'little')
        self._orderData += b'\x1d\x28\x6b' + text_length.to_bytes(2, 'little') + b'\x31\x50\x30'
        self._orderData += content
        self._orderData += b'\x1d\x28\x6b\x03\x00\x31\x51\x30'

    ##################################################
    # Commandes du mode page
    # / Page Mode Commands
    ##################################################

    def enterPageMode(self) -> None:
        """[ESC L] Entre en mode page. / Enters page mode."""
        self._orderData += b'\x1b\x4c'

    def setPrintAreaInPageMode(self, x: int, y: int, w: int, h: int) -> None:
        """
        [ESC W] Definit la zone d'impression en mode page.
        / Sets the print area in page mode.

        :param x: Origine X de la zone
        :param y: Origine Y de la zone
        :param w: Largeur de la zone
        :param h: Hauteur de la zone
        """
        self._orderData += b'\x1b\x57'
        self._orderData += x.to_bytes(2, 'little')
        self._orderData += y.to_bytes(2, 'little')
        self._orderData += w.to_bytes(2, 'little')
        self._orderData += h.to_bytes(2, 'little')

    def setPrintDirectionInPageMode(self, direction: int) -> None:
        """
        [ESC T] Direction d'impression en mode page.
        0=normal, 1=90 degres, 2=180 degres, 3=270 degres.
        / Print direction in page mode. 0=normal, 1=90deg, 2=180deg, 3=270deg.
        """
        if 0 <= direction <= 3:
            self._orderData += b'\x1b\x54' + direction.to_bytes(1, 'little')

    def setAbsoluteVerticalPrintPositionInPageMode(self, n: int) -> None:
        """[GS $] Position verticale absolue en mode page. / Absolute vertical position in page mode."""
        if 0 <= n <= 65535:
            self._orderData += b'\x1d\x24' + n.to_bytes(2, 'little')

    def setRelativeVerticalPrintPositionInPageMode(self, n: int) -> None:
        """[GS \\] Position verticale relative en mode page. / Relative vertical position in page mode."""
        if -32768 <= n <= 32767:
            self._orderData += b'\x1d\x5c' + n.to_bytes(2, 'little')

    def printAndExitPageMode(self) -> None:
        """[FF] Imprime le buffer et sort du mode page. / Prints buffer and exits page mode."""
        self._orderData += b'\x0c'

    def printInPageMode(self) -> None:
        """[ESC FF] Imprime le buffer (reste en mode page). / Prints buffer (stays in page mode)."""
        self._orderData += b'\x1b\x0c'

    def clearInPageMode(self) -> None:
        """[CAN] Efface le buffer (reste en mode page). / Clears buffer (stays in page mode)."""
        self._orderData += b'\x18'

    def exitPageMode(self) -> None:
        """[ESC S] Sort du mode page sans imprimer. / Exits page mode without printing."""
        self._orderData += b'\x1b\x53'
