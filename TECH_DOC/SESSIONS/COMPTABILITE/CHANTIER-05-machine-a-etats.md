# Chantier 05 — Annexe : la machine à états existante, et ce que chaque fiche y change

> **Statut** : 📋 ANNEXE (2026-09-28), écrite à partir du code du working tree de ce jour
> (branche `main-fedow-import`) et des fiches 05-A à 05-H **dans leur état du même jour**
> (elles étaient en cours de correction : relire les numéros de ligne au démarrage).
> **But** : prouver que « la machine à statuts ne change pas » (tronc §3.2), ou dire
> précisément où elle change.
> **Méthode** : lecture de `BaseBillet/signals.py`, `BaseBillet/triggers.py`,
> `BaseBillet/tasks.py`, des producteurs de lignes et des annulations. Aucun test lancé.

Les numéros de ligne sont ceux du code au 2026-09-28 (`~l.` = à ±5 lignes près).

---

## 0. Ce qu'il faut retenir en une minute

1. **Le cœur de la machine** est un seul récepteur `pre_save` générique
   (`BaseBillet/signals.py` l.402-433) et un dictionnaire `PRE_SAVE_TRANSITIONS`
   (l.308-397). Il ne réagit **qu'à une modification** (jamais à une création :
   `_state.adding` l.405) et **seulement** pour 5 modèles : `Paiement_stripe`,
   `LigneArticle`, `Reservation`, `TibilletUser` (champ `is_active`), `Ticket`.
   `Vente` et `Reglement` ne portent pas ces noms : la machine les ignorera.
2. **Deux familles de producteurs** :
   - ceux qui **passent par une transition** (`CREATED/UNPAID → PAID`, `→ REFUNDED`,
     `→ CREDIT_NOTE`) : en ligne, admin, API, annulations. Ils déclenchent e-mails,
     adhésions, billets, envoi à l'ancien LaBoutik, récompenses Fedow ;
   - ceux qui **créent la ligne directement `VALID`** : caisse, tireuse, QR/NFC recréé,
     paiement « ailleurs », webhook Fedow legacy, recharge API v2. **Aucun déclencheur.**
     Leurs effets (adhésion, billets, e-mails) sont codés à la main dans le producteur.
3. **Aucune transition ne lit `payment_method`, `asset`, `carte`, `wallet`,
   `uuid_transaction`, `idempotency_key` ou `point_de_vente`** pour décider d'un
   statut. **Mais six effets les lisent** (SEPA, anti-rejeu QR, envoi et remboursement
   vers l'ancien LaBoutik, TVA par défaut, idempotence caisse et API v2, copies dans les
   avoirs) : c'est là que la fiche H casse quelque chose (§3, §5).
4. **Quatre changements voulus de la logique métier**, tous en fiche D : D30
   (annulation d'adhésion : un seul avoir, pour le dernier paiement), D31 (annulation
   par l'utilisateur d'un achat hors Stripe : aucun avoir), D32 (billet offert dans
   l'admin écrit au prix, part offerte totale), et la FK `booking` posée sur l'avoir
   d'un booking. **Aucun appel Stripe nouveau** : D27 garde le comportement actuel
   (aucun avoir de l'admin n'appelle Stripe, §5 T8) ; le règlement Stripe négatif est
   écrit sans `reference_externe` et le Z le compte « à faire à la main ». En G,
   `total_paid()` sur `total_ttc` retire l'avoir d'argent d'un billet entièrement
   offert (décidé le 2026-09-29).
5. Les fiches B, C, D **ajoutent** des écritures (Vente, Reglement) sans toucher aux
   statuts : c'est vrai **si** le point d'encaissement Stripe ne lève jamais d'exception
   dans le `pre_save` (§5, T4).

---

## 1. Inventaire des statuts

### 1.1 `LigneArticle.status` — `BaseBillet/models.py` l.3706-3724

| Code | Nom | Posé par (principaux) |
|---|---|---|
| `O` | `CREATED` (« pas envoyé au paiement ») | défaut ; tous les producteurs à transition |
| `U` | `UNPAID` | `.update()` après création du checkout (`validators.py` ~l.504, ~l.1000 ; `services_commande.py` ~l.472 ; `booking_engine.py` ~l.726, ~l.776 ; `crowds/views.py` ~l.290, ~l.1234 ; `PaiementStripe/views.py` ~l.340 ; `ApiBillet/serializers.py` ~l.1226) ; réservation anti-rejeu QR/NFC (`BaseBillet/views.py` ~l.1941, ~l.2231) |
| `P` | `PAID` (« payé, pas confirmé ») | `set_ligne_article_paid` (`signals.py` l.48) ; producteurs admin/API (`signals.py` l.514, `views.py` ~l.4566, `validators.py` ~l.309, ~l.1151, `services_commande.py` ~l.526) |
| `V` | `VALID` | posé **en mémoire** par `trigger_A/B/C` dans le `pre_save` (`triggers.py` l.222, l.238, l.320) ; création directe (caisse, tireuse, QR recréé, admin billets, payé ailleurs, webhook Fedow) ; `.update()` recharge API v2 (`api_v2/views.py` ~l.891) ; crowds (`crowds/views.py` ~l.160, `ApiBillet/views.py` ~l.1272) |
| `F` | `FREERES` | réservation gratuite API (`api_v2/serializers.py` ~l.1469, `ApiBillet/serializers.py` ~l.1250) |
| `R` | `REFUNDED` | ligne **négative** créée par `partial_refund_payment` (`PaiementStripe/utils.py` l.101) |
| `N` | `CREDIT_NOTE` | ligne **négative** d'avoir (`models.py` l.2994, `booking/models.py` l.641, `views.py` ~l.4685, `admin_tenant.py` ~l.2097) |
| `D` | `FAILED` | SEPA refusé (`ApiBillet/views.py` l.1313), QR/NFC incertain (`views.py` ~l.1981, ~l.2254), recharge API v2 (`api_v2/views.py` ~l.884) |
| `C` | `CANCELED` | **jamais posé** hors tests (mort) |

Point important : la ligne d'origine **ne change jamais de statut** lors d'un
remboursement ou d'un avoir. On **ajoute** une ligne négative (`REFUNDED` ou
`CREDIT_NOTE`), reliée par `credit_note_for` (avoir) ou par `metadata.original_lignearticle_uuid`.

### 1.2 `Paiement_stripe.status` — `BaseBillet/models.py` l.3432-3446

`N` NON (défaut), `O` OPEN (jamais posé), `W` PENDING, `E` EXPIRE, `F` FAILED, `P` PAID,
`V` VALID, `S` NOTSYNC (**jamais posé**, seulement lu), `C` CANCELED, `R` REFUNDED,
`H` PARTIALLY_REFUNDED. Drapeau associé : `traitement_en_cours` (verrou applicatif).

### 1.3 `Reservation.status` — `BaseBillet/models.py` l.2851-2865

`C` CANCELED, `R` CREATED, `U` UNPAID, `F` FREERES, `FA` FREERES_USERACTIV, `P` PAID,
`PE` PAID_ERROR, `PN` PAID_NOMAIL, `V` VALID. Drapeaux : `to_mail`, `mail_send`, `mail_error`.

### 1.4 `Ticket.status` — `BaseBillet/models.py` l.3280-3290

`C` CREATED, `N` NOT_ACTIV, `K` NOT_SCANNED, `S` SCANNED, `R` CANCELED.

### 1.5 `Membership` — `BaseBillet/models.py` l.4046-4095 (+ `set_deadline` l.4135, `is_valid` l.4274)

`status` : `WP` WAITING_PAYMENT, `D` ADMIN, `I` IMPORT, `L` LABOUTIK, `AW` ADMIN_WAITING,
`AV` ADMIN_VALID, `PP` PAYMENT_PENDING, `A` ONCE, `O` AUTO, `C` CANCELED, `AC`
ADMIN_CANCELED. Champ `state` (l.4033-4043) : hérité, non piloté par la machine.
La **validité** n'est pas un statut : `is_valid()` = pas `ADMIN_CANCELED`, et
`deadline` dans le futur (`CANCELED` reste valide jusqu'à `deadline`). `deadline` est
posée par `set_deadline()` (qui fait un `save()`), à partir de `last_contribution`.
Autres champs pilotés : `contribution_value`, `payment_method`, `first/last_contribution`,
`stripe_id_subscription`, `last_stripe_invoice`, `current_iteration`.

### 1.6 `Commande.status` — `BaseBillet/models.py` l.1666-1683

`DRAFT`, `PENDING`, `PAID` (+ `paid_at`), `CANCELED` et `EXPIRED` (**jamais posés** hors tests).

### 1.7 `booking.Booking.status` — `booking/models.py` l.468-481

`WP` WAITING_PAYMENT, `CA` ADMIN_CANCELED, `VA`, `WA`, `PA` PAID_BY_USER, `AU`, `UC`
USER_CANCELED, `FR` FREERES, `FU` FREERES_USERACTIV. La transition `BOOKING` est
commentée dans `PRE_SAVE_TRANSITIONS` (l.392-396) : le booking **ne déclenche rien**.

### 1.8 `crowds.Contribution.payment_status` — `crowds/models.py` l.342-358

`pending`, `paid`, `admin_paid` (« indiquée comme payée » : **aucune ligne de vente**).

### 1.9 Caisse : `laboutik.CommandeSauvegarde.statut` — `laboutik/models.py` ~l.1110-1121

`OP` OPEN, `SV` SERVED, `PA` PAID, `AN` CANCEL. Aussi `ArticleCommandeSauvegarde.statut`
(`EN_ATTENTE`, `SERVI`, `ANNULE`) et `Table.statut` (`LIBRE`, `OCCUPEE`, `SERVIE`).

### 1.10 `fedow_core.Transaction` — `fedow_core/models.py` ~l.437-447

Pas de statut : un **journal** immuable. `action` : `FST`, `CRE`, `RFL`, `SAL`, `QRS`,
`FUS`, `RFD`, `VOI`, `DEP`, `TRF`, `BTR`. Pertinent pour `Reglement.fedow_transaction_uuid`.

---

## 2. Transitions et effets

### 2.1 La table `PRE_SAVE_TRANSITIONS` (`BaseBillet/signals.py` l.308-397)

Lecture : « si l'ancien statut en base vaut X et le nouveau Y, appeler F ».
`_else_` = toute autre valeur. Absent = rien.

| Modèle | Ancien → Nouveau | Fonction (signals.py) |
|---|---|---|
| Paiement_stripe | `W → P`, `E → P`, **`P → P`** | `set_ligne_article_paid` (l.36) |
| Paiement_stripe | `W → E`, `W → C` | `expire_paiement_stripe` (l.86) — **ne fait rien** |
| Paiement_stripe | `P → V` | `valide_stripe_paiement` (l.91) — journal seulement |
| Paiement_stripe | `P/V → H`, `P/V → R` | `no_change` |
| Paiement_stripe | `P → autre`, `V → autre` | `error_regression` (journal, **ne bloque pas**) |
| Paiement_stripe | `N → P`, `W → F`, `H → R`… | **rien** (clé absente) |
| LigneArticle | `O → P`, `U → P`, **`P → P`** | `ligne_article_paid` (l.134) |
| LigneArticle | `O → R` | `ligne_article_refunded` (l.144) |
| LigneArticle | `O → N` | `ligne_article_credit_note` (l.151) |
| LigneArticle | `P → V` | `set_paiement_stripe_valid` (l.101) |
| LigneArticle | `V → V` | `no_change` ; `P → autre`, `V → autre` : `error_regression` |
| LigneArticle | `O → V`, `O → F`, `R/N/D → *` | **rien** |
| Reservation | `R → P`, `R → FA`, `F → FA`, `FA → FA`, `U → P`, **`P → P`** | `reservation_paid` (l.166) |
| Reservation | `P → PE` | `error_in_mail` (l.212) |
| Reservation | `P → V` | `set_paiement_valid` (l.199) |
| Reservation | `P → C`, `V → V`, `V → C` | `no_change` |
| Reservation | `R → V`, `R → C`, `F → C`… | **rien** |
| TibilletUser | `is_active False → True` | `activator_free_reservation` (l.231) |
| Ticket | `K → S` | `check_reward` (l.220) |

Autres récepteurs qui comptent :

| Récepteur | Où | Quand | Effet |
|---|---|---|---|
| `create_lignearticle_if_membership_created_on_admin` | `signals.py` l.495-529 | `post_save` Membership, **créée** avec `status=ADMIN` | crée une `LigneArticle` `CREATED` (moyen = `membership.payment_method`, `sale_origin=ADMIN`), puis la passe `PAID` → `trigger_A` |
| idem | l.518-529 | **tout** `save()` d'une adhésion qui a une `deadline` | `webhook_membership` en `on_commit` |
| `commande_mark_paid_when_paiement_valid` | `signals.py` l.602-631 | `post_save` Paiement_stripe `VALID` | `Commande → PAID`, `paid_at` |
| `contribution_paid_notify` | `crowds/signals.py` ~l.100-125 | `post_save` Contribution `pending` (hors TEST) | e-mail admin |

### 2.2 Le détail des fonctions déclenchées

| Fonction | Ce qu'elle fait (effets de bord) |
|---|---|
| `set_ligne_article_paid` (l.36-83) | 1) chaque ligne du paiement **non `VALID`** → `PAID` + `save()` (donc `ligne_article_paid` par ligne) ; 2) réservations à valider = FK du paiement + FK des lignes + réservations de la `Commande` du paiement → `PAID` + `save()` (donc `reservation_paid`) |
| `ligne_article_paid` (l.134-142) | `TRIGGER_LigneArticlePaid_ActionByCategorie(ligne)` puis `set_paiement_stripe_valid` |
| `TRIGGER_…` (`triggers.py` l.169-193) | choisit `trigger_<catégorie>` d'après `pricesold.productsold.categorie_article` (repli sur le produit). **Avale toute exception** (journal). Catégories avec déclencheur : `A` adhésion, `B` billet, `C` ressource. Toutes les autres (`D` don, `F`, `R`, `S`, `N` crowds, `Q`…) : rien, la ligne **reste `PAID`** |
| `trigger_A` (l.255-325) | si `paiement_stripe` : `update_membership_state_after_stripe_paiement` (l.20-140 : garde `ADMIN_CANCELED` ; `contribution_value = pricesold.prix` ; `ONCE`, ou `AUTO` + `current_iteration += 1` + `Subscription.modify(cancel_at_period_end)` si max atteint ; `last_stripe_invoice`) ; `set_deadline()` ; rattache l'utilisateur au lieu (`client_achat`) ; nom/prénom ; **`send_membership_invoice_to_email.delay`** (tout de suite) ; `send_to_ghost` / `send_to_brevo` si newsletter ; **en `on_commit`** : `refill_from_lespass_to_user_wallet_from_price_solded` (récompense Fedow, HTTP dans la tâche) et `send_sale_to_laboutik` ; ligne → `VALID` en mémoire. **Plus aucun appel HTTP Fedow direct** (`triggers.py` l.12, l.289-300) |
| `trigger_B` (l.228-240) | `send_sale_to_laboutik` en `on_commit` ; ligne → `VALID` en mémoire |
| `trigger_C` (l.203-224) | nom/prénom de l'utilisateur ; `booking → PAID_BY_USER` ; ligne → `VALID` en mémoire |
| `set_paiement_stripe_valid` (l.101-131) | si la ligne devient `VALID` et que **toutes** les autres lignes du même paiement sont `VALID` : `paiement → VALID`, `traitement_en_cours=False`, `save()` |
| `reservation_paid` (l.166-196) | `webhook_reservation.delay` ; billets `NOT_ACTIV/NOT_SCANNED → NOT_SCANNED` ; si mail pas envoyé : `ticket_celery_mailer.delay` (qui passe la réservation `VALID`, `PAID_NOMAIL` ou `PAID_ERROR`, `tasks.py` l.1388-1460) ; sinon `set_paiement_valid` |
| `set_paiement_valid` (l.199-209) | si `mail_send` : paiements `PAID` de la réservation → `VALID` |
| `error_in_mail` (l.212-215) | `traitement_en_cours=False` sur les paiements (le statut reste `PAID`) |
| `ligne_article_refunded` / `_credit_note` (l.144-160) | si pas `sended_to_laboutik` : `send_refund_to_laboutik.delay` (**pas** en `on_commit`) |
| `activator_free_reservation` (l.231-284) | réservations `FREERES` du compte → `FREERES_USERACTIV` (→ `reservation_paid`) ; si l'événement est complet : billets `NOT_ACTIV`, réservation `CANCELED`, `ValueError` affichée |
| `check_reward` (l.220-226) | `refill_from_lespass_to_user_wallet_from_ticket_scanned.delay` (récompense Fedow au scan) |

**Subtilité qui compte pour la fiche D.** Dans `set_ligne_article_paid`, les lignes
sont lues par `new_instance.lignearticles` : Django pose `ligne.paiement_stripe` = **le
même objet Python** que le paiement en cours de `save()`. Quand la dernière ligne passe
`VALID`, `set_paiement_stripe_valid` met cet objet à `VALID` et le sauve (sauvegarde
**imbriquée**, `post_save` → `Commande → PAID`), **avant** que la sauvegarde extérieure
(`PAID`) ne finisse ; celle-ci écrit alors `VALID`. Donc : panier où toutes les lignes
ont un déclencheur (`A`, `B`, `C`) → paiement `VALID` et `Commande PAID` **pendant** le
`pre_save` ; panier avec une ligne sans déclencheur (don, crowds) → paiement `PAID`
jusqu'au mail des billets (`set_paiement_valid`) ou à la vue crowds.

### 2.3 Transitions faites hors de la machine (code explicite)

| Déclencheur | Où | Condition | Effets |
|---|---|---|---|
| Retour navigateur / webhook `checkout.session.completed` ou `async_payment_succeeded` | `models.py` `update_checkout_status` l.3525-3660 ; `ApiBillet/views.py` l.1200-1288 ; `views.py` l.3512-3517, l.4042-4047, l.470 | `payment_status` Stripe | `unpaid` → `PENDING` (ou `EXPIRE` si `expires_at` passé) ; `paid` → `PAID` + `traitement_en_cours` (abonnement : `subscription`, `invoice_stripe`, `Subscription.modify(metadata)`) ; autre → `CANCELED`. **SEPA** : `lignearticles.update(payment_method=SP)` (l.3557, l.3577). `PENDING` + session `complete` : adhésions `ADMIN_VALID → PAYMENT_PENDING` (l.3648-3650) |
| Webhook SEPA en attente | `ApiBillet/views.py` l.1228-1244 | paiement `PENDING` et **`première ligne.payment_method == SP`** | `send_membership_sepa_pending_user.delay` par adhésion |
| Webhook contribution crowds | `ApiBillet/views.py` l.1255-1287 ; vue retour `crowds/views.py` ~l.130-170 | `metadata.contribution_uuid`, paiement `PAID/VALID` | contribution `paid`, ligne `VALID` (`save(update_fields)` → `P → V`), paiement `VALID`, `email_contribution_paid_user.delay` |
| Webhook `async_payment_failed` (SEPA refusé) | `ApiBillet/views.py` l.1290-1330 | — | paiement → `FAILED` (**aucune transition**), lignes → `FAILED` par `.update()`, adhésions `PAYMENT_PENDING → ADMIN_VALID`, `send_payment_refused_user.delay` |
| Webhook `invoice.paid` (renouvellement) | `ApiBillet/views.py` l.1413-1470 → `PaiementStripe/views.py` l.290-341 → `paiment_stripe_validator` l.841-858 | facture ≠ `last_stripe_invoice` | ligne `CREATED` (`SR`, `amount = line.amount`, `qty = line.quantity`) → `UNPAID` ; paiement `PENDING` source `INVOICE` → `PAID` → `trigger_A` (`AUTO`, itération) |
| Remboursement Stripe | `PaiementStripe/utils.py` l.9-114 (appelé par `cancel_and_refund_resa` l.2999, `cancel_and_refund_ticket` l.3089, `cancel_and_refund_booking`) | lignes `VALID/PAID` du paiement | `stripe.Refund.create(amount = Σ amount × qty)` ; paiement → `PARTIALLY_REFUNDED` ; une ligne négative par ligne `CREATED → REFUNDED` (→ `send_refund_to_laboutik`) ; si `total() == 0` → `REFUNDED` |
| Annulation réservation / billet | `models.py` l.2999-3087, l.3089-3180 | `total_paid()` > 0 ; pas de billet scanné | Stripe : ci-dessus ; hors Stripe : `_creer_avoir` (`CREDIT_NOTE`) ; billets → `CANCELED` ; réservation → `CANCELED`. Refus si payé et rien de remboursable. Appelé par l'utilisateur (`views.py` ~l.1413, ~l.1434) **et** l'admin (`admin_tenant.py` ~l.3236, ~l.3426, ~l.3436) |
| Annulation booking | `booking/models.py` ~l.660-700 | pas déjà annulé | Stripe : `partial_refund_payment` ; hors Stripe : avoir si `amount > 0` (**sans FK `booking`**) ; `USER_CANCELED`. Appelé par l'utilisateur (`booking/views.py` ~l.839) |
| Annulation d'adhésion (admin) | `views.py` `cancel` l.4572-4700 | POST | `ADMIN_CANCELED` ; option résiliation Stripe (non bloquante) ; option avoirs : **un avoir par ligne `VALID/PAID` de l'adhésion sans avoir** (donc **tous les renouvellements**), `CREDIT_NOTE`. **Aucun remboursement Stripe** |
| Avoir admin | `admin_tenant.py` `emettre_avoir` l.2059-2105 | ligne `VALID/PAID` sans avoir | ligne négative `CREDIT_NOTE` (copie `payment_method`, `asset`, `wallet`, `paiement_stripe`). **Aucun remboursement Stripe** |
| Paiement d'adhésion admin | `views.py` `ajouter_paiement` l.4477-4570 | statut autorisé | adhésion `ONCE` (+ dates, moyen) ; ligne `CREATED → PAID` → `trigger_A` |
| Adhésion gratuite API | `validators.py` l.1128-1155 | `FREE` ou montant 0 | adhésion `ONCE`, `set_deadline` ; ligne créée **`PAID`** puis `save(update_fields=["status"])` = **`P → P`** → `trigger_A` |
| Réservation à 0 € / panier gratuit | `validators.py` l.296-317 ; `services_commande.py` l.476-560 | total 0 | lignes billets/adhésions `→ PAID` + `FREE` (→ `trigger_A/B` → `VALID`) ; lignes booking → `VALID` direct ; réservations `FREERES/FREERES_USERACTIV` ; bookings idem ; `Commande PAID` |
| Paiement « ailleurs » (API v2, LaBoutik V1) | `validators.py` l.411-432, l.463-465 | `paid_externally` | ligne créée `VALID` (aucun déclencheur) ; billets `NOT_SCANNED` ; réservation `CREATED → VALID` : **aucune transition, donc pas de mail** (le commentaire l.460 dit le contraire) |
| Billets vendus dans l'admin | `admin_tenant.py` ~l.3092-3110 | — | ligne `VALID` (offert → `amount = 0`) ; `send_sale_to_laboutik.delay` et `ticket_celery_mailer.delay` (pas en `on_commit`) |
| Booking | `booking_engine.py` ~l.692-747 | `to_pay()` | payant : lignes `→ UNPAID` (save), checkout ; gratuit : booking `FR/FU`, ligne `FREE` + `VALID` (pas de `trigger_C`) |
| Caisse (tous chemins) | `laboutik/views.py` `_creer_lignes_articles` l.5311, `_creer_lignes_articles_cascade` l.5559 | — | lignes créées `VALID` (aucun déclencheur) ; stock décrémenté **une fois par article** (l.5436-5450, ~l.5744-5780) ; adhésion : `_creer_ou_renouveler_adhesion` l.5869-5950 (`LABOUTIK`, `set_deadline`, donc `webhook_membership`) ; billets : `_creer_billets_depuis_panier` l.6399 (réservation créée `VALID`, billets `NOT_SCANNED`) puis `_envoyer_billets_par_email` l.6593 **après** l'`atomic` ; FK `membership` / `reservation` posée par `save(update_fields=…)` (`V → V`, rien) sur **une seule part** |
| Commande de table | `laboutik/views.py` `payer_commande` l.11565-11891 | — | `OPEN/SERVED → PAID`, articles `SERVI`, table `LIBRE` si plus rien d'ouvert |
| Clôture de caisse (bouton) | `laboutik/views.py` ~l.2727-2737 | — | tables `OCCUPEE/SERVIE → LIBRE`, commandes **`OPEN → CANCEL`** |
| QR/NFC en ligne | `views.py` l.1871-1885 (demande), l.1921-2084 (`process_with_nfc`), l.2086-2350 (`process_qrcode`) | ligne `CREATED` **et `payment_method = QRCODE_MA`** | `→ UNPAID` (anti-rejeu, 04-F-1) ; Fedow ; échec → `FAILED` ; succès → ligne **supprimée puis recréée** une par monnaie, `VALID`, `send_sale_to_laboutik.delay` **par part**, e-mails admin + client |
| Recharge API v2 | `api_v2/views.py` ~l.790-935 | `idempotency_key` sur la ligne | ligne `CREATED` (= « en cours », 409 sur rejeu) ; Fedow ; `.update(VALID)` ou `.update(FAILED)` ; rejeu d'un `FAILED` → `.update(CREATED)` et nouvel essai ; rejeu d'un `VALID` → 208 reconstruit depuis la ligne |
| Webhook Fedow d'adhésion (legacy) | `fedow_connect/views.py` ~l.66-106 | — | adhésion `LABOUTIK`, `set_deadline` ; ligne `UNKNOWN` `VALID` directe |
| Crowds « marquer payée » (admin) | `crowds/views.py` ~l.1276-1279 | admin | contribution `admin_paid` ; **aucune ligne, aucun paiement** |

---

## 3. Champs de `LigneArticle` lus par les effets, et impact par fiche

Légende impact : **=** rien ne change ; **✎** à adapter (prévu par la fiche) ;
**⚠** non prévu par les fiches → trou du §5.

| # | Effet | Où | Champs de la ligne lus | B / C / D | G | H |
|---|---|---|---|---|---|---|
| E1 | `set_ligne_article_paid` | `signals.py` l.36-83 | `status`, `reservation`, (reverse `paiement_stripe`) | D : point d'encaissement ajouté à la fin **=** pour les statuts | = | = |
| E2 | `set_paiement_stripe_valid` | l.101-131 | `status`, `paiement_stripe`, `uuid` | D : la ligne d'écart n'a pas de `paiement_stripe` **=** | = | = |
| E3 | aiguillage des déclencheurs | `triggers.py` l.169-193 | `pricesold.productsold.categorie_article` | = | = | = |
| E4 | `trigger_A` + `update_membership_state…` | `triggers.py` l.20-140, l.255-325 | `membership`, `paiement_stripe`, **`pricesold.prix`** (devient `contribution_value`), `pk` | = | = | = (une ligne par adhésion : déjà le cas en ligne) |
| E5 | `trigger_B` / `trigger_C` | l.203-240 | `booking`, `pk` | = | = | = |
| E6 | `send_sale_to_laboutik` + `LigneArticleSerializer` | `tasks.py` l.1029-1127 ; `ApiBillet/serializers.py` l.1296-1315 | `uuid`, `pricesold`, `qty`, `vat`, `datetime`, **`payment_method`**, `amount`, `metadata`, **`asset`**, **`wallet`**, `status`, `sended_to_laboutik` | = | ✎ moyen, `asset`, `wallet` lus dans le règlement, un envoi par ligne (T10) | champs retirés : ✎ via G |
| E7 | `send_refund_to_laboutik` (même sérialiseur) | `tasks.py` l.945-1025 ; déclenché par `O → R` et `O → N` | idem E6 | = | **⚠ non traité** | **⚠ T3** : le sérialiseur plante (champ absent) dans la tâche Celery, en silence |
| E8 | récompense Fedow d'adhésion | `tasks.py` l.1867-1943 | `pricesold.price`, `membership`, `paiement_stripe`, **`metadata.fedow_reward`** (anti-doublon **par ligne**) | = | = | = (caisse : jamais déclenché) |
| E9 | remboursement Stripe | `PaiementStripe/utils.py` l.9-114 | `amount`, `qty`, `to_refund_qty`, `total()`, `status`, `pricesold`, `vat`, `reservation`, `booking`, `membership`, **`payment_method`, `asset`, `wallet`** (copiés), `metadata` | D : + vente `AVOIR` | = | **⚠ T20** : copies à retirer ; `amount × qty` (montant envoyé à Stripe) visé par le test de garde H#10 **⚠ T22** |
| E10 | `Paiement_stripe.total()` / `is_fully_refunded` | `models.py` l.3480-3497 | `amount × qty` | = | ✎ Σ `total_ttc` | = |
| E11 | `Reservation.total_paid` (garde d'annulation) | `models.py` l.2921-2926 | `amount × qty`, `status` | = | ✎ Σ `total_ttc` | = |
| E12 | `Booking.total_paid`, **`to_pay`** (décide Stripe ou gratuit) | `booking/models.py` l.577-590 | `amount × qty`, `status` | = | **⚠ T22** (non listé en G) | garde H#10 |
| E13 | `TicketCreator` : Stripe ou « réservation à 0 € » | `validators.py` ~l.289-294 | `amount × qty` | = | **⚠ T22** | garde H#10 |
| E14 | `_lignes_hors_stripe` + `_creer_avoir` (réservation) | `models.py` l.2937-2997 | `paiement_stripe`, `status`, `pricesold`, `qty`, `credit_notes`, `amount`, `vat`, `reservation`, `membership`, **`payment_method`, `asset`, `wallet`**, `metadata` | D : + vente `AVOIR` | = | une ligne au lieu de N parts : avoir d'un billet caisse = **article entier** (aujourd'hui : la part qui porte la FK) — changement voulu, à écrire au CHANGELOG ; copies **⚠ T20** |
| E15 | avoir booking | `booking/models.py` l.592-643 | idem + garde **`amount > 0`** | D ✎ (+ FK booking) | = | **⚠ T20** |
| E16 | annulation d'adhésion | `views.py` l.4595-4687 | `membership`, `status`, `credit_notes`, `qty`, `amount`, `vat`, `paiement_stripe`, **`payment_method`, `asset`, `wallet`** | D ✎ **⚠ T7, T8** | = | **⚠ T20** ; caisse : la FK n'est que sur une part, H corrige (avoir de l'article entier) |
| E17 | `emettre_avoir` | `admin_tenant.py` l.2059-2105 | `status`, `credit_notes`, `qty`, `amount`, `vat`, `paiement_stripe`, `membership`, **`payment_method`, `asset`, `wallet`** | D ✎ (Stripe : pas d’appel, D27) | G : avoir partiel | **⚠ T20** |
| E18 | SEPA : pose du moyen | `models.py` l.3557, l.3577 | **écrit** `payment_method = SP` | D lit ce moyen pour `Reglement.moyen` | = | **⚠ T1** : champ retiré |
| E19 | SEPA : e-mail « en attente » | `ApiBillet/views.py` l.1228-1244 | **`première ligne.payment_method`**, `membership` | = | = | **⚠ T1** : l'e-mail ne part plus |
| E20 | SEPA refusé | `ApiBillet/views.py` l.1311-1313 | `.update(status=FAILED)` | **⚠ T5** : vente jamais annulée | = | = |
| E21 | anti-rejeu QR/NFC | `validators.py` l.1380-1381 ; `views.py` l.1937-1941, l.2227-2231 | `status`, **`payment_method = QRCODE_MA`**, `amount`, `pricesold`, `metadata` | C ✎ (restructuré) | = | **⚠ T2** : filtre sur un champ retiré (`FieldError`) |
| E22 | recharge API v2 (idempotence, rejeu 208) | `api_v2/views.py` ~l.790-935 | **`idempotency_key`**, `status`, `metadata`, `amount`, **`asset`** (~l.931) | D ✎ (`Vente.idempotency_key`) | = | ✎ idempotence ; **⚠ T18** : `asset` du rejeu |
| E23 | idempotence caisse | `laboutik/views.py` l.4611-4668 | **`uuid_transaction`** | B ✎ | = | ✎ (listé en H) |
| E24 | TVA par défaut à la création | `models.py` l.3854-3895 | **`payment_method`** (FREE, NM), `pricesold` | A ✎ (marqueur `_tva_explicite`) | = | **⚠ T19** |
| E25 | facture d'adhésion (hors Stripe) | `tasks.py` l.145-172 | `membership`, `status`, gabarit (`amount`, `qty`) | = | ✎ « la facture lit la vente » | caisse : H corrige (une ligne, montant entier) |
| E26 | fiche utilisateur de l'admin | `admin_tenant.py` ~l.1170-1181 | `amount × qty`, **`payment_method`** | = | ✎ (lecteurs) | à lire sur la vente |
| E27 | stock de la caisse | `laboutik/views.py` l.5436-5450, ~l.5744-5780 | aucun champ lu ; écrit `MouvementStock.ligne_article` = 1ʳᵉ part | = | = | = (la quantité vient de `weight_amount` / `quantite`, pas de `ligne.qty`) |
| E28 | rattachement adhésion / billets caisse | `laboutik/views.py` l.6285-6318, l.6487-6588, l.8472-8533, ~l.9574-9593, ~l.10160-10179 | `pricesold.productsold.product.uuid` ; FK posée sur **la dernière** part (l.6289, l.6491) ou **la première** (l.8477) | B : « FK sur une seule part » = | = | ✎ une ligne |
| E29 | contribution crowds | `crowds/views.py` ~l.137-170 ; `ApiBillet/views.py` l.1255-1287 | `ligne_article.status` | D ✎ | = | = |

**Déclenchements « une fois par ligne » : ce que la fusion de H change.**
Tous les déclencheurs (E4-E8) ne concernent que des lignes **en ligne ou admin**, qui ne
sont jamais coupées en parts. Les lignes coupées (caisse, tireuse, QR/NFC) sont créées
`VALID` et ne déclenchent rien, **sauf** l'envoi QR/NFC à l'ancien LaBoutik (un envoi par
part aujourd'hui, `views.py` l.2053, l.2324) : G lit le moyen dans le règlement (T10),
toujours un envoi par ligne, donc deux envois pour deux monnaies. La fusion de H change donc **uniquement**
des montants d'avoirs et de factures caisse (E14, E16, E25 : aujourd'hui calculés sur la
part qui porte la FK — c'est un bug actuel que H corrige).

---

## 4. Parcours : séquence des statuts et ce que doit être la `Vente`

Notation : `Ligne`, `Pmt` (Paiement_stripe), `Resa`, `Billet`, `Adh`, `Bk` (Booking),
`Cmd` (Commande). « → » = transition ; les effets entre crochets.
`EN_ATT` / `REGLEE` / `ANNUL` = `Vente.statut`.

### P1 — Billets en ligne, Stripe accepté (réservation directe ou panier)

| Étape | Objets existants | Vente attendue |
|---|---|---|
| Checkout créé | `Ligne O → U` (update) ; `Pmt N → W` ; `Resa R` (panier) ou `R → U` (direct) ; `Billet C`/`N` ; `Cmd DRAFT → PENDING` | `EN_ATT`, sans numéro, 0 règlement ; `Pmt.vente` et `Cmd.vente` posées |
| Retour ou webhook `paid` | `Pmt W → P` → `Ligne U → P → V` [`send_sale_to_laboutik` on_commit] → `Resa → P` [`webhook_reservation`, `Billet → K`, `ticket_celery_mailer`] ; dernière ligne `V` → `Pmt → V` (imbriqué) → `Cmd → PAID` | `REGLEE`, numérotée, 1 règlement `SN` = `amount_total` (écart éventuel D26). **Encaissée à la fin de `set_ligne_article_paid`, donc après `Cmd PAID`** |
| Mail parti (Celery) | `Resa P → V` [`set_paiement_valid` : rien, déjà `V`] ou `PN` / `PE` [`traitement_en_cours=False`] | inchangée |
| Rejeu (F5, webhook) | `update_checkout_status` sort tôt si `V` ou `traitement_en_cours` ; sinon `P → P` rejoue `set_ligne_article_paid` | inchangée (garde `REGLEE` d'abord, fiche D §2.2) |

### P2 — Panier mixte (billets + adhésion + ressource), Stripe accepté

Comme P1, plus : `Adh WP → A` (ou `O`), `deadline` [facture par e-mail, ghost/brevo,
récompense Fedow on_commit, `send_sale_to_laboutik` on_commit, `webhook_membership`
on_commit] ; `Bk WP → PA`. **Une** vente, **un** règlement (R5). Si le panier contient une
ligne sans déclencheur (don), `Pmt` reste `P` et `Cmd PENDING` jusqu'au mail des billets :
la vente est pourtant `REGLEE` (l'argent est reçu). Écart normal, à documenter.

### P3 — Adhésion SEPA : en attente, puis accepté ou refusé

| Étape | Objets existants | Vente attendue |
|---|---|---|
| Checkout `complete`, `unpaid` | `Pmt → W` ; `Ligne.payment_method → SP` (update) ; `Adh AV → PP` (si validation manuelle) ; webhook : e-mail « SEPA en attente » (lu sur `payment_method` de la 1ʳᵉ ligne) | `EN_ATT` |
| Relecture après `expires_at` (24 h) mais avant le prélèvement | `Pmt W → E` (`update_checkout_status` l.3582-3586) | `EN_ATT`, inchangée (`EXPIRE` n'annule pas la vente : le prélèvement est toujours en cours) |
| `async_payment_succeeded` | `Pmt W → P` (ou `E → P`) → comme P2 | `REGLEE`, règlement **`SP`** (moyen lu dans `Paiement_stripe.moyen`) |
| `async_payment_failed` | `Pmt → F` (**aucune transition**) ; `Ligne → D` (update) ; `Adh PP → AV` ; e-mail « paiement refusé » | **non décrit** (T5) : doit être `ANNUL`. Sinon `EN_ATT` pour toujours |

### P4 — Session expirée, puis paiement tardif

`EXPIRE` n'est posé **que** si quelqu'un relit la session après `expires_at` (retour
navigateur, rejeu). Aucun webhook `checkout.session.expired` n'est traité. Un panier
abandonné garde donc `Pmt W` et sa vente `EN_ATT` **indéfiniment** (T6).
Si `Pmt W → E` : vente inchangée, `EN_ATT`. `E → P` (cas réel : SEPA de P3) : `REGLEE`,
numéro pris **à ce moment** (plus grand que des ventes faites entre-temps : normal).
`ANNUL` seulement sur `Pmt W → C` (`CANCELED`) et SEPA refusé, sans retour arrière.

### P5 — Remboursement Stripe total ou partiel (annulation par l'utilisateur ou l'admin)

| Étape | Objets existants | Vente attendue |
|---|---|---|
| Un billet sur trois | `Stripe.Refund(amount×1)` ; `Pmt → H` ; nouvelle `Ligne O → R` (qty −1) [`send_refund_to_laboutik`] ; `Billet → R` | vente d'origine inchangée `REGLEE` ; **nouvelle vente `AVOIR` `REGLEE`**, `vente_liee` = origine, règlement `SN` = −montant du refund, `reference_externe` = id |
| Le reste | idem ; `is_fully_refunded()` → `Pmt → R` ; `Resa → C` | une **deuxième** vente `AVOIR` |

### P6 — Annulation de réservation payée hors Stripe (admin espèces, caisse, API « ailleurs »)

`_creer_avoir` : `Ligne O → N` [`send_refund_to_laboutik`] ; billets `R` ; `Resa → C`.
**Par l'admin** : vente `AVOIR` liée, règlement « Remboursé par » (D27) ; billet
entièrement offert (D32) : un seul règlement `FREE −X`, pas de champ. **Par
l'utilisateur** (D31) : réservation et billets `CANCELED`, **aucun avoir, aucune vente**
(`cancel_and_refund_resa` reçoit `moyen_rembourse=None`). Réservation vendue en caisse
et payée en cascade : aujourd'hui l'avoir porte sur la **part** qui a la FK (quantité
fractionnaire) ; après H, sur l'article entier.

### P7 — Annulation d'adhésion (admin)

`Adh → AC` ; résiliation Stripe éventuelle ; **aujourd'hui** avoirs de toutes les lignes
payées (achat + renouvellements) `O → N` ; **après D (D30)** : un seul avoir, pour le
**dernier paiement**. Vente : une `AVOIR` liée à la vente d'origine de ce paiement. Ligne
hors Stripe : « Remboursé par » ; ligne Stripe (D27) : aucun appel Stripe, règlement
Stripe négatif sans `reference_externe`, message à l'admin.

### P8 — Avoir émis dans l'admin

`Ligne O → N` [`send_refund_to_laboutik`] ; aucun autre statut ne bouge (le paiement
Stripe non plus). Vente `AVOIR` liée ; hors Stripe : « Remboursé par » ; payée par Stripe
(D27) : aucun appel Stripe, règlement Stripe négatif sans `reference_externe` (Z : « à
faire à la main »), message à l'admin ; article entièrement offert : `FREE −X` seul.

### P9 — Vente en caisse (espèces, CB, NFC, complément, 2ᵉ carte, recharge, consigne)

Lignes créées `VALID` (aucun déclencheur) ; stock ; adhésion `LABOUTIK` + `deadline`
[`webhook_membership`] ; billets : `Resa V`, `Billet K` [mail + webhook **après** l'`atomic`].
**Pas** d'envoi à l'ancien LaBoutik, **pas** de facture d'adhésion, **pas** de récompense
Fedow (différence volontaire ou non avec l'admin : à figer par un test, §6).
Vente : `REGLEE` dans la **même** `atomic` que les lignes (fiche B). Échec d'égalité après
un débit legacy : incident journalisé, aucune vente (fiche B §1).

### P10 — QR / NFC en ligne

Demande : `Ligne O` (`QRCODE_MA`). Paiement : `O → U` (un seul gagnant), Fedow, puis
suppression et recréation `VALID` par monnaie [`send_sale_to_laboutik` par part, e-mails].
Échec Fedow : `U → D`. Vente (fiche C) : aucune tant que le débit n'est pas fait ; `REGLEE`
créée dans l'`atomic` de la recréation ; échec → pas de vente, ligne `D`.
La demande abandonnée reste `O` sans vente (normal).

### P11 — Tireuse

Lignes `VALID` par part, sans déclencheur. Vente `REGLEE` (fiche C).

### P12 — Commande de table

`CommandeSauvegarde OP → SV → PA` (articles `SERVI`, table `LIBRE`) ; paiement par
`_creer_lignes_articles` ou `_payer_par_nfc` dans une `atomic` extérieure. Vente `REGLEE`,
`CommandeSauvegarde.vente` posée. Clôture : `OP → AN` et tables libérées **par le bouton
de clôture actuel** (T11). Une commande annulée n'a jamais eu de vente : rien à faire.

### P13 — Recharge cadeau API v2 : échec puis nouvel essai

| Étape | Ligne | Vente |
|---|---|---|
| 1ʳᵉ requête | `O` (409 pour une requête concurrente) | `EN_ATT` |
| Fedow en erreur | `O → D` (update) | `EN_ATT`, inchangée (sans numéro, sans effet) |
| Nouvel essai, même clé | `D → O` (update), Fedow | `EN_ATT`, inchangée |
| Succès | `O → V` (update) | `REGLEE`, règlement `FREE`, article offert `OFFRIR` |
| Rejeu après succès | 208 rebâti depuis la ligne (`metadata`, `asset`) | inchangée |
| Processus tué entre `O` et Fedow | `O` pour toujours (409 à chaque rejeu) | `EN_ATT` pour toujours (comportement actuel conservé) |

### P14 — Réservation gratuite

API v2 : `Ligne F` (création) ; `Resa F` ou `FA` [si `FA` : billets, mail]. À la
validation de l'e-mail : `F → FA` [`reservation_paid`] ou, si l'événement est complet,
`Resa → C` et billets `N` (`activator_free_reservation`). Panier / billet à 0 € :
`Ligne → P → V` (`FREE`, `trigger_B`). Booking gratuit : `Ligne V`, `Bk FR/FU`.
Vente : `REGLEE`, total 0, aucun règlement, **numérotée à la création** — y compris pour
une réservation qui sera annulée faute de place (T16).

### P15 — Renouvellement d'abonnement (`invoice.paid`)

`Ligne O → U` ; `Pmt W` (`INVOICE`) → `P` → `trigger_A` [`AUTO`, `current_iteration + 1`,
éventuellement `Subscription.modify(cancel_at_period_end)`, facture, récompense] ; garde
`ADMIN_CANCELED` : la fiche n'est pas réactivée, mais la ligne passe `V` (argent reçu).
Vente : `EN_ATT` à la création de la ligne, `REGLEE` au passage `PAID`, montant
`invoice.amount_paid` (0 → aucun règlement, écart). Adhésion annulée par l'admin et
prélevée quand même : vente `REGLEE` **correcte** (l'argent est reçu), l'alerte existe déjà.

### P16 — Adhésion créée ou payée dans l'admin ; adhésion gratuite API

Admin : `post_save` (création `D`) ou `ajouter_paiement` : `Ligne O → P → V` [`trigger_A`,
tâches on_commit, `webhook_membership`]. API gratuite : ligne créée `P` puis `P → P`.
Vente : `REGLEE`, encaissée **après** la transition de la ligne (le déclencheur ne fait
plus d'HTTP : T15). Montant non nul offert : part offerte totale + règlement `FREE`.

### P17 — Crowds

Stripe : `Ligne O → U → P` (catégorie `N` : pas de déclencheur) ; puis vue de retour ou
webhook : contribution `paid`, `Ligne P → V`, `Pmt → V`, e-mail. Vente `REGLEE` au passage
`PAID`. « Marquer payée » par l'admin : **aucune ligne, aucune vente** (T17).

---

## 5. Trous de la spec (état des fiches au 2026-09-28)

> **Décisions du mainteneur (2026-09-28)** : T7 → D30, T8 → D27 (pas d'appel Stripe), T9 → D31,
> T11 → D29, T12 → D32, T13 → D33 (autre chantier). Elles priment sur les « corrections
> proposées » ci-dessous. Les fiches font foi.

Déjà traités par les fiches au moment de la lecture (non repris ici) : rejeu `PAID → PAID`
qui doublerait le règlement (D §2.2 : garde `REGLEE` d'abord) ; ligne d'écart sans
`paiement_stripe` ; réouverture de la recharge API v2 (A §3) ; producteurs qui gardent leur
transition (A §3) ; envoi QR à deux monnaies (G) ; avoir admin d'une ligne Stripe
tranché : D27, pas d’appel Stripe (D §4).

| # | Gravité | Trou | Correction proposée |
|---|---|---|---|
| T1 | **BLOQUANT** (H) | **SEPA** : le moyen `SP` n'existe **que** sur `LigneArticle.payment_method` (écrit `models.py` l.3557, l.3577 ; lu par le webhook l.1230 pour l'e-mail « SEPA en attente » ; lu par D §2.2 pour `Reglement.moyen`). H retire le champ sans le déplacer : e-mail SEPA plus jamais envoyé, règlement classé `SN` au lieu de `SP` (mauvais compte en E). | Ajouter en A un champ `Paiement_stripe.moyen` (`SN`/`SP`/`SR`), posé par `update_checkout_status` et `new_entry_from_stripe_subscription_invoice` ; le webhook et `encaisser_vente_stripe` le lisent. Test : `test_sepa_en_attente_envoie_le_mail_sans_payment_method_sur_la_ligne`. |
| T2 | **BLOQUANT** (H) | **Anti-rejeu QR/NFC** : trois requêtes filtrent sur `payment_method = QRCODE_MA` (`validators.py` l.1381, `views.py` l.1940, l.2230). H ne les liste pas dans « À adapter » : `FieldError`, plus aucun paiement QR/NFC. | Filtrer sur `sale_origin = QRCODE_MA` (posé à la demande, `views.py` l.1884, et gardé en H par R4) ou sur la catégorie produit `Q`. À écrire dans H §3 et C. |
| T3 | **BLOQUANT** (H) | **Remboursements vers l'ancien LaBoutik** : `send_refund_to_laboutik` (déclenché par chaque avoir et remboursement, `signals.py` l.144-160) utilise `LigneArticleSerializer`, qui liste `payment_method`, `asset`, `wallet`. G ne réécrit que l'envoi des ventes. Après H : exception dans la tâche Celery, ancien LaBoutik jamais prévenu, sans erreur visible. | G : même forme que l'envoi des ventes (moyen lu dans le règlement de la vente `AVOIR`). Test : `test_envoi_remboursement_ancien_laboutik_charge_utile_inchangee`. |
| T4 | IMPORTANT (D) | **Erreur dans le point d'encaissement Stripe** : `encaisser_vente_stripe` tourne **dans le `pre_save`** de `Paiement_stripe`, en autocommit, **après** que les lignes, réservations, billets, e-mails (`.delay` immédiats) et parfois `Commande PAID` (sauvegarde imbriquée, §2.2) sont déjà écrits. D §2.2 prévoit « lever une erreur explicite » si le montant manque ; une `EgaliteDeVenteRompue` ou une erreur de verrou ferait pareil. Résultat : le client a payé, ses billets partent, mais le paiement reste `PENDING` ; le webhook reçoit une 500, Stripe rejoue, `reservation_paid` et les tâches repartent. | Ne **jamais** laisser sortir une exception du `pre_save` : `try/except` autour de `encaisser_vente_stripe`, `logger.error` (Sentry), vente laissée `EN_ATTENTE` ; le rejeu = `paiement_stripe.save()` (`P → P`), action admin « Rejouer l'encaissement » en fiche G. Test : `test_erreur_d_encaissement_ne_bloque_pas_le_paiement`. |
| T5 | IMPORTANT (D) | **SEPA refusé** : `async_payment_failed` passe le paiement `FAILED` (aucune transition dans la table, `expire_paiement_stripe` n'est pas appelé) et les lignes `FAILED` par `.update()`. La vente n'est jamais annulée. | Dans la branche `async_payment_failed` (`ApiBillet/views.py` ~l.1312) : `annuler_vente(paiement.vente)` explicite. Test D : `test_sepa_refuse_vente_annulee`. |
| T6 | IMPORTANT (D) | **Expiration** : D16 promet `ANNULEE` à l'expiration, mais `EXPIRE` n'est posé que si la session est **relue** après `expires_at`. Les paniers abandonnés restent `EN_ATTENTE` pour toujours. Inversement, un SEPA soumis puis relu après 24 h passe `EXPIRE` → vente `ANNULEE` alors que le prélèvement est en cours (elle sera rouverte). | Écrit dans D16 : « `EN_ATTENTE` = paiement pas encore constaté, abandon et `EXPIRE` compris ; `ANNULEE` seulement sur `CANCELED` / SEPA refusé, sans retour arrière ». Plus de réouverture. Aucun numéro n'est consommé, donc pas de conséquence comptable. Option (nouveau comportement, hors chantier) : traiter `checkout.session.expired`. |
| T7 | IMPORTANT (D) | **Avoirs sur plusieurs ventes d'origine** : l'annulation d'adhésion crée un avoir pour **chaque** ligne payée (achat + tous les renouvellements, `views.py` l.4595-4602) ; une réservation peut avoir des lignes Stripe et des lignes admin ; `vente_liee` est une seule FK. La spec ne dit pas combien de ventes `AVOIR` écrire. | Règle : **une vente `AVOIR` par vente d'origine**, par action. Test : `test_annulation_adhesion_deux_renouvellements_deux_ventes_avoir`. (Question métier à poser au passage : annuler une adhésion doit-il vraiment « rembourser » les années passées ?) |
| T8 | IMPORTANT (tronc D27, D) | **Seul vrai changement de logique métier** : aujourd'hui **aucun** avoir de l'admin n'appelle Stripe (`emettre_avoir`, annulation d'adhésion) ; l'avoir recopie le moyen `SN`. D27 prévoit un remboursement Stripe automatique. D §4 le signale pour `emettre_avoir` mais **pas** pour l'annulation d'adhésion (ligne 1 du tableau : « moyen choisi » : on écrirait un remboursement en espèces qui n'a pas eu lieu). | Décision du mainteneur, la même pour les deux écrans : (a) garder le comportement actuel (avoir comptable, pas d'appel Stripe, règlement `SN` négatif marqué « à rembourser à la main ») ou (b) vrai remboursement. Tant que ce n'est pas tranché, le test de caractérisation §6 `test_avoir_admin_sur_ligne_stripe_n_appelle_pas_stripe` fige (a). |
| T9 | IMPORTANT (D) | **Annulation par l'utilisateur** d'une réservation ou d'un booking payé hors Stripe (`views.py` ~l.1413, ~l.1434 ; `booking/views.py` ~l.839) : aucun écran, donc pas de « Remboursé par » (D27). | Règle par défaut : le moyen d'origine s'il est `CA/CC/CH/TR`, sinon `UNKNOWN` (compte d'attente 471, fiche E) + alerte. Test : `test_annulation_par_l_utilisateur_vente_admin_especes_avoir_especes`. |
| T10 | IMPORTANT (G) | **Ancien LaBoutik, « un envoi par règlement »** : aujourd'hui une vente en ligne envoie **un message par ligne** billet / adhésion (`trigger_A/B`), avec son `pricesold`, son `amount`, sa `qty` ; les lignes booking et la caisse n'envoient rien ; l'anti-doublon est `LigneArticle.sended_to_laboutik`. Un panier « 2 billets + 1 adhésion » payé par un seul règlement Stripe deviendrait **un** message (quel `pricesold` ?), et les déclencheurs, qui restent par ligne, l'enverraient N fois. | Garder « un envoi par ligne » ; le moyen, l'`asset` et le `wallet` se lisent dans **le** règlement de la vente quand il n'y en a qu'un ; une vente à plusieurs règlements (QR/NFC seulement) envoie un message par règlement, comme les parts d'aujourd'hui. Test G#18 étendu : panier 2 billets + adhésion → 3 messages, charges identiques à aujourd'hui. |
| T11 | IMPORTANT (F/G) | **Clôture et commandes de table** : le bouton de clôture actuel libère les tables et passe les commandes `OPEN` en `CANCEL` (`laboutik/views.py` ~l.2727-2737). G remplace le bouton (« crée la J unique ») et D28 ajoute un filet à 4 h, sans rien dire de cet effet. | Écrire en G : le nouveau bouton garde ces deux effets ; décider si le filet de 4 h les fait aussi (aujourd'hui l'auto-clôture de `laboutik/tasks.py` ne les fait pas). Test de caractérisation §6. |
| T12 | MINEUR (tronc §2, D) | **Billet offert dans l'admin** : le code écrit `amount = 0` (`admin_tenant.py` ~l.3092-3095). La règle « offert à montant non nul » ne s'applique donc jamais ici ; pour tracer l'offert, il faudrait écrire `amount = prix`, ce qui change les anciens lecteurs (contraire à « aucun ancien lecteur ne change » de D). | Décider : garder 0 (vente gratuite, pas de trace d'offert) ou passer au prix **en H seulement**. |
| T13 | MINEUR (existant) | **Rejeu `PAID → PAID`** : `set_ligne_article_paid` repasse `PAID` **toute** ligne du paiement non `VALID` (`signals.py` l.42), y compris les lignes négatives `REFUNDED` / `CREDIT_NOTE` qui gardent le même `paiement_stripe` (R5). Arrive si le paiement est resté `PAID` (panier avec don, ou `error_in_mail`) et qu'un avoir admin a été fait. Leur vente `AVOIR` resterait `REGLEE`, leurs statuts diraient `PAID`. | Hors chantier (bug actuel) ; le figer par un test de caractérisation, et le signaler au mainteneur. Correctif simple possible plus tard : `exclude(status__in=[VALID, REFUNDED, CREDIT_NOTE, FAILED])`. |
| T14 | MINEUR (B) | **FK adhésion / réservation en caisse** : posée sur la **dernière** part (`laboutik/views.py` l.6289, l.6491) ou la **première** (l.8477, ~l.9580, ~l.10166) selon le chemin. B dit « une seule part » sans dire laquelle. | Ne rien changer en B (écrire « comme aujourd'hui ») ; H fusionne. Noter au CHANGELOG de H que la facture d'adhésion caisse et l'avoir d'un billet caisse portent désormais sur l'article entier. |
| T15 | MINEUR (A, D) | **`trigger_A` ne fait plus d'appel HTTP à Fedow** (`triggers.py` l.12, l.289-300 ; la récompense part en Celery `on_commit`). A §4 et D §3 citent « signals.py ~l.502, PIEGES 13.2 » (13.2 parle de la création d'un **produit**). Le test D#12 et sa mutation ne peuvent rien détecter. | Reformuler : « encaisser après la transition de la ligne, dans la même `atomic` admin ». Remplacer D#12 par un test d'ordre : la vente est `REGLEE` et la ligne `VALID` à la sortie de `ajouter_paiement`. |
| T16 | MINEUR (D) | **Réservation gratuite** : vente numérotée à la création, alors que la réservation peut rester `FREERES` (e-mail jamais validé) ou passer `CANCELED` faute de place (`signals.py` l.252-272). « Un ticket n'existe qu'une fois réglé » (D16) devient ambigu. | Accepter (montant 0, aucun effet comptable) et l'écrire dans D. |
| T17 | MINEUR (tronc §9) | **Crowds « marquer payée »** (`admin_paid`) n'écrit ni ligne ni vente : argent reçu ailleurs, non enregistré. D1 dit « toutes les ventes ». | Ajouter au §9 du tronc : « hors chantier, comportement inchangé ». |
| T18 | MINEUR (H) | **Rejeu 208 de la recharge API v2** : lit `ligne_article.asset` (`api_v2/views.py` ~l.931). | H « À adapter » : lire `Vente.unite`. |
| T19 | MINEUR (H) | **TVA par défaut** : `_compute_default_vat` lit `payment_method` (`models.py` l.3860-3861) à chaque création. | H « À adapter » : retirer la règle (tous les producteurs passent par `ajouter_article`) ou la baser sur le marqueur. |
| T20 | MINEUR (H) | **Copies de `payment_method` / `asset` / `wallet`** dans les producteurs d'avoirs et de remboursements (`PaiementStripe/utils.py` l.93-95 ; `models.py` l.2986-2988 ; `booking/models.py` l.633-635 ; `views.py` l.4678-4680 ; `admin_tenant.py` ~l.2091-2093). | Les lister nommément en H : `TypeError` sinon, sur le chemin des annulations. |
| T21 | MINEUR (G/H) | **Décisions prises sur `amount × qty`** hors de G : `Booking.to_pay` (Stripe ou gratuit, `booking_engine.py` ~l.722), `TicketCreator` (~l.289), montant envoyé à `stripe.Refund` (`utils.py` l.39-44). Le test de garde H#10 les fera tomber ; la réécriture doit garder la **même décision**. | Les ajouter au tableau des lecteurs de G, avec un test par décision (§6). |
| T22 | MINEUR (A) | **Numéros de ligne** : plusieurs repères des fiches sont décalés (`_executer_avec_cle_idempotence` l.4611 et non ~4666 ; `_payer_par_nfc` l.7902 et non ~8457 ; `_executer_paiement_complementaire` l.9139 et non ~9562). | Relire au démarrage de chaque fiche (déjà la règle). |

---

## 6. Filet de sécurité : tests de caractérisation, à écrire **avant** la fiche B

### 6.1 Principe

- Un test de caractérisation **fige le comportement d'aujourd'hui**. Il est **vert** sur
  le code actuel (pas de « vu rouge » ; la preuve de sa force est la **mutation**, §6.4).
- Il n'asserte **que des effets observables** : statuts finaux, objets créés (billets,
  adhésions, lignes négatives), **noms et arguments des tâches Celery demandées**,
  appels Stripe et Fedow simulés, **charge utile** envoyée à l'ancien LaBoutik. Jamais
  un champ que H retire (`payment_method`, `asset`…) lu directement sur la ligne : la
  charge utile de l'ancien LaBoutik est le contrat, pas la colonne.
- Conséquence : ces tests restent verts **sans modification** de B à H, sauf là où une
  fiche change volontairement un comportement (colonne « Peut changer » ci-dessous) ; ce
  changement est alors fait **dans cette fiche**, le test est modifié dans le même
  commit, et la raison est écrite au CHANGELOG.

Outillage existant à réutiliser (rien à inventer) :

- `tests/pytest/fabriques_panier.py` : `taches_celery_enregistrees()`, `noms_des_taches()`,
  `catalogue_stripe_simule()`, `creer_utilisateur`, `creer_adhesion`,
  `creer_evenement_avec_tarif`, `creer_ressource_avec_tarif`, `client_connecte`,
  `requete_avec_session`, `configuration_modifiee` ;
- `tests/pytest/fabriques_reservation.py` : `reservation_payee`, `vente_admin_especes` ;
- fixture `mock_stripe` (`tests/pytest/conftest.py` l.374-415) ; `stripe.Refund.create`
  à patcher en plus ;
- `django_capture_on_commit_callbacks(execute=True)` pour voir les tâches `on_commit`
  (PIEGES 13.1, 13.14) ; `patch("BaseBillet.signals.AssetFedow")` pour créer un produit
  adhésion (PIEGES 13.2) ; `tenant_context`, jamais `schema_context` (PIEGES 13.11) ;
- marque `django_db` (rollback) : aucun de ces tests ne lit la numérotation ni la chaîne.

Un petit assistant commun, dans le premier fichier : `etat_metier(...)` qui rend un
dictionnaire des statuts utiles (paiement, lignes triées, réservation, billets, adhésion
et `deadline is not None`, booking, commande) + la liste des noms de tâches. Chaque test
compare à un dictionnaire attendu écrit en clair.

### 6.2 Les fichiers et les tests

**`tests/pytest/test_caracterisation_en_ligne.py`** (Stripe simulé)

**22 tests** : ceux qui portent une des 11 mutations (§6.4), ceux qui doivent changer
volontairement (fiche A′ §4), et les parcours Stripe P1, P3, P5, P15. Les autres parcours
sont déjà couverts par `test_commande_service.py`, `test_qrcodescanpay_flux_complet.py`
et les tests de `controlvanne`.

| Test | Fige |
|---|---|
| `test_billets_directs_payes_statuts_et_taches` | P1 : `Pmt V`, lignes `V`, `Resa P`, billets `K`, tâches `send_sale_to_laboutik` ×N lignes, `webhook_reservation`, `ticket_celery_mailer` |
| `test_panier_mixte_paye_une_seule_fois` | P2 (reprend `test_commande_service.py` l.439) + charges utiles `LigneArticleSerializer` des lignes billet et adhésion (moyen `SN`, `amount`, `qty`) |
| `test_paiement_reste_paye_puis_rejeu_repasse_les_avoirs_en_paye` | T13 : figer le bug actuel (ligne `CREDIT_NOTE` → `P` après `P → P`) |
| `test_adhesion_en_ligne_payee` | P2 adhésion seule : `Adh A`, `deadline`, `contribution_value = pricesold.prix`, tâches `send_membership_invoice_to_email`, récompense et envoi LaBoutik **on_commit** |
| `test_sepa_soumis_statuts_et_mail_en_attente` | P3 : `Pmt W`, `Adh PP`, tâche `send_membership_sepa_pending_user` (T1) |
| `test_sepa_refuse_lignes_en_echec_adhesion_rearmee` | P3 : `Pmt F`, lignes `D`, `Adh AV`, tâche `send_payment_refused_user` (T5) |
| `test_renouvellement_abonnement_iteration_et_statut_auto` | P15 : nouvelle ligne `V`, `Adh O`, `current_iteration + 1`, `last_stripe_invoice` |

**`tests/pytest/test_caracterisation_annulations.py`**

| Test | Fige |
|---|---|
| `test_annuler_un_billet_stripe_rembourse_un_billet` | P5 : `Refund.create(amount=…)` appelé une fois avec le prix d'**un** billet, `Pmt H`, ligne `R` de qty −1, tâche `send_refund_to_laboutik` et sa charge utile |
| `test_annulation_utilisateur_reservation_admin_especes_cree_un_avoir` | P6 : avoir `N`, moyen `CA` dans la charge utile `send_refund_to_laboutik` ; **change en D** (D31) |
| `test_annuler_un_billet_caisse_offert_cree_un_avoir` | P6 : billet `FREE` à prix non nul → avoir créé (garde `total_paid`) ; **change en G** (`total_paid` sur `total_ttc`, validé le 2026-09-29) |
| `test_annulation_adhesion_avoirs_de_tous_les_renouvellements` | P7 : 1 achat + 2 renouvellements → 3 avoirs, `Adh AC` ; **change en D** (D30) |
| `test_avoirs_admin_et_annulation_adhesion_n_appellent_pas_stripe` | P7/P8 (T8, D27) : `Refund.create` jamais appelé par `emettre_avoir` ni par `cancel` ; reste vert |

**`tests/pytest/test_caracterisation_admin_api.py`**

| Test | Fige |
|---|---|
| `test_adhesion_creee_dans_l_admin_passe_par_trigger_a` | P16 : ligne `V`, `deadline`, tâches (facture, récompense, LaBoutik on_commit, `webhook_membership`) |
| `test_billets_vendus_dans_l_admin_offert_au_prix_part_offerte_totale` | P16/T12 : billet offert écrit au prix, part offerte totale, règlement FREE (D32, depuis D-2b) ; tâche `ticket_celery_mailer`, plus d'envoi `send_sale_to_laboutik` |
| `test_recharge_api_v2_echec_puis_nouvel_essai_meme_ligne` | P13 : `O → D → O → V`, une seule ligne, rejeu 208 identique |
| `test_decision_stripe_ou_gratuit_billets_et_booking` | T21 : total > 0 → checkout ; total 0 → validation gratuite (TicketCreator et `Booking.to_pay`) |

**`tests/pytest/test_caracterisation_caisse.py`**

| Test | Fige |
|---|---|
| `test_vente_caisse_adhesion_sans_facture_ni_envoi_laboutik` | P9 : `Adh L`, `deadline`, **aucune** tâche `send_membership_invoice_to_email` / `send_sale_to_laboutik` / récompense |
| `test_rejeu_meme_cle_caisse_rien_en_double` | E23 |
| `test_paiement_table_nfc_libere_la_table` | P12, chemin NFC (`_payer_par_nfc` puis `payer_commande` lit le HTML) : `PA`, articles `SERVI`, table `LIBRE` |
| `test_cloture_annule_les_commandes_ouvertes_et_libere_les_tables` | T11 (D29) : `OP → AN`, tables `LIBRE`, `SV` intact ; reste vert en G |

**QR / NFC et tireuse** : déjà couverts par `tests/pytest/test_qrcodescanpay_flux_complet.py`
(en cours de modification : chantier 04-F-1) et les tests de `controlvanne`. À compléter,
dans `tests/pytest/test_caracterisation_qr.py` :
`test_qr_deux_monnaies_deux_envois_laboutik_et_deux_mails` (P10, charges utiles `asset`
et `amount` par part) et `test_qr_echec_fedow_ligne_en_echec_rejeu_refuse` (P10, T2).

### 6.3 Qui doit les garder verts

| Fichier | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| `test_caracterisation_en_ligne.py` | vert, **sans modification** | idem | idem (seule la vente s'ajoute) | idem | idem | idem (charges LaBoutik identiques, T10) | idem (T1 corrigé) |
| `test_caracterisation_annulations.py` | idem | idem | idem **sauf** `…utilisateur…especes…` (D31) et `…tous_les_renouvellements` (D30) | idem | idem | idem **sauf** `…billet_caisse_offert…` (validé) | idem |
| `test_caracterisation_admin_api.py` | idem | idem | idem **sauf** `…offert_montant_zero` (D32) | idem | idem | idem | idem |
| `test_caracterisation_caisse.py` | idem **sauf** `…adhesion_sans_facture…` (B-0 : facture et récompense) | idem | idem | idem | idem | idem (D29 : le bouton garde ses effets) | idem |
| `test_caracterisation_qr.py` | idem | idem **sauf** `…deux_envois_laboutik…` (C : envoi legacy QR débranché) ; restructuration « réseau d'abord » | idem | idem | idem | idem | idem (T2 corrigé) |

### 6.4 Mutations (preuve que les tests voient quelque chose)

| Mutation (code actuel) | Doit faire tomber |
|---|---|
| `trigger_B` : retirer `self.ligne_article.status = VALID` | `test_billets_directs_payes_statuts_et_taches` |
| `set_ligne_article_paid` : ne plus ajouter les réservations de la `Commande` | `test_panier_mixte_paye_une_seule_fois` |
| `trigger_A` : `send_membership_invoice_to_email` retiré | `test_adhesion_en_ligne_payee`, `test_adhesion_creee_dans_l_admin_passe_par_trigger_a` |
| webhook SEPA : condition `payment_method == SP` inversée | `test_sepa_soumis_statuts_et_mail_en_attente` |
| `async_payment_failed` : ne plus réarmer les adhésions | `test_sepa_refuse_lignes_en_echec_adhesion_rearmee` |
| `partial_refund_payment` : `specified_quantity` ignoré | `test_annuler_un_billet_stripe_rembourse_un_billet` |
| annulation d'adhésion : ne créer que le premier avoir | `test_annulation_adhesion_avoirs_de_tous_les_renouvellements` (jusqu'à D ; ensuite le test D30 de la fiche D) |
| `_creer_ou_renouveler_adhesion` : `status = ONCE` | `test_vente_caisse_adhesion_sans_facture_ni_envoi_laboutik` |
| clôture : retirer l'annulation des commandes ouvertes | `test_cloture_annule_les_commandes_ouvertes_et_libere_les_tables` |
| recharge API v2 : créer une nouvelle ligne au lieu de réutiliser la `FAILED` | `test_recharge_api_v2_echec_puis_nouvel_essai_meme_ligne` |
| `LigneArticleSerializer` : retirer `asset` | `test_qr_deux_monnaies_deux_envois_laboutik_et_deux_mails` (jusqu'à C, qui débranche l'envoi QR ; ensuite le test 18 de la fiche G) |

Effort estimé : **1,5 j** (une session par fichier, sauf QR). Fiche « 05-A′ », livrée
**avant A** ; chaque test est rejoué en fin de chaque session.
