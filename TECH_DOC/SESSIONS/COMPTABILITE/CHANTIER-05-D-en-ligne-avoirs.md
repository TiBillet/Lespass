# Chantier 05-D — En ligne, admin, API : la vente en attente puis encaissée ; les avoirs

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue Fable + Opus, corrigée
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D1, D4, D13, D16, D26, D27, R5
> Effort : 4 j (3 sessions : §2, §3, §4) — Dépend de : A. **Pas de migration** :
> `Paiement_stripe.montant_encaisse`, `moyen` et `vente` sont créés en A ; les
> produits et catégories « Écart d'encaissement » sont des **lignes** créées à la
> demande (pas un nouveau choix de `categorie_article`). Aucun ancien lecteur ne change.

## 1. Le principe

- **Un paiement Stripe = une vente d'origine, plus ses avoirs éventuels** (R5). La
  vente d'origine est rangée dans `Paiement_stripe.vente` dès l'ouverture du checkout.
  Un panier (`Commande`) réunit des billets
  (`TicketCreator`, `create_checkout=False`, `validators.py` ~l.283), du booking
  (`services_commande.py` ~l.357) et des adhésions (~l.216) sous un seul paiement : la
  vente est ouverte par **l'orchestrateur** (`CommandeService`, l'API) et **transmise**
  aux producteurs, qui y ajoutent leurs articles. Un producteur appelé seul (adhésion
  en ligne, crowds, booking direct) ouvre sa vente lui-même.
- **Stripe** : la vente naît `EN_ATTENTE` avec les lignes (`CREATED`). Elle est
  **encaissée** quand l'argent est confirmé, avec **un** règlement Stripe du montant
  **renvoyé par Stripe**.
- **Sans Stripe** (gratuit, admin, « payé ailleurs ») : vente créée et encaissée dans
  la même transaction que les lignes.
- **Avoirs et remboursements** : une nouvelle vente `AVOIR` liée (D13), au montant
  **réellement** rendu (D27).

## 2. Session D-1 — les ventes payées par Stripe

### 2.1 Le montant encaissé

Aujourd'hui, **aucun chemin ne lit le montant encaissé par Stripe** : `amount_total`
n'est lu nulle part et `Paiement_stripe` ne le stocke pas. On ajoute
`Paiement_stripe.montant_encaisse` (centimes, fiche A) et on le pose **dans chaque
chemin qui constate le paiement** :

| Chemin | Fichier | Montant Stripe |
|---|---|---|
| Mise à jour du statut de checkout (retour navigateur et webhook) | `BaseBillet/models.py` `update_checkout_status` ~l.3524-3660 (passage `PAID` ~l.3603) | `checkout_session.amount_total` |
| Retour navigateur d'une facture d'abonnement (branche `INVOICE`) | `BaseBillet/views.py` ~l.449-465 | `invoice.amount_paid` |
| Validation API d'une facture (branche `INVOICE`) | `ApiBillet/views.py` ~l.840-855 | `invoice.amount_paid` |
| Validation API d'un checkout | `ApiBillet/views.py` ~l.899 (`paiment_stripe_validator`) | `checkout_session.amount_total` |

Chaque chemin pose `montant_encaisse` **avant** le `save()` qui passe le statut à `PAID`
(le `pre_save` le lit).

**Étape 0 de D-1 — la fixture `mock_stripe`** (`tests/pytest/conftest.py` ~l.374-415,
utilisée par 17 fichiers de tests), **avant tout code de production**. Aujourd'hui
`fake_session.amount_total` est un attribut `MagicMock` créé à la volée : `int(MagicMock())`
vaut **1**, sans erreur → `montant_encaisse = 1` et un écart silencieux dans les 17
fichiers. La fixture ne pose **pas de montant fixe** non plus (il ferait apparaître un
écart partout, et 0 simulerait une facture payée par le solde client) : `amount_total`
/ `amount_paid` sont calculés au moment du `retrieve` : Σ `total_catalogue` des articles
de la vente d'origine du `Paiement_stripe` le plus récent qui porte l'id de session du
mock (fixe : `cs_test_mock_session`, ~l.389). Un test d'écart impose sa propre valeur
(`mock_stripe.session.amount_total = …`).

### 2.2 Le point d'encaissement unique

Tous les chemins vers « payé » passent par la transition gérée en `pre_save` de
`Paiement_stripe`, qui appelle `set_ligne_article_paid` (`BaseBillet/signals.py` ~l.36 ;
transitions `PENDING → PAID`, `EXPIRE → PAID` et **`PAID → PAID`** ~l.308-319). C'est
**là** qu'on appelle `encaisser_vente_stripe(paiement_stripe)` (`services_vente.py`),
**après** le passage des lignes en payé (encaisser en dernier, fiche A §4).

Deux faits du code imposent la forme de la fonction :

- la transition `PAID → PAID` rappelle `set_ligne_article_paid` à chaque rejeu
  (`ApiBillet/views.py` ~l.899 repasse `PAID` tant que le paiement n'est pas `VALID`) ;
- le `pre_save` tourne en autocommit (pas d'`atomic` autour du `save()`).

Donc **tout** se fait dans une transaction, et la vérification « déjà réglée » vient
**avant** toute écriture :

```
with transaction.atomic():
  verrou du lieu (pg_advisory_xact_lock, le même que encaisser_vente)
  vente = Vente.objects.select_for_update().get(pk=paiement_stripe.vente_id)   # R5
  si vente.statut == REGLEE : renvoyer vente                 # rejeu : RIEN n'est écrit
  si vente.statut == ANNULEE : lever une erreur explicite    # Stripe a dit non, puis « payé » : à regarder à la main
  montant = paiement_stripe.montant_encaisse
  si montant is None : lever une erreur explicite (chemin qui n'a pas posé le montant)
  ecart = montant − Σ articles.total_catalogue
  si ecart != 0 : ajouter l'article d'écart (ci-dessous) + alerte
                  (logger.error → Sentry, badge admin fiche G)
  si montant != 0 : ajouter_reglement(vente, moyen Stripe, montant, paiement_stripe=…)
                    # montant 0 (facture payée par le solde client) : aucun règlement
  encaisser_vente(vente)
```

- **Article « Écart d'encaissement »** : **deux** produits système, créés à la demande
  par le service (`get_or_create`) : « Écart d'encaissement — reçu en plus » et « Écart
  d'encaissement — reçu en moins ». Chacun a sa **catégorie** (`CategorieProduct`, créée
  à la demande, même nom) : la fiche E relie la première au compte 758, la seconde au
  658. Pas de nouveau choix de `categorie_article`, donc **pas de migration**. L'article :
  TVA 0, `hors_chiffre_affaires`, prix unitaire = |écart|, quantité +1 (reçu en plus)
  ou −1 (reçu en moins). La ligne est créée **directement `VALID`**, **sans**
  `paiement_stripe` : elle ne bloque pas le passage du paiement à `VALID`
  (`set_paiement_stripe_valid`, `signals.py` ~l.98-120), ne déclenche aucune transition
  (création) et n'est jamais envoyée à l'ancien LaBoutik. Jamais saisie à la main.
- **Moyen du règlement** : `Paiement_stripe.moyen` (fiche A, T1), **jamais les lignes**
  (leur `payment_method` disparaît en H). Valeurs : `STRIPE_NOFED` (`SN`),
  `STRIPE_SEPA_NOFED` (`SP`, posé par `update_checkout_status` ~l.3557 — qui pose aussi
  `Paiement_stripe.moyen`), `STRIPE_RECURENT` (`SR`). **Pas `STRIPE_FED` (`SF`)** :
  malgré son nom, ce code désigne la **monnaie fédérée** dépensée en cashless
  (`laboutik/views.py` ~l.1619, ~l.4497), pas un paiement Stripe en ligne. La liste est
  reportée dans la fiche E (compte 5171).
- **Expiration** : `EXPIRE` ne change **rien** à la vente : elle reste `EN_ATTENTE`, sans
  numéro. Le code accepte `EXPIRE → PAID` (~l.315-316) : un paiement tardif l'encaisse
  telle quelle. `ANNULEE` seulement quand Stripe a dit non : `PENDING → CANCELED`
  (`expire_paiement_stripe`, `signals.py` ~l.84, qui ne fait rien aujourd'hui, appelle
  `annuler_vente` **dans ce cas seulement**, pas sur `EXPIRE`) et SEPA refusé (T5).
- SEPA : la vente reste `EN_ATTENTE` jusqu'au paiement confirmé (jusqu'à 14 jours).

### 2.3 Les producteurs

| Producteur | Fichier |
|---|---|
| Billets (panier, API) | `BaseBillet/validators.py` `TicketCreator.method_B` ~l.412, ~l.437 |
| Adhésion en ligne | `BaseBillet/validators.py` `get_checkout_stripe` ~l.974 |
| Panier (orchestrateur) | `BaseBillet/services_commande.py` ~l.216-357 ; `Commande.vente` et `Paiement_stripe.vente` renseignées |
| Booking | `booking/booking_engine.py` `validate_new_booking` ~l.692 |
| Crowds | `crowds/views.py` ~l.241, ~l.1188 |
| Renouvellement d'abonnement | `PaiementStripe/views.py` ~l.290-330 : la ligne est créée, puis un `Paiement_stripe` `PENDING` de source `INVOICE` (~l.109). La vente d'origine est ouverte **avec** la ligne, rangée dans `Paiement_stripe.vente`, et encaissée **par le même point** (§2.2) quand la branche `INVOICE` passe le paiement à `PAID`. `amount` = `price.unit_amount` (plus le total de la ligne Stripe : double compte si quantité > 1) ; prorata / remise → écart d'encaissement (D26) |

## 3. Session D-2 — ventes sans Stripe

| Producteur | Fichier | Règlement |
|---|---|---|
| Billets vendus dans l'admin | `Administration/admin_tenant.py` `ReservationAddAdmin.save` ~l.3116 | moyen choisi (espèces, CB, chèque) ; « offert » → `ajouter_article(..., offert_en_totalite=True)` : part offerte totale + FREE (D32) |
| Paiement d'adhésion dans l'admin | `BaseBillet/views.py` `ajouter_paiement` ~l.4477 | moyen choisi |
| Adhésion créée / renouvelée dans l'admin | `BaseBillet/signals.py` ~l.494 | moyen de l'adhésion ; **encaisser après** les déclencheurs Fedow (`trigger_A`, HTTP) |
| Adhésion gratuite (API) | `BaseBillet/validators.py` ~l.1128-1153 | `amount` = `contribution_value`, qui peut être **non nul** avec FREE → règle « offert à montant non nul » du service (fiche A) : part offerte totale + règlement FREE. La transition `CREATED`/`PAID → PAID` du producteur (~l.1153, e-mails) est gardée |
| ~~Réservation API v1~~ | **Supprimée** en D-1x (route cassée, `AllowAny` ; décision du mainteneur, SUIVI §5) | — |
| Réservation gratuite API v2 | `api_v2/serializers.py` ~l.1444-1471 | complète les lignes de `TicketCreator` : **même vente** (R5) ; `qty` castée en entier (aujourd'hui brute) ; `amount = prix` avec FREE (~l.1463) : si le prix n'est pas nul, règle « offert à montant non nul » (fiche A) |
| Recharge cadeau API v2 | `api_v2/views.py` `_creer_ligne_article_recharge` ~l.825-900 | voir ci-dessous |
| Webhook Fedow d'adhésion (legacy) | `fedow_connect/views.py` ~l.97 | la ligne porte `UNKNOWN` et `sale_origin=LABOUTIK` : règlement `UNKNOWN` (argent reçu par l'ancienne caisse), compte d'attente 471 (fiche E) |
| Booking gratuit | `booking/booking_engine.py` ~l.743 | aucun |

**Recharge API v2** : la ligne est créée `CREATED` **avant** l'appel réseau à Fedow
(~l.843), puis passée `VALID` ou `FAILED` par `.update()` (~l.871, ~l.884), et un échec
est retenté sur la **même** ligne (~l.825). Donc : vente `EN_ATTENTE` créée avec la
ligne ; `REGLEE` au succès (article recharge `hors_chiffre_affaires`, offert en
totalité `OFFRIR`, règlement FREE) ; à l'échec elle **reste `EN_ATTENTE`** (ligne
`FAILED`, sans numéro, sans effet comptable) et le nouvel essai l'encaisse.
`Vente.unite` : la monnaie créditée **seulement si c'est des points ou du temps**
(FID / TIM, unités brutes, D16 du chantier 04) ; une monnaie libellée en euros (locale,
cadeau, fédérée) garde `unite = EUR` — sinon le rapport (fiche F) la classerait « points »
et l'exclurait de tout. L'idempotence **reste** sur `LigneArticle.idempotency_key` jusqu'à H (le verrou 409 en
dépend ; SUIVI §4, D-2c) ; elle passe à `Vente.idempotency_key` en H.

Gratuit : total 0, aucun règlement, vente numérotée (c'est une opération enregistrée).

Pas de vente : `BankTransferService.enregistrer_virement` (`fedow_core/services.py`
~l.1155, virement entre lieux, aucun appelant hors tests) — TODO inter-tenants.

## 4. Session D-3 — avoirs et remboursements

| Producteur | Fichier | Règlement négatif |
|---|---|---|
| Annulation d'adhésion | `BaseBillet/views.py` `cancel` ~l.4593 | **un seul avoir, pour le dernier paiement** de l'adhésion (la période en cours), **pas** pour les renouvellements passés (D30 : change le comportement actuel, qui fait un avoir par ligne payée ~l.4595-4602). Règlement : ligne hors Stripe → moyen choisi (D27) ; ligne Stripe → comme l'avoir admin Stripe ci-dessous |
| Avoir de réservation hors Stripe, **fait par l'admin** | `BaseBillet/models.py` `cancel_and_refund_resa` / `cancel_and_refund_ticket` (`annulation_par_l_admin=True`), par la fonction commune `ecrire_la_vente_d_avoir_d_une_ligne` (`Reservation._creer_avoir` retirée en D-3c-1) | moyen choisi (D27) ; seulement les billets encore actifs (mainteneur, 2026-10-01) |
| Annulation **par l'utilisateur** d'une réservation / d'un booking payé **hors Stripe** (`BaseBillet/views.py` ~l.1413, ~l.1434 ; `booking/views.py` ~l.839) | `cancel_and_refund_resa` (`BaseBillet/models.py` ~l.2999-3087), **partagée** avec l'admin (`admin_tenant.py` ~l.3236, ~l.3426, ~l.3436) : elle reçoit `annulation_par_l_admin=False` (l'utilisateur, valeur par défaut) ; l'admin passe `annulation_par_l_admin=True` et `moyen_rembourse` (SUIVI §6, 2026-10-01, D-3c-1) | **aucun avoir, aucun remboursement** (D31) : réservation et billets passent `CANCELED`, l'argent reste acquis ; la garde actuelle « refus si payé et rien de remboursable » ne s'applique plus à ce cas. Si le lieu rembourse, l'admin fait un avoir (il passe un moyen). Change le comportement actuel (qui crée un avoir) |
| ~~Avoir de booking fait par l'admin~~ | **Périmé** (SUIVI §4, D-3c (e)) : aucune annulation de booking par l'admin n'existe ; l'utilisateur relève de D31 ; `Booking._creer_avoir` retiré en D-3c-1. La FK `booking` est posée par `ajouter_l_article_d_avoir` (remboursement Stripe, D-3b) | — |
| Remboursement Stripe (total ou partiel) | `PaiementStripe/utils.py` `partial_refund_payment` ~l.78 | Stripe, montant = **montant du refund renvoyé par Stripe**, `reference_externe` = id du refund |
| Avoir émis dans l'admin, ligne **hors Stripe** | `Administration/admin_tenant.py` `emettre_avoir` ~l.2059-2105 | moyen choisi (D27) |
| Avoir émis dans l'admin, ligne **payée par Stripe** (`ligne.paiement_stripe` non vide) | idem | **comportement actuel gardé (D27)** : **aucun appel à Stripe**. Règlement négatif au moyen Stripe d'origine (`Paiement_stripe.moyen`), **`reference_externe` vide** (le Z le compte « remboursement Stripe à faire à la main », fiche F), et un message prévient l'admin : « Remboursez cette somme depuis votre tableau de bord Stripe. » Pas de champ « Remboursé par » dans ce cas |

Règles :

- Vente `AVOIR`, `vente_liee` = `ligne_d_origine.vente` (vide pour une ligne de dev
  antérieure au chantier).
- Article : **même prix unitaire, quantité négative** (D13), par `calculer_montants_article`.
- **« Remboursé par »** (D27) : un champ dans chaque écran d'avoir hors Stripe
  (espèces `CA` / CB `CC` / chèque `CH` / virement `TR`), pré-rempli avec le moyen
  d'origine **s'il est dans cette liste**. Sinon (moyen d'origine cashless `LE` / `SF`,
  jetons, points, inconnu), le champ est vide et l'admin doit choisir : le recrédit
  d'une carte reste hors chantier. **Un seul règlement d'argent**, du montant rendu :
  il correspond à un vrai mouvement. Plus de répartition calculée entre plusieurs moyens.
- **Article entièrement offert** (`part_offerte == total_catalogue` : billet offert en
  caisse ou dans l'admin, D32) : **pas** de champ « Remboursé par », l'avoir n'écrit qu'un
  règlement `FREE −X` (trace de l'offert annulé). Sans cette règle, l'admin pourrait
  écrire « espèces −1500 » pour un billet jamais payé.
- **Article payé en partie en jetons** (bière 500 = 300 jetons + 200 CB, rendue) :
  l'avoir recopie la **part offerte** en négatif (−300), net −200 ; règlements : CB
  −200 (argent rendu) + FREE −300 (trace de l'offert annulé). Le moyen de trace est
  `FREE` et non `LG` : aucun jeton n'est recrédité (hors chantier), il n'y a donc aucun
  mouvement de monnaie cadeau à tracer. Les deux égalités tiennent. Pendant la
  transition, l'article est coupé en parts : l'avoir d'une part « jetons » donne
  catalogue −300, offert −300, net 0, un seul règlement FREE −300.
- Avoir **partiel** (une partie de la quantité) d'un article **en partie** offert
  (`0 < part_offerte < total_catalogue`) : **refusé** avec un message clair (« rembourser
  l'article entier ») — cas de la fiche H, où l'avoir partiel apparaît. Aucun prorata
  d'offert dans le projet. Un article **entièrement** offert (`part_offerte =
  total_catalogue`) accepte l'avoir partiel : la part offerte de l'avoir vaut son total,
  exact sans prorata (SUIVI §4, D-3c (d) : annuler 1 billet offert sur 2).
- Remboursement Stripe différent de la somme des articles de l'avoir (frais, arrondi) :
  même règle qu'à l'encaissement (écart d'encaissement, D26).
- `emettre_avoir` ne sait faire aujourd'hui qu'un avoir de **ligne entière** et refuse
  un second avoir : inchangé ici. L'avoir **sur un article** (quantité partielle) est
  l'action nouvelle de la fiche H.

## 5. Tests

Fichiers : `tests/pytest/test_en_ligne_ecrit_la_vente.py`,
`tests/pytest/test_avoirs_ecrivent_la_vente.py` (Stripe mocké ; fabriques
`fabriques_panier` ; chaque test lit sa vente).

| # | Test | Attendu |
|---|---|---|
| 1 | `test_checkout_billets_vente_en_attente_sans_numero` | `EN_ATTENTE`, numéro vide, 0 règlement |
| 2 | `test_paiement_confirme_encaisse_au_montant_stripe` | `REGLEE`, 1 règlement = `montant_encaisse`, `Paiement_stripe.vente` = la vente |
| 3 | `test_webhook_rejoue_deux_fois_une_seule_encaisse` | transition `PAID → PAID` rejouée : toujours **1** règlement, 0 ou 1 article d'écart, empreinte valide |
| 4 | `test_retour_checkout_puis_webhook_une_seule_encaisse` | |
| 4b | `test_facture_payee_par_le_solde_client_montant_zero` | `amount_paid = 0` → aucun règlement, écart −catalogue, vente `REGLEE` |
| 4c | `test_ligne_d_ecart_valid_sans_paiement_stripe` | le paiement passe `VALID` quand ses lignes le sont ; la ligne d'écart n'a pas de `paiement_stripe` |
| 5 | `test_panier_billets_booking_adhesion_une_seule_vente` | 1 vente, 1 règlement, `Commande.vente` |
| 6 | `test_stripe_canceled_vente_annulee_sans_numero` | `PENDING → CANCELED` → `ANNULEE` par `expire_paiement_stripe` |
| 7 | `test_session_expiree_reste_en_attente_puis_encaissee` | `PENDING → EXPIRE` : vente toujours `EN_ATTENTE`, sans numéro ; `EXPIRE → PAID` → `REGLEE`, numérotée |
| 8 | `test_montant_stripe_superieur_ecart_d_encaissement_758` | article « reçu en plus » +x, hors CA, alerte journalisée, vente `REGLEE` |
| 9 | `test_montant_stripe_inferieur_ecart_negatif_658` | article « reçu en moins », quantité −1 |
| 10 | `test_abonnement_quantite_2_prix_unitaire` | `amount` unitaire, total = facture ; encaissée par la branche `INVOICE` |
| 11 | `test_vente_admin_billets_especes_encaissee` | |
| 12 | ~~`test_adhesion_admin_encaissee_apres_trigger_fedow`~~ → `test_ajouter_paiement_vente_reglee_et_ligne_valide_en_sortie` (T15 : `trigger_A` ne fait plus d'appel Fedow) | ordre des appels |
| 13 | `test_adhesion_gratuite_api_montant_non_nul_offerte` | part offerte totale + FREE |
| 14 | `test_reservation_gratuite_api_v2_meme_vente_que_ticket_creator` | |
| 15 | `test_api_v2_quantite_texte_castee_en_entier` | `"2"` → 2 ; `"2.5"` → refus |
| 16 | `test_recharge_api_v2_echec_puis_nouvel_essai_une_vente` | reste `EN_ATTENTE` à l'échec, `REGLEE` au nouvel essai, une seule vente ; idempotence par `LigneArticle.idempotency_key` jusqu'à H (SUIVI §4, D-2c) |
| 17 | `test_remboursement_stripe_partiel_avoir_montant_du_refund` | `AVOIR` liée, qty négative, règlement = refund, `reference_externe` |
| 18 | `test_avoir_admin_rembourse_par_especes_un_seul_reglement` | moyen choisi ≠ moyen d'origine accepté |
| 18b | `test_avoir_admin_ligne_stripe_n_appelle_pas_stripe_et_previent_l_admin` | `stripe.Refund.create` **jamais** appelé ; règlement négatif au moyen Stripe d'origine, `reference_externe` vide ; message « Remboursez… depuis Stripe » |
| 18c | `test_avoir_billet_entierement_offert_un_seul_reglement_free` | billet offert 1500 (admin, D32) annulé par l'admin → un règlement `FREE −1500`, pas de champ « Remboursé par », aucun règlement d'argent |
| 19 | `test_avoir_part_en_jetons_de_la_cascade_un_seul_reglement_free` (l'article est en parts jusqu'à H) | −300 offert, CB −200, FREE −300 ; égalités tenues |
| 20 | `test_annulation_adhesion_avoir_lie` | |
| 21 | `test_remboursement_stripe_booking_pose_la_fk_booking` (seul l'utilisateur annule un booking : côté Stripe, D-3b) | |

Chaque test qui encaisse finit par `verifier_egalites(vente)` (fiche A). Vus rouges :
tous (aucune vente) sauf 15 (comportement actuel à observer). Le 18b est rouge sur le
code actuel pour le règlement et le message (pas pour l'absence d'appel Stripe, déjà
vraie).

Mutations : encaisser à la création du checkout (1) ; montant = Σ articles au lieu de
`montant_encaisse` (8) ; retirer l'idempotence (3, 4) ; test « déjà `REGLEE` » déplacé
après `ajouter_reglement` (3) ; règlement de 0 écrit (4b) ; ligne d'écart avec
`paiement_stripe` et statut `PAID` (4c) ; `emettre_avoir` qui appelle Stripe (18b) ;
champ « Remboursé par » offert pour un article entièrement offert (18c) ; une vente par
producteur (5) ; annuler la vente sur `EXPIRE` (7) ; `amount` = total de la ligne Stripe
(10) ; encaisser avant le déclencheur Fedow (12) ; règlement de l'avoir au moyen
d'origine forcé (18) ; part offerte non recopiée (19).

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-D-en-ligne-avoirs.md` (chaînes i18n :
« Remboursé par », « Écart d'encaissement », messages d'alerte).

## 6. Tests existants à réécrire

D30, D31 et D32 changent trois comportements ; leurs tests actuels changent dans la
même session, raison au CHANGELOG. Vérifier au démarrage :
`rg -ln "with_credit_note|cancel_and_refund|_creer_avoir|emettre_avoir|offert" tests/`.

| Cause | Fichiers |
|---|---|
| D30 : un seul avoir à l'annulation d'adhésion | `tests/e2e/test_admin_cancel_membership.py` et tout test qui compte les avoirs d'une adhésion renouvelée |
| D31 : annulation utilisateur hors Stripe sans avoir | tests d'annulation de réservation / booking par l'utilisateur qui attendent une ligne `CREDIT_NOTE` |
| D32 : billet offert admin écrit au prix, part offerte totale | tests qui assertent `amount == 0` sur un billet offert dans l'admin |
| Tests A′ « peut changer en D » (A′ §4) | modifiés ici |

## Machine à états — compléments obligatoires

Source : [`CHANTIER-05-machine-a-etats.md`](CHANTIER-05-machine-a-etats.md) §5 (trous T…). Les tests de
caractérisation de la fiche A′ doivent rester verts pendant cette fiche.

| Trou | À faire dans cette fiche | Test |
|---|---|---|
| T4 | **Aucune exception ne sort du `pre_save`** de `Paiement_stripe` : `encaisser_vente_stripe` est enveloppée dans `try / except`, `logger.error` (Sentry), vente laissée `EN_ATTENTE`. Sinon le client est payé, ses billets partent, mais le paiement reste `PENDING` et Stripe rejoue tout. **Rejeu = un appel à `encaisser_vente_stripe(paiement)`**, PAS `paiement_stripe.save()` : le paiement passe `VALID` dans son propre `pre_save` (save imbriqué de `set_paiement_stripe_valid`), et `VALID → VALID` n'est pas une transition : un `save()` ne rejoue rien (SUIVI §4 D-1, code `services_vente.py` `encaisser_vente_stripe`). L'action admin « Rejouer l'encaissement » du filtre « À vérifier » (fiche G) appelle cette fonction ; aucune commande. | `test_erreur_d_encaissement_ne_bloque_pas_le_paiement`, `test_rejeu_de_l_encaissement_par_la_fonction` |
| T5 | SEPA refusé (`async_payment_failed`, `ApiBillet/views.py` ~l.1312) : aucune transition n'est appelée → `annuler_vente(paiement.vente)` **explicite** dans cette branche. | `test_sepa_refuse_vente_annulee` |
| T6 | D16 précisé : `EN_ATTENTE` = paiement pas encore constaté, **abandon et `EXPIRE` compris** ; `ANNULEE` seulement quand Stripe a dit non (`CANCELED`, SEPA refusé), sans retour arrière. Un panier abandonné reste `EN_ATTENTE` sans numéro : aucun effet comptable. Traiter `checkout.session.expired` = nouveau comportement, hors chantier. | `test_panier_abandonne_reste_en_attente_sans_numero` |
| T7 | **Tranché (D30)** : l'annulation d'adhésion fait **un seul avoir, pour le dernier paiement** (la période en cours), pas pour les renouvellements passés. Le test de caractérisation `…avoirs_de_tous_les_renouvellements` (A′) est modifié **ici** (renommé `test_annulation_adhesion_un_seul_avoir_sur_le_dernier_paiement`) ; sa réécriture pose l'état de départ (trois paiements) **sans écrire** de colonne que H retire (`payment_method=` sur `LigneArticle.objects.create`, dans `creer_une_adhesion_payee_trois_fois`) : par le service de vente de A (vente, règlements, `Paiement_stripe.moyen`), sinon H le recasse (relecture Fable A′, constat 4). | `test_annulation_adhesion_avoir_seulement_sur_le_dernier_paiement` |
| T8 | **Tranché (D27)** : comportement actuel gardé pour les deux écrans (avoir admin, annulation d'adhésion) : aucun appel à Stripe, l'admin est prévenu. Les 2 tests A′ « n'appelle pas Stripe » restent verts **sans modification**. | A′ |
| T9 | **Tranché (D31)** : annulation par l'utilisateur d'un achat hors Stripe → **aucun avoir, aucun remboursement**. Le test A′ `test_annulation_utilisateur_reservation_admin_especes_cree_un_avoir` est modifié **ici**. | `test_annulation_utilisateur_hors_stripe_aucun_avoir_aucune_vente` |
| T12 | **Tranché (D32)** : billet **offert** vendu dans l'admin (`Administration/admin_tenant.py` ~l.3092-3095, aujourd'hui `amount = 0`) → écrit **comme un offert de la caisse** : `amount` = prix, part offerte = total, `source_offert = OFFRIR`, vente d'origine `ADMIN`, règlement `FREE`. Les anciens lecteurs excluent déjà `FREE` de l'argent (chantier 04). Le test A′ `…offert_montant_zero` est modifié **ici**. | `test_billet_offert_admin_part_offerte_totale` |
| T15 | Le test « adhésion admin encaissée après le trigger Fedow » ne détecte rien (`trigger_A` n'appelle plus Fedow en HTTP) : remplacé par un test d'ordre. | `test_ajouter_paiement_vente_reglee_et_ligne_valide_en_sortie` |
| T16 | Réservation gratuite : vente numérotée à la création, même si la réservation reste `FREERES` ou passe `CANCELED` faute de place (`signals.py` ~l.252-272). Accepté (montant 0, aucun effet comptable). | — |
