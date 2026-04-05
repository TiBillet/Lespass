# Spec — Integration controlvanne dans Lespass

Date : 2026-04-05
Statut : VALIDE (brainstorming termine)

---

## 1. Vision

Integrer l'app `controlvanne` (tireuse a biere connectee avec paiement cashless NFC)
dans le mono-repo Lespass. La tireuse est traitee comme un **point de vente** (POS)
qui accepte uniquement le cashless. Tous les modeles mock (Card, Fut, Configuration)
sont remplaces par les modeles existants de Lespass.

---

## 2. Decisions architecturales

### 2.1 Placement dans les apps

**TENANT_APPS.** Chaque lieu (tenant) a ses propres tireuses, futs, historiques, sessions.

### 2.2 Modele `Card` → supprime

Remplace par `CarteCashless` (SHARED_APPS, identification NFC) + `fedow_core.Token` (solde wallet).
La vue `api_rfid_authorize` interroge le wallet via `WalletService` au lieu de `Card.balance`.

### 2.3 Modele `Fut` → supprime, remplace par `Product` + proxy `FutProduct`

- Nouvelle categorie `FUT` sur `Product.categorie_article`
- Proxy `FutProduct(Product)` pour l'admin controlvanne (formulaire restreint)
- Les infos brasseur/type/degre vont dans `long_description`
- Le prix au litre est un `Price` lie au `FutProduct`
- Le stock est gere par l'app `inventaire` (modele `Stock` + `MouvementStock`)
- `TireuseBec.fut_actif` → FK vers `Product` (filtre `categorie_article=FUT`)

### 2.4 Modele `Configuration` → singleton django-solo dans controlvanne

`controlvanne.Configuration(SingletonModel)` avec les champs propres au module tireuse.
Le champ `allow_self_register` est supprime (remplace par l'appairage PIN).

### 2.5 Appairage Pi → `discovery.PairingDevice`

Suppression de `api_rfid_register` + `Configuration.allow_self_register`.
Reutilisation de `discovery.PairingDevice` (PIN 6 chiffres).

Flow :
1. Admin cree un `PairingDevice` dans Unfold → PIN genere
2. Le Pi envoie le PIN via `POST /api/discovery/claim/`
3. Discovery renvoie un token API + UUID de la `TireuseBec` + URL du tenant
4. Le Pi stocke le token dans son `.env`

### 2.6 Auth API Pi → ViewSet DRF + permission `HasTireuseAccess`

Conformite skill djc : ViewSet explicite, pas de `@csrf_exempt` ni de check maison.

- Les endpoints `ping`, `authorize`, `event` deviennent des actions d'un `TireuseViewSet`
- Permission `HasTireuseAccess` : verifie le token API (recu au claim) et que le Pi
  est bien associe a une `TireuseBec` du tenant courant
- Header `Authorization: Api-Key <key>`

### 2.7 Auth kiosk → session Django via POST token

Le token ne doit pas fuiter en query string (logs, referer, historique navigateur).

Flow :
1. Le Pi fait `POST /controlvanne/auth-kiosk/` avec header `Authorization: Api-Key <key>`
2. Django verifie le token, cree une session, renvoie `Set-Cookie: sessionid=xxx`
3. Le Pi recupere le cookie et lance Chromium avec le cookie de session
4. Le WebSocket herite du cookie via `AuthMiddlewareStack` (deja en place dans `asgi.py`)

### 2.8 `CarteMaintenance` → OneToOne vers `CarteCashless`

Meme pattern que `CartePrimaire` de laboutik. Une `CarteCashless` avec un role
"maintenance" et des permissions sur certaines tireuses.

```python
class CarteMaintenance(models.Model):
    carte = models.OneToOneField(CarteCashless, on_delete=models.CASCADE)
    tireuses = models.ManyToManyField(TireuseBec, blank=True)
    produit = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
```

Flow dans `api_rfid_authorize` :
1. Badge NFC → chercher `CarteCashless` par `tag_id`
2. Si `carte.carte_maintenance` existe → mode rincage (pas de facturation)
3. Sinon → mode normal, verifier le wallet fedow_core

### 2.9 `TireuseBec` — changements

**Champs supprimes :**
- `monnaie` (CharField) — la monnaie vient de l'Asset TLF du tenant
- `prix_litre_override` — le prix vient uniquement du `Price` lie au `FutProduct`

**Champs modifies :**
- `fut_actif` → FK vers `Product` (filtre `categorie_article=FUT`) au lieu de FK `Fut`

**Champs ajoutes :**
- `point_de_vente` → OneToOne vers `PointDeVente` (type `TIREUSE`)
- `pairing_device` → FK nullable vers `discovery.PairingDevice`

**Champs inchanges :**
- `uuid` PK, `nom_tireuse`, `enabled`, `notes`
- `debimetre` FK vers `Debimetre`
- `reservoir_ml`, `seuil_mini_ml`, `appliquer_reserve`

### 2.10 `PointDeVente` — nouveau type `TIREUSE`

Ajout de `TIREUSE = "TI"` dans les choices de `PointDeVente.comportement`.
La tireuse est un POS qui accepte uniquement le cashless NFC.

### 2.11 `Debimetre` — inchange

Modele purement technique propre aux tireuses. Reste dans `controlvanne.models`.

### 2.12 `RfidSession` — recentre sur le journal physique

La facturation passe par `LigneArticle` + `fedow_core.Transaction` + `MouvementStock`.
La session reste le journal du tirage physique (volumes, duree, vanne).

**Champs supprimes :**
- `card` FK vers `controlvanne.Card`
- `balance_avant`, `balance_apres`
- `charged_units`
- `unit_label_snapshot`, `unit_ml_snapshot`

**Champs ajoutes :**
- `carte` FK nullable vers `CarteCashless`
- `ligne_article` FK nullable vers `LigneArticle`

**Champs inchanges :**
- `uid`, `tireuse_bec`, `started_at`, `ended_at`
- `volume_start_ml`, `volume_end_ml`, `volume_delta_ml`, `dernier_volume_ml`
- `allowed_ml_session`, `authorized`, `last_message`
- `is_maintenance`, `is_calibration`, `volume_reel_ml`
- `carte_maintenance` FK (vers le nouveau `CarteMaintenance`)
- `liquid_label_snapshot`, `label_snapshot`
- `produit_maintenance_snapshot`

**Proxy models inchanges :** `HistoriqueCarte`, `HistoriqueTireuse`,
`HistoriqueMaintenance`, `SessionCalibration`

### 2.13 Facturation — circuit existant laboutik/fedow_core

La tireuse utilise le meme circuit qu'un paiement NFC au bar :

1. Badge NFC → `CarteCashless` → wallet
2. Verifier solde `Token` (asset TLF) via `WalletService.obtenir_solde()`
3. Calculer volume max autorise (solde / prix_litre)
4. Au `pour_end` : `TransactionService.creer_vente()` → debit wallet client
5. Creer `LigneArticle` avec `payment_method=LOCAL_EURO`, `carte`, `wallet`, `asset`
6. `MouvementStock` via inventaire (type `DM` debit compteur ou `VE` vente)

### 2.14 WebSocket — consumer dans controlvanne, routes dans asgi.py

- `PanelConsumer` reste dans `controlvanne/consumers.py`
- `controlvanne/routing.py` garde ses patterns (`ws/rfid/<slug>/`)
- `asgi.py` combine les routes de `wsocket` et de `controlvanne`
- `WebSocketTenantMiddleware` existant resout le tenant pour controlvanne aussi
- `PanelConsumer` doit utiliser `scope["tenant"]`

### 2.15 Admin Unfold

- Enregistrement sur `staff_admin_site` (pas `admin.site`)
- Section sidebar "Tireuses" conditionnelle sur `module_tireuse`
- Permissions via `TenantAdminPermissionWithRequest`
- Entrees : Tireuses, Produits fut, Debimetres, Cartes maintenance,
  Sessions/Historiques, Configuration

### 2.16 Templates kiosk — base template autonome

Le kiosk garde son propre base template leger (pas le skin Lespass).
C'est un ecran dedie sur un Pi HDMI — pas de sidebar, header, footer Lespass.

Changements :
- Remplacer "Mike's Bar" par le nom du tenant (`config.organisation`)
- Charger Bootstrap depuis les statics Lespass (le Pi peut etre hors-ligne)
- Ajouter `data-testid`, `aria-*`, `{% translate %}`
- Extraire le JS dans `controlvanne/static/controlvanne/js/panel_kiosk.js`
- Les donnees initiales via `data-*` sur les elements HTML
- Le WebSocket reste en JS (pas d'alternative HTMX pour du push serveur)

### 2.17 Templates calibration — integrer dans l'admin Unfold

Les templates de calibration sont des pages admin HTMX.
Elles doivent heriter du base admin Unfold.

---

## 3. Modeles — resume final

### Modeles supprimes
- `controlvanne.Card` (remplace par `CarteCashless` + `fedow_core.Token`)
- `controlvanne.Fut` (remplace par `Product` categorie `FUT` + proxy `FutProduct`)

### Modeles crees
- `controlvanne.Configuration` (SingletonModel django-solo)
- `controlvanne.CarteMaintenance` (OneToOne `CarteCashless`, M2M `TireuseBec`)
- `BaseBillet.FutProduct` (proxy Product, zero migration)

### Modeles modifies
- `controlvanne.TireuseBec` : voir section 2.9
- `controlvanne.RfidSession` : voir section 2.12
- `laboutik.PointDeVente` : ajout type `TIREUSE` dans choices
- `BaseBillet.Product` : ajout categorie `FUT` dans choices

### Modeles inchanges
- `controlvanne.Debimetre`
- `controlvanne.HistoriqueFut` (adapte : FK vers `Product` au lieu de `Fut`)
- Les 4 proxy de `RfidSession`

---

## 4. Phases d'implementation

### Phase 0 — Branchement minimal

Objectif : l'app tourne dans Lespass, on peut creer des tireuses dans l'admin.

- `controlvanne` dans TENANT_APPS + `settings.py`
- URLs dans `urls_tenants.py`
- WebSocket dans `asgi.py` (import `controlvanne.routing`)
- Migrations avec les modeles existants (tels quels, y compris les mocks)
- Admin enregistre sur `staff_admin_site`
- `module_tireuse` BooleanField sur `BaseBillet.Configuration`
- Sidebar conditionnelle

### Phase 1 — Refactoring modeles

Objectif : les modeles controlvanne utilisent les modeles Lespass existants.

- Supprimer `Card`, `Fut`, `Configuration` maison
- `CarteMaintenance` → OneToOne vers `CarteCashless`
- `FutProduct` proxy + categorie `FUT` sur `Product`
- `TireuseBec` → OneToOne `PointDeVente` (type `TIREUSE`), FK `PairingDevice`,
  FK `Product` pour `fut_actif`, supprimer `monnaie` et `prix_litre_override`
- `RfidSession` → FK `CarteCashless`, FK `LigneArticle`, supprimer champs financiers
- `controlvanne.Configuration` en django-solo
- `HistoriqueFut` → FK vers `Product`
- Migrations

### Phase 2 — Auth + API DRF

Objectif : le Pi s'authentifie proprement et communique via DRF.

- Appairage via `discovery.PairingDevice`
- Auth kiosk (POST token → session cookie)
- `TireuseViewSet` avec permission `HasTireuseAccess`
- Actions : `ping`, `authorize`, `event`
- Supprimer les anciennes vues fonctionnelles

### Phase 3 — Facturation fedow_core

Objectif : les tirages sont factures via le circuit existant.

- `authorize` → verifie solde wallet via `WalletService`
- `pour_end` → `TransactionService.creer_vente()` + `LigneArticle` + `MouvementStock`
- Plus de debit `card.balance`, tout passe par le circuit laboutik/fedow_core
- Cloture de caisse inclut les ventes tireuse

### Phase 4 — Templates + conformite djc

Objectif : le front est conforme aux standards Lespass.

- Kiosk : base template propre avec nom tenant, Bootstrap local,
  `data-testid`, `aria-*`, `{% translate %}`, JS externalise
- Calibration : heritage base admin Unfold
- Filtre date admin : compatible Unfold
- Commentaires FALC bilingues FR/EN

### Phase 5 — Tests

Objectif : couverture pytest + E2E.

- pytest DB-only : modeles, services, API DRF, facturation, permissions
- E2E Playwright : kiosk WebSocket, admin tireuses, calibration HTMX
- Conformite TESTS_README.md (pieges documentes)

### Phase 6+ — Client Pi (chantier separe)

Objectif : adapter le code Python du Raspberry Pi aux nouveaux endpoints.

- Adapter les appels API vers le `TireuseViewSet` DRF
- Remplacer l'auth `X-API-Key` maison par le token de pairing discovery
- Adapter le flow kiosk (POST token → cookie → Chromium)
- Mettre a jour `install.sh` et `.env`
- Tests hardware (NFC, debitmetre, electrovanne)
- **Ce chantier est planifie apres la stabilisation de l'API Django (fin phase 2).**

---

## 5. Fichiers cles concernes

### Fichiers a creer
- `controlvanne/viewsets.py` (TireuseViewSet DRF)
- `controlvanne/serializers.py` (validation DRF)
- `controlvanne/permissions.py` (HasTireuseAccess)
- `controlvanne/static/controlvanne/js/panel_kiosk.js`
- Tests : `tests/pytest/test_controlvanne_*.py`, `tests/e2e/test_controlvanne_*.py`

### Fichiers a modifier
- `TiBillet/settings.py` : TENANT_APPS + module_tireuse
- `TiBillet/asgi.py` : import controlvanne.routing
- `TiBillet/urls_tenants.py` : include controlvanne.urls
- `BaseBillet/models.py` : categorie FUT + proxy FutProduct
- `laboutik/models.py` : type TIREUSE sur PointDeVente
- `Administration/admin_tenant.py` : sidebar conditionnelle module_tireuse
- `controlvanne/models.py` : refactoring complet (voir sections 2.x)
- `controlvanne/admin.py` : staff_admin_site + permissions
- `controlvanne/consumers.py` : scope["tenant"]
- `controlvanne/signals.py` : adapter aux nouveaux modeles
- `controlvanne/templates/` : conformite djc

### Fichiers a supprimer
- `controlvanne/views.py` (remplace par viewsets.py)
- `controlvanne/forms.py` (remplace par serializers.py)

---

## 6. Risques et points de vigilance

1. **Coexistence phase 0** : les modeles mock (`Card`, `Fut`) cohabitent temporairement
   avec les modeles Lespass. Phase 1 les supprime.

2. **Migration des donnees** : si des donnees de test existent avec les anciens modeles,
   prevoir une data migration pour les convertir (ou les purger).

3. **WebSocket tenant** : `PanelConsumer` doit gerer `scope["tenant"]` correctement.
   Le `WebSocketTenantMiddleware` existant le fournit, mais le consumer ne l'utilise
   pas encore — a verifier.

4. **Inventaire debit compteur** : le `MouvementStock` de type `DM` (debit compteur)
   n'existe peut-etre pas encore. A verifier si on utilise `VE` (vente) ou si on
   cree un nouveau type.

5. **Prix au litre** : la tireuse vend au volume. Le champ `Price.poids_mesure=True`
   existe deja et gere exactement ce cas : le prix est par litre, la quantite saisie
   est en centilitres (unite stock), et `LigneArticle.weight_quantity` stocke le volume
   verse. Pas de risque de compatibilite — le mecanisme est deja code.

6. **Kiosk hors-ligne** : le Pi peut perdre la connexion reseau. Le kiosk doit
   gerer la reconnexion WebSocket (deja le cas dans le JS actuel avec `onclose → reconnect`).
   Mais les requetes API echoueront — le Pi doit gerer ce cas cote client.
