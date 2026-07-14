# Design Spec — Session 21 : Profils CSV comptables configurables

> **Date** : 2026-04-03
> **Depend de** : Session 20 (CompteComptable, MappingMoyenDePaiement, fec.py)
> **Scope** : Refactorisation ventilation, 5 profils CSV en dur, generateur CSV, boutons admin, 8 tests

---

## 1. Refactorisation : extraction de la ventilation

### Fichier : `laboutik/ventilation.py` (nouveau)

Logique comptable commune au FEC et aux profils CSV.
Aujourd'hui cette logique est dans `laboutik/fec.py` (parcours de rapport_json,
lookup mappings, generation lignes debit/credit). On l'extrait dans un module dedie.

Fonction principale :

```python
def ventiler_cloture(cloture, mappings_paiement, comptes_tva):
    """
    Extrait les lignes debit/credit d'une cloture a partir de son rapport_json.
    / Extracts debit/credit lines from a closure's rapport_json.

    :param cloture: ClotureCaisse instance
    :param mappings_paiement: dict {code: MappingMoyenDePaiement}
    :param comptes_tva: dict {"20.00": CompteComptable, ...}
    :return: tuple (list[dict], list[str] avertissements)

    Chaque dict dans la liste :
    {
        "sens": "D" ou "C",
        "numero_compte": str,
        "libelle_compte": str,
        "montant_centimes": int,
        "libelle_ecriture": str,
    }
    """
```

Fonctions utilitaires :

```python
def charger_mappings_paiement():
    """Charge tous les MappingMoyenDePaiement en memoire (dict code → obj)."""

def charger_comptes_tva():
    """Charge les CompteComptable de nature TVA (dict taux_str → obj)."""
```

### Impact sur fec.py

`laboutik/fec.py` est refactorise pour appeler `ventiler_cloture()` au lieu de
parcourir `rapport_json` directement. Le formatage FEC (18 colonnes, tab, CRLF)
reste dans `fec.py`.

---

## 2. Les 5 profils (en dur)

### Fichier : `laboutik/profils_csv.py` (nouveau)

Chaque profil est un dict Python avec la config de formatage :

```python
PROFILS = {
    'sage_50': {
        'nom': 'Sage 50',
        'separateur': ';',
        'decimal': '.',
        'format_date': '%d/%m/%Y',
        'entetes': False,
        'encodage': 'utf-8',
        'extension': '.csv',
        'mode_montant': 'DEBIT_CREDIT',  # 2 colonnes
        'colonnes': ['date', 'code_journal', 'numero_compte', 'numero_piece', 'libelle', 'debit', 'credit'],
    },
    'ebp': {
        'nom': 'EBP classique',
        'separateur': ',',
        'decimal': '.',
        'format_date': '%d%m%y',   # JJMMAA
        'entetes': False,
        'encodage': 'utf-8',
        'extension': '.txt',
        'mode_montant': 'MONTANT_SENS',  # 1 colonne montant + 1 colonne D/C
        'colonnes': ['numero_ligne', 'date', 'code_journal', 'numero_compte', 'libelle_auto', 'libelle', 'numero_piece', 'montant', 'sens', 'date_echeance'],
    },
    'dolibarr': {
        'nom': 'Dolibarr',
        'separateur': ',',
        'decimal': '.',      # PIEGE : point, pas virgule
        'format_date': '%Y-%m-%d',
        'entetes': True,
        'encodage': 'utf-8',
        'extension': '.csv',
        'mode_montant': 'DEBIT_CREDIT',
        'colonnes': ['numero_transaction', 'date', 'reference_piece', 'code_journal', 'numero_compte', 'compte_auxiliaire', 'libelle', 'debit', 'credit', 'libelle_compte'],
    },
    'paheko': {
        'nom': 'Paheko simplifie',
        'separateur': ';',
        'decimal': ',',
        'format_date': '%d/%m/%Y',
        'entetes': True,
        'encodage': 'utf-8',
        'extension': '.csv',
        'mode_montant': 'MONTANT_UNIQUE',  # 1 colonne montant + compte_debit/compte_credit
        'colonnes': ['numero_ecriture', 'date', 'compte_debit', 'compte_credit', 'montant', 'libelle', 'numero_piece', 'remarques'],
    },
    'pennylane': {
        'nom': 'PennyLane',
        'separateur': ';',
        'decimal': ',',
        'format_date': '%d/%m/%Y',
        'entetes': True,
        'encodage': 'utf-8',
        'extension': '.csv',
        'mode_montant': 'DEBIT_CREDIT',
        'colonnes': ['date', 'code_journal', 'numero_compte', 'libelle_compte', 'libelle', 'numero_piece', 'debit', 'credit'],
    },
}
```

---

## 3. Generateur CSV comptable

### Fichier : `laboutik/csv_comptable.py` (nouveau)

Fonction principale :

```python
def generer_csv_comptable(clotures_queryset, profil_nom, schema_name):
    """
    Genere un fichier CSV comptable selon le profil choisi.
    / Generates an accounting CSV file based on the chosen profile.

    :param clotures_queryset: QuerySet de ClotureCaisse
    :param profil_nom: str — cle dans PROFILS ('sage_50', 'ebp', etc.)
    :param schema_name: str — pour le nom du fichier
    :return: tuple (bytes contenu, str nom_fichier, list avertissements)
    """
```

Logique :
1. Recupere le profil depuis `PROFILS[profil_nom]`
2. Appelle `charger_mappings_paiement()` et `charger_comptes_tva()`
3. Pour chaque cloture : `ventiler_cloture()` → liste de lignes debit/credit
4. Pour chaque ligne : formater selon le profil (separateur, decimal, date, colonnes)
5. Assembler le fichier (BOM si encodage utf-8, en-tetes si profil.entetes)

### 3 modes de montant

**DEBIT_CREDIT** (Sage, Dolibarr, PennyLane) : 2 colonnes `debit` et `credit`.
Ligne debit → debit=montant, credit=0. Ligne credit → debit=0, credit=montant.

**MONTANT_SENS** (EBP) : 1 colonne `montant` + 1 colonne `sens` (D ou C).

**MONTANT_UNIQUE** (Paheko) : 1 colonne `montant` + `compte_debit` et `compte_credit`.
Ligne debit → compte_debit=numero, compte_credit=vide, montant=valeur.
Ligne credit → compte_debit=vide, compte_credit=numero, montant=valeur.

---

## 4. Export dans l'admin

### 4.1 Bandeau clotures (periode)

Ajouter un bouton "Export CSV comptable" dans `changelist_before.html` (a cote de
"Export fiscal" et "Export FEC"). Le bouton fait `hx-get` vers une action ViewSet
`export_csv_comptable` qui affiche un formulaire HTMX avec :
- Dates debut/fin (optionnelles)
- Dropdown profil (Sage 50, EBP, Dolibarr, Paheko, PennyLane)

### 4.2 Vue detail cloture

Ajouter un bouton "CSV compta" dans `rapport_before.html` (a cote de CSV/PDF/Excel/FEC).
Ce bouton ouvre un petit formulaire (juste le dropdown profil, pas de dates).
URL admin : `<object_id>/exporter-csv-comptable/?profil=sage_50`

### 4.3 Action ViewSet

Dans `CaisseViewSet`, action `export_csv_comptable` (GET + POST).
Template HTMX admin : `admin/cloture/export_csv_comptable_form.html`.

---

## 5. Tests

| Test | Verifie |
|------|---------|
| `test_ventiler_cloture_debits_credits` | Ventilation retourne debits + credits equilibres |
| `test_ventiler_cloture_cashless_4191` | Cashless mappe vers 4191 en debit |
| `test_csv_sage_separateur_point_virgule` | Sage 50 : `;` comme separateur |
| `test_csv_ebp_montant_sens` | EBP : colonne montant + sens D/C |
| `test_csv_dolibarr_decimal_point` | Dolibarr : `.` comme decimal |
| `test_csv_paheko_montant_unique` | Paheko : compte_debit/compte_credit + montant |
| `test_csv_pennylane_code_journal_lettres` | PennyLane : code journal = lettres |
| `test_fec_utilise_ventilation` | FEC refactorise appelle ventiler_cloture() |

---

## 6. Hors scope

- Modele ExportProfile en base (YAGNI — profils en dur suffisent)
- Profils custom editables par le gerant
- Import plan comptable depuis CSV
