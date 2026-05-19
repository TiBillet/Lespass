"""
Configuration des profils CSV comptables.
/ Configuration of accounting CSV profiles.

LOCALISATION : comptabilite/profils_csv.py

Chaque profil decrit le format CSV attendu par un logiciel comptable :
- separateur (; ou ,)
- decimal (. ou ,)
- encodage (utf-8-sig, cp1252, utf-8)
- mode_montant : DEBIT_CREDIT (2 colonnes), MONTANT_SENS (montant + D/C),
                 MONTANT_UNIQUE (montant + compte_debit + compte_credit)
- colonnes : liste ordonnee des colonnes du CSV
- format_date : strftime pattern
- extension : '.csv' ou '.txt'

S5 livre 3 profils : Sage 50, EBP, Paheko. S6 ajoutera Dolibarr, PennyLane,
CIEL, ODOO, DOKO.
/ S5 ships 3 profiles. S6 will add 5 more.
"""

PROFILS = {
    "sage_50": {
        "nom_affiche": "Sage 50",
        "separateur": ";",
        "decimal": ".",
        "encodage": "utf-8-sig",
        "mode_montant": "DEBIT_CREDIT",
        "format_date": "%d/%m/%Y",
        "colonnes": [
            "JournalCode", "EcritureDate", "CompteNum", "CompteLib",
            "PieceRef", "EcritureLib", "Debit", "Credit",
        ],
        "extension": ".csv",
    },
    "ebp": {
        "nom_affiche": "EBP Compta",
        "separateur": ",",
        "decimal": ".",
        "encodage": "cp1252",
        "mode_montant": "MONTANT_SENS",
        "format_date": "%d/%m/%Y",
        "colonnes": [
            "Date", "Journal", "Compte", "Libelle", "Montant", "Sens",
        ],
        "extension": ".txt",
    },
    "paheko": {
        "nom_affiche": "Paheko / Garradin",
        "separateur": ";",
        "decimal": ",",
        "encodage": "utf-8",
        "mode_montant": "MONTANT_UNIQUE",
        "format_date": "%Y-%m-%d",
        "colonnes": [
            "date", "libelle", "compte_debit", "compte_credit", "montant",
        ],
        "extension": ".csv",
    },
    "dolibarr": {
        "nom_affiche": "Dolibarr ERP",
        "separateur": ",",
        "decimal": ".",
        "encodage": "utf-8",
        "mode_montant": "DEBIT_CREDIT",
        "format_date": "%Y-%m-%d",
        "colonnes": [
            "code_journal", "date", "piece", "compte", "libelle_compte",
            "label_operation", "debit", "credit",
        ],
        "extension": ".csv",
    },
    "pennylane": {
        "nom_affiche": "PennyLane",
        "separateur": ";",
        "decimal": ",",
        "encodage": "utf-8",
        "mode_montant": "DEBIT_CREDIT",
        "format_date": "%d/%m/%Y",
        "colonnes": [
            "Journal", "Date", "Compte", "LibelleCompte",
            "Piece", "Libelle", "Debit", "Credit",
        ],
        "extension": ".csv",
    },
    "ciel": {
        "nom_affiche": "CIEL Compta",
        "separateur": "\t",
        "decimal": ",",
        "encodage": "cp1252",
        "mode_montant": "DEBIT_CREDIT",
        "format_date": "%d/%m/%Y",
        "colonnes": [
            "Journal", "Date", "Compte", "Libelle", "Piece", "Debit", "Credit",
        ],
        "extension": ".txt",
    },
    "odoo": {
        "nom_affiche": "Odoo",
        "separateur": ",",
        "decimal": ".",
        "encodage": "utf-8",
        "mode_montant": "DEBIT_CREDIT",
        "format_date": "%Y-%m-%d",
        "colonnes": [
            "journal_id", "date", "account_id", "name", "ref", "debit", "credit",
        ],
        "extension": ".csv",
    },
    "doko": {
        "nom_affiche": "DOKO",
        "separateur": ";",
        "decimal": ",",
        "encodage": "utf-8",
        "mode_montant": "DEBIT_CREDIT",
        "format_date": "%d/%m/%Y",
        "colonnes": [
            "JournalCode", "EcritureDate", "CompteNum", "CompteLib",
            "PieceRef", "EcritureLib", "Debit", "Credit",
        ],
        "extension": ".csv",
    },
}
