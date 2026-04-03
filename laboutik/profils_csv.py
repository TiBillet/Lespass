"""
Profils d'export CSV comptable — configuration par logiciel de comptabilite.

Chaque profil decrit le format attendu par un logiciel cible :
separateur, format de date, colonnes, encodage, et mode de gestion
des montants (debit/credit, montant+sens, ou montant unique).

/ CSV accounting export profiles — configuration per accounting software.
Each profile describes the format expected by a target software:
separator, date format, columns, encoding, and amount mode
(debit/credit, amount+direction, or single amount).

LOCALISATION : laboutik/profils_csv.py
"""


# --- Modes de montant ---
# DEBIT_CREDIT : deux colonnes separees (debit, credit)
# MONTANT_SENS : une colonne montant + une colonne sens (D/C)
# MONTANT_UNIQUE : une colonne montant + deux colonnes compte_debit / compte_credit
#
# / Amount modes:
# DEBIT_CREDIT: two separate columns (debit, credit)
# MONTANT_SENS: one amount column + one direction column (D/C)
# MONTANT_UNIQUE: one amount column + two account columns (debit / credit)


PROFILS = {
    'sage_50': {
        'nom': 'Sage 50',
        'description': 'Import Sage 50 / Sage 100 — point-virgule, decimal point, sans en-tetes',
        'separateur': ';',
        'decimal': '.',
        'format_date': '%d/%m/%Y',
        'entetes': False,
        'encodage': 'utf-8',
        'extension': '.csv',
        'mode_montant': 'DEBIT_CREDIT',
        'colonnes': [
            'date',
            'code_journal',
            'numero_compte',
            'numero_piece',
            'libelle',
            'debit',
            'credit',
        ],
    },
    'ebp': {
        'nom': 'EBP classique',
        'description': 'EBP Compta Classic — virgule, decimal point, montant + sens D/C',
        'separateur': ',',
        'decimal': '.',
        'format_date': '%d%m%y',
        'entetes': False,
        'encodage': 'utf-8',
        'extension': '.txt',
        'mode_montant': 'MONTANT_SENS',
        'colonnes': [
            'numero_ligne',
            'date',
            'code_journal',
            'numero_compte',
            'libelle_auto',
            'libelle',
            'numero_piece',
            'montant',
            'sens',
            'date_echeance',
        ],
    },
    'dolibarr': {
        'nom': 'Dolibarr',
        'description': 'Dolibarr ERP — virgule, decimal POINT (attention), format ISO',
        'separateur': ',',
        'decimal': '.',
        'format_date': '%Y-%m-%d',
        'entetes': True,
        'encodage': 'utf-8',
        'extension': '.csv',
        'mode_montant': 'DEBIT_CREDIT',
        'colonnes': [
            'numero_transaction',
            'date',
            'reference_piece',
            'code_journal',
            'numero_compte',
            'compte_auxiliaire',
            'libelle',
            'debit',
            'credit',
            'libelle_compte',
        ],
    },
    'paheko': {
        'nom': 'Paheko simplifie',
        'description': 'Paheko (ex Garradin) — point-virgule, virgule decimale, compte debit/credit',
        'separateur': ';',
        'decimal': ',',
        'format_date': '%d/%m/%Y',
        'entetes': True,
        'encodage': 'utf-8',
        'extension': '.csv',
        'mode_montant': 'MONTANT_UNIQUE',
        'colonnes': [
            'numero_ecriture',
            'date',
            'compte_debit',
            'compte_credit',
            'montant',
            'libelle',
            'numero_piece',
            'remarques',
        ],
    },
    'pennylane': {
        'nom': 'PennyLane',
        'description': 'PennyLane — point-virgule, virgule decimale, code journal lettres uniquement',
        'separateur': ';',
        'decimal': ',',
        'format_date': '%d/%m/%Y',
        'entetes': True,
        'encodage': 'utf-8',
        'extension': '.csv',
        'mode_montant': 'DEBIT_CREDIT',
        'colonnes': [
            'date',
            'code_journal',
            'numero_compte',
            'libelle_compte',
            'libelle',
            'numero_piece',
            'debit',
            'credit',
        ],
    },
}
