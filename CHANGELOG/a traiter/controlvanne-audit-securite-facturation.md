# controlvanne : sécurité et facturation, suites de l'audit

**Relevé du 2026-09-26.** Il vient de trois audits en lecture seule de
`controlvanne/` : djc côté Python, djc côté templates/JS, et hallmark sur
l'interface. Les lots 3 (écran kiosk) et 4 (calibration, i18n, a11y) ont été
corrigés : voir `CHANGELOG/2026-09-26-controlvanne-audit.md`. Les lots 1 et 2
ci-dessous sont **volontairement mis en attente**.

Chaque point **critique** a été vérifié dans le code. Les autres viennent des
audits et sont à confirmer au moment de les traiter.

**Ordre de priorité proposé :** 1.1 + 1.2 (fuite WebSocket entre lieux) →
2.1 (erreur de stock dans la facture) → 1.3 (redirection) → 1.4 (clé ↔ tireuse)
→ 2.3 (montants calculés par le serveur) → le reste.

> **À savoir tant que 1.1 et 1.2 ne sont pas faits :** un kiosk ouvert sur
> `/ws/rfid/all/` dans un lieu reçoit les passages de carte **des autres lieux**
> (prénom, UID de la carte, solde). N'importe quel navigateur, même non
> connecté, peut ouvrir ce WebSocket.

---

## Lot 1 — Sécurité

### 1.1 Le consumer WebSocket accepte tout le monde (vérifié)

- **Où :** `controlvanne/consumers.py:51-81`, `PanelConsumer.connect()`.
- **Constat :** `group_add` puis `accept()`, sans aucun contrôle. Ni
  `session["controlvanne_authenticated"]`, ni admin du lieu. Si
  `scope["tenant"]` vaut `None`, la requête du payload initial part sur le
  schéma public.
- **Scénario d'échec :** un visiteur ouvre
  `wss://lieu.tibillet…/ws/rfid/all/` depuis sa console. Il reçoit chaque
  badge : prénom, UID et solde.
- **Correctif :** dans `connect()`, `await self.close()` si le lieu manque, ou
  si le client n'est ni un kiosk (`scope["session"]`) ni un admin du lieu
  (`scope["user"].is_tenant_admin(tenant)` via `database_sync_to_async`). C'est
  la même règle que `_verifier_authentification_kiosk`
  (`controlvanne/viewsets.py:1000`), sans le jeton. `AuthMiddlewareStack` fournit
  déjà la session et l'utilisateur (`TiBillet/asgi.py:31`).

### 1.2 Les groupes Channels ne portent pas le lieu (vérifié)

- **Où :** `consumers.py:68-70`, `viewsets.py:77-87` (`_push_ws_kiosk`),
  `signals.py:229-239`.
- **Constat :** les groupes s'appellent `rfid_state.all` et
  `rfid_state.<uuid>`. Redis est partagé par tous les lieux
  (`TiBillet/settings.py:659`, pas de préfixe). Le groupe `all` est donc
  **commun à tous les lieux**. Les groupes par UUID sont de fait séparés, car
  les UUID sont uniques.
- **Correctif :** une seule fonction, `nom_du_groupe_ws(tenant_pk, slug)`, qui
  renvoie `rfid_state.{tenant_pk}.all` / `rfid_state.{tenant_pk}.{uuid}`. Elle
  est utilisée par les trois émetteurs (consumer, `_push_ws_kiosk`, signal).
- **Test à écrire :** `WebsocketCommunicator` (pytest-asyncio) avec
  `scope["tenant"]`, `session` et `user` fournis à la main. Une connexion
  anonyme doit être refusée, et le groupe doit être préfixé par le lieu.

### 1.3 `next` non validé dans `KioskTokenView` (vérifié)

- **Où :** `viewsets.py:977-988`.
- **Constat :** `escape(iri_to_uri(next_url))` ne bloque ni
  `https://autre-site`, ni `javascript:…`. Ce dernier est exécuté par
  `window.location.replace('…')`.
- **Portée :** il faut un jeton valide, à usage unique et d'une durée de vie de
  5 min. Le risque est faible, mais bien réel.
- **Correctif :** `url_has_allowed_host_and_scheme(next_url,
  {request.get_host()}, require_https=request.is_secure())`, sinon
  `/controlvanne/kiosk/`.

### 1.4 Une clé API n'est pas liée à sa tireuse

- **Où :** `permissions.py:23-60` (`HasTireuseAccess`),
  `viewsets.py:391` (`authorize`) et `event`.
- **Constat :** n'importe quelle `TireuseAPIKey` du lieu peut agir sur n'importe
  quelle tireuse, en passant un autre `tireuse_uuid`.
- **Correctif :** si `request.tireuse_api_key` existe, exiger
  `tireuse.terminal.term_user == request.tireuse_api_key.user`, sinon 403.
  L'admin connecté (simulateur) garde l'accès.

### 1.5 Calibration ouverte au staff de tous les lieux

- **Où :** `calibration_views.py:87,108,130` (`@staff_member_required`).
- **Constat :** `is_staff` est un drapeau global. Un admin d'un autre lieu peut
  donc calibrer. De plus, `Debimetre` est une FK partagée : calibrer une tireuse
  change le facteur de toutes celles qui ont le même débitmètre.
- **Correctif :** contrôle `TenantAdminPermissionWithRequest(request)`, sinon
  403. Le partage du débitmètre est à documenter dans l'écran.

### 1.6 Pas de limitation de débit sur `authorize`

- **Constat :** avec une clé valide, `authorize` renvoie `solde_centimes`. On
  peut donc tester des UID en masse.
- **Correctif :** `ScopedRateThrottle`, par exemple 60/min.

---

## Lot 2 — Facturation / argent

### 2.1 Une erreur de stock peut annuler toute la facture (vérifié)

- **Où :** `billing.py:350-363`.
- **Constat :** `except Exception: pass` autour de
  `StockService.decrementer_pour_vente`, **dans** le `transaction.atomic()` de
  `facturer_tirage` (`billing.py:223`), sans savepoint.
- **Scénario d'échec :** une erreur base de données dans `StockService`
  (contrainte, verrou…) met la transaction Postgres en état « aborted ». Le
  `pass` cache l'erreur. La requête suivante lève alors
  `TransactionManagementError`, qui fait remonter une 500 : transactions,
  `LigneArticle` et fermeture de session sont annulées, sans message clair.
- **Correctif :** tester l'absence de stock proprement
  (`hasattr(produit, "stock_inventaire")`), appeler `StockService` dans un
  `atomic()` imbriqué, et journaliser avec `logger.exception`.

### 2.2 Réservoir mis à jour avec une valeur périmée

- **Où :** `viewsets.py:229` (`_cloturer_session_et_facturer`).
- **Constat :** `tireuse.reservoir_ml = max(0, tireuse.reservoir_ml - v)` est
  calculé sur une tireuse lue sans verrou. Deux fermetures simultanées
  (session orpheline + `pour_end`) perdent une décrémentation.
- **Correctif :** `update(reservoir_ml=Greatest(F("reservoir_ml") - v, 0))`,
  puis `refresh_from_db`. Attention : `update()` ne déclenche pas `post_save`.
  Il faut extraire le push du snapshot (`signals.py`) dans une fonction et
  l'appeler via `on_commit`.

### 2.3 Montants calculés côté client

- **Où :** `controlvanne/static/controlvanne/js/ecran_tireuse.js:35,216`
  (nombre de verres, `prix_litre × 0.25`) et le calcul du prix servi.
- **Constat :** c'est de la logique d'argent dans le JS. L'arrondi JS n'est pas
  celui du serveur (`billing.py`), donc l'écran peut afficher un centime de
  différence avec le montant débité.
- **Correctif :** `_construire_payload_session` ajoute `prix_servi` et
  `nombre_verres`, déjà formatés, calculés par une fonction commune avec la
  facture. Le JS se contente d'écrire. `ws_payloads.py` doit être mis à jour.

### 2.4 Trop de requêtes à chaque `pour_update` (≈ 1/s/tireuse)

- **Constat :** `prix_litre` est lu 3 fois (une requête chaque fois),
  `liquid_label` charge le fût, `reservoir_max_ml` fait une requête sur Stock,
  plus le contexte cashless et une requête de solde par asset. Au total, plus
  de 10 requêtes par seconde et par tireuse.
- **Correctif :** `select_related("fut_actif")`, `prix_litre` lu une seule fois
  dans une variable, et le solde de l'`authorize` gardé en mémoire (à voir : un
  champ sur `RfidSession` demanderait une migration).

### 2.5 Restriction des cartes maintenance jamais appliquée

- **Où :** `models.py:158-164` (`CarteMaintenance.tireuses`, « Leave empty for
  all taps »), qui n'est jamais lu dans `authorize`.
- **Correctif :** refuser si `carte_maintenance.tireuses.exists()` et que la
  tireuse n'y figure pas (`_push_refus` avec un message traduit).

### 2.6 Refus sur tireuse désactivée non affiché

- **Où :** `viewsets.py:456`.
- **Constat :** le refus renvoie « Tap is disabled. » sans `_push_refus` : le
  kiosk n'affiche pas le refus.
- **Correctif :** ajouter `_push_refus(tireuse, _("Tireuse hors service."))`.

---

## Hors lots, relevés mais non instruits

- `ws_payloads.py` n'est importé nulle part, `force_close` n'est jamais émis,
  `RfidSession.last_message` n'est jamais écrit, `controlvanne/tests.py` est
  vide, et `ConfigurationTireuse` n'a aucun champ.
- `billing.py` importe des fonctions privées de `laboutik/views.py`
  (`_obtenir_ou_creer_wallet`, `_calculer_qty_partielles`) : il faudrait les
  déplacer dans un module `services`.
- `REMOTE_ADDR` derrière Traefik donne l'IP du proxy, pas celle du Pi.
- Docstring de `AuthKioskView` contradictoire : elle dit que le jeton ne passe
  pas en query string, alors que le Pi utilise `?kiosk_token=`.
