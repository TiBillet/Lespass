# KIOSK — Spec de conception (2026-07-06)

App `kiosk` : borne de rechargement cashless en libre-service sur terminal
Android (Cordova), avec TPE Stripe physique (BBPOS WisePOS E) et crédit de la
carte NFC **côté Fedow distant** (V1 legacy, via webhook Stripe).

Source du copier-coller : `../LaBoutik` (branche `main-tpe`), app `htmxview` +
modèles `APIcashless` (`Terminal`, `PaymentsIntent`, `Location`).

> **Cadre : coexistence V1.** Fedow reste un service HTTP distant (`fedow_connect`).
> Aucune dépendance à `fedow_core`. Le crédit monétaire n'est jamais stocké côté
> Lespass — c'est Fedow qui crédite après vérification de la signature reçue dans
> le webhook Stripe.

---

## 1. Objectif

Un terminal Android (Sunmi + TPE Stripe) appairé en **rôle Kiosque (`KI`)** ouvre
directement le front kiosk. Parcours client :

1. Choix du montant (boutons additifs +1/+5/+10/+20/+50 €).
2. Scan de la carte NFC TiBillet (lecteur Sunmi via plugin Cordova).
3. Paiement CB sur le TPE Stripe.
4. Fedow crédite la carte (webhook Stripe → vérif signature → crédit).
5. Écran succès / annulation, retour accueil.

Mode DEMO : simulateur de TPE (pas de hardware).

**Non inclus (YAGNI)** : le sous-parcours `link` (lier une carte à un compte) —
c'était un TODO non implémenté dans LaBoutik. On ne copie que la recharge.

---

## 2. Principe d'architecture

- App **`kiosk/`** dans **TENANT_APPS** (comme `laboutik`, `PaiementStripe`).
- **App autonome, distincte de `laboutik`.** Menu admin propre, module propre.
  Le kiosk grandira (gestion d'adhésions, etc.) → séparation justifiée dès le départ.
- **Même APK Cordova** que LaBoutik (`laboutik_client_android_v2`). Rien à
  rebuild : c'est l'appairage typé `KI` côté serveur qui décide de la destination.

---

## 3. Modèles (`kiosk/models.py`)

Copiés d'`APIcashless`, rebranchés sur les dépendances Lespass.

### `StripeLocation` (copié de `APIcashless.Location`)
Location Stripe Terminal, requise pour créer un reader. Absente de Lespass → copiée.
Singleton (django-solo) ou 1 par lieu. Clé Stripe via `RootConfiguration.get_solo().get_stripe_api()`.

### `Terminal`
TPE Stripe WisePOS.
- Champs : `id` (UUID PK), `name`, `registration_code`, `stripe_id`, `type`
  (`STRIPE_WISEPOS`), `archived`.
- `get_stripe_id()` : crée le reader Stripe (`stripe.terminal.Reader.create`) depuis
  `registration_code` + `StripeLocation`. Rebranché sur `RootConfiguration`.
- `status()` : interroge Stripe.

### `PaymentsIntent`
**Objet de pilotage du TPE + affichage, stocké localement.** Ce n'est PAS le crédit
Fedow — c'est l'état technique éphémère d'un paiement en cours.
- Champs : `id` (UUID PK), `amount` (centimes), `payment_intent_stripe_id`,
  FK `Terminal`, FK `CarteCashless` (**`QrcodeCashless`**, nullable), `datetime`,
  `status` (machine à états `R/P/A/S/C`).
- **Champ `pos` SUPPRIMÉ** (décision) : LaBoutik s'en servait pour tagger la vente ;
  inutile au flux Fedow, éviterait un couplage `kiosk → laboutik`.
- `send_to_terminal()` : crée le PaymentIntent Stripe (`card_present`, capture
  automatique) avec **metadata signées** `{fedow_place_uuid, tag_id}` puis
  `process_payment_intent` sur le reader.
  - Signature : `Configuration.get_private_key()` (clé RSA du lieu).
  - `fedow_place_uuid` : lu sur `FedowConfig` (pas `Configuration`).
- `get_from_stripe()` : rafraîchit le statut depuis Stripe. Inchangé (DEMO inclus).

**Pourquoi le PaymentsIntent est local et nécessaire** : le polling Celery et le
WebSocket relisent `payment_intent.status` en base (suivi spinner → succès/échec,
annulation, rejeu d'état à la reconnexion). Sans ce modèle, l'écran ne peut pas suivre.

---

## 4. Controllers (`kiosk/views.py`, `tasks.py`, `validators.py`)

### `KioskViewSet` (DRF `ViewSet`)
`SessionAuthentication` + `IsAuthenticated` + garde `terminal_role == KI`.
- `list` → `select_amount.html`.
- `check_request_card` (POST `tag_id`) → vérifie la carte via Fedow, affiche le montant.
- `refill_with_wisepos` (POST) → valide, crée `PaymentsIntent`, `send_to_terminal`,
  lance le polling Celery, rend `waiting_credit_card_terminal.html`.
- `cancel` (GET) → annule l'action reader + le PaymentIntent Stripe.

### `poll_payment_intent_status` (`kiosk/tasks.py`, Celery)
Copié tel quel : poll 1×/s pendant 120 s max, push WebSocket sur le room
(`= payment_intent_stripe_id`), écran final ou cancel sur timeout.

### `RefillWisePoseValidator` (`kiosk/validators.py`)
Rebranché sur `QrcodeCashless.CarteCashless` + `NFCcardFedow` (structure Lespass,
différente de LaBoutik). Montant → centimes.

---

## 5. WebSocket (`wsocket/`)

Ajouter `TerminalConsumer` dans `wsocket/consumers.py` + route
`ws/terminal/<pi_id>/` dans `wsocket/routing.py`. Copié de LaBoutik, avec le
**rejeu d'état à la (re)connexion** (relit le statut réel en base).

---

## 6. Front (`kiosk/templates/kiosk/` + `kiosk/static/kiosk/`)

Copie fidèle du front LaBoutik : `base.html`, `select_amount.html`,
`waiting_credit_card_terminal.html`, `success.html`, `cancel.html`,
`sweet_scan_button.html`, `main.js`, CSS (Bootstrap + SweetAlert + HTMX + WS).

Adaptations :
- URLs `/htmx/kiosk/` → `/kiosk/`.
- Path WebSocket → `ws/terminal/`.
- **Injection conditionnelle de `cordova.js`** selon `type_app` (comme
  `laboutik/base.html`) pour que le lecteur NFC Cordova fonctionne.

---

## 7. Admin Unfold (`kiosk/admin.py`)

Enregistré sur `staff_admin_site`. Conventions Unfold projet (skill `unfold`) :
`compressed_fields`/`warn_unsaved_form = True`, 4 `has_*_permission` =
`TenantAdminPermissionWithRequest`, helpers **hors classe**.

- `TerminalAdmin` : appairage TPE Stripe. Action Unfold « Créer le reader Stripe »
  (`get_stripe_id()`).
- `StripeLocationAdmin` : singleton (solo).
- `PaymentsIntentAdmin` : lecture seule (historique).

Menu admin **propre au kiosk**, séparé de LaBoutik.

---

## 8. Appairage / routing (branchement central)

- `discovery` **inchangé** : le claim `KI` crée déjà `TermUser(role=KI)` +
  `LaBoutikAPIKey`.
- **Modifier `LaBoutikAuthBridgeView`** (`laboutik/views.py`, fichier sensible) :
  après `login`, router selon `terminal_role` :
  - `KI` → `HttpResponseRedirect("/kiosk/?type_app=" + type_app)`
  - sinon → `/laboutik/caisse?type_app=...` (comportement actuel).
- `kiosk/urls.py` (router DRF) monté sur `/kiosk/` dans `urls_tenants.py`.

---

## 9. Module Groupware (`module_kiosk`)

- **Nouveau champ `module_kiosk`** (BooleanField) sur `Configuration` (comme les
  autres `module_*`).
- Section sidebar « Kiosk » conditionnelle sur `module_kiosk`.
- Carte d'activation dans le dashboard Unfold (pattern `MODULE_FIELDS` existant).

---

## 10. Réglages (`settings.py`, fichier sensible)

- Ajouter `'kiosk'` dans `TENANT_APPS`.
- **S'arrêter et demander** avant de toucher `settings.py` / `urls_tenants.py` /
  `asgi.py` (routing WS) — fichiers sensibles.

---

## 11. Points de branchement non-triviaux

| Dépendance LaBoutik | Équivalent Lespass | Action |
|---|---|---|
| `APIcashless.CarteCashless` | `QrcodeCashless.CarteCashless` | Rebrancher import ; **pas de `total_monnaie()`** → solde masqué ou via Fedow |
| `FedowAPI().NFCcard.retrieve` | `fedow_connect` `NFCcardFedow` (API différente) | Adapter l'appel de validation carte |
| `ConfigurationStripe.get_stripe_api()` | `RootConfiguration.get_solo().get_stripe_api()` | Rebrancher |
| `Configuration.fedow_place_uuid` | `FedowConfig.fedow_place_uuid` | Rebrancher |
| clés RSA `Configuration.get_private_key/public_key` | idem sur `BaseBillet.Configuration` | OK, existe |
| `APIcashless.Location` | absent | **Copier `StripeLocation`** |
| `Appareil.terminals` | `TermUser` / appareil Lespass | Vérifier le lien terminal↔appareil |
| injection `cordova.js` | `laboutik/base.html` (pattern existant) | Reproduire dans `kiosk/base.html` |

---

## 12. Résultat attendu

Terminal Android appairé `KI` → front kiosk → scan carte → montant → CB sur TPE →
Fedow crédite. Mode DEMO simule le TPE sans hardware. Le solde reste la vérité de
Fedow ; Lespass ne stocke que l'état technique du paiement (`PaymentsIntent`).

---

## Décisions actées (session 2026-07-06)

1. `PaymentsIntent` stocké localement (pilotage TPE), **champ `pos` supprimé**. Crédit = Fedow.
2. **Module `module_kiosk` à part**, app et menu admin distincts de LaBoutik.
3. Bridge `laboutik` modifié pour typer la redirection selon `terminal_role`.
4. Sous-parcours `link` : **ignoré** (YAGNI).
5. Fedow **distant** (coexistence V1), aucune dépendance `fedow_core`.
