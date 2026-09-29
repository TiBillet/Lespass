# Chantier 05-B — La caisse écrit aussi la Vente et ses règlements

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue Fable + Opus, corrigée
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D7 à D14, D17, R3, R6
> Effort : 4,5 j (4 sessions : §2 bis B-0, §3, §4, §5) — Dépend de : A. **Migration : oui** (lien
> `consigne_remboursee` sur `Product`).
> Les lignes sont écrites comme aujourd'hui (même `amount`, même `qty`), avec en plus
> leur vente, leurs règlements et leurs montants entiers. **Une seule valeur change
> pour les anciens lecteurs** : la TVA d'une ligne de recharge passe de 20 % (défaut du
> produit, `_compute_default_vat`) à **0** (§7). La nouvelle forme poids / tireuse (D15)
> attend la fiche H (R6).

## 1. Le principe

Chaque **encaissement** de la caisse (un clic sur un moyen de paiement qui réussit)
produit **une `Vente` encaissée**, dans la même transaction de base que les lignes.

- Les lignes passent par `ajouter_article(...)` au lieu de `LigneArticle.objects.create(...)`,
  avec leurs champs historiques (`payment_method`, `asset`, `carte`, `uuid_transaction`…).
- Une ligne coupée en parts (cascade) reçoit, par part, `total_catalogue_impose` =
  **l'argent réel de la part** (3ᵉ élément du tuple). Voir le §5 du tronc.
- **HT et empreinte par ligne** : la boucle HMAC existante (`laboutik/views.py`
  ~l.5510-5532 et ~l.5824-5846) recalcule `total_ht` par `calculer_total_ht()`, un
  `round()` flottant arrondi au pair (`laboutik/integrity.py` ~l.167-183) : 111 c à
  20 % donnerait 92 au lieu de 93, et `total_ht + total_tva ≠ total_ttc`. La boucle
  **reprend `ligne.total_ht` posé par `ajouter_article`** et écrit par `.update()`
  (jamais de seconde `save()`, fiche A §3).
- Les règlements sont écrits **à partir des débits réels**, jamais depuis les lignes :

| Source de l'argent | Règlement |
|---|---|
| `TransactionService.creer_vente(...)` (une par monnaie et par carte : ~l.8412-8450, ~l.9503-9540, ~l.10057-10115) | un règlement : `moyen` = moyen de la monnaie, `montant` = `montant_en_centimes` passé, `asset`, `carte`, `wallet`, `fedow_transaction_uuid` = uuid de la transaction **renvoyée** (plusieurs appels, dont ~l.8440, jettent aujourd'hui la valeur de retour : la garder) |
| Débit legacy Fedow (`_debiter_legacy`, `_repartir_legacy_sur_articles` ~l.1385-1430) | **un règlement par transaction legacy** (élément de `transactions_legacy`), montant = `transaction["amount"]`, référence = `transaction["uuid"]`. `_debiter_legacy` ne renvoie aujourd'hui que `(asset, amount, pm)` (~l.1625) : étendre le tuple avec l'uuid |
| Espèces / CB / chèque (paiement direct ou complément) | un règlement, montant **encaissé** (somme du panier ou `reste_complement`) |
| Monnaie cadeau (TNF / LG) | un règlement `LG` (offert, D8) + sur la part : `part_offerte` = montant de la part, `source_offert = JETONS` |
| OFFRIR (FREE, mode gérant) | `ajouter_article(..., offert_en_totalite=True)` : un règlement `FREE` du total + sur chaque ligne : `part_offerte = total_catalogue`, `source_offert = OFFRIR` |
| Recharge cadeau (`RC`) | article recharge `hors_chiffre_affaires`, offert en totalité (`offert_en_totalite=True`, `OFFRIR`, net 0) + règlement `FREE` du total |
| Recharge temps (`TM`) | aujourd'hui hors caisse (commentée, ~l.1685) ; si réactivée, même règle que la recharge cadeau |
| Points (NM) | `Vente.unite` = uuid de la monnaie ; un règlement `NM` par transaction (une par article : ~l.8409-8427) ; TVA 0 |

- `Vente.origine = LABOUTIK`, `point_de_vente`, `operateur` (carte primaire / user),
  `client` et `carte` quand ils sont connus.
- `Vente.nature = VENTE`, recharges comprises : une recharge est un article
  `hors_chiffre_affaires` d'une vente ordinaire. Les rapports lisent ce champ, jamais
  la nature.
- `prix_achat` = `Product.prix_achat` (`BaseBillet/models.py` ~l.1452) lu à la vente.
  **Coût sur la quantité réelle** (`quantite_pour_cout`, fiche A) : pour une vente au
  poids / à la mesure, la ligne garde `qty = 1` et le poids dans `weight_quantity`
  (en g ou en cl, `laboutik/views.py` ~l.5414) ; `quantite_pour_cout` =
  `weight_quantity / 1000` (g → kg) ou `/ 100` (cl → L), multiplié par la fraction de
  la part si la ligne est coupée. Pour une part d'un article à l'unité, `qty` de la
  part suffit.
- Aucun règlement de montant 0 (panier OFFRIR à 0 €, articles gratuits).

### Échec d'égalité et débits déjà faits

Si `encaisser_vente` lève `EgaliteDeVenteRompue`, l'`atomic` du producteur annule
les lignes **et les débits fedow_core** (base locale, même transaction). **Mais pas le
débit legacy** : `_debiter_legacy` (appel réseau, sans remboursement possible) est fait
**avant** l'`atomic` (~l.8338, ~l.9456, ~l.9856, ~l.10008). Aujourd'hui seul
`SoldeInsuffisant` y est attrapé (~l.8535), avec le journal « INCIDENT legacy débité
sans LigneArticle ». **`EgaliteDeVenteRompue` est attrapée au même endroit**, avec le
même journal d'incident (montant, carte, transaction legacy), et l'écran d'erreur de
la caisse. Un test le vérifie.

## 2. Les producteurs de la caisse (inventaire, diagnostic §1)

| Chemin | Fonction (`laboutik/views.py`) | Ce qui change |
|---|---|---|
| CB, chèque, OFFRIR | appel ~l.7417 → `_creer_lignes_articles` ~l.5311 | vente + 1 règlement (ou FREE + parts offertes) |
| Espèces | ~l.7642 → `_creer_lignes_articles` | vente + 1 règlement espèces |
| Recharges (RE, RC) | `_executer_recharges` ~l.6621 (appelée ~l.7433, 7658, 8397, 8875, 9486, 10040) | articles `hors_chiffre_affaires` dans **la même vente** que le reste du panier ; `uuid_transaction` passé (manquait) |
| Retour de consigne **par carte** | `_rembourser_consigne_par_nfc` ~l.7753 | vente `AVOIR` sans vente liée ; règlement négatif = transaction de recrédit |
| Retour de consigne **en espèces** | `_payer_en_especes` ~l.7513 (moyens proposés pour un retour : espèces ou carte, `moyens_paiement` ~l.5211-5220 ; panier mélangé refusé, `_panier_est_uniquement_retour_consigne` ~l.2099) | vente `AVOIR` ; règlement espèces négatif |
| Paiement NFC seul | `_payer_par_nfc` ~l.7902 (appel de la cascade ~l.8457) → `_creer_lignes_articles_cascade` ~l.5559 | règlements par transaction (points, cascade, legacy) ; la fonction expose **en plus** la vente (attribut sur la réponse ou tuple) : elle renvoie toujours le HTML que `payer_commande` inspecte (~l.11773) |
| Complément espèces/CB | `_executer_paiement_complementaire` ~l.9139 (part espèces/CB ~l.9546) | règlements carte 1 + FED partiel + règlement espèces/CB du reste |
| 2ᵉ carte | ~l.10147 | chaque règlement porte **sa** carte (les lignes gardent `carte=carte1` jusqu'à H) |
| Adhésion payée à la caisse | ~l.8515-8535 | la FK `membership` **reste sur une seule part** jusqu'à H (la poser sur chaque part relancerait les déclencheurs d'adhésion une fois par ligne) ; la facture lit la vente (fiche G) |
| Commande de table | `payer_commande` ~l.11565-11891 (hors NFC ~l.11818, NFC ~l.11760) | une vente ; `CommandeSauvegarde.vente` renseignée (en NFC : depuis la vente renvoyée par `_payer_par_nfc`, le succès étant aujourd'hui détecté dans le HTML ~l.11773) ; `uuid_transaction` et clé d'idempotence passés (manquaient) |
| Vider carte | `fedow_core/services.py` `rembourser_en_especes` ~l.517-700 (appelé ~l.10645) | vente `VIDAGE_CARTE` sans article : **un règlement par transaction REFUND** (une par jeton éligible : la TLF du lieu et la FED, ~l.579-590) + un règlement espèces −(total). Les jetons cadeau (TNF) ne sont ni rendus ni touchés par cette fonction : aucun règlement pour eux. Les lignes « Refund » restent jusqu'à H |
| Correction de moyen | `corriger_moyen_paiement` ~l.10960-11130 | en plus de la correction actuelle des lignes : vente `CORRECTION` liée, règlements `−ancien` / `+nouveau` du montant corrigé |

Idempotence : `_executer_avec_cle_idempotence` (~l.4611) cherche des lignes par
`uuid_transaction` ; `Vente.idempotency_key` reçoit la même clé. Un rejeu retrouve la
vente et ne crée rien.

## 2 bis. Session B-0 — effets d'adhésion communs (décision du mainteneur, 2026-09-29)

**Changement voulu de la logique métier**, séparé des montants : une adhésion payée a
**les mêmes effets en ligne et en caisse**, par **un seul code**.

Aujourd'hui : en ligne, `trigger_A` (`BaseBillet/triggers.py` ~l.255) pose l'échéance,
rattache l'utilisateur au lieu (`client_achat`), complète son nom, envoie la facture par
mail, gère la newsletter, puis (on_commit) la récompense en monnaie et l'envoi à l'ancien
LaBoutik. En caisse, `_creer_ou_renouveler_adhesion` (`laboutik/views.py` ~l.5869) ne
fait que créer / renouveler et poser l'échéance (ligne créée `VALID`, aucun
déclencheur).

Le changement :

- Une **fonction explicite** (pas de passage de la caisse par la machine à états) :
  `appliquer_les_effets_d_une_adhesion_payee(adhesion, ligne_article)` dans
  `BaseBillet/triggers.py`. Elle fait : échéance, `client_achat`, nom / prénom, facture
  par mail, newsletter, récompense en monnaie (on_commit).
- `trigger_A` l'appelle, et garde **seulement** ce qui est propre au web :
  `update_membership_state_after_stripe_paiement` (avant) et l'envoi à l'ancien LaBoutik
  (on_commit, après). Même ordre des tâches qu'aujourd'hui : les tests A′-1 et A′-3
  restent verts **sans modification**.
- La caisse l'appelle après chaque `_creer_ou_renouveler_adhesion` (4 appels :
  ~l.6301, ~l.8516, ~l.9583, ~l.10169). **Pas d'envoi à l'ancien LaBoutik** : la caisse
  V2 ne parle pas à la caisse legacy (mainteneur, 2026-09-29).
- L'échéance n'est posée **qu'une fois** : `_creer_ou_renouveler_adhesion` ne la pose
  plus (deux enregistrements = deux `webhook_membership`, voir P15). À vérifier au
  démarrage.
- Cascade (plusieurs lignes pour une adhésion, T14) : la fonction est appelée **une
  fois**, avec la ligne qui porte la FK `membership`.
- Adhésion sans utilisateur (carte anonyme) : `_creer_ou_renouveler_adhesion` rend
  `None`, rien n'est appelé (comme aujourd'hui).

Tests (`tests/pytest/test_caisse_effets_adhesion.py`, vus rouges) :

| Test | Vérifie |
|---|---|
| `test_adhesion_caisse_especes_demande_facture_et_recompense` | tâches `send_membership_invoice_to_email` et `refill_from_lespass_to_user_wallet_from_price_solded` demandées, **pas** `send_sale_to_laboutik` ; utilisateur rattaché au lieu |
| `test_adhesion_caisse_nfc_demande_facture_et_recompense_une_fois` | chemin cascade : une seule facture, une seule récompense |
| `test_adhesion_caisse_renouvelee_echeance_posee_une_fois` | un seul `webhook_membership` au renouvellement |
| `test_facture_de_l_adhesion_caisse_part_au_bon_destinataire` | la tâche de facture, **exécutée** (appel direct, pas `.delay`), dépose un mail dans `mailoutbox` (pytest-django) : destinataire = e-mail de l'adhérent, pièce jointe PDF |

Mutations : retirer l'appel dans la caisse (le test espèces tombe) ; retirer l'appel dans
`trigger_A` (les tests A′-1 d'adhésion tombent) ; remettre `set_deadline` dans
`_creer_ou_renouveler_adhesion` (le test de renouvellement tombe).

Test A′ qui change ici (fiche A′ §4) : `test_vente_caisse_adhesion_sans_facture_ni_envoi_laboutik`
→ renommé `test_vente_caisse_adhesion_facture_et_recompense_sans_envoi_laboutik`.

## 3. Session B-1 — un moyen de paiement (espèces, CB, chèque, OFFRIR, recharges, consigne)

- `_creer_lignes_articles` et ses appelants, `_executer_recharges`, retours de consigne.
- **Consigne reliée (D11)** : `Product.consigne_remboursee` = FK nullable vers `Product`
  (le gobelet vendu), sur les produits `methode_caisse = CR`. Au retour, l'article
  reprend le **prix et le taux de TVA du produit consigne** (plus ceux du produit de
  retour). Admin : un champ « Rembourse la consigne : […] » visible seulement pour la
  méthode « Retour de consigne » ; un retour sans consigne reliée est refusé à la
  vente avec un message clair. La ligne garde `amount` négatif et `qty` positive
  jusqu'à H (`calculer_remboursements` lit `amount < 0`).

Tests : §6, lignes 1 à 8.

## 4. Session B-2 — la cascade (NFC, complément, 2ᵉ carte, points, jetons, legacy)

`_creer_lignes_articles_cascade` et ses trois appelants. `_calculer_qty_partielles`
reste (anciens lecteurs) ; la part reçoit en plus son argent réel. Tests : §6, lignes
9 à 17.

## 5. Session B-3 — commandes de table, vider carte, correction

Tests : §6, lignes 18 à 22.

## 6. Tests

Fichier : `tests/pytest/test_caisse_ecrit_la_vente.py` (réutiliser les helpers de
`tests/pytest/test_paiement_complementaire.py` et des tests de cascade). Chaque test ne
lit **que sa vente** (retrouvée par `idempotency_key` / `uuid_transaction`) → base
partagée ; le 23 (anciens rapports) en schéma dédié. Chaque test finit par
`verifier_egalites(vente)` (fiche A) ; pendant la transition, aucun test n'asserte le HT
d'une part (±1 c, §5 du tronc).

| # | Test | Attendu |
|---|---|---|
| 1 | `test_vente_especes_trois_jus_une_vente_un_reglement` | vente numérotée `REGLEE`, 1 règlement espèces 1050, article 1050 / 875 / 175 |
| 2 | `test_vente_cb_prix_libre` | total catalogue = saisie |
| 3 | `test_offrir_en_mode_gerant_part_offerte_totale` | net 0, TVA 0, règlement FREE = catalogue |
| 4 | `test_recharge_seule_hors_ca_tva_zero` | nature `VENTE`, article `hors_chiffre_affaires`, `vat` **0** en base |
| 5 | `test_biere_et_recharge_meme_panier_une_seule_vente` | 2 articles (1 hors CA), 1 règlement ; lignes de recharge avec `uuid_transaction` |
| 6 | `test_recharge_cadeau_offerte_en_totalite` | net 0, `OFFRIR`, règlement FREE |
| 7 | `test_retour_consigne_reprend_prix_et_tva_du_gobelet` | gobelet 100 à 20 %, produit retour réglé à 5,5 % → article du retour à 20 %, −100 |
| 8 | `test_retour_consigne_especes_vente_avoir` | règlement espèces négatif |
| 9 | `test_nfc_trois_jus_500_le_550_cb_parts_entieres` | l'exemple fil rouge : parts 500 / 550, règlements LE 500 (`fedow_transaction_uuid`) + CB 550 |
| 10 | `test_reglement_fedow_egal_montant_de_la_transaction` | Σ règlements cashless = Σ `Transaction.amount` créées |
| 11 | `test_deux_articles_meme_monnaie_un_seul_reglement_par_monnaie` | |
| 12 | `test_jetons_benevoles_part_offerte_hors_tva` | bière 500 = 300 jetons + 200 CB → part jetons offerte 300 net 0 ; part CB net 200, HT 167, TVA 33 ; règlements LG 300 + CB 200 |
| 13 | `test_deuxieme_carte_chaque_reglement_porte_sa_carte` | |
| 14 | `test_vente_en_points_unite_monnaie_tva_zero` | |
| 15 | `test_legacy_un_reglement_par_transaction_legacy` | montant et uuid de la transaction |
| 16 | `test_egalite_rompue_apres_debit_legacy_journalisee` | incident journalisé, écran d'erreur, pas d'erreur 500 |
| 17 | `test_ht_de_la_part_111_centimes_vaut_93` | la boucle HMAC ne recalcule plus au pair |
| 17b | `test_vente_au_poids_cout_sur_le_poids_reel` | fromage 350 g, prix d'achat 800 / kg → `cout_achat` 280 (et non 800) |
| 18 | `test_paiement_table_especes_vente_liee_a_la_commande` | `CommandeSauvegarde.vente` |
| 19 | `test_paiement_table_nfc_vente_liee_a_la_commande` | idem par NFC |
| 20 | `test_vider_carte_tlf_et_fed_deux_reglements` | TLF du lieu 500 + FED 300 → règlements LE +500 et SF +300, espèces −800, Σ = 0 |
| 21 | `test_correction_moyen_nouvelle_vente_correction` | vente liée, −CA +CB, vente d'origine inchangée (empreinte valide) |
| 22 | `test_rejeu_meme_cle_idempotence_une_seule_vente` | |
| 23 | `test_anciens_rapports_inchanges` | schéma dédié : l'ancien rapport caisse donne les mêmes totaux avant / après (scénarios 1, 9, 12) |

Vus rouges : 1-22 et 17b (aucune vente, TVA 20 en 4, HT 92 en 17). Le 16 est rouge
parce que l'exception n'existe pas encore (`ImportError` noté), puis rouge contre un
producteur qui ne l'attrape pas (erreur 500 noté). Le 23
est vert avant et doit le rester (non-régression : le noter tel quel).

Mutations :

| Mutation | Doit faire tomber |
|---|---|
| `total_catalogue_impose` retiré (calcul depuis la `qty` partielle) | 9 |
| règlement cashless = somme des parts au lieu du montant de la transaction | 10 |
| règlement legacy par part au lieu de par transaction | 15 |
| ne plus attraper `EgaliteDeVenteRompue` après le débit legacy | 16 |
| boucle HMAC qui repasse par `calculer_total_ht` | 17 |
| `quantite_pour_cout` non passé pour le poids | 17b |
| règlement LG compté comme argent (moyen CB) | 12 |
| retour de consigne avec la TVA de son propre produit | 7 |
| `carte=carte1` sur les règlements de la carte 2 | 13 |
| `CommandeSauvegarde.vente` non posée | 18, 19 |
| correction qui modifie la vente d'origine | 21 |
| `idempotency_key` non posée | 22 |

E2E : `make e2e` complet en fin de fiche (l'écran de la caisse ne change pas). CHANGELOG :
`CHANGELOG/2026-MM-JJ-montants-entiers-B-caisse.md` (chaînes i18n : champ « Rembourse
la consigne », message de refus).

## 7. Tests existants à réécrire

| Cause | Fichiers |
|---|---|
| TVA des lignes de recharge : 20 % → 0 (ancien Z, archive LNE, FEC caisse) | `rg -ln "RECHARGE_EUROS|RECHARGE_CADEAU|recharge" tests/pytest/` au démarrage de B-1 ; en particulier `test_ventes_remontent_au_ticket_z.py`, `test_archivage_fiscal_lne.py`, `test_hors_argent_offerts.py`, `test_cloture_*.py` : valeurs de TVA attendues à relire |
| Rejeu d'idempotence : les lignes de recharge portent désormais `uuid_transaction` | tests du rejeu caisse (`rg -ln "_executer_avec_cle_idempotence|uuid_transaction" tests/pytest/`) : la réponse rejouée peut contenir plus de lignes |

Chaque réécriture est listée dans le CHANGELOG avec sa raison.

## Machine à états — compléments obligatoires

Source : [`CHANTIER-05-machine-a-etats.md`](CHANTIER-05-machine-a-etats.md) §5 (trous T…). Les tests de
caractérisation de la fiche A′ doivent rester verts pendant cette fiche.

| Trou | À faire dans cette fiche | Test |
|---|---|---|
| T14 | La FK adhésion / réservation d'un paiement en parts est posée sur la **dernière** part (`laboutik/views.py` ~l.6289, ~l.6491) ou la **première** (~l.8477, ~l.9580, ~l.10166) selon le chemin. B **ne change rien** (« comme aujourd'hui ») ; H fusionne. | `test_caracterisation_caisse.py` (fiche A′) reste vert |
| T11 | Hors B : le bouton de clôture libère les tables (voir fiche G). Rien à faire ici. | — |
