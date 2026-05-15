# Plan d'implémentation — S6 (Chantier 01 / App `comptabilite`) — DERNIÈRE SESSION

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.
>
> **Hub :** [`INDEX.md`](INDEX.md) — **Spec :** [`SPEC.md`](SPEC.md) §6.5, §9 (S6)
>
> **Garde-fous :**
> - **NEVER git** — maintaineur seul.
> - **Pas de `runserver_plus`** — byobu sur port 8002.
> - **Pas de `ruff format` sur existant.**

**Goal :** Finitions du chantier 01 :
1. 5 profils CSV comptables restants (Dolibarr, PennyLane, CIEL, ODOO, DOKO)
2. Management command `verify_clotures` (audit continuité + hash chain)
3. Doc utilisateur `TECH_DOC/comptabilite.md`
4. Mise à jour `tests/PIEGES.md` (2 pièges découverts)

**Tech Stack :** Pas de nouvelle techno — extensions et docs.

---

## Découpage en 3 blocs subagent

| Bloc | Tasks | Cible |
|---|---|---|
| **B1** | 5 profils dans `profils_csv.py` + 5 tests | 8 profils totaux |
| **B2** | `verify_clotures` management command + 2 tests | Audit DB |
| **B3** | Doc utilisateur + PIEGES.md | Documentation |

---

## Bloc B1 — 5 profils CSV restants

### Mapping formats (basé sur les conventions courantes des logiciels)

| Profil | Séparateur | Décimal | Encodage | Mode montant | Extension |
|---|---|---|---|---|---|
| `dolibarr` | `,` | `.` | utf-8 | DEBIT_CREDIT | `.csv` |
| `pennylane` | `;` | `,` | utf-8 | DEBIT_CREDIT | `.csv` |
| `ciel` | `\t` (tab) | `,` | cp1252 | DEBIT_CREDIT | `.txt` |
| `odoo` | `,` | `.` | utf-8 | DEBIT_CREDIT | `.csv` |
| `doko` | `;` | `,` | utf-8 | DEBIT_CREDIT | `.csv` |

Tous utilisent `DEBIT_CREDIT` (2 colonnes Debit + Credit) — c'est le mode le plus standard. Sage 50 et Paheko gardent leurs spécificités (déjà livrées en S5).

### Colonnes par profil

```python
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
```

Note : `_generer_csv_debit_credit()` actuel utilise 8 colonnes fixes
(`JournalCode, EcritureDate, CompteNum, CompteLib, PieceRef, EcritureLib, Debit, Credit`).
Pour les nouveaux profils, on **garde le même générateur** (les colonnes dans le profil sont utilisées pour le header) mais on doit s'assurer que `_generer_csv_debit_credit` mappe correctement chaque colonne du profil.

**Refactor mineur de `_generer_csv_debit_credit`** : utiliser un dict de mapping pour aligner ses sorties aux colonnes du profil.

Code adapté :

```python
def _generer_csv_debit_credit(lignes, profil, date_ecriture, piece_ref):
    """Mode DEBIT_CREDIT : 2 colonnes Debit + Credit (Sage 50, Dolibarr, PennyLane, CIEL, ODOO, DOKO)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=profil["separateur"], quoting=csv.QUOTE_MINIMAL)
    writer.writerow(profil["colonnes"])
    date_str = date_ecriture.strftime(profil["format_date"])

    # Mapping nom de colonne -> valeur. Le profil pioche dedans dans l'ordre defini.
    # / Column name -> value mapping. Profile picks in order.
    def _valeurs_ligne(ligne):
        debit_str = _decimal_str(ligne["debit_centimes"], profil["decimal"])
        credit_str = _decimal_str(ligne["credit_centimes"], profil["decimal"])
        valeurs_par_nom = {
            # Sage 50 / DOKO
            "JournalCode": "VTE", "code_journal": "VTE", "Journal": "VTE",
            "journal_id": "VTE",
            "EcritureDate": date_str, "date": date_str, "Date": date_str,
            "CompteNum": ligne["compte_num"], "compte": ligne["compte_num"],
            "Compte": ligne["compte_num"], "account_id": ligne["compte_num"],
            "CompteLib": ligne["compte_lib"], "libelle_compte": ligne["compte_lib"],
            "LibelleCompte": ligne["compte_lib"],
            "PieceRef": piece_ref, "piece": piece_ref, "Piece": piece_ref,
            "ref": piece_ref,
            "EcritureLib": ligne["libelle"], "label_operation": ligne["libelle"],
            "Libelle": ligne["libelle"], "name": ligne["libelle"],
            "Debit": debit_str, "debit": debit_str,
            "Credit": credit_str, "credit": credit_str,
        }
        return [valeurs_par_nom.get(col, "") for col in profil["colonnes"]]

    for ligne in lignes:
        writer.writerow(_valeurs_ligne(ligne))
    return buffer.getvalue()
```

### Tests : 5 nouveaux dans `test_comptabilite_csv_comptable.py`

Pour chaque profil, vérifier :
- Existe dans `PROFILS`
- Fonctionne avec `generer_csv_comptable(cloture, profil)` sans erreur
- Encodage correct
- Séparateur correct

---

## Bloc B2 — Management command `verify_clotures`

### Fichier

`comptabilite/management/commands/verify_clotures.py`

### Comportement

```
$ manage.py verify_clotures              # tous les tenants
$ manage.py verify_clotures --tenant=lespass

[tenant=lespass]
  ✓ 12 clotures, numeros 1-12 continus
  ⚠ cloture #7 : hash recalcule different (lignes modifiees post-cloture)
  ✗ trou detecte entre #9 et #11 (manque #10)

[tenant=chantefrein]
  ✓ 3 clotures, numeros 1-3 continus, hash valides
```

Pour chaque tenant :
1. Liste les clôtures par `numero_sequentiel` ASC
2. Vérifie continuité (pas de trou)
3. Pour chaque clôture, recalcule le hash via `RapportComptableService(.datetime_debut, .datetime_fin).calculer_hash_lignes()` et compare avec `cloture.hash_lignes`

### Tests

```python
def test_verify_clotures_continuite_ok(...):
    """3 clotures successives -> 'continus' dans le rapport."""

def test_verify_clotures_detecte_hash_modifie(...):
    """Modifier hash_lignes en DB -> verify detecte l'anomalie."""
```

---

## Bloc B3 — Doc utilisateur + PIEGES.md

### `TECH_DOC/comptabilite.md` (~150 lignes)

Sections :
- Vue d'ensemble (à quoi sert l'app)
- Visualiser les clôtures (admin)
- Comprendre le rapport (8 sections)
- Configurer son plan comptable
- Configurer le mapping moyens de paiement
- Exporter pour son comptable (4 formats + 8 profils)
- Configurer l'envoi auto par email
- Vérifier l'intégrité (`verify_clotures`)
- FAQ

### `tests/PIEGES.md` : 2 pièges à ajouter

1. **stdimage post_delete sur Event** : `event.delete()` crash si pas d'image. Workaround : retirer temporairement le receiver post_delete matching `id(Event)`.
2. **Pytest API_KEY workaround** : conftest tente `docker exec` depuis l'intérieur du container. Solution : `API_KEY=$(...) docker exec -e "API_KEY=$API_KEY" ...`.

---

## Commit suggéré (B3 final)

```
feat(comptabilite): S6 — 5 profils CSV restants + verify_clotures + doc

- comptabilite/profils_csv.py : +5 profils (Dolibarr, PennyLane, CIEL, ODOO, DOKO)
- comptabilite/csv_comptable.py : refactor _generer_csv_debit_credit
  (mapping colonne → valeur, supporte les 6 profils DEBIT_CREDIT)
- comptabilite/management/commands/verify_clotures.py : audit continuité
  numéros séquentiels + recalcul hash chain (per tenant ou global)
- TECH_DOC/comptabilite.md : guide utilisateur complet (vue d'ensemble,
  admin, exports, plan comptable paramétrable, FAQ)
- tests/PIEGES.md : +2 pièges (stdimage post_delete Event, pytest API_KEY)
- tests : +5 profils + 2 verify_clotures

Chantier 01 complet : S1+S2+S3+S4+S5+S6 ✅.
Référence : TECH_DOC/SESSIONS/COMPTABILITE/SPEC.md §6.5, §9 (S6).
Plan : TECH_DOC/SESSIONS/COMPTABILITE/PLAN-S6-profils-verify-doc.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Estimation

- B1 (5 profils CSV) : ~25 min
- B2 (verify_clotures) : ~30 min
- B3 (doc + PIEGES) : ~20 min

**Total : ~1h15**.
