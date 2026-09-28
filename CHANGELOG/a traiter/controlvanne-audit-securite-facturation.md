# controlvanne : sécurité et facturation, suites de l'audit

**Relevé du 2026-09-26.** Il vient de trois audits en lecture seule de
`controlvanne/` : djc côté Python, djc côté templates/JS, et hallmark sur
l'interface. Les lots 3 (écran kiosk) et 4 (calibration, i18n, a11y) ont été
corrigés : voir `CHANGELOG/2026-09-26-controlvanne-audit.md`. Les lots 1 et 2
ci-dessous sont **volontairement mis en attente**.

Chaque point **critique** a été vérifié dans le code. Les autres viennent des
audits et sont à confirmer au moment de les traiter.

**Traités depuis :** 1.4 (clé ↔ tireuse), 1.5 (calibration réservée au lieu),
1.6 (limite sur `authorize`) → `CHANGELOG/2026-09-28-controlvanne-securite-cles-calibration.md`.

**Ordre de priorité proposé :** 1.1 + 1.2 ensemble (fuite WebSocket entre
lieux) → 2.1 (erreur de stock dans la facture) → 1.3 (redirection) → 2.3
(montants calculés par le serveur) → le reste.

> **À savoir tant que 1.1 et 1.2 ne sont pas faits :** un kiosk ouvert sur
> `/ws/rfid/all/` dans un lieu reçoit les passages de carte **des autres lieux**
> (prénom, UID de la carte, solde). N'importe quel navigateur, même non
> connecté, peut ouvrir ce WebSocket.

---

## Lot 1 — Sécurité : plan détaillé des points restants (1.1, 1.2, 1.3)

Les points 1.1 et 1.2 se font **dans le même changement** : ils touchent les
mêmes fonctions, et corriger l'un sans l'autre laisse la fuite ouverte.

### Contexte vérifié le 2026-09-28

- **Pile WebSocket** (`TiBillet/asgi.py`) :
  `AllowedHostsOriginValidator` → `WebSocketTenantMiddleware` →
  `AuthMiddlewareStack` → `URLRouter`.
  - `WebSocketTenantMiddleware` (`wsocket/middlewares.py`) pose
    `scope["tenant"]` à partir du nom de domaine. Il vaut **`None`** si le
    domaine est inconnu.
  - `AuthMiddlewareStack` pose `scope["session"]` (lu depuis le cookie
    `sessionid`) et `scope["user"]`.
  - **Piège :** lire `scope["session"]` ou appeler `is_tenant_admin` fait une
    requête en base. En async, il faut passer par `database_sync_to_async`, et
    rétablir le lieu dans ce thread (`connection.set_tenant`), comme le fait
    déjà `_construire_payload_initial` (`consumers.py`).
- **Qui a le droit de voir le kiosk (HTTP)** :
  `_verifier_authentification_kiosk` (`controlvanne/viewsets.py:1113`). Trois
  cas : session kiosk (`controlvanne_authenticated`), jeton à usage unique
  `?kiosk_token=`, ou admin du lieu.
- **Groupes Channels** : `rfid_state.all` et `rfid_state.<uuid tireuse>`.
  Redis est partagé par tous les lieux, sans préfixe
  (`TiBillet/settings.py:659`). **Cinq endroits** écrivent ou lisent ces noms :
  - `consumers.py:52` : `PanelConsumer.connect` (abonnement) ;
  - `viewsets.py:55` : `_push_ws_kiosk` (badge, versement, fin, refus) ;
  - `signals.py:39` : `demander_rechargement_des_kiosks` (changement de fût) ;
  - `signals.py:296` : `pousser_snapshot_apres_commit` (post_save de la tireuse) ;
  - les docstrings de `routing.py` et `consumers.py`.
- **Clé primaire des lieux** : `Client.uuid` (UUID). Un nom de groupe
  `rfid_state.<uuid lieu>.<uuid tireuse>` fait 84 caractères, sous la limite
  Channels de 100 (lettres, chiffres, `-`, `_`, `.`).
- **Sessions** : `SESSION_COOKIE_AGE` = 12 semaines, prolongé à chaque requête
  HTTP (`SESSION_SAVE_EVERY_REQUEST = True`). Le cookie est propre à chaque
  domaine (`SESSION_COOKIE_DOMAIN` désactivé), donc une session kiosk ne vaut
  que pour son lieu.
- **Outils de test disponibles** : `channels` 4.3.2, `pytest-asyncio` 1.3.0.
  Aucun test du consumer n'existe aujourd'hui.

### 1.1 Contrôle d'accès du consumer WebSocket

**Problème (vérifié) :** `PanelConsumer.connect()` fait `group_add` puis
`accept()` sans aucun contrôle. N'importe quel navigateur peut ouvrir
`wss://<lieu>/ws/rfid/all/` et recevoir les badges.

**Étapes :**

1. **Extraire la règle d'accès en une fonction commune, sans le jeton**, dans
   `controlvanne/viewsets.py` (ou un nouveau `controlvanne/acces.py` si l'on
   veut éviter que `consumers.py` importe `viewsets.py`) :
   ```python
   def peut_voir_les_kiosks(session, utilisateur, lieu):
       """Session kiosk OU admin du lieu. Synchrone (fait des requêtes)."""
       if session.get("controlvanne_authenticated"):
           return True
       if utilisateur and utilisateur.is_authenticated:
           return utilisateur.is_tenant_admin(lieu)
       return False
   ```
   `_verifier_authentification_kiosk` l'appelle pour ses cas 1 et 3 (le cas 2,
   le jeton, reste propre au HTTP). Une seule règle pour la page et le
   WebSocket.
2. **Dans `PanelConsumer.connect()`**, avant `group_add` :
   ```python
   lieu = self.scope.get("tenant")
   if lieu is None:
       await self.close(code=4003)   # domaine inconnu
       return
   acces_permis = await self._client_peut_voir_les_kiosks(lieu)
   if not acces_permis:
       await self.close(code=4003)   # ni kiosk ni admin du lieu
       return
   ```
   `_client_peut_voir_les_kiosks` est un `@database_sync_to_async` qui fait
   `connection.set_tenant(lieu)`, puis
   `peut_voir_les_kiosks(self.scope["session"], self.scope["user"], lieu)`.
   `close()` avant `accept()` : le navigateur reçoit un refus de handshake
   (HTTP 403).
3. **Côté écran (`ecran_tireuse.js`)** : rien à changer. Un refus déclenche
   `onclose`, donc le bandeau « connexion perdue » et une nouvelle tentative
   (1 s → 30 s). La page du kiosk exige déjà la même authentification, donc un
   kiosk légitime n'est jamais refusé.
4. **Journaliser les refus** (`logger.warning` avec le lieu et le slug, sans
   données de carte), pour repérer les tentatives.

**Risque à vérifier avant de livrer :** un kiosk qui reste des semaines sur la
même page ne fait que du WebSocket, et **le WebSocket ne prolonge pas la
session**. Au-delà de 12 semaines sans requête HTTP, sa reconnexion serait
refusée. Parade simple : dans `connect()`, une fois l'accès permis,
enregistrer la session (`session.save()` via `database_sync_to_async`) pour la
prolonger. Autre solution : le Pi se ré-authentifie à chaque démarrage, ce qui
est déjà le cas (`Pi/main.py:87`).

**Tests (`tests/pytest/test_controlvanne_ws.py`, nouveau)** : avec
`channels.testing.WebsocketCommunicator` et `@pytest.mark.asyncio`, construire
le `scope` à la main (le communicator ne passe pas par les middlewares) :
`scope["tenant"]`, `scope["session"]` (une vraie `SessionStore` enregistrée),
`scope["user"]`, `scope["url_route"]`. Cas à couvrir :
- anonyme → `connected is False` ;
- `scope["tenant"] = None` → refusé ;
- session kiosk → accepté ;
- admin du lieu → accepté ;
- admin d'un **autre** lieu → refusé.

### 1.2 Groupes Channels nommés par lieu

**Problème (vérifié) :** `rfid_state.all` est le même groupe pour tous les
lieux. Un kiosk « liste » du lieu A reçoit les badges du lieu B. (Les groupes
`rfid_state.<uuid tireuse>` sont de fait séparés, car les UUID sont uniques,
mais on les préfixe aussi pour avoir une seule règle.)

**Étapes :**

1. **Nouveau module `controlvanne/groupes_ws.py`**, sans import de
   `viewsets`/`signals`/`consumers`, pour éviter les imports circulaires :
   ```python
   def groupe_de_la_tireuse(uuid_du_lieu, uuid_de_la_tireuse):
       return f"rfid_state.{uuid_du_lieu}.{uuid_de_la_tireuse}"

   def groupe_de_tout_le_lieu(uuid_du_lieu):
       return f"rfid_state.{uuid_du_lieu}.all"

   def pousser_aux_kiosks(tireuse, payload):
       """Envoie payload au groupe de la tireuse ET au groupe « all » du lieu.
       Lieu courant : connection.tenant (on est dans une requête HTTP ou un
       on_commit de cette requête)."""
   ```
2. **Remplacer les trois émetteurs par `pousser_aux_kiosks`** :
   - `viewsets._push_ws_kiosk` ;
   - `signals.demander_rechargement_des_kiosks` ;
   - `signals.pousser_snapshot_apres_commit`.
   Les trois font aujourd'hui deux `group_send` presque identiques : les
   regrouper supprime la duplication.
3. **Dans `PanelConsumer.connect()`** (après le contrôle du 1.1) :
   `self.group = groupe_de_tout_le_lieu(lieu.uuid)` ou
   `groupe_de_la_tireuse(lieu.uuid, slug)`.
4. **Valider le slug** : aujourd'hui n'importe quelle chaîne devient un nom de
   groupe. Accepter seulement `all` ou un UUID de tireuse **de ce lieu**
   (`TireuseBec.objects.filter(uuid=slug).exists()` dans le même appel
   `database_sync_to_async`). Sinon, `close()`.
5. **Mettre à jour** les docstrings de `routing.py` et `consumers.py`, et la
   section WebSocket de `controlvanne/README.md`.

**Déploiement :** les kiosks déjà ouverts sont abonnés aux anciens noms. Le
redémarrage de daphne au déploiement ferme leurs WebSocket, et
`ecran_tireuse.js` se reconnecte tout seul (1 s → 30 s) sur les nouveaux noms.
Rien à faire à la main. On peut aussi pousser un `kiosk_reload` avant, par
précaution.

**Tests** :
- dans `test_controlvanne_ws.py`, le groupe du consumer contient l'UUID du
  lieu ;
- avec un faux channel layer (comme `_CanalFictif` dans
  `test_controlvanne_ecran_calibration.py`), `pousser_aux_kiosks` n'écrit que
  dans les groupes du lieu courant ;
- mettre à jour les tests existants qui vérifient `rfid_state.<uuid>` et
  `rfid_state.all` (`TestRechargementDuKiosk`).

### 1.3 Redirection du jeton kiosk (`KioskTokenView`)

**Problème (vérifié) :** `viewsets.py:1090`,
`next_url = request.GET.get("next", …)` est seulement passé dans
`escape(iri_to_uri(...))`. Deux conséquences :
- `https://autre-site` est accepté (redirection ouverte) ;
- `javascript:…` est exécuté par `<script>window.location.replace('…')</script>`
  (l'échappement HTML ne protège pas une URL `javascript:`).
Il faut un jeton valide, à usage unique et d'une durée de vie de 5 min : le
risque est faible, mais réel.

**Constat en plus :** le Pi actuel **n'utilise pas** cette vue. Il passe le
jeton directement à la page du kiosk (`?kiosk_token=`, `Pi/main.py:88`),
consommé par `_verifier_authentification_kiosk`. `KioskTokenView` n'est
référencée que par `urls.py` et des commentaires (`Pi/network/backend_client.py:128`).

**Deux options, à choisir :**
- **A — Supprimer `KioskTokenView`** (recommandé si aucun ancien Pi ne
  l'utilise) : retirer la vue, sa route `kiosk-token/<token>/` et les
  commentaires qui la citent (`viewsets.py`, `backend_client.py`). Plus de code
  = plus de risque. Avant, vérifier dans les logs de production qu'aucun appel
  à `/controlvanne/kiosk-token/` n'arrive.
- **B — La garder et la corriger** :
  1. `from django.utils.http import url_has_allowed_host_and_scheme` ;
  2. si `not url_has_allowed_host_and_scheme(next_url,
     allowed_hosts={request.get_host()}, require_https=request.is_secure())`,
     alors `next_url = "/controlvanne/kiosk/"` ;
  3. supprimer le `<script>window.location.replace(...)</script>`. Le
     `<meta http-equiv="refresh">` et le lien suffisent, et on n'injecte plus
     d'URL dans du JavaScript ;
  4. mettre à jour la docstring de `AuthKioskView`, qui dit que le jeton ne
     passe pas en query string, ce qui est faux (voir « Hors lots »).

**Tests (option B)**, dans `test_controlvanne_api.py` : jeton valide mis en
cache, puis
- `next=https://evil.example` → la page pointe vers `/controlvanne/kiosk/` ;
- `next=javascript:alert(1)` → idem, et aucune balise `<script>` dans la
  réponse ;
- `next=/controlvanne/kiosk/<uuid>/` → conservé.
Option A : un test vérifie que `/controlvanne/kiosk-token/x/` renvoie 404.

### Vérification commune (1.1 + 1.2 + 1.3)

1. `pytest tests/pytest/test_controlvanne_*.py -q` : tout passe, y compris le
   nouveau `test_controlvanne_ws.py`.
2. À la main, deux lieux ouverts dans deux onglets (`/controlvanne/kiosk/`) :
   un badge dans le lieu A n'apparaît pas dans la liste du lieu B.
3. Dans la console d'un navigateur non connecté :
   `new WebSocket("wss://<lieu>/ws/rfid/all/")` → fermé tout de suite
   (code 1006 côté navigateur).
4. Le kiosk réel d'un Pi (session kiosk) continue de recevoir ses messages
   après un redémarrage de daphne.

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
