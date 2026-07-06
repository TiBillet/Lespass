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
| CHANTIER-01-*.md | Câblage (à venir : plan d'implémentation) | ⏳ |

## Décisions clés

1. **Fedow distant** (coexistence V1) — aucune dépendance `fedow_core`. Le crédit
   monétaire n'est jamais stocké côté Lespass (Fedow via webhook Stripe).
2. `PaymentsIntent` **stocké localement** (pilotage TPE + affichage), champ `pos`
   supprimé.
3. **App et module autonomes** (`module_kiosk`), menu admin distinct de LaBoutik.
   Le kiosk grandira (adhésions, etc.).
4. Appairage réutilise `discovery` + bridge : le rôle `KI` route vers `/kiosk/`
   (modif `LaBoutikAuthBridgeView`).
5. **Même APK Cordova** que LaBoutik — c'est l'appairage typé `KI` qui décide.
6. Sous-parcours `link` : ignoré (YAGNI).

## Fichiers touchés (prévision)

- Neufs : `kiosk/` (models, views, tasks, validators, admin, urls, templates, static).
- Modifiés (sensibles, à confirmer) : `laboutik/views.py` (bridge),
  `wsocket/consumers.py` + `routing.py`, `BaseBillet/models.py` (`module_kiosk`),
  `Administration/admin_tenant.py` (sidebar + dashboard), `TiBillet/settings.py`
  (TENANT_APPS), `TiBillet/urls_tenants.py`.
