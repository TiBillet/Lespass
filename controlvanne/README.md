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

## Installation du Raspberry Pi

### Prerequis

- Un Raspberry Pi (teste sur 3B+, tout modele avec GPIO)
- Raspberry Pi OS Lite (Legacy, 32-bit) flashe avec [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- SSH active, utilisateur **`sysop`**, cle publique injectee via Imager
- Le materiel connecte (lecteur RFID, debitmetre, electrovanne, ecran) — voir section cablage ci-dessous
- Une tireuse deja creee dans l'admin Django (etapes 1-4 du tuto ci-dessus)

### Lancer l'installation

Connectez-vous en SSH au Pi puis executez :

```bash
wget https://raw.githubusercontent.com/TiBillet/Lespass/integration_laboutik/controlvanne/Pi/install.sh \
  && chmod +x install.sh && ./install.sh
```

Le script est interactif. Il demande :

1. **URL publique TiBillet** — ex: `https://tibillet.mondomaine.tld` (le domaine racine, pas le sous-domaine tenant)
2. **PIN 6 chiffres** — affiche dans Admin → Discovery → Pairing devices (cree a l'etape 3 du tuto)
3. **Type de lecteur RFID** — RC522 (SPI, defaut), VMA405 (serie USB), ou ACR122U (USB PC/SC)

Le script appelle automatiquement `/api/discovery/claim/` avec le PIN et recoit :
- `server_url` (URL du tenant)
- `api_key` (TireuseAPIKey unique)
- `tireuse_uuid` (UUID de la tireuse)

### Ce que le script fait automatiquement

- Mise a jour systeme + installation des dependances (pigpio, chromium, python3-venv)
- Clonage du depot + creation de l'environnement virtuel Python
- Generation du fichier `.env` avec les valeurs recues de discovery
- Configuration du kiosk Chromium (Openbox + plein ecran sur `{server_url}/controlvanne/kiosk/{tireuse_uuid}/`)
- Activation des services systemd :
  - `pigpiod` — daemon GPIO
  - `tibeer.service` — boucle principale (RFID + vanne + debitmetre + API)
  - `kiosk.service` — Chromium plein ecran

### Le fichier .env genere

```env
SERVER_URL=https://lespass.mondomaine.tld
API_KEY=xxxxxxx.yyyyyyy
TIREUSE_UUID=abc123-def456-...
RFID_TYPE=RC522
GPIO_VANNE=18
GPIO_FLOW_SENSOR=23
FLOW_CALIBRATION_FACTOR=6.5
SYSTEMD_NOTIFY=True
```

### Commandes utiles sur le Pi

```bash
# Voir les logs en temps reel
sudo journalctl -u tibeer -f

# Redemarrer les services
sudo systemctl restart tibeer.service kiosk.service

# Arreter les services
sudo systemctl stop tibeer.service kiosk.service

# Editer la configuration
nano /home/sysop/tibeer/.env

# Re-appairer (nouveau PIN)
cd /home/sysop/tibeer && python3 -c "
import requests, json
url = input('URL publique TiBillet: ')
pin = input('PIN 6 chiffres: ')
r = requests.post(f'{url}/api/discovery/claim/', json={'pin_code': pin})
print(json.dumps(r.json(), indent=2))
"
```

### Demarrage automatique

Au demarrage du Pi, la sequence est :
1. `pigpiod` demarre (GPIO)
2. `tibeer.service` demarre :
   - Ping serveur (verif connectivite + calibration)
   - Auth kiosk (cookie session)
   - Lance Chromium kiosk en arriere-plan
   - Boucle controleur (RFID + vanne + API)
3. `kiosk.service` demarre (X11 + Chromium plein ecran)

Si le serveur est injoignable au demarrage, le Pi continue — le kiosk affichera une page d'erreur et le controleur retentera les appels API.

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

## Documentation technique — comment ca fonctionne

### Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SERVEUR DJANGO (Lespass)                        │
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                │
│  │  TireuseViewSet  │   │  billing.py  │   │  fedow_core  │                │
│  │  (DRF API)    │──▶│  facturation │──▶│  WalletService │                │
│  │  ping         │   │              │   │  TransactionSvc│                │
│  │  authorize    │   └──────────────┘   └──────────────┘                │
│  │  event        │          │                   │                       │
│  └──────┬───────┘          │                   ▼                       │
│         │            ┌─────▼──────┐    ┌──────────────┐                │
│         │            │LigneArticle│    │    Token      │                │
│         │            │(comptable) │    │  (solde wallet)│                │
│         │            └────────────┘    └──────────────┘                │
│         │                                                               │
│  ┌──────▼───────┐   ┌──────────────┐                                   │
│  │   signals.py  │──▶│  WebSocket   │──────────────────────┐           │
│  │  (post_save)  │   │  Channels    │                      │           │
│  └──────────────┘   └──────────────┘                      │           │
│         │                                                  │           │
│  ┌──────▼───────┐                                         │           │
│  │  kiosk_view   │ GET /kiosk/<uuid>/                      │           │
│  │  (template)   │────────────────────────────┐           │           │
│  └──────────────┘                             │           │           │
└───────────────────────────────────────────────┼───────────┼───────────┘
                                                │           │
                          HTTPS / API           │    WSS    │
                                                │           │
┌───────────────────────────────────────────────┼───────────┼───────────┐
│                      RASPBERRY PI             │           │           │
│                                               │           │           │
│  ┌──────────────┐                    ┌────────▼───────────▼──────┐   │
│  │  main.py      │                    │      Chromium kiosk       │   │
│  │  (orchestrateur)                   │  panel_bootstrap.html     │   │
│  └──────┬───────┘                    │  ← WebSocket push         │   │
│         │                            │  jauges SVG + prix + solde│   │
│  ┌──────▼───────┐                    └──────────────────────────┘   │
│  │ TibeerController                                                  │
│  │ (boucle 100ms)│                                                   │
│  │               │                                                   │
│  │  ┌─────────┐  │  ┌─────────────┐  ┌──────────────┐              │
│  │  │  RFID   │──┼──│ BackendClient│  │   Valve      │              │
│  │  │ Reader  │  │  │ (HTTP POST) │  │  (GPIO 18)   │              │
│  │  └─────────┘  │  └─────────────┘  └──────────────┘              │
│  │  ┌─────────┐  │                                                   │
│  │  │FlowMeter│  │                                                   │
│  │  │(GPIO 23)│  │                                                   │
│  │  └─────────┘  │                                                   │
│  └──────────────┘                                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### Algorithme principal (boucle du Pi)

```
DEMARRAGE
│
├── Init hardware (RFID, vanne, debitmetre)
├── Ping serveur → recupere config tireuse (nom, prix, calibration)
├── Auth kiosk → obtient cookie session
├── Lance Chromium kiosk (plein ecran, pointe sur le serveur Django)
│
▼
BOUCLE (toutes les 100ms)
│
├── Lire RFID → uid (ou None)
├── Mettre a jour debitmetre (compteur impulsions)
│
├── SI nouvelle carte detectee :
│   │
│   ├── POST /authorize { tireuse_uuid, uid }
│   │   Django repond :
│   │   ├── authorized: true → session_id, allowed_ml, solde_centimes
│   │   └── authorized: false → message (solde insuffisant, carte inconnue...)
│   │
│   ├── SI autorise :
│   │   ├── Ouvrir la vanne (GPIO)
│   │   ├── Stocker allowed_ml (volume max autorise)
│   │   ├── Envoyer event "pour_start"
│   │   └── → passer en mode SERVICE
│   │
│   └── SI refuse :
│       └── Log + rien (le kiosk affiche le refus via WebSocket)
│
├── SI en mode SERVICE (meme carte, toutes les 1s) :
│   │
│   ├── Calculer volume_servi = debitmetre.volume - volume_au_debut_session
│   │
│   ├── SI volume_servi >= allowed_ml :
│   │   ├── FERMER LA VANNE (volume max atteint)
│   │   ├── Envoyer event "pour_end" { volume_ml }
│   │   │   Django repond : montant_centimes, transaction_id
│   │   │   (Transaction creee, wallet debite, LigneArticle creee)
│   │   └── → sortir du mode SERVICE
│   │
│   └── SINON :
│       └── Envoyer event "pour_update" { volume_ml }
│           (Django met a jour la session, pousse WebSocket → kiosk affiche volume)
│
├── SI carte retiree (absente depuis > 1 seconde) :
│   │
│   ├── SI en mode SERVICE :
│   │   ├── FERMER LA VANNE
│   │   ├── Envoyer event "pour_end" { volume_final }
│   │   │   Django facture le volume reel servi
│   │   └── → sortir du mode SERVICE
│   │
│   ├── Envoyer event "card_removed"
│   │   (Django pousse popup "Bonne degustation" sur le kiosk via WebSocket)
│   │
│   └── → retour en ATTENTE
│
└── REPETER
```

### Circuit de facturation (cote Django)

```
authorize :
  CarteCashless (tag_id=uid)
  → Wallet (via carte.user.wallet ou carte.wallet_ephemere)
  → Asset TLF du tenant (monnaie locale)
  → WalletService.obtenir_solde(wallet, asset) → solde en centimes
  → allowed_ml = (solde / prix_litre) * 1000
  → min(allowed_ml, reservoir_disponible)
  → Creer RfidSession(authorized=True, allowed_ml_session)

pour_end :
  → montant_centimes = volume_ml * prix_litre / 1000 * 100
  → TransactionService.creer_vente(wallet_client → wallet_lieu, montant)
     (atomic : debit Token client + credit Token lieu + insert Transaction)
  → ProductSold + PriceSold (snapshots) + LigneArticle (comptable)
  → StockService.decrementer_pour_vente() si Stock existe
  → Session.ligne_article = ligne creee
  → La vente apparait dans la cloture de caisse comme n'importe quelle vente NFC
```

### Flux WebSocket (temps reel)

```
Django                          Kiosk (Chromium)
  │                                  │
  │  signal post_save TireuseBec     │
  ├─────────────────────────────────▶│  Mise a jour jauge fut
  │                                  │
  │  authorize → session creee       │
  ├─────────────────────────────────▶│  Badge vert + solde
  │                                  │
  │  pour_update (chaque seconde)    │
  ├─────────────────────────────────▶│  Volume servi en temps reel
  │                                  │
  │  pour_end → session fermee       │
  ├─────────────────────────────────▶│  Popup "Bonne degustation"
  │                                  │
  │  card_removed                    │
  ├─────────────────────────────────▶│  Retour ecran d'attente
  │                                  │
```

Le kiosk se connecte via `ws://<serveur>/ws/rfid/<uuid-tireuse>/`.
Le consumer `PanelConsumer` (Django Channels) dispatch les messages vers le groupe de la tireuse.
Les signaux Django (`signals.py`) poussent les mises a jour apres chaque modification de TireuseBec.

### Appairage (premiere installation)

```
Admin Unfold                    install.sh (Pi)
  │                                  │
  │  1. Creer PairingDevice          │
  │     → PIN 6 chiffres genere      │
  │                                  │
  │  2. Creer TireuseBec             │
  │     → lier au PairingDevice      │
  │                                  │
  │                                  │  3. Saisir URL publique + PIN
  │                                  │
  │                     POST /api/discovery/claim/ { pin_code }
  │◀─────────────────────────────────┤
  │                                  │
  │  Discovery detecte la tireuse    │
  │  liee au PairingDevice           │
  │  → Cree TireuseAPIKey            │
  │  → Retourne server_url,          │
  │    api_key, tireuse_uuid         │
  │─────────────────────────────────▶│
  │                                  │
  │                                  │  4. Genere .env
  │                                  │  5. Configure services systemd
  │                                  │  6. Redemarre
  │                                  │
  │  PIN consomme (usage unique)     │
```

### Principes techniques detailles

#### Lecture RFID — `hardware/rfid_reader.py`

Le lecteur NFC lit l'identifiant unique (UID, 4 octets) de la carte sans contact posee sur la tireuse. Trois types de lecteurs sont supportes, tous derriere la meme interface `read_uid() → str | None` :

- **RC522** (SPI) — le plus courant. Communique via le bus SPI du Pi (`/dev/spidev0.0`). La lecture est un cycle requete (`MFRC522_Request`) + anticollision (`MFRC522_Anticoll`). Le 5e octet (checksum XOR) est retire, on ne garde que les 4 octets de l'UID convertis en hex majuscule (ex: `"741ECC2A"`). Bibliotheque : `mfrc522-python`.

- **VMA405** (serie USB) — lecteur autonome connecte en USB. Envoie l'UID en texte sur le port serie (`/dev/ttyUSB0`, 9600 bauds). Lecture via `pyserial`, non bloquante.

- **ACR122U** (USB PC/SC) — lecteur de bureau. Utilise le protocole PC/SC via `pyscard`. Commande APDU standard `FF CA 00 00 00` (GET UID ISO 14443). Necessite le daemon `pcscd` actif.

La boucle principale appelle `read_uid()` toutes les 100ms. Si une carte est presente, la methode retourne son UID hex. Sinon, `None`. La detection de presence/absence se fait par comparaison avec l'UID precedent + un delai anti-rebond de 1 seconde (evite les fausses deconnexions dues aux micro-coupures de lecture).

#### Debitmetre — `hardware/flow_meter.py`

Le debitmetre est un capteur a effet Hall qui genere des impulsions electriques proportionnelles au debit de liquide. Chaque rotation de la turbine interne produit un signal carre sur le GPIO.

**Principe physique :**
```
1 litre = facteur_calibration × 60 impulsions
```
Exemple avec un YF-S201 (facteur 6.5) : 1 litre = 6.5 × 60 = 390 impulsions.

**Comptage des impulsions** : on utilise `pigpio` (pas `RPi.GPIO`) car il offre des callbacks par interruption materielle (`FALLING_EDGE`) avec une precision a la microseconde. Chaque front descendant incremente un compteur atomique (`flow_count`).

**Calcul du debit** (methode `update()`, appelee toutes les ~100ms) :
```
frequence_hz = nombre_impulsions / delta_temps_secondes
debit_litres_par_minute = (frequence_hz / facteur_calibration) * 60
volume_ajoute_ml = (debit_litres_par_minute / 60) * delta_temps * 1000
```

**Calcul du volume total** (methode `volume_l()`) :
```
volume_litres = total_impulsions / (facteur_calibration * 60)
```

Le facteur de calibration peut etre mis a jour en temps reel par le serveur Django (recu dans la reponse `ping`). La page de calibration admin permet d'affiner ce facteur en comparant le volume mesure par Django avec le volume reel verse dans un verre gradue.

#### Electrovanne — `hardware/valve.py`

L'electrovanne est une vanne pilotee electriquement qui ouvre ou ferme le passage du liquide. Elle est commandee via un relais connecte a un GPIO du Pi.

**Controle** : un seul GPIO, deux etats :
- `write(pin, 1)` → relais active → vanne ouverte → le liquide coule
- `write(pin, 0)` → relais desactive → vanne fermee → le liquide s'arrete

**Securite** : la vanne est forcee fermee au demarrage (`close()` dans `__init__`). En cas de crash du programme, de perte de courant, ou de deconnexion, le relais retombe → vanne fermee. C'est un choix de securite delibere : en cas de defaillance, la biere ne coule pas.

Le controleur ouvre la vanne uniquement apres une autorisation reussie du serveur Django. Il la ferme dans 3 cas :
1. Le volume autorise (`allowed_ml`) est atteint
2. La carte est retiree (grace period de 1s ecoulee)
3. Une erreur survient (exception, serveur injoignable)

#### Gestion du wallet — `controlvanne/billing.py` + `fedow_core/services.py`

Le portefeuille (wallet) de chaque carte NFC est gere par le moteur `fedow_core` de Lespass. Chaque wallet contient des `Token` — des lignes de solde pour chaque type de monnaie (`Asset`).

**A l'authorize** (quand le client pose sa carte) :

1. **Trouver le wallet** : `CarteCashless` → `carte.user.wallet` (si utilisateur identifie) ou `carte.wallet_ephemere` (carte anonyme). Si aucun wallet n'existe, un wallet ephemere est cree automatiquement.

2. **Trouver l'asset TLF** : chaque tenant a un asset de type TLF (Token Local Fiduciaire, adosse a l'euro, 1 token = 1 centime). C'est la monnaie locale du lieu.

3. **Lire le solde** : `WalletService.obtenir_solde(wallet, asset_tlf)` retourne le solde en centimes (int). Pas de verrou a ce stade — c'est une lecture rapide.

4. **Calculer le volume autorise** : `solde_centimes / prix_centimes_par_litre * 1000` donne le nombre de ml que le client peut se servir. Ce volume est plafonne par le reservoir disponible de la tireuse.

**Au pour_end** (quand le service est termine) :

1. **Calculer le montant** : `volume_ml * prix_litre / 1000 * 100` → montant en centimes.

2. **Creer la transaction** : `TransactionService.creer_vente()` dans un bloc `transaction.atomic()`. Le Token du client est debite (`select_for_update()` pour eviter les race conditions), le Token du lieu est credite, et un enregistrement `Transaction` est insere.

3. **Creer la ligne comptable** : `LigneArticle` avec les snapshots produit/prix (`ProductSold`, `PriceSold`), le moyen de paiement (`LOCAL_EURO`), la carte, le wallet, le point de vente. Cette ligne est identique a celles creees par la caisse POS — elle apparait dans la cloture de caisse et les rapports de ventes.

4. **Decrementer le stock** : si le produit fut a un `Stock` inventaire, `StockService.decrementer_pour_vente()` retire le volume servi (en cl) du stock avec un `F()` expression atomique.

**Race condition** : si le solde change entre l'authorize et le pour_end (ex: le client utilise sa carte sur un autre terminal en meme temps), `WalletService.debiter()` leve `SoldeInsuffisant`. La biere est deja servie — le serveur log l'erreur mais ne bloque pas. C'est un risque accepte (la probabilite est faible et le montant est petit).

#### Authentification — `controlvanne/permissions.py`

Chaque Raspberry Pi a sa propre cle API (`TireuseAPIKey`), creee automatiquement lors de l'appairage via discovery. Cette cle est differente des cles `LaBoutikAPIKey` utilisees par les caisses — un Pi ne peut pas acceder aux endpoints de caisse, et inversement.

La permission `HasTireuseAccess` accepte deux chemins :
1. **Cle API** (header `Authorization: Api-Key xxx`) → le Raspberry Pi
2. **Session admin** (cookie `sessionid`) → un admin tenant connecte via navigateur (pour debug/tests)

Les cles sont tenant-isolees par `django-tenants` : une cle creee sur le tenant A n'existe pas dans le schema du tenant B.

#### WebSocket temps reel — `controlvanne/consumers.py` + `controlvanne/signals.py`

Le kiosk (Chromium sur le Pi) recoit les mises a jour en temps reel via WebSocket, sans polling.

**Cote serveur** : le signal `post_save` sur `TireuseBec` (dans `signals.py`) construit un payload JSON avec l'etat complet de la tireuse (nom, volume, prix, session en cours, solde) et le pousse vers le groupe WebSocket `rfid_state.<uuid>` via Django Channels (`channel_layer.group_send`).

**Cote kiosk** : le JS (`panel_kiosk.js`) ouvre une connexion WebSocket sur `ws://<serveur>/ws/rfid/<uuid>/`. A chaque message recu, il met a jour l'interface : jauge SVG du fut, volume servi, solde de la carte, etat de la vanne, popup de fin de service.

Le consumer `PanelConsumer` gere deux groupes :
- `rfid_state.<uuid>` — un kiosk dedie a une tireuse specifique
- `rfid_state.all` — le dashboard admin qui voit toutes les tireuses

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
