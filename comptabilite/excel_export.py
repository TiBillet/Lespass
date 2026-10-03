"""
Export Excel (.xlsx) d'une clôture comptable.
/ Excel (.xlsx) export of an accounting closure.

LOCALISATION : comptabilite/excel_export.py

Le tableur écrit les sections du rapport stocké (`cloture.rapport_json`), préparées par
comptabilite/presentation.py `sections_pour_affichage` : les mêmes que la fiche de
l'admin, dans le même ordre, sur une seule feuille (« Rapport », traduit). Chaque
section a son titre (sur fond sombre), sa phrase, puis ses tableaux.
Les montants sont écrits en NOMBRES (en euros, format « 1 050,00 € ») : le trésorier
peut les additionner. Un texte qui commence par « = », « + », « - » ou « @ » est
écrit tel quel dans une case de type texte, avec le marqueur natif d'Excel
(`quotePrefix`) : il n'est jamais lu comme une formule. Le nom du fichier est
daté du jour de fin de la clôture, en heure du lieu.
/ The spreadsheet writes the stored report's sections; amounts are NUMBERS in euros;
texts are protected against formulas.

FLUX : comptabilite/admin.py `exporter_excel` → `generer_excel_cloture`.
"""
import io

from django.utils.translation import gettext
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from comptabilite.presentation import (
    nom_du_fichier_de_la_cloture,
    sections_pour_affichage,
    commence_comme_une_formule,
)


# Styles reutilises (definis au niveau module : crees une seule fois).
# / Reusable styles defined at module level (created once).
_POLICE_DU_TITRE = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
_FOND_DU_TITRE = PatternFill("solid", fgColor="333333")
_POLICE_D_UNE_SECTION = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_FOND_D_UNE_SECTION = PatternFill("solid", fgColor="333333")
_POLICE_D_UN_SOUS_TITRE = Font(name="Calibri", size=10, bold=True)
_POLICE_D_UNE_ALERTE = Font(name="Calibri", size=10, bold=True, color="B91C1C")
_POLICE_DES_COLONNES = Font(name="Calibri", size=10, bold=True)
_FOND_DES_COLONNES = PatternFill("solid", fgColor="F0F0F0")
_ALIGNEMENT_A_DROITE = Alignment(horizontal="right")
_BORDURE_FINE = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)

# Le format d'un montant en euros dans le tableur : deux décimales, « € » après.
# / The number format of an amount in euros.
_FORMAT_DES_EUROS = '#,##0.00 "€"'

# Le nombre de colonnes d'un titre de section (le plus large tableau du rapport).
# / Number of columns of a section title (the widest table of the report).
_LARGEUR_D_UN_TITRE = 7


def _ecrire_un_texte(feuille, numero_de_ligne, numero_de_colonne, texte):
    """
    Écrit un texte dans une case, protégé contre les formules. Un texte qui commence
    comme une formule (« =1+1 ») est gardé tel quel, mais la case est déclarée
    « texte » et reçoit le marqueur natif d'Excel (`quotePrefix`, l'apostrophe que
    l'on tape devant « =1+1 ») : le tableur affiche « =1+1 » et ne calcule jamais rien.
    / Writes a text in a cell; a formula-like text is kept as is, the cell is typed as
    text and gets Excel's native quote prefix: never computed.
    """
    texte = str(texte)
    case = feuille.cell(row=numero_de_ligne, column=numero_de_colonne, value=texte)
    if commence_comme_une_formule(texte):
        # openpyxl prend un texte qui commence par « = » pour une formule : on le
        # redéclare en texte, APRÈS l'avoir écrit.
        # / openpyxl takes a leading "=" for a formula: the cell is retyped as text.
        case.data_type = "s"
        case.quotePrefix = True
    return case


def _ecrire_le_titre_d_une_section(feuille, numero_de_ligne, titre):
    """
    Écrit un titre de section sur une ligne fusionnée, fond sombre.
    / Writes a merged section title, dark background.
    """
    case_du_titre = _ecrire_un_texte(feuille, numero_de_ligne, 1, titre)
    case_du_titre.font = _POLICE_D_UNE_SECTION
    case_du_titre.fill = _FOND_D_UNE_SECTION
    feuille.merge_cells(
        start_row=numero_de_ligne,
        start_column=1,
        end_row=numero_de_ligne,
        end_column=_LARGEUR_D_UN_TITRE,
    )
    return numero_de_ligne + 1


def _ecrire_les_colonnes(feuille, numero_de_ligne, colonnes):
    """Écrit une ligne d'en-têtes de colonnes. / Writes a column header row."""
    numero_de_colonne = 1
    for colonne in colonnes:
        case_de_la_colonne = _ecrire_un_texte(
            feuille, numero_de_ligne, numero_de_colonne, colonne
        )
        case_de_la_colonne.font = _POLICE_DES_COLONNES
        case_de_la_colonne.fill = _FOND_DES_COLONNES
        case_de_la_colonne.border = _BORDURE_FINE
        numero_de_colonne += 1
    return numero_de_ligne + 1


def _ecrire_une_ligne_de_cellules(feuille, numero_de_ligne, cellules):
    """
    Écrit une ligne de cellules du rapport : la valeur (un nombre) quand la cellule en
    a une, sinon son texte (protégé contre les formules). Un montant reçoit le format
    des euros.
    / Writes a row of report cells: the number when there is one, otherwise the text.
    """
    numero_de_colonne = 1
    for cellule in cellules:
        if cellule["valeur"] is not None:
            case = feuille.cell(
                row=numero_de_ligne, column=numero_de_colonne, value=cellule["valeur"]
            )
            case.alignment = _ALIGNEMENT_A_DROITE
            if cellule["est_un_montant"]:
                case.number_format = _FORMAT_DES_EUROS
        else:
            case = _ecrire_un_texte(
                feuille, numero_de_ligne, numero_de_colonne, cellule["texte"]
            )
        case.border = _BORDURE_FINE
        numero_de_colonne += 1
    return numero_de_ligne + 1


def generer_excel_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export Excel.
    / Returns (bytes, filename, content_type) for the Excel export.
    """
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = gettext("Rapport")

    numero_de_ligne = 1

    # Le titre : numéro et niveau de la clôture, puis son empreinte.
    # / The title: closure number and level, then its fingerprint.
    feuille.merge_cells(
        start_row=numero_de_ligne,
        start_column=1,
        end_row=numero_de_ligne,
        end_column=_LARGEUR_D_UN_TITRE,
    )
    titre_de_la_feuille = gettext("Clôture n° %(numero)s — %(niveau)s") % {
        "numero": cloture.numero_sequentiel,
        "niveau": cloture.get_niveau_display(),
    }
    case_du_titre = _ecrire_un_texte(feuille, numero_de_ligne, 1, titre_de_la_feuille)
    case_du_titre.font = _POLICE_DU_TITRE
    case_du_titre.fill = _FOND_DU_TITRE
    numero_de_ligne += 1
    _ecrire_un_texte(feuille, numero_de_ligne, 1, gettext("Empreinte de la clôture"))
    _ecrire_un_texte(feuille, numero_de_ligne, 2, cloture.hmac_hash)
    numero_de_ligne += 2

    sections = sections_pour_affichage(cloture.rapport_json)
    for section in sections:
        numero_de_ligne = _ecrire_le_titre_d_une_section(
            feuille, numero_de_ligne, section["titre"]
        )
        if section["phrase"]:
            case_de_la_phrase = _ecrire_un_texte(
                feuille, numero_de_ligne, 1, section["phrase"]
            )
            if section["phrase_en_alerte"]:
                case_de_la_phrase.font = _POLICE_D_UNE_ALERTE
            numero_de_ligne += 1
        for tableau in section["tableaux"]:
            if tableau["titre"]:
                case_du_sous_titre = _ecrire_un_texte(
                    feuille, numero_de_ligne, 1, tableau["titre"]
                )
                if tableau["alerte"]:
                    case_du_sous_titre.font = _POLICE_D_UNE_ALERTE
                else:
                    case_du_sous_titre.font = _POLICE_D_UN_SOUS_TITRE
                numero_de_ligne += 1
            if tableau["message_d_alerte"]:
                case_de_l_alerte = _ecrire_un_texte(
                    feuille, numero_de_ligne, 1, tableau["message_d_alerte"]
                )
                case_de_l_alerte.font = _POLICE_D_UNE_ALERTE
                numero_de_ligne += 1
            numero_de_ligne = _ecrire_les_colonnes(
                feuille, numero_de_ligne, tableau["colonnes"]
            )
            for ligne in tableau["lignes"]:
                numero_de_ligne = _ecrire_une_ligne_de_cellules(
                    feuille, numero_de_ligne, ligne
                )
        numero_de_ligne += 1

    # Largeurs de colonnes : la 1re large (libellés), les suivantes plus étroites.
    # / Column widths: the first wide (labels), the next ones narrower.
    feuille.column_dimensions[get_column_letter(1)].width = 40
    for numero_de_colonne in range(2, _LARGEUR_D_UN_TITRE + 1):
        feuille.column_dimensions[get_column_letter(numero_de_colonne)].width = 18

    tampon_du_classeur = io.BytesIO()
    classeur.save(tampon_du_classeur)

    nom_du_fichier = nom_du_fichier_de_la_cloture(cloture, "xlsx")
    type_du_contenu = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return tampon_du_classeur.getvalue(), nom_du_fichier, type_du_contenu
