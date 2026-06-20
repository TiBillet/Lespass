"""
Generateur de Fichier des Ecritures Comptables (FEC) — 18 colonnes.
Transforme les ClotureCaisse en fichier FEC conforme au format
impose par l'administration fiscale francaise (article A.47 A-1 du LPF).

/ FEC (Fichier des Ecritures Comptables) generator — 18 columns.
Transforms ClotureCaisse records into a FEC file compliant with the
French tax administration format (article A.47 A-1 of the LPF).

LOCALISATION : laboutik/fec.py
"""

import logging
from decimal import Decimal

from BaseBillet.models import Configuration
from laboutik.ventilation import (
    charger_mappings_paiement,
    charger_categories_par_nom,
    charger_comptes_tva,
    ventiler_cloture,
)

logger = logging.getLogger(__name__)


# --- En-tete FEC (18 colonnes) ---
# / FEC header (18 columns)
ENTETE_FEC = (
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
)


def _formater_montant(centimes):
    """
    Convertit un montant en centimes (int) en chaine FEC avec virgule.
    Exemples : 15000 → "150,00"   /   0 → "0,00"   /   1234 → "12,34"
    / Converts an amount in cents (int) to FEC string with comma.
    """
    # Utiliser Decimal pour eviter les erreurs d'arrondi float
    # / Use Decimal to avoid float rounding errors
    montant_decimal = Decimal(centimes) / Decimal(100)
    return f"{montant_decimal:.2f}".replace('.', ',')


def _formater_date(dt):
    """
    Formate un datetime en YYYYMMDD pour le FEC.
    Exemple : datetime(2026, 3, 31) → "20260331"
    / Formats a datetime as YYYYMMDD for FEC.
    """
    return dt.strftime("%Y%m%d")


def _generer_ligne_fec(
    journal_code,
    journal_lib,
    numero_ecriture,
    date_ecriture,
    numero_compte,
    libelle_compte,
    reference_piece,
    date_piece,
    libelle_ecriture,
    debit_centimes,
    credit_centimes,
    date_validation,
):
    """
    Genere une ligne FEC (18 champs separes par tabulation).
    Les colonnes 7, 8, 14, 15, 17, 18 sont toujours vides.
    / Generates a FEC line (18 tab-separated fields).
    Columns 7, 8, 14, 15, 17, 18 are always empty.
    """
    champs = [
        journal_code,                               # 1  JournalCode
        journal_lib,                                 # 2  JournalLib
        numero_ecriture,                             # 3  EcritureNum
        date_ecriture,                               # 4  EcritureDate
        numero_compte,                               # 5  CompteNum
        libelle_compte,                              # 6  CompteLib
        "",                                          # 7  CompAuxNum (vide)
        "",                                          # 8  CompAuxLib (vide)
        reference_piece,                             # 9  PieceRef
        date_piece,                                  # 10 PieceDate
        libelle_ecriture,                            # 11 EcritureLib
        _formater_montant(debit_centimes),           # 12 Debit
        _formater_montant(credit_centimes),          # 13 Credit
        "",                                          # 14 EcritureLet (vide)
        "",                                          # 15 DateLet (vide)
        date_validation,                             # 16 ValidDate
        "",                                          # 17 Montantdevise (vide)
        "",                                          # 18 Idevise (vide)
    ]
    return "\t".join(champs)


def generer_fec(clotures_queryset, schema_name):
    """
    Genere un fichier FEC a partir d'un QuerySet de ClotureCaisse.
    / Generates a FEC file from a ClotureCaisse QuerySet.

    :param clotures_queryset: QuerySet de ClotureCaisse, ordonne par date
    :param schema_name: str — nom du schema tenant (pour le nom de fichier)
    :return: tuple (bytes contenu_fec, str nom_fichier, list avertissements)
    """
    avertissements = []

    # --- Charger le SIREN depuis la configuration du tenant ---
    # / Load SIREN from tenant configuration
    try:
        configuration = Configuration.get_solo()
        siren = configuration.siren or ""
    except Exception:
        siren = ""

    if not siren:
        siren = schema_name.upper()
        avertissements.append(
            f"SIREN absent de la configuration. Utilisation de '{siren}' par defaut."
        )

    # --- Charger les mappings comptables en memoire (une seule fois) ---
    # / Load accounting mappings into memory (once)
    mappings_paiement = charger_mappings_paiement()
    categories_par_nom = charger_categories_par_nom()
    comptes_tva = charger_comptes_tva()

    # --- Construire les lignes FEC ---
    # / Build FEC lines
    lignes = []

    # Ligne d'en-tete / Header line
    lignes.append("\t".join(ENTETE_FEC))

    journal_code = "VE"
    journal_lib = "Journal de ventes"

    # Ordonner les clotures par date
    # / Order closures by date
    clotures = clotures_queryset.order_by('datetime_cloture')

    for seq, cloture in enumerate(clotures, start=1):
        date_cloture_str = _formater_date(cloture.datetime_cloture)
        numero_ecriture = f"VE-{date_cloture_str}-{seq:03d}"
        reference_piece = f"Z-{date_cloture_str}-{seq:03d}"

        # Ventiler la cloture via le module partage
        # / Break down the closure via the shared module
        lignes_ventilees, avertissements_cloture = ventiler_cloture(
            cloture, mappings_paiement, categories_par_nom, comptes_tva
        )
        avertissements.extend(avertissements_cloture)

        # Convertir chaque dict ventile en ligne FEC
        # / Convert each ventilated dict into a FEC line
        for ligne_dict in lignes_ventilees:
            if ligne_dict["sens"] == "D":
                debit_centimes = ligne_dict["montant_centimes"]
                credit_centimes = 0
            else:
                debit_centimes = 0
                credit_centimes = ligne_dict["montant_centimes"]

            ligne = _generer_ligne_fec(
                journal_code=journal_code,
                journal_lib=journal_lib,
                numero_ecriture=numero_ecriture,
                date_ecriture=date_cloture_str,
                numero_compte=ligne_dict["numero_compte"],
                libelle_compte=ligne_dict["libelle_compte"],
                reference_piece=reference_piece,
                date_piece=date_cloture_str,
                libelle_ecriture=ligne_dict["libelle_ecriture"],
                debit_centimes=debit_centimes,
                credit_centimes=credit_centimes,
                date_validation=date_cloture_str,
            )
            lignes.append(ligne)

    # --- Assembler le fichier FEC ---
    # Separateur de ligne : CRLF (norme FEC)
    # Encodage : UTF-8
    # / Assemble the FEC file — line separator: CRLF, encoding: UTF-8
    contenu_texte = "\r\n".join(lignes) + "\r\n"
    contenu_bytes = contenu_texte.encode("utf-8")

    # --- Nom du fichier : {SIREN}FEC{YYYYMMDD}.txt ---
    # Date = date de la derniere cloture du QuerySet
    # / Filename: {SIREN}FEC{YYYYMMDD}.txt — date = last closure date
    derniere_cloture = clotures.last()
    if derniere_cloture:
        date_fichier = _formater_date(derniere_cloture.datetime_cloture)
    else:
        # Queryset vide / Empty queryset
        from django.utils import timezone
        date_fichier = _formater_date(timezone.now())

    nom_fichier = f"{siren}FEC{date_fichier}.txt"

    return contenu_bytes, nom_fichier, avertissements
