# Session 21 — Profils CSV comptables : Plan d'implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter 5 profils CSV comptables (Sage, EBP, Dolibarr, Paheko, PennyLane) en refactorisant la logique de ventilation commune avec le FEC.

**Architecture:** Extraire la ventilation comptable dans `laboutik/ventilation.py`, refactoriser `fec.py` pour l'utiliser, creer `profils_csv.py` (5 profils en dur) et `csv_comptable.py` (generateur), ajouter boutons admin (bandeau + vue detail).

**Tech Stack:** Django 4.2, django-tenants, csv, io, Unfold admin, HTMX.

**Spec:** `TECH DOC/Laboutik sessions/Session 02 - Billetterie POS et ventes/specs/2026-04-03-profils-csv-comptable-design.md`

---

## Fichiers

| Action | Fichier | Responsabilite |
|--------|---------|----------------|
| Creer | `laboutik/ventilation.py` | Logique de ventilation commune (debits/credits depuis rapport_json) |
| Modifier | `laboutik/fec.py` | Refactoriser pour utiliser ventilation.py |
| Creer | `laboutik/profils_csv.py` | 5 profils en dur (dict Python) |
| Creer | `laboutik/csv_comptable.py` | Generateur CSV comptable configurable |
| Modifier | `laboutik/views.py` | Action ViewSet export_csv_comptable |
| Modifier | `Administration/admin/laboutik.py` | URL exporter-csv-comptable + methode |
| Creer | `Administration/templates/admin/cloture/export_csv_comptable_form.html` | Formulaire HTMX (dates + dropdown profil) |
| Modifier | `Administration/templates/admin/cloture/changelist_before.html` | Bouton "Export CSV comptable" |
| Modifier | `Administration/templates/admin/cloture/rapport_before.html` | Bouton "CSV compta" par cloture |
| Creer | `tests/pytest/test_profils_csv_comptable.py` | 8 tests |

---

## Task 1 : Extraire la ventilation dans `laboutik/ventilation.py`

**Files:**
- Create: `laboutik/ventilation.py`

- [ ] **Step 1: Creer ventilation.py**

Extraire la logique de ventilation depuis `fec.py` (lignes 146-310). Le module expose 3 fonctions :

1. `charger_mappings_paiement()` → dict {code: MappingMoyenDePaiement}
2. `charger_comptes_tva()` → dict {"20.00%": CompteComptable}
3. `ventiler_cloture(cloture, mappings_paiement, categories_par_nom, comptes_tva)` → tuple (list[dict], list[str])

Chaque dict dans la liste retournee :
```python
{
    "sens": "D" ou "C",
    "numero_compte": str,
    "libelle_compte": str,
    "montant_centimes": int,
    "libelle_ecriture": str,
}
```

Le contenu de `ventiler_cloture` est exactement les lignes 190-310 de `fec.py` actuellement, mais au lieu de generer des lignes FEC formatees, on retourne des dicts bruts.

Aussi : `charger_categories_par_nom()` → dict {nom: CategorieProduct} (extrait depuis fec.py ligne 156-158).

Et la constante `CLE_RAPPORT_VERS_CODE_PAIEMENT` (extrait depuis fec.py ligne 49-54).

- [ ] **Step 2: Verifier l'import**

```bash
docker exec lespass_django poetry run python -c "from laboutik.ventilation import ventiler_cloture, charger_mappings_paiement, charger_comptes_tva, charger_categories_par_nom; print('OK')"
```

---

## Task 2 : Refactoriser `fec.py` pour utiliser `ventilation.py`

**Files:**
- Modify: `laboutik/fec.py`

- [ ] **Step 1: Refactoriser generer_fec()**

Remplacer les lignes 146-310 de `fec.py` par des appels a `ventilation.py` :

```python
from laboutik.ventilation import (
    charger_mappings_paiement,
    charger_comptes_tva,
    charger_categories_par_nom,
    ventiler_cloture,
)

def generer_fec(clotures_queryset, schema_name):
    # ... (SIREN, etc. — inchange)

    mappings_paiement = charger_mappings_paiement()
    categories_par_nom = charger_categories_par_nom()
    comptes_tva = charger_comptes_tva()

    for seq, cloture in enumerate(clotures, start=1):
        date_cloture_str = _formater_date(cloture.datetime_cloture)
        numero_ecriture = f"VE-{date_cloture_str}-{seq:03d}"
        reference_piece = f"Z-{date_cloture_str}-{seq:03d}"

        lignes_ventilation, avert_cloture = ventiler_cloture(
            cloture, mappings_paiement, categories_par_nom, comptes_tva,
        )
        avertissements.extend(avert_cloture)

        for ligne_v in lignes_ventilation:
            if ligne_v["sens"] == "D":
                debit = ligne_v["montant_centimes"]
                credit = 0
            else:
                debit = 0
                credit = ligne_v["montant_centimes"]

            ligne_fec = _generer_ligne_fec(
                journal_code=journal_code,
                journal_lib=journal_lib,
                numero_ecriture=numero_ecriture,
                date_ecriture=date_cloture_str,
                numero_compte=ligne_v["numero_compte"],
                libelle_compte=ligne_v["libelle_compte"],
                reference_piece=reference_piece,
                date_piece=date_cloture_str,
                libelle_ecriture=ligne_v["libelle_ecriture"],
                debit_centimes=debit,
                credit_centimes=credit,
                date_validation=date_cloture_str,
            )
            lignes.append(ligne_fec)
    # ... (assemblage fichier — inchange)
```

Supprimer de `fec.py` : `CLE_RAPPORT_VERS_CODE_PAIEMENT`, les imports `MappingMoyenDePaiement`, `CategorieProduct`, `CompteComptable` (maintenant dans ventilation.py). Garder `Configuration` pour le SIREN.

- [ ] **Step 2: Verifier que les tests FEC existants passent toujours**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_export_comptable.py -v
```

Les 11 tests doivent passer sans modification — la refactorisation ne change pas le comportement.

---

## Task 3 : Creer `laboutik/profils_csv.py`

**Files:**
- Create: `laboutik/profils_csv.py`

- [ ] **Step 1: Creer le module avec les 5 profils**

Chaque profil est un dict avec : nom, separateur, decimal, format_date (strftime), entetes (bool), encodage, extension, mode_montant (DEBIT_CREDIT / MONTANT_SENS / MONTANT_UNIQUE), colonnes (list[str]).

Les 5 profils : sage_50, ebp, dolibarr, paheko, pennylane.

Details exacts dans la spec section 2.

- [ ] **Step 2: Verifier**

```bash
docker exec lespass_django poetry run python -c "from laboutik.profils_csv import PROFILS; print(list(PROFILS.keys()))"
```

Expected: `['sage_50', 'ebp', 'dolibarr', 'paheko', 'pennylane']`

---

## Task 4 : Creer `laboutik/csv_comptable.py`

**Files:**
- Create: `laboutik/csv_comptable.py`

- [ ] **Step 1: Creer le generateur**

Fonction principale `generer_csv_comptable(clotures_queryset, profil_nom, schema_name)` → tuple (bytes, nom_fichier, avertissements).

La fonction :
1. Recupere le profil depuis `PROFILS[profil_nom]`
2. Appelle `charger_mappings_paiement()`, `charger_categories_par_nom()`, `charger_comptes_tva()`
3. Pour chaque cloture : `ventiler_cloture()` → liste de dicts
4. Pour chaque dict : formater selon le profil

Fonctions internes :
- `_formater_montant_csv(centimes, decimal_sep)` → str ("150.00" ou "150,00")
- `_formater_date_csv(dt, format_str)` → str
- `_formater_ligne(ligne_ventilation, profil, metadata_cloture)` → list[str] (une cellule par colonne)

Les 3 modes de montant :
- **DEBIT_CREDIT** : colonnes `debit` et `credit` (Sage, Dolibarr, PennyLane)
- **MONTANT_SENS** : colonnes `montant` et `sens` = "D"/"C" (EBP)
- **MONTANT_UNIQUE** : colonnes `compte_debit`, `compte_credit`, `montant` (Paheko)

Metadata par cloture (passee au formateur) :
```python
{
    "numero_ecriture": f"VE-{date_str}-{seq:03d}",
    "reference_piece": f"Z-{date_str}-{seq:03d}",
    "date_cloture": cloture.datetime_cloture,
    "journal_code": "VE",
    "journal_lib": "Journal de ventes",
    "numero_ligne": compteur_global,  # Pour EBP
}
```

- [ ] **Step 2: Verifier l'import**

```bash
docker exec lespass_django poetry run python -c "from laboutik.csv_comptable import generer_csv_comptable; print('OK')"
```

---

## Task 5 : Boutons admin (bandeau + vue detail + ViewSet)

**Files:**
- Modify: `laboutik/views.py` — action `export_csv_comptable`
- Modify: `Administration/admin/laboutik.py` — URL `exporter-csv-comptable` + methode
- Create: `Administration/templates/admin/cloture/export_csv_comptable_form.html`
- Modify: `Administration/templates/admin/cloture/changelist_before.html` — bouton bandeau
- Modify: `Administration/templates/admin/cloture/rapport_before.html` — bouton vue detail

- [ ] **Step 1: Action ViewSet export_csv_comptable**

Dans `CaisseViewSet`, ajouter :

```python
@action(detail=False, methods=["get", "post"], url_path="export-csv-comptable", url_name="export_csv_comptable")
def export_csv_comptable(self, request):
```

GET HTMX → template `admin/cloture/export_csv_comptable_form.html` (dates + dropdown profil)
POST → generer le CSV via `generer_csv_comptable()`, retourner HttpResponse attachment

Le dropdown profil envoie `profil` dans le POST (sage_50, ebp, dolibarr, paheko, pennylane).

- [ ] **Step 2: Template formulaire HTMX**

Meme pattern que `export_fec_form.html` : dates optionnelles + dropdown profil (5 options).
Classes Unfold internes. Animation fadeSlideIn.

- [ ] **Step 3: URL admin pour export par cloture**

Dans `ClotureCaisseAdmin.get_urls()`, ajouter :

```python
path('<path:object_id>/exporter-csv-comptable/',
     self.admin_site.admin_view(self.exporter_csv_comptable),
     name='laboutik_cloturecaisse_exporter_csv_comptable'),
```

La methode `exporter_csv_comptable(self, request, object_id)` :
- GET : retourne un mini formulaire HTML avec juste le dropdown profil
- POST : genere le CSV pour cette seule cloture

- [ ] **Step 4: Bouton dans changelist_before.html**

Ajouter un 3e bouton "Export CSV comptable" dans le bandeau des clotures, a cote de "Export fiscal" et "Export FEC". `hx-get` vers `/laboutik/caisse/export-csv-comptable/`.

- [ ] **Step 5: Bouton dans rapport_before.html**

Ajouter un bouton "CSV compta" a cote de CSV/PDF/Excel/FEC dans la vue detail. Lien vers `../exporter-csv-comptable/` avec un query param `?profil=sage_50` par defaut (le formulaire permet de changer).

Pour simplifier, le bouton va directement vers le mini formulaire de choix du profil (GET), puis le formulaire fait le POST de telechargement.

- [ ] **Step 6: Injecter l'URL dans changelist_view**

Ajouter `extra_context['export_csv_comptable_url'] = '/laboutik/caisse/export-csv-comptable/'` dans `ClotureCaisseAdmin.changelist_view`.

- [ ] **Step 7: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 6 : Tests

**Files:**
- Create: `tests/pytest/test_profils_csv_comptable.py`

8 tests FastTenantTestCase :

1. **test_ventiler_cloture_debits_credits** — `ventiler_cloture()` retourne des lignes equilibrees (sum D = sum C)
2. **test_ventiler_cloture_cashless_4191** — Cashless LE mappe vers 4191 apparait en debit
3. **test_csv_sage_separateur_point_virgule** — Sage 50 : contenu utilise `;`
4. **test_csv_ebp_montant_sens** — EBP : colonnes montant + sens D/C
5. **test_csv_dolibarr_decimal_point** — Dolibarr : decimal = `.`
6. **test_csv_paheko_montant_unique** — Paheko : compte_debit + compte_credit + montant
7. **test_csv_pennylane_code_journal_lettres** — PennyLane : code journal = lettres
8. **test_fec_utilise_ventilation** — FEC refactorise produit le meme resultat qu'avant

setUp : meme pattern que test_export_comptable.py (ClotureCaisse avec rapport_json, CompteComptable charges via fixture, MappingMoyenDePaiement).

- [ ] **Step 1: Creer le fichier de test**

- [ ] **Step 2: Lancer**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_profils_csv_comptable.py -v
```

- [ ] **Step 3: Non-regression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_export_comptable.py tests/pytest/test_profils_csv_comptable.py -v
```

---

## Task 7 : Verification finale

- [ ] **Step 1: Ruff**

```bash
docker exec lespass_django poetry run ruff check laboutik/ventilation.py laboutik/fec.py laboutik/profils_csv.py laboutik/csv_comptable.py laboutik/views.py Administration/admin/laboutik.py
```

- [ ] **Step 2: Django check**

```bash
docker exec lespass_django poetry run python manage.py check
```

- [ ] **Step 3: Tests complets laboutik**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_export_comptable.py tests/pytest/test_profils_csv_comptable.py tests/pytest/test_archivage_fiscal.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_envoi_rapports_version.py -v
```
