# Total d'une ligne arrondi, jamais tronqué / Line total rounded, never truncated

**Date :** 2026-09-28
**Migration :** Non

## Resume / Summary

**Quoi / What :** `LigneArticle.total()` arrondit `amount × qty` au centime le plus proche
(half-up, comme `Round()` de PostgreSQL dans les rapports) au lieu de le tronquer. Le détail
d'une vente à la caisse utilise `total()`, et la liste des ventes arrondit sa somme. /
`LigneArticle.total()` rounds half-up instead of truncating; the POS sale detail and the
sales list round too.

**Pourquoi / Why :** un article payé par deux moyens donne deux lignes au même prix unitaire
et à des quantités à 6 décimales. 3 jus à 3,50 € (5,50 € CB + 5,00 € monnaie locale) :
350 × 1,571429 = 550,00015 et 350 × 1,428571 = 499,99985. Tronqué, 499,99985 donnait
4,99 € : l'admin (liste et fiche des lignes, export des lignes) affichait 5,50 + 4,99, et le
détail de la vente à la caisse **10,49 €** pour 10,50 €. Les données en base et les rapports
(Z, X, FEC : somme puis arrondi en SQL) étaient justes. /
Truncation showed 4.99 € and a 10.49 € sale detail; stored data and reports were right.

**Rustine :** un cas limite reste possible (deux parts à exactement « ,5 » centime, arrondies
chacune vers le haut → +1 centime ligne par ligne). La résolution de fond (montant entier
stocké par ligne, répartition entière « Money.allocate ») est un chantier à part, à
spécifier avant la fiche 04-F (chaînage HMAC).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `LigneArticle.total()` : arrondi half-up (sert à l'admin, à l'export des lignes, aux remboursements) |
| `laboutik/views.py` | `detail_vente` : `ligne.total()` ; `liste_ventes` : somme arrondie |
| `tests/pytest/test_vente_en_points.py` | 3 tests (total de ligne, détail de la vente, liste filtrée sur la monnaie locale) |

Non modifié : `comptabilite/services.py` (compta en ligne, `int(Sum)`), quantités entières
en pratique ; repris par le chantier « montants entiers ».

Avant correctif : 3 tests rouges (« 10,49 € »). Mutations (3, toutes détectées) : `total()`
tronqué, détail recalculé en tronquant, somme de la liste tronquée. `make test` 2073 passed.

---

## Comment tester (a la main) / Manual test

1. Caisse : un article à 3,50 € ×3, carte NFC avec 5,00 € de monnaie locale, complément en CB.
2. Ventes → détail de la vente : total 10,50 €, lignes 5,50 € et 5,00 €.
3. Admin → lignes de vente : 5,50 et 5,00 (plus 4,99).
