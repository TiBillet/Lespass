# Moyens de paiement — Spec chantier futur

**Date création :** 2026-05-16
**Statut :** Spec brouillon — sera la base d'un futur chantier de refacto large des moyens de paiement.

Ce document est ouvert comme **point d'entrée** d'un chantier futur. Au fur et à mesure que des décisions sont prises sur les paiements (Stripe Connect, Stripe Checkout, abonnements, refunds, comptabilité, multi-providers éventuels…), on les consolide ici.

---

## 1. Contexte immédiat (2026-05-16)

La session ONBOARD a supprimé le flow legacy `/tenant/new/` (création de tenant). Ce flow vivait dans `BaseBillet/views.py::Tenant` (un ViewSet DRF). Cette classe mélangeait DEUX responsabilités :

1. **Création de tenant** (legacy `/tenant/new/`) — remplacé par l'app `onboard/`. Méthodes supprimées :
   - `Tenant.new()`
   - `Tenant.create_waiting_configuration()`
   - `Tenant.emailconfirmation_tenant()`
   - `Tenant.onboard_stripe()` (variante création — appelée juste après confirmation email)
   - `Tenant.onboard_stripe_return()` (variante création — retour Stripe + notif superadmin)

2. **Configuration Stripe Connect d'un tenant EXISTANT** — déclenchée depuis l'admin Unfold quand un admin essaie de créer un produit payant. Méthodes conservées et **migrées vers `PaiementStripe/`** :
   - `Tenant.onboard_stripe_from_config()`
   - `Tenant.onboard_stripe_return_from_config()`

Le point d'entrée est `Administration/admin/products.py::CheckStripeComponent` (un Unfold component) qui rend `admin/product/checkstripe_component.html`. Si `Configuration.stripe_payouts_enabled=False`, un bouton "Créer et lier son compte Stripe" est affiché — clic → `/tenant/onboard_stripe_from_config` → Stripe AccountLink → retour sur `/tenant/<id>/onboard_stripe_return_from_config/` → flag mis à `True`.

### Choix de design (volontaire)

**Stripe N'EST PAS dans le wizard d'onboarding initial.** L'utilisateur découvre TiBillet, crée son espace avec ses adhésions / réservations gratuites, et n'est invité à configurer Stripe Connect que **plus tard**, au moment où il crée son premier produit payant. Raison : Stripe Connect demande IBAN, identité légale, justificatifs — friction énorme qu'on veut différer.

---

## 2. Migration immédiate (Session 2026-05-16)

| Avant | Après |
|---|---|
| `BaseBillet/views.py::Tenant.onboard_stripe_from_config()` | `PaiementStripe/views.py::StripeConnectOnboardingViewSet.onboard_from_config()` |
| `BaseBillet/views.py::Tenant.onboard_stripe_return_from_config()` | `PaiementStripe/views.py::StripeConnectOnboardingViewSet.onboard_return_from_config()` |
| URL `GET /tenant/onboard_stripe_from_config` | URL `GET /stripe/onboard/from_config/` |
| URL `GET /tenant/<id_acc_connect>/onboard_stripe_return_from_config/` | URL `GET /stripe/onboard/return_from_config/<id_acc_connect>/` |
| Template lien `<a href="/tenant/onboard_stripe_from_config">` dans `Administration/templates/admin/product/checkstripe_component.html` | `<a href="/stripe/onboard/from_config/">` |
| Template render `reunion/views/tenant/after_onboard_stripe.html` | `PaiementStripe/templates/paiementstripe/after_onboard_stripe.html` (copié depuis l'ancien) |

### Acceptation

- Le bouton "Créer et lier son compte Stripe" affiché à l'admin quand il crée un Product payant fonctionne toujours.
- Le retour de Stripe atterrit sur la même page de confirmation (succès / pending) qu'avant.
- `Configuration.stripe_payouts_enabled` se met à `True` après onboarding complet.
- Aucune référence à `Tenant.*onboard_stripe*` ne subsiste dans le code.

### Hors-scope (volontaire) de cette migration

- ❌ Pas de modification de la logique métier Stripe (mêmes appels `stripe.AccountLink.create`, mêmes vérifs `details_submitted` / `payouts_enabled`).
- ❌ Pas de modification du modèle `Configuration` (le champ `stripe_connect_account` / `stripe_connect_account_test` reste là).
- ❌ Pas de refacto multi-providers (cf. section 3).
- ❌ Pas de modification du flow webhooks Stripe (`PaiementStripe/webhooks.py` ou équivalent).

---

## 3. Pistes pour un chantier de refacto large (à venir)

### 3.1 Multi-providers

À ce jour, TiBillet ne supporte que Stripe Connect. Idée d'un chantier futur : abstraction `PaymentProvider` pour pouvoir brancher d'autres processeurs (HelloAsso, Mollie, SumUp pour POS, Lydia/Pumpkin pour France-only…).

Implications :
- Interface commune : `create_checkout()`, `create_account_link()`, `verify_webhook()`, `refund()`.
- Settings par tenant : `Configuration.payment_provider` (choice field) au lieu du `stripe_connect_account` direct.
- Migration des données existantes : tous les tenants existants → `payment_provider="stripe"`.
- Templates de paiement : un partial par provider, sélectionné dynamiquement.

### 3.2 Refacto Configuration Stripe

Aujourd'hui sur `Configuration` (singleton tenant) :
- `stripe_connect_account` (str, prod)
- `stripe_connect_account_test` (str, test)
- `stripe_mode_test` (bool)
- `stripe_payouts_enabled` (bool, set par `onboard_return_from_config`)

Avant la migration :
- Le champ `stripe_mode_test` est dupliqué entre `Configuration` (tenant) et `RootConfiguration` (root). Source de vérité confuse.
- `Configuration.get_stripe_connect_account()` choisit l'un ou l'autre selon `stripe_mode_test` — mais `RootConfiguration.stripe_mode_test` est aussi consulté ailleurs.

Idée : extraire dans un sous-modèle `StripeConnectConfig` lié à `Configuration` par `OneToOneField` (ou `ForeignKey` nullable si on prévoit multi-providers).

### 3.3 Webhooks Stripe — événements à mieux gérer

Les webhooks Stripe (`payment_intent.succeeded`, `account.updated`, etc.) sont actuellement traités dans `PaiementStripe/views.py` (ou similaire). Pistes :
- Idempotence par `event.id` (déjà fait ?) — à vérifier.
- File d'attente Celery pour ne pas bloquer le webhook HTTP (Stripe time out après 30s).
- Retry policy explicite.
- Logs structurés.

### 3.4 Refunds et avoirs

Le projet a déjà un système d'**avoirs** (cf. `BaseBillet/models.py::Avoir`) pour les remboursements manuels. Le pendant Stripe (refund automatique) est moins évident :
- Quand on annule une réservation, on émet un avoir comptable interne — pas un refund Stripe.
- L'admin doit refunder manuellement côté Stripe Dashboard.
- Refacto possible : workflow "demander un refund" qui appelle `stripe.Refund.create` ET émet un Avoir.

### 3.5 Comptabilité (export FEC)

Déjà implémenté pour LaBoutik (cf. `laboutik/exports/`). Pour Lespass (billetterie), pas encore. Chantier à envisager :
- Export FEC des transactions Stripe (billets, adhésions, refunds).
- Plan comptable mappable par tenant.

### 3.6 Stripe Connect — passage Express vers Custom ?

Aujourd'hui : compte Stripe Connect **Express** (Stripe gère l'onboarding, dashboard, paiements). Pour un futur passage à **Custom** (TiBillet gère tout en marque blanche), plein de boulot :
- Nouveau flow KYC.
- Refonte UI dashboard.
- Conformité PSP partielle.

Pas prioritaire — Express suffit pour le modèle coopératif actuel.

---

## 4. Décisions à prendre (à compléter)

- [ ] Garder `Configuration.stripe_payouts_enabled` comme flag autoritaire, ou re-fetcher à chaque besoin via API Stripe ?
- [ ] Standardiser les `return_url` Stripe : URL absolue dans tous les cas (https://...) ? Ou path relatif avec `request.build_absolute_uri()` ?
- [ ] Tests des callbacks Stripe : mock `stripe.AccountLink.create` (déjà fait dans `tests/pytest/test_stripe_*.py`) ou stripe-mock server ?

---

## 5. Liens

- Migration Session 2026-05-16 (Stripe `_from_config` → `PaiementStripe/`) : cf. `02-implementation-migration-2026-05-16.md` (à venir).
- Récap ONBOARD : `TECH_DOC/SESSIONS/ONBOARD/03-session-recap.md`.
- Pièges Stripe documentés : `tests/PIEGES.md` section "Mock Stripe".
