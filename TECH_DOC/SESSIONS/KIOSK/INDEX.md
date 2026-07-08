# KIOSK — Hub du chantier

App `kiosk` : borne de rechargement cashless en libre-service sur terminal Android
(Cordova), avec TPE Stripe physique (BBPOS WisePOS E) et crédit de la carte NFC
**côté Fedow distant** (coexistence V1 legacy, via webhook Stripe).

Copier-coller rebranché depuis `../LaBoutik` (branche `main-tpe`) : app `htmxview`
+ modèles `APIcashless` (`Terminal`, `PaymentsIntent`, `Location`).

## Documents

| Doc | Contenu | Statut |
|---|---|---|
| [SPEC.md](./SPEC.md) | Conception : modèles, controllers, front, admin, appairage, module | ✅ Validé 2026-07-06 |
| [CHANTIER-01-app-modeles-tpe.md](./CHANTIER-01-app-modeles-tpe.md) | Plan d'impl. : app kiosk + modèles TPE (StripeLocation, Terminal, PaymentsIntent) + admin Unfold | ✅ Implémenté 2026-07-06 (5/5 tâches, review Fable OK, 4 tests verts) — à committer |
| [CHANTIER-02-front-vues-ws.md](./CHANTIER-02-front-vues-ws.md) | Front (copie) + KioskViewSet + validators + NFCcard.retrieve + WebSocket | ✅ Implémenté + Fable review (statics 404 corrigés, bug fedow_api débusqué) |
| [CHANTIER-03-branchements.md](./CHANTIER-03-branchements.md) | module_kiosk + sidebar/dashboard + bridge KI + URLs | ✅ Implémenté + Fable review (i18n FR corrigé) — 16 tests |
| [CHANTIER-04-fedow-e2e.md](./CHANTIER-04-fedow-e2e.md) | Extension route TPE Fedow (miroir S6) + idempotence unique/IntegrityError | ✅ Implémenté (repo Fedow) + Fable review — 54 tests Fedow verts |
| [CHANTIER-05-nfc-duo.md](./CHANTIER-05-nfc-duo.md) | NFC duo Android (NFCMC) / Pi socket.io (NFCLO) + DEMO simulateur cartes | ✅ Implémenté + Fable review (2 bugs bloquants corrigés : protocole socket.io Pi, z-index overlay) — 12 tests |

## Passe finale (djc + chasse aux bugs Fable 5) — ✅ FAITE

8 vrais bugs corrigés (dont : `type_app`/cordova jamais injecté = NFC mort, double-paiement TPE
par listener empilé, erreurs refill invisibles HTMX 4xx, `request.user.terminal` sans garde → 500,
spinner bloqué sur exception polling). Conformité DJC : JSON UI → HTML partials, `{% translate %}` FR,
`data-testid`, aria. **16/16 tests Lespass + 14/14 Fedow verts.** Rapport :
`scratchpad/kiosk-exec/passe-finale-review.md`.

## À faire par le mainteneur (déploiement)
- **Commits** : Lespass (`kiosk/` + fichiers modifiés) et **Fedow** (`fedow_core/` + migration 0025) — 2 repos.
- **Fedow : rebuild d'image** `tibillet/fedow` (code baké, un restart ne suffit pas) + `migrate` (0025).
- **makemessages/compilemessages** (FR/EN) pour les `{% translate %}` ajoutés au front kiosk.
- Migrations Lespass déjà appliquées en dev : `kiosk` 0001-0003, `BaseBillet` 0227.
- Points ouverts non bloquants : regex chat `wsocket/routing.py:7` (pré-existant), garde KI bypass en DEBUG (voulu).

## Décisions clés

1. **Fedow distant** (coexistence V1) — aucune dépendance `fedow_core`. Le crédit
   monétaire n'est jamais stocké côté Lespass (Fedow via webhook Stripe).
2. **Crédit via la route TPE Fedow existante, étendue** (miroir « EXTENSION S6 » sur
   `validate_stripe_reader_wise_pose_and_make_transaction`) — pas de nouveau flux Fedow.
3. **Pas de signature des metadata côté Lespass.** Modèle mono-serveur + clé Stripe
   Root exclusive → l'isolation inter-place par signature RSA est sans objet
   (raisonnement complet dans SPEC §8bis). ⚠️ Repose sur : compte Stripe Root
   exclusif au serveur de la fédération.
4. `PaymentsIntent` **stocké localement** (pilotage TPE + affichage), champ `pos`
   supprimé. Clé Stripe = compte Root (partagé avec Fedow).
5. **App et module autonomes** (`module_kiosk`), menu admin distinct de LaBoutik.
   Le kiosk grandira (adhésions, etc.).
6. Appairage réutilise `discovery` + bridge : le rôle `KI` route vers `/kiosk/`
   (modif `LaBoutikAuthBridgeView`).
7. **Même APK Cordova** que LaBoutik — c'est l'appairage typé `KI` qui décide.
8. Sous-parcours `link` : ignoré (YAGNI).

## Fichiers touchés (prévision)

- Neufs : `kiosk/` (models, views, tasks, validators, admin, urls, templates, static).
- Modifiés Lespass (sensibles, à confirmer) : `laboutik/views.py` (bridge),
  `wsocket/consumers.py` + `routing.py`, `BaseBillet/models.py` (`module_kiosk`),
  `Administration/admin_tenant.py` (sidebar + dashboard), `TiBillet/settings.py`
  (TENANT_APPS), `TiBillet/urls_tenants.py`.
- Modifié **Fedow** (`../Fedow`, branche `main`) : `fedow_core/views.py` —
  extension ~10 lignes de `validate_stripe_reader_wise_pose_and_make_transaction`.
