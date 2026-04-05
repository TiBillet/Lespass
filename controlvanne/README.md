# Controlvanne — Tireuse a biere connectee

Module Django integre dans le mono-repo Lespass. Transforme une tireuse a biere en point de vente cashless connecte : badge NFC, debit en temps reel, facturation via fedow_core, interface kiosk sur ecran, administration Unfold.

Projet open source — licence AGPLv3 — [Cooperative Code Commun](https://codecommun.coop) / [TiBillet](https://tibillet.org).

---

## Architecture dans Lespass

`controlvanne` est une **TENANT_APP**. Chaque lieu (tenant) a ses propres tireuses, futs, historiques et sessions.

Le module reutilise les modeles existants de Lespass :

| Concept | Modele Lespass | Ancien modele (supprime) |
|---------|---------------|--------------------------|
| Carte NFC | `QrcodeCashless.CarteCashless` | `controlvanne.Card` |
| Fut de boisson | `BaseBillet.Product` (categorie `FUT`) | `controlvanne.Fut` |
| Solde client | `fedow_core.Token` (wallet) | `Card.balance` |
| Point de vente | `laboutik.PointDeVente` (type `TIREUSE`) | — |
| Stock fut | `inventaire.Stock` + `MouvementStock` | `Fut.quantite_stock` |
| Transaction | `fedow_core.Transaction` + `BaseBillet.LigneArticle` | debit `Card.balance` |

### Modeles propres a controlvanne

| Modele | Role |
|--------|------|
| `Configuration` | Singleton django-solo, config du module tireuse |
| `Debimetre` | Modele de capteur de debit + facteur de calibration |
| `CarteMaintenance` | Carte NFC dediee au rincage (OneToOne `CarteCashless`) |
| `TireuseBec` | Une tireuse physique (fut actif, debimetre, POS, pairing Pi) |
| `RfidSession` | Session de service (pose a depose de la carte NFC) |
| `TireuseAPIKey` | Cle API dediee aux Raspberry Pi des tireuses |
| 4 proxy `RfidSession` | `SessionCalibration`, `HistoriqueMaintenance`, `HistoriqueTireuse`, `HistoriqueCarte` |

---

## Fichiers du module

```
controlvanne/
  models.py           Modeles (voir tableau ci-dessus)
  viewsets.py          TireuseViewSet (ping, authorize, event) + AuthKioskView
  permissions.py       HasTireuseAccess (cle API tireuse OU session admin)
  serializers.py       PingSerializer, AuthorizeSerializer, EventSerializer
  billing.py           Facturation : wallet check, Transaction, LigneArticle, Stock
  urls.py              Router DRF + path auth-kiosk
  consumers.py         PanelConsumer WebSocket (Django Channels)
  routing.py           Routes WebSocket (ws/rfid/<slug>/)
  signals.py           pre_save (init reservoir) + post_save (push WS)
  admin.py             Admin Unfold (staff_admin_site)
  calibration_views.py Wizard HTMX de calibration debitmetre
  ws_payloads.py       TypedDict du payload WebSocket

  templates/
    base.html                       Base kiosk (Bootstrap local, nom tenant)
    controlvanne/panel_bootstrap.html  Kiosk : jauges SVG, grille prix, WS
    calibration/page.html           Calibration (herite admin Unfold)
    calibration/partial_*.html      Fragments HTMX calibration
    admin/date_range_filter.html    Filtre plage de dates admin

  static/controlvanne/
    css/bootstrap.min.css           Bootstrap 5.3 (local, Pi hors-ligne)
    js/bootstrap.bundle.min.js      Bootstrap 5.3 JS
    js/panel_kiosk.js               JS du kiosk (externalise)

  Pi/                               Code embarque Raspberry Pi (chantier separe)
```

---

## API du Raspberry Pi

Tous les endpoints sont proteges par `HasTireuseAccess` : cle API `TireuseAPIKey` dans le header `Authorization: Api-Key <key>`, ou session admin tenant.

### Endpoints

| Methode | URL | Description |
|---------|-----|-------------|
| POST | `/controlvanne/api/tireuse/ping/` | Test de connectivite + config tireuse |
| POST | `/controlvanne/api/tireuse/authorize/` | Badge NFC → verification solde → autorisation |
| POST | `/controlvanne/api/tireuse/event/` | Evenement temps reel (pour_start, pour_update, pour_end, card_removed) |
| POST | `/controlvanne/auth-kiosk/` | Token API → cookie session Django (pour Chromium kiosk) |

### Flow de service (tirage de biere)

```
1. Pi: POST /authorize { tireuse_uuid, uid }
   Django: CarteCashless → wallet → WalletService.obtenir_solde()
           → calcule volume_max = solde / prix_litre
   Reponse: { authorized, allowed_ml, solde_centimes }

2. Pi: ouvre la vanne, le client se sert

3. Pi: POST /event { tireuse_uuid, uid, event_type: "pour_update", volume_ml }
   Django: met a jour RfidSession.volume_delta_ml (pas de facturation)

4. Pi: POST /event { tireuse_uuid, uid, event_type: "pour_end", volume_ml }
   Django: TransactionService.creer_vente() → debit wallet client
           LigneArticle + MouvementStock
   Reponse: { montant_centimes, transaction_id }
```

### Appairage du Pi

Le Raspberry Pi s'appaire via le systeme `discovery` existant :

1. L'admin cree un `PairingDevice` dans Unfold → PIN 6 chiffres genere
2. L'admin cree une `TireuseBec` et la lie au `PairingDevice`
3. Le Pi envoie le PIN via `POST /api/discovery/claim/`
4. Discovery detecte la tireuse liee → cree une `TireuseAPIKey` (pas `LaBoutikAPIKey`)
5. Reponse : `{ server_url, api_key, tireuse_uuid, device_name }`
6. Le Pi stocke le token et l'UUID dans son `.env`

---

## Tuto : brancher une tireuse pas a pas

### Prerequis

- Le module tireuse est active sur le tenant (Dashboard → carte "Tireuse" → switch ON)
- Un asset TLF (monnaie locale) est actif sur le tenant
- Le Raspberry Pi est pret (voir section Pi ci-dessous)

### Etape 1 : creer un debitmetre

**Admin → Tireuses → Debitmetres → Ajouter**

| Champ | Valeur |
|-------|--------|
| Model | `YF-S201` (ou le modele de votre capteur) |
| Facteur de calibration | `6.5` (defaut YF-S201, affiner avec la calibration) |

### Etape 2 : creer un produit fut

**Admin → Tireuses → Keg products → Ajouter**

Ou bien : **Admin → Billetterie → Produits → Ajouter** avec categorie = "Keg (connected tap)"

| Champ | Valeur |
|-------|--------|
| Nom | `Blonde Pression` (nom affiche sur le kiosk) |
| Categorie | `Keg (connected tap)` (FUT) |
| Description longue | Brasseur, type, degre — affiches dans l'admin |

Puis ajouter un **Price** sur ce produit :

| Champ | Valeur |
|-------|--------|
| Nom | `Litre` |
| Prix | `5.00` (prix au litre en EUR) |
| Vente au poids/volume | **cocher** (obligatoire pour la tireuse) |

### Etape 3 : creer l'appareil d'appairage

**Admin → Discovery → Pairing devices → Ajouter**

| Champ | Valeur |
|-------|--------|
| Nom | `Pi Tireuse 1` |
| Tenant | votre lieu |

Un PIN 6 chiffres est genere automatiquement. Notez-le.

### Etape 4 : creer la tireuse

**Admin → Tireuses → Taps → Ajouter**

| Champ | Valeur |
|-------|--------|
| Nom tireuse | `Biere` (affiche sur le kiosk) |
| Fut actif | `Blonde Pression` (le produit FUT cree a l'etape 2) |
| Debitmetre | `YF-S201` (cree a l'etape 1) |
| Pairing device | `Pi Tireuse 1` (cree a l'etape 3) |
| Seuil minimum (ml) | `500` (reserve de securite) |
| Appliquer reserve | cocher |
| En service | cocher |

Le Point de vente (`PointDeVente`) peut etre cree automatiquement ou manuellement.

### Etape 5 : appairer le Pi

Sur le Raspberry Pi, lancer le script d'appairage avec le PIN note a l'etape 3 :

```bash
# Le Pi envoie le PIN au serveur
curl -X POST https://votre-domaine.tld/api/discovery/claim/ \
  -H "Content-Type: application/json" \
  -d '{"pin_code": "123456"}'
```

Reponse :
```json
{
  "server_url": "https://lespass.votre-domaine.tld",
  "api_key": "xxxxxxx.yyyyyyy",
  "tireuse_uuid": "abc123-...",
  "device_name": "Pi Tireuse 1"
}
```

Le Pi stocke `api_key` et `tireuse_uuid` dans son `.env`.

### Etape 6 : creer des cartes de maintenance (optionnel)

**Admin → Tireuses → Cartes maintenance → Ajouter**

Selectionnez une `CarteCashless` existante. Quand cette carte est badgee sur la tireuse, la vanne s'ouvre sans facturation (mode rincage).

### Etape 7 : calibrer le debitmetre

**Admin → Tireuses → Calibration sessions**

Ou directement : `/controlvanne/calibration/<uuid-tireuse>/`

1. Desactivez la tireuse (Admin → Taps → decocher "En service")
2. Badgez une carte maintenance → la vanne s'ouvre
3. Versez dans un verre gradue (~50 cl)
4. Retirez la carte
5. Sur la page calibration, saisissez le volume reel lu sur le verre
6. Repetez 2-3 fois
7. Cliquez "Appliquer le facteur"

### Etape 8 : c'est pret

Reactivez la tireuse (En service = cocher). Les clients peuvent badger leur carte NFC :
- Solde suffisant → vanne ouverte, biere coule, volume affiche en temps reel sur le kiosk
- Solde insuffisant → refus affiche
- Carte maintenance → mode rincage (pas de facturation)

Les ventes apparaissent dans les historiques admin et dans la cloture de caisse.

---

## Carte maintenance vs carte client

| | Carte client | Carte maintenance |
|---|---|---|
| Badger | Verifie le solde wallet | Ouvre la vanne sans facturation |
| Facturation | `TransactionService.creer_vente()` au pour_end | Aucune |
| Volume autorise | `solde / prix_litre` | Tout le reservoir |
| Admin | `CarteCashless` standard | `CarteMaintenance` (OneToOne `CarteCashless`) |

---

## Kiosk (ecran du Pi)

L'ecran du Pi affiche le template `panel_bootstrap.html` :
- Jauge SVG du fut (niveau en %)
- Grille de prix (25cl, 33cl, 50cl)
- Etat vanne (ouverte/fermee)
- Volume servi en temps reel
- Solde de la carte
- Popup "Bonne degustation" a la fin du service

Le kiosk se connecte via WebSocket (`ws/rfid/<uuid>/`) et recoit les mises a jour en push.

Bootstrap 5.3 est charge depuis les statics locaux (le Pi peut etre hors-ligne).

Le JS est dans `controlvanne/static/controlvanne/js/panel_kiosk.js`.

### Auth kiosk

Le Pi obtient un cookie session Django via `POST /controlvanne/auth-kiosk/` (cle API dans le header). Chromium est lance avec ce cookie.

---

## Materiel requis (Pi)

| Composant | Detail |
|---|---|
| Raspberry Pi | Teste sur Pi 3B+ (tout modele avec GPIO) |
| Lecteur RFID | Module RC522 (SPI) |
| Debitmetre | Capteur a effet Hall (ex : YF-S201, FS300A) |
| Electrovanne | 12V ou 24V pilotee via relais |
| Relais | Isolation circuit de puissance |
| Ecran | HDMI ou tactile |

### Cablage GPIO (BCM, valeurs par defaut)

| Composant | Pin BCM | Role |
|---|:---:|---|
| Electrovanne | GPIO 18 | Commande du relais |
| Debitmetre | GPIO 23 | Entree impulsions |
| RFID SDA | GPIO 8 (CE0) | SPI Chip Select |
| RFID SCK | GPIO 11 | SPI Clock |
| RFID MOSI | GPIO 10 | SPI MOSI |
| RFID MISO | GPIO 9 | SPI MISO |
| RFID RST | GPIO 25 | Reset RC522 |

---

## Tests

```bash
# Tests pytest DB-only (32 tests, ~4s)
docker exec lespass_django poetry run pytest \
  tests/pytest/test_controlvanne_api.py \
  tests/pytest/test_controlvanne_billing.py \
  tests/pytest/test_controlvanne_models.py -v

# Tests E2E Playwright (3 tests, serveur requis)
docker exec lespass_django poetry run pytest tests/e2e/test_controlvanne_admin.py -v -s
```

Couverture :
- `test_controlvanne_api.py` (13 tests) : TireuseAPIKey, HasTireuseAccess, ping, authorize, event, auth-kiosk
- `test_controlvanne_billing.py` (7 tests) : calcul volume, facturation, Transaction, LigneArticle
- `test_controlvanne_models.py` (12 tests) : proprietes modeles, maintenance, events complementaires
- `test_controlvanne_admin.py` (3 tests E2E) : sidebar, liste tireuses, historique
