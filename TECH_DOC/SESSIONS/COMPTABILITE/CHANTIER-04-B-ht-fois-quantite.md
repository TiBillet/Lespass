# Chantier 04-B — HT d'une ligne = HT de `amount × qty` (LNE)

> **Statut** : ✅ LIVRÉ (non commité) le 2026-09-27 — voir CHANGELOG
> Tronc commun : [`CHANTIER-04-melanges-argent.md`](CHANTIER-04-melanges-argent.md)
> Décision : D19

---

## 1. Le défaut, simplement

La certification LNE (exigence 3) demande de **stocker** le montant hors taxes (HT)
de chaque ligne de vente. Le code calcule ce HT à partir du **prix d'un seul
article**, en oubliant la quantité.

> 3 bières à 5 € TTC, TVA 20 % :
> - HT juste : 15 € / 1,2 = **12,50 €**
> - HT enregistré : 5 € / 1,2 = **4,17 €**

Ce HT faux :

- est **exporté** dans l'archive fiscale (`laboutik/archivage.py` ~l.175-179), qui
  en déduit une TVA fausse : `total_tva = amount × qty − total_ht`
  (15 € − 4,17 € = 10,83 € de « TVA ») ;
- est **scellé** dans l'empreinte HMAC de la ligne (`laboutik/integrity.py:47`).

**Ce qui n'est PAS touché** : les rapports X/Z et la clôture recalculent le HT à
partir du TTC agrégé (`laboutik/reports.py` ~l.395 et ~l.483). Leurs totaux HT et
TVA sont justes. Seule la donnée élémentaire par ligne est fausse.

## 2. Où, dans le code (vérifié le 2026-09-27)

Deux endroits identiques, dans le bloc « Chaînage HMAC » :

- `laboutik/views.py` ~l.5143, fin de `_creer_lignes_articles()` ;
- `laboutik/views.py` ~l.5448, fin de `_creer_lignes_articles_cascade()`.

```python
ligne_a_chainer.total_ht = calculer_total_ht(
    ligne_a_chainer.amount, ligne_a_chainer.vat      # ← prix unitaire seul
)
```

`calculer_total_ht(amount_ttc_centimes, taux_tva)` (`laboutik/integrity.py:167`)
attend un **TTC total** : la fonction elle-même est juste.

## 3. Le correctif

Passer le TTC de la ligne, arrondi au centime « loin de zéro », comme `Round()` de
PostgreSQL dans les rapports (le `round()` de Python arrondit au pair) :

```python
# Le HT porte sur le TTC de la LIGNE (prix unitaire x quantite), pas sur un seul
# article. Arrondi comme montant_ttc_centimes() des rapports (0,5 -> 1).
# / HT is computed on the LINE total (unit price x qty), not on a single item.
ttc_de_la_ligne_centimes = int(
    Decimal(ligne_a_chainer.amount * ligne_a_chainer.qty).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
)
ligne_a_chainer.total_ht = calculer_total_ht(ttc_de_la_ligne_centimes, ligne_a_chainer.vat)
```

Aux deux endroits. La fiche F (chaînage tireuse et QR/NFC) réutilise la même
formule.

**Effet sur la chaîne HMAC** : seules les **nouvelles** lignes changent. Les
anciennes gardent leur `total_ht` et leur empreinte : `verifier_chaine()` recalcule
l'empreinte avec la valeur **stockée**, pas avec une valeur recalculée. On ne migre
aucune ligne (dev, et une migration casserait la chaîne).

## 4. Tests

### 4.1 Tests existants — aucun ne fait échouer le défaut

| Test | Ce qu'il vérifie | Pourquoi il ne voit pas le défaut |
|---|---|---|
| `test_integrity_hmac.py` → `TestTotalHT` (~l.124-141) | `calculer_total_ht(1200, 20) == 1000` | teste la fonction seule, pas son appel |
| `test_integrity_hmac.py` ~l.178, ~l.215 | chaîne de lignes | **recopie la formule fautive** (`calculer_total_ht(ligne.amount, ligne.vat)`) |
| `test_pos_retour_consigne.py` ~l.673 | `total_ht == -83` | ligne avec `qty = 1` |

### 4.2 Tests à écrire (rouges sur le code actuel)

| # | Scénario (vente réelle par la vue de paiement) | Assertion |
|---|---|---|
| B1 | espèces, 3 × article à 500 cts, TVA 20 % (`_creer_lignes_articles`) | `ligne.total_ht == 1250` (aujourd'hui 417) |
| B2 | NFC, article à 1000 cts TVA 20 % payé en cascade TNF 600 + TLF 400 (`_creer_lignes_articles_cascade`) | `total_ht` 500 et 333, `Σ == 833` (aujourd'hui 1666) |
| B3 | archive fiscale de B1 (`archivage.py`), ligne retrouvée **par son uuid** (base partagée) | colonne `total_tva_centimes == 250` (aujourd'hui 1083) |
| B4 | chaîne HMAC après B1 | `verifier_chaine()` valide (**vert aujourd'hui** : non-régression) |

Les tests `test_integrity_hmac.py` ~l.178 et ~l.215 créent des lignes `qty = 1` :
les deux formules y donnent le même résultat. On les aligne sur le code par
propreté, sans effet sur leur résultat.

**Preuve en base** : 7 lignes LABOUTIK chaînées ont `qty ≠ 1`. Exemple :
`amount 500, qty 0,2, vat 0` → `total_ht` stocké 500 au lieu de 100.

### 4.3 Mutations à jouer

| Mutation | Test qui doit tomber |
|---|---|
| retour à `calculer_total_ht(ligne_a_chainer.amount, ...)` dans `_creer_lignes_articles` | B1, B3 |
| idem dans `_creer_lignes_articles_cascade` | B2 |

## 5. Fichiers touchés

| Fichier | Changement |
|---|---|
| `laboutik/views.py` | 2 appels à `calculer_total_ht` |
| `tests/pytest/test_integrity_hmac.py` | formule alignée |
| nouveau test (ou `test_cloture_export.py`) | B1-B4 |

Pas de migration.
