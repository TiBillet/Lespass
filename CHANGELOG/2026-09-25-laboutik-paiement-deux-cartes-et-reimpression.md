# LaBoutik : paiement à deux cartes puis reste en espèces / CB, et ré-impression / LaBoutik: two-card payment then cash / CC remainder, and reprint

**Date :** 2026-09-25
**Migration :** Non
**Commit :** `56425264`

## Resume / Summary

### 1. Deux cartes insuffisantes, puis le reste en espèces ou en CB
**Quoi / What :** exemple, 15 € d'articles, carte 1 à 6 €, carte 2 à 8 €, reste 1 €.
- **Espèces :** « Somme donnée insuffisante » alors que le client donnait assez.
- **CB :** la vente passait, mais **la carte 2 n'était jamais débitée** et la compta
  enregistrait **9 € en CB** alors que le caissier encaissait 1 € au terminal.
  L'écran de succès n'affichait que la carte 1.
/ Cash was refused; CC went through but card 2 was never debited and 9 € was booked as CC.

**Pourquoi / Why :** le 2e écran « reste à payer » ne renvoyait que la carte 1. La branche
espèces / CB de `payer_complementaire()` recalculait donc le paiement avec la carte 1 seule.
/ The second remainder screen only sent card 1 back.

**Correction / Fix :** l'écran renvoie `tag_id_carte2` (champ caché) et affiche la ligne
« Payé par la carte ·· XXXX » de la carte 2. Côté serveur, espèces / CB avec une carte 2
repassent par la branche 2e carte : les DEUX cartes sont débitées, le reste est enregistré
en espèces / CB, la somme donnée est vérifiée AVANT tout débit, la monnaie à rendre est
calculée sur le vrai reste.
/ The screen sends card 2 back; the server debits both cards then books the rest.

### 2. Ré-imprimer un ticket depuis l'écran Ventes
**Quoi / What :** « Ré-imprimer » répondait toujours « Donnees manquantes pour l'impression »,
et le message remplaçait les boutons (« Corriger moyen » disparaissait).
**Correction / Fix :** `detail_vente` fournit `uuid_pv_vente`, le bouton l'envoie ; le message
s'affiche dans sa propre zone `#reimpression-<uuid>` sous les boutons.
/ The reprint button now sends the POS uuid; feedback goes to its own zone.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `payer_complementaire()` : routage espèces / CB + carte 2 vers la branche 2e carte, lignes du reste, contrôle somme donnée, monnaie à rendre ; contexte du re-render (`tag_id_carte2`, `total_nfc_carte2_euros`). `detail_vente()` : `uuid_pv_vente`. |
| `laboutik/templates/laboutik/partial/hx_complement_paiement.html` | Champ caché `tag_id_carte2`, ligne « Payé par la carte » de la carte 2 |
| `laboutik/templates/laboutik/partial/hx_detail_vente.html` | `uuid_pv` envoyé, zone `#reimpression-<uuid>` |
| `tests/pytest/test_paiement_complementaire.py` | 4 tests : 2e écran porte la carte 2 ; espèces ; CB ; somme insuffisante |

### Migration
- **Migration necessaire / Migration required:** Non

## Tests a realiser / How to test

### Automatiques
```bash
poetry run pytest tests/pytest/test_paiement_complementaire.py -v
```

### Test 1 : Deux cartes puis espèces
1. Panier de 15 €. Carte 1 avec 6 €, carte 2 avec 8 €.
2. Payer en cashless avec la carte 1 → « Reste à payer 9,00 € » → **2ᵉ CARTE** → carte 2.
3. Attendu : « Reste à payer 1,00 € », deux lignes « Payé par la carte ».
4. **ESPÈCE** → donner 2 € → Valider.
5. Attendu : succès, « Monnaie à rendre 1,00 € », deux cadres de carte (1re / 2e).
6. En base : les deux cartes à 0 ; lignes de vente = 15 € dont **1 € en espèces**.

### Test 2 : Deux cartes puis CB
Même scénario, **CB** au lieu d'espèces. Attendu : les deux cartes débitées, **1 € en CB** (pas 9 €).

### Test 3 : Somme donnée insuffisante
Même scénario, donner 0,50 € → message « Somme donnée insuffisante », **rien n'est débité**.

### Test 4 : Ré-impression
1. Ventes → Historique de vente → ouvrir une vente → **Ré-imprimer**.
2. Attendu : « Impression lancée » (ou « Impression impossible » sans imprimante) sous les
   boutons ; « Corriger moyen » toujours visible.
