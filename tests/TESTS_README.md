# Tests — Lespass (TiBillet)

## Prerequis : installer Playwright (E2E uniquement)

Les tests E2E utilisent Playwright Python avec Chromium headless.
Les navigateurs ne sont pas inclus dans l'image Docker — il faut les installer
une fois apres chaque rebuild du container :

```bash
# Installer Chromium pour Playwright dans le container
docker exec lespass_django poetry run playwright install chromium
```

Si l'installation echoue avec des erreurs de dependances systeme :

```bash
# Installer les dependances systeme manquantes puis Chromium
docker exec lespass_django poetry run playwright install --with-deps chromium
```

> **Note** : cette etape n'est necessaire que pour les tests E2E (`tests/e2e/`).
> Les tests pytest DB-only (`tests/pytest/`) n'ont pas besoin de Playwright.

## Lancer les tests

```bash
# --- Mode rapide : tests unitaires DB-only (~30s) ---
docker exec lespass_django poetry run pytest tests/pytest/ -q

# --- Mode lent : tests E2E navigateur (~3 min) ---
# Prerequis : serveur Django actif via Traefik
docker exec lespass_django poetry run pytest tests/e2e/ -v -s

# --- Tout d'un coup (~3.5 min) ---
docker exec lespass_django poetry run pytest tests/ -q

# --- Raccourcis utiles ---
# Relancer uniquement les tests qui ont echoue au run precedent
docker exec lespass_django poetry run pytest tests/ --last-failed

# S'arreter au premier echec
docker exec lespass_django poetry run pytest tests/ --stepwise

# --- Couverture de code (pytest-cov) ---
# Rapport couverture sur les tests DB-only (pas les E2E — serveur separe)
docker exec lespass_django poetry run pytest tests/pytest/ \
  --cov=BaseBillet --cov=laboutik --cov=crowds --cov=fedow_core \
  --cov=PaiementStripe --cov=AuthBillet --cov=Administration \
  --cov=ApiBillet --cov=api_v2 \
  --cov-report=term-missing -q

# Rapport HTML (ouvre htmlcov/index.html dans le navigateur)
docker exec lespass_django poetry run pytest tests/pytest/ \
  --cov=BaseBillet --cov=laboutik --cov=crowds --cov=fedow_core \
  --cov=PaiementStripe --cov=AuthBillet --cov=Administration \
  --cov=ApiBillet --cov=api_v2 \
  --cov-report=html -q
```

> **Note couverture** : coverage ne mesure que les tests pytest (DB-only).
> Les tests E2E pilotent un navigateur vers un serveur Django separe — le code
> s'execute dans un autre processus, invisible pour coverage.
> Couverture actuelle : **44% global**, avec les modeles metier a 70-97%
> et les taches Celery / vues legacy a 11-25%.

## Deux suites complementaires

### Tests pytest (DB-only) — `tests/pytest/`

**186 tests, ~30 secondes.**

Testent la logique **Python/Django** : modeles, serializers, vues, API, validations serveur, triggers post-paiement. Utilisent le client Django in-process (`self.client`) — pas de reseau, pas de navigateur.

Stripe est **mocke** cote serveur (`@patch("stripe.checkout.Session.create")`) pour eviter les appels reseau.

### Tests E2E (navigateur) — `tests/e2e/`

**36 tests, ~3 minutes.**

Testent le comportement **JavaScript/CSS/navigateur** : validation HTML5, web components (`bs-counter`), SweetAlert2, HTMX swaps, rendu visuel POS, simulation NFC, navigation cross-tenant.

Utilisent Playwright Python avec Chromium headless. Le serveur Django doit tourner (via Traefik).

### Pourquoi deux suites ?

| Question | Reponse |
|----------|---------|
| Ca teste du Python ? | → pytest DB-only (rapide, isole) |
| Ca teste du JS/CSS/navigateur ? | → E2E Playwright (navigateur reel) |
| Ca teste les deux ? | → pytest pour le serveur, E2E pour le rendu |

Les tests pytest ne peuvent pas executer de JavaScript (pas de navigateur).
Les tests E2E ne peuvent pas faire de ROLLBACK DB (pas de LiveServer ephemere avec django-tenants).

---

## Lancer par domaine

### Adhesions / Memberships

```bash
# Logique metier (creation, validation, recurring, cancel, prix libre, formulaires dynamiques)
docker exec lespass_django poetry run pytest tests/pytest/test_membership_*.py tests/pytest/test_adhesions_*.py tests/pytest/test_admin_membership_*.py tests/pytest/test_sepa_*.py -v

# Paiement Stripe mock (anonyme, SSA, validation manuelle, multi-tarifs, prix zero)
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_membership_*.py -v

# Validation JS navigateur (email mismatch, champs dynamiques, prix libre vide)
docker exec lespass_django poetry run pytest tests/e2e/test_membership_validations.py -v -s
```

### Evenements / Reservations

```bash
# Logique metier (creation, limites, annulation, adhesion obligatoire, duplication)
docker exec lespass_django poetry run pytest tests/pytest/test_event_*.py tests/pytest/test_reservation_*.py tests/pytest/test_admin_reservation_*.py tests/pytest/test_product_duplication.py -v

# Paiement Stripe mock (gratuit, payant, options, formulaires dynamiques)
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_reservation.py -v

# Validation JS navigateur (bs-counter, email mismatch, code promo)
docker exec lespass_django poetry run pytest tests/e2e/test_reservation_validations.py -v -s
```

### API v2

```bash
# CRUD events, products, reservations, memberships, addresses, crowds
docker exec lespass_django poetry run pytest tests/pytest/test_event_create.py tests/pytest/test_events_list.py tests/pytest/test_event_retrieve.py tests/pytest/test_event_delete.py tests/pytest/test_event_create_extended.py tests/pytest/test_event_images.py tests/pytest/test_event_link_address.py tests/pytest/test_postal_address_*.py tests/pytest/test_reservation_create.py tests/pytest/test_membership_create.py tests/pytest/test_crowd_*.py -v
```

### LaBoutik / POS (caisse)

```bash
# Modeles, vues, navigation, serializers
docker exec lespass_django poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_caisse_*.py tests/pytest/test_paiement_*.py tests/pytest/test_cloture_*.py tests/pytest/test_retour_carte_*.py tests/pytest/test_laboutik_*.py -v

# E2E : paiements (especes, CB, NFC), adhesion NFC (6 chemins), tuiles visuelles
docker exec lespass_django poetry run pytest tests/e2e/test_pos_*.py -v -s
```

### Crowds (financement participatif)

```bash
# Logique metier + Stripe mock
docker exec lespass_django poetry run pytest tests/pytest/test_crowd_*.py tests/pytest/test_crowds_*.py tests/pytest/test_stripe_crowds.py -v

# E2E : popup SweetAlert2 (pro-bono, covenant, mark completed)
docker exec lespass_django poetry run pytest tests/e2e/test_crowds_participation.py -v -s
```

### Fedow (monnaie locale, tokens, federation)

```bash
# Assets, tokens, transactions, isolation cross-tenant, federation invitation
docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py tests/pytest/test_verify_transactions.py -v

# E2E : federation cross-tenant (Lespass ↔ Chantefrein, Tom Select, invitation)
docker exec lespass_django poetry run pytest tests/e2e/test_asset_federation.py -v -s
```

### Admin Django

```bash
# Dashboard, changelist, proxy products, audit, credit notes, configuration
docker exec lespass_django poetry run pytest tests/pytest/test_admin_*.py -v
```

---

## Couverture : ce qui EST teste

### Adhesions (25 tests pytest + 1 E2E + 5 Stripe mock)
- Creation simple, recurrente, AMAP, SSA avec formulaire
- Validation manuelle (prix solidaire)
- Annulation avec/sans avoir
- Liste admin par statut (ONCE, ADMIN, FREE)
- Paiement admin especes/offert
- Custom form fields (affichage admin)
- M2M adhesions obligatoires sur Price
- Compte utilisateur (affichage adhesions, bouton annulation)
- Prix libre (montant custom, multi-tarifs, zero euro)
- Formulaire dynamique cycle complet (6 types de champs)
- Protection anti-doublon SEPA
- Stripe mock : anonyme, SSA tokens, validation manuelle, prix libre, multi-tarifs, zero prix

### Evenements / Reservations (20 tests pytest + 1 E2E + 4 Stripe mock)
- CRUD API v2 (create, list, retrieve, delete, extended, images, link address)
- Quick create + doublon rejete
- Limites : stock epuise, max par utilisateur, adhesion requise
- Annulation + avoirs (double annulation bloquee)
- Duplication produit avec tarifs et form fields
- Adhesion obligatoire bloque le tarif
- Options radio/checkbox sur evenement
- Formulaires dynamiques (shortText, multiSelect, etc.)
- Stripe mock : gratuit, payant, options, formulaires dynamiques

### LaBoutik / POS (60+ tests pytest + 17 E2E)
- Modeles : CategorieProduct, Product POS, POSProduct proxy, Price.asset, PointDeVente, CartePrimaire, Table
- Navigation : tag NFC, carte primaire valide/inconnue/non-primaire, auth 403
- Vues donnees : produits charges depuis la DB
- Paiements especes + CB (2 consecutifs, fix HTMX reset)
- Paiements NFC cashless (solde suffisant, carte inconnue, solde insuffisant, reset NFC→cash, NFC→NFC, multi-articles + solde exact)
- **Identification client unifiee** (session 05) :
  - Flag `panier_necessite_client` (5 tests logique pure : VT seul, RE, AD, mixte, email masque)
  - `moyens_paiement()` : ecran identification adaptatif (7 tests HTTP : VT normal, RE NFC-only, AD NFC+email, mixte, titres)
  - `identifier_client()` : NFC carte connue/anonyme/inconnue, email valide/invalide, recapitulatif articles (9 tests HTTP)
  - Paniers mixtes : AD+VT cashless, VT+RE especes, VT+RE+AD CB, VT+RE cashless rejete (4 tests HTTP)
  - Verification LigneArticle en DB : payment_method, sale_origin, amount, qty, status, carte, email, membership (3 tests HTTP)
  - E2E 8 chemins identification : email→especes, email→CB, NFC user→especes, NFC user→cashless, NFC anonyme→form, NFC anonyme→especes, retour identification, retour formulaire
  - E2E verification LigneArticle : email correct, payment_method (CA/CC), sale_origin=LB, status=V, carte=None (3 tests enrichis)
- Adhesion NFC (6 chemins identification : NFC/email × user connu/anonyme + 2 boutons retour)
- Cloture caisse (totaux, transactions, tables liberees, rapport JSON, filtre datetime, double cloture, annulation commandes)
- Export (PDF, CSV, endpoint 200/404, envoi email avec pieces jointes)
- Securite : aria-live, XSS echappement, validation prix libre min
- Tuiles visuelles : background-color, badges categorie, footer prix, icones menu, couleurs specifiques, data-testid, filtre categorie
- **Billetterie POS** (session 07) :
  - Extraction articles billet : ID composite `event__price`, article standard dans PV BILLETTERIE (2 tests unitaires)
  - Creation Reservation + Ticket : especes sans email (to_mail=False), avec email (to_mail=True), status NOT_SCANNED (6 tests unitaires)
  - Jauge atomique : event complet → ValueError + rollback, Price.stock epuise → ValueError (2 tests unitaires)
  - Panier mixte : biere + billet → 2 LigneArticle + 1 Ticket (1 test unitaire)
  - Flow HTTP complet : moyens_paiement → identification "Billetterie" → recap "Billet" → payer especes → Reservation(V) + Ticket(K) en DB (4 tests HTTP)
  - E2E 5 scenarios : tuiles visibles avec jauge, clic → panier, VALIDER → identification, email → especes → Ticket(K) en DB, panier mixte biere+billet

### Fedow (15 tests pytest + 1 E2E)
- Assets : creation, categories (TLF, TNF, FED, TIM, FID)
- Tokens : creation, centimes
- Transactions : creation, SALE, id BigAutoField auto-increment
- Wallet : solde, credit, debit, solde insuffisant
- Isolation cross-tenant (pas de leak)
- Tenant sur transaction
- Federation : pending_invitations, accept_invitation, visibilite queryset admin
- E2E : flow complet invitation cross-tenant (12 etapes, Tom Select, 2 sous-domaines)
- Verification integrite (verify_transactions command)

### Crowds (10 tests pytest + 1 E2E)
- CRUD API v2 (initiative create, list, budget item, votes/participations)
- Page summary (data-testid)
- Contribution Stripe direct_debit (mock)
- Contribution anonyme bloquee
- E2E : popup participation SweetAlert2 (pro-bono, covenant, montant, mark completed, duree)

### Admin (30 tests pytest)
- Dashboard, changelist (HumanUser, Paiement_stripe, Initiative, Event, Price, Membership)
- Filtres admin (client_admin, initiate_payment)
- Configuration page
- Proxy products (TicketProduct, MembershipProduct, formulaires restreints)
- Avoir/credit note (creation + anti-doublon)
- Audit fixes (tous les changelist accessibles)

### Auth / Theme (2 + 3 E2E)
- Login flow complet (TEST MODE)
- Validation format email
- Toggle theme dark/light
- Switch langue fr/en
- Sync preferences (profil admin)

### Stripe (17 pytest mock + 2 E2E)
- Adhesions : anonyme, SSA tokens, validation manuelle, prix libre, multi-tarifs, zero prix, formulaire dynamique
- Reservations : gratuit, payant, options, formulaires dynamiques
- Crowds : contribution direct_debit
- 2 smoke tests E2E : vrai checkout Stripe (carte 4242, retour confirmation)

### Divers
- Validation numerique overflow (max_digits=6)
- Discovery/PIN pairing (generation PIN, claim, reclaim rejete)
- Adresses postales CRUD + images
- Prix libre validation (12 tests)
- Retour carte + recharges

---

## Couverture : ce qui N'EST PAS teste

### Critique (risque eleve)

| Domaine | Detail |
|---------|--------|
| **Webhook Stripe** (`POST /webhook_stripe/`) | Le handler qui recoit les evenements Stripe (checkout.session.completed, invoice.paid, etc.) n'est jamais appele directement dans les tests. Le flow est teste jusqu'a `update_checkout_status()` mais pas le POST HTTP du webhook. |
| **OAuth/SSO** | Le flow Authlib/Communecter (`/api/user/oauth`) n'a aucun test. |
| **Taches Celery** (~40 taches) | Aucune tache Celery n'est testee en isolation : `send_membership_invoice_to_email`, `webhook_reservation`, `membership_renewal_reminder`, `send_to_brevo`, `send_to_ghost`, etc. |
| **WebSocket** (`wsocket/`) | Les consumers Django Channels ne sont pas testes. |

### Important (risque moyen)

| Domaine | Detail |
|---------|--------|
| **Renouvellement abonnement Stripe** | Le webhook `invoice.paid` et le cycle de renouvellement ne sont pas testes. |
| **SEPA** | La creation de mandat et les scenarios d'echec (`async_payment_failed`) ne sont pas testes. |
| **Remboursement Stripe** | L'appel `stripe.Refund.create()` et le webhook `charge.refunded` ne sont pas testes. |
| **Scan tickets** (QR/barcode) | Le scan de billets n'est pas teste (NFC adhesion oui, mais pas QR tickets). |
| **Isolation cross-tenant** (BaseBillet) | Seul fedow_core a un test d'isolation explicite. Pas de test verifiant qu'un tenant ne voit pas les Product/Event/Reservation d'un autre. |

### Souhaitable (risque faible)

| Domaine | Detail |
|---------|--------|
| **Carrousel** | Les templates carrousel ne sont pas testes. |
| **PDF tickets/factures** | Seul le PDF de cloture est teste. Les PDF de billets et factures ne le sont pas. |
| **Optimisation images** (stdimage) | L'upload est teste, mais pas le redimensionnement ni le nettoyage a la suppression. |
| **Rate limiting** | Le code de throttling est commente dans le code source. Pas de tests. |
| **Import V1→V2** | La migration des anciens tenants (Phase 6-7 du plan de fusion) n'est pas testee. |
| **Commandes tables** (mode restaurant) | Feature UI incomplete. Tests supprimes volontairement. A recreer quand la feature sera prete. |

---

## Architecture des fichiers

```
tests/
├── pytest/                    # 186 tests DB-only (~30s)
│   ├── conftest.py            # Fixtures : api_client, admin_user, tenant, mock_stripe
│   ├── test_admin_*.py        # Admin Django (dashboard, changelist, proxy, audit)
│   ├── test_event_*.py        # Evenements (CRUD API v2, quick create, adhesion obligatoire)
│   ├── test_membership_*.py   # Adhesions (creation, validation, compte)
│   ├── test_reservation_*.py  # Reservations (limites, creation)
│   ├── test_pos_*.py          # POS modeles et vues
│   ├── test_paiement_*.py     # Paiements (especes, CB, cashless)
│   ├── test_cloture_*.py      # Cloture caisse (totaux, export PDF/CSV)
│   ├── test_stripe_*.py       # Stripe mock (adhesions, reservations, crowds)
│   ├── test_fedow_core.py     # Fedow (assets, tokens, transactions, federation)
│   ├── test_crowd_*.py        # Crowds API v2
│   ├── test_websocket_jauge.py  # WebSocket : consumer, ping/pong, broadcast jauge
│   └── ...
├── e2e/                       # 36 tests navigateur (~3 min)
│   ├── conftest.py            # Fixtures : playwright, browser, page, login_as, pos_page, django_shell, fill_stripe_card
│   ├── test_login.py          # Login flow
│   ├── test_membership_validations.py  # Validation JS adhesion
│   ├── test_reservation_validations.py # Validation JS reservation
│   ├── test_crowds_participation.py    # SweetAlert2 crowds
│   ├── test_pos_paiement.py           # POS paiements (especes, CB, NFC)
│   ├── test_pos_adhesion_nfc.py       # POS adhesion 6 chemins NFC
│   ├── test_pos_tiles_visual.py       # POS tuiles visuelles
│   ├── test_asset_federation.py       # Federation cross-tenant
│   ├── test_stripe_smoke.py           # Smoke tests Stripe (vrai checkout)
│   └── test_theme_language.py         # Theme et langue
└── SESSIONS/                  # Fiches des 11 sessions de migration
    ├── PLAN_TEST.md           # Strategie de tests detaillee
    ├── README.md              # Vue d'ensemble des sessions
    └── 01_..11_*.md           # Fiches individuelles
```

---

## Metriques

| Metrique | Valeur |
|----------|--------|
| Tests pytest (DB-only) | 234 |
| Tests E2E (navigateur) | 41 |
| **Total** | **275** |
| Temps pytest | ~70s |
| Temps E2E | ~4 min |
| **Temps total** | **~5 min** |

---

## Tests WebSocket (Django Channels)

### Dependance

Les tests async du consumer necessitent `pytest-asyncio` (groupe dev) :
```bash
docker exec lespass_django poetry add --group dev pytest-asyncio
```

### 3 approches selon ce qu'on teste

| Je teste... | Outil | Exemple |
|-------------|-------|---------|
| **Le consumer** (connexion, ping/pong, groups) | `channels.testing.WebsocketCommunicator` + `@pytest.mark.asyncio` | `test_consumer_ping_pong` |
| **Le calcul de broadcast** (jauges par Price/Event) | `unittest.mock.patch("wsocket.broadcast.broadcast_html")` | `test_broadcast_jauge_calcule_par_price` |
| **Le signal** (Ticket.post_save → on_commit → broadcast) | `unittest.mock.patch("BaseBillet.signals._safe_broadcast_jauge")` | `test_signal_ticket_declenche_broadcast` |

### Tests du consumer (WebsocketCommunicator)

Le `WebsocketCommunicator` simule une connexion WebSocket sans navigateur ni Redis.
Il faut fournir le scope manuellement (url_route, tenant) :

```python
import pytest
from unittest.mock import MagicMock
from channels.testing import WebsocketCommunicator
from wsocket.consumers import LaboutikConsumer

@pytest.mark.asyncio
async def test_consumer_ping_pong():
    mock_tenant = MagicMock()
    mock_tenant.schema_name = "lespass"

    communicator = WebsocketCommunicator(
        LaboutikConsumer.as_asgi(),
        "/ws/laboutik/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/",
    )
    communicator.scope["url_route"] = {
        "kwargs": {"pv_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    }
    communicator.scope["tenant"] = mock_tenant

    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"type": "ping", "client_ts": 1700000000000})
    response = await communicator.receive_json_from(timeout=2)
    assert response["type"] == "pong"
    assert response["client_ts"] == 1700000000000

    await communicator.disconnect()
```

Points importants :
- `@pytest.mark.asyncio` obligatoire (pas dans une classe `TestCase`)
- `communicator.scope["url_route"]` doit etre fourni manuellement (le URLRouter n'est pas utilise)
- `communicator.scope["tenant"]` : mock suffit, pas besoin d'un vrai Client en DB
- `receive_nothing(timeout=0.5)` pour verifier qu'aucun message n'est envoye
- Toujours appeler `await communicator.disconnect()` en fin de test

### Tests du broadcast (mock broadcast_html)

On mocke `broadcast_html` pour intercepter le contexte sans envoyer a Redis :

```python
from unittest.mock import patch
from wsocket.broadcast import broadcast_jauge_event

def test_broadcast_jauge(event_fixture):
    with patch("wsocket.broadcast.broadcast_html") as mock:
        broadcast_jauge_event(event)

    context = mock.call_args.kwargs["context"]
    assert context["event"]["places_vendues"] == 2
    assert len(context["tuiles"]) == 2  # 1 par Price
```

Cela teste la logique de calcul (jauge par Price vs par Event) sans infrastructure WebSocket.

### Tests du signal (mock _safe_broadcast_jauge)

Le signal `post_save` Ticket utilise `transaction.on_commit()`. Dans notre setup de test
(pas de rollback — `django_db_setup = pass`), `on_commit` fire automatiquement apres le save.
On mocke `_safe_broadcast_jauge` pour verifier l'appel sans toucher a Redis :

```python
from unittest.mock import patch

def test_signal_ticket(event_fixture):
    with patch("BaseBillet.signals._safe_broadcast_jauge") as mock:
        Ticket.objects.create(reservation=reservation, ...)

    mock.assert_called_once_with(event.pk)
```

### Tests E2E (a venir)

Le test E2E de la jauge temps reel necessite 2 contextes Playwright :
1. Page 1 : vendre un billet
2. Page 2 : verifier que la jauge se met a jour sans refresh

```python
def test_jauge_temps_reel(pos_page, browser):
    context2 = browser.new_context()
    page2 = context2.new_page()
    page2.goto(URL_PV_BILLETTERIE)

    # Vendre un billet dans pos_page...
    # Verifier dans page2 :
    expect(
        page2.locator('[id="billet-jauge-..."] .billet-jauge-text')
    ).to_have_text("10/50", timeout=5000)

    context2.close()
```

Piege : l'ID contient `__` (double underscore). Utiliser `[id="..."]` au lieu de `#...`
car `#id__with__underscores` est invalide en CSS.

### Ce qui est teste actuellement (session 08-09)

| Test | Fichier | Ce qu'il verifie |
|------|---------|-----------------|
| `test_consumer_connexion_et_groups` | `test_websocket_jauge.py` | Consumer accepte la connexion WebSocket |
| `test_consumer_ping_pong` | `test_websocket_jauge.py` | Ping → pong avec client_ts + server_ts |
| `test_consumer_ignore_messages_non_ping` | `test_websocket_jauge.py` | Messages inconnus/invalides ignores silencieusement |
| `test_broadcast_jauge_calcule_par_price` | `test_websocket_jauge.py` | Price.stock=10 → jauge 2/10 ; Price sans stock → jauge globale 2/50 |
| `test_broadcast_jauge_complet_par_price` | `test_websocket_jauge.py` | Price complet (12/10) meme si Event pas complet (12/50) |
| `test_broadcast_resilient_si_redis_down` | `test_websocket_jauge.py` | Redis down → warning log, pas de crash |
| `test_signal_ticket_declenche_broadcast` | `test_websocket_jauge.py` | Ticket.save() → on_commit → _safe_broadcast_jauge(event.pk) |
| `test_signal_ticket_sans_reservation_ne_crashe_pas` | `test_websocket_jauge.py` | Ticket orphelin → pas de broadcast, pas de crash |

### Ce qui n'est PAS teste (a faire en E2E)

| Scenario | Pourquoi pas encore |
|----------|-------------------|
| Jauge temps reel entre 2 onglets | Necessite Playwright multi-contexte + serveur Daphne actif |
| Indicateur vert/rouge au chargement | Test visuel (E2E) |
| Ping latence au clic sur l'icone | Test visuel (E2E) |
| OOB swap HTMX (remplacement DOM) | Le DOM n'est pas accessible en pytest DB-only |
| Reconnexion auto apres coupure | L'extension HTMX ws gere ca — tester manuellement |
| Broadcast cross-PV (meme event, 2 PV differents) | Necessite 2 PV BILLETTERIE dans les fixtures E2E |

---

## Pieges documentes

**A lire AVANT d'ecrire un nouveau test.** 41 lecons apprises pendant la migration et les sessions suivantes.

### Django multi-tenant

**9.1 — `schema_context` vs `tenant_context` (FakeTenant).**
`schema_context('lespass')` met un `FakeTenant` sur `connection.tenant`. Les modeles qui appellent `connection.tenant.get_primary_domain()` ou `.uuid` crashent. Utiliser `tenant_context(tenant)` pour `Event.objects.create()` et tout appel qui accede a `connection.tenant`.

```python
# ❌ Crash sur Event.save()
with schema_context('lespass'):
    Event.objects.create(name='Test', ...)

# ✅ OK
tenant = Client.objects.get(schema_name='lespass')
with tenant_context(tenant):
    Event.objects.create(name='Test', ...)
```

**9.5 — Routes publiques et `HTTP_HOST`.**
Les routes `/api/discovery/` sont dans `urls_public.py`. Utiliser `HTTP_HOST='tibillet.localhost'` (schema public), pas `lespass.tibillet.localhost` (tenant).

### Modeles et signaux

**9.2 — `ProductSold` n'a pas de champ `name`.**
Creation minimale : `ProductSold.objects.create(product=product)`. Idem pour `PriceSold`.

**9.3 — Signal `send_membership_product_to_fedow` cree des tarifs auto.**
Apres `Product.objects.create(categorie_article=ADHESION)`, le signal peut creer un "Tarif gratuit" supplementaire. Utiliser `assert count >= 3` (pas `== 3`), ou filtrer par nom.

**9.6 — Duplication produit et signaux.**
`_duplicate_product()` declenche les signaux → le duplicata peut avoir plus de tarifs. Verifier par nom, pas par comptage exact.

**9.20 — `Membership.custom_form` (pas `custom_field`).**
Les reponses aux champs dynamiques sont dans `custom_form` (JSONField). Toujours verifier le nom exact : `[f.name for f in Model._meta.get_fields()]`.

**9.22 — Options reservation = UUID (pas noms en clair).**
Le champ `options` dans `ReservationValidator` attend des UUID `OptionGenerale`. Le champ M2M s'appelle `options_radio` et `options_checkbox` (pas `option_generale_*`).

### Serializers et vues

**9.4 — `admin_clean_html(None)` crashe.**
Toujours envoyer `long_description=''` (pas `None`) dans les POST vers `simple_create_event`.

**9.16 — `newsletter` boolean dans MembershipValidator.**
Envoyer `"false"` (pas `""`) dans les donnees POST. Le formulaire HTML envoie `""` pour une checkbox non cochee, mais le serializer attend un boolean.

**9.17 — Header `Referer` requis par MembershipMVT.create().**
En cas d'erreur, la vue fait `request.headers['Referer']`. Ajouter `HTTP_REFERER="https://..."` au POST du test client Django.

**9.21 — `sale_origin="LP"` (LESPASS) pour les crowds.**
Les contributions crowds creent des LigneArticle avec `sale_origin="LP"`, pas `"LS"`.

### Mock Stripe

**9.18 — `tenant_context` requis pour `get_checkout_stripe()`.**
Cette methode accede a `connection.tenant.uuid` pour les metadata Stripe. Meme piege que 9.1.

**9.19 — Flow de test mock Stripe en 3 etapes.**
```python
# 1. POST formulaire → Paiement_stripe.PENDING + Session.create (mock)
resp = api_client.post("/memberships/", data=post_data, HTTP_REFERER="...")

# 2. Verifier que Session.create a ete appele
assert mock_stripe.mock_create.called

# 3. Simuler retour Stripe
paiement = Paiement_stripe.objects.filter(
    checkout_session_id_stripe="cs_test_mock_session"
).first()
paiement.update_checkout_status()  # mock retrieve retourne paid
```

### E2E Playwright

**9.7 — Dual-mode container/host dans conftest.py.**
Les tests E2E tournent dans le container ou `docker` n'existe pas. Detection automatique via `shutil.which("docker") is None`. Les commandes sont adaptees (docker exec vs direct).

**9.8 — Template membership : partiel sans HTMX.**
`/memberships/<uuid>/` rend `form.html` — un template PARTIEL sans `{% extends %}`, sans `<html>`, sans HTMX. Le formulaire se soumet en GET natif au lieu d'un POST HTMX. Pour tester le flow complet (soumission → Stripe), naviguer vers `/memberships/` (page liste avec base template + HTMX), trouver le produit, et cliquer Subscribe pour charger le formulaire dans l'offcanvas. Pour tester les validations client-side uniquement, `/memberships/<uuid>/` est acceptable car les scripts inline et la validation HTML5 fonctionnent sans HTMX.

**9.9 — Fixture `ensure_pos_data` pour donnees POS garanties.**
La fixture session-scoped `ensure_pos_data` (conftest.py) lance `create_test_pos_data` une fois par session. Les tests POS qui utilisent `pos_page` en dependent automatiquement. Utiliser `pytest.fail()` (pas `pytest.skip()`) quand un produit cree par la fixture est introuvable — un skip masque le vrai probleme. Utiliser `data-name="Biere"` (attribut) au lieu de `has_text=re.compile(r"^Biere$")` — le regex sans `re.MULTILINE` ne matche pas quand la tuile contient aussi le prix et le badge quantite.

**9.10 — `select_for_update` dans django_shell.**
`WalletService.crediter()` utilise `select_for_update()`. Wrapper dans `with db_transaction.atomic():` en code multi-ligne (`\n`), pas en one-liner (`;`).

**9.11 — Ordre des tests NFC adhesion.**
Chemin 2 (carte anonyme) doit passer AVANT chemin 4 (qui associe un user a la carte). Les noms de tests controlent l'ordre.

**9.12 — `scope="module"` pour setups lourds.**
Le setup NFC (asset + wallet + credit) prend ~2s. `scope="module"` evite de le repeter a chaque test.

**9.13 — Login cross-tenant : URLs absolues.**
`login_as_admin(page)` resout vers `base_url` (Lespass). Pour Chantefrein, reproduire le flow avec des URLs absolues. Les cookies sont per-subdomain.

**9.14 — Pagination changelist admin.**
Toujours filtrer par nom (`?q=...`) pour eviter qu'un asset soit invisible a cause de la pagination.

**9.15 — `django_shell` parametre `schema`.**
Parametre optionnel pour executer du code sur un autre tenant : `django_shell("...", schema="chantefrein")`.

**9.23 — HTMX `HX-Redirect` et Playwright.**
Les formulaires HTMX retournent un header `HX-Redirect` et HTMX fait `window.location.href = url`. Playwright detecte cette navigation si HTMX est charge sur la page. Le piege : certains templates sont des PARTIELS sans base template (cf. 9.8) — sans HTMX, la soumission se fait en GET natif. Solution : toujours passer par la page parente (liste, event) qui charge le formulaire via HTMX dans un offcanvas/panel.

**9.28 — `networkidle` ne resout jamais sur les pages Stripe.**
Stripe Checkout maintient des connexions persistantes (analytics, SSE). Utiliser `domcontentloaded` (pas `networkidle`) apres `wait_for_url("checkout.stripe.com")`. `networkidle` est OK pour les pages TiBillet internes.

**9.29 — `wait_for_url` callback recoit une string (pas un objet URL).**
En Playwright Python, le callback de `page.wait_for_url(lambda url: ...)` recoit une string. Utiliser `"tibillet.localhost" in url` (pas `url.host` ni `url.hostname`). En Playwright JS, le callback recoit un objet URL avec `.hostname`.

**9.24 — `DJANGO_SETTINGS_MODULE` est redondant.**
Deja configure dans `pyproject.toml`. Ne pas ajouter `os.environ.setdefault(...)` dans les nouveaux tests.

**9.25 — Deux conftest.py separes, pas de racine.**
`tests/pytest/conftest.py` (fixtures DB) et `tests/e2e/conftest.py` (fixtures navigateur) sont independants. Ne pas creer de conftest racine.

**9.26 — `pytest.skip` pour elements UI optionnels.**
Verifier la visibilite avant d'interagir avec des elements qui peuvent ne pas exister selon la config du tenant.

**9.27 — Verifier l'inventaire complet apres migration.**
Toujours comparer fichier par fichier, pas seulement par comptage global.

### Flow identification client unifie (session 05)

**9.30 — `CarteCashless` est en SHARED_APPS : pas de FastTenantTestCase.**
`CarteCashless` vit dans le schema `public`. En `FastTenantTestCase` (schema isole),
`CarteCashless.objects.get_or_create(tag_id=...)` echoue car la table n'existe pas
dans le schema de test. Utiliser `schema_context('lespass')` + `APIClient` pour les
tests qui touchent aux cartes NFC.

**9.31 — `tag_id` et `number` sur CarteCashless : max 8 caracteres.**
Les champs `tag_id` et `number` ont `max_length=8`. Utiliser des codes courts
(ex: `IDNFC001`) et pas de noms longs (`IDENT001N` → trop long pour `number`).

**9.32 — `create_test_pos_data` prend le premier tenant, pas forcement `lespass`.**
La commande fait `Client.objects.exclude(schema_name="public").first()`.
Si la DB contient des tenants "waiting" (UUID), ils passent avant `lespass`
alphabetiquement. Forcer le schema avec `--schema=lespass` :
```bash
docker exec lespass_django poetry run python manage.py tenant_command create_test_pos_data --schema=lespass
```

**9.33 — Le NFC reader soumet `#addition-form`, pas les hidden fields du partial.**
Le composant `<c-read-nfc>` appelle `sendEvent('additionManageForm', ... submit)`.
Ca soumet `#addition-form` — pas les `<input hidden>` dans le slot du composant.
Pour propager des flags via le flow NFC, il faut les injecter dans `#addition-form`
avec du JS au chargement du partial (pas en hidden fields dans le slot).

**9.34 — `{% translate %}` peut changer le texte attendu dans les assertions.**
`{% translate "Adhesion" %}` peut rendre "Membership" selon la langue active.
Tester avec `assert 'Adhesion' in contenu or 'Membership' in contenu`.

**9.35 — Le formulaire email ne fait plus de `hx-post` separe.**
Le bouton VALIDER dans `hx_formulaire_identification_client.html` appelle
`soumettreIdentificationEmail()` (JS inline) qui injecte les champs dans
`#addition-form` puis soumet. Les `repid-*` arrivent dans le POST car ils
sont deja dans `#addition-form`. Si on recree un `<form hx-post>` separe,
les articles du panier seront perdus.

### Billetterie POS (session 07)

**9.36 — `_, _created = get_or_create()` masque `_()` (gettext).**
Dans une fonction qui utilise `_("texte")` pour les traductions, ne jamais
ecrire `product_sold, _ = ProductSold.objects.get_or_create(...)`.
Python traite `_` comme variable locale dans toute la fonction → `_("texte")`
leve `UnboundLocalError`. Utiliser `_created` comme nom de variable.
Meme piege avec `for _ in range()` → utiliser `for _i in range()`.

**9.37 — `PointDeVente.objects.first()` depend de `poid_liste`.**
Les fixtures d'autres tests utilisent `PointDeVente.objects.first()` pour
trouver le premier PV (ex: "Bar"). Si un PV de test a un `poid_liste` bas
(ou un nom alphabetiquement premier), il sera retourne a la place.
Toujours mettre `poid_liste=9999` sur les PV de test pour qu'ils soient en
fin de liste (`ordering = ('poid_liste', 'name')`).

**9.38 — Le flow paiement via recapitulatif client n'a PAS d'ecran de confirmation.**
`payerAvecClient('espece')` dans `hx_recapitulatif_client.html` soumet
directement `#addition-form` vers `payer()`. Il n'y a PAS d'ecran
`paiement-confirmation` intermediaire (contrairement au flow VT normal).
En E2E : apres clic `[data-testid="client-btn-especes"]`, attendre
directement `[data-testid="paiement-succes"]`.

**9.39 — `#bt-retour-layer1` existe en double dans le DOM.**
Deux elements ont l'ID `bt-retour-layer1` : un dans `#message-no-article`
et un dans `[data-testid="paiement-succes"]`. Toujours scoper :
`page.locator('[data-testid="paiement-succes"] #bt-retour-layer1')`.

**9.40 — Playwright `install-deps` necessite root dans Docker.**
`playwright install --with-deps chromium` echoue car `su` n'a pas de mot de passe.
Utiliser `-u root` avec le chemin complet du virtualenv :
```bash
docker exec -u root lespass_django /home/tibillet/.cache/pypoetry/virtualenvs/lespass-LcPHtxiF-py3.11/bin/playwright install-deps chromium
docker exec lespass_django poetry run playwright install chromium
```

**9.41 — `Reservation.objects.create(status=VALID)` ne declenche PAS les signaux.**
La machine a etat `pre_save_signal_status` ignore les `_state.adding=True`.
Creer directement en VALID saute `reservation_paid()` (webhook + email).
Appeler `_envoyer_billets_par_email()` explicitement APRES le bloc atomic.

**9.42 — `LigneArticle.user_email()` ne couvrait pas les billets POS.**
L'ancienne version ne regardait que `membership.user.email` et
`paiement_stripe.user.email`. Les billets POS passent par
`reservation.user_commande.email`. Ajouter cette branche.

### WebSocket et Django Channels

**9.43 — `pytest-asyncio` obligatoire pour les tests consumer.**
Les tests `WebsocketCommunicator` sont des coroutines (`async def`). `pytest` ne les
execute pas sans `pytest-asyncio`. Installer : `poetry add --group dev pytest-asyncio`.
Decorer chaque test async avec `@pytest.mark.asyncio`. Ne pas mixer avec `unittest.TestCase`.

**9.44 — `WebsocketCommunicator` ne passe pas par le URLRouter.**
Le `scope["url_route"]` doit etre fourni manuellement dans le test. Le consumer
ne trouvera pas `self.scope["url_route"]["kwargs"]["pv_uuid"]` sans ca.
```python
communicator.scope["url_route"] = {"kwargs": {"pv_uuid": "aaaa-bbbb-..."}}
communicator.scope["tenant"] = mock_tenant  # MagicMock suffit
```

**9.45 — `on_commit` et les tests : pas de rollback = fire automatique.**
Notre setup de test (`django_db_setup = pass`, pas de `TransactionTestCase`) n'utilise
pas de transaction wrapper. `transaction.on_commit()` fire immediatement apres le `save()`.
Pas besoin de mocker `on_commit` — mocker directement `_safe_broadcast_jauge` suffit.
Attention : si le setup change pour utiliser des transactions, `on_commit` ne firera plus
et il faudra le mocker avec `side_effect=lambda fn: fn()`.

**9.46 — `broadcast_html` ne doit PAS etre appele dans un `atomic()`.**
Le signal `post_save` Ticket utilise `on_commit()` pour differer le broadcast.
Si on cree un Ticket a l'interieur d'un `db_transaction.atomic()`, le broadcast
ne partira qu'au commit de la transaction englobante. C'est voulu : si rollback,
pas de broadcast avec des donnees incoherentes.

**9.47 — ID HTML avec `__` (double underscore) invalide en selecteur CSS `#`.**
Les tuiles billet ont des IDs composites `billet-jauge-{event_uuid}__{price_uuid}`.
Le selecteur `#billet-jauge-xxx__yyy` est invalide en CSS (les `__` ne sont pas
escapes). Utiliser l'attribut : `[id="billet-jauge-xxx__yyy"]` ou
`page.locator(f'[id="billet-jauge-{event_uuid}__{price_uuid}"]')` en Playwright.

**9.48 — `hx-swap-oob` avec selecteur de classe (pas d'ID).**
HTMX 2 supporte `hx-swap-oob="innerHTML:.ma-classe"` pour cibler par classe CSS.
Utilise pour la sidebar jauge (`.sidebar-jauge-event-{uuid}`) car il n'y a qu'un
element par event. Pour les tuiles, on utilise des IDs uniques (1 par Price).

**9.49 — `Price.objects.filter(product__events=event)` ne marche pas.**
La relation M2M est `Event.products` (Event → Product), pas `Product.events`.
Le filtre correct : `Price.objects.filter(product__in=event.products.all())`.
Sinon : `Cannot query "Event": Must be "Product" instance.`

### Pieges impression (sessions 10-11-12)

**9.50 — Celery autodiscover ne scanne pas les sous-modules.**
`laboutik/printing/tasks.py` n'est PAS decouvert par `app.autodiscover_tasks()`.
Celery ne scanne que `<app>/tasks.py`, pas `<app>/sous_module/tasks.py`.
Solution : importer les taches dans `laboutik/tasks.py` :
```python
from laboutik.printing.tasks import imprimer_async, imprimer_commande  # noqa: F401
```
Symptome : `Received unregistered task of type 'laboutik.printing.tasks.imprimer_async'`
dans les logs Celery. Le message est ignore et l'impression ne se fait pas.

**9.51 — `point_de_vente` n'est pas dans le scope des sous-fonctions de paiement.**
`_payer_par_carte_ou_cheque()` et `_payer_en_especes()` recoivent `donnees_paiement`
mais PAS `point_de_vente` en parametre. Pour acceder au PV (et a son imprimante),
il faut le recuperer depuis `donnees_paiement["uuid_pv"]` :
```python
uuid_pv = donnees_paiement.get("uuid_pv", "")
point_de_vente = PointDeVente.objects.select_related('printer').get(uuid=uuid_pv)
```
Symptome : `NameError: name 'point_de_vente' is not defined` dans les vues de paiement.

**9.52 — Le SunmiCloudPrinter exige app_id/app_key/printer_sn dans __init__.**
Pour utiliser `SunmiCloudPrinter` comme builder ESC/POS pur (sans envoyer),
il faut passer des valeurs bidon :
```python
builder = SunmiCloudPrinter(
    dots_per_line=576,
    app_id="builder_only",
    app_key="builder_only",
    printer_sn="builder_only",
)
```
C'est accepte car on n'appelle pas `httpPost()` — on recupere juste `.orderData`.

**9.53 — Tests impression : fixtures avec `schema_context` + cleanup obligatoire.**
Les modeles `Printer`, `PointDeVente` sont dans TENANT_APPS. Les fixtures doivent :
1. Creer dans `schema_context('lespass')`
2. Yield l'objet
3. Supprimer dans `schema_context('lespass')` en teardown
Sinon : `ProgrammingError: relation "laboutik_printer" does not exist`

**9.54 — `imprimer_async.delay()` ne peut pas etre mocke via `laboutik.printing.tasks.imprimer`.**
Le mock doit cibler `laboutik.printing.imprimer` (le module `__init__.py`),
pas `laboutik.printing.tasks.imprimer` (l'import local dans la tache).
Symptome : `AttributeError: module does not have the attribute 'imprimer'`

**9.55 — Restart Celery obligatoire apres ajout de nouvelles taches.**
Celery charge les taches au demarrage. Si on ajoute `laboutik/printing/tasks.py`
sans restart, le worker ignore les messages. `docker restart lespass_celery` suffit.

---

*Ce document est un commun numerique. Prenez-en soin !*
*This document is a digital common. Take care of it!*
