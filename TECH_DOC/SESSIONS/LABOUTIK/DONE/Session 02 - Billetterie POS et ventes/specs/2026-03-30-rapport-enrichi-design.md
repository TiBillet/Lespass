# Design Spec — Enrichissement rapports comptables + templates admin

> Date : 2026-03-30
> Statut : EN REVUE
> Depend de : Session 15 (mode ecole + exports admin)
> Objectif : combler les manques identifies par comparaison avec le legacy LaBoutik

---

## 1. Contexte

La session 15 a livre les exports (PDF/CSV/Excel) et la vue detail HTML du rapport
dans l'admin. L'analyse du code legacy (`OLD_REPOS/LaBoutik/administration/ticketZ.py`)
revele des donnees manquantes et un rendu trop generique (sections en `pprint`).

Ce design couvre 7 ameliorations :
1. Tableaux structures pour toutes les sections du template admin et PDF
2. Quantites offertes (cadeaux) dans le detail des ventes
3. Prix d'achat et benefice estime sur les articles POS
4. Statistiques cartes detaillees (medianes, moyennes, soldes)
5. Noms des monnaies dans les totaux par moyen de paiement
6. Affichage en euros (pas en centimes) via filtre template
7. Nettoyage i18n (toutes les strings en `_()` / `{% translate %}`)

---

## 2. Decisions

| Sujet | Decision | Raison |
|-------|----------|--------|
| `prix_achat` | `IntegerField(default=0)` en centimes sur Product | Coherent avec convention "centimes partout" |
| Affichage euros | Filtre template `|euros` dans `laboutik_filters.py` | JSON reste en centimes (pas de perte de precision), conversion a l'affichage |
| Symbole monnaie | Lu depuis `Configuration.currency_code` (existant) | Pas de nouveau champ |
| Noms monnaies cashless | Depuis `fedow_core.Asset` (TLF, TNF) | Deja en production |
| Stats cartes | Via `fedow_core.Token` pour soldes, `LigneArticle` pour depenses | Wallets deja en service |
| Sections template | Tableaux HTML inline styles (pas de Tailwind) | Contrainte Unfold |
| i18n | Tout en `_()` / `{% translate %}` | Regle du projet |

---

## 3. Nouveau champ modele

### 3.1 `prix_achat` sur Product

```python
# BaseBillet/models.py, dans la section POS fields
prix_achat = models.IntegerField(
    default=0,
    verbose_name=_("Purchase price (cents)"),
    help_text=_(
        "Prix d'achat unitaire en centimes. Utilise pour le calcul du benefice "
        "estime dans les rapports de cloture. Uniquement pour les articles POS. "
        "/ Unit purchase price in cents. Used for estimated profit calculation "
        "in closure reports. POS articles only."
    ),
)
```

Migration simple, default=0, pas de data migration.
Visible dans l'admin POSProduct (fieldset "POS").

---

## 4. Filtre template `|euros`

Fichier : `laboutik/templatetags/laboutik_filters.py`

```python
@register.filter
def euros(centimes):
    """
    Convertit des centimes (int) en affichage euros.
    12750 → "127,50 €"
    0 → "0,00 €"
    -500 → "-5,00 €"
    """
    config = Configuration.get_solo()
    symbole = "€" if config.currency_code == "EUR" else config.currency_code
    valeur = centimes / 100
    return f"{valeur:,.2f} {symbole}".replace(",", " ").replace(".", ",")
```

Le separateur de milliers est un espace, le separateur decimal une virgule (convention FR).
Pour EN, on pourra ajouter un parametre de locale plus tard. Pour l'instant FR.

---

## 5. Enrichissement `RapportComptableService`

### 5.1 `calculer_totaux_par_moyen()` — noms monnaies

Structure actuelle :
```python
{"especes": int, "carte_bancaire": int, "cashless": int, "cheque": int, "total": int}
```

Structure enrichie :
```python
{
    "especes": int,
    "carte_bancaire": int,
    "cashless": int,
    "cashless_detail": [
        {"nom": "Monnaie locale Reunion", "code": "MLR", "montant": int},
        {"nom": "Cadeau Festival", "code": "CAD", "montant": int},
    ],
    "cheque": int,
    "total": int,
    "currency_code": "EUR",
}
```

Le `cashless_detail` est obtenu en joignant `LigneArticle.asset` → `fedow_core.Asset.name`.
Le `cashless` total reste inchange (somme des montants cashless).

### 5.2 `calculer_detail_ventes()` — qty offerts + prix achat + benefice

Structure actuelle par article :
```python
{"nom": str, "qty": float, "total_ttc": int, "total_ht": int, "total_tva": int, "taux_tva": float}
```

Structure enrichie :
```python
{
    "nom": str,
    "qty_vendus": float,      # paye en euros/CB/cheque
    "qty_offerts": float,     # paye en LOCAL_GIFT / EXTERIEUR_GIFT
    "qty_total": float,       # vendus + offerts
    "total_ttc": int,
    "total_ht": int,
    "total_tva": int,
    "taux_tva": float,
    "prix_achat_unit": int,   # Product.prix_achat (centimes)
    "cout_total": int,        # prix_achat * qty_total
    "benefice": int,          # total_ht - cout_total
}
```

`qty_offerts` = lignes payees via `LOCAL_GIFT` ou `EXTERIEUR_GIFT`.
`prix_achat_unit` lu depuis `Product.prix_achat` via le join existant.
`benefice = total_ht - cout_total` (estimation brute, pas de charges).

Le champ `prix_achat` n'est pertinent que pour `methode_caisse=VENTE`.
Pour les recharges/adhesions, `prix_achat_unit=0` et `benefice=total_ht`.

### 5.3 `calculer_habitus()` — statistiques cartes enrichies

Structure actuelle :
```python
{"nb_cartes": int, "total": int, "panier_moyen": int}
```

Structure enrichie :
```python
{
    "nb_cartes": int,
    "total": int,
    "panier_moyen": int,
    "recharge_mediane": int,        # mediane du total recharge par carte
    "depense_mediane": int,         # mediane du total depense par carte
    "reste_moyenne": int,           # solde moyen des wallets (via Token)
    "med_on_card": int,             # mediane des soldes des wallets
    "nouveaux_membres": int,        # Membership crees dans la periode
}
```

**Medianes** : calculees en Python (pas en SQL) car PostgreSQL `PERCENTILE_CONT`
n'est pas accessible via l'ORM Django sans `RawSQL`. On recupere les totaux par carte
via `values('carte').annotate(total=Sum('amount'))` puis on calcule la mediane en Python.
Le volume est faible (nombre de cartes distinctes, pas nombre de lignes).

**`reste_moyenne` et `med_on_card`** : query sur `fedow_core.Token` filtre par
les cartes actives de la periode. `Token.value` est en centimes.

```python
from fedow_core.models import Token, Asset
# Cartes actives dans la periode
cartes_actives = self.lignes.filter(carte__isnull=False).values_list('carte', flat=True).distinct()
# Soldes des wallets lies a ces cartes (asset TLF = monnaie locale euro)
soldes = Token.objects.filter(
    wallet__carte_cashless__in=cartes_actives,
    asset__category=Asset.TLF,
).values_list('value', flat=True)
```

**`nouveaux_membres`** : `Membership.objects.filter(date_added__range=(debut, fin)).count()`

---

## 6. Template admin `cloture_detail.html` — tableaux structures

Chaque section du rapport aura un tableau HTML dedie avec styles inline.
Plus de `pprint` generique.

### Sections et colonnes

| Section | Colonnes |
|---------|---------|
| 1. Totaux par moyen | Moyen, Montant (€), avec sous-detail cashless |
| 2. Detail ventes | Categorie > Produit, Qty vendus, Qty offerts, CA HT, TVA, CA TTC, Cout, Benefice |
| 3. TVA | Taux (%), HT (€), TVA (€), TTC (€), Total |
| 4. Solde caisse | Ligne : Fond, Entrees especes, Solde final |
| 5. Recharges | Type (RE/RC/TM), Moyen paiement, Montant, Nombre |
| 6. Adhesions | Moyen paiement, Nombre, Montant |
| 7. Remboursements | Total, Nombre |
| 8. Habitus | Stat, Valeur (nb cartes, panier moyen, medianes, soldes) |
| 9. Billets | Evenement, Nombre, Montant |
| 10. Synthese | Type x Moyen (tableau croise) |
| 11. Operateurs | (placeholder) |
| 12. Ventilation PV | Point de vente, CA TTC |
| 13. Infos legales | Champ, Valeur |

Tous les montants affiches via `|euros`.
Toutes les strings en `{% translate %}`.

---

## 7. Template PDF `rapport_comptable.html` — aligne

Meme structure que le template admin mais en CSS d'impression (`@page A4`).
Utilise le meme filtre `|euros`.
Toutes les strings en `{% translate %}`.

---

## 8. Nettoyage i18n admin

Fieldsets de `ClotureCaisseAdmin` :
- `'Period'` → `_('Periode')`
- `'Totals (cents)'` → `_('Totaux')`
- `'Details'` → `_('Details')`

Toutes les strings des templates et du code admin passees en `_()` / `{% translate %}`.

---

## 9. Fichiers concernes

### Fichiers a modifier

| Fichier | Changement |
|---------|-----------|
| `BaseBillet/models.py` | Ajouter `prix_achat` sur Product |
| `laboutik/reports.py` | Enrichir 3 methodes (totaux, detail_ventes, habitus) |
| `Administration/templates/admin/cloture_detail.html` | Refaire avec tableaux structures + `|euros` |
| `laboutik/templates/laboutik/pdf/rapport_comptable.html` | Aligner sur le template admin |
| `Administration/admin/laboutik.py` | i18n fieldsets + POSProduct admin (`prix_achat`) |

### Fichiers a creer

| Fichier | Role |
|---------|------|
| `laboutik/templatetags/__init__.py` | Package templatetags |
| `laboutik/templatetags/laboutik_filters.py` | Filtre `|euros` |
| Migration Product `prix_achat` | IntegerField default=0 |

### Tests a modifier/creer

| Fichier | Changement |
|---------|-----------|
| `tests/pytest/test_exports.py` | Adapter aux nouvelles structures |
| `tests/pytest/test_mode_ecole.py` | Verifier que `prix_achat` et `qty_offerts` fonctionnent |

---

## 10. Ce qui ne change PAS

- Le `RapportComptableService` garde ses 13 methodes (pas de nouvelle methode)
- Le JSON est toujours stocke en centimes dans `rapport_json`
- Les exports CSV/Excel/PDF gardent leur mecanique (actions admin)
- Les tests existants (299 pytest + 42 E2E) ne doivent pas regresser
