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
| Tests pytest (DB-only) | 569 |
| Tests E2E (navigateur) | 91 |
| **Total** | **660** |
| Temps pytest | ~3.5 min |
| Temps E2E | ~13 min |
| **Temps total** | **~17 min** |

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

**Deplace dans un fichier dedie pour une meilleure lisibilite.**

Voir **[`tests/PIEGES.md`](PIEGES.md)** — 70+ pieges documentes, classes par domaine.

A lire AVANT d'ecrire un nouveau test.

