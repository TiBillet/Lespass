# Tests restants à faire — Lespass main

Date : 2026-06-11

Ce document liste ce qui n'est **pas** testé aujourd'hui.
Classé par priorité. Une ligne = un manque.

---

## Checklist mainteneur (2026-06-11) — flux d'argent à couvrir

Liste fournie par le mainteneur, vérifiée contre les suites actuelles :

| Action | État |
|---|---|
| Recharge portefeuille depuis « mon compte » (UI) | ❌ Rien (seule la recharge par API est testée) |
| Remboursement du portefeuille des monnaies fédérées | ❌ Rien |
| Paiement QR code « initier un paiement » | ❌ Rien |
| Deposit → retour en banque depuis la page d'asset | ❌ Rien |
| Paiement QR code multi-tenant + deposits/totaux dans X tenants fédérés | ❌ Rien |
| Adhésion SEPA (mandat complet + échecs) | ⚠️ Partiel (TS 36 : doublon seulement) |
| Paiement récurrent (cycle de renouvellement réel) | ⚠️ Partiel (création admin + annulation seulement) |
| Récurrent + SSA → déclencheur de monnaie à chaque échéance | ⚠️ Partiel (SSA one-shot mocké seulement) |
| Réservation prix libre — achat complet montant custom | ⚠️ Partiel (validations client seulement) |
| Options adhésion (prix libre, validation manuelle) | ✅ Couvert (mocks + TS + Python) |
| Options réservation (gratuite, adhésion obligatoire) | ✅ Couvert (mocks + TS 19/38) |

## Priorité 1 — Critique (flux d'argent et parcours essentiels)

| Manque | Détail | Format conseillé |
|---|---|---|
| **Paiement / scan QR code** | Les vues QR existent (`BaseBillet/views.py`, `ApiBillet`) mais aucun test dédié. C'est pourtant un des 4 flux essentiels (recharge wallet, QR code, adhésion, billetterie). | pytest DB-only (vue + état wallet) puis 1 test E2E Python |
| **Webhooks Stripe directs** | Le handler `/webhook_stripe/` (`checkout.session.completed`, `invoice.paid`) n'est jamais appelé directement dans les tests. On simule toujours via `update_checkout_status()`. | pytest avec POST signé mocké |
| **Renouvellement d'abonnement Stripe** | Le webhook `invoice.paid` et le cycle de renouvellement ne sont pas testés. | pytest |
| **Remboursements** | `stripe.Refund.create()` et le webhook `charge.refunded` sans test. | pytest |
| **Isolation cross-tenant BaseBillet** | Aucun test ne vérifie qu'un tenant ne voit pas les données d'un autre (events, memberships, reservations). La V2 le fait pour fedow_core. | pytest avec 2 tenants |

## Priorité 2 — Important

| Manque | Détail | Format conseillé |
|---|---|---|
| **Tâches Celery** | ~40 tâches non testées (envoi factures, emails de billets, webhooks reservation). `crowds/tasks.py` est à 19 % de coverage. | pytest, appel direct des fonctions |
| **Échecs SEPA** | Création de mandat OK (spec 36), mais aucun scénario d'échec. | pytest |
| **OAuth / SSO** | Flow Authlib (`/api/user/oauth`) sans test. | pytest |
| **PaiementStripe/views.py** | 20 % de coverage seulement. Les retours d'erreur Stripe ne sont pas couverts. | pytest |
| **crowds/views.py** | 13 % de coverage. Les vues HTMX crowds reposent uniquement sur 3 specs TS. | pytest (rendu partials + statuts HTTP) |

## Priorité 3 — Souhaitable

| Manque | Détail |
|---|---|
| E2E adhésion en Python | Aujourd'hui 100 % TypeScript. À migrer (voir PLAN_SIMPLIFICATION.md). |
| E2E billetterie en Python | Idem. |
| PDF tickets / factures | Génération non testée. |
| Redimensionnement images (stdimage) | Upload testé, pas le resize. |
| Carrousel templates | Non testé. |
| Rate limiting | Code commenté, pas de test. |

## Cibles coverage — où attaquer quand le socle sera validé

Mesure du 2026-06-11 (pytest seul, hors migrations, avant l'ajout des tests
Stripe mockés). Les fichiers ci-dessous sont les plus gros écarts entre
« code critique » et « coverage » :

| Fichier | Coverage | Pourquoi c'est prioritaire |
|---|---|---|
| `crowds/views.py` (598 lignes) | 13 % | Toutes les vues HTMX crowds reposent sur 2 specs TS |
| `fedow_connect/fedow_api.py` (573 lignes) | 18 % | Client HTTP Fedow : argent, tokens, wallets |
| `crowds/tasks.py` (118 lignes) | 19 % | Tâches Celery crowdfunding (emails, cascade) |
| `PaiementStripe/views.py` (183 lignes) | 20 % | Webhooks et retours Stripe — cœur du flux d'argent |
| `ApiBillet/views.py` | ~29 % | API legacy v1 encore branchée |
| `api_v2/serializers.py` (731 lignes) | 28 % | Mapping schema.org — beaucoup de branches non couvertes |

Méthode quand on s'y attaque :
1. Relancer la mesure (`pytest tests/pytest/ --cov=... --cov-report=term-missing`)
   pour avoir les lignes exactes manquantes — les nouveaux tests Stripe mockés
   ont déjà dû améliorer `PaiementStripe` et `BaseBillet`.
2. Commencer par les branches d'erreur des webhooks Stripe (priorité 1 ci-dessus).
3. `pytest-cov` est installé via pip dans le venv du container — pour le
   pérenniser : `poetry add --group dev pytest-cov` (décision mainteneur).

## Référence

La liste « ce qui n'est pas testé » de la V2 (`lespass-main/tests/TESTS_README.md`)
recoupe largement celle-ci : webhooks Stripe, OAuth, Celery, SEPA, refunds.
Les deux repos ont les mêmes angles morts. Un test écrit pour le main au
format V2 (pytest / Playwright Python) pourra être copié dans la V2 presque tel quel.
