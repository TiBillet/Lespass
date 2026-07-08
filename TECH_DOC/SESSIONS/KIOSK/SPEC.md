# KIOSK — Spec de conception (2026-07-06)

App `kiosk` : borne de rechargement cashless en libre-service sur terminal
Android (Cordova), avec TPE Stripe physique (BBPOS WisePOS E) et crédit de la
carte NFC **côté Fedow distant** (V1 legacy, via webhook Stripe).

Source du copier-coller : `../LaBoutik` (branche `main-tpe`), app `htmxview` +
modèles `APIcashless` (`Terminal`, `PaymentsIntent`, `Location`).

> **Cadre : coexistence V1.** Fedow reste un service HTTP distant (`fedow_connect`).
> Aucune dépendance à `fedow_core`. Le crédit monétaire n'est jamais stocké côté
> Lespass — c'est Fedow qui crédite sur réception du webhook Stripe, via sa route
> TPE existante (`validate_stripe_reader_wise_pose_and_make_transaction`),
> **étendue** pour accepter les places Lespass (voir §8bis).

> **Décision signature (importante).** Contrairement à LaBoutik, Lespass **ne signe
> PAS** les metadata TPE. Voir §8bis pour le raisonnement complet (modèle
> mono-serveur, clé Stripe Root exclusive → l'isolation inter-place par signature
> RSA est sans objet).

---

## 1. Objectif

Un terminal Android (Sunmi + TPE Stripe) appairé en **rôle Kiosque (`KI`)** ouvre
directement le front kiosk. Parcours client :

1. Choix du montant (boutons additifs +1/+5/+10/+20/+50 €).
2. Scan de la carte NFC TiBillet (lecteur Sunmi via plugin Cordova).
3. Paiement CB sur le TPE Stripe.
4. Fedow crédite la carte (webhook Stripe → route TPE étendue, branche Lespass sans
   signature → crédit — voir §8bis).
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
**NB** : dans LaBoutik ce n'est PAS un singleton — c'est un modèle normal avec un flag
`is_primary_location` + `get_primary_location()` (crée la Location chez Stripe à la
volée), qui distingue location primaire fédérée vs location du lieu. On peut le
simplifier en solo, mais c'est un **choix qui change la sémantique** — à assumer.
Clé Stripe via `RootConfiguration.get_solo().get_stripe_api()`.

### `Terminal`
TPE Stripe WisePOS.
- Champs : `id` (UUID PK), `name`, `registration_code`, `stripe_id`, `type`
  (`STRIPE_WISEPOS`), `archived`.
- **`term_user`** : `OneToOneField("AuthBillet.TibilletUser", ...)` — **1 borne = 1 TPE**
  (décision mainteneur). Cible le `TibilletUser` **concret** (pas le proxy `TermUser`, dont
  le manager filtre par tenant et casserait l'accès hors contexte tenant) ; l'admin restreint
  le choix aux `TermUser`. Remplace `user.appareil.terminals` de LaBoutik (pas de modèle
  `Appareil`). Le kiosk récupère son TPE via `request.user.terminal`.
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
  automatique) avec les metadata `{fedow_place_uuid, tag_id}` **non signées**, puis
  `process_payment_intent` sur le reader.
  - **Pas de signature** (voir §8bis). Metadata en clair.
  - `fedow_place_uuid` : lu sur `FedowConfig` (pas `Configuration`).
  - Clé Stripe : `RootConfiguration.get_solo().get_stripe_api()` (**compte Stripe
    Root**, partagé avec Fedow — le webhook Fedow retrouve le PaymentIntent sur ce
    même compte).
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
  lance le polling Celery, rend `waiting_credit_card_terminal.html`. **Récupère le TPE
  via `request.user.terminal`** (OneToOne), pas via `appareil.terminals`.
- `cancel` (GET) → annule l'action reader + le PaymentIntent Stripe.

### `poll_payment_intent_status` (`kiosk/tasks.py`, Celery)
Copié tel quel : poll 1×/s pendant 120 s max, push WebSocket sur le room
(`= payment_intent_stripe_id`), écran final ou cancel sur timeout.

### `RefillWisePoseValidator` (`kiosk/validators.py`)
Rebranché sur `QrcodeCashless.CarteCashless`. Montant → centimes.
**⚠️ `NFCcardFedow.retrieve(tag_id)` n'existe PAS côté Lespass** — c'est une **nouvelle
méthode client à écrire** (~15 lignes sur le pattern `_get`), pas une simple adaptation.
`NFCcardFedow` (`fedow_connect/fedow_api.py:758`) n'expose que `retrieve_card_by_signature`
(par user) et `card_tag_id_retrieve` (par numéro imprimé). La route Fedow existe côté
serveur (`CardAPI.retrieve`, `Card.objects.get(first_tag_id=pk)`, permission
`HasKeyAndPlaceSignature` → OK via branche S6). À écrire + validator de réponse.

---

## 5. WebSocket (`wsocket/`)

Ajouter `TerminalConsumer` dans `wsocket/consumers.py` + route
`ws/terminal/<pi_id>/` dans `wsocket/routing.py`. Copié de LaBoutik, avec le
**rejeu d'état à la (re)connexion** (relit le statut réel en base).
**Adaptation** : `connect()` teste `hasattr(user, 'appareil')` chez LaBoutik → à
remplacer par `terminal_role == KI` (pas de modèle `Appareil` côté Lespass).

---

## 6. Front (`kiosk/templates/kiosk/` + `kiosk/static/kiosk/`)

Copie fidèle du front LaBoutik : `base.html`, `select_amount.html`,
`waiting_credit_card_terminal.html`, `success.html`, `cancel.html`,
`sweet_scan_button.html`, `spinner.html`, `tpe/request_card.html`, `main.js`,
CSS (Bootstrap + SweetAlert + HTMX + WS).

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

## 8bis. Chantier Fedow — extension de la route TPE (crédit)

**Repo `../Fedow`, branche `main`.** C'est le seul dev côté Fedow.

### Le mécanisme existant (LaBoutik)
Le webhook Stripe (`IsStripe`, vérif `stripe_endpoint_secret`) déclenche
`StripeAPI.validate_stripe_reader_wise_pose_and_make_transaction` (`fedow_core/views.py:1095`).
Cette fonction :
1. `stripe.PaymentIntent.retrieve()` (clé Stripe de Fedow = compte Root) → source de vérité.
2. Lit `metadata['data']` = `{fedow_place_uuid, tag_id}` + `metadata['signature']`.
3. Vérifie `verify_signature(place.cashless_public_key(), ...)` — **échoue pour une
   place Lespass** (pas de `cashless_rsa_pub_key`).
4. Crédite la carte (transaction `REFILL`).

### L'extension (miroir de l'« EXTENSION S6 »)
Dans `validate_stripe_reader_wise_pose_and_make_transaction`, brancher la vérif.
**⚠️ Piège (relevé en relecture)** : dans le code actuel, `signature = metadata['signature']`
est lu **avant** la vérif → un PaymentIntent Lespass sans clé `signature` lèverait
`KeyError`. La lecture de la signature doit passer **dans le `else`** :

```python
if place.lespass_domain and not place.cashless_rsa_pub_key:
    pass  # place Lespass de confiance : PaymentIntent sur le compte Stripe Root = preuve suffisante
else:
    signature = stripe_payment.metadata['signature']   # lecture ICI, pas avant
    if not verify_signature(place.cashless_public_key(), data_to_b64(data), signature):
        raise Exception(...)  # LaBoutik, inchangé
```

~10 lignes. Aucun nouveau flux, modèle, ni handshake. LaBoutik reste strictement inchangé.

### ⚠️ Durcir l'idempotence (même PR Fedow)
L'anti-rejeu actuel est un `CheckoutStripe.objects.filter(checkout_session_id_stripe=...).exists()`
(`views.py:1395`) **sans `unique=True`** (`models.py:38`) et **non atomique** → fenêtre TOCTOU :
une redélivrance concurrente du même event Stripe peut **double-créditer**. Comme la décision
« pas de signature » s'appuie sur cette idempotence, il faut la rendre fiable :
**contrainte unique (partielle) sur `checkout_session_id_stripe`** ou `get_or_create` +
`IntegrityError` (~5 lignes + migration). Défaut préexistant (LaBoutik y est aussi exposé),
mais on le corrige puisqu'on s'en sert comme garde-fou.

### Portée réelle de la branche (honnêteté)
Le « miroir S6 » du webhook est **sémantiquement plus faible** que S6 sur les routes API :
dans S6 l'API key de place authentifie encore l'appelant (1 facteur conservé) ; ici, sans
signature, `place` n'est plus utilisée après chargement (asset fédéré, carte globale par
`first_tag_id`) et `fedow_place_uuid` devient purement déclaratif. C'est acceptable **sous la
seule hypothèse Root-exclusif** (ci-dessous), pas au-delà. Invariant à documenter :
`lespass_domain` est posé à la création de place et rétro-rempli pour d'anciennes places —
une place LaBoutik qui garderait `lespass_domain` en perdant sa clé RSA basculerait en mode
confiance (risque faible, à surveiller).

### Pourquoi pas de signature côté Lespass
- **Modèle mono-serveur.** LaBoutik = plusieurs serveurs cashless physiques distincts
  partageant le compte Stripe plateforme → la signature RSA isole les serveurs entre eux.
  Lespass = **un seul serveur par fédération**, clé Stripe **Root** partagée par tout le
  serveur. Il n'y a pas plusieurs serveurs à cloisonner.
- **Preuve d'origine déjà acquise.** Le `PaymentIntent` existe sur le compte Stripe Root,
  vérifié par le `retrieve()` authentifié de Fedow → il a forcément été créé par le serveur
  de confiance unique (seul détenteur de la clé Root, avec Fedow). La signature ne ferait
  que re-prouver ça.
- **Rien d'autre n'est perdu.** Anti-rejeu = idempotence (`payment_intent_stripe_id` →
  un seul `CheckoutStripe`), pas la signature. Intégrité/compromis : la clé RSA vivrait sur
  le même serveur que la clé Stripe Root → un compromis serveur donne les deux, la
  signature n'ajoute aucune défense.
- **Techniquement, Lespass n'a pas de clé de place.** `RsaKey` est OneToOne sur `TibilletUser`
  (seuls les users ont une clé privée) ; le `Wallet` de place ne stocke que `public_pem`.
  Signer aurait exigé de passer par un user — bancal. Ne pas signer est donc aussi le choix
  le plus simple.

### ⚠️ Hypothèse de sécurité (porte tout le raisonnement)
**Le compte Stripe Root est exclusif au serveur de la fédération** (confirmé mainteneur).
Si ce compte était un jour partagé hors du serveur + Fedow (plusieurs serveurs Lespass, ou
un acteur tiers détenant la clé Root), l'isolation par signature redeviendrait nécessaire.

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
| `FedowAPI().NFCcard.retrieve(tag_id)` | inexistant (`NFCcardFedow` n'a pas ce retrieve) | **Écrire** la méthode client (~15 l., pattern `_get`) + validator |
| `ConfigurationStripe.get_stripe_api()` | `RootConfiguration.get_stripe_api()` (`root_billet/models.py:43`, compte Root) | Rebrancher |
| `Configuration.fedow_place_uuid` | `FedowConfig.fedow_place_uuid` | Rebrancher |
| `Configuration.currency_code` | `BaseBillet.Configuration.currency_code` | OK, existe |
| signature RSA des metadata (`config.get_private_key()`) | — | **Supprimée** (§8bis) — plus de signature côté Lespass |
| `APIcashless.Location` | absent | **Copier `StripeLocation`** (pas singleton, cf. §3) |
| `Appareil.terminals` | **`Terminal.term_user` OneToOne → `TibilletUser`** (choix admin restreint aux TermUser) | Décidé — pas de modèle `Appareil` |
| injection `cordova.js` | `laboutik/base.html` (pattern existant) | Reproduire dans `kiosk/base.html` |

---

## 12. Résultat attendu

Terminal Android appairé `KI` → front kiosk → scan carte → montant → CB sur TPE →
Fedow crédite. Le solde reste la vérité de Fedow ; Lespass ne stocke que l'état
technique du paiement (`PaymentsIntent`).

**Mode DEMO** : simule le TPE sans hardware (`get_from_stripe` tire le statut au sort :
80 % attente / 10 % cancel / 10 % succès). **Attention recette** : en DEMO il n'y a pas de
webhook Stripe → **rien n'est réellement crédité côté Fedow**, l'écran « succès » est
cosmétique. À dire dans la doc utilisateur.

---

## Décisions actées (session 2026-07-06)

1. `PaymentsIntent` stocké localement (pilotage TPE), **champ `pos` supprimé**. Crédit = Fedow.
2. **Module `module_kiosk` à part**, app et menu admin distincts de LaBoutik.
3. Bridge `laboutik` modifié pour typer la redirection selon `terminal_role`.
4. Sous-parcours `link` : **ignoré** (YAGNI).
5. Fedow **distant** (coexistence V1), aucune dépendance `fedow_core`.
6. **Crédit via la route TPE Fedow existante, étendue** (`validate_stripe_reader_wise_pose_and_make_transaction`,
   branche Lespass miroir S6) — **pas de nouveau flux Fedow**.
7. **Pas de signature des metadata côté Lespass** (§8bis). Repose sur l'hypothèse :
   compte Stripe Root exclusif au serveur de la fédération.
8. Clé Stripe = **compte Root** (`RootConfiguration`), partagé avec Fedow — le webhook
   Fedow retrouve le PaymentIntent sur ce compte.
9. **Lien TPE↔borne = `Terminal.term_user` OneToOne → `TibilletUser`** (concret, choix
   restreint aux `TermUser` dans l'admin ; 1 borne = 1 TPE). Pas de modèle `Appareil` ;
   le kiosk lit `request.user.terminal`.

## Corrections issues de la relecture Fable 5 (à ne pas oublier à l'implémentation)

- Patch Fedow : lire `metadata['signature']` **dans le `else`** (sinon `KeyError`).
- **Durcir l'idempotence Fedow** (contrainte unique / `get_or_create` atomique sur
  `checkout_session_id_stripe`) — même PR que l'extension.
- `NFCcardFedow.retrieve(tag_id)` = **méthode client à écrire**, pas une adaptation.
- `TerminalConsumer.connect` : `hasattr(user,'appareil')` → `terminal_role == KI`.
- Templates : ne pas oublier `spinner.html` + `tpe/request_card.html`.
- `StripeLocation` : pas un singleton dans LaBoutik (sémantique location primaire/lieu).
- DEMO ne crédite jamais Fedow (écran succès cosmétique).
