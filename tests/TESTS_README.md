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

**446 tests, ~3 minutes.**

Testent la logique **Python/Django** : modeles, serializers, vues, API, validations serveur, triggers post-paiement. Utilisent le client Django in-process (`self.client`) — pas de reseau, pas de navigateur.

Stripe est **mocke** cote serveur (`@patch("stripe.checkout.Session.create")`) pour eviter les appels reseau.

### Tests E2E (navigateur) — `tests/e2e/`

**62 tests, ~6 minutes.**

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

### Inventaire / Stock

```bash
# Modeles, services, ViewSet API, actions admin, affichage POS
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py tests/pytest/test_stock_visuel_pos.py tests/pytest/test_stock_actions_admin.py -v

# E2E admin inventaire (bandeaux aide, autocomplete, actions HTMX, filtres)
docker exec lespass_django poetry run pytest tests/e2e/test_admin_inventaire.py -v -s
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

### Inventaire / Stock (27 pytest + 5 pytest actions + 14 pytest POS + 7 E2E)
- Modeles Stock, MouvementStock, UniteStock, TypeMouvement (tests/pytest/test_inventaire.py)
- StockService : decrementation atomique F(), mouvements, ajustement (tests/pytest/test_inventaire.py)
- StockViewSet API : reception, perte, offert (tests/pytest/test_inventaire.py)
- DebitMetreViewSet : capteur Pi (tests/pytest/test_inventaire.py)
- ResumeStockService : resume cloture (tests/pytest/test_inventaire.py)
- Actions admin : stock_action_view reception/ajustement/perte/offert + validation type invalide (tests/pytest/test_stock_actions_admin.py)
- Affichage POS : _formater_stock_lisible 10 cas, _construire_donnees_articles enrichissement stock 3 cas, broadcast WebSocket 1 cas (tests/pytest/test_stock_visuel_pos.py)
- Admin E2E : bandeau aide stock list, add form autocomplete VT, actions HTMX (reception/ajustement/perte), mouvements list aide + filtre (tests/e2e/test_admin_inventaire.py)
- **Non teste en E2E** : WebSocket multi-onglet (vente sur onglet 1 → badge mis a jour sur onglet 2), stock bloquant grise sur POS

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

**9.23 — Proxy models sans manager filtre (TicketProduct, POSProduct, etc.).**
`TicketProduct.objects.first()` retourne N'IMPORTE QUEL Product (pas forcement un billet). Les proxy models n'ont pas de manager custom filtre — le filtrage est dans l'admin (`get_queryset`). Dans les tests, filtrer explicitement comme le fait l'admin :
```python
# ❌ Retourne une adhesion, pas un billet
product = TicketProduct.objects.first()

# ✅ Filtrer comme l'admin
product = Product.objects.filter(
    categorie_article__in=[Product.BILLET, Product.FREERES]
).first()
```

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

### Chainage HMAC et integrite LNE (session 12)

**9.56 — `Decimal` vs `float` vs `str` dans le HMAC : normaliser avant de hasher.**
`LigneArticle.qty` est un `DecimalField(max_digits=12, decimal_places=6)`.
Au moment du `create()`, `qty=1` (int en memoire). Apres le `save()` et re-read
depuis la DB, `qty=Decimal('1.000000')`. Si on utilise `str()` directement,
le hash change entre creation et verification (`'1'` vs `'1.000000'`).
Solution : normaliser avec un format fixe : `f"{float(ligne.qty):.6f}"`.
Meme chose pour `vat` : `f"{float(ligne.vat):.2f}"`.

**9.57 — Isolation des tests HMAC : utiliser `uuid_transaction`.**
Les tests pytest ne font pas de rollback (pas de `TransactionTestCase` avec
django-tenants). Si un test cree des `LigneArticle` avec HMAC, le suivant les
verra dans ses queries. Filtrer par `uuid_transaction` unique par test :
```python
import uuid as uuid_module
test_uuid = uuid_module.uuid4()
ligne.uuid_transaction = test_uuid
# ... plus tard :
lignes = LigneArticle.objects.filter(uuid_transaction=test_uuid)
```

**9.58 — `obtenir_previous_hmac()` et `verifier_chaine()` doivent trier identiquement.**
Les deux fonctions parcourent les LigneArticle dans un ordre. Si l'un trie
par `(-datetime, -pk)` et l'autre par `(datetime, uuid)`, les lignes avec le
meme `datetime` (creees dans la meme seconde) seront dans un ordre different.
`uuid` est aleatoire, `pk` est auto-increment. Toujours utiliser `(datetime, pk)`.

**9.59 — `Ticket` non importe dans `laboutik/views.py` (bug pre-existant).**
Le modele `Ticket` est utilise a 6 endroits dans `views.py` mais n'etait pas
importe. Corrige : ajoute dans `from BaseBillet.models import ..., Ticket`.
Symptome : `NameError: name 'Ticket' is not defined` lors du paiement especes
en billetterie.

### Clotures enrichies (session 13)

**9.60 — `datetime_ouverture` auto : les tests ne peuvent pas utiliser de total absolu.**
`cloturer()` calcule `datetime_ouverture` = 1ere vente apres la derniere cloture J.
Si on supprime les clotures d'un PV (`ClotureCaisse.objects.filter(pv=pv).delete()`)
pour "repartir a zero", TOUTES les ventes passees (des tests precedents) sont
incluses dans la prochaine cloture. Les totaux absolus (`assert total == 5000`)
echouent systematiquement.
Solution : verifier les deltas (difference entre avant et apres), pas les absolus.
```python
perpetuel_avant = config.total_perpetuel
# ... cloturer ...
config.refresh_from_db()
delta = config.total_perpetuel - perpetuel_avant
assert delta == 5000
```

**9.61 — `cloturer()` retourne 400 sans vente : les tests "tables" et "commandes" cassent.**
Avant session 13, `cloturer()` acceptait toujours (meme sans vente).
Maintenant il retourne 400 "Aucune vente a cloturer" si `datetime_ouverture`
est `None` (pas de `LigneArticle` apres la derniere cloture).
Les tests qui ne creent que des tables ou des commandes (sans `LigneArticle`)
doivent ajouter au moins une vente pour que la cloture fonctionne :
```python
_creer_ligne_article_directe(produit, prix, 100, PaymentMethod.CASH)
```

**9.62 — `ClotureSerializer` n'a plus de `datetime_ouverture`.**
Les tests qui envoyaient `datetime_ouverture` dans le POST continuent de
fonctionner MAIS le champ est simplement ignore par le serializer (DRF ignore
les champs inconnus). Cependant, c'est trompeur — retirer le champ du payload.

**9.63 — Clotures M/A Celery Beat : `_generer_cloture_agregee()` est testable directement.**
Pas besoin de mocker Celery Beat pour tester les clotures mensuelles/annuelles.
La fonction utilitaire `_generer_cloture_agregee()` est importable directement :
```python
from laboutik.tasks import _generer_cloture_agregee
_generer_cloture_agregee(niveau='M', niveau_source='J', date_debut=..., date_fin=...)
```

**9.64 — La cloture est GLOBALE au tenant, pas par PV.**
`ClotureCaisse.point_de_vente` est nullable et informatif (d'ou la cloture
a ete declenchee). Le numero sequentiel est par niveau (J/M/A), global au tenant.
Ne JAMAIS filtrer par `point_de_vente` pour retrouver des clotures dans les tests.
Utiliser `ClotureCaisse.objects.filter(niveau=ClotureCaisse.JOURNALIERE)`.
Pour nettoyer : `ClotureCaisse.objects.all().delete()` (pas `.filter(pv=pv)`).

**9.65 — Bug locale especes : `{{ total }}` rend une virgule en francais.**
`USE_L10N=True` fait que `{{ 5.0 }}` rend `5,0` dans un template Django.
Si cette valeur est passee dans un query param (`?total=5,0`), cote serveur
`floatformat("5,0")` echoue silencieusement (Python `float()` n'accepte pas
les virgules). Solution : utiliser `{{ total|unlocalize }}` dans les URLs
et `total_brut.replace(",", ".")` cote serveur.

### Mentions legales et tracabilite impressions (session 14)

**9.66 — `Price.vat` est un CharField avec des codes, pas un Decimal.**
`Price.vat` contient des codes TVA ('NA', 'DX', 'VG'...) definis dans `BaseBillet.models`.
`LigneArticle.vat` est un DecimalField (le taux numerique). La conversion se fait
dans `_creer_lignes_articles()` de `views.py`. Dans les tests, ne pas passer
`price.vat` directement a `LigneArticle.create()` — utiliser un mapping :
```python
CODES_TVA = {'NA': 0, 'DX': 10, 'VG': 20}
taux_tva = Decimal(str(CODES_TVA.get(str(price.vat), 0)))
```
Symptome : `InvalidOperation` ou `ValueError` en creant une LigneArticle de test.

**9.67 — `compteur_tickets` race condition : toujours utiliser `select_for_update()`.**
Le compteur sequentiel de tickets (sur `LaboutikConfiguration`) est incremente
atomiquement dans `formatter_ticket_vente()`. Sans `select_for_update()`, deux
workers Celery simultanees peuvent lire la meme valeur apres l'UPDATE :
```python
# BON : verrou sur la ligne pendant la transaction
from django.db import transaction
with transaction.atomic():
    LaboutikConfiguration.objects.select_for_update().filter(
        pk=config.pk,
    ).update(compteur_tickets=F('compteur_tickets') + 1)
    config.refresh_from_db()
```
Meme pattern que `numero_sequentiel` dans `cloturer()` (session 13).

**9.68 — Detection duplicata : garde quand `uuid_transaction` est `None`.**
Si `impression_meta` est fourni sans `uuid_transaction` ni `cloture_uuid`,
le filtre `ImpressionLog.objects.filter(type_justificatif=...)` remonte TOUTES
les impressions du type — faux positif systematique. Garde implementee :
```python
if not uuid_transaction and not cloture_uuid:
    est_duplicata = False  # Pas de reference → original par defaut
```

**9.69 — `ticket_data.pop("impression_meta")` dans `imprimer_async()`.**
Le `.pop()` retire la cle `impression_meta` du dict avant de le passer au
builder ESC/POS (qui ne connait pas cette cle). En contexte Celery serialise,
le dict est deserialisee independamment donc pas de side-effect. Mais si le
code est appele en synchrone (tests), le dict de l'appelant est modifie.
Pour les tests, passer une copie du dict ou ne pas re-utiliser `ticket_data`.

**9.70 — `detail_ventes` dans `rapport_json` est un dict, pas une liste.**
Le `RapportComptableService.calculer_detail_ventes()` retourne un dict
`{ "categorie_nom": { "articles": [...], "total_ttc": int } }`, pas une
liste plate d'items. Dans les templates admin, iterer avec
`{% for cat_nom, cat_data in section.items %}` puis
`{% for article in cat_data.articles %}`. Ne pas supposer une liste plate.

**9.71 — `actions_row` Unfold sur un admin read-only.**
`ClotureCaisseAdmin` a `has_change_permission = False`. Les `actions_row`
s'affichent quand meme (icone `more_horiz` a droite de chaque ligne).
Le pattern fonctionne tant que les actions retournent une `TemplateResponse`
ou `HttpResponse` directe (pas un redirect vers un formulaire de modification).

**9.72 — Filtre produit POS dans les tests : `methode_caisse` vs `categorie_article`.**
`Product.VENTE` est un choix de `methode_caisse`, pas de `categorie_article`.
Pour filtrer les produits de vente directe dans les tests, utiliser
`Product.objects.filter(methode_caisse=Product.VENTE)` et non
`Product.objects.filter(categorie_article=Product.VENTE)`.

**9.73 — `calculer_totaux_par_moyen()` retourne des cles non-numeriques.**
Apres enrichissement, le dict retourne par `calculer_totaux_par_moyen()` contient
`cashless_detail` (list) et `currency_code` (str) en plus des montants (int).
Les tests qui iterent sur les valeurs du dict pour verifier qu'elles sont toutes
des entiers doivent exclure ces cles :
```python
for cle, valeur in totaux.items():
    if cle in ('cashless_detail', 'currency_code'):
        continue
    assert isinstance(valeur, int)
```

**9.74 — `statistics.median()` leve `StatisticsError` sur liste vide.**
Le module `statistics` de Python leve `StatisticsError` si on passe une
liste vide a `median()`. Dans `calculer_habitus()`, toujours verifier
`if liste:` avant d'appeler `statistics.median(liste)`.

**9.75 — Soldes wallets via `fedow_core.Token` : wrap dans try/except.**
La query `Token.objects.filter(wallet__in=..., asset__category=Asset.TLF)`
peut echouer si fedow_core n'est pas encore peuple (pas d'asset TLF cree).
Toujours wraper dans `try/except` avec fallback a 0.

### Menu Ventes — Ticket X + liste (session 16)

**9.76 — `uuid_transaction` dans l'URL de `detail_vente` : valider le format UUID.**
Le `url_path` accepte toute chaine (`[^/.]+`). Si on passe `"pas-un-uuid"`,
Django leve `ValidationError` sur le filtre `uuid_transaction=...` (UUIDField).
La vue `detail_vente()` doit valider avec `uuid_module.UUID(str(uuid_transaction))`
dans un `try/except (ValueError, AttributeError)` avant le filtre ORM.

**9.77 — `page` en query param : toujours wrapper dans try/except.**
`int(request.GET.get("page", 1))` leve `ValueError` si `?page=abc`.
Pattern defensif :
```python
try:
    page = int(request.GET.get("page", 1))
except (ValueError, TypeError):
    page = 1
```

**9.78 — Bouton "Retour" dans les vues Ventes : pas de `hx-get` vers `point_de_vente`.**
Les vues du menu Ventes (Ticket X, liste, detail) sont chargees dans
`#products-container` par HTMX. La vue `point_de_vente()` a besoin de
`?uuid_pv=...&tag_id_cm=...` — ces params ne sont pas disponibles dans le
contexte des vues Ventes. Utiliser `window.location.reload()` pour revenir
a l'interface POS (recharge la page complete qui a les bons params dans l'URL).

**9.79 — `_calculer_datetime_ouverture_service()` est global au tenant, pas par PV.**
La fonction cherche la derniere `ClotureCaisse` journaliere tous PV confondus
(pas de filtre `point_de_vente`). C'est le meme comportement que `cloturer()`
(la cloture est globale au tenant, session 13). Ne jamais filtrer par PV.

**9.80 — Pagination SQL `Coalesce` + `Max` : les agrégats sont par transaction, pas par ligne.**
`liste_ventes` utilise `GROUP BY COALESCE(uuid_transaction, uuid)` cote SQL.
Les champs `moyen_paiement=Max('payment_method')` et `nom_pv=Max('point_de_vente__name')`
retournent la valeur la plus grande alphabetiquement. En pratique, toutes les
lignes d'une transaction ont le meme moyen et le meme PV, donc `Max` est correct.
Mais si un jour le split payment est implemente (2 moyens sur 1 transaction),
le `Max` retournera un seul moyen — celui qui gagne le tri alphabetique.

**9.81 — `detail_vente` : fallback uuid_transaction → uuid (pk).**
La vue `detail_vente` cherche d'abord par `uuid_transaction`, puis par `uuid`
(pk de `LigneArticle`). Ce fallback est necessaire car `Coalesce(uuid_transaction, uuid)`
dans la pagination peut retourner un uuid de ligne (quand `uuid_transaction` est `NULL`).
Sans ce fallback, le clic sur une vente sans `uuid_transaction` retourne 404.

**9.82 — Commentaires Django `{# #}` HORS d'un element HTML → texte brut dans les swaps HTMX.**
Quand un partial HTMX commence par un commentaire Django `{# TITRE ... #}` avant
le premier `<div>`, HTMX injecte le commentaire comme du texte brut visible dans
la page. Les commentaires de template dans un `<body>` ou `<td>` sont interpretes
comme du texte par le navigateur. Solution : utiliser des commentaires HTML
`<!-- ... -->` a l'interieur du premier element, ou supprimer les commentaires
du haut du fichier.

**9.83 — `stateJson` manquant dans les vues Ventes → `JSON.parse("")` crash.**
`base.html` ligne 32 fait `const state = JSON.parse("{{stateJson|escapejs}}")`.
Si `stateJson` n'est pas dans le contexte, Django rend une chaine vide et
`JSON.parse("")` leve `SyntaxError`. Ce crash empeche htmx de s'initialiser
(les `hx-*` ne fonctionnent plus). Solution : fournir un `stateJson` minimal
(via `_construire_state()`) dans le contexte de toutes les pages qui
etendent `base.html`.

**9.84 — Pattern collapse pour le detail de vente : `fetch()` + `insertAfter`.**
Le detail d'une vente dans la liste utilise un pattern collapse JS minimal :
`toggleDetailVente(ligneTr, url)` fait un `fetch()` pour charger le partial
et l'insere comme `<tr class="ventes-detail-row">` apres la ligne cliquee.
Re-clic = retire le `<tr>`. Ce n'est PAS du HTMX pur (pas de `hx-get`
sur le `<tr>`) car on a besoin du toggle et de la gestion de l'ancien
detail ouvert — trop complexe en attributs HTMX seuls.

**9.85 — `_rendre_vue_ventes()` : detection page complete vs partial.**
La fonction verifie `request.htmx.target == "body"` pour decider si elle
rend la page complete (avec header via `ventes.html`) ou juste le partial.
Les onglets HTMX ciblent `#ventes-zone` → partial seul.
Le scroll infini cible `this` (outerHTML sur le `<tr>` loader) → partial.
Seul le burger menu cible `body` → page complete.

### Corrections, fond de caisse, sortie de caisse (session 17)

**9.86 — `LaboutikConfiguration.get_solo()` en FastTenantTestCase : singleton absent.**
Le singleton django-solo n'existe pas dans le schema de test cree par
`FastTenantTestCase`. `get_solo()` retourne un objet en memoire avec
`_state.adding=True`. Un `save(update_fields=[...])` sur cet objet leve
`DatabaseError: Save with update_fields did not affect any rows.`
Solution : utiliser `save()` sans `update_fields` pour le singleton.
django-solo gere l'insert-or-update correctement quand `update_fields`
n'est pas specifie.

**9.87 — `ProductSold` n'a pas de champ `name` — ne pas passer `name=` au create.**
`ProductSold` a seulement `product` (FK) et `categorie_article`.
Le champ `name` n'existe pas. Utiliser `ProductSold.objects.create(product=produit)`.
Le nom est derive de `self.product.name` via `__str__()`.
De meme, `PriceSold.qty_solded` (et non `qty_sold`).

**9.88 — Fixture `admin_user` post-flush : user `is_active=False`.**
Apres un flush DB, le signal `pre_save_signal_status` peut mettre
`is_active=False` sur le user admin. La fixture `admin_client` dans
`conftest.py` fait `force_login()` mais l'admin Django refuse l'acces
aux users inactifs → redirect 302 vers login sur toutes les pages admin.
Fix : la fixture `admin_user` force `is_active=True` si necessaire :
```python
if not user.is_active:
    user.is_active = True
    user.save(update_fields=['is_active'])
```

**9.89 — Correction moyen de paiement : `transaction.atomic()` obligatoire.**
La creation de `CorrectionPaiement` et la modification de `ligne.payment_method`
doivent etre dans le meme `transaction.atomic()`. Si le `save()` echoue apres
le `create()`, on a une trace d'audit sans correction reelle (incoherence LNE).

**9.90 — Fond de caisse : conversion euros → centimes via `Decimal`, pas `float`.**
La regle projet (MEMORY.md) est "jamais via float". Utiliser
`Decimal(montant_brut)` puis `int(round(montant * 100))`. Attraper
`InvalidOperation` en plus de `ValueError`.

**9.91 — `fetch()` + `innerHTML` ne declenche PAS htmx : appeler `htmx.process()`.**
Le pattern collapse de `toggleDetailVente()` dans `hx_liste_ventes.html`
utilise `fetch()` + `td.innerHTML = html` pour injecter le detail sous la
ligne cliquee. Le contenu injecte par `fetch()` n'est PAS traite par htmx :
les attributs `hx-get`, `hx-post`, etc. sont **morts** dans le DOM.
Les boutons "Re-imprimer" et "Corriger moyen" ne fonctionnent pas.
Solution : ajouter `htmx.process(td)` apres `ligneTr.after(detailRow)`.
htmx scanne alors le nouveau contenu et active les attributs `hx-*`.
Regle generale : chaque fois qu'on injecte du HTML avec `hx-*` via JS
natif (pas via htmx), il faut appeler `htmx.process(element)`.

**9.92 — `hx-target="body"` envoie `HX-Target: contenu` a cause de `<body id="contenu">`.**
Le `<body>` dans `laboutik/base.html` a `id="contenu"`. Quand un element a
`hx-target="body"`, htmx resout le selecteur vers l'element `<body>` mais
envoie son **id** dans le header HTTP : `HX-Target: contenu` (pas `"body"`).
Cote serveur, `request.htmx.target == "body"` est **faux**.
Solution dans `_rendre_vue_ventes()` : verifier les deux valeurs :
```python
est_navigation_complete = (
    not request.htmx
    or request.htmx.target in ("body", "contenu")
)
```
Ce piege s'applique a toute logique serveur qui teste `request.htmx.target`.

**9.93 — RC/TM (recharges gratuites) utilisent `PaymentMethod.FREE`, pas le moyen de paiement du panier.**
Les recharges cadeau (RC) et temps (TM) sont gratuites : le `payment_method` de
leur `LigneArticle` est toujours `FREE` ("NA" en DB), meme si le panier contient
d'autres articles payes en especes ou CB. Ne pas tester `payment_method == 'CA'`
sur une LigneArticle de type RC/TM.

Le code d'interface pour `PaymentMethod.FREE` est `"gift"`, pas `"NA"`.
Le mapping est dans `MAPPING_CODES_PAIEMENT` : `"gift" → PaymentMethod.FREE`.
Passer `PaymentMethod.FREE` directement a `_creer_lignes_articles()` donne
`PaymentMethod.UNKNOWN` ("UK") car la fonction attend un code d'interface, pas
une valeur DB.

**9.94 — Carte anonyme + recharge seule (RE/RC/TM) : pas de formulaire email.**
Quand une carte NFC sans user est scannee et que le panier ne contient que des
recharges (pas d'adhesion, pas de billet), le flow court-circuite le formulaire
email. Pour les recharges euros (RE), on affiche le recapitulatif avec boutons
de paiement. Pour les recharges gratuites (RC/TM), le credit est immediat
(ecran de succes direct). Le formulaire email ne s'affiche que si le panier
contient un article qui necessite un user : adhesion (AD) ou billet.

---

### Float Django dans les attributs CSS style — piege `USE_L10N`

Quand on injecte un float Django dans un attribut `style=""` d'un template
(ex: `width: {{ pourcentage }}%`), et que `USE_L10N=True`, Django formate
le nombre avec la virgule francaise : `width: 84,6%` au lieu de `width: 84.6%`.

Le CSS est invalide — le navigateur ignore la propriete et applique le defaut
(souvent `width: auto` ou `100%`).

**Solution** : utiliser `|unlocalize` sur les nombres injectes dans du CSS.

```html
{% load l10n %}
{# BON — le point decimal est force #}
<div style="width: {{ pourcentage|unlocalize }}%;"></div>

{# MAUVAIS — la virgule casse le CSS en locale FR #}
<div style="width: {{ pourcentage }}%;"></div>
```

Ce piege affecte toutes les progress bars et tout element avec une dimension
calculee depuis une variable Django. Decouvert sur les progress bars du bilan
billetterie (Session 05, avril 2026).

---

### Piege 56 : `AutocompleteSelect` dans un formulaire custom Unfold

`AutocompleteSelect(field, admin_site)` attend `field.remote_field` (la relation FK),
pas le field Django lui-meme. De plus, `autocomplete_fields` sur le ModelAdmin ne
s'applique PAS si `get_form()` retourne une classe de formulaire directement
(`return self.add_form`). Il faut passer par `kwargs["form"] = self.add_form` puis
`return super().get_form(request, obj, **kwargs)` pour que Django applique les widgets.

Pour retirer le lien "+" (add related) d'un autocomplete, le faire dans `get_form()`
(pas dans `formfield_for_foreignkey` — `autocomplete_fields` ecrase le widget apres).

```python
def get_form(self, request, obj=None, **kwargs):
    form = super().get_form(request, obj, **kwargs)
    if "product" in form.base_fields:
        form.base_fields["product"].widget.can_add_related = False
    return form
```

Decouvert sur StockAdmin (Session 25, avril 2026).

---

### Piege 57 : Unfold `@display(label=...)` avec label complet

Pour afficher un label complet (ex: "Reception") avec une couleur de badge,
la fonction display doit retourner un **tuple `(cle, texte)`**. La cle est matchee
contre le dict `label`, le texte est affiche.

```python
LABELS = {TypeMouvement.RE: "success", TypeMouvement.PE: "danger"}

@display(description=_("Type"), label=LABELS)
def display_type(obj):
    # Tuple (cle, texte) : cle pour la couleur, texte pour l'affichage
    return obj.type_mouvement, obj.get_type_mouvement_display()
```

Si on retourne juste une string, Unfold l'utilise comme cle ET comme texte.
Retourner `get_type_mouvement_display()` seul ne matche pas les cles du dict
(qui sont les codes courts VE, RE, etc.).

Decouvert sur MouvementStockAdmin (Session 25, avril 2026).

---

### Piege 58 : HTMX double submit — boutons dans un form avec hx-target

Des boutons avec `hx-post` dans un `<form hx-target="...">` declenchent DEUX
requetes HTMX : une du bouton, une du form (heritage). Le partial se retrouve
imbrique dans lui-meme.

Solution : pas de `<form>`, des boutons `type="button"` autonomes avec
`hx-post`, `hx-vals`, `hx-include`, `hx-target` et `hx-headers` pour le CSRF.

```html
<!-- BON : bouton autonome, pas de form -->
<button type="button"
        hx-post="/action/"
        hx-vals='{"type": "RE"}'
        hx-include="#input-qty, #input-motif"
        hx-target="#container"
        hx-swap="innerHTML"
        hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
    Reception
</button>
```

Decouvert sur stock_actions_partial.html (Session 25, avril 2026).

---

### Piege 59 : OOB swap `innerHTML` vs `outerHTML` — les attributs ne sont PAS mis a jour

`hx-swap-oob="innerHTML"` remplace uniquement le **contenu interieur** du div cible.
Les attributs du div lui-meme (`data-*`, `class`, `aria-*`) ne sont **pas** modifies.

Si on a besoin de mettre a jour un `data-stock-bloquant` sur le div badge via OOB,
il faut `hx-swap-oob="outerHTML"` pour remplacer le div entier (tag + attributs + contenu).

```html
<!-- MAUVAIS : innerHTML ne met PAS a jour data-stock-bloquant sur le div -->
<div id="stock-badge-xxx" hx-swap-oob="innerHTML" data-stock-bloquant="true">
    <span>Epuise</span>
</div>

<!-- BON : outerHTML remplace tout le div, attributs inclus -->
<div id="stock-badge-xxx" hx-swap-oob="outerHTML" data-stock-bloquant="true">
    <span>Epuise</span>
</div>
```

Attention avec `outerHTML` : le nouveau div doit avoir le meme `id` pour que
les swaps suivants (ou le JS) puissent le retrouver.

Decouvert sur hx_stock_badge.html (Session 25, avril 2026).

---

### Piege 60 : HTMX WebSocket n'execute PAS les `<script>` dans les messages

Les `<script>` inclus dans du HTML recu via l'extension HTMX ws (`hx-ext="ws"`)
ne sont **jamais executes**. C'est une decision de securite de HTMX.

Si on a besoin de modifier le DOM au-dela de l'OOB swap (ex: propager un attribut
d'un badge vers un container parent), utiliser un listener JS sur `htmx:wsAfterMessage`
qui lit le DOM apres le swap et propage les changements.

```javascript
// Le script inline dans le HTML WebSocket ne s'execute PAS :
// <script>document.querySelector(...).classList.add('bloquant')</script>

// Solution : listener global qui s'execute apres chaque message WebSocket
document.body.addEventListener('htmx:wsAfterMessage', function() {
    // Lire le badge et propager l'etat vers le container parent
    var badges = document.querySelectorAll('[id^="stock-badge-"]');
    badges.forEach(function(badge) {
        var uuid = badge.id.replace('stock-badge-', '');
        var container = document.querySelector('[data-uuid="' + uuid + '"]');
        if (!container) return;
        if (badge.dataset.stockBloquant === 'true') {
            container.classList.add('article-bloquant');
            container.dataset.stockBloquant = 'true';
        } else {
            container.classList.remove('article-bloquant');
            delete container.dataset.stockBloquant;
        }
    });
});
```

Decouvert sur le broadcast stock WebSocket (Session 25, avril 2026).

---

### Piege 61 : Dedupliquer les broadcasts quand le panier a N fois le meme article

Quand le panier contient 5x Biere, `_creer_lignes_articles()` boucle 5 fois
sur le meme produit. Chaque iteration decremente le stock et collecte les donnees
pour le broadcast. Sans deduplication, le broadcast envoie 5 divs OOB avec le meme
`id` — le resultat depend de l'ordre d'iteration de HTMX sur `fragment.children`.

Solution : dedupliquer par `product_uuid` et ne garder que le dernier etat (stock final).

```python
# MAUVAIS : 5 entrees pour le meme produit
donnees_a_broadcaster = list(produits_stock_mis_a_jour)

# BON : deduplication par product_uuid, seul l'etat final compte
donnees_par_produit = {}
for donnee in produits_stock_mis_a_jour:
    donnees_par_produit[donnee["product_uuid"]] = donnee
donnees_a_broadcaster = list(donnees_par_produit.values())
```

Decouvert via le test E2E WebSocket multi-onglet (Session 25, avril 2026).

---

### Piege 62 : `stock.save()` apres `StockService.ajuster_inventaire()` ecrase la quantite

`StockService.ajuster_inventaire()` utilise `F()` pour un update atomique de la quantite.
L'instance Python en memoire garde l'ancienne valeur. Si on fait `stock.save()` apres
(pour modifier un autre champ comme `autoriser_vente_hors_stock`), Django ecrase
la quantite en DB avec l'ancienne valeur en memoire.

```python
# MAUVAIS : stock.save() ecrase la quantite ajustee par F()
stock.autoriser_vente_hors_stock = True
stock.save()
StockService.ajuster_inventaire(stock=stock, stock_reel=10)  # DB: qty=10
stock.autoriser_vente_hors_stock = False
stock.save()  # DB: qty=100 (ancienne valeur en memoire !)

# BON : utiliser update() pour modifier uniquement le champ voulu
StockService.ajuster_inventaire(stock=stock, stock_reel=10)
stock.refresh_from_db()
Stock.objects.filter(pk=stock.pk).update(autoriser_vente_hors_stock=False)
```

Ce piege affecte tout code qui appelle `save()` sur une instance dont un champ
a ete modifie par `F()` ou `update()` sans `refresh_from_db()` entre les deux.

Decouvert dans le setup du test E2E WebSocket (Session 25, avril 2026).

---

### Piege 63 : Daphne ne hot-reload PAS les consumers WebSocket

Contrairement a `runserver` qui recharge le code Python a chaque modification,
Daphne charge les consumers au demarrage et ne les recharge jamais.

Si on ajoute une methode `stock_update()` sur `LaboutikConsumer`, les messages
`type: "stock_update"` sont **silencieusement ignores** tant que Daphne n'est pas
redemarre. Les logs montrent le broadcast mais rien n'arrive aux navigateurs.

```bash
# Apres modification de wsocket/consumers.py, toujours redemarrer Daphne
# Le serveur HTTP hot-reload (views, templates) mais PAS les consumers ASGI
```

Decouvert lors du debug WebSocket (Session 25, avril 2026).

### Piege 59 : `#articles-zone` n'existe pas — le conteneur est `#products`

L'element qui contient la grille d'articles POS s'appelle `#products`
(defini dans `cotton/articles.html`). Il n'y a pas de `#articles-zone` dans le DOM.
Si un subagent ou un dev utilise `document.querySelector('#articles-zone')`, il obtient
`null` et le `dispatchEvent` qui suit crash avec `Cannot read properties of null`.

Toujours verifier les IDs reels dans les templates avant de les utiliser dans le JS.

### Piege 60 : `conditional_fields` Unfold ne fonctionne PAS dans les inlines

L'attribut `conditional_fields` d'Unfold (Alpine.js) est reserve au `ModelAdmin` principal.
Les templates inline (`stacked.html`, `tabular.html`) n'ont pas de support `x-show`.
Pour des champs conditionnels dans un inline, utiliser le mecanisme custom
`inline_conditional_fields` + `inline_conditional_fields.js` (cree en session 26).

### Piege 61 : lignes panier a montant variable — suffixe `--N` obligatoire

Les tarifs a montant variable (prix libre, poids/mesure) doivent creer une ligne panier
unique a chaque saisie : `repid-{uuid}--{priceUuid}--{N}`. Sans le suffixe `--N`,
la 2e saisie ecrase la 1re (meme cle = increment qty au lieu de nouvelle ligne).
Le backend (`extraire_articles_du_post`) ignore le 3e segment `--N` lors du parsing.
Les tarifs fixes n'ont PAS de suffixe (clic = increment qty sur la meme ligne).

---

*Ce document est un commun numerique. Prenez-en soin !*
*This document is a digital common. Take care of it!*
