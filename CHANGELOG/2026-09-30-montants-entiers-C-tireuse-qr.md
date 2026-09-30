# Tireuse et paiement QR / NFC écrivent leur vente (chantier 05, fiche C) / Tap and QR / NFC payment write their sale (worksite 05, sheet C)

**Date :** 2026-09-30
**Migration :** Non

## Resume / Summary
**Quoi / What :** chaque tirage de la tireuse et chaque paiement en ligne par QR code ou carte NFC écrit maintenant une `Vente` scellée (numérotée, chaînée) avec une part d'article et un règlement par monnaie débitée. La tireuse paie comme le cashless de la caisse : monnaies locales d'abord, puis l'ancien Fedow. Le QR / NFC en ligne reste sur l'ancien Fedow seul, et n'envoie plus rien à l'ancien LaBoutik. /
Each tap pour and each online QR / NFC payment now writes a sealed, chained `Vente` with one item part and one payment per debited currency. The tap pays like the register's cashless (local currencies, then the old Fedow). Online QR / NFC stays on the old Fedow only and no longer sends anything to the old LaBoutik.

**Pourquoi / Why :** chantier 05 « montants entiers » : toute vente passe par le service de vente (argent en centimes entiers, égalités vérifiées, chaîne des ventes). /
Worksite 05 "whole amounts": every sale goes through the sale service.

Sections ci-dessous : C-0 (tests controlvanne isolés), C-1a (tireuse, monnaies locales), C-1b (tireuse, ancien Fedow), C-2 (QR / NFC). / Sections below: C-0, C-1a, C-1b, C-2.

## Tests controlvanne : les tirages facturés tournent sous `django_db` / Controlvanne tests: billed pours run under `django_db`

**Type :** tests seulement / tests only

### Resume / Summary
**Quoi / What :** les tests controlvanne qui facturent un tirage (`pour_end`, fermeture d'une session orpheline) sont marqués `django_db`. Le rollback de fin de test efface la vente, les règlements, les cartes et les portefeuilles qu'ils créent. Les nettoyages manuels devenus inutiles sont retirés. /
Controlvanne tests that bill a pour are marked `django_db`; the end-of-test rollback erases everything they create, and the now useless manual cleanups are removed.

**Pourquoi / Why :** une vente enregistrée protège sa carte, son portefeuille et son point de vente (clés étrangères en `PROTECT`). Un nettoyage manuel qui supprime la carte échouerait donc en `ProtectedError`, et les lignes de test s'accumulaient dans la base de dev. /
A recorded sale protects its card, wallet and POS (`PROTECT` foreign keys): a manual cleanup would raise `ProtectedError`, and test rows piled up in the dev database.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_controlvanne_billing.py` | `TestBillingIntegration` et `TestSessionOrpheline` passent en `django_db` ; nettoyages retirés (test_07 carte à zéro, test_08 deux monnaies) |
| `tests/pytest/test_controlvanne_review_fixes.py` | La fixture `rf_tireuse` réutilise tireuse, point de vente et terminal au lieu de les supprimer |
| `tests/pytest/test_controlvanne_facturation_lot2.py` | `TestFacturationLot2` passe en `django_db` ; nettoyages retirés (Stock du test_04, remise du réservoir du test_05) |

### Tests passés en `django_db`
- `test_controlvanne_billing.py` : `test_05`, `test_06` (pour_end 500 ml), `test_07`, `test_08_pour_end_reparti...` (deux monnaies) ; `TestSessionOrpheline::test_08` (fermeture d'une session orpheline).
- `test_controlvanne_facturation_lot2.py` : `test_04` (pour_end), `test_05` (clôture directe), `test_06` (pour_end), `test_07`.
- Déjà `django_db`, inchangés : `test_controlvanne_api.py`, `test_controlvanne_models.py`.

### Nettoyages retirés (objets créés dans le test, effacés par le rollback)
- billing `test_07` : carte, jetons et portefeuille à zéro.
- billing `test_08` (deux monnaies) : lignes de vente, transactions, jetons, carte, portefeuille.
- lot2 `test_04` : `Stock` créé par le test.
- lot2 `test_05` : remise du réservoir à 30 000 ml (la modification est annulée par le rollback).
Les objets des fixtures de session (tireuse, asset, carte à solde) gardent leur nettoyage de fixture.

### Reste hors `django_db` : le test des deux threads, assumé comme un E2E
`test_controlvanne_review_fixes.py::TestC1DoubleFacturationConcurrente` lance deux threads, chacun avec sa propre connexion : ils ne voient pas les données d'une transaction non validée. Le test reste donc sans `django_db` et laisse de vraies données en base de dev (une vente par exécution), comme un test E2E.
La fixture `rf_tireuse` ne supprime plus jamais la tireuse, son point de vente ni son terminal : une vente enregistrée protège le point de vente (`PROTECT`). Elle les réutilise s'ils existent (recherche par nom, création seulement s'ils manquent), remet l'état attendu (actif, fût, réservoir illimité, 30 000 ml) et ferme les sessions restées ouvertes.
Billing `test_07` : l'assignation inutilisée `carte_zero` est retirée (la carte reste créée).

## La tireuse écrit sa vente (monnaies locales) / The tap writes its sale (local currencies)

**Migration :** Non — **Chaînes i18n :** aucune nouvelle.

**Quoi / What :** au `pour_end`, `facturer_tirage` écrit le tirage par le service de vente, dans son `atomic` existant, après les débits en cascade (inchangés) :
- une `Vente` d'origine `TIREUSE`, nature `VENTE`, au point de vente de la tireuse, avec la carte et son utilisateur comme client (aucun pour une carte anonyme), sans opérateur ;
- un article par monnaie débitée (`ajouter_article`), forme des lignes inchangée (`amount` = total du tirage, `qty` = fraction de 1, mêmes champs historiques). Total catalogue = débit réel de la monnaie ; TVA par `_taux_tva_de_la_ligne_de_caisse` ; part en jetons cadeau offerte en entier (JETONS) ; coût d'achat = litres servis × fraction de la part × prix d'achat du fût au litre ;
- un règlement par transaction `fedow_core` créée : montant et uuid copiés (`fedow_transaction_uuid`) ;
- `encaisser_vente` en dernier. `EgaliteDeVenteRompue` n'est pas attrapée : tout est annulé, 500, Sentry.
Le total d'un tirage (`calculer_montant_centimes`, commun à la facture et à l'écran de la tireuse) est arrondi au centime demi-haut : 173 ml à 5 €/L = 87 c (86 avant). /
At pour end, the pour is written through the sale service: one TIREUSE sale, one item per debited currency (same line shape, real debited money, gift tokens offered, cost on the litres), one payment per local transaction, settled last. The pour total is rounded half-up (screen and bill alike).

**Pourquoi / Why :** chantier 05 (montants entiers) : l'argent est écrit une fois, en centimes entiers, et la tireuse entre dans la chaîne des ventes du lieu. /
Money is written once in whole cents, and the tap joins the venue's sale chain.

| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/billing.py` | `calculer_montant_centimes` demi-haut ; `facturer_tirage` ouvre, remplit et encaisse la vente |
| `tests/pytest/test_tireuse_ecrit_la_vente.py` | nouveau : 10 tests (dont 1 en schéma dédié) |

**Tests existants changés :** aucun. Aucun test controlvanne n'asserte un total tombant sur un demi-centime.

**Tests ajoutés** (`tests/pytest/test_tireuse_ecrit_la_vente.py`, vraies routes `authorize` puis `pour_end`, `django_db`) :
`test_tirage_50cl_une_vente_un_reglement`, `test_tirage_jetons_et_monnaie_locale_parts_entieres`, `test_tirage_88_centimes_30_plus_58`, `test_total_tirage_arrondi_demi_haut`, `test_montant_ecran_egal_montant_facture_demi_haut`, `test_tirage_solde_insuffisant_total_egal_debit_reel`, `test_tirage_cout_sur_les_litres_reels`, `test_tirage_ne_prend_ni_temps_ni_fidelite` (témoin, vert avant le code), `test_tirage_egalite_rompue_remonte_et_n_ecrit_rien`, `TestTireuseVenteChainee::test_tirage_vente_chainee` (schéma dédié `test_tireuse_vente`).

**Vus rouges avant le code :** 8 failed, 1 passed (« 0 vente trouvée » ×6 ; `assert 86 == 87` ×2 : total et écran), puis le test d'égalité rompue seul : `Failed: DID NOT RAISE <class 'BaseBillet.services_vente.EgaliteDeVenteRompue'>`.

**Vert après le code :** fichier 10 passed ; `test_controlvanne_*.py` 85 passed ; `test_caracterisation_*.py` 22 passed ; `test_vente_*.py` 135 passed ; `manage.py check` sans erreur.

**Mutations (à jouer par l'orchestrateur)** — `controlvanne/billing.py` :
| Mutation | Ligne | Test attendu en échec |
|---|---|---|
| `round()` au lieu du demi-haut | l.137 | `test_total_tirage_arrondi_demi_haut`, `test_montant_ecran_egal_montant_facture_demi_haut` |
| `total_catalogue_impose` retiré (part depuis la fraction) | l.471 | aucun : équivalente (qty à 6 décimales), gardée comme double sécurité |
| règlement jetons en argent (moyen LE au lieu de LG) | l.494 | `test_tirage_jetons_et_monnaie_locale_parts_entieres`, `test_tirage_88_centimes_30_plus_58`, `test_tirage_cout_sur_les_litres_reels` (égalité rompue) |
| part jetons non offerte | l.450 | les trois mêmes |
| coût sur la fraction au lieu des litres | l.472 | `test_tirage_cout_sur_les_litres_reels` |
| `encaisser_vente` retiré | l.551 | `test_tirage_50cl_une_vente_un_reglement`, `test_tirage_egalite_rompue_remonte_et_n_ecrit_rien`, `TestTireuseVenteChainee::test_tirage_vente_chainee` (et tout test qui lit la vente) |
| `point_de_vente` non passé à la vente | l.406 | `test_tirage_50cl_une_vente_un_reglement` |
| règlement sans `fedow_transaction_uuid` | l.499 | `test_tirage_50cl_une_vente_un_reglement`, `test_tirage_jetons_et_monnaie_locale_parts_entieres`, `test_tirage_solde_insuffisant_total_egal_debit_reel` |

## La tireuse paie aussi avec l'ancien Fedow / The tap also pays with the old Fedow

**Migration :** Non — **Chaînes i18n :** aucune nouvelle.

**Quoi / What :** la tireuse paie comme le cashless de la caisse. Monnaies locales d'abord (jetons cadeau TNF → TLF → FED local), puis le reste sur l'ancien Fedow par `_debiter_legacy` (TLF fédérés puis FED ; moyens `LE` / `SF`). Temps et fidélité : jamais.
- Ancien Fedow seulement pour une carte d'utilisateur dans un lieu relié (`lire_depensable_fed_frais`) ; carte anonyme ou lieu non relié : aucun appel.
- Au badge (`authorize`) : solde = monnaies locales + ancien Fedow lu frais ; ancien Fedow injoignable = 0, jamais de refus pour ça. Une seule fonction de solde (`calculer_solde_de_la_carte`) sert au badge et à l'écran (`_lire_le_solde_de_la_carte`).
- À la fin du service : débits locaux, puis relecture du solde distant et débit de `min(solde lu, reste)`, sous le verrou de la session, AVANT `ouvrir_vente` / `encaisser_vente` (le verrou du lieu n'attend jamais le réseau). L'identifiant de paiement du tirage est envoyé avec le débit et posé sur toutes les parts.
- Débit distant en échec ou solde lu insuffisant : on facture ce qui a été réellement débité ; un seul avertissement dit le montant non facturé (le détail de l'erreur distante est journalisé en INFO).
- Vente : une part et un règlement par transaction ; règlement de l'ancien Fedow avec `reference_externe` = uuid de la transaction distante et `asset` = uuid de la monnaie distante.
- Réponse du `pour_end` : `transaction_id` absent quand aucune transaction `fedow_core` locale n'existe (tirage payé entièrement par l'ancien Fedow). /
The tap pays like the register's cashless: locals first, then the remainder on the old Fedow (user card, linked venue only). Authorize and screen share one balance function including the old Fedow. The remote debit happens under the session lock, before the sale is opened and settled; failure or short balance bills what was really debited with one warning. One part and one payment per transaction (`reference_externe` for the old Fedow). No `transaction_id` without a local transaction.

**Pourquoi / Why :** décision du mainteneur (fiche C §1 bis) : une carte qui n'a que du FED / TLF sur l'ancien Fedow doit pouvoir payer à la tireuse, comme à la caisse. /
A card holding only old-Fedow FED / TLF must be able to pay at the tap, as at the register.

| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/billing.py` | `lire_le_solde_de_l_ancien_fedow`, `calculer_solde_de_la_carte` ; `facturer_tirage` : cran de l'ancien Fedow, parts et règlements distants, `uuid_transaction` créé avant le débit distant |
| `controlvanne/viewsets.py` | `authorize` et `_lire_le_solde_de_la_carte` utilisent `calculer_solde_de_la_carte` ; `transaction_id` absent sans transaction locale |
| `tests/pytest/test_tireuse_ancien_fedow.py` | nouveau : 10 tests |
| `tests/pytest/test_tireuse_ecrit_la_vente.py` | fixture automatique : ancien Fedow simulé (relié, solde 0, débit interdit, aucun envoi réseau) |

**Tests existants changés :** `test_tireuse_ecrit_la_vente.py` seulement (sa carte d'utilisateur lirait sinon le vrai ancien Fedow au badge) ; ce qu'il vérifie est inchangé. Cartes des autres tests controlvanne : anonymes (TSTCV01, TSTMD01, TSTMT01 relues en base : sans utilisateur) → rien à simuler.

**Tests ajoutés** (`tests/pytest/test_tireuse_ancien_fedow.py`, vraies routes, `django_db`, ancien Fedow simulé dans `laboutik.views`, garde réseau automatique) :
`test_tirage_locales_puis_ancien_fedow_une_vente`, `test_tirage_paye_entierement_par_l_ancien_fedow`, `test_carte_anonyme_n_appelle_jamais_l_ancien_fedow` (témoin), `test_lieu_non_relie_n_appelle_jamais_l_ancien_fedow` (témoin), `test_authorize_compte_le_solde_de_l_ancien_fedow`, `test_authorize_ancien_fedow_injoignable_continue_avec_les_locales`, `test_fin_de_service_ancien_fedow_en_echec_facture_les_locales`, `test_fin_de_service_solde_distant_insuffisant_debite_ce_qu_il_a`, `test_ecran_et_authorize_meme_solde`, `test_debit_distant_hors_du_verrou_du_lieu`.

**Vus rouges avant le code :** 8 failed, 2 passed (témoins 3 et 4). Puis, `billing.py` écrit mais `viewsets.py:1093` pas encore corrigé : test 2 en `AttributeError: 'NoneType' object has no attribute 'id'` (500).

**Vert après le code :** fichier 10 passed ; `test_tireuse_*.py` + `test_controlvanne_*.py` + `test_caracterisation_*.py` + `test_vente_*.py` : 262 passed ; `manage.py check` sans erreur.

**Mutations (à jouer par l'orchestrateur)** :
| Mutation | Fichier:ligne | Test attendu en échec |
|---|---|---|
| ancien Fedow appelé avant les locales (bloc « 1 bis » déplacé avant la boucle locale) | `controlvanne/billing.py:428-467` (uuid + bloc) déplacées juste avant la boucle locale l.398 | `test_tirage_locales_puis_ancien_fedow_une_vente` |
| garde `carte.user` retirée | `controlvanne/billing.py:217-219` | `test_carte_anonyme_n_appelle_jamais_l_ancien_fedow` |
| garde « lieu relié » retirée | `controlvanne/billing.py:224-225` | aucun : **équivalente** (la vraie lecture rend `(0, False)` pour un lieu non relié, le solde vaut 0 de toute façon) ; double sécurité |
| `reference_externe` vide | `controlvanne/billing.py:662` | `test_tirage_locales_puis_ancien_fedow_une_vente`, `test_tirage_paye_entierement_par_l_ancien_fedow` |
| moyen distant forcé à `LE` | `controlvanne/billing.py:658` | `test_tirage_locales_puis_ancien_fedow_une_vente` |
| `authorize` sans l'ancien Fedow (`calculer_solde_total_cascade`) | `controlvanne/viewsets.py:773` | `test_authorize_compte_le_solde_de_l_ancien_fedow` (et `test_ecran_et_authorize_meme_solde`) |
| exception distante non attrapée (try/except retiré) | `controlvanne/billing.py:448-463` | `test_fin_de_service_ancien_fedow_en_echec_facture_les_locales` |
| `min(solde lu, reste)` → `reste` | `controlvanne/billing.py:445-447` | `test_fin_de_service_solde_distant_insuffisant_debite_ce_qu_il_a` |
| débit distant après `encaisser_vente` (bloc déplacé juste après l.714, le reste du code inchangé) | `controlvanne/billing.py:439-467` | `test_debit_distant_hors_du_verrou_du_lieu` |

## Le paiement QR / NFC écrit sa vente / QR / NFC payment writes its sale

**Migration :** Non — **Chaînes i18n :** aucune nouvelle (les deux messages d'erreur existaient déjà).

**Quoi / What :** `QrCodeScanPay.valid_payment` (QR code) et `QrCodeScanPay.process_with_nfc` (carte) suivent le même flux :
1. réservation de la demande (`CREATED → UNPAID`), inchangée ; son filtre, et celui de `QrCodeScanPayNfcValidator`, lisent désormais l'origine `sale_origin = QRCODE_MA` au lieu du moyen `payment_method = QRCODE_MA` (trou T2) ;
2. débit sur l'ancien Fedow (`to_place_from_qrcode`), inchangé (erreur → demande `FAILED`) ;
3. tous les autres appels réseau AVANT la base : la catégorie de chaque monnaie débitée (`asset.retrieve`), une fois par monnaie (`_moyens_des_monnaies_debitees`). Erreur réseau ou catégorie autre que FED / TLF → demande `FAILED`, aucune ligne recréée, aucune vente, même message que l'étape 2 ;
4. une seule transaction de base (`_ecrire_la_vente_payee`) : la demande est supprimée ; une vente `VENTE` d'origine `QRCODE_MA` (QR) ou `NFC_MA` (carte), au nom du payeur, avec la carte locale du tag lu si elle existe, sans point de vente ni opérateur ; une part par transaction de l'ancien Fedow (forme des lignes inchangée, `total_catalogue_impose` = montant de la transaction, TVA par `_taux_tva_de_la_ligne_de_caisse`, la première part garde l'uuid de la demande) ; un règlement par transaction (moyen, montant, monnaie, carte, `reference_externe` = uuid de la transaction distante ; pas de portefeuille, comme la caisse) ; `encaisser_vente` en dernier ;
5. échec pendant l'écriture : rien n'est écrit, la demande passe `FAILED` (le débit est fait, il ne se rejoue jamais), journal et réponse d'erreur inchangés ;
6. après la validation en base : les deux mails (lieu, payeur) en `on_commit`. **Plus aucun `send_sale_to_laboutik`** pour le QR / NFC.
Débit partiel : comportement gardé (la vente vaut ce qui a été débité). Réponses des deux vues inchangées ; le solde affiché après un paiement QR est calculé (solde lu avant le débit − montant débité) au lieu d'être relu sur l'ancien Fedow après l'écriture. /
Both views: reserve (now by `sale_origin`), debit, every other network call before the database (category once per currency; failure → request FAILED, no sale), one database transaction writing a settled sale with one part and one payment per remote transaction (the first part keeps the request uuid), mails on commit, no more legacy LaBoutik sending. A failure while writing leaves nothing and fails the request.

**Pourquoi / Why :** chantier 05 (montants entiers) : la vente naît au paiement, entre dans la chaîne des ventes du lieu, et l'argent est écrit une fois. L'envoi à l'ancien LaBoutik est débranché pour le QR / NFC (décision du mainteneur, 2026-09-29). T2 : l'anti-rejeu ne dépend plus d'un champ qui disparaît en H. /
The sale is born at payment and joins the venue's chain; legacy LaBoutik sending is unplugged for QR / NFC; the replay guard no longer depends on a field removed in H.

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `QrCodeScanPay` : `_moyens_des_monnaies_debitees`, `_ecrire_la_vente_payee` ; `valid_payment` et `process_with_nfc` réécrits après le débit ; réservation par `sale_origin` |
| `BaseBillet/validators.py` | `QrCodeScanPayNfcValidator.validate_ligne_article_uuid_hex` : filtre par `sale_origin` |
| `tests/pytest/test_qrcode_ecrit_la_vente.py` | nouveau : 16 tests, schéma dédié `test_qrcode_vente` |
| `tests/pytest/test_qrcodescanpay_flux_complet.py` | adapté (voir ci-dessous) |
| `tests/pytest/test_caracterisation_qr.py` | test A′ renommé (voir ci-dessous) |
| `tests/pytest/test_parcours_vente_fed_et_remise_en_banque.py` | le faux `to_place_from_qrcode` rend une transaction avec `uuid` (voir ci-dessous) |

**Tests existants changés, avec leur raison :**
- `test_caracterisation_qr.py::test_qr_deux_monnaies_deux_envois_laboutik_et_deux_mails` → renommé `test_qr_deux_monnaies_aucun_envoi_laboutik_et_deux_mails` (liste fermée A′ §4) : plus aucun envoi `send_sale_to_laboutik`, les deux mails restent (mêmes arguments) ; les deux lignes recréées VALID sont relues par la vente de la demande ; ses transactions simulées reçoivent un `uuid` (le vrai client en rend toujours un). Les assistants de charge utile LaBoutik, devenus inutiles, sont retirés. Les autres tests de caractérisation ne changent pas.
- `test_qrcodescanpay_flux_complet.py` :
  - toutes les transactions simulées reçoivent un `uuid` (17) : le règlement copie l'uuid de la transaction distante dans `reference_externe`, et le vrai client (`TransactionValidator`) en rend toujours un ;
  - `setUp` enregistre `LaboutikConfiguration.get_solo()` : un paiement réussi encaisse une vente, qui lit la clé de l'empreinte (tests/PIEGES.md 9.86) ;
  - `test_une_ligne_qui_n_est_pas_un_qrcode_ne_peut_pas_etre_payee` : la ligne « qui n'est pas un QR » a désormais une autre **origine** (`sale_origin = LESPASS`) au lieu d'un autre moyen de paiement — c'est le sens de T2 ; assertions inchangées ;
  - `test_une_monnaie_non_fiduciaire_ne_produit_aucune_vente` **change de sens** : la catégorie est lue avant la base, la demande passe `FAILED` ; assertion ajoutée (seule la demande reste, en `FAILED`), assertion d'origine gardée.
  Aucune assertion affaiblie.
- `test_parcours_vente_fed_et_remise_en_banque.py` : une seule ligne, le faux `FedowSimule.to_place_from_qrcode` rend désormais une transaction avec un `uuid`, comme le vrai client (`TransactionValidator`) : le règlement copie cet uuid dans `reference_externe`. Sans lui, l'écriture de la vente échouait et le parcours tombait. Rien d'autre ne change dans ce fichier.
- `BaseBillet/views.py` : l'import de `send_sale_to_laboutik` est retiré (plus aucun usage dans ce fichier, vérifié par `rg`) : le QR / NFC n'envoie plus rien à l'ancien LaBoutik. La tâche elle-même reste (utilisée ailleurs).

**Tests ajoutés** (`tests/pytest/test_qrcode_ecrit_la_vente.py`) :
`test_qr_paye_tlf_et_fed_deux_reglements_exacts`, `test_qr_non_paye_aucune_vente` (deux QR, un seul payé), `test_nfc_ma_une_vente_origine_nfc`, `test_nfc_vente_porte_la_carte_et_le_client`, `test_qr_echec_reseau_apres_debit_aucune_vente_ligne_failed`, `test_nfc_echec_reseau_apres_debit_aucune_vente_ligne_failed`, `test_qr_aucun_envoi_ancien_laboutik`, `test_nfc_aucun_envoi_ancien_laboutik`, `test_qr_refus_fedow_aucune_vente` (témoin), `test_qr_echec_ecriture_apres_debit_aucune_vente_ligne_failed`, `test_nfc_echec_ecriture_apres_debit_aucune_vente_ligne_failed`, `test_qr_tva_taux_du_lieu`, `test_qr_debit_partiel_vente_du_montant_debite`, `test_anti_rejeu_qr_ne_lit_plus_payment_method`, `test_anti_rejeu_nfc_ne_lit_plus_payment_method`, `test_qr_paye_check_payment_annonce_le_paiement` (témoin).

**Vus rouges avant le code :** 11 failed, 2 passed (témoins `check_payment` et refus de l'ancien Fedow) ; test A′ renommé : 1 failed ; `test_qr_tva_taux_du_lieu` : rouge (aucune vente ; le taux seul valait déjà 20 % par `_compute_default_vat`). Les deux tests « échec pendant l'écriture » sont écrits après le code : à prouver par mutation (table ci-dessous).

**Vert après le code :** fichier 16 passed ; `test_qrcode_ecrit_la_vente.py` + `test_qrcodescanpay_*.py` + `test_caracterisation_*.py` + `test_vente_*.py` + `test_parcours_vente_fed_et_remise_en_banque.py` : 230 passed ; `manage.py check` sans erreur.

**Mutations (à jouer par l'orchestrateur)** — `BaseBillet/views.py` sauf mention :
| Mutation | Fichier:ligne | Test attendu en échec |
|---|---|---|
| vente créée à la génération du QR (`ouvrir_vente(origine=QRCODE_MA, nature="VENTE")` ajouté après la création de la demande) | `BaseBillet/views.py:2072` (après le `LigneArticle.objects.create` de `generate_qrcode`) | `test_qr_non_paye_aucune_vente` |
| `asset.retrieve` remis dans l'écriture (bloc `try` « étape 3 » l.2473-2487 retiré ; son appel l.2476 placé dans le `try` d'écriture, juste avant l.2524) | `BaseBillet/views.py:2473-2487` | `test_qr_echec_reseau_apres_debit_aucune_vente_ligne_failed` (message) |
| idem par carte (bloc l.2183-2199 retiré ; son appel l.2186 placé juste avant l.2238) | `BaseBillet/views.py:2183-2199` | `test_nfc_echec_reseau_apres_debit_aucune_vente_ligne_failed` (message) |
| `send_sale_to_laboutik.delay(ex_ligne_article_uuid)` remis après l'écriture (QR) | après `BaseBillet/views.py:2535` | `test_qr_aucun_envoi_ancien_laboutik`, `test_qr_deux_monnaies_aucun_envoi_laboutik_et_deux_mails` |
| idem par carte | après `BaseBillet/views.py:2249` | `test_nfc_aucun_envoi_ancien_laboutik` |
| mails hors `on_commit` (`envoyer_les_mails_de_confirmation()` appelé directement) | `BaseBillet/views.py:2575` (QR), `:2281` (carte) | `test_qr_aucun_envoi_ancien_laboutik` / `test_nfc_aucun_envoi_ancien_laboutik` |
| `reference_externe` vide | `BaseBillet/views.py:1972` | `test_qr_paye_tlf_et_fed_deux_reglements_exacts`, `test_nfc_ma_une_vente_origine_nfc` |
| uuid de la demande non gardé (`uuid_de_la_part = uuid.uuid4()`) | `BaseBillet/views.py:1941` | `test_qr_paye_check_payment_annonce_le_paiement` (et 7, 8, 9, A′) |
| anti-rejeu remis sur `payment_method` (réservation QR) | `BaseBillet/views.py:2437` | `test_anti_rejeu_qr_ne_lit_plus_payment_method`, `test_une_ligne_qui_n_est_pas_un_qrcode_ne_peut_pas_etre_payee` |
| idem, réservation carte | `BaseBillet/views.py:2128` | `test_anti_rejeu_nfc_ne_lit_plus_payment_method` (409) |
| idem, validateur | `BaseBillet/validators.py:1385` | `test_anti_rejeu_nfc_ne_lit_plus_payment_method` (400) |
| `encaisser_vente` retiré (`vente_encaissee = vente`) | `BaseBillet/views.py:1975` | `test_qr_paye_tlf_et_fed_deux_reglements_exacts` (et tout test qui appelle `verifier_egalites`) |
| demande non passée `FAILED` après un échec d'écriture (`.update(status=FAILED)` retiré) | `BaseBillet/views.py:2547` (QR), `:2261` (carte) | `test_qr_echec_ecriture_apres_debit_aucune_vente_ligne_failed` / `test_nfc_echec_ecriture_apres_debit_aucune_vente_ligne_failed` |
| écriture hors transaction unique (`with db_transaction.atomic():` retiré, bloc dé-indenté) | `BaseBillet/views.py:1925` | `test_qr_echec_ecriture_apres_debit_aucune_vente_ligne_failed` (parts et règlements restent) |
| carte du tag non passée (`carte=None`) | `BaseBillet/views.py:2247` | `test_nfc_vente_porte_la_carte_et_le_client` |
| client = encaisseur (`client=request.user`) | `BaseBillet/views.py:2246` | `test_nfc_vente_porte_la_carte_et_le_client` |
| TVA à 0 (`taux_tva=Decimal("0")`) | `BaseBillet/views.py:1956` | `test_qr_tva_taux_du_lieu` |

## Tireuse : l'ancien Fedow débité avant les monnaies locales (C-3) / Tap: the old Fedow debited before local currencies (C-3)

**Migration :** Non — **Chaînes i18n :** aucune nouvelle.

**Quoi / What :** corrections de la relecture de la fiche C.
- `facturer_tirage` suit l'ordre de la caisse : 1. lire les soldes locaux de la cascade et le solde de l'ancien Fedow, sans rien débiter ; 2. répartir (locales dans l'ordre de la cascade, le reste sur l'ancien Fedow plafonné à son solde lu) ; 3. débiter l'ancien Fedow d'abord, AVANT le bloc atomique local (donc avant tout verrou de jeton ; toujours sous le verrou de la session) ; 4. dans le bloc atomique : débits locaux, vente, `encaisser_vente` en dernier. Parts, règlements, montants et vente inchangés. Remplace l'ordre « débits locaux, puis ancien Fedow » décrit plus haut.
- L'échec de `_debiter_legacy` est journalisé en ERROR (cause, carte, montant demandé ; il peut suivre un débit côté serveur). L'avertissement « montant non facturé » reste le seul WARNING.
- Commentaires exacts : le débit de l'ancien Fedow ne s'annule pas avec la base. Si le bloc local échoue ensuite (`EgaliteDeVenteRompue` → 500 + Sentry ; `SoldeInsuffisant` → erreur journalisée par l'appelant), l'argent pris là-bas reste pris, sans vente. Pas de journal d'incident (décision du mainteneur).
- `viewsets.py` : commentaire sur la relecture du solde après le `pour_end` (lecture réseau pour l'affichage seulement, hors transaction, après la facture).
- `viewsets.py` : commentaire du `except SoldeInsuffisant` exact (l'atomic interne annule le local ; un débit déjà fait sur l'ancien Fedow reste pris, sans vente).
- Tests QR plus exacts : code 400 exact pour la seconde lecture de carte ; la part de la PREMIÈRE transaction garde l'uuid de la demande. /
`facturer_tirage` now follows the register: read local and remote balances, split, debit the old Fedow FIRST (before the local atomic block and any token lock, still under the session lock), then local debits, the sale, and settlement last. Same parts, payments and amounts. Remote debit failure logged as ERROR. Comments now state that the remote debit is not rolled back. Exact QR test assertions.

**Pourquoi / Why :** pendant l'appel réseau à l'ancien Fedow, les jetons du client et du lieu étaient verrouillés (`creer_vente` → `select_for_update`) : toutes les ventes cashless du lieu attendaient le réseau. Un échec distant peut suivre un débit fait côté serveur : il mérite une ERREUR, pas une INFO. /
During the remote call, the client's and the venue's tokens were locked: every cashless sale of the venue waited for the network. A remote failure may follow a server-side debit: it deserves an ERROR.

| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/billing.py` | `facturer_tirage` : lecture + répartition hors bloc atomique, débit de l'ancien Fedow avant le bloc, débits locaux dans le bloc ; échec distant en ERROR ; docstring et commentaire de l'étape 8 exacts |
| `controlvanne/viewsets.py` | commentaires seulement (lecture du solde après la facture ; `except SoldeInsuffisant`) |
| `tests/pytest/test_tireuse_ancien_fedow.py` | 2 tests ajoutés ; docstring du module (règle 4) et de `test_fin_de_service_solde_distant_insuffisant_debite_ce_qu_il_a` exactes (aucune assertion changée) |
| `tests/pytest/test_qrcode_ecrit_la_vente.py` | `status_code == 400` ; part de la première transaction = uuid de la demande |

**Tests ajoutés :** `test_ancien_fedow_debite_avant_les_monnaies_locales` (ordre `_debiter_legacy` puis `TransactionService.creer_vente` par espion `wraps` ; 400 = 100 jetons + 100 TLF local + 200 ancien Fedow), `test_echec_de_l_ancien_fedow_journalise_en_erreur_avec_la_cause`.

**Vus rouges avant le code :** 2 failed, 10 passed (journal `['débit local', 'débit local', 'débit ancien Fedow']` ; aucune ERROR, l'échec était en INFO).

**Vert après le code :** `test_tireuse_*.py` + `test_controlvanne_*.py` + `test_qrcode_ecrit_la_vente.py` + `test_caracterisation_*.py` : 145 passed ; `manage.py check` sans erreur.

**Mutations (à jouer par l'orchestrateur)** :
| Mutation | Fichier:ligne | Test attendu en échec |
|---|---|---|
| débit distant remis après les débits locaux (bloc `if restant_centimes > 0:` de l.451-481 déplacé dans le bloc atomique, juste après la boucle locale l.523-538) | `controlvanne/billing.py:451-481` | `test_ancien_fedow_debite_avant_les_monnaies_locales` |
| ERROR remis en INFO (`logger.error` → `logger.info`) | `controlvanne/billing.py:471` | `test_echec_de_l_ancien_fedow_journalise_en_erreur_avec_la_cause` |

---

## Comment tester (a la main) / Manual test
1. Compter (lecture seule) les `LigneArticle` d'origine `TIREUSE`, les `fedow_core.Transaction` au commentaire « Tirage… » et les `RfidSession`.
2. `make test ARGS="tests/pytest/test_controlvanne_billing.py tests/pytest/test_controlvanne_facturation_lot2.py tests/pytest/test_controlvanne_api.py tests/pytest/test_controlvanne_models.py tests/pytest/test_controlvanne_ecran_calibration.py"` deux fois de suite : tout est vert.
3. Recompter : les trois nombres n'ont pas bougé.

### La tireuse écrit sa vente
1. Poser une carte avec du solde en monnaie locale sur une tireuse (ou le simulateur), servir 50 cl.
2. Admin → Ventes : une vente « Tireuse connectée », réglée, numérotée, au point de vente de la tireuse ; un article (la bière) et un règlement « monnaie locale » du même montant.
3. Carte avec des jetons cadeau et de la monnaie locale : deux articles (part en jetons offerte) et deux règlements (jetons, monnaie locale).
4. 173 ml à 5 €/L : l'écran affiche 0,87 €, la vente vaut 87 c.

### La tireuse paie aussi avec l'ancien Fedow
1. Carte reliée à un utilisateur, avec un peu de monnaie locale (ex. 1 €) et du FED / TLF sur l'ancien Fedow (lieu relié).
2. Badge sur la tireuse : l'écran affiche le solde total (local + ancien Fedow) et autorise le volume correspondant.
3. Servir 50 cl à 8 €/L : Admin → Ventes : une vente « Tireuse connectée » de 4 € ; un règlement local (1 €) et un règlement par transaction de l'ancien Fedow (moyen « monnaie locale » pour les TLF fédérés, « Stripe fédéré » pour le FED), avec la référence externe = uuid de la transaction distante.
4. Carte anonyme : seules les monnaies locales comptent au badge et à la facture.

### Le paiement QR / NFC écrit sa vente
1. Un encaisseur (droit « initier un paiement ») génère un QR code de 12,50 €. Admin → Ventes : aucune vente nouvelle.
2. Un adhérent avec du FED / TLF sur l'ancien Fedow scanne et confirme. Admin → Ventes : une vente « QrCode online », réglée, numérotée, au nom de l'adhérent ; un article par monnaie débitée et un règlement par transaction distante (référence externe = uuid de la transaction). L'écran de l'encaisseur passe à « paiement reçu ».
3. Même chose en lisant la carte de l'adhérent au lecteur NFC : vente « NFC online », avec la carte si le lieu la connaît.
4. Re-confirmer le même QR code : « déjà traité », aucun second débit.
5. Aucune tâche « envoi à LaBoutik » dans les logs Celery ; les deux mails (lieu, adhérent) partent.

### L'ancien Fedow débité avant les monnaies locales
1. Carte reliée à un utilisateur, 1 € en monnaie locale, du FED sur l'ancien Fedow (lieu relié). Servir 50 cl à 8 €/L.
2. Admin → Ventes : même vente qu'avant (règlement local 1 €, règlements distants pour le reste).
3. Logs du serveur : le débit de l'ancien Fedow apparaît avant les lignes « Transaction #… Vente … centimes » des débits locaux.
4. Ancien Fedow coupé pendant le service (après le badge) : la vente ne porte que la part locale ; les logs ont une ligne ERROR « Débit de l'ancien Fedow en échec » (cause, carte, montant) et un seul WARNING « manque … cts (non facturé) ».
