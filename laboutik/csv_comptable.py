"""
Generateur d'export CSV comptable multi-profils.
Transforme les ClotureCaisse en fichier CSV adapte au logiciel
de comptabilite choisi (Sage, EBP, Dolibarr, Paheko, PennyLane).

/ Multi-profile CSV accounting export generator.
Transforms ClotureCaisse records into a CSV file adapted to the
chosen accounting software (Sage, EBP, Dolibarr, Paheko, PennyLane).

LOCALISATION : laboutik/csv_comptable.py
"""

import logging
from decimal import Decimal

from django.utils import timezone

from laboutik.profils_csv import PROFILS
from laboutik.ventilation import (
    charger_mappings_paiement,
    charger_categories_par_nom,
    charger_comptes_tva,
    ventiler_cloture,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------
# Fonctions utilitaires / Utility functions
# ---------------------------------------------------------------

def _formater_montant_csv(centimes, decimal_sep):
    """
    Convertit un montant en centimes (int) en chaine avec le separateur decimal voulu.
    Exemples : (15000, ',') → "150,00"   /   (15000, '.') → "150.00"
    / Converts an amount in cents (int) to string with the desired decimal separator.
    """
    montant_decimal = Decimal(centimes) / Decimal(100)
    chaine = f"{montant_decimal:.2f}"
    if decimal_sep != '.':
        chaine = chaine.replace('.', decimal_sep)
    return chaine


def _formater_date_csv(dt, format_str):
    """
    Formate un datetime selon le format du profil.
    Exemple : (datetime(2026, 3, 31), '%d/%m/%Y') → "31/03/2026"
    / Formats a datetime using the profile's date format.
    """
    return dt.strftime(format_str)


def _construire_ligne(ligne_ventilation, profil, metadata):
    """
    Construit une ligne CSV (list de str) a partir d'un dict de ventilation,
    du profil choisi, et des metadonnees de la cloture.

    / Builds a CSV row (list of str) from a ventilation dict,
    the chosen profile, and the closure metadata.

    :param ligne_ventilation: dict avec sens, numero_compte, libelle_compte,
                              montant_centimes, libelle_ecriture
    :param profil: dict du profil (depuis PROFILS)
    :param metadata: dict avec numero_ecriture, reference_piece, date_cloture,
                     code_journal, libelle_journal, numero_ligne
    :return: list[str] — valeurs des colonnes dans l'ordre du profil
    """
    sens = ligne_ventilation["sens"]
    montant_centimes = ligne_ventilation["montant_centimes"]
    decimal_sep = profil["decimal"]
    mode = profil["mode_montant"]

    # --- Calculer les valeurs dependantes du mode de montant ---
    # / Compute values that depend on the amount mode
    montant_formate = _formater_montant_csv(montant_centimes, decimal_sep)
    zero_formate = _formater_montant_csv(0, decimal_sep)

    if mode == "DEBIT_CREDIT":
        debit = montant_formate if sens == "D" else zero_formate
        credit = montant_formate if sens == "C" else zero_formate
    else:
        debit = ""
        credit = ""

    if mode == "MONTANT_SENS":
        montant_col = montant_formate
        sens_col = sens
    else:
        montant_col = ""
        sens_col = ""

    if mode == "MONTANT_UNIQUE":
        compte_debit = ligne_ventilation["numero_compte"] if sens == "D" else ""
        compte_credit = ligne_ventilation["numero_compte"] if sens == "C" else ""
        montant_col = montant_formate
    else:
        compte_debit = ""
        compte_credit = ""

    date_formatee = _formater_date_csv(metadata["date_cloture"], profil["format_date"])

    # --- Mapping colonne → valeur ---
    # Chaque nom de colonne correspond a une valeur precalculee.
    # / Column name → value mapping. Each column name maps to a precomputed value.
    valeurs = {
        "date": date_formatee,
        "code_journal": metadata["code_journal"],
        "numero_compte": ligne_ventilation["numero_compte"],
        "libelle_compte": ligne_ventilation["libelle_compte"],
        "libelle": ligne_ventilation["libelle_ecriture"],
        "numero_piece": metadata["reference_piece"],
        "reference_piece": metadata["reference_piece"],
        "numero_ecriture": metadata["numero_ecriture"],
        "numero_transaction": metadata["numero_ecriture"],
        "debit": debit,
        "credit": credit,
        "montant": montant_col,
        "sens": sens_col,
        "compte_debit": compte_debit,
        "compte_credit": compte_credit,
        # Colonnes toujours vides / Always-empty columns
        "libelle_auto": "",
        "date_echeance": "",
        "compte_auxiliaire": "",
        "remarques": "",
        # Compteur global / Global counter
        "numero_ligne": str(metadata["numero_ligne"]),
    }

    # Construire la ligne dans l'ordre des colonnes du profil
    # / Build the row in the profile's column order
    ligne = []
    for colonne in profil["colonnes"]:
        ligne.append(valeurs.get(colonne, ""))
    return ligne


# ---------------------------------------------------------------
# Fonction principale / Main function
# ---------------------------------------------------------------

def generer_csv_comptable(clotures_queryset, profil_nom, schema_name):
    """
    Genere un fichier CSV comptable a partir d'un QuerySet de ClotureCaisse.
    / Generates an accounting CSV file from a ClotureCaisse QuerySet.

    :param clotures_queryset: QuerySet de ClotureCaisse
    :param profil_nom: str — cle dans PROFILS ('sage_50', 'ebp', etc.)
    :param schema_name: str — nom du schema tenant (pour le nom de fichier)
    :return: tuple (bytes contenu, str nom_fichier, list avertissements)
    """
    # --- Valider le profil ---
    # / Validate the profile
    if profil_nom not in PROFILS:
        profils_disponibles = ", ".join(PROFILS.keys())
        raise ValueError(
            f"Profil '{profil_nom}' inconnu. "
            f"Profils disponibles : {profils_disponibles}"
        )

    profil = PROFILS[profil_nom]
    avertissements = []

    # --- Charger les mappings comptables en memoire (une seule fois) ---
    # / Load accounting mappings into memory (once)
    mappings_paiement = charger_mappings_paiement()
    categories_par_nom = charger_categories_par_nom()
    comptes_tva = charger_comptes_tva()

    # --- Construire les lignes ---
    # / Build lines
    lignes_csv = []
    separateur = profil["separateur"]

    # En-tete optionnel / Optional header
    if profil["entetes"]:
        lignes_csv.append(separateur.join(profil["colonnes"]))

    # Ordonner les clotures par date / Order closures by date
    clotures = clotures_queryset.order_by('datetime_cloture')

    # Compteur global de lignes (pour EBP numero_ligne)
    # / Global line counter (for EBP numero_ligne)
    compteur_global = 0

    for seq, cloture in enumerate(clotures, start=1):
        date_cloture_str = cloture.datetime_cloture.strftime("%Y%m%d")
        numero_ecriture = f"VE-{date_cloture_str}-{seq:03d}"
        reference_piece = f"Z-{date_cloture_str}-{seq:03d}"

        metadata = {
            "numero_ecriture": numero_ecriture,
            "reference_piece": reference_piece,
            "date_cloture": cloture.datetime_cloture,
            "code_journal": "VE",
            "libelle_journal": "Journal de ventes",
            "numero_ligne": 0,  # sera mis a jour par ligne / updated per line
        }

        # Ventiler la cloture / Break down the closure
        lignes_ventilees, avertissements_cloture = ventiler_cloture(
            cloture, mappings_paiement, categories_par_nom, comptes_tva
        )
        avertissements.extend(avertissements_cloture)

        # Convertir chaque dict ventile en ligne CSV
        # / Convert each ventilated dict into a CSV row
        for ligne_dict in lignes_ventilees:
            compteur_global += 1
            metadata["numero_ligne"] = compteur_global

            valeurs = _construire_ligne(ligne_dict, profil, metadata)
            lignes_csv.append(separateur.join(valeurs))

    # --- Assembler le fichier ---
    # / Assemble the file
    contenu_texte = "\n".join(lignes_csv) + "\n"
    contenu_bytes = contenu_texte.encode(profil["encodage"])

    # --- Nom du fichier ---
    # / Filename
    derniere_cloture = clotures.last()
    if derniere_cloture:
        date_fichier = derniere_cloture.datetime_cloture.strftime("%Y%m%d")
    else:
        date_fichier = timezone.now().strftime("%Y%m%d")

    extension = profil["extension"]
    nom_fichier = f"export_comptable_{profil_nom}_{schema_name}_{date_fichier}{extension}"

    return contenu_bytes, nom_fichier, avertissements
