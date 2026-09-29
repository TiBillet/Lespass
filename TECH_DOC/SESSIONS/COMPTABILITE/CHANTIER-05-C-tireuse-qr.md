# Chantier 05-C — Tireuse et paiement QR/NFC écrivent aussi la Vente

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue Fable + Opus, corrigée
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D4, D8, R3, R6
> Effort : 2 j — Dépend de : A, et **04-F-1 livrée avant** (réservation `CREATED →
> UNPAID` des lignes QR : déjà présente dans le working tree, `BaseBillet/views.py`
> ~l.1939-1941 et ~l.2229-2231 ; vérifier qu'elle est commitée). Pas de migration.
> Cette fiche **reprend** la restructuration QR/NFC de 04-F §5.3 (session 04-F-3
> arrêtée) : réseau d'abord, puis une seule transaction de base, puis `on_commit`.

## 1. Tireuse (`controlvanne/billing.py` `facturer_tirage` ~l.250-395)

Aujourd'hui : `amount` = **total du tirage** (`int(round(vol_ml × prix_litre / 1000 × 100))`,
arrondi au pair, réduit si le solde est insuffisant ~l.274-283), `qty` = fraction de 1
par monnaie, pas de `total_ht`, pas d'empreinte.

Changement, dans l'`atomic` existant (~l.223) :

- une `Vente` `origine=TIREUSE`, `point_de_vente` de la tireuse s'il existe, `carte` ;
- **forme des lignes inchangée** (`amount` = total, `qty` = fraction de 1 : R6, la forme
  « litres × prix au litre » arrive en H) ; chaque part reçoit
  `total_catalogue_impose` = débit réel de sa monnaie (`debits_par_asset`, ~l.318) ;
- le total du tirage est calculé avec **`arrondi_demi_haut`** au lieu de `round()` ;
- un règlement par `TransactionService` créée (montant copié, `fedow_transaction_uuid`) ;
  monnaie cadeau → part offerte `JETONS` + règlement LG (D8) ;
- `prix_achat` : celui du produit, **au litre** (unité de vente, D21) ; le coût de la
  part = litres de la part × prix au litre, figé : `quantite_pour_cout` = volume servi
  en litres × fraction de la part (fiche A) ;
- solde insuffisant : comportement actuel gardé (D27 du chantier 04) ; pendant la
  transition, le total imposé est ce qui a **réellement** été débité. Vérifier au
  démarrage si le **volume servi** est réduit avec le solde (~l.274-283) : si oui, en H
  `qty` = litres réellement servis et le total redevient `qty × prix` sans exception ;
  sinon, l'écart devient un article « Écart d'encaissement reçu en moins » (D26). Dans
  les deux cas `total_catalogue_impose` disparaît en H ;
- la tireuse est désormais chaînée (via la vente).

## 2. Paiement QR / NFC en ligne (`BaseBillet/views.py`)

Flux actuel : `generate_qrcode` (~l.1877) crée une ligne `CREATED` (la demande) ;
`process_with_nfc` (~l.1921-2060) et `valid_payment` (~l.2164-2330) la **suppriment**,
appellent Fedow **dans la boucle** (`fedowAPI.asset.retrieve`, ~l.2029 et ~l.2300),
recréent une ligne par transaction, **sans `atomic`**, et lancent
`send_sale_to_laboutik.delay()` tout de suite (~l.2053 et ~l.2324). Si Fedow débite
moins que demandé, le total devient la somme réellement débitée (~l.2007-2022).

Nouveau flux (après la réservation de 04-F-1) :

```
1. Débit Fedow (to_place_from_qrcode) — réseau.
2. Tous les autres appels réseau : catégories des monnaies (asset.retrieve), une fois
   par monnaie. Échec ici : ligne d'origine → FAILED (règle de 04-F-1).
3. with transaction.atomic():
       supprimer la ligne CREATED (la demande)
       vente = ouvrir_vente(origine=QRCODE_MA ou NFC_MA, client=…, point_de_vente=…)
       une ligne par transaction Fedow (forme actuelle), total_catalogue_impose = transaction['amount']
         (transition ; en H, un débit partiel devient un article « Écart d'encaissement
          reçu en moins », D26, comme pour Stripe)
       un règlement par transaction (montant et uuid copiés)
       encaisser_vente(vente)            # en dernier
       on_commit(send_sale_to_laboutik.delay(...))   pour chaque ligne
```

- La **vente naît au paiement**, pas à la génération du QR : une demande jamais payée
  ne laisse pas de vente.
- `point_de_vente` : celui qui a généré le QR s'il est connu (le passer dans la
  demande), sinon vide (journal par défaut : fiche E).
- Monnaies acceptées : **FED et TLF seulement** (une autre catégorie lève « Unknown
  asset category », ~l.1997-2001). Pas de branche monnaie cadeau ici.
- TVA : taux par défaut du lieu (D26 du chantier 04), inchangé.
- Catégorie inconnue : `raise Exception("Unknown asset category")` (~l.2034) ; elle est
  maintenant levée à l'étape 2, **avant** l'`atomic` (ligne d'origine → `FAILED`).

## 3. Tests

Fichiers : `tests/pytest/test_tireuse_ecrit_la_vente.py`,
`tests/pytest/test_qrcode_ecrit_la_vente.py` (Fedow distant mocké comme dans les tests
QR actuels ; chaque test lit sa vente et finit par `verifier_egalites(vente)`, base
partagée ; le 6 en schéma dédié).

| # | Test | Attendu |
|---|---|---|
| 1 | `test_tirage_50cl_une_vente_un_reglement` | total 400, 1 règlement 400, vente `TIREUSE` numérotée, forme des lignes inchangée |
| 2 | `test_tirage_jetons_et_monnaie_locale_parts_entieres` | 400 = 100 jetons + 300 TLF → part jetons offerte 100 ; part LE net 300 ; règlements LG 100 + LE 300 |
| 3 | `test_tirage_88_centimes_30_plus_58` | parts 30 / 58 exactes |
| 4 | `test_total_tirage_arrondi_demi_haut` | 173 ml à 5 €/L = 86,5 c → **87** (au pair : 86) |
| 5 | `test_tirage_solde_insuffisant_total_egal_debit_reel` | égalités tenues |
| 6 | `test_tirage_vente_chainee` | `previous_hmac` = vente précédente du lieu |
| 7 | `test_qr_paye_tlf_et_fed_deux_reglements_exacts` | montants et uuid Fedow |
| 8 | `test_qr_non_paye_aucune_vente` | |
| 9 | `test_nfc_ma_une_vente_origine_nfc` | |
| 10 | `test_qr_echec_reseau_apres_debit_aucune_vente_ligne_failed` | `asset.retrieve` en erreur → aucune ligne recréée, aucune vente, ligne d'origine `FAILED` |
| 11 | `test_qr_envoi_ancien_laboutik_apres_commit` | `send_sale_to_laboutik` appelé seulement au COMMIT : fixture `django_capture_on_commit_callbacks` (sous la marque `django_db`, `on_commit` ne part pas, PIEGES 13.1) ; aucun appel avant la fin du bloc |
| 13 | `test_tirage_cout_sur_les_litres_reels` | 0,50 L, prix d'achat 300 / L, deux parts → Σ `cout_achat` = 150 |
| 12 | `test_qr_refus_fedow_aucune_vente` | ligne redevenue payable (04-F-1) |

Vus rouges : 1-3, 5-11, 13 (aucune vente, pas d'`atomic`, `delay` immédiat) ; 4 (86).

Mutations : `round()` au lieu de `arrondi_demi_haut` (4) ; part calculée depuis la
fraction (3) ; vente créée à la génération du QR (8) ; `asset.retrieve` remis dans la
boucle, sous l'`atomic` (10) ; `delay()` hors `on_commit` (11) ; règlement jetons en
argent (2) ; coût calculé sur la fraction au lieu des litres (13).

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-C-tireuse-qr.md`.

## 4. Tests existants à réécrire

| Cause | Fichiers |
|---|---|
| Envoi à l'ancien LaBoutik désormais en `on_commit` (QR/NFC) | `tests/pytest/test_qrcodescanpay_flux_complet.py` : capturer par `django_capture_on_commit_callbacks(execute=True)` là où `send_sale_to_laboutik` est attendu |
| Total d'un tirage arrondi demi-haut au lieu d'au pair | tests de `controlvanne` qui assertent un total sur un demi-centime (`rg -ln "facturer_tirage" tests/`) |

Chaque réécriture est listée dans le CHANGELOG avec sa raison.

## Machine à états — compléments obligatoires

Source : [`CHANTIER-05-machine-a-etats.md`](CHANTIER-05-machine-a-etats.md) §5 (trous T…). Les tests de
caractérisation de la fiche A′ doivent rester verts pendant cette fiche.

| Trou | À faire dans cette fiche | Test |
|---|---|---|
| T2 | L'anti-rejeu QR/NFC filtre sur `payment_method = QRCODE_MA` (`BaseBillet/validators.py` ~l.1381, `BaseBillet/views.py` ~l.1940, ~l.2230). Il filtre désormais sur `sale_origin = QRCODE_MA` (posé à la demande ~l.1884, gardé en H par R4). Fait **ici**, pour que H ne casse pas le paiement QR. | `test_qr_echec_fedow_ligne_en_echec_rejeu_refuse` (A′) reste vert ; `test_anti_rejeu_qr_ne_lit_plus_payment_method` |
