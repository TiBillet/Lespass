# Changelog / Journal des modifications

## 2. Polish header, sidebar categories et footer / Header, sidebar & footer polish

**Quoi / What:** Ameliorations visuelles et d'accessibilite sur les zones permanentes de l'interface POS : header, sidebar categories, footer et menu burger.
**Pourquoi / Why:** Un benevole en festival doit comprendre chaque zone en 1 seconde, sur desktop ET mobile.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/header.html` | Bordure accent vert 3px, `text-wrap: balance` sur titre, aria-label + data-testid sur burger, animation slide-down + overlay sombre sur menu burger, menu pleine largeur mobile |
| `laboutik/templates/cotton/categories.html` | Separateur visuel sous "Tous", `text-wrap: balance` + overflow sur noms longs |
| `laboutik/templates/laboutik/views/common_user_interface.html` | `tabular-nums` sur total, `.toFixed(2)` pour 2 decimales, `data-testid` sur les 3 boutons footer |
| `locale/fr/LC_MESSAGES/django.po` | Traductions "Menu", "Menu principal" |
| `locale/en/LC_MESSAGES/django.po` | Traductions "Menu", "Main menu" |

### Migration
- **Migration necessaire / Migration required:** Non

---

## 1. Polish paiement et ecrans modaux (FALC) / Payment screens polish (FALC)

**Quoi / What:** Refonte FALC des 5 ecrans de paiement de la caisse POS pour qu'un benevole comprenne chaque ecran en 1 seconde.
**Pourquoi / Why:** Les ecrans de paiement etaient fonctionnels mais peu lisibles : boutons tous identiques (vert), pas de total visible avant saisie especes, monnaie a rendre peu visible, carte "federee" incomprehensible pour un benevole.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/bt/paiement.html` | Variable Cotton `bg` pour couleur de fond, `aria-hidden` sur icone, commentaire LOCALISATION |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Couleurs par moyen (CASHLESS bleu, CB marine, CHEQUE gris, OFFRIR dore), titre recharge FALC, total affiche, `data-testid` sur tous les boutons |
| `laboutik/templates/laboutik/partial/hx_confirm_payment.html` | Total en grand, champ 80px avec devise, `inputmode="decimal"`, `autofocus`, `aria-label`, `role="alert"`, media query mobile, commentaires FALC bilingues |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Icone check animee, "Paiement reussi", "Paye en", monnaie a rendre en box rouge/dore, `data-testid` |
| `laboutik/templates/laboutik/partial/hx_card_feedback.html` | Icone carte, "Carte avec nom", icones par asset (TLF/TNF/TIM), `data-testid` par section, commentaires bilingues |
| `locale/fr/LC_MESSAGES/django.po` | Traductions FR + correction fuzzy "Paiement reussi" (etait "Envoye a Stripe") |
| `locale/en/LC_MESSAGES/django.po` | Traductions EN completes |

### Migration
- **Migration necessaire / Migration required:** Non

---

## v1.7.6 — Skin Faire Festival + Corrections UX et Sentry

**Date :** Mars 2026
**Migration :** Non

---

### 1. Skin Faire Festival — ameliorations CSS et templates / Faire Festival skin — CSS and template improvements

**FR :**
Ameliorations du skin "Faire Festival" suite aux retours terrain :
- Bordures arrondies (`border-radius`) sur les cartes et le bouton burger mobile
- Titres des evenements en police mono, taille reduite, avec `hyphens: auto`
- Bordure image evenement epaissie (1px → 3px)
- Badge de date repositionne (`margin-left: 0` au lieu de -100px)
- Padding horizontal des cartes ajuste

**EN:**
Improvements to the "Faire Festival" skin based on field feedback:
- Rounded borders (`border-radius`) on cards and mobile burger button
- Event titles in mono font, smaller size, with `hyphens: auto`
- Event image border thickened (1px → 3px)
- Date badge repositioned (`margin-left: 0` instead of -100px)
- Card horizontal padding adjusted

**Fichiers / Files:**
- `BaseBillet/static/faire_festival/css/faire_festival.css`

---

### 2. Lazy-load video sur la page d'accueil / Video lazy-load on homepage

**FR :**
La video motion-table de la page d'accueil bloquait le chargement sur Firefox mobile.
Remplacement de `autoplay` + `src` par un mecanisme `IntersectionObserver` :
la video n'est telechargee et lue que lorsqu'elle entre dans le viewport.
`preload="none"` empeche tout telechargement au chargement initial de la page.

**EN:**
The motion-table video on the homepage was blocking page load on Firefox mobile.
Replaced `autoplay` + `src` with an `IntersectionObserver` mechanism:
the video is only downloaded and played when it enters the viewport.
`preload="none"` prevents any download on initial page load.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/home.html`

---

### 3. Description adhesion en accordeon intelligent / Smart collapsible membership description

**FR :**
La description longue de la page d'adhesion est desormais tronquee automatiquement
si elle depasse ~10-12 lignes (250px). Un bouton "Lire la suite" / "Reduire" apparait.
Si la description est courte, elle s'affiche en entier sans bouton.

**EN:**
The long description on the membership page is now automatically truncated
if it exceeds ~10-12 lines (250px). A "Read more" / "Show less" button appears.
If the description is short, it displays fully without a button.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/membership/list.html`

---

### 4. Filtre par date sur la page evenements / Date filter on events page

**FR :**
Le dropdown "Trier par date" etait present dans le template mais non branche cote back.
Le parametre `?date=` est maintenant lu par la vue `list()`, et le dict `dated_events`
est filtre pour n'afficher que les evenements de la date selectionnee.
Le dropdown conserve toutes les dates disponibles meme quand un filtre est actif.
Le bouton affiche la date selectionnee en format lisible ("lundi 15 mars").

**EN:**
The "Sort by date" dropdown was present in the template but not wired to the backend.
The `?date=` parameter is now read by the `list()` view, and the `dated_events` dict
is filtered to display only events for the selected date.
The dropdown keeps all available dates even when a filter is active.
The button shows the selected date in readable format ("Monday March 15").

**Fichiers / Files:**
- `BaseBillet/views.py` — `EventMVT.list()` : lecture param `date`, filtrage du dict
- `BaseBillet/templates/faire_festival/views/event/list.html` — affichage date active, format ISO dans les liens

---

### 5. Correction erreur Sentry : confirmation email reservation expiree / Fix Sentry error: expired reservation email confirmation

**FR :**
Quand un utilisateur confirmait son email plus de 15 minutes apres une reservation gratuite
et que l'evenement etait presque complet, le signal levait un `ValueError` qui remontait
en `Http404` generique. L'utilisateur voyait une page 404 sans explication.
Desormais le `ValueError` est intercepte dans `emailconfirmation()` et le message
est affiche a l'utilisateur via `django.messages` sur la page d'accueil.
Les messages d'erreur sont maintenant traduits via `_()`.

**EN:**
When a user confirmed their email more than 15 minutes after a free reservation
and the event was nearly full, the signal raised a `ValueError` that surfaced
as a generic `Http404`. The user saw a 404 page with no explanation.
Now the `ValueError` is caught in `emailconfirmation()` and the message
is displayed to the user via `django.messages` on the homepage.
Error messages are now translated via `_()`.

**Fichiers / Files:**
- `BaseBillet/views.py` — `emailconfirmation()` : catch `ValueError` separement
- `BaseBillet/signals.py` — `activator_free_reservation()` : messages avec `_()`

---

### 6. Section produits retiree de la page evenement / Products section removed from event detail page

**FR :**
La section "Tickets and prices" a ete retiree de la page detail evenement du skin Faire Festival.
Le label "Intervenant-e-s" en dur a egalement ete supprime.

**EN:**
The "Tickets and prices" section was removed from the event detail page of the Faire Festival skin.
The hardcoded "Intervenant-e-s" label was also removed.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/event/retrieve.html`

---

### 7. Correction calcul paiement adhesion sans contribution / Fix membership payment calculation without contribution

**FR :**
Correction d'un crash quand `contribution_value` etait absente lors du calcul
du montant de paiement d'une adhesion. La valeur manquante est maintenant traitee gracieusement.

**EN:**
Fixed a crash when `contribution_value` was missing during membership payment amount calculation.
The missing value is now handled gracefully.

**Fichiers / Files:**
- Commit `50132e35`

---

### Autres ameliorations / Other improvements

- **Admin breadcrumb** : affiche le nom du produit au lieu du nom du tarif dans le fil d'Ariane
- **Admin product archive filter** : filtre pour afficher/masquer les produits archives
- **Redirect tarif → produit** : retour automatique vers le produit parent apres sauvegarde d'un tarif
- **Widget adhesions obligatoires** : passage en `MultipleHiddenInput`
- **Integration Fedow** : gestion d'erreur non-bloquante lors de la creation d'assets et validation d'adhesion
- **Newsletter** : ajout de l'URL newsletter dans le skin
- **Traductions** : nouvelles chaines FR/EN pour les filtres, messages d'erreur, et boutons

**Migration necessaire / Migration required:** Non

### 9. UX POS Session 5 — Responsive et ecrans tactiles / POS UX Session 5 — Responsive and touch screens

**FR :**
4 corrections CSS pour garantir le bon fonctionnement sur ecrans tactiles (Sunmi D3mini 1278x800) :
- Suppression `width`/`height` parasites sur `:root` dans la media query >1278px (contraignait `<html>` a 160px, casse potentiel sur Android WebView)
- Correction typo selecteur CSS `.categorie-nom` → `.category-nom` (le `font-size` ne s'appliquait jamais)
- Elargissement colonne bouton "-" du panier (12% → 16%) et `min-height: 44px` pour respecter le seuil tactile WCAG 2.5.8
- Ajout font-smoothing (`antialiased`) sur `body` pour le texte blanc sur fond sombre

**EN:**
4 CSS fixes to ensure proper behavior on touch screens (Sunmi D3mini 1278x800):
- Removed parasitic `width`/`height` on `:root` in >1278px media query (constrained `<html>` to 160px, potential breakage on Android WebView)
- Fixed CSS selector typo `.categorie-nom` → `.category-nom` (`font-size` was never applied)
- Widened cart "-" button column (12% → 16%) and `min-height: 44px` to meet WCAG 2.5.8 touch target threshold
- Added font-smoothing (`antialiased`) on `body` for white text on dark backgrounds

**Fichiers / Files:**
- `laboutik/templates/cotton/articles.html` — suppression width/height sur :root
- `laboutik/templates/cotton/categories.html` — correction selecteur .category-nom
- `laboutik/templates/cotton/addition.html` — grille 16/12/56/16 + min-height 44px
- `laboutik/static/css/modele00.css` — font-smoothing sur body

**Migration necessaire / Migration required:** Non

---

### 8. UX POS Session 2 — Polish articles et panier / POS UX Session 2 — Article and cart polish

**FR :**
Ameliorations visuelles de l'interface caisse (POS LaBoutik) :
- Badge quantite invisible quand 0 (opacity 0, transition 200ms au lieu d'afficher "0" en permanence)
- Feedback tactile au clic sur les articles (scale 0.95, 100ms)
- Placeholder "Panier vide" avec icone quand le panier est vide (disparait au premier article, reapparait au RESET)
- Alignement numerique propre (`font-variant-numeric: tabular-nums`) sur prix et quantites
- Anti-debordement des prix (`text-overflow: ellipsis`) y compris sur le breakpoint Sunmi 1278px
- Traductions i18n "Panier vide" / "Empty cart"

**EN:**
Visual improvements to the POS (LaBoutik) interface:
- Quantity badge hidden when 0 (opacity 0, 200ms transition instead of showing "0" permanently)
- Tactile feedback on article click (scale 0.95, 100ms)
- "Empty cart" placeholder with icon when cart is empty (disappears on first article, reappears on RESET)
- Clean numeric alignment (`font-variant-numeric: tabular-nums`) on prices and quantities
- Price overflow prevention (`text-overflow: ellipsis`) including on Sunmi 1278px breakpoint
- i18n translations "Panier vide" / "Empty cart"

**Fichiers / Files:**
- `laboutik/templates/cotton/articles.html` — CSS badge, feedback tactile, tabular-nums, overflow
- `laboutik/static/js/articles.js` — classList toggle badge-visible
- `laboutik/templates/cotton/addition.html` — placeholder HTML + CSS
- `laboutik/static/js/addition.js` — placeholder remove/recreate
- `locale/fr/LC_MESSAGES/django.po` — traduction "Panier vide"
- `locale/en/LC_MESSAGES/django.po` — traduction "Empty cart"

**Migration necessaire / Migration required:** Non

---

## v1.7.2 — Corrections production + Paiement admin adhesions + Avoir comptable

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

## v1.6.8 — Corrections Sentry + Import/Export Events

**Date :** Fevrier 2026
**Migration :** Non

---

### 1. Correction boucle infinie sur ProductFormField.save() / Fix infinite loop on ProductFormField.save()

**FR :**
Quand le label d'un champ de formulaire dynamique generait un slug de 64 caracteres ou plus,
la generation de nom unique entrait dans une boucle infinie (le suffixe etait tronque puis identique a chaque tour).
Le serveur finissait par un `SystemExit`.
On utilise maintenant un fragment d'UUID pour garantir l'unicite en un seul essai.

**EN:**
When a dynamic form field label produced a slug of 64+ characters,
the unique name generation entered an infinite loop (the suffix was truncated to the same value each iteration).
The server ended up with a `SystemExit`.
We now use a UUID fragment to guarantee uniqueness in a single attempt.

**Fichiers / Files:** `BaseBillet/models.py` — `ProductFormField.save()`

---

### 2. Correction timeout cashless / Fix cashless ReadTimeout

**FR :**
L'appel HTTP vers le serveur cashless avait un timeout de 1 seconde, trop court en production.
Passe a 10 secondes.

**EN:**
The HTTP call to the cashless server had a 1-second timeout, too short for production.
Increased to 10 seconds.

**Fichiers / Files:** `BaseBillet/tasks.py`

---

### 3. Correction creation de tenant en doublon / Fix duplicate tenant creation

**FR :**
Quand un utilisateur cliquait deux fois sur le lien de confirmation email,
la creation du tenant pouvait echouer car le lien `WaitingConfiguration → tenant` n'etait pas assigne assez tot.
On assigne maintenant le tenant des sa creation, et on ajoute un fallback qui repare le lien si le tenant existe deja.

**EN:**
When a user clicked the email confirmation link twice,
tenant creation could fail because the `WaitingConfiguration → tenant` link was not assigned early enough.
We now assign the tenant immediately after creation, and added a fallback that repairs the link if the tenant already exists.

**Fichiers / Files:** `BaseBillet/validators.py`, `BaseBillet/views.py`

---

### 4. Correction carte perdue 404 / Fix lost_my_card 404

**FR :**
Quand un utilisateur cliquait deux fois sur "carte perdue", le deuxieme appel a Fedow renvoyait un 404
car la carte etait deja detachee. On attrape maintenant cette erreur proprement.

**EN:**
When a user double-clicked "lost my card", the second call to Fedow returned a 404
because the card was already detached. We now catch this error gracefully.

**Fichiers / Files:** `BaseBillet/views.py` — `admin_lost_my_card`, `lost_my_card`

---

### 5. Correction formulaire adhesion admin sans wallet / Fix admin membership form without wallet

**FR :**
Dans l'admin, le formulaire d'adhesion plantait si on validait le numero de carte
sans avoir d'abord renseigne un email valide (attribut `user_wallet_serialized` absent).
On verifie maintenant que le wallet existe avant d'y acceder.

**EN:**
In the admin, the membership form crashed when validating the card number
without first providing a valid email (missing `user_wallet_serialized` attribute).
We now check the wallet exists before accessing it.

**Fichiers / Files:** `Administration/admin_tenant.py` — `MembershipForm.clean_card_number()`

---

### 6. Verification SEPA Stripe avant activation / Stripe SEPA capability check before activation

**FR :**
Activer le paiement SEPA dans la configuration alors que le compte Stripe Connect n'a pas la capacite SEPA
provoquait une erreur au moment du paiement. On verifie maintenant la capacite SEPA via l'API Stripe
au moment de la sauvegarde de la configuration. Si le checkout echoue malgre tout, le SEPA est desactive automatiquement.

**EN:**
Enabling SEPA payment in the configuration while the Stripe Connect account lacked SEPA capability
caused an error at checkout time. We now verify SEPA capability via the Stripe API
when saving the configuration. If checkout still fails, SEPA is automatically disabled.

**Fichiers / Files:** `BaseBillet/models.py` — `Configuration.check_stripe_sepa_capability()`, `PaiementStripe/views.py`

---

### 7. Tri des produits par poids / Product weight ordering

**FR :**
Les prix affiches sur la page evenement ignoraient le poids (`poids`) du produit parent.
Les produits sont maintenant tries par `product__poids`, puis `order`, puis `prix`.

**EN:**
Prices displayed on the event page ignored the parent product's weight (`poids`).
Products are now sorted by `product__poids`, then `order`, then `prix`.

**Fichiers / Files:** `BaseBillet/views.py`

---

### 8. Import/Export CSV des evenements (PR #351) / CSV import/export for events (PR #351)

**FR :**
Contribution de @AoiShidaStr : ajout de l'import/export CSV des evenements depuis l'admin Django.
Ameliore ensuite avec : export de l'adresse postale par nom (pas par ID),
lignes identiques ignorees a l'import, et rapport des lignes ignorees.

**EN:**
Contribution by @AoiShidaStr: added CSV import/export for events from the Django admin.
Then improved with: postal address exported by name (not ID),
unchanged rows skipped on import, and skipped rows reported.

**Fichiers / Files:** `Administration/admin_tenant.py` — `EventResource`

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*

---

## v1.6.4 — Migration requise

**Date :** Fevrier 2025
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 1. Moteur de skin configurable / Configurable skin engine

**FR :**
Nous pouvons maintenant choisir son theme graphique depuis l'administration.
Un nouveau champ `skin` a ete ajoute au modele `Configuration`.
Le systeme cherche d'abord le template dans le dossier du skin choisi,
puis retombe automatiquement sur le theme par defaut (`reunion`) si le template n'existe pas.
Cela permet de creer un nouveau skin en ne surchargeant que les templates souhaités.

**EN:**
Each venue can now choose its visual theme from the admin panel.
A new `skin` field has been added to the `Configuration` model.
The system first looks for the template in the chosen skin folder,
then automatically falls back to the default theme (`reunion`) if the template does not exist.
This allows creating a new skin by only overriding the desired templates.

**Details techniques / Technical details:**

- Nouveau champ `Configuration.skin` (CharField, defaut `"reunion"`)
  New field `Configuration.skin` (CharField, default `"reunion"`)
- Nouvelle fonction `get_skin_template(config, path)` avec logique de fallback
  New function `get_skin_template(config, path)` with fallback logic
- Ajout du skin `faire_festival` (theme brutaliste) avec templates et CSS dedies
  Added `faire_festival` skin (brutalist theme) with dedicated templates and CSS
- Migration : `BaseBillet/migrations/0195_configuration_skin.py`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — resolution dynamique des templates
- `BaseBillet/models.py` — champ `skin` sur `Configuration`
- `BaseBillet/templates/faire_festival/` — nouveau dossier skin complet
- `BaseBillet/static/faire_festival/css/` — styles dedies
- `Administration/admin_tenant.py` — champ expose dans l'admin

---

### 2. Pre-remplissage des formulaires d'adhesion / Membership form pre-fill

**FR :**
Quand un utilisateur connecte remplit un formulaire d'adhesion,
le systeme recherche sa derniere adhesion au meme produit.
Si une adhesion precedente existe, tous les champs du formulaire dynamique
sont pre-remplis avec les valeurs deja saisies.
L'utilisateur n'a plus a re-saisir son adresse, telephone, etc. a chaque renouvellement.

**EN:**
When a logged-in user fills out a membership form,
the system looks up their most recent membership for the same product.
If a previous membership exists, all dynamic form fields
are pre-filled with the previously entered values.
The user no longer has to re-enter their address, phone, etc. on each renewal.

**Details techniques / Technical details:**

- Recherche de la derniere `Membership` du user pour le meme produit avec `custom_form` non vide
  Lookup of the user's latest `Membership` for the same product with non-empty `custom_form`
- Construction d'un dict `prefill` qui mappe `field.name` vers la valeur stockee
  Builds a `prefill` dict mapping `field.name` to the stored value
- Tous les types de champs supportes : texte, textarea, select, radio, checkbox, multi-select
  All field types supported: text, textarea, select, radio, checkbox, multi-select
- Nouveau filtre de template `get_item` pour acceder aux cles d'un dict dans le template
  New `get_item` template filter for dict key lookup in templates

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — logique de pre-remplissage dans `MembershipMVT.retrieve()`
- `BaseBillet/templates/reunion/views/membership/form.html` — affichage des valeurs pre-remplies
- `BaseBillet/templatetags/tibitags.py` — filtre `get_item`

---

### 3. Edition des formulaires dynamiques depuis l'admin / Admin custom form field editing

**FR :**
Les administrateurs peuvent maintenant modifier les reponses d'un formulaire dynamique
directement depuis la fiche adhesion dans l'admin, sans passer par le shell ou la base de donnees.
Ils peuvent aussi ajouter des champs libres (non definis dans le produit).
Tout se fait en HTMX, sans rechargement de page.

**EN:**
Admins can now edit dynamic form responses
directly from the membership detail page in the admin panel, without using the shell or database.
They can also add free-form fields (not defined in the product).
Everything works via HTMX, without page reload.

**Details techniques / Technical details:**

- 5 nouvelles actions HTMX sur `MembershipMVT` :
  5 new HTMX actions on `MembershipMVT`:
  - `admin_edit_json_form` (GET) — affiche le formulaire editable / shows editable form
  - `admin_cancel_edit` (GET) — annule l'edition / cancels editing
  - `admin_change_json_form` (POST) — valide et sauvegarde / validates and saves
  - `admin_add_custom_field_form` (GET) — formulaire d'ajout de champ / add field form
  - `admin_add_custom_field` (POST) — sauvegarde le nouveau champ / saves new field
- Validation des champs requis, anti-doublon sur les labels, sanitisation HTML via `nh3`
  Required field validation, duplicate label check, HTML sanitization via `nh3`
- Chaque type de champ (`ProductFormField`) est rendu avec le bon widget HTML
  Each field type (`ProductFormField`) is rendered with the appropriate HTML widget
- Support des champs "orphelins" (presents dans le JSON mais pas dans le produit)
  Support for "orphan" fields (present in JSON but not defined in the product)
- Protection par `TenantAdminPermission`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — actions HTMX
- `Administration/utils.py` — fonction `clean_text()` (sanitisation `nh3`)
- `Administration/templates/admin/membership/custom_form.html` — vue lecture avec boutons
- `Administration/templates/admin/membership/partials/custom_form_edit.html` — formulaire editable
- `Administration/templates/admin/membership/partials/custom_form_edit_success.html` — confirmation
- `Administration/templates/admin/membership/partials/custom_form_add_field.html` — ajout de champ
- `BaseBillet/models.py` — correction de `ProductFormField.save()` (ne pas ecraser `name`)
- `BaseBillet/validators.py` — recherche de cle robuste avec fallback UUID/label

---

### Autres ameliorations / Other improvements

- **Duplication de produit** : nouvelle action admin pour dupliquer un produit existant
  New admin action to duplicate an existing product
- **Validation anti-doublon d'evenement** : empeche la creation d'evenements avec le meme nom et la meme date
  Prevents creating events with same name and date
- **Accessibilite** : ameliorations `aria-label`, `visually-hidden`, meilleur support des themes clair/sombre
  Accessibility improvements: `aria-label`, `visually-hidden`, better light/dark theme support
- **Tests E2E** : nouveau test Playwright pour le cycle complet d'edition des formulaires dynamiques
  New Playwright test for the full dynamic form editing cycle

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*
