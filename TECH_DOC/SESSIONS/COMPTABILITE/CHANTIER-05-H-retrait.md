# Chantier 05-H — Une ligne par article, et on retire l'ancien

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue Fable + Opus, corrigée
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D13, D14, D15, R3, R4, R6
> Effort : 6 j (3 sessions : §2, §3, §4) — Dépend de : G. **Migrations : oui**
> (retrait de champs et de modèles, dev uniquement ; une migration par nature
> d'opération, jamais DDL et DML dans la même, PIEGES 9.113). Les FK de clôture sont
> déjà déplacées en G.
> Mesure au 2026-09-28 (hors tests, py + html + js) : `payment_method` ≈ 270
> occurrences dans 39 fichiers (tous modèles confondus), 157 dans les tests ;
> `uuid_transaction` ≈ 138 dans 14 fichiers ; 18 fichiers de tests créent des lignes
> (31 créations) ; `laboutik.ClotureCaisse` citée dans 24 fichiers. Relire au démarrage.

## 1. Le but

Après cette fiche, il n'existe **qu'une** façon d'écrire et de lire de l'argent :
`Vente` → articles (entiers figés) + règlements (entiers copiés).

## 2. Session H-1 — une ligne par article, forme poids / tireuse

- `_creer_lignes_articles_cascade` (caisse), `facturer_tirage` (tireuse), QR/NFC
  (`BaseBillet/views.py`) écrivent **une ligne par article** : `qty` = vraie quantité,
  `amount` = prix unitaire, `part_offerte` = Σ des débits offerts (jetons, OFFRIR) de
  cet article, `source_offert`. Les règlements ne changent pas.
- `_calculer_qty_partielles` (`laboutik/views.py` ~l.4507) et le regroupement par
  `id(article_dict)` sont **supprimés**.
- **D15** : poids et mesure (caisse) → `qty` = kg / L, `amount` = prix au kg / au litre ;
  tireuse → `qty` = litres, `amount` = prix au litre. Vérifier avant : décrément de
  stock (`qty` ou `weight_quantity` ?), ticket, détail des ventes, gabarits
  `floatformat:0`.
- `total_catalogue_impose` est retiré, **sauf pour deux cas** où le total est ce qui a
  réellement été débité, documentés dans la docstring :
  - la tireuse (solde insuffisant, D27 du chantier 04) ;
  - le paiement QR / NFC en ligne : si Fedow débite moins que demandé, le total est la
    somme débitée (`BaseBillet/views.py` ~l.2007-2022). Sans cette exception, l'égalité
    serait rompue **après** un débit réseau qu'on ne peut pas annuler.
- FK `membership` : une seule ligne par adhésion (plus de parts).
- Retour de consigne : `qty` négative, `amount` positif (D13).
- `corriger_moyen_paiement` ne modifie **plus** les lignes : seule la vente
  `CORRECTION` reste (D14).
- **« Avoir sur un article »** (quantité partielle) dans la fiche « Vente » de l'admin
  (reporté de G) : l'article n'est plus coupé en parts ; même prix unitaire, quantité
  négative, part offerte rendue au prorata plafonné (fiche D §4), champ « Remboursé
  par ».

## 3. Session H-2 — retrait des champs et de l'ancienne clôture

**Champs retirés de `LigneArticle`** : `payment_method`, `asset`, `carte`, `wallet`,
`uuid_transaction`, `hmac_hash`, `previous_hmac`, `idempotency_key`, `point_de_vente`.
`vente` devient **obligatoire**. Gardés (R4) : `paiement_stripe`, `sale_origin`.

**Lignes sans vente dans la base de dev** (démo, e2e, lignes antérieures à B) : la
contrainte NOT NULL échouerait. Procédure, en migrations séparées :

1. le mainteneur régénère la base de dev (données de démo par le service de vente,
   §4) **avant** d'appliquer les migrations de H ;
2. une migration `RunPython` de **vérification seule** (aucune écriture) échoue avec un
   message clair s'il reste des lignes sans vente, schéma par schéma ;
3. puis l'`AlterField` NOT NULL, puis les `RemoveField`.

Aucune suppression automatique de lignes par une migration.

À adapter avant le retrait :

- `_executer_avec_cle_idempotence` (`laboutik/views.py` ~l.4666) cherche par
  `uuid_transaction` → `Vente.idempotency_key`.
- Recharge API v2 : idempotence déjà sur `Vente.idempotency_key` (fiche D).
- `LigneArticle.total()` reste une **méthode** (appels `.total()` dans `laboutik/views.py`
  ~l.4141, `Administration/admin_tenant.py` ~l.2034, `total_decimal()`,
  `PaiementStripe/utils.py` ~l.44) et renvoie `total_ttc`.
- Envoi vers l'ancien LaBoutik : déjà un envoi par règlement depuis G ; le sérialiseur
  (`ApiBillet/serializers.py` ~l.1296) ne lit plus `payment_method`, `asset`, `wallet`
  sur la ligne.

**Modèles et code retirés :**

| Retrait | Où |
|---|---|
| `laboutik.ClotureCaisse` + admin + gabarits + `LaboutikConfiguration.total_perpetuel` | `laboutik/models.py` ~l.1226, ~l.134 ; `Administration/admin/laboutik.py` |
| Ancien moteur caisse | `laboutik/reports.py` (`RapportComptableService`, `montant_ttc_centimes`, `calculer_hash_lignes`) |
| Ancien moteur en ligne | `comptabilite/services.py` `RapportComptableService` (et sa comparaison dans `tests/e2e/conftest.py`) |
| Anciens FEC / ventilation / profils CSV en doublon | `comptabilite/fec.py` (ancien), `laboutik/ventilation.py`, `laboutik/fec.py`, le jeu de profils non retenu (fiche F) |
| Exports de clôture en doublon | le jeu non retenu (fiche G) |
| `CorrectionPaiement` + admin | `laboutik/models.py` ~l.1585 |
| HMAC par ligne | `calculer_hmac`, `obtenir_previous_hmac`, `verifier_chaine`, `calculer_total_ht` (`laboutik/integrity.py`) |
| Constantes `MOYENS_HORS_ARGENT`, `lignes_argent` (chantier 04) | remplacées par `MOYENS_OFFERTS` + `NM` |
| « Entries » et « Ancien rapport caisse » | retirés du menu (l'URL « Entries » reste pour le support) |

## 4. Session H-3 — démo, fixtures, tests existants

- Démo : `create_test_pos_data.py` (~l.1546 double compte, ~l.1703-1752),
  `launch_payment.py` (~l.160), `_demo_data_v2_ventes.py`, `demo_data_v2.py` → par le
  service de vente.
- Tests existants : voir §6.

## 5. Tests

| # | Test | Attendu |
|---|---|---|
| 1 | `test_nfc_trois_jus_une_seule_ligne_qty_3` | 1 ligne `qty` 3, 1050 ; règlements LE 500 + CB 550 |
| 2 | `test_jetons_une_ligne_part_offerte_300` | 1 ligne, offert 300, net 200 |
| 3 | `test_fromage_une_ligne_0_350_kg_prix_au_kilo` | `qty` 0,350, `amount` 1290, total 452 |
| 4 | `test_tireuse_une_ligne_litres_total_debite` | `qty` 0,50 L ; total = débit réel |
| 5 | `test_retour_consigne_quantite_negative_prix_positif` | |
| 5b | `test_qr_debit_partiel_total_egal_au_debit` | Fedow débite 800 sur 1000 demandés → une ligne, total 800, égalités tenues |
| 5c | `test_admin_avoir_sur_un_article_quantite_partielle` | 1 jus sur 3, remboursé en espèces → vente `AVOIR` −350, un règlement espèces −350 |
| 6 | `test_correction_ne_modifie_plus_la_ligne` | |
| 7 | `test_vente_obligatoire_sur_chaque_ligne` | contrainte base |
| 7b | `test_migration_de_verification_refuse_les_lignes_sans_vente` | schéma dédié avec une ligne sans vente → la migration de vérification échoue avec le message |
| 8 | `test_idempotence_caisse_par_la_vente` | rejeu → une vente |
| 9 | `test_sale_origin_et_paiement_stripe_coherents_avec_la_vente` | **vert dès G** (noté : garde de cohérence, pas rouge) |
| 10 | `test_garde_aucune_multiplication_amount_qty_dans_le_projet` | tout le code hors migrations et tests : ni `F("amount") * F("qty")`, ni `amount * qty` / `amount*qty` / `qty * amount`, ni `F("pricesold__prix") * F("qty")`, ni `int(` autour d'un montant de ligne |
| 11 | `test_montants_entiers_egalites` (transversal) | tous les scénarios rejoués sur le modèle final |

Vus rouges : 1-8, 5b, 5c, 7b sur le code de la fiche G ; 10 liste les occurrences
restantes (noter le nombre).

Mutations : réintroduire le découpage en parts (1) ; oublier la part offerte à la
fusion (2) ; `qty = 1` pour le poids (3) ; recalculer le total de la tireuse depuis le
volume (4) ; retirer l'exception QR de `total_catalogue_impose` (5b) ; réintroduire
`amount * qty` dans un lecteur (10).

`make test` + `make e2e` complets. Après les migrations : purger les schémas `test_*`
(skill `tibillet-test`). CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-H-retrait.md`.

## 6. Tests existants à réécrire

Ceux qui créent des lignes passent par `fabriques_vente.py` ; ceux qui lisent
`payment_method` d'une ligne lisent les règlements ; ceux des fiches 04-A / 04-B
(fractions, HT × qty) sont réécrits sur les champs entiers ou supprimés s'ils ne testent
plus que la mécanique retirée. Chaque suppression est listée dans le CHANGELOG, avec sa
raison. Vérifiés au 2026-09-28 :

| Cause | Fichiers |
|---|---|
| créent des `LigneArticle` à la main (`rg -l "LigneArticle.objects.create\(" tests/`) | `tests/django_test/test_sales_api.py`, `tests/e2e/test_admin_cancel_membership.py`, `tests/e2e/test_parcours_fedow_reel.py`, `tests/pytest/test_api_v2_wallet_refill.py`, `test_cloture_caisse.py`, `test_cloture_enrichie.py`, `test_cloture_export.py`, `test_comptabilite_service.py`, `test_corrections_fond_sortie.py`, `test_export_comptable.py`, `test_integrity_hmac.py`, `test_mail_annulation_booking.py`, `test_menu_ventes.py`, `test_rapports_cheque.py`, `test_stripe_refund.py`, `test_ticket_client_imprime.py`, `test_vente_en_points.py`, `test_ventes_remontent_au_ticket_z.py` |
| testent la mécanique retirée (`_calculer_qty_partielles`, `calculer_hmac`, `verifier_chaine`, `CorrectionPaiement`, `calculer_total_ht`) | `test_c2_legacy_repartition.py`, `test_corrections_fond_sortie.py`, `test_integrity_hmac.py`, `test_poids_mesure.py`, `test_pos_retour_consigne.py`, `test_total_ht_ligne.py` |
| lisent l'ancien moteur, retiré ici | `test_comptabilite_service.py`, `tests/e2e/conftest.py` (~l.785-920) |

Relire au démarrage : `rg -l "payment_method|uuid_transaction|laboutik\.reports|comptabilite\.services" tests/`.

## 7. Après la fiche

- `GUIDELINES.md`, `tests/PIEGES.md` : la règle d'or du tronc (§2) remplace
  « `total = amount × qty` ».
- Signaler au mainteneur les `.md` à pousser dans Atomic (`push-md.sh`).

## Machine à états — compléments obligatoires

Source : [`CHANTIER-05-machine-a-etats.md`](CHANTIER-05-machine-a-etats.md) §5 (trous T…). Les tests de
caractérisation de la fiche A′ doivent rester verts pendant cette fiche.

| Trou | À faire dans cette fiche | Test |
|---|---|---|
| T1 | Le courriel « SEPA en attente » (`ApiBillet/views.py` ~l.1230) et le moyen du règlement Stripe lisent `Paiement_stripe.moyen` (fiche A), plus `LigneArticle.payment_method`. | `test_sepa_en_attente_envoie_le_mail_sans_payment_method_sur_la_ligne` |
| T2 | Vérifier que l'anti-rejeu QR ne lit plus `payment_method` (fait en C). | `test_qr_echec_fedow_ligne_en_echec_rejeu_refuse` (A′) |
| T18 | Rejeu 208 de la recharge API v2 (`api_v2/views.py` ~l.931) lit `ligne_article.asset` → lire `Vente.unite`. | test A′ P13 reste vert |
| T19 | `_compute_default_vat` (`BaseBillet/models.py` ~l.3860) lit `payment_method` : la règle est retirée (tous les producteurs passent par `ajouter_article`, qui pose la TVA). | `test_tva_zero_explicite_respectee_par_save` (A) reste vert |
| T20 | Copies de `payment_method` / `asset` / `wallet` dans les producteurs d'avoirs et de remboursements, **à retirer nommément** : `PaiementStripe/utils.py` ~l.93-95, `BaseBillet/models.py` ~l.2986-2988, `booking/models.py` ~l.633-635, `BaseBillet/views.py` ~l.4678-4680, `Administration/admin_tenant.py` ~l.2091-2093. Sinon `TypeError` sur les annulations. | `test_caracterisation_annulations.py` (A′) reste vert |
| T14 | Après fusion, la facture d'adhésion caisse et l'avoir d'un billet caisse portent sur l'article entier : l'écrire au CHANGELOG. | test A′ « …cascade…part_rattachee » modifié ici |
