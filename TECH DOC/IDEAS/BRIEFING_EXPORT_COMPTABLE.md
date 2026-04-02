# EXPORT COMPTABLE — Briefing agent Claude Code

> Ce document est un briefing pour un agent IA travaillant sur le code de LaBoutik.
> Il contient tout ce qu'il faut pour implémenter l'export des données de caisse
> vers les logiciels de comptabilité.

---

## Contexte métier

LaBoutik est un **logiciel de caisse + cashless NFC** (point de vente).
C'est une app Django, multi-tenant (django-tenants, schémas PostgreSQL).
Elle tourne sur des terminaux SUNMI et en navigateur.

**Le problème à résoudre** : les structures (assos, tiers-lieux, festivals)
qui utilisent LaBoutik doivent transmettre leurs données de vente à leur comptable.
Aujourd'hui c'est manuel. On veut générer des fichiers d'export que le comptable
peut **importer directement** dans son logiciel de comptabilité.

**Ce que LaBoutik produit déjà** : des tickets Z (clôtures journalières)
avec les totaux par moyen de paiement et par taux de TVA.

**Ce qu'on veut ajouter** : un système d'export qui transforme ces données Z
en écritures comptables importables par les logiciels du marché.

---

## Architecture cible

### Nouveau module : `laboutik/exports/`

```
laboutik/exports/
├── __init__.py
├── models.py          # ExportProfile, ExportHistory
├── generators.py      # Classe de base + un générateur par format
├── fec.py             # Générateur FEC (format pivot)
├── csv_configurable.py # Générateur CSV avec mapping configurable
├── views.py           # Vues d'export (admin + API)
├── serializers.py     # Sérialisation DRF
├── urls.py
└── templates/
    └── exports/
        └── partials/   # Fragments HTMX pour l'admin
```

### Deux exports à implémenter (par priorité)

**Priorité 1 — Export FEC (format pivot)**
Le FEC est un format figé, obligatoire en France, accepté nativement par :
PennyLane, Odoo, EBP Hubbix, Paheko, et via import paramétrable par Sage.
Un seul code = couvre 80% des cas.

**Priorité 2 — Export CSV configurable (profils)**
Pour les cabinets comptables avec leur propre format maison.
Profils pré-configurés : Sage 50, EBP classique, Dolibarr, Paheko simplifié.

---

## Priorité 1 — Format FEC : spécification exacte

### Caractéristiques techniques du fichier

| Paramètre            | Valeur                                               |
| -------------------- | ---------------------------------------------------- |
| Extension            | `.txt`                                               |
| Encodage             | UTF-8                                                |
| Séparateur de champs | Tabulation `\t`                                      |
| Séparateur décimal   | Virgule `,`                                          |
| Format de date       | AAAAMMJJ (ex: 20260331)                              |
| Fin de ligne         | `\r\n` (CRLF)                                        |
| Première ligne       | En-têtes des 18 colonnes                             |
| Nom du fichier       | `{SIREN}FEC{AAAAMMJJ}.txt` (date = clôture exercice) |

### Les 18 colonnes obligatoires

```
JournalCode    JournalLib    EcritureNum    EcritureDate    CompteNum    CompteLib    CompAuxNum    CompAuxLib    PieceRef    PieceDate    EcritureLib    Debit    Credit    EcritureLet    DateLet    ValidDate    Montantdevise    Idevise
```

Détail :

| #   | Nom           | Description                         | Obligatoire | Exemple                        |
| --- | ------------- | ----------------------------------- | ----------- | ------------------------------ |
| 1   | JournalCode   | Code du journal                     | ✅           | `VE`                           |
| 2   | JournalLib    | Libellé du journal                  | ✅           | `Journal de ventes`            |
| 3   | EcritureNum   | Numéro séquentiel de l'écriture     | ✅           | `VE-20260331-001`              |
| 4   | EcritureDate  | Date de l'écriture                  | ✅           | `20260331`                     |
| 5   | CompteNum     | Numéro de compte PCG                | ✅           | `707000`                       |
| 6   | CompteLib     | Libellé du compte                   | ✅           | `Ventes de marchandises`       |
| 7   | CompAuxNum    | Compte auxiliaire                   | ❌           | `` (vide si pas utilisé)       |
| 8   | CompAuxLib    | Libellé compte auxiliaire           | ❌           | ``                             |
| 9   | PieceRef      | Référence de la pièce justificative | ✅           | `Z-20260331-001`               |
| 10  | PieceDate     | Date de la pièce                    | ✅           | `20260331`                     |
| 11  | EcritureLib   | Libellé de l'écriture               | ✅           | `Ventes espèces du 31/03/2026` |
| 12  | Debit         | Montant au débit                    | ✅           | `0,00` ou `150,00`             |
| 13  | Credit        | Montant au crédit                   | ✅           | `150,00` ou `0,00`             |
| 14  | EcritureLet   | Lettrage                            | ❌           | ``                             |
| 15  | DateLet       | Date de lettrage                    | ❌           | ``                             |
| 16  | ValidDate     | Date de validation                  | ✅           | `20260331`                     |
| 17  | Montantdevise | Montant en devise étrangère         | ❌           | ``                             |
| 18  | Idevise       | Code devise ISO                     | ❌           | ``                             |

### Règles de validation FEC

- Chaque écriture (même EcritureNum) doit être **équilibrée** : somme des débits = somme des crédits.
- Les champs 7, 8, 14, 15, 17, 18 peuvent être vides mais la **colonne doit exister** (tabulation présente).
- Les montants sont en centimes formatés avec virgule : `150,00` (pas `150.00`).
- Les dates sont sans séparateur : `20260331` (pas `2026-03-31`).
- Le FEC est normalement trié par EcritureDate puis EcritureNum.

---

## Priorité 2 — Export CSV configurable : les profils cibles

### Modèle ExportProfile

```python
class ExportProfile(models.Model):
    """
    Profil d'export comptable configurable par lieu.
    Chaque lieu peut avoir un ou plusieurs profils.
    / Configurable accounting export profile per venue.

    LOCALISATION : laboutik/exports/models.py
    """
    # Identifiant unique du profil
    # / Unique profile identifier
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Nom lisible du profil (ex: "Sage 50 — Cabinet Martin")
    # / Human-readable profile name
    nom_du_profil = models.CharField(max_length=200)

    # Separateur de champs dans le fichier CSV
    # / Field separator character
    SEPARATEUR_CHOICES = [
        ('\t', 'Tabulation'),
        (';', 'Point-virgule'),
        (',', 'Virgule'),
        ('|', 'Pipe'),
    ]
    separateur_de_champs = models.CharField(
        max_length=2,
        choices=SEPARATEUR_CHOICES,
        default=';',
    )

    # Separateur decimal pour les montants
    # / Decimal separator for amounts
    DECIMAL_CHOICES = [
        (',', 'Virgule (1 234,56)'),
        ('.', 'Point (1234.56)'),
    ]
    separateur_decimal = models.CharField(
        max_length=1,
        choices=DECIMAL_CHOICES,
        default=',',
    )

    # Format de date dans le fichier
    # / Date format in the output file
    FORMAT_DATE_CHOICES = [
        ('AAAAMMJJ', 'AAAAMMJJ (20260331)'),
        ('JJ/MM/AAAA', 'JJ/MM/AAAA (31/03/2026)'),
        ('JJMMAA', 'JJMMAA (310326)'),
        ('AAAA-MM-JJ', 'AAAA-MM-JJ (2026-03-31)'),
    ]
    format_de_date = models.CharField(
        max_length=20,
        choices=FORMAT_DATE_CHOICES,
        default='JJ/MM/AAAA',
    )

    # Inclure une ligne d'en-tetes (noms de colonnes)
    # / Include a header row with column names
    inclure_les_entetes = models.BooleanField(default=True)

    # Encodage du fichier
    # / File encoding
    ENCODAGE_CHOICES = [
        ('utf-8', 'UTF-8'),
        ('iso-8859-1', 'ISO-8859-1 (Latin-1)'),
        ('cp1252', 'Windows-1252'),
    ]
    encodage_du_fichier = models.CharField(
        max_length=20,
        choices=ENCODAGE_CHOICES,
        default='utf-8',
    )

    # Extension du fichier genere
    # / Generated file extension
    EXTENSION_CHOICES = [
        ('.csv', 'CSV'),
        ('.txt', 'TXT'),
    ]
    extension_du_fichier = models.CharField(
        max_length=5,
        choices=EXTENSION_CHOICES,
        default='.csv',
    )

    # Mode debit/credit : deux colonnes separees ou montant + sens
    # / Debit/credit mode: two separate columns or amount + direction
    MODE_MONTANT_CHOICES = [
        ('DEBIT_CREDIT', 'Deux colonnes (Débit / Crédit)'),
        ('MONTANT_SENS', 'Montant + Sens (D/C)'),
    ]
    mode_debit_credit = models.CharField(
        max_length=20,
        choices=MODE_MONTANT_CHOICES,
        default='DEBIT_CREDIT',
    )

    # Ordre des colonnes dans le fichier (JSON : liste de noms de champs)
    # / Column order in the output file (JSON: list of field names)
    ordre_des_colonnes = models.JSONField(
        default=list,
        help_text="Liste ordonnée des noms de colonnes à inclure dans l'export.",
    )

    class Meta:
        verbose_name = "Profil d'export comptable"
        verbose_name_plural = "Profils d'export comptable"
```

### Les 5 profils pré-configurés à créer

#### Profil « Sage 50 »

| Paramètre               | Valeur                                                                                |
| ----------------------- | ------------------------------------------------------------------------------------- |
| Séparateur              | Point-virgule `;`                                                                     |
| Décimal                 | Point `.`                                                                             |
| Date                    | JJ/MM/AAAA                                                                            |
| En-têtes                | Non                                                                                   |
| Encodage                | UTF-8                                                                                 |
| Mode montant            | Deux colonnes (Débit / Crédit)                                                        |
| Colonnes (dans l'ordre) | `date`, `code_journal`, `numero_compte`, `numero_piece`, `libelle`, `debit`, `credit` |

#### Profil « EBP classique »

| Paramètre    | Valeur                                                                                                                                 |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Séparateur   | Virgule `,`                                                                                                                            |
| Décimal      | Point `.`                                                                                                                              |
| Date         | JJMMAA                                                                                                                                 |
| En-têtes     | Non (1ère ligne = commentaire ignoré)                                                                                                  |
| Encodage     | UTF-8                                                                                                                                  |
| Extension    | `.txt`                                                                                                                                 |
| Mode montant | Montant + Sens (D/C)                                                                                                                   |
| Colonnes     | `numero_ligne`, `date`, `code_journal`, `numero_compte`, `libelle_auto`, `libelle`, `numero_piece`, `montant`, `sens`, `date_echeance` |

**Attention EBP** : le libellé et le numéro de pièce sont entre guillemets `"..."`.
Le champ `libelle_auto` est toujours vide. Le dernier champ est suivi d'une virgule.

#### Profil « Dolibarr »

| Paramètre    | Valeur                                                                                                                                                |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Séparateur   | Virgule `,`                                                                                                                                           |
| Décimal      | Point `.` (IMPORTANT — pas virgule)                                                                                                                   |
| Date         | AAAA-MM-JJ                                                                                                                                            |
| En-têtes     | Oui                                                                                                                                                   |
| Encodage     | UTF-8                                                                                                                                                 |
| Mode montant | Deux colonnes                                                                                                                                         |
| Colonnes     | `numero_transaction`, `date`, `reference_piece`, `code_journal`, `numero_compte`, `compte_auxiliaire`, `libelle`, `debit`, `credit`, `libelle_compte` |

#### Profil « Paheko simplifié »

| Paramètre    | Valeur                                                                                                        |
| ------------ | ------------------------------------------------------------------------------------------------------------- |
| Séparateur   | Point-virgule `;`                                                                                             |
| Décimal      | Virgule `,`                                                                                                   |
| Date         | JJ/MM/AAAA                                                                                                    |
| En-têtes     | Oui                                                                                                           |
| Encodage     | UTF-8                                                                                                         |
| Mode montant | Montant unique (pas débit/crédit)                                                                             |
| Colonnes     | `numero_ecriture`, `date`, `compte_debit`, `compte_credit`, `montant`, `libelle`, `numero_piece`, `remarques` |

#### Profil « PennyLane »

| Paramètre    | Valeur                                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------------------- |
| Séparateur   | Point-virgule `;`                                                                                       |
| Décimal      | Virgule `,`                                                                                             |
| Date         | JJ/MM/AAAA                                                                                              |
| En-têtes     | Oui                                                                                                     |
| Encodage     | UTF-8                                                                                                   |
| Mode montant | Deux colonnes                                                                                           |
| Colonnes     | `date`, `code_journal`, `numero_compte`, `libelle_compte`, `libelle`, `numero_piece`, `debit`, `credit` |

**Note PennyLane** : le code journal doit contenir **uniquement des lettres** (max 5 caractères). PennyLane accepte aussi le FEC natif — c'est même le chemin le plus simple.

---

## Mapping des comptes PCG par défaut

Ce mapping traduit les données de caisse LaBoutik en comptes du Plan Comptable Général.
Il doit être **configurable par lieu** (chaque structure a son propre plan comptable).

### Modèle MappingComptable

```python
class MappingComptable(models.Model):
    """
    Correspondance entre un type de donnee de caisse et un compte PCG.
    Chaque lieu peut personnaliser ses comptes comptables.
    / Maps POS data types to PCG account numbers. Configurable per venue.

    LOCALISATION : laboutik/exports/models.py
    """
    # Identifiant unique
    # / Unique identifier
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Le type de donnee de caisse que ce mapping concerne
    # / The POS data type this mapping handles
    TYPE_CHOICES = [
        # --- Comptes de produits (classe 7) ---
        ('VENTE_MARCHANDISE', 'Vente de marchandises'),
        ('VENTE_PRESTATION', 'Prestation de services'),
        ('VENTE_BILLETTERIE', 'Billetterie / Entrées'),
        ('VENTE_ADHESION', 'Adhésions'),
        ('VENTE_CROWDFUNDING', 'Crowdfunding / Dons'),

        # --- Comptes de TVA (classe 44) ---
        ('TVA_COLLECTEE_20', 'TVA collectée 20%'),
        ('TVA_COLLECTEE_10', 'TVA collectée 10%'),
        ('TVA_COLLECTEE_55', 'TVA collectée 5,5%'),
        ('TVA_COLLECTEE_21', 'TVA collectée 2,1%'),

        # --- Comptes de tresorerie (classe 5) ---
        ('CAISSE_ESPECES', 'Caisse espèces'),
        ('BANQUE_CB', 'Banque CB / TPE'),
        ('BANQUE_STRIPE', 'Banque Stripe'),
        ('BANQUE_HELLOASSO', 'Banque HelloAsso'),

        # --- Comptes d'attente / cashless ---
        ('CASHLESS_NFC', 'Cashless NFC (avances clients)'),
        ('CASHLESS_MLCC', 'Cashless MLCC (monnaie locale)'),
        ('CASHLESS_GIFT', 'Carte cadeau'),

        # --- Comptes de tiers ---
        ('CLIENT_COMPTOIR', 'Client comptoir (anonyme)'),
    ]
    type_de_donnee = models.CharField(max_length=50, choices=TYPE_CHOICES)

    # Le numero de compte PCG associe
    # / The associated PCG account number
    numero_de_compte = models.CharField(max_length=20)

    # Le libelle du compte (pour affichage dans le FEC)
    # / Account label (for FEC display)
    libelle_du_compte = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Mapping comptable"
        verbose_name_plural = "Mappings comptables"
        unique_together = ['type_de_donnee']  # Un seul mapping par type
```

### Valeurs par défaut du mapping

| type_de_donnee       | numero_de_compte | libelle_du_compte                   |
| -------------------- | ---------------- | ----------------------------------- |
| `VENTE_MARCHANDISE`  | `707000`         | Ventes de marchandises              |
| `VENTE_PRESTATION`   | `706000`         | Prestations de services             |
| `VENTE_BILLETTERIE`  | `706300`         | Locations et prestations diverses   |
| `VENTE_ADHESION`     | `756000`         | Cotisations                         |
| `VENTE_CROWDFUNDING` | `754100`         | Dons manuels                        |
| `TVA_COLLECTEE_20`   | `445710`         | TVA collectée 20%                   |
| `TVA_COLLECTEE_10`   | `445711`         | TVA collectée 10%                   |
| `TVA_COLLECTEE_55`   | `445712`         | TVA collectée 5,5%                  |
| `TVA_COLLECTEE_21`   | `445713`         | TVA collectée 2,1%                  |
| `CAISSE_ESPECES`     | `530000`         | Caisse                              |
| `BANQUE_CB`          | `512000`         | Banque                              |
| `BANQUE_STRIPE`      | `512100`         | Banque Stripe                       |
| `BANQUE_HELLOASSO`   | `512200`         | Banque HelloAsso                    |
| `CASHLESS_NFC`       | `419100`         | Clients — avances et acomptes reçus |
| `CASHLESS_MLCC`      | `419200`         | Avances en monnaie locale           |
| `CASHLESS_GIFT`      | `419300`         | Cartes cadeau                       |
| `CLIENT_COMPTOIR`    | `411000`         | Clients                             |

---

## Logique métier : d'un ticket Z à des écritures comptables

### Qu'est-ce qu'un ticket Z ?

Le ticket Z est la **clôture de caisse journalière**. Il contient :

- Le total des ventes par catégorie de produit
- Le total par moyen de paiement (espèces, CB, cashless, etc.)
- La ventilation TVA (base HT + montant TVA par taux)
- La date et l'heure de la clôture

### Comment transformer un Z en écritures comptables

Pour chaque ticket Z, on génère **une écriture comptable équilibrée** :

```
DEBIT  530000  Caisse espèces         150,00    ← total encaissé en espèces
DEBIT  512000  Banque CB              320,00    ← total encaissé en CB
DEBIT  419100  Cashless NFC           180,00    ← total encaissé en NFC
                                      -------
                                       650,00   ← TOTAL DEBITS

CREDIT 707000  Ventes marchandises    541,67    ← total HT des ventes
CREDIT 445710  TVA collectée 20%      108,33    ← total TVA
                                      -------
                                       650,00   ← TOTAL CREDITS (= DEBITS)
```

L'écriture est **toujours équilibrée** : total des débits = total des crédits.

### Granularité de la ventilation TVA

Si le Z contient des ventes avec des taux de TVA différents, chaque taux
génère sa propre ligne de crédit :

```
CREDIT 707000  Ventes 20%             400,00   ← HT à 20%
CREDIT 445710  TVA 20%                 80,00
CREDIT 707000  Ventes 10%             100,00   ← HT à 10%
CREDIT 445711  TVA 10%                 10,00
CREDIT 706000  Prestations 5,5%        50,00   ← HT à 5,5%
CREDIT 445712  TVA 5,5%                 2,75
```

---

## Conventions de code (rappel DJC)

- **Noms de variables en français, très explicites** : `total_des_ventes_en_especes`, pas `cash_total`
- **Commentaires bilingues FR/EN** : français détaillé + une ligne anglais
- **ViewSet explicite** (pas de ModelViewSet)
- **Pas de magic** : pas de metaclass, pas de decorators qui cachent la logique
- **Tests** : lire `tests/TESTS_README.md` avant d'écrire des tests

### Exemple de style attendu pour le générateur FEC

```python
def generer_ligne_fec(
    code_journal,
    libelle_journal,
    numero_ecriture,
    date_ecriture,
    numero_compte,
    libelle_compte,
    reference_piece,
    libelle_ecriture,
    montant_debit,
    montant_credit,
    date_validation,
    numero_compte_auxiliaire="",
    libelle_compte_auxiliaire="",
):
    """
    Genere une ligne au format FEC (18 champs separes par tabulation).
    Les montants sont formates avec virgule comme separateur decimal.
    Les dates sont au format AAAAMMJJ sans separateur.
    / Generates one FEC line (18 tab-separated fields).

    LOCALISATION : laboutik/exports/fec.py

    :param code_journal: Code du journal comptable (str, ex: "VE")
    :param libelle_journal: Libelle du journal (str, ex: "Journal de ventes")
    :param numero_ecriture: Identifiant unique de l'ecriture (str)
    :param date_ecriture: Date de l'ecriture (datetime.date)
    :param numero_compte: Numero de compte PCG (str, ex: "707000")
    :param libelle_compte: Libelle du compte (str)
    :param reference_piece: Reference de la piece justificative (str, ex: "Z-20260331-001")
    :param libelle_ecriture: Description de l'ecriture (str)
    :param montant_debit: Montant au debit en Decimal (Decimal)
    :param montant_credit: Montant au credit en Decimal (Decimal)
    :param date_validation: Date de validation de l'ecriture (datetime.date)
    :param numero_compte_auxiliaire: Compte auxiliaire optionnel (str)
    :param libelle_compte_auxiliaire: Libelle auxiliaire optionnel (str)
    :return: Chaine de caracteres representant la ligne FEC (str)
    """
    # Formate la date au format AAAAMMJJ (ex: 20260331)
    # / Formats date as YYYYMMDD
    date_formatee = date_ecriture.strftime("%Y%m%d")
    date_validation_formatee = date_validation.strftime("%Y%m%d")

    # Formate le montant avec virgule comme separateur decimal
    # Ex: Decimal("150.00") → "150,00"
    # / Formats amount with comma as decimal separator
    debit_formate = f"{montant_debit:.2f}".replace(".", ",")
    credit_formate = f"{montant_credit:.2f}".replace(".", ",")

    # Assemble les 18 champs separes par tabulation
    # Les champs 14, 15, 17, 18 (lettrage et devise) sont vides
    # / Assembles 18 tab-separated fields
    les_18_champs = [
        code_journal,                   # 1. JournalCode
        libelle_journal,                # 2. JournalLib
        numero_ecriture,                # 3. EcritureNum
        date_formatee,                  # 4. EcritureDate
        numero_compte,                  # 5. CompteNum
        libelle_compte,                 # 6. CompteLib
        numero_compte_auxiliaire,       # 7. CompAuxNum
        libelle_compte_auxiliaire,      # 8. CompAuxLib
        reference_piece,                # 9. PieceRef
        date_formatee,                  # 10. PieceDate (= EcritureDate)
        libelle_ecriture,               # 11. EcritureLib
        debit_formate,                  # 12. Debit
        credit_formate,                 # 13. Credit
        "",                             # 14. EcritureLet (vide)
        "",                             # 15. DateLet (vide)
        date_validation_formatee,       # 16. ValidDate
        "",                             # 17. Montantdevise (vide)
        "",                             # 18. Idevise (vide)
    ]

    ligne_fec = "\t".join(les_18_champs)
    return ligne_fec
```

---

## Résumé des formats par logiciel (aide-mémoire rapide)

| Logiciel          | Meilleur chemin        | Séparateur   | Décimal      | Date         | En-têtes             | Particularité                            |
| ----------------- | ---------------------- | ------------ | ------------ | ------------ | -------------------- | ---------------------------------------- |
| **Sage 50**       | FEC ou CSV `;`         | `;`          | `.`          | JJ/MM/AAAA   | Non                  | Import paramétrable, mapping manuel      |
| **Sage 100**      | FEC ou CSV             | configurable | configurable | configurable | configurable         | Très flexible                            |
| **EBP classique** | CSV dédié              | `,`          | `.`          | JJMMAA       | Non (L1=commentaire) | Montant+Sens, guillemets sur libellé     |
| **EBP Hubbix**    | FEC natif              | `\t`         | `,`          | AAAAMMJJ     | Oui                  | Auto-mapping des colonnes FEC            |
| **PennyLane**     | FEC natif              | `\t`         | `,`          | AAAAMMJJ     | Oui                  | Code journal = lettres uniquement        |
| **Odoo**          | FEC natif              | `\t`         | `,`          | AAAAMMJJ     | Oui                  | Comptes tronqués à 6 chiffres            |
| **Dokos**         | CSV générique          | configurable | `.`          | AAAA-MM-JJ   | Oui                  | Fork ERPNext, pas d'import FEC natif     |
| **Dolibarr**      | CSV ou FEC             | `,`          | `.` ⚠️       | AAAA-MM-JJ   | Oui                  | Piège : décimal = point obligatoire      |
| **Paheko**        | FEC natif ou simplifié | `;`          | `,`          | JJ/MM/AAAA   | Oui                  | 4 formats (simplifié/complet/groupé/FEC) |

### Conclusion opérationnelle

**Le FEC couvre directement** : EBP Hubbix, PennyLane, Odoo, Paheko, Sage (via import paramétrable).
**Besoin d'un profil CSV dédié** : EBP classique (format exotique), Dolibarr, Dokos, vieux Sage.

→ Implémenter le FEC en premier. Ajouter les profils CSV ensuite.
