"""
Export FEC (Fichier des Écritures Comptables) d'une clôture.
/ FEC export (French legal accounting file) of a closure.

LOCALISATION : comptabilite/fec.py

LE FICHIER (article A47 A-1 du Livre des procédures fiscales)
Texte tabulé, 18 colonnes, encodage UTF-8 sans BOM, lignes séparées par CRLF. Une ligne
d'en-tête (les noms des colonnes), puis une ligne par compte de chaque écriture.
Montants avec une virgule décimale (« 12,34 »).

LES ÉCRITURES
Elles viennent de `ecritures_de_l_export` (comptabilite/ventilation.py), qui porte
leurs règles. Le FEC est le seul export comptable du lieu : tout logiciel comptable
(Sage, EBP, PennyLane, Paheko, Odoo…) l'importe.
- Le FEC n'est produit que par les clôtures J : une écriture par journal, équilibrée.
- Une semaine, un mois, une année (H / M / A) n'ont pas d'écriture propre : leur FEC
  est la suite des écritures des J DATÉES dans la période, dans l'ordre des numéros.
  Le FEC fait foi par J.
- La date d'une écriture (`EcritureDate`, `PieceDate`, `ValidDate`) est la date de
  début de service de sa J : la date locale de la première vente de la J, dans le
  fuseau figé dans l'en-tête de son rapport. Une J du 31 à 22 h au 1ᵉʳ à 2 h est
  datée du 31, et va dans le FEC du mois du 31.
- `EcritureNum` : « numéro de la J-code journal », un par journal et par J. Ce fichier
  est un fichier d'import pour le comptable du lieu. Le numéro est stable entre le
  FEC d'une J et celui de sa période, mais il n'est pas continu : le logiciel
  comptable renumérote les écritures à l'import.
- `PieceRef` : le numéro de la clôture J.
- Le nom du fichier porte une date locale : pour une J, sa date de début de service ;
  pour une H / M / A, son dernier jour, dans son fuseau.
- Le FEC est recalculé à chaque export, avec le plan comptable du moment : rien n'est
  figé dans la clôture. C'est le logiciel comptable du lieu qui fige les écritures
  qu'il importe.
- Un refus de la ventilation (`CompteComptableManquant`, `EcritureDesequilibree`)
  remonte : aucun fichier n'est produit. Un compte manquant est relevé avec le numéro
  de la J en cause (utile dans le FEC d'une période).
/ FEC built from the J entries only; a period = the entries of its dated J. Dated by
the start of service, in the time zone frozen in the J report. Recomputed at each
export. A refusal goes up: no file.

APPELÉE PAR : `comptabilite/admin.py` (`ClotureCaisseAdmin.exporter_fec`).

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§4).
Tests : tests/pytest/test_fec_equilibre.py
"""

from decimal import Decimal

from comptabilite.ventilation import ecritures_de_l_export
from laboutik.plan_comptable import s_assurer_que_le_plan_existe

# Les 18 colonnes obligatoires du FEC, dans l'ordre (article A47 A-1).
# / The 18 mandatory FEC columns, in order.
COLONNES_FEC = [
    "JournalCode",
    "JournalLib",
    "EcritureNum",
    "EcritureDate",
    "CompteNum",
    "CompteLib",
    "CompAuxNum",
    "CompAuxLib",
    "PieceRef",
    "PieceDate",
    "EcritureLib",
    "Debit",
    "Credit",
    "EcritureLet",
    "DateLet",
    "ValidDate",
    "Montantdevise",
    "Idevise",
]


def _montant_du_fec(centimes):
    """
    Des centimes entiers en montant du FEC : 1234 → « 12,34 », 0 → « 0,00 ».
    / Whole cents written the FEC way.
    """
    montant_en_euros = Decimal(centimes) / Decimal(100)
    return f"{montant_en_euros:.2f}".replace(".", ",")


def _ligne_fec(valeur_par_colonne):
    """
    Une ligne du FEC : les 18 colonnes séparées par des tabulations, vides si absentes.
    Une tabulation ou un saut de ligne dans une valeur casserait le format : ils
    deviennent des espaces.
    / One FEC line: the 18 tab-separated columns; tabs and newlines become spaces.
    """
    valeurs = []
    for colonne in COLONNES_FEC:
        valeur = str(valeur_par_colonne.get(colonne, ""))
        valeur = valeur.replace("\t", " ").replace("\r", " ").replace("\n", " ")
        valeurs.append(valeur)
    return "\t".join(valeurs)


def generer_fec_cloture(cloture):
    """
    Le FEC d'une clôture : ses écritures si c'est une J ; celles des J datées dans sa
    période si c'est une H, M ou A (`ecritures_de_l_export`).
    / The FEC of a closure: its entries for a J; its dated J's entries for H / M / A.

    :param cloture: une `ClotureCaisse`
    :return: (contenu en octets UTF-8, nom du fichier, type du contenu)
    :raises CompteComptableManquant: si un compte ou un journal manque
    :raises EcritureDesequilibree: si une écriture n'est pas équilibrée
    """
    # Le filet : un lieu qui n'a encore aucun compte reçoit le plan par défaut avant
    # son premier export.
    # / The safety net: a venue without any account gets the default plan first.
    s_assurer_que_le_plan_existe()

    export = ecritures_de_l_export(cloture)

    lignes_du_fichier = ["\t".join(COLONNES_FEC)]
    for ecriture in export["ecritures"]:
        date_de_l_ecriture = ecriture["date"].strftime("%Y%m%d")
        for ligne in ecriture["lignes"]:
            lignes_du_fichier.append(
                _ligne_fec(
                    {
                        "JournalCode": ecriture["journal"],
                        "JournalLib": ecriture["libelle_du_journal"],
                        "EcritureNum": ecriture["numero_d_ecriture"],
                        "EcritureDate": date_de_l_ecriture,
                        "CompteNum": ligne["compte"],
                        "CompteLib": ligne["libelle"],
                        "PieceRef": ecriture["piece"],
                        "PieceDate": date_de_l_ecriture,
                        "EcritureLib": ecriture["libelle"],
                        "Debit": _montant_du_fec(ligne["debit"]),
                        "Credit": _montant_du_fec(ligne["credit"]),
                        "ValidDate": date_de_l_ecriture,
                    }
                )
            )

    # UTF-8 sans BOM : l'encodage du FEC. Tout caractère d'un nom (point de vente,
    # compte) est gardé tel quel.
    # / UTF-8 without BOM: the FEC encoding. Every character is kept as is.
    contenu = "\r\n".join(lignes_du_fichier).encode("utf-8")

    date_du_nom_du_fichier = export["date_du_nom_du_fichier"]
    nom_du_fichier = (
        f"FEC-{date_du_nom_du_fichier:%Y%m%d}-{cloture.numero_sequentiel}.txt"
    )
    type_du_contenu = "text/plain; charset=utf-8"
    return contenu, nom_du_fichier, type_du_contenu
