# HT de chaque ligne de caisse calculé sur toute la ligne / Line HT computed on the whole line

**Date :** 2026-09-27
**Migration :** Non

## Resume / Summary

**Quoi / What :** le HT stocké sur chaque ligne de vente de la caisse
(`LigneArticle.total_ht`, donnée élémentaire LNE exigence 3) est calculé sur le TTC de
la ligne (`amount × qty`, arrondi comme les rapports) au lieu du prix d'un seul article. /
The HT stored on each register line is computed on the line total (`amount × qty`).

**Pourquoi / Why :** 3 bières à 5 € TTC (TVA 20 %) stockaient un HT de 4,17 € au lieu de
12,50 €. Ce HT est scellé dans l'empreinte HMAC et exporté dans l'archive fiscale, qui en
déduisait une TVA de 10,83 € au lieu de 2,50 €. Les totaux HT/TVA du ticket Z n'étaient
pas touchés (ils sont recalculés depuis le TTC). /
3 beers at 5 € stored 4.17 € HT instead of 12.50 €; the fiscal archive derived a wrong VAT.

Chantier : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-04-B-ht-fois-quantite.md`.
Seules les nouvelles lignes changent : les empreintes existantes sont relues avec la
valeur stockée. Aucune ligne existante n'est modifiée.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_creer_lignes_articles` et `_creer_lignes_articles_cascade` : HT sur `amount × qty` (`ROUND_HALF_UP`) |
| `tests/pytest/test_total_ht_ligne.py` | nouveau (schéma dédié) : ligne à quantité 3, parts d'une cascade, archive fiscale, chaîne HMAC |
| `tests/pytest/test_integrity_hmac.py` | formule du HT alignée sur le code (`amount × qty`, `ROUND_HALF_UP`) ; lignes à `qty = 1` : résultat inchangé |

### Tests vus échouer puis mutations
Avant correctif : HT 417 au lieu de 1250 ; parts d'une cascade 833 / 833 au lieu de
500 / 333 ; archive : TVA 1083 au lieu de 250. La chaîne HMAC était déjà valide
(non-régression).

| Mutation du code de production | Test qui tombe |
|---|---|
| `_creer_lignes_articles` : HT sur `amount` seul | `test_le_ht_d_une_ligne_porte_sur_toute_la_quantite`, `test_l_archive_fiscale_deduit_la_bonne_tva_de_la_ligne` |
| `_creer_lignes_articles_cascade` : HT sur `amount` seul | `test_le_ht_des_parts_d_un_paiement_en_cascade` |

Chaque mutation restaurée, empreinte sha256 vérifiée.

---

## Comment tester (a la main) / Manual test

### Test 1 — quantité 3
1. Caisse : vendre 3 × un article à 5,00 € (produit à TVA 20 %) en espèces.
2. Admin → Lignes comptables : la ligne a `Total HT` = 12,50 €.
3. Exporter l'archive fiscale de la journée : colonne TVA de la ligne = 2,50 €.

### Test 2 — intégrité
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py verify_integrity
```
Attendu : chaîne LABOUTIK valide.
