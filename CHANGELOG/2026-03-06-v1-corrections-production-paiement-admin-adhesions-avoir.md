# v1.7.2 — Corrections production + Paiement admin adhesions + Avoir comptable

**Date :** Mars 2026
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 0. Protection doublon paiement adhesion (SEPA) / Duplicate membership payment protection (SEPA)

**FR :**
Quand un utilisateur cliquait plusieurs fois sur le lien de paiement d'adhesion
(recu par email apres validation admin), un nouveau checkout Stripe etait cree a chaque clic.
Cela pouvait entrainer des **doubles prelevements SEPA** (signaie en production).

La vue `get_checkout_for_membership` verifie maintenant si un paiement Stripe existe deja :
- **Session Stripe encore ouverte** : reutilise l'URL existante (pas de doublon).
- **Session "complete" (SEPA en cours)** : affiche une page d'information expliquant
  que le prelevement est en cours de traitement (jusqu'a 14 jours).
- **Session expiree** : cree un nouveau checkout normalement.

**EN:**
When a user clicked multiple times on the membership payment link
(received by email after admin validation), a new Stripe checkout was created each time.
This could cause **duplicate SEPA debits** (reported in production).

The `get_checkout_for_membership` view now checks for an existing Stripe payment:
- **Stripe session still open**: reuses the existing URL (no duplicate).
- **Session "complete" (SEPA pending)**: displays an info page explaining
  the debit is being processed (up to 14 days).
- **Session expired**: creates a new checkout normally.

**Fichiers / Files:**
- `BaseBillet/views.py` — protection doublon dans `get_checkout_for_membership`
- `BaseBillet/templates/reunion/views/membership/payment_already_pending.html` — nouveau template

**Migration necessaire / Migration required:** Non

---

### 1. Avoir comptable (credit note) sur les ventes / Credit note on sales

**FR :**
Les admins peuvent emettre un **avoir** sur une ligne de vente depuis l'admin (bouton "Avoir" dans la liste des ventes).
Un avoir cree une ligne miroir avec quantite negative pour annuler comptablement la vente,
sans supprimer l'ecriture originale (conformite fiscale francaise).
Gardes : uniquement sur lignes confirmees ou payees, et un seul avoir par ligne.
L'avoir est envoye a LaBoutik si un serveur cashless est configure.
L'export CSV inclut une colonne "Ref. avoir" pour la tracabilite.

**EN:**
Admins can issue a **credit note** on a sale line from the admin (row action button in the sales list).
A credit note creates a mirror line with negative quantity to cancel the sale for accounting purposes,
without deleting the original entry (French fiscal compliance).
Guards: only on confirmed or paid lines, and only one credit note per line.
The credit note is sent to LaBoutik if a cashless server is configured.
CSV export includes a "Credit note ref." column for traceability.

**Fichiers / Files:**
- `BaseBillet/models.py` — status `CREDIT_NOTE`, FK `credit_note_for`
- `BaseBillet/signals.py` — transition CREATED → CREDIT_NOTE
- `Administration/admin_tenant.py` — `LigneArticleAdmin.emettre_avoir()`
- `Administration/importers/lignearticle_exporter.py` — colonne export
- `BaseBillet/migrations/0199_credit_note_lignearticle.py`

**Annulation adhesion avec avoir :**
L'action "Annuler" sur une adhesion affiche desormais une page de confirmation.
Si l'adhesion a des lignes de vente payees, l'admin peut choisir "Annuler et creer un avoir".
Les avoirs sont crees pour chaque ligne VALID/PAID liee a l'adhesion.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.cancel()` (GET/POST avec confirmation)
- `Administration/templates/admin/membership/cancel_confirm.html` (nouveau)

---

### 2. Correction annulation reservation admin (cheque, especes) / Fix admin reservation cancellation (non-Stripe)

**FR :**
Quand un admin annulait une reservation creee manuellement (payee par cheque, especes, etc.),
aucune ligne de remboursement ou d'avoir n'etait creee. La reservation passait en "annulee"
sans trace comptable, car `cancel_and_refund_resa` ne cherchait les LigneArticle que via
les `Paiement_stripe` (FK), et les reservations admin n'en ont pas.
Desormais, lors de l'annulation, un avoir (CREDIT_NOTE) est automatiquement cree pour chaque
LigneArticle hors-Stripe (sale_origin=ADMIN) liee a la reservation.
Meme correction pour l'annulation de ticket individuel (`cancel_and_refund_ticket`).

**EN:**
When an admin cancelled a manually created reservation (paid by check, cash, etc.),
no refund or credit note line was created. The reservation was marked as cancelled
with no accounting trace, because `cancel_and_refund_resa` only looked for LigneArticle
via `Paiement_stripe` (FK), and admin reservations don't have one.
Now, upon cancellation, a credit note (CREDIT_NOTE) is automatically created for each
non-Stripe LigneArticle (sale_origin=ADMIN) linked to the reservation.
Same fix for single ticket cancellation (`cancel_and_refund_ticket`).

**Fichiers / Files:**
- `BaseBillet/models.py` — `Reservation._lignes_hors_stripe()`, `Reservation._creer_avoir()`,
  `cancel_and_refund_resa()`, `cancel_and_refund_ticket()`

---

### 3. FK reservation sur LigneArticle / Reservation FK on LigneArticle

**FR :**
Ajout d'une FK directe `LigneArticle.reservation` pour lier une ligne comptable a sa reservation
sans dependre de `Paiement_stripe` comme intermediaire.
Avant, les reservations admin (cheque, especes) n'avaient aucun lien vers leurs LigneArticle.
La FK est renseignee dans les 4 flows de creation (front, API v1, API v2, admin).
Une data migration backfill les lignes existantes depuis `paiement_stripe.reservation`.
Les methodes `articles_paid()` et `_lignes_hors_stripe()` utilisent la FK directe
avec fallback sur l'ancien chemin pour compatibilite.

**EN:**
Added a direct FK `LigneArticle.reservation` to link an accounting line to its reservation
without relying on `Paiement_stripe` as intermediary.
Previously, admin reservations (check, cash) had no link to their LigneArticle.
The FK is set in all 4 creation flows (front, API v1, API v2, admin).
A data migration backfills existing lines from `paiement_stripe.reservation`.
`articles_paid()` and `_lignes_hors_stripe()` use the direct FK with legacy fallback.

**Fichiers / Files:**
- `BaseBillet/models.py` — FK `reservation` + simplification `articles_paid()`, `_lignes_hors_stripe()`
- `BaseBillet/validators.py` — `reservation=reservation` (front)
- `ApiBillet/serializers.py` — `reservation=reservation` (API v1)
- `api_v2/serializers.py` — `reservation=reservation` (API v2)
- `Administration/admin_tenant.py` — `reservation=reservation` (admin)
- `BaseBillet/migrations/0200_add_reservation_fk_to_lignearticle.py`
- `BaseBillet/migrations/0201_backfill_lignearticle_reservation.py`

---

### 4. Correction niveau de log API Brevo / Fix Brevo API log level

**FR :**
Quand un admin testait sa cle API Brevo depuis la configuration et que la cle etait invalide,
l'erreur 401 remontait en `logger.error` dans Sentry, polluant les alertes.
C'est une erreur de configuration utilisateur, pas un bug applicatif.
Le niveau de log est passe a `logger.warning`.

**EN:**
When an admin tested their Brevo API key from the configuration and the key was invalid,
the 401 error was logged as `logger.error` in Sentry, polluting alerts.
This is a user configuration error, not an application bug.
Log level changed to `logger.warning`.

**Fichiers / Files:** `Administration/admin_tenant.py` — `BrevoConfigAdmin.test_api_brevo()`

---

### 5. Correction deconnexion automatique apres 3 mois / Fix automatic logout after 3 months

**FR :**
Les utilisateurs etaient deconnectes apres exactement 3 mois, meme s'ils utilisaient le site quotidiennement.
Cause : `SESSION_SAVE_EVERY_REQUEST` n'etait pas defini (defaut Django = `False`),
donc le cookie de session n'etait renouvele que lors de modifications de la session, pas a chaque visite.
Ajout de `SESSION_SAVE_EVERY_REQUEST = True` pour que chaque visite renouvelle le cookie.

**EN:**
Users were logged out after exactly 3 months, even when using the site daily.
Cause: `SESSION_SAVE_EVERY_REQUEST` was not set (Django default = `False`),
so the session cookie was only renewed when the session was modified, not on every visit.
Added `SESSION_SAVE_EVERY_REQUEST = True` so every visit renews the cookie.

**Fichiers / Files:** `TiBillet/settings.py`

---

### 6. Bouton "Ajouter un paiement" sur les adhesions en attente / "Add payment" button on pending memberships

**FR :**
Les admins de lieux recoivent des adhesions remplies en ligne mais payees sur place
(especes, cheque, virement). Ces adhesions restaient bloquees en "attente de paiement"
sans moyen de les valider depuis l'admin.
Nouveau bouton "Ajouter un paiement" sur la page detail d'une adhesion en attente (WP ou AW).
Le formulaire demande le montant et le moyen de paiement, puis declenche toute la chaine :
creation de la ligne de vente, calcul de la deadline, envoi de l'email de confirmation,
transaction Fedow, et notification LaBoutik.

**EN:**
Venue admins receive memberships filled out online but paid on-site
(cash, check, bank transfer). These memberships were stuck in "waiting for payment"
with no way to validate them from the admin.
New "Add payment" button on the detail page of a pending membership (WP or AW).
The form asks for the amount and payment method, then triggers the full chain:
sale line creation, deadline calculation, confirmation email,
Fedow transaction, and LaBoutik notification.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.ajouter_paiement()`
- `Administration/templates/admin/membership/ajouter_paiement.html` (nouveau / new)

---
