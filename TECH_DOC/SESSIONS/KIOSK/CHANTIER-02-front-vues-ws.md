# CHANTIER-02 — Front + vues + WebSocket — Plan (copie rebranchée)

**Goal :** porter le parcours de recharge kiosk de LaBoutik (`../LaBoutik/htmxview`) dans l'app
`kiosk` de Lespass : client Fedow `retrieve(tag_id)`, validator, `KioskViewSet`, tâche Celery de
polling, URLs, front (templates + static) et WebSocket `TerminalConsumer`.

**Cadre :** copier-coller **rebranché** (SPEC §11). Fedow distant, pas de signature (SPEC §8bis).
Source : `../LaBoutik/htmxview/` (branche `main-tpe`).

## Global Constraints
- Subagents SANS git. Pas de `runserver`/`makemessages`. Commandes via `docker exec lespass_django poetry run ...`.
- Tests : `pytest ... --api-key dummy`.
- Rebranchements obligatoires : `APIcashless.*` → `kiosk.models`/`QrcodeCashless` ; `ConfigurationStripe` → `RootConfiguration` ; carte via `QrcodeCashless.CarteCashless` ; `fedow_place_uuid` via `FedowConfig`.
- **Pas de signature** dans `send_to_terminal` (déjà fait CHANTIER-01, ne pas réintroduire).
- Front FALC, i18n `_()`/`{% translate %}` source FR.

---

## Task 02A — Backend (client Fedow, validator, viewset, tâche, URLs)

**Fichiers :**
- Modifier `fedow_connect/fedow_api.py` : ajouter `NFCcardFedow.retrieve(tag_id)`.
- Créer `kiosk/validators.py` : `RefillWisePoseValidator` (rebranché).
- Créer `kiosk/tasks.py` : `poll_payment_intent_status` (copié de `htmxview/tasks.py`, rebranché `kiosk.models`).
- Créer `kiosk/views.py` : `KioskViewSet` (copié de `htmxview/views.py` `class Kiosk`, SANS le parcours `link` — YAGNI).
- Créer `kiosk/urls.py` : router DRF `kiosk`.
- Modifier `TiBillet/urls_tenants.py` : `path("kiosk/", include("kiosk.urls"))`.
- Test : `tests/pytest/test_kiosk_flow.py`.

**Détails de rebranchement :**
- `NFCcardFedow.retrieve(tag_id)` (`fedow_connect/fedow_api.py`, classe `NFCcardFedow`) : `GET card/{tag_id}/retrieve` côté Fedow (route `CardAPI.retrieve`, `Card.objects.get(first_tag_id=pk)`). Utiliser le helper `_get(self.fedow_config, path=f'card/{tag_id.upper()}/retrieve')`. Retourner le JSON validé (ou lever si 404). S'inspirer de `card_tag_id_retrieve` existant.
- `RefillWisePoseValidator` : champs `totalAmount` (Decimal, →centimes) + `tag_id` (8 char). `validate_tag_id` appelle `FedowAPI().NFCcard.retrieve(tag_id)` puis `self.card = CarteCashless.objects.get(tag_id=tag_id)` (**`QrcodeCashless`**).
- `KioskViewSet` : actions `list` (→`kiosk/select_amount.html`), `check_request_card`, `refill_with_wisepos`, `cancel`. Auth `SessionAuthentication`+`IsAuthenticated` + garde `request.user.terminal_role == "KI"`. Récupère le TPE via `request.user.terminal` (OneToOne). `PaymentsIntent`/`Terminal`/`StripeLocation` depuis `kiosk.models`. `ConfigurationStripe`→`RootConfiguration`.
- **Ne PAS copier** l'action `link` ni `check_request_card`→`tpe/request_card.html` si non nécessaire (garder `request_card` seulement si utilisé par le flux ; sinon YAGNI).

**Tests attendus (DEMO) :** un test `KioskViewSet.list` rend le template ; un test `refill_with_wisepos` en DEMO crée un `PaymentsIntent` et rend `waiting_credit_card_terminal.html` (mocker Fedow/carte). Au moins 2 tests verts.

---

## Task 02B — Front + WebSocket

**Fichiers :**
- Copier `../LaBoutik/htmxview/templates/kiosk/` → `kiosk/templates/kiosk/` : `base.html`, `select_amount.html`, `waiting_credit_card_terminal.html`, `success.html`, `cancel.html`, `sweet_scan_button.html`, `spinner.html`. **Exclure** `link/`, `not_used/`.
- Copier `../LaBoutik/htmxview/static/kiosk/` → `kiosk/static/kiosk/` (js/css/images).
- Modifier `wsocket/consumers.py` : ajouter `TerminalConsumer` (copié de `htmxview/consumers.py`, adaptation `hasattr(user,'appareil')` → `terminal_role == "KI"`).
- Modifier `wsocket/routing.py` : `re_path(r"ws/terminal/(?P<room_name>[\w-]+)/$", TerminalConsumer.as_asgi())`.

**Adaptations front :**
- URLs `/htmx/kiosk/` → `/kiosk/` dans tous les templates/JS.
- WS `ws-connect="/ws/terminal/{{ payment_intent.payment_intent_stripe_id }}/"`.
- `base.html` : injection conditionnelle `{% if type_app == "cordova" %}<script src="http://localhost/cordova.js"></script>{% endif %}` (pattern `laboutik/base.html:35-37`) pour le lecteur NFC.
- Le room WS = `payment_intent_stripe_id` (cohérent avec la tâche Celery).

**Test attendu :** un test qui vérifie que la route `ws/terminal/` est enregistrée (ou un smoke du rendu template). Au moins 1 test/vérif.

---

## Fin de chantier
- Review + correction par agent **Fable 5**.
- Check conformité **`/djc`** (patterns Django+HTMX du projet).
