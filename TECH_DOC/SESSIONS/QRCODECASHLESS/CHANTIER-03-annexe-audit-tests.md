# Audit : les tests Lespass qui « adoubent » un bug

Audit en lecture seule. Je n'ai lancé aucun test, modifié aucun fichier, ni fait aucune écriture git (seulement `log -S` et `blame`).

Périmètre :
- `tests/pytest/` : 289 fichiers ;
- `tests/e2e/` : 64 fichiers.

Je n'ai pas tout lu de la même façon :
- **Lu en profondeur par moi** : cartes, FED, rapatriement, caisse, tireuse, vidage, QR.
- **Délégué à trois agents** : Stripe et adhésions ; compta et clôtures ; borne et E2E.

Pour chaque verdict « BUG ADOUBÉ » d'un agent, j'ai relu moi-même le code de prod :
- la borne : `kiosk/carte.py` ;
- le SEPA d'adhésion : `BaseBillet/models.py:4267` ;
- le débit legacy : `laboutik/views.py:1804-1830`.

## 1. Résumé

### Nombre de tests ou fixtures suspects

| Famille | Total | BUG ADOUBÉ | DOUTEUX À TRANCHER | LIMITE LÉGITIME |
|---|---|---|---|---|
| A. Assertion d'absence ou de refus | 14 | 8 | 3 | 3 |
| B. Fixture qui court-circuite le parcours réel | 15 groupes | 6 | 7 | 2 |
| C. Simulateur partiel | 10 | 3 cachent un chemin de prod | 7 | 0 |
| D. Contradiction entre specs figée par un test | 9 | — | — | — |

### La cause commune : une hypothèse fausse

Les tests de la famille A s'appuient sur une hypothèse : « l'ancien Fedow ne débite que le portefeuille d'un utilisateur, par sa signature RSA ». Le code réel de Fedow la contredit sur quatre points.

1. **Une vente n'exige que la carte client et la carte primaire du lieu.** Aucune signature d'utilisateur n'est demandée. Voir `Fedow/fedow_core/serializers.py:1286-1293`, dans `get_action`, la branche `place.wallet == receiver` qui renvoie `SALE`.
2. **La route accepte la simple clé API d'une place Lespass.** `TransactionAPI.create` passe par `HasKeyAndPlaceSignature` (`Fedow/fedow_core/views.py:1769`), complété par l'extension S6 pour les places Lespass (`Fedow/fedow_core/permissions.py:259-268`). LaBoutik V1 débitait ainsi n'importe quelle carte (`LaBoutik/fedow_connect/fedow_api.py:538-560`, `to_place`).
3. **La lecture d'une carte ne demande que la clé de la place.** `GET card/{tag}/` (`Fedow/fedow_core/views.py:378`, permission en `:422`) renvoie les jetons du portefeuille de la carte, FED compris, qu'elle soit anonyme ou liée. Lespass s'en sert déjà pour le vidage (`laboutik/views.py:2179-2236`, `_lire_la_carte_sur_l_ancien_fedow`).
4. **Les cartes anonymes portent réellement du FED.** Le TPE Stripe de l'ancienne borne crédite le FED (`STRIPE_FED_FIAT`) sur `card.get_wallet()`, c'est-à-dire le portefeuille éphémère d'une carte anonyme (`Fedow/fedow_core/views.py:1154-1191`, `models.py:1158-1162`). Un test Lespass le reconnaît lui-même (`tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py:15-16`).

### Les 5 constats les plus graves

1. **Le FED d'une carte sans `user` est invisible et impossible à débiter, et c'est verrouillé à plusieurs endroits** (A1 à A5 ; B1).
   - Tests : `test_c1_solde_complet_carte.py:170`, `test_tireuse_ancien_fedow.py:716`, `test_rapatriement_carte_fedow.py:556`, et la fabrique `test_caisse_ecrit_la_vente.py:1936-1948` (« Seule une carte liée à un utilisateur peut payer avec la monnaie du réseau »), utilisée par les 13 tests FED de la caisse.
   - Le comportement verrouillé : `laboutik/views.py:1536`, `:10578`, `:12016`, `:12530`, `:12605` ; `controlvanne/billing.py:260-262`.
2. **Liaison QR faite avant le premier scan NFC : c'est la cause directe du bug, et aucun test ne l'exerce** (B2, D4).
   - `/qr/link` avale `CarteIntrouvable` en le traitant de « ATTENDU … Rien a reparer ici » (`BaseBillet/views.py:784-795`).
   - Au premier scan, le rapatriement crée ensuite la carte sans `user` (`QrcodeCashless/services.py:156-161`), même quand Fedow la dit liée.
   - Tous les tests de liaison créent la carte locale **avant** la liaison : `test_vues_carte_branchees_sur_service.py` (fixture `carte_vierge_et_user_sans_carte`) et `tests/e2e/test_carte_perdue_recharge_fed.py:101-104`.
3. **Le faux Fedow de la caisse cache un débit FED sans vente** (C4).
   - Le faux fournit toujours `serialized_asset`. La vraie réponse de `transaction/qrcodescanpay` n'en a pas : elle est construite par `TransactionSerializer` (`Fedow/fedow_core/views.py:1742` ; `serializers.py:478-507`, sans ce champ).
   - En prod, chaque débit passe donc par `asset.retrieve` **après** le débit (`laboutik/views.py:1695-1699`, `:1814-1823`). Une erreur à cet endroit remonte dans le `except` de l'appelant, qui répond « rescannez » (409) sans journal d'incident (`laboutik/views.py:10680-10693`).
   - Résultat : FED débité, aucune vente écrite, et un rescan peut débiter une seconde fois. La docstring de `_debiter_legacy` (« AUCUN débit partiel », `:1793`) est fausse dans ce cas.
4. **Une adhésion directe payée par SEPA ne bloque pas une 2ᵉ adhésion** (A8, B8).
   - Le test qui le verrouille : `test_max_per_user_adhesion_en_cours.py:124`, `WAITING_PAYMENT` ne compte jamais.
   - Pendant le prélèvement, une adhésion directe reste `WAITING_PAYMENT` : seule `ADMIN_VALID` passe en `PAYMENT_PENDING` (`BaseBillet/models.py:4267-4270`).
   - Elle ne compte donc pas dans `max_per_user` (`models.py:1391-1396`, `STATUTS_EN_COURS` en `:4983`), et ne compte dans le stock que 30 minutes (`models.py:2057`). Un 2ᵉ prélèvement est possible, ce que la docstring du même fichier prétend empêcher.
5. **Le FED repris au vidage n'apparaît dans aucun test de compta** (B9, D7).
   - Les vidages fabriqués pour la compta (`test_rapport_unique.py`, `test_fec_equilibre.py`, `test_comptabilite_*`) n'ont jamais de règlement SF.
   - Pourtant `card/refund` reprend **toujours** le FED (`Fedow/fedow_core/serializers.py:236-241`), et la caisse écrit un règlement SF pour lui (`laboutik/views.py:2064-2118`).
   - Le cas courant (vidage avec FED, puis Z, puis FEC au 467000) n'est jamais lu par une clôture.

## 2. Tableaux par famille

### A. Tests qui affirment une absence ou un refus

| # | fichier:ligne | test | règle verrouillée | source de la règle | verdict | impact en prod | preuve (code réel lu) |
|---|---|---|---|---|---|---|---|
| A1 | `tests/pytest/test_c1_solde_complet_carte.py:170` | `test_carte_anonyme_pas_de_lecture_fed` | carte sans user → `lecture_fed.assert_not_called()`, FED = 0, « pas de user → pas de signature RSA » | spec 11 §6 garde 1 ; commit 41a70dbd (2026-06-21) ; garde en 63f1b252 | **BUG ADOUBÉ** | FED d'une carte anonyme ou rapatriée invisible au « check carte » et à la cascade | Lecture possible sans signature : `Fedow/fedow_core/views.py:378`, `:422`. Lespass le fait déjà pour le vidage : `laboutik/views.py:2205-2224`. Garde : `laboutik/views.py:1536` |
| A2 | `tests/pytest/test_tireuse_ancien_fedow.py:716` (et en-tête `:13-14`) | `test_carte_anonyme_n_appelle_jamais_l_ancien_fedow` | « L'ancien Fedow ne débite que le portefeuille d'un utilisateur » : aucune lecture ni aucun débit distants | docstring de `controlvanne/billing.py:242-244` ; commit d475f3ac (2026-09-30) | **BUG ADOUBÉ** | Volume servi plafonné aux monnaies locales, FED d'une carte anonyme jamais facturé | `Fedow/fedow_core/serializers.py:1286-1293` (vente = carte client + carte primaire) ; `LaBoutik/fedow_connect/fedow_api.py:538-560` ; `controlvanne/billing.py:260-262`, `:548` |
| A3 | `tests/pytest/test_rapatriement_carte_fedow.py:556` | `test_20_carte_rapatriee_sans_utilisateur_ni_portefeuille_ephemere` | `user_id is None` après rapatriement, même pour une carte liée | CHANTIER-02 §4.1 étape 6 et §8.2 n°20 ; commit 5987072c (2026-10-12) | **BUG ADOUBÉ** | Une carte liée chez Fedow arrive « anonyme » en caisse V2, son FED est masqué | La fiche Fedow dit si la carte est liée (`is_wallet_ephemere`) et donne l'uuid du portefeuille (`Fedow/fedow_core/serializers.py:459-475`). Le portefeuille local d'un user porte cet uuid (spec 11 §6bis). Rien ne pose jamais `user` : `QrcodeCashless/services.py:156-161`, `laboutik/views.py:1390-1392` |
| A4 | `tests/pytest/test_rapatriement_carte_points_de_scan.py:948` (31a), `:1327` (37a) | `test_31_a_…_identifiee_anonyme`, `test_37_a_check_carte_…` | carte rapatriée = « anonyme » : formulaire e-mail, `retour-carte-anonyme` | CHANTIER-02 §8.4 | **BUG ADOUBÉ** (le seul cas simulé est l'anonyme, voir C2) | Une carte liée chez Fedow affiche « Carte anonyme », et la caisse redemande l'e-mail | `laboutik/views.py:13352-13354` (couleur et e-mail tirés de `carte.user`) |
| A5 | `tests/pytest/test_caisse_ecrit_la_vente.py:1936-1948` (fabrique `creer_une_carte_nfc_d_un_membre_sans_solde_local`) | 13 tests FED (`:1978`, `:2055`, `:2136`, `:2726`, `:2834`, `:2943`, `:3306`, `:3543`, `:3653`…) | « Seule une carte liée à un utilisateur peut payer avec la monnaie du réseau » | docstring b234cef8 ; garde d8396a64 | **BUG ADOUBÉ** | Même impact que A1, sur tout le paiement | `laboutik/views.py:10578`, `:12016`, `:12530`, `:12605` |
| A6 | `tests/pytest/test_laboutik_adhesions_apres_paiement.py:99` | `test_une_carte_anonyme_n_a_aucune_adhesion_active` | `user=None` = aucune adhésion | `laboutik/views.py:3047-3052` | DOUTEUX À TRANCHER | La carte rapatriée d'un membre (sans user en local) n'affiche pas ses adhésions | `QrcodeCashless/services.py:156-161` |
| A7 | `tests/pytest/test_cascade_sans_monnaie_archivee.py:131` | `test_cascade_ignore_une_monnaie_archivee` | la cascade prend **la première** monnaie TLF par nom, une seule par catégorie | design Session 06 (`DESIGN_CASCADE_MULTI_ASSET_NFC.md`) ; piège 9.97 | DOUTEUX À TRANCHER | Un lieu V2 qui a sa monnaie TLF plus une TLF fédérée (fédération `fedow_core`) : les jetons de la 2ᵉ ne sont ni lus ni débités en caisse ni à la tireuse | `laboutik/views.py:10359-10368` (`.first()` par catégorie) ; `fedow_core/services.py:113-117` (monnaies propres et fédérées). La fixture `test_caracterisation_caisse.py:393-396` le dit : « une autre monnaie ne serait pas vue » |
| A8 | `tests/pytest/test_max_per_user_adhesion_en_cours.py:124` | `test_panier_stripe_abandonne_ne_bloque_pas_a_vie` | `WAITING_PAYMENT` ne compte jamais dans `max_per_user` | commit beb7063c (2026-07-25) | **BUG ADOUBÉ** (vérifié sur le code) | 2ᵉ adhésion et 2ᵉ prélèvement SEPA possibles pendant les 3 à 14 jours du 1ᵉʳ | `BaseBillet/models.py:4267-4270`, `:1391-1396`, `:4983`, `:2057` |
| A9 | `tests/pytest/test_caracterisation_en_ligne.py:593` | `test_paiement_reste_paye_puis_rejeu_repasse_les_avoirs_en_paye` | un rejeu Stripe `PAID → PAID` repasse les avoirs en `PAID` et renvoie les billets | `TECH_DOC/SESSIONS/TODO/BUGS-constats-chantier-05.md` n°3, décision D33 | BUG ADOUBÉ volontairement (caractérisation documentée) | Un rejeu annule un avoir | signal `set_ligne_article_paid` (agent ; je ne l'ai pas relu) |
| A10 | `tests/pytest/test_rapports_cheque.py:315` | `test_les_totaux_de_la_cloture_se_recomposent_en_total_general` | espèces + carte + cashless + chèque = total général, sans colonne pour le fédéré | docstring du fichier | **BUG ADOUBÉ** (code legacy, faible) | `export-fec` et le CSV legacy lisent encore cette clôture | `laboutik/reports.py:200-207` ; `laboutik/views.py:4113`, `:4218` (agent) |
| A11 | `tests/pytest/test_qrcodescanpay_flux_complet.py:901` | `test_une_carte_non_rattachee_a_un_compte_est_refusee` | paiement QR par carte : une carte éphémère est refusée | `BaseBillet/validators.py:1527-1529` | LIMITE LÉGITIME | Ce parcours n'a pas de carte primaire, que la vente Fedow exige | `Fedow/fedow_core/serializers.py:1286-1291` |
| A12 | `tests/e2e/test_recharge_pos_puis_qrcode.py:307` | `test_une_recharge_au_comptoir_n_est_pas_depensable_par_qrcode` | l'argent rechargé au comptoir (V2) n'est pas dépensable par QR | en-tête « CE TEST DOIT DEVENIR ROUGE… » | LIMITE LÉGITIME DOCUMENTÉE | Frontière connue entre les deux moteurs | (agent) |
| A13 | `tests/pytest/test_kiosk_ecrans.py:143` | `test_lecture_carte_anonyme_ouvre_la_modale_non_enregistree` | la modale promet que l'enregistrement par QR protège la carte | gabarit `etape_solde_et_montant.html:126-147` | DOUTEUX À TRANCHER | Enregistrer par QR avant tout scan NFC ne lie rien en local (voir le constat 2), et le FED reste invisible en caisse | `BaseBillet/views.py:784-795` |
| A14 | `tests/e2e/test_caisse_carte_rapatriee_depuis_fedow.py:218-221` | `test_une_carte_connue_seulement_de_l_ancien_fedow_est_rapatriee_…` | carte rapatriée = « Carte anonyme », 0,00 € | CHANTIER-02 §8.5 | LIMITE LÉGITIME pour une carte vraiment anonyme, mais angle mort : jamais de FED, jamais de carte liée | — | fixture `:122-133` (agent) |

### B. Fixtures qui court-circuitent le parcours réel

| # | fichier:ligne | test(s) | état fabriqué | parcours réel jamais traversé | verdict | preuve |
|---|---|---|---|---|---|---|
| B1 | `tests/pytest/test_c1_solde_complet_carte.py:45-66` ; `test_paiement_complementaire.py:169-179` ; `test_caisse_ecrit_la_vente.py:1936-1948` ; `test_tireuse_ancien_fedow.py:318-358` ; `test_wallet_carte_fedow.py:102` | tous les tests FED de la caisse et de la tireuse | `CarteCashless.objects.create(user=…)` (ou `update(user=…)`), et **portefeuille du user créé par `Wallet.objects.create`, donc à uuid aléatoire** | QR, puis rapatriement, puis liaison, puis caisse. Le portefeuille d'un user doit porter l'uuid Fedow (`get_or_create_wallet`, invariant de la spec 11 §6bis) | **BUG ADOUBÉ** | `QrcodeCashless/services.py:156-161` ; `fedow_connect/fedow_api.py:552` |
| B2 | `tests/pytest/test_vues_carte_branchees_sur_service.py` (fixture `carte_vierge_et_user_sans_carte`, test `test_le_parcours_qr_lie_la_carte_cote_lespass`) | liaison `/qr/link` | la carte existe déjà en local **avant** la liaison | `/qr/link` sur une carte qui n'existe que chez Fedow : la branche `CarteIntrouvable` n'a aucun test | **BUG ADOUBÉ** (par omission) | `BaseBillet/views.py:784-795` ; `fedow_core/services.py:1433-1436` |
| B3 | `tests/e2e/test_carte_perdue_recharge_fed.py:78-115` | `test_carte_perdue_la_recharge_fed_suit_l_adherent_…` | carte créée en base (`:101`) **avant** `linkwallet_cardqrcode` (`:104`), « comme le parcours QR » | le vrai `/qr` ne crée pas la carte locale. Le test ne fait aucun paiement en caisse | **BUG ADOUBÉ** | idem B2 (agent, confirmé par moi) |
| B4 | `tests/e2e/test_parcours_fedow_reel.py:700-735` (`carte.user = user`, `:723`), `:1154-1198` | `test_caisse_encaisse_du_fed_de_l_ancien_fedow`, `test_caisse_vide_une_carte_avec_du_fed_…` | carte `E2EFED01`, inconnue de Fedow, avec son user posé par l'ORM | le seul E2E qui débite du **vrai** FED en caisse le fait par la signature du user, jamais pour une carte réelle rapatriée | **BUG ADOUBÉ** (masqué) | `laboutik/views.py:1777-1810` (agent) |
| B5 | `tests/pytest/test_rapatriement_carte_points_de_scan.py:255-283` | `carte_connue_seulement_de_fedow` (tests 32 à 39) | solde de **monnaie locale V2** posé sur le portefeuille miroir d'une carte jamais vue en local | en prod, une carte connue seulement de Fedow porte ses soldes **chez Fedow** (TLF legacy, FED). Le cas « FED distant » n'est jamais simulé | DOUTEUX À TRANCHER | fiche `wallet.tokens: []` (`test_rapatriement_carte_fedow.py:162`) |
| B6 | `tests/pytest/test_rapatriement_carte_points_de_scan.py:472-477` | faux `declarer_wallet_user_a_fedow` (tests 30 bis) | portefeuille de l'adhérente à uuid aléatoire | la vraie déclaration pose l'uuid Fedow | DOUTEUX À TRANCHER | même invariant que B1 |
| B7 | `tests/pytest/test_scan_qr_carte_v2.py:158-188` | `test_scan_carte_vierge_cree_wallet_ephemere`, etc. | teste `CarteService.scanner_carte`, qui crée un portefeuille éphémère local à uuid aléatoire | **aucun appelant en prod** : code mort testé (seuls les tests l'appellent) | DOUTEUX À TRANCHER (voir D5) | `fedow_core/services.py:1309-1388` ; aucune autre occurrence de `scanner_carte(` |
| B8 | `tests/pytest/test_max_per_user_adhesion_en_cours.py:82-97` | `test_adhesion_en_cours_sans_deadline_atteint_la_limite` | `Membership(status=PAYMENT_PENDING)` posé à la main | une adhésion directe payée par SEPA n'atteint jamais `PAYMENT_PENDING` | **BUG ADOUBÉ** (lié à A8) | `BaseBillet/models.py:4267-4270` |
| B9 | `test_rapport_unique.py:1047`, `:1086`, `:1583`, `:1712`, `:3221`, `:3498` ; `test_fec_equilibre.py:591`, `:862` ; `test_comptabilite_admin.py:329` ; `test_comptabilite_exports.py:315` ; `test_rapport_temps_reel.py:246` | tous les vidages lus par la compta | vente `VIDAGE_CARTE` avec seulement des règlements LE, espèces ou LG, **jamais SF** | vidage réel avec FED repris : règlement SF, puis Z, puis FEC 467000 / 530000 | **BUG ADOUBÉ par omission** | `laboutik/views.py:2064-2118` ; `Fedow/fedow_core/serializers.py:236-241` (agent) |
| B10 | `tests/pytest/test_kiosk_credit.py:87-121` (7 tests) | `carte_et_borne` | carte avec un `wallet_ephemere` local déjà posé | carte rapatriée (sans portefeuille) : le crédit appelle d'abord Fedow (`_obtenir_ou_creer_wallet`, `kiosk/credit.py:129`). Si Fedow échoue, l'erreur est journalisée et le crédit n'est pas fait (`:165-170`) alors que la CB est débitée. Un rattrapage par « sondage » est évoqué (`:136`) mais je ne l'ai pas vérifié | DOUTEUX À TRANCHER | `kiosk/credit.py:105-170` ; `laboutik/views.py:1424-1433` |
| B11 | `tests/pytest/test_fec_equilibre.py:1592` | `test_fec_reglement_fed_au_compte_du_reseau` | `MappingMonnaie` sur un `uuid4()` au hasard | miroir `AssetFedowPublic` du FED, puis chargeur du plan, puis FEC | DOUTEUX À TRANCHER | `laboutik/plan_comptable.py:241-259`, `:448-457` (agent) |
| B12 | `tests/e2e/test_renouvellement_adhesion_recurrente.py:252-273` ; `test_caracterisation_en_ligne.py:1010` ; `test_vente_modeles.py:387` ; `test_en_ligne_ecrit_la_vente.py:1336` | renouvellement d'abonnement | métadonnées de la `Subscription` recopiées par le test | 1ᵉʳ checkout en `mode=subscription`, puis `Subscription.modify(metadata)`, puis `invoice.paid` : jamais traversé | DOUTEUX À TRANCHER | `BaseBillet/models.py:4246-4251` ; `ApiBillet/views.py:1489-1527` (agent) |
| B13 | `tests/pytest/test_laboutik_adhesions_apres_paiement.py:72-96` | `carte_d_un_adherent` | `SimpleNamespace(user=adherent)` | carte rapatriée sans user | DOUTEUX À TRANCHER | lié à A6 |
| B14 | `tests/pytest/test_card_refund_service.py:110-175` | `test_rembourser_carte_avec_user_*` | FED local forcé (`FEDOW_AUTORISER_ASSET_FED_LOCAL`), carte « avec user » en fait anonyme | — | LIMITE LÉGITIME DOCUMENTÉE (préparation d'un FED local) | docstring `:112-121` (agent) |
| B15 | `tests/pytest/test_remboursement_especes_trace_comptable.py:109-138` | vidage « monnaie locale ET fédérée » | FED local et `can_fedow` forcé à False | le vrai vidage FED passe par l'ancien Fedow | LIMITE LÉGITIME DOCUMENTÉE (titre trompeur) | (agent) |

### C. Simulateurs qui ne couvrent qu'une partie des réponses réelles

| # | fichier:ligne | simulateur | ce qui manque par rapport au vrai Fedow ou Stripe | verdict | impact | preuve |
|---|---|---|---|---|---|---|
| C1 | `tests/pytest/test_rapatriement_carte_fedow.py:140-172` | `fiche_de_l_ancien_fedow` | `is_wallet_ephemere: True` codé en dur, `wallet.tokens: []` toujours vide | **Cache un chemin de prod** : la carte liée (`False`) et le FED distant ne sont jamais simulés | sur toute la suite du rapatriement | vrai `CardSerializer` : `Fedow/fedow_core/serializers.py:440-475` ; `is_wallet_ephemere()` : `models.py:1172-1175` |
| C2 | `tests/pytest/test_rapatriement_carte_points_de_scan.py:340-349` | `faux_card_tag_id_retrieve` | toujours `is_wallet_ephemere: True`, sans `origin`. Une panne **lève** une exception, alors que le vrai client rend `None` sur toute réponse autre que 200, d'où « carte inconnue » | **Cache un chemin de prod** | « Fedow en panne » se confond avec « carte inconnue » au 1ᵉʳ paiement : `_obtenir_ou_creer_wallet` lève « inconnue de Fedow » | `fedow_connect/fedow_api.py:963-973` ; `laboutik/views.py:1369-1379` |
| C3 | `tests/pytest/test_wallet_carte_fedow.py:121-222` | réponses de `card_tag_id_retrieve` | seulement `is_wallet_ephemere: True` | DOUTEUX À TRANCHER | la branche « carte liée chez Fedow, `carte.user` vide en local » n'est jamais testée : le portefeuille du user est trouvé, mais le FED n'est pas lu et Fedow est rappelé à chaque scan | `laboutik/views.py:1384-1394` |
| C4 | `tests/pytest/test_caisse_ecrit_la_vente.py:1950-1962` (`transaction_du_reseau`) | débit legacy | fournit toujours `serialized_asset.category`, que la vraie réponse n'a pas | **Cache un chemin de prod** : FED débité sans vente (constat 3) | double débit possible au rescan | `Fedow/fedow_core/views.py:1742` ; `laboutik/views.py:1695-1699`, `:1814-1823`, `:10680-10693` |
| C5 | `tests/pytest/test_kiosk_ecrans.py:37-52` ; `test_kiosk_flow.py:126`, `:171` | fiche de carte de la borne | sans `wallet.uuid`, `origin`, `first_tag_id`… ; `test_kiosk_flow` sans `is_wallet_ephemere`, que la borne lit alors comme « enregistrée » | DOUTEUX À TRANCHER | 3ᵉ branche de `trouver_le_portefeuille_local` (lecture par uuid Fedow) jamais exercée | `kiosk/carte.py:88-89`, `:147` (agent) |
| C6 | `tests/pytest/test_webhook_transfer_created.py:87-110` | `FedowSimule.global_asset_bank_stripe_deposit` | « comme le vrai, rend la même transaction (208) » est faux : le vrai Fedow refuse d'abord un montant supérieur au solde (`ValueError`, donc 500), avant son anti-rejeu | DOUTEUX À TRANCHER | rejeu Stripe après un débit Fedow : virement jamais enregistré dans Lespass | `Fedow/fedow_core/views.py:509-517` ; `ApiBillet/views.py:1398-1416` (agent) |
| C7 | `tests/pytest/test_balance_soldes_et_recharge.py:653` | `refund_fed_by_signature` → 202 | le remboursement partiel (202) n'est jamais simulé | DOUTEUX À TRANCHER | le mail annonce un montant plus élevé que le virement réel | `Fedow/fedow_core/views.py:603-633` ; `BaseBillet/views.py:1823-1845` (agent) |
| C8 | `tests/pytest/conftest.py:556-592` ; `test_vente_modeles.py:266-331` | faux Stripe | aucun `checkout.session.async_payment_succeeded` ; jamais un paiement par carte sur une session `["card","sepa_debit"]` | DOUTEUX À TRANCHER | SEPA réussi jamais traversé ; risque qu'une carte soit classée SEPA | `BaseBillet/models.py:4148-4160` (agent) |
| C9 | `tests/pytest/test_plan_comptable_unique.py:3399-3488` | `card/refund` | reprend les TNF d'**un autre lieu** (impossible chez le vrai Fedow), et jamais de FED | Simulateur irréaliste | fausse couverture du vidage dans le plan comptable | `Fedow/fedow_core/serializers.py:236-241` (agent) |
| C10 | `tests/pytest/test_parcours_vente_fed_et_remise_en_banque.py:154`, `:172` | `FedowSimule` | une seule transaction, toujours FED, jamais de cascade TLF + FED | faible | — | (agent) |

### D. Contradictions entre specs figées par des tests

| # | spec A | spec B (ou réalité) | test qui fige l'une | effet |
|---|---|---|---|---|
| D1 | `QRCODECASHLESS/CHANTIER-02-rapatriement-cartes-fedow.md` §4.1 étape 6 : « Ni `user` ni `wallet_ephemere` » | `FEDOW_IMPORT/11-spec-cc-segment-legacy.md` §6bis étape 2 : carte liée → « résoudre le user via `wallet_uuid` », miroir avec `user` résolu | `test_rapatriement_carte_fedow.py:556` (n°20) ; docstring de `test_rapatriement_carte_points_de_scan.py` sur le 30 bis (CHANTIER-02 §8.4 : « Une carte rapatriée n'a jamais de user ») | La spec 11 §6bis n'est pas annulée. CHANTIER-02 affirme en plus que `obtenir_wallet_carte_depuis_fedow` « les répare au premier paiement » : c'est **faux** pour `user` (`laboutik/views.py:1390-1392` ne pose que `wallet_ephemere`) |
| D2 | spec 11 §6 garde 1 : « Carte anonyme → pas de FED » | réalité Fedow (vente = carte client + carte primaire ; FED sur portefeuille éphémère) ; `test_pos_adhesion_fusion_wallet_fedow.py:15-16` dit que le FED d'une carte anonyme existe ; le vidage le reprend (`laboutik/views.py:1909-1913`) | A1, A2, A5 | Une même carte se voit rendre son FED en espèces au vidage, mais ne peut pas le dépenser |
| D3 | borne : le FED d'une carte anonyme compte (`kiosk/carte.py:138-143`) | caisse : il ne compte pas (`laboutik/views.py:1536`) | `test_kiosk_credit.py:250` (450 + 1500 = 1950) **et** `test_c1_solde_complet_carte.py:170`, verts ensemble | La borne annonce 19,50 €, la caisse du même lieu 15,00 €. « Enregistrée » vient de Fedow côté borne (`kiosk/carte.py:147`), de `carte.user` côté caisse |
| D4 | `BaseBillet/views.py:784-795` : `CarteIntrouvable` à `/qr/link` = « ATTENDU … lieu V1 ou carte hors réseau, rien à réparer » | CHANTIER-02 §1 et §3 : les cartes d'un lieu **V2** n'existent que chez Fedow jusqu'au 1ᵉʳ scan | aucun test de cette branche (B2) | La liaison faite en ligne avant tout scan est perdue côté Lespass : c'est le bug de prod |
| D5 | `SPEC_SCAN_QR_CARTE_V2` (cité dans `fedow_core/services.py:1300-1304`) : portefeuille éphémère créé à la volée, uuid local | `laboutik/views.py:1421-1427` : « On ne fabrique PLUS de wallet local a uuid aleatoire » | `test_scan_qr_carte_v2.py:158-188` contre `test_wallet_carte_fedow.py:121` | Deux règles opposées, toutes deux vertes ; la première ne sert qu'à du code mort |
| D6 | `KIOSK/SPEC.md:4-14` : « le crédit n'est jamais stocké côté Lespass, c'est Fedow qui crédite » | `kiosk/credit.py:116-139` (commit f47023f4) : crédit TLF dans `fedow_core` local | `test_kiosk_credit.py:137` | Spec périmée : la recharge à la borne n'est pas du FED, elle est invisible au paiement QR |
| D7 | `CHANTIER-05-F-rapport-unique.md` §6 test 20 : FEC = Σ règlements du Z « par moyen et monnaie », vidage compris | même spec §2 et §7 : le vidage sort de la section 3, et le Z n'en garde que le nombre, les espèces rendues et les jetons | `test_fec_equilibre.py:1084` (`test_fec_egal_au_z`), qui pose « monnaie locale = LE − espèces rendues » | Un vidage avec FED débite le 467000 sans aucun chiffre du Z qui le justifie (agent) |
| D8 | `BaseBillet/models.py:100`, `:113-118` : SF = « En ligne : Stripe fédéré » et `online()` | `comptabilite/rapport.py:121-126`, `:253-270` : SF rangé en cashless | `test_comptabilite_service.py:170-186` fige `comptabilite/services.py:463`, du code mort | Le FED dépensé au comptoir s'affiche « En ligne » au Z (agent) |
| D9 | docstring de `test_max_per_user_adhesion_en_cours.py` : les statuts en cours empêchent un 2ᵉ prélèvement SEPA | test `:124` du même fichier : `WAITING_PAYMENT` ne compte jamais | lui-même | voir A8 |

## 3. Parcours réels de bout en bout qu'aucun test ne traverse

1. Carte connue seulement de l'ancien Fedow, liaison QR (`/qr/link`) **avant** le 1ᵉʳ scan NFC, recharge FED en ligne, scan en caisse V2 (rapatriement), solde affiché, paiement avec débit FED. C'est le bug de prod.
2. Même parcours dans l'autre ordre : scan (rapatriement), puis liaison QR (`lier_a_user` devrait réussir), puis paiement FED.
3. Carte anonyme portant du FED legacy (ancienne borne TPE ou LaBoutik V1), puis paiement caisse V2. Idem à la tireuse.
4. Carte que Fedow dit liée (`is_wallet_ephemere: False`), rapatriée : identification du client, adhésions affichées, adhésion au comptoir (`linkwallet_card_number` refusé par Fedow).
5. Débit FED réel avec une réponse Fedow sans `serialized_asset` : `asset.retrieve`, miroir `AssetFedowPublic`, règlement SF, clôture, Z, FEC 467000 ; et le cas où cette lecture échoue après le débit.
6. Vidage d'une carte avec FED sur l'ancien Fedow : vente `VIDAGE_CARTE` avec SF, section 7 du Z, FEC.
7. Borne : recharge CB d'une carte rapatriée (sans portefeuille local), puis paiement en caisse. Aucun E2E ne touche la borne.
8. Cascade à deux monnaies TLF actives (propre et fédérée `fedow_core`) sur une même carte.
9. Adhésion directe payée par SEPA, puis nouvelle adhésion ou contrôle du stock pendant le prélèvement ; SEPA réussi (`async_payment_succeeded`).
10. 1ᵉʳ abonnement Stripe réel, puis `Subscription.modify(metadata)`, puis `invoice.paid` de renouvellement.
11. `transfer.created` rejoué contre le vrai comportement de Fedow.
12. Aucun E2E n'appelle les vraies vues `/qr/<uuid>/` ou `/qr/link` : toute liaison passe par `django_shell` ou par l'ORM.

## 4. Ce que je n'ai pas pu vérifier

- **L'exécution** : aucun test n'a été lancé, je ne sais pas lesquels sont verts aujourd'hui.
- **Le FED dans la fiche de la carte** : je n'ai pas vérifié qu'il fait partie des monnaies acceptées par chaque lieu. Or le portefeuille renvoyé par Fedow est filtré par ces monnaies (`Fedow/fedow_core/serializers.py:156-166`). Le code de vidage de Lespass suppose que oui.
- **Un débit par carte et carte primaire depuis une place Lespass** n'a jamais été essayé contre le vrai Fedow. Le client Lespass n'a d'ailleurs pas de méthode `to_place`. La permission et le validateur le permettent à la lecture, mais il faut un débit par monnaie, sans la cascade « EURO » côté serveur.
- **Le volume réel en prod** des cartes rapatriées sans user mais liées chez Fedow, et des cartes anonymes portant du FED.
- **Un rattrapage du crédit de la borne** (sondage ou Celery) après un échec réseau (B10).
- **Ce qu'ont seulement survolé les agents** : environ 50 fichiers E2E vus par recherche de motifs, la reprise 05-R, `test_api_v2_wallet_refill.py`, `test_asset_recharge_signal.py`.
- **Les constats A9, A10, C6 à C10, D7 et D8** viennent des agents, sur leur lecture du code. Je n'ai pas relu chaque ligne citée.
