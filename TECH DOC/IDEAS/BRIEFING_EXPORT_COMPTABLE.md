# EXPORT COMPTABLE — Briefing agent Claude Code

> Ce document est un briefing pour un agent IA travaillant sur le code de LaBoutik.
> Il contient tout ce qu'il faut pour :
> 1. Permettre aux gérants d'associer leurs catégories de produits à des comptes comptables
> 2. Générer des fichiers d'export que le comptable peut importer directement

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

**Ce qu'on veut ajouter (deux couches)** :

1. **Couche mapping** : permettre au gérant (ou son comptable) d'associer
   chaque catégorie d'article et chaque moyen de paiement à un numéro de
   compte du plan comptable. TiBillet ne fait PAS de comptabilité — on
   pré-mâche le travail pour que le cabinet comptable n'ait plus à ressaisir.

2. **Couche export** : transformer les données Z en fichiers d'écritures
   comptables importables par les logiciels du marché (FEC, CSV paramétré).

### Ce qu'on ne fait PAS

On ne veut **pas** implémenter un module comptable complet dans TiBillet.
Pas de grand livre, pas de balance, pas de bilan, pas de clôture d'exercice.
On reste un logiciel de caisse. Le rôle de TiBillet est de produire des
données propres et bien ventilées que le comptable peut aspirer telles quelles.

### Comment font les autres : enseignements de Paheko, Dolibarr, Odoo, PennyLane

Tous les outils du marché utilisent le même pattern : un **mapping
catégorie de produit → compte comptable** configurable.

**Paheko** (logiciel associatif) est le plus accessible : il propose une
vue simplifiée où l'utilisateur ne voit pas de numéros de compte, et un
mode "expert" activable à tout moment. Le plan comptable associatif 2020
est pré-installé. Les comptes sont classés en "favoris" et "usuels" pour
ne montrer que les 10-15 comptes dont l'asso a réellement besoin.
On peut importer un plan comptable personnalisé en CSV (6 colonnes).

**Dolibarr** a un module "Comptabilité Simplifiée" qui génère des rapports
comptables directement depuis les données métier (factures, paiements, TVA)
SANS gérer de comptes comptables. Il produit un zip CSV+PDF à envoyer au
comptable. C'est exactement le positionnement qu'on vise. Son module avancé
ajoute un champ "compte comptable vente/achat" sur chaque fiche produit.

**Odoo** attache un compte de revenu et un compte de charges par défaut à
chaque catégorie de produit. Le module POS génère automatiquement les
écritures comptables à la clôture de session (= ticket Z). Puissant mais
surdimensionné pour nos structures.

**PennyLane** fait le pont via la plateforme Chift : à la clôture de
caisse, Chift génère une écriture comptable dans PennyLane avec les bons
comptes pré-affectés. PennyLane utilise des "règles d'affectation" : à
partir d'un libellé ou d'un montant, on automatise l'attribution du compte
comptable et du taux de TVA.

### Exemple réel : le plan comptable d'un petit bar/resto

Voici un exemple de ce que les structures nous envoient aujourd'hui
dans un tableur pour expliquer leur ventilation à leur comptable :

```
COMPTES VENTES (à attribuer par catégories ou produits) :
  7072000  Boissons à 20%
  7071000  Boissons à 10%
  7011000  Alimentaire à 10%
  7010500  Alimentaire à emporter à 5,5%
  41960000 Contenant Bako (consignes)

COMPTES MOYENS DE PAIEMENT :
  51120001 Paiement CB
  5300000  Paiement Espèces
  51120002 Paiement Tickets Restaurants
  51120000 Paiement en chèque

COMPTES TVA :
  445712   TVA 20%
  445710   TVA 10%
  445705   TVA 5,5%

COMPTES SPECIAUX :
  709000   Remises
  5811000  Caisse (mouvements d'espèces)
  758000   Ecart de gestion + (écarts de caisse)
  658000   Ecart de gestion - (écarts de caisse)
```

C'est CE tableau qu'on veut permettre de configurer dans l'admin TiBillet,
et c'est CE mapping qu'on utilise pour générer les écritures d'export.

---

## Architecture cible

### Nouveau module : `laboutik/exports/`

```
laboutik/exports/
├── __init__.py
├── models.py          # CompteComptable, MappingCategorie, ExportProfile, ExportHistory
├── generators.py      # Classe de base + un générateur par format
├── fec.py             # Générateur FEC (format pivot)
├── csv_configurable.py # Générateur CSV avec mapping configurable
├── views.py           # Vues d'export (admin + API)
├── serializers.py     # Sérialisation DRF
├── admin_tenant.py    # Admin Unfold pour la configuration
├── urls.py
├── fixtures/
│   └── plan_comptable_defaut.json  # Comptes par défaut (bar/resto + asso)
└── templates/
    └── exports/
        └── partials/   # Fragments HTMX pour l'admin
```

### Trois couches à implémenter (par priorité)

**Priorité 0 — Mapping catégories → comptes comptables**
Permettre au gérant de lier ses catégories d'articles et ses moyens de
paiement à des numéros de compte PCG. C'est le pré-requis indispensable :
sans ce mapping, on ne peut pas générer d'export propre.

**Priorité 1 — Export FEC (format pivot)**
Le FEC est un format figé, obligatoire en France, accepté nativement par :
PennyLane, Odoo, EBP Hubbix, Paheko, et via import paramétrable par Sage.
Un seul code = couvre 80% des cas.

**Priorité 2 — Export CSV configurable (profils)**
Pour les cabinets comptables avec leur propre format maison.
Profils pré-configurés : Sage 50, EBP classique, Dolibarr, Paheko simplifié.

---

## Priorité 0 — Mapping catégories → comptes comptables

C'est la brique fondamentale. Avant de pouvoir exporter quoi que ce soit,
chaque lieu doit pouvoir configurer la correspondance entre ses données de
caisse et les comptes du plan comptable de son cabinet.

### Principe : deux niveaux de mapping

**Niveau 1 — Comptes de vente (liés aux catégories d'articles)**
Chaque catégorie d'article dans LaBoutik (ex: "Boissons", "Alimentaire",
"Billetterie") est associée à un couple (compte comptable + taux de TVA).
Le mapping se fait au niveau de la CATEGORIE, pas de l'article individuel.
C'est ce que montre l'exemple réel : "Boissons à 20%" → compte 7072000.

**Niveau 2 — Comptes de trésorerie (liés aux moyens de paiement)**
Chaque moyen de paiement (espèces, CB, cashless NFC, chèque, ticket-resto)
est associé à un compte comptable de trésorerie. Les comptes de TVA et les
comptes spéciaux (remises, écarts de caisse) sont gérés à part.

### Modèle CompteComptable

```python
class CompteComptable(models.Model):
    """
    Un compte du plan comptable utilisable pour le mapping.
    Chaque lieu a sa propre liste de comptes (multi-tenant).
    TiBillet ne gere PAS un plan comptable complet :
    on stocke uniquement les comptes utiles pour l'export.
    / An accounting code usable for mapping. Per-tenant. Not a full chart of accounts.

    LOCALISATION : laboutik/exports/models.py
    """
    # Identifiant unique
    # / Unique identifier
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Le numero de compte PCG (ex: "7072000", "445712", "5300000")
    # / PCG account number
    numero_de_compte = models.CharField(
        max_length=20,
        verbose_name="N° de compte",
        help_text="Numéro du compte dans le plan comptable (ex: 7072000)",
    )

    # Le libelle du compte (ex: "Boissons à 20%", "TVA 20%")
    # / Account label
    libelle_du_compte = models.CharField(
        max_length=200,
        verbose_name="Intitulé",
        help_text="Intitulé du compte tel qu'il apparaîtra dans l'export",
    )

    # La nature du compte, pour faciliter le filtrage dans l'admin
    # / Account nature, for filtering
    NATURE_CHOICES = [
        ('VENTE', 'Compte de vente (classe 7)'),
        ('TVA', 'Compte de TVA (classe 44)'),
        ('TRESORERIE', 'Compte de trésorerie (classe 5)'),
        ('TIERS', 'Compte de tiers (classe 4)'),
        ('CHARGE', 'Compte de charge (classe 6)'),
        ('PRODUIT_EXCEPTIONNEL', 'Produit exceptionnel (classe 7)'),
        ('SPECIAL', 'Compte spécial (remises, écarts, etc.)'),
    ]
    nature_du_compte = models.CharField(
        max_length=30,
        choices=NATURE_CHOICES,
        verbose_name="Nature",
    )

    # Taux de TVA associe a ce compte (uniquement pour les comptes de vente)
    # Null si pas applicable (comptes de tresorerie, TVA, etc.)
    # / VAT rate for sales accounts, null otherwise
    taux_de_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Taux de TVA (%)",
        help_text="Remplir uniquement pour les comptes de vente (ex: 20.00, 10.00, 5.50)",
    )

    # Compte actif ou pas (pour desactiver sans supprimer)
    # / Active flag
    est_actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Compte comptable"
        verbose_name_plural = "Comptes comptables"
        ordering = ['numero_de_compte']

    def __str__(self):
        return f"{self.numero_de_compte} — {self.libelle_du_compte}"
```

### Modèle MappingCategorieVersCompte

```python
class MappingCategorieVersCompte(models.Model):
    """
    Associe une categorie d'articles LaBoutik a un compte comptable de vente.
    C'est ici que le gerant (ou son comptable) configure :
    "Mes articles de la categorie Boissons vont dans le compte 7072000".
    / Maps a LaBoutik article category to a sales accounting code.

    LOCALISATION : laboutik/exports/models.py

    ATTENTION MULTI-TENANT :
    Ce modele vit dans le schema du tenant (pas en public).
    Utiliser tenant_context(tenant) pour toute creation/modification.
    """
    # Identifiant unique
    # / Unique identifier
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # La categorie d'articles LaBoutik (ForeignKey vers le modele existant)
    # / The LaBoutik article category
    categorie = models.OneToOneField(
        'Categorie',  # Adapter au nom reel du modele de categorie dans LaBoutik
        on_delete=models.CASCADE,
        related_name='mapping_comptable',
        verbose_name="Catégorie d'articles",
    )

    # Le compte comptable de vente associe
    # / The associated sales account
    compte_de_vente = models.ForeignKey(
        CompteComptable,
        on_delete=models.PROTECT,
        related_name='categories_associees',
        verbose_name="Compte de vente",
        help_text="Le compte comptable où seront enregistrées les ventes HT de cette catégorie",
    )

    class Meta:
        verbose_name = "Mapping catégorie → compte"
        verbose_name_plural = "Mappings catégories → comptes"

    def __str__(self):
        return f"{self.categorie} → {self.compte_de_vente}"
```

### Modèle MappingMoyenDePaiement

```python
class MappingMoyenDePaiement(models.Model):
    """
    Associe un moyen de paiement LaBoutik a un compte comptable de tresorerie.
    Ex: "Especes" → 5300000, "CB" → 51120001, "Ticket Resto" → 51120002
    / Maps a LaBoutik payment method to a treasury accounting code.

    LOCALISATION : laboutik/exports/models.py
    """
    # Identifiant unique
    # / Unique identifier
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Le moyen de paiement LaBoutik
    # / The LaBoutik payment method
    MOYEN_CHOICES = [
        ('ESPECES', 'Espèces'),
        ('CARTE_BANCAIRE', 'Carte bancaire'),
        ('CASHLESS_NFC', 'Cashless NFC'),
        ('CASHLESS_MLCC', 'Monnaie locale (MLCC)'),
        ('CHEQUE', 'Chèque'),
        ('TICKET_RESTAURANT', 'Ticket restaurant'),
        ('STRIPE', 'Stripe (en ligne)'),
        ('HELLOASSO', 'HelloAsso'),
        ('CARTE_CADEAU', 'Carte cadeau'),
        ('VIREMENT', 'Virement bancaire'),
    ]
    moyen_de_paiement = models.CharField(
        max_length=30,
        choices=MOYEN_CHOICES,
        unique=True,
        verbose_name="Moyen de paiement",
    )

    # Le compte comptable de tresorerie associe
    # / The associated treasury account
    compte_de_tresorerie = models.ForeignKey(
        CompteComptable,
        on_delete=models.PROTECT,
        related_name='moyens_de_paiement_associes',
        verbose_name="Compte de trésorerie",
    )

    class Meta:
        verbose_name = "Mapping moyen de paiement → compte"
        verbose_name_plural = "Mappings moyens de paiement → comptes"

    def __str__(self):
        return f"{self.get_moyen_de_paiement_display()} → {self.compte_de_tresorerie}"
```

### Modèle MappingComptesSpeciaux

```python
class MappingComptesSpeciaux(models.Model):
    """
    Comptes comptables speciaux qui ne sont ni des ventes ni des moyens de paiement.
    TVA, remises, ecarts de caisse, mouvements de caisse, consignes.
    Un seul enregistrement par lieu (singleton pattern via un manager).
    / Special accounts: VAT, discounts, cash discrepancies, deposits.

    LOCALISATION : laboutik/exports/models.py
    """
    # --- Comptes de TVA ---
    # / VAT accounts
    compte_tva_20 = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        related_name='+', verbose_name="TVA collectée 20%",
        null=True, blank=True,
    )
    compte_tva_10 = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        related_name='+', verbose_name="TVA collectée 10%",
        null=True, blank=True,
    )
    compte_tva_55 = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        related_name='+', verbose_name="TVA collectée 5,5%",
        null=True, blank=True,
    )
    compte_tva_21 = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        related_name='+', verbose_name="TVA collectée 2,1%",
        null=True, blank=True,
    )

    # --- Comptes speciaux ---
    # / Special accounts
    compte_remises = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        related_name='+', verbose_name="Remises accordées",
        null=True, blank=True,
        help_text="Ex: 709000",
    )
    compte_ecart_positif = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        related_name='+', verbose_name="Écart de caisse (+)",
        null=True, blank=True,
        help_text="Ex: 758000 — Produits divers de gestion",
    )
    compte_ecart_negatif = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        related_name='+', verbose_name="Écart de caisse (-)",
        null=True, blank=True,
        help_text="Ex: 658000 — Charges diverses de gestion",
    )
    compte_mouvement_caisse = models.ForeignKey(
        CompteComptable, on_delete=models.PROTECT,
        related_name='+', verbose_name="Mouvements de caisse",
        null=True, blank=True,
        help_text="Ex: 5811000 — Virements internes",
    )

    class Meta:
        verbose_name = "Comptes spéciaux"
        verbose_name_plural = "Comptes spéciaux"
```

### Fixtures par défaut (deux jeux)

#### Jeu "Bar / Restaurant" (structures commerciales)

| Compte | Libellé | Nature | TVA |
|---|---|---|---|
| 7072000 | Boissons à 20% | VENTE | 20% |
| 7071000 | Boissons à 10% | VENTE | 10% |
| 7011000 | Alimentaire à 10% | VENTE | 10% |
| 7010500 | Alimentaire à emporter 5,5% | VENTE | 5,5% |
| 51120001 | Paiement CB | TRESORERIE | — |
| 5300000 | Paiement Espèces | TRESORERIE | — |
| 51120002 | Paiement Tickets Restaurants | TRESORERIE | — |
| 51120000 | Paiement en chèque | TRESORERIE | — |
| 445712 | TVA 20% | TVA | — |
| 445710 | TVA 10% | TVA | — |
| 445705 | TVA 5,5% | TVA | — |
| 709000 | Remises | SPECIAL | — |
| 5811000 | Caisse | SPECIAL | — |
| 758000 | Écart de gestion + | PRODUIT_EXCEPTIONNEL | — |
| 658000 | Écart de gestion - | CHARGE | — |

#### Jeu "Association / Tiers-lieu" (structures non-commerciales)

| Compte | Libellé | Nature | TVA |
|---|---|---|---|
| 706000 | Prestations de services | VENTE | 20% |
| 707000 | Ventes de marchandises | VENTE | 20% |
| 706300 | Billetterie | VENTE | 5,5% |
| 756000 | Cotisations | VENTE | — |
| 754100 | Dons manuels | VENTE | — |
| 512000 | Banque | TRESORERIE | — |
| 530000 | Caisse | TRESORERIE | — |
| 419100 | Avances clients (cashless) | TIERS | — |
| 445710 | TVA collectée 20% | TVA | — |
| 445712 | TVA collectée 5,5% | TVA | — |

### Interface admin (approche Paheko)

S'inspirer de l'approche Paheko pour l'UX :

- **Vue simple par défaut** : le gérant voit un tableau à deux colonnes
  "Catégorie d'articles" / "Compte comptable" avec des menus déroulants.
  Pas de jargon comptable inutile.

- **Bouton "Configurer les comptes"** : ouvre un écran admin Unfold où on
  peut ajouter/modifier les comptes comptables disponibles. C'est ici
  que le comptable du cabinet intervient pour personnaliser le plan.

- **Pré-remplissage intelligent** : à la création d'un lieu, proposer
  un choix "Bar/Restaurant" ou "Association" et charger les fixtures
  correspondantes. Le gérant n'a plus qu'à ajuster.

- **Validation douce** : si une catégorie n'a pas de mapping, l'export
  fonctionne quand même mais un avertissement s'affiche. Pas de blocage.

---

## Priorité 1 — Format FEC : spécification exacte

### Caractéristiques techniques du fichier

| Paramètre | Valeur |
|---|---|
| Extension | `.txt` |
| Encodage | UTF-8 |
| Séparateur de champs | Tabulation `\t` |
| Séparateur décimal | Virgule `,` |
| Format de date | AAAAMMJJ (ex: 20260331) |
| Fin de ligne | `\r\n` (CRLF) |
| Première ligne | En-têtes des 18 colonnes |
| Nom du fichier | `{SIREN}FEC{AAAAMMJJ}.txt` (date = clôture exercice) |

### Les 18 colonnes obligatoires

```
JournalCode	JournalLib	EcritureNum	EcritureDate	CompteNum	CompteLib	CompAuxNum	CompAuxLib	PieceRef	PieceDate	EcritureLib	Debit	Credit	EcritureLet	DateLet	ValidDate	Montantdevise	Idevise
```

Détail :

| # | Nom | Description | Obligatoire | Exemple |
|---|---|---|---|---|
| 1 | JournalCode | Code du journal | ✅ | `VE` |
| 2 | JournalLib | Libellé du journal | ✅ | `Journal de ventes` |
| 3 | EcritureNum | Numéro séquentiel de l'écriture | ✅ | `VE-20260331-001` |
| 4 | EcritureDate | Date de l'écriture | ✅ | `20260331` |
| 5 | CompteNum | Numéro de compte PCG | ✅ | `707000` |
| 6 | CompteLib | Libellé du compte | ✅ | `Ventes de marchandises` |
| 7 | CompAuxNum | Compte auxiliaire | ❌ | `` (vide si pas utilisé) |
| 8 | CompAuxLib | Libellé compte auxiliaire | ❌ | `` |
| 9 | PieceRef | Référence de la pièce justificative | ✅ | `Z-20260331-001` |
| 10 | PieceDate | Date de la pièce | ✅ | `20260331` |
| 11 | EcritureLib | Libellé de l'écriture | ✅ | `Ventes espèces du 31/03/2026` |
| 12 | Debit | Montant au débit | ✅ | `0,00` ou `150,00` |
| 13 | Credit | Montant au crédit | ✅ | `150,00` ou `0,00` |
| 14 | EcritureLet | Lettrage | ❌ | `` |
| 15 | DateLet | Date de lettrage | ❌ | `` |
| 16 | ValidDate | Date de validation | ✅ | `20260331` |
| 17 | Montantdevise | Montant en devise étrangère | ❌ | `` |
| 18 | Idevise | Code devise ISO | ❌ | `` |

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

| Paramètre | Valeur |
|---|---|
| Séparateur | Point-virgule `;` |
| Décimal | Point `.` |
| Date | JJ/MM/AAAA |
| En-têtes | Non |
| Encodage | UTF-8 |
| Mode montant | Deux colonnes (Débit / Crédit) |
| Colonnes (dans l'ordre) | `date`, `code_journal`, `numero_compte`, `numero_piece`, `libelle`, `debit`, `credit` |

#### Profil « EBP classique »

| Paramètre | Valeur |
|---|---|
| Séparateur | Virgule `,` |
| Décimal | Point `.` |
| Date | JJMMAA |
| En-têtes | Non (1ère ligne = commentaire ignoré) |
| Encodage | UTF-8 |
| Extension | `.txt` |
| Mode montant | Montant + Sens (D/C) |
| Colonnes | `numero_ligne`, `date`, `code_journal`, `numero_compte`, `libelle_auto`, `libelle`, `numero_piece`, `montant`, `sens`, `date_echeance` |

**Attention EBP** : le libellé et le numéro de pièce sont entre guillemets `"..."`.
Le champ `libelle_auto` est toujours vide. Le dernier champ est suivi d'une virgule.

#### Profil « Dolibarr »

| Paramètre | Valeur |
|---|---|
| Séparateur | Virgule `,` |
| Décimal | Point `.` (IMPORTANT — pas virgule) |
| Date | AAAA-MM-JJ |
| En-têtes | Oui |
| Encodage | UTF-8 |
| Mode montant | Deux colonnes |
| Colonnes | `numero_transaction`, `date`, `reference_piece`, `code_journal`, `numero_compte`, `compte_auxiliaire`, `libelle`, `debit`, `credit`, `libelle_compte` |

#### Profil « Paheko simplifié »

| Paramètre | Valeur |
|---|---|
| Séparateur | Point-virgule `;` |
| Décimal | Virgule `,` |
| Date | JJ/MM/AAAA |
| En-têtes | Oui |
| Encodage | UTF-8 |
| Mode montant | Montant unique (pas débit/crédit) |
| Colonnes | `numero_ecriture`, `date`, `compte_debit`, `compte_credit`, `montant`, `libelle`, `numero_piece`, `remarques` |

#### Profil « PennyLane »

| Paramètre | Valeur |
|---|---|
| Séparateur | Point-virgule `;` |
| Décimal | Virgule `,` |
| Date | JJ/MM/AAAA |
| En-têtes | Oui |
| Encodage | UTF-8 |
| Mode montant | Deux colonnes |
| Colonnes | `date`, `code_journal`, `numero_compte`, `libelle_compte`, `libelle`, `numero_piece`, `debit`, `credit` |

**Note PennyLane** : le code journal doit contenir **uniquement des lettres** (max 5 caractères). PennyLane accepte aussi le FEC natif — c'est même le chemin le plus simple.

---

---

## Mapping des comptes — référence croisée

Les modèles de mapping sont définis dans la section "Priorité 0" ci-dessus :
`CompteComptable`, `MappingCategorieVersCompte`, `MappingMoyenDePaiement`,
et `MappingComptesSpeciaux`.

Les deux jeux de fixtures (Bar/Restaurant et Association) fournissent les
valeurs par défaut. Le gérant peut les personnaliser dans l'admin Unfold.

---

## Logique métier : d'un ticket Z à des écritures comptables

### Qu'est-ce qu'un ticket Z ?

Le ticket Z est la **clôture de caisse journalière**. Il contient :
- Le total des ventes par catégorie de produit
- Le total par moyen de paiement (espèces, CB, cashless, etc.)
- La ventilation TVA (base HT + montant TVA par taux)
- La date et l'heure de la clôture

### Comment transformer un Z en écritures comptables

Pour chaque ticket Z, on génère **une écriture comptable équilibrée**.
Voici un exemple réaliste pour un bar/resto (comptes du jeu "Bar/Restaurant") :

```
DEBIT  5300000   Paiement Espèces          150,00   ← total encaissé en espèces
DEBIT  51120001  Paiement CB               320,00   ← total encaissé en CB
DEBIT  51120002  Paiement Tickets Resto      45,00   ← total en titres-resto
                                            -------
                                             515,00   ← TOTAL DEBITS

CREDIT 7072000   Boissons à 20%            250,00   ← HT boissons 20%
CREDIT 445712    TVA 20%                     50,00   ← TVA sur boissons 20%
CREDIT 7071000   Boissons à 10%            100,00   ← HT boissons 10%
CREDIT 445710    TVA 10%                     10,00   ← TVA sur boissons 10%
CREDIT 7011000   Alimentaire à 10%          90,91   ← HT alimentaire 10%
CREDIT 445710    TVA 10%                      9,09   ← TVA sur alimentaire 10%
CREDIT 709000    Remises                     -5,00   ← remises accordées (négatif)
CREDIT 758000    Écart de gestion +          10,00   ← fond de caisse en trop
                                            -------
                                             515,00   ← TOTAL CREDITS (= DEBITS)
```

L'écriture est **toujours équilibrée** : total des débits = total des crédits.

### Granularité de la ventilation

Le Z est ventilé par catégorie d'article (chacune ayant son propre
compte de vente et son taux de TVA), pas par produit individuel.
L'algorithme de génération des écritures est :

```
POUR CHAQUE ticket Z de la période d'export :
    numero_ecriture = generer_numero_sequentiel()

    # --- DEBITS : un par moyen de paiement utilisé ---
    POUR CHAQUE moyen_de_paiement ayant un montant > 0 :
        mapping = MappingMoyenDePaiement.get(moyen_de_paiement)
        creer_ligne_debit(mapping.compte_de_tresorerie, montant)

    # --- CREDITS : un par catégorie de vente ---
    POUR CHAQUE categorie ayant des ventes :
        mapping = MappingCategorieVersCompte.get(categorie)
        montant_ht = calculer_ht(total_ttc, taux_tva)
        montant_tva = total_ttc - montant_ht
        creer_ligne_credit(mapping.compte_de_vente, montant_ht)
        creer_ligne_credit(compte_tva_correspondant, montant_tva)

    # --- CREDITS/DEBITS SPECIAUX ---
    SI remises > 0 :
        creer_ligne_credit(comptes_speciaux.compte_remises, remises)
    SI ecart_caisse != 0 :
        SI ecart > 0 : creer_ligne_credit(comptes_speciaux.compte_ecart_positif, ecart)
        SI ecart < 0 : creer_ligne_debit(comptes_speciaux.compte_ecart_negatif, abs(ecart))

    verifier_equilibre(total_debits == total_credits)
```

---

## Conventions de code (rappel DJC)

- **Noms de variables en français, très explicites** : `total_des_ventes_en_especes`, pas `cash_total`
- **Commentaires bilingues FR/EN** : français détaillé + une ligne anglais
- **ViewSet explicite** (pas de ModelViewSet)
- **Pas de magic** : pas de metaclass, pas de decorators qui cachent la logique
- **Admin Unfold** : lire le skill `/mnt/skills/user/unfold/SKILL.md` avant de créer des ModelAdmin
- **Tests** : lire `tests/TESTS_README.md` avant d'écrire des tests
- **Multi-tenant** : les modèles vivent dans le schema du tenant (pas en public).
  Utiliser `tenant_context(tenant)` pour tout `create()` ou appel qui accède au tenant.

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

| Logiciel | Meilleur chemin | Séparateur | Décimal | Date | En-têtes | Particularité |
|---|---|---|---|---|---|---|
| **Sage 50** | FEC ou CSV `;` | `;` | `.` | JJ/MM/AAAA | Non | Import paramétrable, mapping manuel |
| **Sage 100** | FEC ou CSV | configurable | configurable | configurable | configurable | Très flexible |
| **EBP classique** | CSV dédié | `,` | `.` | JJMMAA | Non (L1=commentaire) | Montant+Sens, guillemets sur libellé |
| **EBP Hubbix** | FEC natif | `\t` | `,` | AAAAMMJJ | Oui | Auto-mapping des colonnes FEC |
| **PennyLane** | FEC natif | `\t` | `,` | AAAAMMJJ | Oui | Code journal = lettres uniquement |
| **Odoo** | FEC natif | `\t` | `,` | AAAAMMJJ | Oui | Comptes tronqués à 6 chiffres |
| **Dokos** | CSV générique | configurable | `.` | AAAA-MM-JJ | Oui | Fork ERPNext, pas d'import FEC natif |
| **Dolibarr** | CSV ou FEC | `,` | `.` ⚠️ | AAAA-MM-JJ | Oui | Piège : décimal = point obligatoire |
| **Paheko** | FEC natif ou simplifié | `;` | `,` | JJ/MM/AAAA | Oui | 4 formats (simplifié/complet/groupé/FEC) |

### Conclusion opérationnelle

**Priorité 0** : Modèles `CompteComptable` + `MappingCategorieVersCompte` +
`MappingMoyenDePaiement` + `MappingComptesSpeciaux` + admin Unfold + fixtures.

**Priorité 1** : Générateur FEC utilisant ces mappings. Couvre directement :
EBP Hubbix, PennyLane, Odoo, Paheko, Sage (via import paramétrable).

**Priorité 2** : Profils CSV dédiés pour EBP classique, Dolibarr, Dokos, vieux Sage.

→ Implémenter dans cet ordre. Le mapping (P0) est le pré-requis de tout le reste.
