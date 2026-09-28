# Chantier 05-C — Tireuse et paiement QR/NFC écrivent aussi la Vente

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D4, D8, D15, R3
> Effort : 1 j — Dépend de : A, et **04-F-1 (anti-rejeu QR) livrée avant** : elle
> restructure les mêmes fonctions QR/NFC (réservation, réseau d'abord, puis une seule
> transaction de base). Pas de migration.

## 1. Tireuse (`controlvanne/billing.py` `facturer_tirage` ~l.250-395)

Aujourd'hui : `amount` = **total du tirage** (`int(round(vol_ml × prix_litre / 1000 × 100))`,
arrondi au pair, réduit si le solde est insuffisant ~l.274), `qty` = fraction de 1
par monnaie, pas de `total_ht`, pas d'empreinte.

Changement, dans l'`atomic` existant (~l.223) :

- une `Vente` `origine=TIREUSE`, `point_de_vente` de la tireuse s'il existe, `carte` ;
- **D15** : `amount` = prix au litre (centimes), `qty` = litres servis, en parts par
  monnaie ; chaque part reçoit `total_catalogue_impose` = débit réel de la monnaie
  (`debits_par_asset`, ~l.318) ;
- le total du tirage est calculé avec **`arrondi_demi_haut`** (règle d'or) au lieu de
  `round()` : la seule formule d'argent du projet ;
- un règlement par `TransactionService` créée (montant copié, `fedow_transaction_uuid`) ;
- `prix_achat_unitaire` = prix d'achat **au litre** du produit ;
- solde insuffisant : comportement actuel gardé (D27 du chantier 04) — le total est
  ce qui a **réellement** été débité ; `qty` = volume réellement servi ;
- `encaisser_vente` : la tireuse est désormais chaînée (via la vente).

## 2. Paiement QR / NFC en ligne (`BaseBillet/views.py`)

Flux actuel : `generate_qrcode` (~l.1877) crée une ligne `CREATED` (la demande) ;
`process_with_nfc` (~l.2005) et `valid_payment` (~l.2231) la **suppriment** et
recréent une ligne par transaction Fedow (FED → SF, TLF → LE), `amount` = total,
`qty` = fraction de 1.

Changement (dans la transaction de base unique posée par 04-F-1, après les appels
réseau) :

- la **vente est créée au paiement**, pas à la génération du QR : la ligne `CREATED`
  est une demande, pas un ticket (une demande jamais payée ne laisse pas de vente) ;
- `Vente.origine` = `QRCODE_MA` ou `NFC_MA` ; `client` = l'utilisateur du wallet ;
- lignes recréées comme aujourd'hui (anciens lecteurs), chaque part avec
  `total_catalogue_impose` = `transaction['amount']` ;
- un règlement par transaction Fedow (montant copié) ; monnaie cadeau éventuelle →
  part offerte `JETONS` + règlement LG (D8) ;
- TVA : taux par défaut du lieu (D26 du chantier 04), inchangé ;
- `send_sale_to_laboutik` inchangé (`transaction.on_commit`, posé par 04-F-1).

## 3. Tests

Fichiers : `tests/pytest/test_tireuse_ecrit_la_vente.py`,
`tests/pytest/test_qrcode_ecrit_la_vente.py` (réutiliser les helpers de
`tests/pytest/` controlvanne et QR existants ; Fedow distant mocké comme dans les
tests QR actuels).

| # | Test | Attendu |
|---|---|---|
| 1 | `test_tirage_50cl_a_8_euros_litre_une_vente` | `qty` 0,50, `amount` 800, total 400, 1 règlement 400, vente `TIREUSE` numérotée |
| 2 | `test_tirage_deux_monnaies_parts_entieres` | 400 = 100 TNF(jetons) + 300 TLF → part jetons offerte 100 ; part LE net 300 ; règlements LG 100 + LE 300 |
| 3 | `test_tirage_88_centimes_30_plus_58` | parts 30 / 58 exactes (aujourd'hui 0,340909 / 0,659091) |
| 4 | `test_total_tirage_arrondi_demi_haut` | un volume qui donne x,5 centimes → arrondi vers le haut |
| 5 | `test_tirage_solde_insuffisant_total_egal_debit_reel` | total = débit réel, égalités tenues |
| 6 | `test_tirage_vente_chainee` | `hmac_hash` posé, `previous_hmac` = vente précédente du lieu |
| 7 | `test_qr_paye_tlf_et_fed_deux_reglements_exacts` | deux règlements aux montants Fedow, parts entières |
| 8 | `test_qr_non_paye_aucune_vente` | QR généré seul → aucune `Vente` |
| 9 | `test_nfc_ma_une_vente_origine_nfc` | `origine=NFC_MA` |
| 10 | `test_qr_refus_fedow_aucune_vente` | refus → aucune vente, ligne redevenue payable (04-F-1) |

Vus rouges : 1-3, 5-9 (aucune vente) ; 4 (arrondi au pair actuel).

Mutations : `round()` au lieu de `arrondi_demi_haut` (4) ; part calculée depuis la
fraction (3) ; vente créée à la génération du QR (8) ; règlement jetons compté en
argent (2) ; `qty = 1` au lieu des litres (1).

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-C-tireuse-qr.md`.
