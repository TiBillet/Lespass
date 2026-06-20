"""
Backend d'impression Mock — construit les MEMES donnees ESC/POS que les vrais
backends (Cloud, LAN), puis les decode en texte lisible pour la console Celery.
/ Mock printing backend — builds the SAME ESC/POS data as real backends
(Cloud, LAN), then decodes it to readable text for the Celery console.

LOCALISATION : laboutik/printing/mock.py

FLUX :
1. can_print() retourne toujours True
2. print_ticket() appelle build_escpos_from_ticket_data() (meme que Cloud/LAN)
3. Decode les bytes ESC/POS en texte lisible (supprime les codes de controle)
4. Affiche le resultat dans la console Celery avec un cadre ASCII

Le mock est un vrai test end-to-end du builder ESC/POS :
si le texte est lisible dans la console, il sera lisible sur l'imprimante.
/ The mock is a real end-to-end test of the ESC/POS builder:
if the text is readable in the console, it will be readable on the printer.
"""
import logging

from laboutik.printing.base import PrinterBackend
from laboutik.printing.escpos_builder import build_escpos_from_ticket_data

logger = logging.getLogger(__name__)


def _decode_escpos_to_text(escpos_bytes):
    """
    Decode des bytes ESC/POS en texte lisible.
    Supprime les sequences de controle ESC/POS (ESC, GS, LF, etc.)
    et extrait uniquement le texte UTF-8 imprimable.
    / Decodes ESC/POS bytes to readable text.
    Strips ESC/POS control sequences (ESC, GS, LF, etc.)
    and extracts only printable UTF-8 text.

    LOCALISATION : laboutik/printing/mock.py

    :param escpos_bytes: bytes ESC/POS bruts
    :return: liste de lignes de texte (str)
    """
    lignes = []
    ligne_courante = ""
    position = 0
    taille = len(escpos_bytes)

    while position < taille:
        octet = escpos_bytes[position]

        # --- LF (0x0A) : saut de ligne ---
        # / LF (0x0A): line feed
        if octet == 0x0A:
            lignes.append(ligne_courante)
            ligne_courante = ""
            position += 1
            continue

        # --- ESC (0x1B) : sequence de controle ESC ---
        # On saute la sequence entiere selon la commande.
        # / ESC (0x1B): ESC control sequence — skip the whole sequence.
        if octet == 0x1B:
            if position + 1 < taille:
                commande = escpos_bytes[position + 1]
                if commande == 0x40:
                    # ESC @ : reset (2 octets)
                    position += 2
                elif commande == 0x21:
                    # ESC ! : modes d'impression (3 octets)
                    position += 3
                elif commande == 0x61:
                    # ESC a : alignement (3 octets)
                    position += 3
                elif commande == 0x33:
                    # ESC 3 : interligne (3 octets)
                    position += 3
                elif commande == 0x32:
                    # ESC 2 : interligne defaut (2 octets)
                    position += 2
                elif commande == 0x24:
                    # ESC $ : position absolue (4 octets)
                    position += 4
                elif commande == 0x5C:
                    # ESC \ : position relative (4 octets)
                    position += 4
                elif commande == 0x2D:
                    # ESC - : souligne (3 octets)
                    position += 3
                elif commande == 0x7B:
                    # ESC { : mode renverse (3 octets)
                    position += 3
                elif commande == 0x54:
                    # ESC T : direction page mode (3 octets)
                    position += 3
                elif commande == 0x57:
                    # ESC W : zone impression page mode (10 octets)
                    position += 10
                elif commande == 0x4C:
                    # ESC L : entrer page mode (2 octets)
                    position += 2
                elif commande == 0x53:
                    # ESC S : sortir page mode (2 octets)
                    position += 2
                elif commande == 0x0C:
                    # ESC FF : imprimer en page mode (2 octets)
                    position += 2
                else:
                    # Commande ESC inconnue — sauter 2 octets
                    # / Unknown ESC command — skip 2 bytes
                    position += 2
            else:
                position += 1
            continue

        # --- GS (0x1D) : sequence de controle GS ---
        # / GS (0x1D): GS control sequence
        if octet == 0x1D:
            if position + 1 < taille:
                commande = escpos_bytes[position + 1]
                if commande == 0x21:
                    # GS ! : taille caracteres (3 octets)
                    position += 3
                elif commande == 0x42:
                    # GS B : mode inverse (3 octets)
                    position += 3
                elif commande == 0x56:
                    # GS V : coupe papier (3 ou 4 octets)
                    if position + 2 < taille:
                        sous_commande = escpos_bytes[position + 2]
                        if sous_commande in (0x61, 0x62):
                            # Coupe differee (4 octets)
                            position += 4
                        else:
                            # Coupe simple (3 octets)
                            position += 3
                            # Ajouter un marqueur visuel de coupe
                            # / Add a visual cut marker
                            lignes.append(ligne_courante)
                            ligne_courante = ""
                            lignes.append("✂ — — — — — — — — — — —")
                    else:
                        position += 3
                elif commande == 0x48:
                    # GS H : position HRI barcode (3 octets)
                    position += 3
                elif commande == 0x66:
                    # GS f : police HRI (3 octets)
                    position += 3
                elif commande == 0x68:
                    # GS h : hauteur barcode (3 octets)
                    position += 3
                elif commande == 0x77:
                    # GS w : largeur module barcode (3 octets)
                    position += 3
                elif commande == 0x6B:
                    # GS k : donnees barcode — sauter type + longueur + contenu
                    # / GS k: barcode data — skip type + length + content
                    if position + 3 < taille:
                        longueur_barcode = escpos_bytes[position + 3]
                        lignes.append(ligne_courante)
                        ligne_courante = ""
                        contenu_barcode = escpos_bytes[position + 4:position + 4 + longueur_barcode]
                        lignes.append(f"[BARCODE: {contenu_barcode.decode('utf-8', errors='replace')}]")
                        position += 4 + longueur_barcode
                    else:
                        position += 3
                elif commande == 0x28:
                    # GS ( : commande etendue — lire la longueur sur 2 octets
                    # / GS (: extended command — read 2-byte length
                    if position + 4 < taille:
                        sous_type = escpos_bytes[position + 2]
                        longueur = escpos_bytes[position + 3] + (escpos_bytes[position + 4] << 8)

                        # GS ( k : QR code — extraire le contenu
                        # / GS ( k: QR code — extract content
                        if sous_type == 0x6B:
                            # Les donnees QR sont dans le bloc "store data" (fn=80, 0x50)
                            if longueur >= 3 and position + 5 + longueur <= taille:
                                bloc = escpos_bytes[position + 5:position + 5 + longueur]
                                # Le bloc "store data" a le format : cn=49 fn=80 m=48 + data
                                if len(bloc) >= 3 and bloc[1] == 0x50:
                                    qr_data = bloc[3:]
                                    qr_texte = qr_data.decode('utf-8', errors='replace')
                                    lignes.append(ligne_courante)
                                    ligne_courante = ""
                                    lignes.append(f"[QR CODE: {qr_texte}]")

                        position += 5 + longueur
                    else:
                        position += 3
                elif commande == 0x24:
                    # GS $ : position verticale page mode (4 octets)
                    position += 4
                elif commande == 0x5C:
                    # GS \ : position verticale relative page mode (4 octets)
                    position += 4
                else:
                    # Commande GS inconnue — sauter 2 octets
                    # / Unknown GS command — skip 2 bytes
                    position += 2
            else:
                position += 1
            continue

        # --- HT (0x09) : tabulation ---
        if octet == 0x09:
            ligne_courante += "    "
            position += 1
            continue

        # --- FF (0x0C) : saut de page ---
        if octet == 0x0C:
            lignes.append(ligne_courante)
            ligne_courante = ""
            position += 1
            continue

        # --- CAN (0x18) : effacer buffer ---
        if octet == 0x18:
            position += 1
            continue

        # --- Caractere imprimable ou UTF-8 multi-octets ---
        # / Printable character or multi-byte UTF-8
        if octet >= 0x20:
            # Determiner la longueur de la sequence UTF-8
            # / Determine UTF-8 sequence length
            if octet < 0x80:
                nb_octets = 1
            elif octet < 0xC0:
                # Continuation byte sans debut — sauter
                position += 1
                continue
            elif octet < 0xE0:
                nb_octets = 2
            elif octet < 0xF0:
                nb_octets = 3
            else:
                nb_octets = 4

            if position + nb_octets <= taille:
                try:
                    caractere = escpos_bytes[position:position + nb_octets].decode('utf-8')
                    ligne_courante += caractere
                except UnicodeDecodeError:
                    ligne_courante += "?"
            position += nb_octets
            continue

        # --- Autre octet de controle — ignorer ---
        # / Other control byte — skip
        position += 1

    # Derniere ligne si pas terminee par LF
    # / Last line if not terminated by LF
    if ligne_courante:
        lignes.append(ligne_courante)

    return lignes


def _format_ascii_ticket(lignes_decodees, largeur_caracteres):
    """
    Encadre les lignes decodees dans un cadre ASCII style ticket thermique.
    / Wraps decoded lines in an ASCII frame styled like a thermal ticket.

    LOCALISATION : laboutik/printing/mock.py

    :param lignes_decodees: liste de str (lignes de texte decodees de l'ESC/POS)
    :param largeur_caracteres: nombre de caracteres par ligne
    :return: str multi-lignes
    """
    largeur_interieure = largeur_caracteres - 4

    def bordure_haut():
        return "╔" + "═" * (largeur_caracteres - 2) + "╗"

    def bordure_bas():
        return "╚" + "═" * (largeur_caracteres - 2) + "╝"

    def ligne_texte(texte):
        # Tronquer si trop long
        if len(texte) > largeur_interieure:
            texte = texte[:largeur_interieure]
        return "║ " + texte.ljust(largeur_interieure) + " ║"

    resultat = [bordure_haut()]
    for ligne in lignes_decodees:
        # Ignorer les lignes vides consecutives (LF multiples)
        # / Skip consecutive empty lines (multiple LFs)
        if not ligne.strip():
            continue
        resultat.append(ligne_texte(ligne))
    resultat.append(bordure_bas())

    return "\n".join(resultat)


class MockBackend(PrinterBackend):
    """
    Backend mock pour le developpement et les tests.
    Passe par le MEME builder ESC/POS que les vrais backends (Cloud, LAN),
    puis decode les bytes pour afficher le ticket en texte lisible.
    / Mock backend for development and testing.
    Uses the SAME ESC/POS builder as real backends (Cloud, LAN),
    then decodes the bytes to display the ticket as readable text.

    LOCALISATION : laboutik/printing/mock.py

    Avantage : le mock valide le contenu exact du builder ESC/POS.
    Si le texte est lisible dans la console, il sera lisible sur l'imprimante.
    / Advantage: the mock validates the exact ESC/POS builder output.
    If the text is readable in the console, it will be readable on the printer.
    """

    def can_print(self, printer):
        """
        Toujours pret — pas besoin de materiel.
        / Always ready — no hardware needed.
        """
        return (True, None)

    def print_ticket(self, printer, ticket_data):
        """
        Construit les donnees ESC/POS (meme code que Cloud/LAN),
        decode les bytes, et affiche le resultat dans les logs.
        / Builds ESC/POS data (same code as Cloud/LAN),
        decodes the bytes, and displays the result in logs.
        """
        # 1. Construire les bytes ESC/POS — MEME chemin que les vrais backends
        # / Build ESC/POS bytes — SAME path as real backends
        escpos_bytes = build_escpos_from_ticket_data(printer.dots_per_line, ticket_data)

        # 2. Decoder les bytes ESC/POS en texte lisible
        # / Decode ESC/POS bytes to readable text
        lignes_decodees = _decode_escpos_to_text(escpos_bytes)

        # 3. Calculer la largeur en caracteres
        # En police standard ESC/POS : 1 caractere ASCII = 12 dots
        # / Calculate character width (standard ESC/POS: 1 ASCII char = 12 dots)
        largeur_caracteres = max(20, printer.dots_per_line // 12)

        # 4. Encadrer dans un cadre ASCII
        # / Wrap in ASCII frame
        ticket_ascii = _format_ascii_ticket(lignes_decodees, largeur_caracteres)

        # 5. Afficher les bytes bruts en hex (pour debug si besoin)
        # / Display raw hex bytes (for debugging if needed)
        taille_bytes = len(escpos_bytes)

        logger.info(
            f"\n[MOCK PRINTER] {printer.name} "
            f"({taille_bytes} bytes ESC/POS)\n"
            f"{ticket_ascii}\n"
        )

        return {"ok": True}

    def print_test(self, printer):
        """
        Imprime un ticket de test mock.
        / Prints a mock test ticket.
        """
        from django.utils import timezone
        now = timezone.now()
        ticket_data = {
            "header": {
                "title": "TEST MOCK",
                "subtitle": printer.name,
                "date": now.strftime("%d/%m/%Y %H:%M"),
            },
            "articles": [
                {"name": "Article test", "qty": 2, "price": 350, "total": 700},
                {"name": "Autre article", "qty": 1, "price": 150, "total": 150},
            ],
            "total": {
                "amount": 850,
                "label": "Especes",
            },
            "qrcode": "https://tibillet.org/test",
            "footer": ["Merci !"],
        }
        return self.print_ticket(printer, ticket_data)
