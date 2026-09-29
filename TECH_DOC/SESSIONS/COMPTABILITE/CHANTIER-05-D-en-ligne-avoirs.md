# Chantier 05-D — En ligne, admin, API : la vente en attente puis encaissée ; les avoirs

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D1, D4, D13, D16, R3
> Effort : 2,5 j (3 sessions : §2, §3, §4) — Dépend de : A. Pas de migration.
> Aucun ancien lecteur ne change.

## 1. Le principe

- **Paiement Stripe** : la vente naît `EN_ATTENTE` quand les lignes naissent
  (`CREATED`, au checkout). Elle est **encaissée** quand l'argent est confirmé
  (webhook / retour de paiement), avec **un** règlement Stripe dont le montant est
  celui **renvoyé par Stripe** (entier). Paiement expiré ou échoué → `ANNULEE`,
  jamais numérotée.
- **Sans Stripe** (gratuit, admin, « payé ailleurs » par l'API) : la vente est créée
  et encaissée **dans la même transaction** que les lignes.
- **Avoirs et remboursements** : une nouvelle vente `AVOIR` liée (D13).

## 2. Session D-1 — les ventes en ligne payées par Stripe

| Producteur | Fichier | Règlement |
|---|---|---|
| Billets (panier, API) | `BaseBillet/validators.py` `TicketCreator.method_B` ~l.412, ~l.437 | Stripe |
| Adhésion en ligne | `BaseBillet/validators.py` `get_checkout_stripe` ~l.974 | Stripe |
| Panier (adhésions ; billets via TicketCreator) | `BaseBillet/services_commande.py` ~l.216 ; `Commande.vente` renseignée | Stripe |
| Booking | `booking/booking_engine.py` `validate_new_booking` ~l.692 | Stripe |
| Crowds (financement, contribution) | `crowds/views.py` ~l.241, ~l.1188 | Stripe |
| Renouvellement d'abonnement | `PaiementStripe/views.py` ~l.304 (appelé par `ApiBillet/views.py` ~l.1463) | Stripe récurrent ; **une vente par facture payée**, créée et encaissée d'un coup ; corrige le double compte : `amount` = prix **unitaire** de la ligne Stripe |

**Un seul point d'encaissement Stripe** : la fonction `encaisser_vente_stripe(paiement_stripe)`
(dans `services_vente.py`), appelée **là où `Paiement_stripe` passe à « payé »**. Au
démarrage : lister tous les chemins qui posent ce statut (webhook
`checkout.session.completed`, retour de checkout, SEPA, `invoice.paid`) et appeler la
fonction à chacun. Elle est **idempotente** : une vente déjà `REGLEE` ne bouge plus.

Montant du règlement = `amount_total` de la session Stripe (ou de la facture), en
centimes, **tel que Stripe l'a encaissé**. Si ce montant diffère de la somme des
articles, `encaisser_vente` refuse (égalité rompue) : la vente reste `EN_ATTENTE`,
l'erreur part dans les journaux / Sentry, et **la livraison du billet ou de
l'adhésion n'est pas bloquée** (la machine à statuts de `LigneArticle` est
inchangée). La vente en attente est visible en admin (fiche G). Un test le vérifie.

Expiration / échec (`FAILED`, `CANCELED`, session expirée) : `annuler_vente`.

## 3. Session D-2 — ventes sans Stripe

| Producteur | Fichier | Règlement |
|---|---|---|
| Billets vendus dans l'admin | `Administration/admin_tenant.py` `ReservationAddAdmin.save` ~l.3116 | moyen choisi (espèces, CB, chèque, offert) |
| Paiement d'adhésion dans l'admin | `BaseBillet/views.py` `ajouter_paiement` ~l.4477 | moyen choisi |
| Adhésion créée / renouvelée dans l'admin | `BaseBillet/signals.py` ~l.494 | moyen de l'adhésion |
| Adhésion gratuite (API) | `BaseBillet/validators.py` ~l.1144 | aucun (total 0) |
| Réservation API v1 | `ApiBillet/serializers.py` ~l.1185 | moyen déclaré (« payé ailleurs ») |
| Réservation gratuite API v2 | `api_v2/serializers.py` ~l.1463 | aucun ; `qty` castée en entier (aujourd'hui brute) |
| Recharge cadeau API v2 | `api_v2/views.py` `_creer_ligne_article_recharge` ~l.987 | `FREE` (cadeau émis) ; article `hors_chiffre_affaires`, **entièrement offert** (`part_offerte` = total, `OFFRIR`) ; nature `RECHARGE` |
| Webhook Fedow d'adhésion (legacy) | `fedow_connect/views.py` ~l.97 | moyen reçu ; enveloppé dans une vente (D24 : le webhook reste) |
| Booking gratuit | `booking/booking_engine.py` ~l.743 | aucun |

Gratuit : total 0, aucun règlement, égalités 0 = 0. La vente est numérotée (c'est une
opération enregistrée).

Pas de vente : `BankTransferService.enregistrer_virement` (`fedow_core/services.py`
~l.1155, virement entre lieux, aucun appelant hors tests) — ce n'est pas une vente
(TODO `COMPTABILITE-inter-tenants.md`). Le rapport unique l'ignore.

## 4. Session D-3 — avoirs et remboursements

| Producteur | Fichier | Règlement négatif |
|---|---|---|
| Annulation d'adhésion | `BaseBillet/views.py` `cancel` ~l.4593 | moyen d'origine |
| Avoir de réservation hors Stripe | `BaseBillet/models.py` `Reservation._creer_avoir` ~l.2978 | moyen d'origine |
| Avoir de booking | `booking/models.py` `_creer_avoir` ~l.626 (poser aussi la FK `booking`, manquante) | moyen d'origine |
| Remboursement Stripe (total ou partiel) | `PaiementStripe/utils.py` `partial_refund_payment` ~l.78 | Stripe, montant = **montant du refund renvoyé par Stripe**, `reference_externe` = id du refund |
| Avoir émis dans l'admin | `Administration/admin_tenant.py` `emettre_avoir` ~l.2101 | voir ci-dessous |

Règles :

- Vente `AVOIR`, `vente_liee` = `ligne_d_origine.vente` (vide si la ligne d'origine
  n'a pas de vente : lignes de dev antérieures au chantier).
- Article : **même prix unitaire, quantité négative** (D13), montants entiers par
  `calculer_montants_article`.
- **Avoir partiel d'une vente à plusieurs règlements** (possible pour une vente de
  caisse) : le montant négatif est réparti sur les règlements d'origine au **plus
  grand reste** (fonction `repartir_au_plus_grand_reste(montant, poids)` dans
  `services_vente.py`, entiers, Σ parts = montant exactement). C'est la **seule**
  répartition du projet, faite **une fois**, à l'écriture.
- Remboursement Stripe : le montant du règlement est celui de Stripe ; si Stripe
  rembourse moins que la somme des articles de l'avoir (frais, arrondi), l'égalité
  refuse → l'avoir reste `EN_ATTENTE` + erreur journalisée (même règle qu'en §2).

## 5. Tests

Fichiers : `tests/pytest/test_en_ligne_ecrit_la_vente.py`,
`tests/pytest/test_avoirs_ecrivent_la_vente.py` (Stripe mocké comme les tests
existants `tests/pytest/` PaiementStripe ; fabriques `fabriques_panier`).

| # | Test | Attendu |
|---|---|---|
| 1 | `test_checkout_billets_vente_en_attente_sans_numero` | vente `EN_ATTENTE`, `numero` vide, 0 règlement |
| 2 | `test_webhook_paye_encaisse_la_vente_montant_stripe` | `REGLEE`, numéro, 1 règlement = `amount_total` |
| 3 | `test_webhook_rejoue_deux_fois_une_seule_encaisse` | idempotent |
| 4 | `test_retour_checkout_puis_webhook_une_seule_encaisse` | idempotent entre chemins |
| 5 | `test_session_expiree_vente_annulee_sans_numero` | `ANNULEE` |
| 6 | `test_montant_stripe_different_vente_reste_en_attente_billet_livre` | vente `EN_ATTENTE`, erreur journalisée, réservation valide |
| 7 | `test_abonnement_une_vente_par_facture_prix_unitaire` | quantité 2 → `amount` unitaire, total = facture |
| 8 | `test_panier_commande_liee_a_la_vente` | `Commande.vente` |
| 9 | `test_vente_admin_billets_especes_encaissee` | 1 règlement espèces |
| 10 | `test_reservation_gratuite_vente_zero_numerotee` | total 0, aucun règlement, numéro posé |
| 11 | `test_recharge_cadeau_api_hors_ca_reglement_free` | nature `RECHARGE`, article offert en totalité (net 0), règlement `FREE` = total ; les deux égalités tiennent |
| 12 | `test_api_v2_quantite_texte_castee_en_entier` | `"2"` → 2 ; `"2.5"` → refus |
| 13 | `test_remboursement_stripe_partiel_avoir_montant_du_refund` | vente `AVOIR` liée, qty négative, règlement = refund, `reference_externe` |
| 14 | `test_avoir_admin_vente_caisse_deux_reglements_plus_grand_reste` | vente 1050 (500 LE + 550 CB), avoir de 1 jus (350) → −167 / −183 (Σ = −350) |
| 15 | `test_repartir_au_plus_grand_reste_somme_exacte` | 100 sur poids 1/1/1 → 34/33/33 ; 5 sur 70/30 → 4/1 ; montant négatif |
| 16 | `test_annulation_adhesion_avoir_lie` | vente `AVOIR`, `vente_liee` |
| 17 | `test_avoir_booking_pose_la_fk_booking` | FK `booking` renseignée |

Vus rouges : tous (aucune vente) sauf 12 (comportement actuel à observer : noter la
sortie).

Mutations : encaisser à la création du checkout (1) ; montant du règlement = Σ
articles au lieu du montant Stripe (6) ; retirer l'idempotence (3, 4) ; `amount` =
total de la ligne Stripe (7) ; répartition proportionnelle arrondie sans plus grand
reste (14, 15) ; prix unitaire négatif au lieu de la quantité (13).

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-D-en-ligne-avoirs.md`.
