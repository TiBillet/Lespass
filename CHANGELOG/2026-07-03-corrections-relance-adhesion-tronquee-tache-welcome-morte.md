# Corrections : relance d'adhésion tronquée, tâche welcome morte, bouton fermer du panneau ticket / Fixes: truncated membership reminder, dead welcome task, ticket panel close button

**Date :** 2026-07-03
**Migration :** Non / No

**Quoi / What :** Trois corrections de bugs découverts pendant l'audit de la session skins.

**1. `membership_renewal_reminder` s'arrêtait au premier adhérent / stopped at the first member**
- Le `return mail.sended` était DANS la boucle `for membership` : seul le premier
  adhérent (du premier tenant) recevait l'email de relance, puis la tâche Celery
  se terminait. Le `return` est supprimé : chaque adhérent est traité, une erreur
  d'envoi est loggée et n'interrompt plus les suivants.
- Correction aussi du message de log copié-collé trompeur (« send_welcome_email »
  → « membership_renewal_reminder »).

**2. Suppression de la tâche morte `send_welcome_email` / dead task removed**
- Jamais appelée nulle part, et son template `emails/welcome/welcome_email.html`
  n'existe pas (l'erreur `TemplateDoesNotExist` était avalée par le `try/except`).
  Le seul `welcome_email.html` existant est l'email legacy de création d'instance
  (`reunion/views/tenant/emails/`), au contexte incompatible — remplacé depuis par
  `onboard/emails/ready.html`. La tâche est supprimée.

**3. Bouton fermer du panneau ticket inopérant / ticket panel close button broken**
- `data-bs-dismiss="ticketPanel"` (valeur invalide) → `data-bs-dismiss="offcanvas"`.
  Le bouton ✕ de l'offcanvas `#ticketPanel` (page « Mes réservations ») ferme
  désormais le panneau.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/tasks.py` | Suppression `send_welcome_email` ; fix `return` dans la boucle de `membership_renewal_reminder` + log |
| `BaseBillet/templates/reunion/views/account/reservations.html` | `data-bs-dismiss="offcanvas"` sur le bouton close |



**Date :** 2026-06-30
**Migration :** Oui / Yes — `BaseBillet/migrations/0220_lignearticle_idempotency_key_and_more.py`

**Quoi / What :** Trois corrections sur l'API v2, remontées par un intégrateur.

**1. Partager un produit sur plusieurs événements / Share a product across several events**
- `isRelatedTo` accepte désormais une **liste** (UUID et/ou objets schema.org) au
  `POST /api/v2/products/` : le produit est attaché à tous les events listés.
  Avant, une liste renvoyait 201 mais n'attachait rien.
- Nouvelle route `POST /api/v2/events/{uuid}/link-product/` : attache un (ou
  plusieurs) produit(s) **déjà créé(s)** à un événement (M2M `Event.products`),
  sans en créer un nouveau. Accepte `productId`, `productIds`, `product`, `products`.

**2. Double ticket sur un sous-événement / Double ticket on a sub-event**
- Un sous-événement (avec `parent`) est forcé en catégorie `ACTION`. Le
  `TicketCreator` créait alors DEUX tickets quand l'event avait aussi un produit
  réservable : le bon, plus un ticket « bénévole » vide (sans `pricesold`, donc
  `identifier` vide en sortie). Désormais `method_A` n'est appelé que si aucun
  produit n'a été traité (`products_dict` vide).

**3. Sécurité idempotence de la recharge cadeau / Gift-refill idempotency hardening**
- `POST /api/v2/wallet-refills/` : l'`Idempotency-Key` est désormais **obligatoire**
  (400 si absente) et stockée en **base** (`LigneArticle.idempotency_key`,
  contrainte d'unicité = verrou atomique contre les requêtes concurrentes), au
  lieu d'un cache best-effort. Même clé + même corps → 208 ; même clé + corps
  **différent** → 409 ; une clé dont la tentative précédente a échoué (Fedow) peut
  être ré-essayée. Résout le risque de double-crédit (TOCTOU + réutilisation de clé).

**Pourquoi / Why :** Limites/risques signalés sur l'API v2 (réutilisation produit,
tickets parasites, double-crédit possible sur recharge).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/serializers.py` | `isRelatedTo` en liste (`_extract_event_uuids`), boucle d'attachement ; nettoyage ruff |
| `api_v2/views.py` | route `link_product` ; refonte idempotence wallet-refill (verrou DB, 208/409/retry) |
| `api_v2/openapi-schema.yaml` | doc route `link-product`, `isRelatedTo` liste, header `Idempotency-Key` requis + 409 |
| `api_v2/README.md` | doc idempotence en base, header obligatoire |
| `BaseBillet/validators.py` | `method_A` appelé seulement si `products_dict` vide |
| `BaseBillet/models.py` | `LigneArticle.idempotency_key` + `UniqueConstraint` conditionnelle |
| `tests/pytest/test_api_v2_product_link_event.py` | **nouveau** — 6 tests (multi-events + link-product) |
| `tests/pytest/test_reservation_subevent_tickets.py` | **nouveau** — 4 tests (1 ticket par cas) |
| `tests/pytest/test_api_v2_wallet_refill.py` | + 4 tests idempotence (208/409/400/retry), maj des tests existants |

### Migration
- **Migration nécessaire / Migration required :** Oui / Yes
- `migrate_schemas --executor=multiprocessing` (ajout colonne `idempotency_key`
  nullable + contrainte unique conditionnelle sur `LigneArticle` ; additif, sans risque).

### i18n
- Nouvelles chaînes `_()` à traduire (FR source) : `Idempotency-Key header is required.`,
  `Idempotency-Key already used with different parameters.`,
  `A refill with this key is already in progress.`,
  `No product identifier provided. Use productId or productIds.`
  → à passer au workflow `makemessages` / `compilemessages` (côté mainteneur).
