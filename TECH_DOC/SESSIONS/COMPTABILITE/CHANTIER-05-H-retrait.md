# Chantier 05-H — Une ligne par article, et on retire l'ancien

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D13, D14, D15, R3, R4
> Effort : 3 j (2 sessions : §2, §3) — Dépend de : G. **Migration : oui** (retrait de
> champs et de modèles, dev uniquement).
> Mesure au 2026-09-28 : `payment_method` = 263 occurrences dans 36 fichiers hors
> tests (tous modèles confondus), 157 dans les tests ; `uuid_transaction` = 121
> occurrences dans 9 fichiers. Relire le décompte au démarrage.

## 1. Le but

Après cette fiche, il n'existe **qu'une** façon d'écrire et de lire de l'argent :
`Vente` → articles (entiers figés) + règlements (entiers copiés).

## 2. Session H-1 — une ligne par article

- `_creer_lignes_articles_cascade` (caisse), `facturer_tirage` (tireuse), QR/NFC
  (`BaseBillet/views.py`) écrivent **une ligne par article** : `qty` = vraie quantité,
  `amount` = prix unitaire, `part_offerte` = Σ des débits offerts (jetons, OFFRIR) de
  cet article, `source_offert`. Les règlements ne changent pas (déjà un par transaction).
- `_calculer_qty_partielles` (`laboutik/views.py` ~l.4507) et le regroupement par
  `id(article_dict)` sont **supprimés**.
- `total_catalogue_impose` est retiré de `calculer_montants_article`, **sauf pour la
  tireuse** : le total d'un tirage est ce qui a réellement été débité (solde
  insuffisant, D27 du chantier 04), qui peut différer de `prix au litre × volume`.
  Seule exception, documentée dans la docstring.
- Retour de consigne : `qty` négative, `amount` positif (D13) — fin de l'exception de
  la fiche B.
- Les avoirs ne recopient plus de fraction (il n'y en a plus).
- `corriger_moyen_paiement` ne modifie **plus** les lignes : seule la vente
  `CORRECTION` reste (D14).

## 3. Session H-2 — retraits

**Champs retirés de `LigneArticle`** (ils vivent sur `Vente` / `Reglement`) :
`payment_method`, `asset`, `carte`, `wallet`, `uuid_transaction`, `hmac_hash`,
`previous_hmac`, `idempotency_key`, `point_de_vente`. `vente` devient **obligatoire**.

**Gardés sur `LigneArticle`** (R4) : `paiement_stripe` (lien technique vers le checkout,
utilisé par la machine à statuts : `.lignearticles.update(status=…)` dans
`PaiementStripe/views.py`, `validators.py`, `booking_engine.py`, `crowds/views.py`…) et
`sale_origin` (filtres et déclencheurs existants). Ce ne sont pas des montants ; ils
restent cohérents avec la vente (un test le vérifie).

**Modèles et code retirés :**

| Retrait | Où |
|---|---|
| `laboutik.ClotureCaisse` + admin + gabarits + `LaboutikConfiguration.total_perpetuel` | `laboutik/models.py` ~l.1226, ~l.134 ; `Administration/admin/laboutik.py` |
| Ancien moteur caisse | `laboutik/reports.py` (`RapportComptableService`, `montant_ttc_centimes`, `calculer_hash_lignes`) |
| Ancien moteur en ligne | `comptabilite/services.py` `RapportComptableService` |
| Anciens FEC / ventilation / profils CSV en doublon | `comptabilite/fec.py` (ancien), `laboutik/ventilation.py`, `laboutik/fec.py`, le jeu de profils CSV non retenu en F |
| Exports de clôture en doublon | le jeu non retenu en G |
| `CorrectionPaiement` + admin | `laboutik/models.py` ~l.1585 |
| HMAC par ligne | `calculer_hmac`, `obtenir_previous_hmac`, `verifier_chaine`, `calculer_total_ht` (`laboutik/integrity.py`) |
| `LigneArticle.total()` | remplacé par une propriété qui renvoie `total_ttc` (gabarits existants) |
| Constantes `MOYENS_HORS_ARGENT`, `lignes_argent` (chantier 04) | remplacées par `MOYENS_OFFERTS` + `NM` (fiche A) |
| « Entries » (admin `LigneArticle`) | retiré du menu ; l'URL reste pour le support |

**Données de démo et fixtures** (passent par le service de vente) :
`laboutik/management/commands/create_test_pos_data.py` (~l.1546 : double compte),
`Administration/management/commands/launch_payment.py` (~l.160 : ancienne convention),
`Administration/management/commands/_demo_data_v2_ventes.py`, `demo_data_v2.py`.

**Tests existants** : ceux qui créent des `LigneArticle` directement passent par
`tests/pytest/fabriques_vente.py` ; ceux qui lisent `payment_method` d'une ligne lisent
les règlements. Les tests des fiches 04-A / 04-B (fractions, HT × qty) sont réécrits
sur les champs entiers ou supprimés s'ils ne testent plus que la mécanique retirée
(lister chaque suppression dans le CHANGELOG, avec sa raison).

## 4. Tests

| # | Test | Attendu |
|---|---|---|
| 1 | `test_nfc_trois_jus_une_seule_ligne_qty_3` | 1 ligne `qty` 3, 1050 ; règlements LE 500 + CB 550 |
| 2 | `test_jetons_une_ligne_part_offerte_300` | bière : 1 ligne, offert 300, net 200 |
| 3 | `test_tireuse_une_ligne_litres_total_debite` | 1 ligne `qty` 0,50 L |
| 4 | `test_retour_consigne_quantite_negative_prix_positif` | |
| 5 | `test_correction_ne_modifie_plus_la_ligne` | empreinte de la vente d'origine valide |
| 6 | `test_vente_obligatoire_sur_chaque_ligne` | contrainte base |
| 7 | `test_sale_origin_et_paiement_stripe_coherents_avec_la_vente` | |
| 8 | `test_garde_aucune_multiplication_amount_qty_dans_le_projet` | recherche dans tout le code hors migrations et tests : ni `F("amount") * F("qty")`, ni `amount * qty`, ni `amount*qty`, ni `int(` autour d'un montant de ligne |
| 9 | `test_montants_entiers_egalites` (transversal) | tous les scénarios B-D rejoués sur le modèle final |

Vus rouges : 1-7 sur le code de la fiche G ; 8 liste les occurrences restantes (noter
le nombre).

Mutations : réintroduire le découpage en parts (1) ; oublier la part offerte à la
fusion (2) ; recalculer le total de la tireuse depuis le volume (3) ; réintroduire
`amount * qty` dans un lecteur (8).

`make test` + `make e2e` complets. Après la migration : purger les schémas `test_*`
(skill `tibillet-test`). CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-H-retrait.md`.

## 5. Après la fiche

- Mettre à jour `GUIDELINES.md` / `tests/PIEGES.md` : la règle d'or du tronc (§2)
  remplace « `total = amount × qty` ».
- Signaler au mainteneur les fichiers `.md` à pousser dans Atomic (`push-md.sh`).
