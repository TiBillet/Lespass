# Design Spec — Session 20 : Export comptable (mapping + FEC)

> **Date** : 2026-04-02
> **Briefing source** : `TECH DOC/IDEAS/BRIEFING_EXPORT_COMPTABLE.md` (priorites 0 + 1)
> **Depend de** : Session 18 (archivage fiscal — pattern export admin)
> **Scope** : 2 nouveaux modeles, 1 FK ajoutee, 1 generateur FEC, fixtures, admin, doc utilisateur, 11 tests

---

## 1. Modeles

### 1.1 `CompteComptable` (nouveau, dans `laboutik/models.py`)

Un compte du plan comptable utilisable pour le mapping.
Chaque lieu a sa propre liste de comptes (multi-tenant).
TiBillet ne gere PAS un plan comptable complet : on stocke uniquement les comptes utiles pour l'export.

| Champ | Type | Contraintes | Exemple |
|-------|------|-------------|---------|
| `uuid` | UUIDField PK | default=uuid4 | — |
| `numero_de_compte` | CharField(20) | — | "7072000" |
| `libelle_du_compte` | CharField(200) | — | "Boissons a 20%" |
| `nature_du_compte` | CharField(30) | choices (voir ci-dessous) | "VENTE" |
| `taux_de_tva` | DecimalField(5,2) | null=True, blank=True | 20.00 |
| `est_actif` | BooleanField | default=True | True |

**Choices nature_du_compte** :
- `VENTE` — Compte de vente (classe 7)
- `TVA` — Compte de TVA (classe 44)
- `TRESORERIE` — Compte de tresorerie (classe 5)
- `TIERS` — Compte de tiers (classe 4)
- `CHARGE` — Compte de charge (classe 6)
- `PRODUIT_EXCEPTIONNEL` — Produit exceptionnel (classe 7)
- `SPECIAL` — Compte special (remises, ecarts, etc.)

Meta : `ordering = ['numero_de_compte']`, `verbose_name = "Compte comptable"`.

Le champ `taux_de_tva` est utilise pour deux cas :
- Sur les comptes VENTE : taux de TVA applicable aux ventes de cette categorie
- Sur les comptes TVA : le taux que ce compte collecte (permet le lookup `nature=TVA, taux_de_tva=20.00`)

### 1.2 `MappingMoyenDePaiement` (nouveau, dans `laboutik/models.py`)

Associe un code PaymentMethod a un compte comptable de tresorerie.
Plusieurs moyens peuvent pointer vers le meme compte (CB + Stripe → 512000).
Null = moyen ignore a l'export (ex: cashless NFC = argent deja encaisse lors de la recharge).

| Champ | Type | Contraintes | Exemple |
|-------|------|-------------|---------|
| `uuid` | UUIDField PK | default=uuid4 | — |
| `moyen_de_paiement` | CharField(10) | unique, codes PaymentMethod | "CA" |
| `libelle_moyen` | CharField(100) | — | "Especes" |
| `compte_de_tresorerie` | FK CompteComptable | SET_NULL, null=True, blank=True | → 530000 |

Meta : `verbose_name = "Mapping moyen de paiement"`.

### 1.3 FK `compte_comptable` sur `CategorieProduct` (modifie, dans `BaseBillet/models.py`)

Ajout d'un champ sur le modele existant `CategorieProduct` :

```python
compte_comptable = models.ForeignKey(
    'laboutik.CompteComptable', on_delete=models.SET_NULL,
    null=True, blank=True,
    verbose_name=_("Accounting code"),
    help_text=_(
        "Compte comptable de vente associe a cette categorie. "
        "Utilise pour l'export FEC et CSV comptable. "
        "/ Sales accounting code for this category. "
        "Used for FEC and CSV accounting export."
    ),
)
```

Migration BaseBillet.

---

## 2. Fixtures par defaut

### 2.1 Management command `charger_plan_comptable`

```
docker exec lespass_django poetry run python manage.py charger_plan_comptable \
    --schema=lespass --jeu=bar_resto
```

Arguments :
- `--schema` (requis) : schema tenant
- `--jeu` (requis) : `bar_resto` ou `association`
- `--reset` (optionnel) : supprime les comptes existants avant de charger

Garde : si des comptes existent deja et pas de `--reset`, affiche un warning et ne fait rien.

### 2.2 Bouton admin

Dans la page admin `CompteComptable`, un bouton HTMX "Charger un plan comptable par defaut"
qui affiche un choix (Bar/Restaurant ou Association) et appelle le ViewSet.

### 2.3 Jeu "Bar / Restaurant" (15 comptes)

| Numero | Libelle | Nature | TVA |
|--------|---------|--------|-----|
| 7072000 | Boissons a 20% | VENTE | 20.00 |
| 7071000 | Boissons a 10% | VENTE | 10.00 |
| 7011000 | Alimentaire a 10% | VENTE | 10.00 |
| 7010500 | Alimentaire a emporter 5,5% | VENTE | 5.50 |
| 51120001 | Paiement CB | TRESORERIE | — |
| 5300000 | Paiement Especes | TRESORERIE | — |
| 51120002 | Paiement Tickets Restaurants | TRESORERIE | — |
| 51120000 | Paiement en cheque | TRESORERIE | — |
| 445712 | TVA 20% | TVA | 20.00 |
| 445710 | TVA 10% | TVA | 10.00 |
| 445705 | TVA 5,5% | TVA | 5.50 |
| 709000 | Remises | SPECIAL | — |
| 5811000 | Caisse (mouvements especes) | SPECIAL | — |
| 758000 | Ecart de gestion + | PRODUIT_EXCEPTIONNEL | — |
| 658000 | Ecart de gestion - | CHARGE | — |

### 2.4 Jeu "Association / Tiers-lieu" (10 comptes)

| Numero | Libelle | Nature | TVA |
|--------|---------|--------|-----|
| 706000 | Prestations de services | VENTE | 20.00 |
| 707000 | Ventes de marchandises | VENTE | 20.00 |
| 706300 | Billetterie | VENTE | 5.50 |
| 756000 | Cotisations | VENTE | — |
| 512000 | Banque | TRESORERIE | — |
| 530000 | Caisse | TRESORERIE | — |
| 419100 | Avances clients (cashless) | TIERS | — |
| 445710 | TVA collectee 20% | TVA | 20.00 |
| 445712 | TVA collectee 5,5% | TVA | 5.50 |
| 709000 | Remises | SPECIAL | — |

---

## 3. Generateur FEC

### 3.1 Fichier : `laboutik/fec.py`

Fonction principale :

```python
def generer_fec(clotures_queryset, schema_name):
    """
    Genere un fichier FEC a partir d'un queryset de ClotureCaisse.
    Chaque cloture = 1 ecriture comptable equilibree (debits = credits).
    / Generates a FEC file from a ClotureCaisse queryset.
    Each closure = 1 balanced accounting entry (debits = credits).

    :param clotures_queryset: QuerySet de ClotureCaisse
    :param schema_name: str — pour le nom du fichier (SIREN)
    :return: tuple (bytes contenu_fec, str nom_fichier)
    """
```

### 3.2 Algorithme par cloture

Pour chaque `ClotureCaisse` dans le queryset :

1. **Numero d'ecriture** : `VE-{date_cloture_AAAAMMJJ}-{numero_sequentiel:03d}`
2. **Reference piece** : `Z-{date_cloture_AAAAMMJJ}-{numero_sequentiel:03d}`
3. **Date** : `datetime_cloture` formatee AAAAMMJJ

**Lignes DEBIT** (moyens de paiement) :
- Pour chaque moyen dans `rapport_json['totaux_par_moyen']` ayant montant > 0 :
  - Chercher `MappingMoyenDePaiement` pour ce code
  - Si mapping existe et `compte_de_tresorerie` non null : ecrire ligne debit
  - Si mapping null ou inexistant : ignorer (pas d'ecriture)
  - Montant en euros avec 2 decimales, virgule comme separateur

**Lignes CREDIT ventes** (categories) :
- Pour chaque categorie dans `rapport_json['detail_ventes']` :
  - Chercher `CategorieProduct.compte_comptable` pour cette categorie
  - Si compte existe : ecrire ligne credit avec le montant HT
  - Si pas de compte : ecrire avec un compte generique "CATEGORIE_NON_MAPPEE" (warning)

**Lignes CREDIT TVA** :
- Pour chaque taux dans `rapport_json['tva']` :
  - Chercher `CompteComptable.objects.filter(nature='TVA', taux_de_tva=taux)`
  - Ecrire ligne credit avec le montant TVA

**Verification** : `sum(debits) == sum(credits)` pour chaque ecriture.

### 3.3 Format du fichier

| Parametre | Valeur |
|-----------|--------|
| Extension | `.txt` |
| Encodage | UTF-8 |
| Separateur | Tabulation `\t` |
| Decimal | Virgule `,` |
| Dates | AAAAMMJJ (ex: `20260331`) |
| Fin de ligne | CRLF `\r\n` |
| Premiere ligne | En-tetes des 18 colonnes |
| Nom fichier | `{SIREN}FEC{AAAAMMJJ}.txt` (date = derniere cloture) |

### 3.4 Les 18 colonnes

| # | Nom | Obligatoire | Exemple |
|---|-----|-------------|---------|
| 1 | JournalCode | oui | `VE` |
| 2 | JournalLib | oui | `Journal de ventes` |
| 3 | EcritureNum | oui | `VE-20260331-001` |
| 4 | EcritureDate | oui | `20260331` |
| 5 | CompteNum | oui | `707000` |
| 6 | CompteLib | oui | `Ventes de marchandises` |
| 7 | CompAuxNum | non | `` (vide) |
| 8 | CompAuxLib | non | `` (vide) |
| 9 | PieceRef | oui | `Z-20260331-001` |
| 10 | PieceDate | oui | `20260331` |
| 11 | EcritureLib | oui | `Ventes especes du 31/03/2026` |
| 12 | Debit | oui | `150,00` ou `0,00` |
| 13 | Credit | oui | `0,00` ou `150,00` |
| 14 | EcritureLet | non | `` (vide) |
| 15 | DateLet | non | `` (vide) |
| 16 | ValidDate | oui | `20260331` |
| 17 | Montantdevise | non | `` (vide) |
| 18 | Idevise | non | `` (vide) |

---

## 4. Admin Unfold

### 4.1 `CompteComptableAdmin`

- CRUD complet (add, change, delete)
- `list_display` : numero_de_compte, libelle_du_compte, nature_du_compte, taux_de_tva, est_actif
- `list_filter` : nature_du_compte, est_actif
- `search_fields` : numero_de_compte, libelle_du_compte
- `list_before_template` : bandeau avec bouton "Charger un plan comptable par defaut"

### 4.2 `MappingMoyenDePaiementAdmin`

- CRUD complet
- `list_display` : moyen_de_paiement, libelle_moyen, compte_de_tresorerie
- Dropdown autocomplete pour le compte

### 4.3 `CategorieProduct` enrichi

Ajouter le champ `compte_comptable` dans les fieldsets de l'admin existant de `CategorieProduct`.
Autocomplete vers `CompteComptable` (filtre `nature=VENTE`).

### 4.4 Export FEC

Meme pattern que l'export fiscal (session 18) :
- Bouton HTMX dans `list_before_template` des clotures (a cote de "Export fiscal")
- GET : formulaire dates debut/fin
- POST : genere le FEC et propose le telechargement
- Warning si categories sans mapping (liste les noms)

### 4.5 Sidebar

Section "Caisse LaBoutik" : ajouter "Comptes comptables" et "Mapping moyens de paiement".

---

## 5. Validation douce

Si une categorie n'a pas de `compte_comptable`, l'export fonctionne quand meme :
- Les ventes sont regroupees sous un libelle "** CATEGORIE NON MAPPEE **"
- Le numero de compte est `000000` (invalide mais visible)
- Un avertissement est affiche dans le formulaire d'export listant les categories sans mapping
- Le gerant peut corriger et re-exporter

---

## 6. ViewSet action `charger_plan_comptable`

Dans `CaisseViewSet`, action POST qui :
1. Recoit le jeu choisi (`bar_resto` ou `association`)
2. Verifie qu'il n'y a pas deja de comptes (ou que `force=true`)
3. Cree les CompteComptable du jeu
4. Cree les MappingMoyenDePaiement par defaut
5. Retourne un message de succes

---

## 7. Documentation utilisateur

Fichier : `TECH DOC/A DOCUMENTER/export-comptable-guide-utilisateur.md`

Sections :
1. C'est quoi un compte comptable ? (explication pour debutants, debit=credit, les classes)
2. Pourquoi configurer un mapping ? (pour que le comptable importe directement)
3. Etape 1 : charger un plan comptable par defaut
4. Etape 2 : verifier/personnaliser les comptes
5. Etape 3 : mapper les categories d'articles
6. Etape 4 : mapper les moyens de paiement
7. Etape 5 : exporter le FEC
8. FAQ (cashless, remises, ecarts, categories sans mapping)

---

## 8. Tests

| Test | Ce qu'il verifie |
|------|-----------------|
| `test_compte_comptable_creation` | CRUD CompteComptable (natures, taux_de_tva) |
| `test_mapping_moyen_paiement_creation` | Liaison moyen → compte |
| `test_mapping_moyen_null_ignore` | Moyen avec compte null = pas d'ecriture |
| `test_categorie_avec_compte` | FK CategorieProduct.compte_comptable fonctionne |
| `test_charger_plan_bar_resto` | Command charge 15 comptes |
| `test_charger_plan_association` | Command charge 10 comptes |
| `test_fec_18_colonnes` | Chaque ligne a 18 champs separes par tab |
| `test_fec_equilibre_debits_credits` | Sum debits = sum credits par ecriture |
| `test_fec_format_montants_virgule` | Montants avec virgule decimale |
| `test_fec_format_dates_aaaammjj` | Dates sans separateur |
| `test_fec_categorie_non_mappee` | Export fonctionne, warning affiche |

---

## 9. Hors scope

- Profils CSV configurables (session 21)
- Modele ExportProfile (session 21)
- Import de plan comptable depuis CSV (futur)
- Comptabilite complete (grand livre, balance, bilan) — jamais, TiBillet reste un logiciel de caisse
