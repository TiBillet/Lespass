# Chantier 05-B — La caisse écrit aussi la Vente et ses règlements

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D7 à D15, D17, R3
> Effort : 3 j (3 sessions : §3, §4, §5) — Dépend de : A. Pas de migration.
> **Aucun ancien lecteur ne change** : les lignes sont écrites comme aujourd'hui, avec
> en plus leur vente, leurs règlements et leurs montants entiers.

## 1. Le principe

Chaque **encaissement** de la caisse (un clic sur un moyen de paiement qui réussit)
produit **une `Vente` encaissée** (`encaisser_vente`, fiche A), dans la même
transaction de base que les lignes.

- Les lignes passent par `ajouter_article(...)` au lieu de `LigneArticle.objects.create(...)`,
  en gardant leurs champs historiques (`payment_method`, `asset`, `carte`,
  `uuid_transaction`, HMAC par ligne…) : les anciens rapports ne voient aucune différence.
- Une ligne coupée en parts (cascade) reçoit, par part, `total_catalogue_impose` =
  **l'argent réel de la part** (3ᵉ élément du tuple : `debit_sur_cet_asset`,
  `reste_article`, part legacy, part espèces/CB). Voir le tableau du §5 du tronc.
- Les règlements sont écrits **à partir des débits réels**, jamais depuis les lignes :

| Source de l'argent | Règlement |
|---|---|
| `TransactionService.creer_vente(...)` (une par monnaie et par carte : `laboutik/views.py` ~l.8412-8450, ~l.9503-9540, ~l.10057-10115) | un règlement : `moyen` = moyen de la monnaie, `montant` = `montant_en_centimes` passé, `asset`, `carte`, `wallet`, `fedow_transaction_uuid` = uuid de la transaction renvoyée |
| Débit legacy Fedow (`_repartir_legacy_sur_articles` ~l.1410) | un règlement par débit legacy, montant `couvert` |
| Espèces / CB / chèque (paiement direct ou complément) | un règlement, montant **encaissé** (somme du panier ou `reste_complement`) |
| Monnaie cadeau (TNF / LG) | un règlement `LG` (offert, D8) + sur la part : `part_offerte` = montant de la part, `source_offert = JETONS` |
| OFFRIR (FREE, mode gérant) | un règlement `FREE` du total + sur chaque ligne : `part_offerte = total_catalogue`, `source_offert = OFFRIR` |
| Recharge cadeau (monnaie cadeau créditée gratuitement) | article recharge `hors_chiffre_affaires`, **offert en totalité** (`OFFRIR`, net 0) + règlement `FREE` du total |
| Points (NM) | `Vente.unite` = uuid de la monnaie ; un règlement `NM` par transaction (une par article : ~l.8409-8427) ; TVA 0 |

- `Vente.origine = LABOUTIK`, `point_de_vente`, `operateur` (carte primaire / user de
  la session), `client` et `carte` quand ils sont connus.
- `Vente.nature` : `RECHARGE` si **tous** les articles sont des recharges, `VENTE` sinon.
- `prix_achat_unitaire` = `Product.prix_achat` (`BaseBillet/models.py` ~l.1452) lu au
  moment de la vente.

Si `encaisser_vente` lève `EgaliteDeVenteRompue`, l'`atomic` du producteur annule
tout : **mieux vaut une vente refusée qu'une vente fausse**. Les débits Fedow sont
dans la même transaction de base (fedow_core est local) : ils sont annulés aussi.
À vérifier au démarrage pour chaque chemin (aucun appel réseau externe entre le
débit et l'encaissement).

## 2. Les producteurs de la caisse (inventaire, diagnostic §1)

| Chemin | Fonction (`laboutik/views.py`) | Ce qui change |
|---|---|---|
| CB, chèque, OFFRIR | appel ~l.7417 → `_creer_lignes_articles` ~l.5311 | vente + 1 règlement (ou FREE + parts offertes) |
| Espèces | ~l.7642 → `_creer_lignes_articles` | vente + 1 règlement espèces |
| Recharges (RE/RC/TM) | `_executer_recharges` ~l.6695 (appelée ~l.7433, 7658, 8397, 8875, 9486, 10040) | articles `hors_chiffre_affaires` dans **la même vente** que le reste du panier ; `uuid_transaction` passé (manquait) |
| Retour de consigne NFC | `_rembourser_consigne_par_nfc` ~l.7847 | vente `AVOIR` sans vente liée ; règlement négatif (monnaie recréditée) |
| Paiement NFC seul | `_payer_par_nfc` ~l.8457 → `_creer_lignes_articles_cascade` ~l.5559 | règlements par transaction Fedow (points, cascade, legacy) |
| Complément espèces/CB | `_executer_paiement_complementaire` ~l.9562 | règlements carte 1 + FED partiel + règlement espèces/CB du reste |
| 2ᵉ carte | ~l.10147 | règlements carte 1 **et carte 2** : chaque règlement porte **sa** carte (les lignes, elles, gardent `carte=carte1` jusqu'à H) |
| Adhésion payée à la caisse | ~l.8515-8535 | FK `membership` posée sur **chaque** part (plus seulement la 1ʳᵉ) |
| Commande de table | `payer_commande` ~l.11818 (hors NFC) et chemin NFC ~l.11760 | une vente ; `CommandeSauvegarde.vente` renseignée ; `uuid_transaction` passé (manquait) |
| Vider carte | `fedow_core/services.py` `rembourser_en_especes` ~l.643-676 (appelé ~l.10645) | vente `VIDAGE_CARTE` sans article : règlements `+tlf` (LE), `+fed` (SF), `−(tlf+fed)` espèces ; les deux lignes « Refund » restent jusqu'à H |
| Correction de moyen | `corriger_moyen_paiement` ~l.11126 | en plus de la correction actuelle des lignes : vente `CORRECTION` liée, règlements `−ancien` / `+nouveau` du montant corrigé |

Idempotence : `_executer_avec_cle_idempotence` (~l.4665) cherche des lignes par
`uuid_transaction` ; `Vente.idempotency_key` reçoit la même clé (unique). Un rejeu
retrouve la vente et ne crée rien.

## 3. Session B-1 — un moyen de paiement (espèces, CB, chèque, OFFRIR, recharges)

Changements dans `_creer_lignes_articles` et ses appelants, `_executer_recharges`,
consigne. Tests : §6, lignes 1 à 7.

## 4. Session B-2 — la cascade (NFC, complément, 2ᵉ carte, points, jetons, adhésion)

Changements dans `_creer_lignes_articles_cascade` et ses trois appelants.
`_calculer_qty_partielles` reste (anciens lecteurs) ; la part reçoit en plus son argent
réel. Tests : §6, lignes 8 à 15.

## 5. Session B-3 — poids/mesure, commandes de table, vider carte, correction

**Poids / mesure (D15)** : `_creer_lignes_articles` écrit désormais `qty` = quantité
réelle (kg, L) et `amount` = prix au kg / au litre (`_montant_poids_mesure_en_centimes`
~l.4694 reste la formule du total, passée en `total_catalogue_impose`). À vérifier
avant de changer : le décrément de stock (lit-il `qty` ou `weight_quantity` ?), le
ticket imprimé, `calculer_detail_ventes`. Les anciens lecteurs `Round(Sum(amount×qty))`
retombent sur le même centime (1290 × 0,350 = 451,5 → 452 = arrondi de la caisse) ;
un test le vérifie.

Retour de consigne : la ligne garde `amount` négatif et `qty` positive jusqu'à la
fiche H (`calculer_remboursements` lit `amount < 0`). Les montants entiers sont
négatifs.

Tests : §6, lignes 16 à 21.

## 6. Tests

Fichier : `tests/pytest/test_caisse_ecrit_la_vente.py` (réutiliser les helpers de
`tests/pytest/test_paiement_complementaire.py` et des tests de cascade existants ;
chaque test ne lit **que sa vente**, retrouvée par `idempotency_key` ou
`uuid_transaction` → base partagée possible, sauf les tests de numérotation).
Le test transversal `test_montants_entiers_egalites.py` rejoue chaque scénario.

| # | Test | Attendu |
|---|---|---|
| 1 | `test_vente_especes_trois_jus_une_vente_un_reglement` | vente n° posé, `REGLEE`, 1 règlement espèces 1050, article 1050 / 875 / 175 |
| 2 | `test_vente_cb_prix_libre` | total catalogue = saisie |
| 3 | `test_offrir_en_mode_gerant_part_offerte_totale` | net 0, TVA 0, règlement FREE = catalogue, 0 € encaissé |
| 4 | `test_recharge_seule_nature_recharge_hors_ca` | nature `RECHARGE`, article `hors_chiffre_affaires`, TVA 0, règlement CB |
| 5 | `test_biere_et_recharge_meme_panier_une_seule_vente` | nature `VENTE`, 2 articles (dont 1 hors CA), 1 règlement ; lignes de recharge avec `uuid_transaction` |
| 6 | `test_vente_consigne_dans_le_chiffre_affaires` | article consigne, `hors_chiffre_affaires` faux |
| 7 | `test_retour_consigne_nfc_vente_avoir_reglement_negatif` | nature `AVOIR`, totaux négatifs, règlement négatif |
| 8 | `test_nfc_trois_jus_500_le_550_cb_parts_entieres` | **l'exemple fil rouge** : parts 500 / 550, règlements LE 500 (avec `fedow_transaction_uuid`) et CB 550 |
| 9 | `test_reglement_fedow_egal_montant_de_la_transaction` | Σ règlements cashless = Σ `Transaction.amount` créées |
| 10 | `test_deux_articles_meme_monnaie_un_seul_reglement_par_monnaie` | un règlement par transaction Fedow |
| 11 | `test_jetons_benevoles_part_offerte_hors_tva` | bière 500 = 300 jetons + 200 CB → part jetons : offert 300, net 0 ; part CB : net 200, HT 167, TVA 33 ; règlements LG 300 + CB 200 |
| 12 | `test_deuxieme_carte_chaque_reglement_porte_sa_carte` | règlement carte 2 → `carte=carte2` |
| 13 | `test_vente_en_points_unite_monnaie_tva_zero` | `unite` = monnaie, règlement NM, TVA 0 |
| 14 | `test_adhesion_payee_le_et_cb_membership_sur_chaque_part` | 35 € = 20 + 15 → deux parts liées à l'adhésion, Σ = 3500 |
| 15 | `test_legacy_fedow_reglement_par_debit_legacy` | chemin legacy |
| 16 | `test_poids_quantite_reelle_prix_au_kilo` | `qty` 0,350, `amount` 1290, total 452 |
| 17 | `test_poids_ancien_rapport_meme_centime` | `montant_ttc_centimes` de la ligne = 452 |
| 18 | `test_paiement_table_une_vente_liee_a_la_commande` | `CommandeSauvegarde.vente` renseignée |
| 19 | `test_vider_carte_vente_sans_article_reglements_nuls` | nature `VIDAGE_CARTE`, Σ règlements = 0, espèces = −(tlf+fed) |
| 20 | `test_correction_moyen_nouvelle_vente_correction` | vente `CORRECTION` liée, −CA +CB, vente d'origine **inchangée** (empreinte de vente toujours valide) |
| 21 | `test_rejeu_meme_cle_idempotence_une_seule_vente` | 2 appels → 1 vente |
| 22 | `test_anciens_rapports_inchanges` | sur un schéma dédié : `RapportComptableService` caisse donne les mêmes totaux avant/après (scénarios 1, 8, 11) |

Vus rouges : 1 à 21 échouent (aucune vente créée) sur le code actuel. Le 22 est vert
avant et doit le rester (non-régression) : le noter tel quel.

Mutations :

| Mutation | Doit faire tomber |
|---|---|
| `total_catalogue_impose` retiré (calcul depuis `qty` partielle) | 8 (499 au lieu de 500 ou refus d'égalité) |
| règlement cashless = somme des parts au lieu du montant de la transaction | 9 |
| règlement LG compté comme argent (moyen CB) | 11 |
| `carte=carte1` sur les règlements de la carte 2 | 12 |
| FK membership sur la 1ʳᵉ part seulement | 14 |
| `qty = 1` pour le poids | 16 |
| `CommandeSauvegarde.vente` non posée | 18 |
| correction qui modifie la vente d'origine | 20 |
| `idempotency_key` non posée | 21 |

E2E : `make e2e` complet (la caisse ne change pas à l'écran). Pas de nouveau test E2E.

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-B-caisse.md`.
