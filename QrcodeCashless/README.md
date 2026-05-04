# QrcodeCashless — Cartes NFC cashless TiBillet

App Django **SHARED_APPS** (schema `public`) qui modelise la carte physique NFC
(pont entre l'objet matériel et l'utilisateur·ice TiBillet). Elle est volontairement
minimaliste : **aucune logique métier**, juste les modèles et un management command
pour creer des cartes de test. Toute la logique de paiement vit dans
`fedow_core/services.py` et `laboutik/views.py`.

> **Important :** la carte NFC n'est qu'un **identifiant physique**. Elle ne contient
> ni solde, ni monnaie. Le solde est porté par un `Wallet` (AuthBillet) qui agrège
> des `Token` (fedow_core), un par `Asset` (monnaie/token).

---

## 1. Modèles de l'app

### `Detail` — batch de cartes

Représente un lot de cartes (génération, image recto, lieu d'origine).
Permet de regrouper les cartes d'un même festival, d'une même commande, etc.

| Champ | Type | Rôle |
|---|---|---|
| `uuid` | UUIDField | Identifiant interne |
| `img` | StdImageField | Visuel imprimé sur la carte (recto) |
| `img_url`, `base_url` | URL/Char | URL de redirection scan QR |
| `origine` | FK `Customers.Client` | Tenant qui a commandé / produit le batch |
| `generation` | SmallInt | Génération du lot (v1, v2, …) |
| `slug` | SlugField unique | Identifiant lisible (ex: `test-pos-cards`) |

### `CarteCashless` — la carte physique

Le modèle central de l'app. Une ligne = une carte NFC unique.

| Champ | Type | Rôle |
|---|---|---|
| `tag_id` | CharField(8) unique | **UID hexadécimal lu par le lecteur RFID** (ex: `52BE6543`). Clé de recherche principale du POS. |
| `uuid` | UUIDField unique | Identifiant interne TiBillet (utilisé dans les URLs QR code legacy) |
| `number` | CharField(8) unique | Numéro court imprimé sur la carte |
| `detail` | FK `Detail` | Batch d'origine (pour le visuel et le lieu créateur) |
| `user` | FK `AuthBillet.TibilletUser` (nullable) | **Utilisateur·ice identifié·e**, après scan + email, ou aucun si carte anonyme |
| `wallet_ephemere` | OneToOne `AuthBillet.Wallet` (nullable, `SET_NULL`) | **Wallet temporaire** pour cartes anonymes. Détaché lors de la fusion vers `user.wallet` |

**Contraintes critiques :**
- `tag_id` et `number` font **max 8 caractères** (cf. piège 9.31 dans `tests/PIEGES.md`).
- Le modèle vit en `SHARED_APPS` (schema `public`) — donc en `FastTenantTestCase`,
  la table n'existe pas dans le schema de test ; utiliser `schema_context('lespass')`
  + `APIClient` (cf. piège 9.30).

---

## 2. Carte des relations entre modèles

```
                       ┌────────────────────────┐
                       │  CarteCashless         │   (SHARED_APPS, public)
                       │  ──────────────        │
                       │  tag_id  (RFID UID)    │
                       │  number  (imprimé)     │
                       │  uuid                  │
                       └────┬─────────┬─────────┘
                            │         │
                  detail FK │         │ user FK (nullable)
                            ▼         ▼
                  ┌───────────┐   ┌───────────────────────┐
                  │  Detail   │   │  AuthBillet.          │
                  │  (batch)  │   │  TibilletUser         │
                  └─────┬─────┘   └──────────┬────────────┘
                        │                    │ wallet OneToOne
                        │ origine FK         ▼
                        ▼            ┌────────────────────┐
                  ┌───────────┐      │  AuthBillet.Wallet │
                  │ Customers │      │  ───────────────   │
                  │  .Client  │      │  uuid (PK)         │
                  │ (tenant)  │      │  origin → Client   │
                  └───────────┘      │  name              │
                                     │  public_pem        │
                                     └─────────┬──────────┘
                            wallet_ephemere    │
                            OneToOne (nullable)│ (1 wallet ↔ N tokens)
                                  ▲            │
                                  │            ▼
                  ┌───────────────┴──────────────────────┐
                  │                              ┌──────────────┐
                  │                              │  fedow_core. │
                  │                              │  Token       │
                  │                              │  ─────────   │
                  │                              │  wallet FK   │
                  │                              │  asset FK    │
                  │                              │  value (¢)   │
                  │                              └──────┬───────┘
                  │                                     │
                  │                                     ▼
                  │                              ┌──────────────┐
                  │                              │ fedow_core.  │
                  │                              │ Asset        │
                  │                              │ ───────      │
                  │                              │ category     │
                  │                              │ (TLF/TNF/    │
                  │                              │  FED/TIM/    │
                  │                              │  FID)        │
                  │                              │ tenant_      │
                  │                              │ origin FK    │
                  │                              │ wallet_      │
                  │                              │ origin FK    │
                  │                              └──────────────┘
                  │
                  │  carte FK (nullable)  ┌───────────────────────────┐
                  └─────────────────────► │ fedow_core.Transaction    │
                                          │ ─────────────────         │
                                          │ id (BigAutoField, PK)     │
                                          │ uuid                      │
                                          │ sender FK Wallet          │
                                          │ receiver FK Wallet        │
                                          │ asset FK                  │
                                          │ amount (¢)                │
                                          │ action (SAL/RFL/FUS/…)    │
                                          │ tenant FK Client          │
                                          │ card FK CarteCashless     │
                                          │ primary_card FK Carte…    │
                                          └───────────────────────────┘

                  │  carte (OneToOne)
                  └─────► laboutik.CartePrimaire  (TENANT_APPS)
                                ─────────────
                                edit_mode (bool)
                                points_de_vente M2M
```

### Lecture des cardinalités

- **CarteCashless ↔ TibilletUser** : `0..1 ↔ 1` (carte anonyme ou liée à un user).
- **CarteCashless ↔ Wallet (éphémère)** : `OneToOne` nullable. Détaché après fusion.
- **TibilletUser ↔ Wallet** : `OneToOne` (1 user = 1 wallet permanent).
- **Wallet ↔ Token** : `1 → N`, un Token par `Asset`.
- **Asset** : créé par 1 tenant (`tenant_origin`), partageable via `Federation`.
- **CarteCashless ↔ Transaction** : `1 → N` (toutes les transactions effectuées avec cette carte).
- **CarteCashless ↔ CartePrimaire** : `OneToOne`. Les cartes manager du POS sont des `CarteCashless` reliées à une `CartePrimaire`.

---

## 3. Cycle de vie d'une carte NFC

```
[1] CRÉATION
    create_test_carte 52BE6543
    └─ CarteCashless(tag_id=52BE6543, user=None, wallet_ephemere=None)

[2] PREMIER SCAN AU POS
    Scan NFC → POST /laboutik/paiement/retour_carte/  (tag_id=52BE6543)
    └─ _obtenir_ou_creer_wallet(carte) :
       ├─ carte.user existe ?         → renvoie user.wallet
       ├─ wallet_ephemere existe ?    → renvoie wallet_ephemere
       └─ sinon                       → crée Wallet(origin=tenant, name="Éphémère - 52BE6543")
                                        carte.wallet_ephemere = wallet  (save)
    └─ Affiche solde réel via WalletService.obtenir_tous_les_soldes(wallet)

[3] RECHARGE (carte anonyme OK)
    Caissier ajoute "Recharge 10€" au panier, encaisse en CB/espèces
    └─ _executer_recharges() :
       ├─ wallet_client = _obtenir_ou_creer_wallet(carte_client)
       └─ TransactionService.creer_recharge(
              sender_wallet = asset.wallet_origin,    (le lieu émet)
              receiver_wallet = wallet_client,        (le client reçoit)
              asset = produit.asset,
              montant = 1000,                         (centimes)
              tenant, ip)
       └─ Ligne de caisse créée par _creer_lignes_articles(asset_uuid, carte, wallet)

[4] PAIEMENT NFC (cascade multi-asset)
    Cascade ORDRE_CASCADE_FIDUCIAIRE = [TNF, FED, TLF]  (cadeau d'abord, fédéré, local)
    └─ Pour chaque article, on consomme dans l'ordre de la cascade
       jusqu'à couvrir le montant. Sinon : complément espèce/CB ou 2e carte.
    └─ TransactionService.creer_vente(sender=carte.wallet, receiver=asset.wallet_origin)
    └─ LigneArticle créées par _creer_lignes_articles_cascade()

[5] FUSION VERS UN USER (au moment de l'adhésion ou identification)
    Caissier scanne la carte ET saisit l'email
    └─ user = get_or_create_user(email)
    └─ WalletService.fusionner_wallet_ephemere(carte, user, tenant, ip) :
       ├─ Crée user.wallet si inexistant
       ├─ Pour chaque Token(wallet_ephemere, value > 0) :
       │  └─ TransactionService.creer(action=FUSION, sender=ephemere, receiver=user.wallet)
       ├─ carte.user = user
       └─ carte.wallet_ephemere = None  (le wallet éphémère reste en BDD pour l'audit)
```

---

## 4. Comment LaBoutik (POS) utilise la carte

Tout vit dans `laboutik/views.py`. Les imports principaux :

```python
from QrcodeCashless.models import CarteCashless
from fedow_core.services import AssetService, WalletService, TransactionService
```

### 4.1 Helpers centraux (`laboutik/views.py`)

| Helper | Rôle | Ligne |
|---|---|---|
| `_charger_carte_primaire(tag_id)` | Cherche la carte caissier (CartePrimaire) | ~922 |
| `_obtenir_ou_creer_wallet(carte)` | Renvoie `user.wallet` ou `wallet_ephemere`, crée le wallet éphémère sinon | ~941 |

### 4.2 Endpoints POS qui touchent la carte

| URL | Méthode | Rôle |
|---|---|---|
| `POST /laboutik/paiement/retour_carte/` | POS | Affiche le solde réel + adhésions actives après scan (couleur fond : vert si user, orange si anonyme) |
| `GET  /laboutik/paiement/lire_nfc/` | POS | Attend la lecture NFC pour paiement cashless |
| `GET  /laboutik/paiement/lire_nfc_complement/` | POS | Lecture d'une **2e carte** quand la 1re ne suffit pas (cascade) |
| `POST /laboutik/paiement/payer/` | POS | Exécute le paiement (NFC, espèces, CB, mixte) |
| `GET  /laboutik/paiement/verifier_carte/` | POS | Vérification simple du solde |

### 4.3 Cas d'usage métier dans laboutik

| Cas | Code | Identification |
|---|---|---|
| **Caissier·ère** scanne sa carte primaire | `_charger_carte_primaire()` | `CartePrimaire.objects.get(carte=carte_cashless)` |
| **Recharge** carte client | `_executer_recharges()` (~4423) | `tag_id` du POST → `CarteCashless.objects.get(tag_id=…)` |
| **Vente NFC** simple | `_payer_par_nfc()` | idem, puis `WalletService.obtenir_solde()` |
| **Vente NFC en cascade** TNF→FED→TLF | `_creer_lignes_articles_cascade()` (~3701) | 1 LigneArticle par asset débité |
| **Vente NFC + complément CB/espèce** | views.py ~6150 | `tag_id_carte1` lit la carte 1 |
| **Vente NFC + 2e carte (carte_complement)** | views.py ~6481 | `tag_id_carte2` lit la 2e carte |
| **Adhésion + scan NFC** | `_creer_adhesions_depuis_panier()` (~4080) | scan NFC → `WalletService.fusionner_wallet_ephemere()` |
| **Billet + scan NFC** | `_creer_billets_depuis_panier()` (~4254) | scan NFC → `carte.user` ou fallback email |

### 4.4 Lien comptable : `BaseBillet.LigneArticle`

Chaque vente cashless crée une `LigneArticle` (TENANT_APP) avec :

```python
asset    = UUIDField  # uuid de fedow_core.Asset (pas une FK : cross-schema impossible)
carte    = FK CarteCashless           # PROTECT
wallet   = FK AuthBillet.Wallet       # PROTECT
```

C'est ainsi qu'on retrace, dans le tenant, quelle carte a payé quel article avec quelle monnaie — sans avoir besoin d'une FK cross-schema vers `fedow_core.Transaction`.

### 4.5 `laboutik.CartePrimaire` (carte caissier·ère)

```python
class CartePrimaire(models.Model):
    carte = OneToOneField(CarteCashless, …)   # la carte physique du caissier
    points_de_vente = ManyToManyField(PointDeVente, …)
    edit_mode = BooleanField(default=False)
```

Une carte primaire est **une `CarteCashless` enrichie** d'une autorisation POS : scanner la carte sur la tablette ouvre la session de caisse et expose les PV autorisés. Le champ `edit_mode` autorise la modification des produits/prix depuis l'interface POS.

---

## 5. Initier un paiement depuis le navigateur — `/my_account/balance/`

> **À retenir :** ce flow utilise **encore Fedow V1** (`fedow_connect.fedow_api.FedowAPI`,
> serveur Fedow distant via HTTP). Il n'est **pas encore migré vers `fedow_core`** —
> c'est de la dette technique à traiter. Côté V2, l'équivalent passera par
> `fedow_core.services.TransactionService.creer_vente()`.

### 5.1 Page `/my_account/balance/`

| Élément | Localisation | Rôle |
|---|---|---|
| Vue | `BaseBillet/views.py:750` (`MyAccount.balance`) | Rend la page solde + bouton "Initier un paiement" si `profile.admin_this_tenant` ou `profile.can_initiate_payment` |
| Template | `BaseBillet/templates/reunion/views/account/balance.html` | Boutons : recharge, scanner QR (utilisateur), initier paiement (admin), demande remboursement |
| Liste tokens | `hx-get /my_account/tokens_table/` | Chargement HTMX des soldes |
| Historique | `hx-get /my_account/transactions_table/` | Chargement HTMX différé |

### 5.2 ViewSet `QrCodeScanPay` (`BaseBillet/views.py:1106`)

ViewSet qui gère **les deux côtés** d'un paiement entre comptes utilisateur·ices TiBillet
sans passer par une caisse physique.

| URL | Méthode | Permission | Rôle |
|---|---|---|---|
| `GET /qrcodescanpay/get_generator/` | View | `CanInitiatePaymentPermission` | Formulaire (montant, devise) — **côté receveur** (le collectif) |
| `POST /qrcodescanpay/generate_qrcode/` | View | idem | Crée une `LigneArticle(status=CREATED, payment_method=QRCODE_MA, sale_origin=QRCODE_MA)` puis génère un QR vers `https://<tenant>/qrcodescanpay/<uuid_hex>/process_qrcode` |
| `GET /qrcodescanpay/get_scanner/` | View | `IsAuthenticated` + `email_valid` | Active la caméra (`qr-scanner.min.js`) — **côté payeur** |
| `GET /qrcodescanpay/<uuid>/process_qrcode/` | Resolve | `AllowAny` (redirige vers login si besoin) | Recharge la `LigneArticle`, vérifie le solde du payeur, affiche `payment_validation.html` |
| `POST /qrcodescanpay/valid_payment/` | Confirm | `IsAuthenticated` | Exécute la transaction Fedow + Stripe Connect (split entre tenants) |
| `POST /qrcodescanpay/process_with_nfc/` | NFC tap | `CanInitiatePaymentPermission` | **Variante NFC** : remplace le scan caméra par une lecture NFC navigateur (cf. §5.4) |
| `GET /qrcodescanpay/<uuid>/check_payment/` | Polling HTMX | `CanInitiatePaymentPermission` | Bouton "Vérifier le paiement" — renvoie un fragment selon `LigneArticle.status` |

### 5.3 Cycle de vie d'une `LigneArticle` QR/NFC

```
[1] generate_qrcode  → LigneArticle.status = CREATED
                       payment_method   = PaymentMethod.QRCODE_MA
                       sale_origin      = SaleOrigin.QRCODE_MA
                       metadata         = {"admin": <email>}
                       (PAS de wallet, PAS de carte, PAS d'asset)

[2] Le receveur affiche le QR ET/OU clique "Lire la carte TiBillet (NFC)".

[3a] CHEMIN QR — le payeur scanne avec son téléphone
     → process_qrcode (resolve UUID hex, check solde Fedow)
     → payment_validation.html
     → POST valid_payment
     → Fedow API → tokens débités → LigneArticle.status = VALID

[3b] CHEMIN NFC — le receveur tape la carte du payeur sur SON téléphone
     → process_with_nfc (validator NFC, voir §5.4)
     → Fedow API to_place_from_qrcode (peut splitter en 2 LigneArticle si TLF + FED)
     → LigneArticle initiale supprimée, 1..N lignes recréées avec status=VALID,
       asset=<uuid>, wallet=<wallet_payeur>, sale_origin=NFC_MA
     → send_sale_to_laboutik.delay() pour chaque ligne
     → emails confirmation admin + utilisateur (Celery)
```

### 5.4 Lecteur NFC navigateur (Web NFC API)

C'est la partie peu documentée. Elle vit **uniquement** dans `generator.html`
(lignes 127-241) et utilise la **Web NFC API** native du navigateur.

#### Compatibilité

| Plateforme | Support |
|---|---|
| Android + Chrome | ✅ |
| Android + Opera (Opéra) | ✅ |
| Android + Firefox | ❌ |
| iOS (toutes apps) | ❌ — Apple n'expose pas Web NFC |
| Desktop (Chrome, Edge, Firefox, Safari) | ❌ |
| HTTPS | obligatoire (sauf `localhost`) |

Détection : `if (!('NDEFReader' in window)) { btn.disabled = true; … }`.
Si non supporté, le bouton bascule sur le texte "NFC : fonctionne sur Android avec Chrome ou Opéra uniquement.".

#### Flow technique côté JS (`generator.html`)

```javascript
// 1. Création du lecteur natif (NDEF = NFC Data Exchange Format)
const ndef = new NDEFReader();

// 2. Listener AVANT scan() — { once: true } : on ne lit qu'une carte
ndef.addEventListener('reading', async (event) => {
  // event.serialNumber → UID NFC sous forme "62:fe:16:01" (4 octets, hex avec :)
  // event.message.records → contenu NDEF si la carte en porte (texte, URL…)
  const payload = {
    tagSerial: event.serialNumber,                       // requis
    records: [...],                                      // info, non utilisée par le validator
    ligne_article_uuid_hex: '{{ ligne_article_uuid_hex }}'
  };
  fetch('{% url "qrcodescanpay-process-with-nfc" %}', {method:'POST', …});
}, { once: true });

// 3. Démarre la lecture (déclenche la prompt permission Android)
await ndef.scan();
```

Pendant l'attente : un overlay SweetAlert2 ("attente de lecteur de carte TiBillet")
bloque l'UI. Le résultat (succès ou erreur DRF) est affiché dans une autre SweetAlert2
puis redirige vers le générateur.

#### Validation serveur — `BaseBillet/validators.py:1033`

`QrCodeScanPayNfcValidator(serializers.Serializer)` reçoit `{tagSerial, ligne_article_uuid_hex}` :

1. **`_normalize_tag(value)`** :
   - lowercase, retire `:` et `-`
   - exige exactement **8 caractères hex** (4 octets)
   - renvoie en uppercase
   - lève `ValidationError(_("le format du tag NFC n'est pas bon"))` sinon
2. **`validate_tagSerial`** :
   - appelle Fedow distant : `FedowAPI().NFCcard.card_tag_id_retrieve(tag_id)`
   - rejette si carte inexistante
   - rejette si `is_wallet_ephemere=True` (carte non liée à un user — message
     "Merci de demander à la personne propriétaire de la lier en flashant le qrcode au dos de la carte")
   - charge `Wallet.objects.get(uuid=card_serialized['wallet_uuid'])` (V1 wallet, pas fedow_core)
3. **`validate_ligne_article_uuid_hex`** :
   - exige `LigneArticle(status=CREATED, payment_method=QRCODE_MA)`
4. **`validate(attrs)`** :
   - vérifie le solde via Fedow distant (`get_total_fiducial_and_all_federated_token`)
   - rejette `Solde insuffisant` si nécessaire

Si tout passe, `process_with_nfc` (vue) :

- Stocke les méta NFC (`tag_id`, `read_at`, `reader=admin email`, `user=payeur email`)
- Appelle `FedowAPI().transaction.to_place_from_qrcode(…)` qui peut renvoyer **plusieurs transactions** (cas TLF + FED → 2 splits, donc 2 `LigneArticle` créées avec `qty` proportionnel)
- Pour chaque transaction : crée une nouvelle `LigneArticle(status=VALID, asset=<uuid>, wallet=<wallet>, sale_origin=NFC_MA)` avec `payment_method=STRIPE_FED` ou `LOCAL_EURO` selon `asset.category`
- `send_sale_to_laboutik.delay(ligne.uuid)` pour chaque ligne (Celery → laboutik distant V1)
- Emails admin + user via Celery
- Retourne JSON `{status, user_email, amount_paid, balance}` consommé par SweetAlert2

#### Pièges et limites

- **Web NFC vs RFID POS** : c'est le **même `tag_id` 4 octets** que côté POS (`CarteCashless.tag_id`).
  Le validator normalise tout en hex 8 chars uppercase. Compatible avec `CarteCashless.objects.get(tag_id=…)`.
- **Carte anonyme refusée** : le flow exige une carte **liée à un user** (test `is_wallet_ephemere`).
  Pour lier la carte : flasher le QR au dos (`/qr/<uuid>/`) — ancien flow QrcodeCashless V1.
- **HTTPS obligatoire** : Web NFC ne fonctionne que sur origines sécurisées. En dev local, OK sur `https://lespass.tibillet.localhost/` (cert mkcert).
- **Permission utilisateur** : le 1er `ndef.scan()` déclenche la prompt système Android.
  Si l'utilisateur refuse, l'erreur est attrapée et affichée en SweetAlert2.
- **`{ once: true }`** : un seul listener par session. Si le receveur veut lire une 2e carte,
  il doit revenir au générateur (la SweetAlert2 de succès propose explicitement le retour).
- **`event.message.records`** est lu mais non exploité par le validator — utile uniquement
  si on voulait valider que la carte porte un NDEF spécifique TiBillet (pas le cas aujourd'hui).
- **Dette V1/V2** : `process_with_nfc` utilise `fedow_connect.FedowAPI` (HTTP vers serveur Fedow distant).
  Une migration vers `fedow_core.services.TransactionService` éliminera l'aller-retour HTTP
  et fera passer ce flow par les mêmes services que LaBoutik POS.

---

## 6. Données de test

```bash
# Cartes par défaut créées par create_test_pos_data (settings DEMO_TAGID_*)
DEMO_TAGID_CM       = "A49E8E2A"   # carte primaire (manager, tous les PV, edit_mode=True)
DEMO_TAGID_CLIENT1  = "52BE6543"   # client 1 — pré-rechargée pour cascade NFC
DEMO_TAGID_CLIENT2  = "33BC1DAA"   # client 2
DEMO_TAGID_CLIENT3  = "D74B1B5D"   # client 3 « jetable » — reset à chaque run en DEBUG

# Créer une carte avec un tag_id arbitraire (lu sur le lecteur RFID)
docker exec lespass_django poetry run python manage.py create_test_carte 741ECC2A
docker exec lespass_django poetry run python manage.py create_test_carte 741ECC2A AABB1122 DEADBEEF
```

`reset_carte(tag_id)` (`laboutik/utils/test_helpers.py`) supprime `user` et
`wallet_ephemere` de la carte en mode `DEBUG` pour rejouer un test propre.

---

## 7. Pièges spécifiques carte NFC

À lire avant tout test ou nouvelle vue qui touche `CarteCashless` (extraits de `tests/PIEGES.md`) :

- **9.30** — `CarteCashless` est en `SHARED_APPS` : pas de `FastTenantTestCase`,
  utiliser `schema_context('lespass')` + `APIClient`.
- **9.31** — `tag_id` et `number` font **max 8 caractères**.
- **9.32** — `create_test_pos_data` prend le 1er tenant — forcer `--schema=lespass`.
- **9.33** — Le composant `<c-read-nfc>` soumet `#addition-form` (pas les hidden fields du partial).
- **9.94** — Carte anonyme + recharge seule : court-circuite le formulaire email.

---

## 8. Coexistence V1 / V2 (pendant la migration)

| Mode | Détection | Backend solde | État carte |
|---|---|---|---|
| **V1** (anciens tenants) | `Configuration.server_cashless` renseigné | HTTP vers serveur Fedow distant | `carte.user` posé, `wallet_ephemere` non utilisé |
| **V2** (nouveaux tenants) | `module_caisse=True` + `module_monnaie_locale=True` | DB directe via `fedow_core.services` | `carte.user` + `carte.wallet_ephemere` actifs |

Les deux flux partagent **`CarteCashless.user`**, mais **pas** les soldes :
les anciens tokens sont sur le serveur Fedow distant, les nouveaux dans `fedow_core.Token`.
La fusion V1 → V2 n'est pas faite côté code — un tenant est sur l'un OU l'autre.

---

## 9. Pour aller plus loin

- `fedow_core/models.py` — Asset, Token, Transaction, Federation
- `fedow_core/services.py` — `AssetService`, `WalletService`, `TransactionService`
- `AuthBillet/models.py` — `Wallet`, `TibilletUser`
- `laboutik/README.md` — flux POS détaillé (étapes 1-9 du paiement adhésion, etc.)
- `BaseBillet/views.py` (`MyAccount`, `QrCodeScanPay`) — page solde + flow QR/NFC navigateur
- `BaseBillet/validators.py` (`QrCodeScanPayNfcValidator`) — validation NFC navigateur
- `BaseBillet/templates/reunion/views/qrcode_scan_pay/` — templates QR/NFC (generator, scanner, validation)
- [Web NFC API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_NFC_API)
- `tests/PIEGES.md` sections 9.30–9.35, 9.94 — pièges NFC
- `MEMORY.md` (auto-memory) — décisions fusion Lespass + LaBoutik + Fedow