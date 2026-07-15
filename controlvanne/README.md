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
| `ConfigurationTireuse` | Singleton django-solo, config du module tireuse |
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
  viewsets.py          TireuseViewSet (ping, authorize, event) + AuthKioskView/KioskTokenView + KioskBridgeThrottle
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
    controlvanne/kiosk_list.html       Kiosk : toutes les tireuses (jauges, prix, WS)
    controlvanne/kiosk_detail.html     Kiosk : une tireuse (+ simulateur si DEMO=1)
    controlvanne/partial/kiosk_card.html  Carte tireuse (partagee list/detail)
    calibration/page.html           Calibration (herite admin Unfold)
    calibration/partial_*.html      Fragments HTMX calibration
    admin/date_range_filter.html    Filtre plage de dates admin

  static/controlvanne/
    css/bootstrap.min.css           Bootstrap 5.3 (local, Pi hors-ligne)
    js/bootstrap.bundle.min.js      Bootstrap 5.3 JS
    js/panel_kiosk.js               JS du kiosk (WS + reconnexion auto)
    js/simu_pi.js                   Simulateur Pi (panneau debug DEMO=1)

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

Le Raspberry Pi s'appaire par le systeme `discovery`, **exactement comme une caisse ou une
borne**. Les trois roles suivent le meme chemin ; seule la classe de la cle change.

**LA TIREUSE ET SON PI SONT DEUX CHOSES DIFFERENTES.** La tireuse est l'objet METIER : elle
porte le fut, le debitmetre, le prix, et tout l'historique des services. Le `Terminal` est le
MATERIEL : il est jetable. C'est le terminal qu'on appaire, pas la tireuse.

1. L'admin cree une `TireuseBec` dans Unfold.
2. Son signal `post_save` fabrique aussitot :
   - son **point de vente** (type TIREUSE) ;
   - son **`Terminal`** (role TI) — le Raspberry Pi qui la pilotera ;
   - le **code PIN a 6 chiffres** de ce terminal (un `PairingDevice`, dans le schema public).

   Le `PairingDevice` porte `cible_uuid` = l'identifiant du **Terminal** a remplir. Ce n'est
   **pas** une cle etrangere — `PairingDevice` vit dans le schema `public`, `Terminal` dans
   celui du lieu, et PostgreSQL ne saurait pas quelle table viser.
3. Le code PIN se lit **en ouvrant la tireuse** dans l'admin (pas dans la liste : il ne sert
   qu'au moment ou l'on installe le Pi).
4. **Le code PIN expire au bout d'une heure.** Passe ce delai : Admin → **Terminaux** →
   cocher → action « Generer un nouveau code PIN ».
5. Le Pi envoie le PIN via `POST /api/discovery/claim/` — **sur le domaine public**
   (`https://tibillet.org/...`), pas sur celui du lieu : l'appareil ne connait pas encore son
   lieu, c'est le serveur qui le lui apprend.
6. **Le claim ne cree pas le terminal — il le REMPLIT.** Dans le schema du lieu, il pose :
   - un **`TermUser`** — le compte de l'appareil ;
   - une **`TireuseAPIKey`** liee a ce compte (et non une `LaBoutikAPIKey` : les permissions de
     controlvanne s'appuient sur une classe de cle distincte) ;
   - puis `Terminal.term_user`, ce qui fait passer le terminal a l'etat « appaire ».
7. Le `PairingDevice` est alors **consomme** : son code PIN et sa cible sont vides.
8. Reponse : `{ server_url, api_key, tireuse_uuid, device_name }`
9. Le Pi stocke le token et l'UUID dans son `.env`.

**Le Pi crame ?** Admin → **Terminaux** → cocher → « **Generer un nouveau code PIN** ». L'ancien
appareil est coupe (compte **et** cle), le terminal repasse en attente avec un nouveau code, et
**la tireuse garde toute sa configuration et son historique**. On tape le code sur le Pi neuf.

**Revoquer une tireuse** : Admin → **Terminaux** → cocher → action « Revoquer le terminal ».
Elle coupe les **deux** acces — le compte (`is_active`) et la cle (`revoked`). Revoquer le
compte seul ne suffirait pas : la cle est stockee sur le Pi, il suffirait de reactiver le
compte pour qu'il se reconnecte.

---

## Tuto : brancher une tireuse pas a pas

### Prerequis

- Le module tireuse est active sur le tenant (Dashboard → carte "Connected taps" → switch ON)
- Un asset TLF (monnaie locale) est actif sur le tenant
- Le materiel est pret et cablé (Pi, lecteur RFID, electrovanne, debitmetre)

### Etape 1 : creer un debitmetre

**Admin → Tireuses → Debitmetres → Ajouter**

| Champ | Valeur |
|-------|--------|
| Model | `YF-S201` (ou le modele de votre capteur) |
| Facteur de calibration | `6.5` (defaut YF-S201, affiner avec la calibration) |

### Etape 2 : creer un produit fut

**Admin → Tireuses → Keg products → Ajouter**

(La categorie FUT n'est pas selectionnable depuis le formulaire produit generique :
passer obligatoirement par le proxy « Keg products ».)

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

### Etape 3 : creer la tireuse

**Admin → Tireuses → Taps → Ajouter**

| Champ | Valeur |
|-------|--------|
| Nom tireuse (Tap name) | `Biere` (affiche sur le kiosk) |
| Fut actif (Active keg) | `Blonde Pression` (le produit FUT cree a l'etape 2) |
| Debitmetre (Flow meter) | `YF-S201` (cree a l'etape 1) |
| En service | cocher |
| Reservoir illimite (Unlimited reservoir) | cocher (aucun suivi de volume) — ou decocher pour suivre le niveau du fut (`reservoir_ml`, rempli a l'activation) |

A la sauvegarde, un code PIN d'appairage et un `PointDeVente` de type TIREUSE sont crees automatiquement par signal.

### Etape 4 : installer le Pi

**Admin → Tireuses** — **ouvrir** la tireuse et noter son code PIN (il est dans la fiche, pas dans la liste : il ne sert qu'au moment ou l'on installe le Pi).

> ⚠️ **Le code PIN expire au bout d'une heure.** Si la colonne affiche « Code PIN expire »,
> le regenerer avant de lancer le script (action « Regenerer le code PIN »). Une fois la
> tireuse appairee, la colonne affiche « Appairee : \<nom du terminal\> ».

Puis sur le Raspberry Pi en SSH, lancer le script d'installation avec ce PIN :

```bash
wget https://raw.githubusercontent.com/TiBillet/Lespass/main-fedow-import/controlvanne/Pi/install_pi.sh \
  && chmod +x install_pi.sh && ./install_pi.sh
```

Le script demande l'URL publique TiBillet, le PIN et le type de lecteur RFID. Il appaire le Pi, configure les services systemd et redemarre. Une fois termine, l'ecran du Pi affiche le kiosk de la tireuse.

### Apres l'installation (optionnel)

#### Cartes de maintenance

**Admin → Tireuses → Cartes maintenance → Ajouter**

Selectionnez une `CarteCashless` existante. Quand cette carte est badgee sur la tireuse, la vanne s'ouvre sans facturation (mode rincage).

#### Calibrer le debitmetre

**Admin → Tireuses → Calibration sessions**

Ou directement : `/controlvanne/calibration/<uuid-tireuse>/`

1. Desactivez la tireuse (Admin → Taps → decocher "En service")
2. Badgez une carte maintenance → la vanne s'ouvre
3. Versez dans un verre gradue (~50 cl)
4. Retirez la carte
5. Sur la page calibration, saisissez le volume reel lu sur le verre
6. Repetez 2-3 fois
7. Cliquez « ✓ Calculer et appliquer le facteur »

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
| `reservoir_ml` decremente | Oui | **Non** |
| Admin | `CarteCashless` standard | `CarteMaintenance` (OneToOne `CarteCashless`) |

---

## Kiosk (ecran du Pi)

L'ecran du Pi affiche le template `kiosk_detail.html` (une tireuse) ou `kiosk_list.html` (toutes) :
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

Le Pi appelle `POST /controlvanne/auth-kiosk/` (cle API dans le header) et recoit un token a usage unique. Ce token est passe en parametre URL (`?kiosk_token=<token>`) au demarrage de Chromium. Django valide le token, ouvre une session, et redirige vers le kiosk authentifie.

**Protections de sécurité** :
- Throttle anti-brute-force : 10 requêtes/min par IP (classe `KioskBridgeThrottle`)
- Session 12h (`request.session.set_expiry`) — aligné avec `LaBoutikAuthBridgeView`
- `next_url` échappé avec `iri_to_uri` + `escape` pour parer le XSS reflectif
- Token UUID stocké en cache 5 min — nécessite un cache partagé (Redis) en multi-worker

---

## Installation du Raspberry Pi

### Prerequis

- Un Raspberry Pi (teste sur 3B+, tout modele avec GPIO)
- Le materiel connecte (lecteur RFID, debitmetre, electrovanne, ecran) — voir section cablage ci-dessous
- Une tireuse deja creee dans l'admin Django (etapes 1-4 du tuto ci-dessus)

### Flasher la carte SD avec Raspberry Pi Imager

Telecharger [Raspberry Pi Imager](https://www.raspberrypi.com/software/) puis :

1. **Choose Device** : votre modele de Pi (ex : Raspberry Pi 3)
2. **Choose OS** : `Raspberry Pi OS (other)` → **Raspberry Pi OS Lite (Legacy, 32-bit)**
   (pas de bureau — le kiosk Chromium est installe par le script)
3. **Choose Storage** : la carte SD
4. Cliquer **Suivant** → **Modifier les reglages** (la roue dentee) :
   - Nom d'utilisateur : **`sysop`** (obligatoire — les scripts et services systemd
     utilisent ce nom) + un mot de passe
   - Wi-Fi : SSID + mot de passe si pas de cable Ethernet
   - Onglet **Services** : activer **SSH**, de preference avec une cle publique
     (sinon par mot de passe)
5. Ecrire l'image, inserer la carte dans le Pi, brancher, attendre le demarrage
6. Trouver l'IP du Pi (box internet, ou `ping raspberrypi.local`) puis :
   `ssh sysop@<ip-du-pi>`

### Lancer l'installation

Connectez-vous en SSH au Pi puis executez :

```bash
wget https://raw.githubusercontent.com/TiBillet/Lespass/main-fedow-import/controlvanne/Pi/install_pi.sh \
  && chmod +x install_pi.sh && ./install_pi.sh
```

Le script est interactif. Il demande :

1. **URL publique TiBillet** — ex: `https://tibillet.mondomaine.tld` (le domaine racine, pas le sous-domaine tenant)
2. **PIN 6 chiffres** — visible dans Admin → Tireuses → Taps, colonne "PIN code"
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
# Adresse du TENANT (le lieu) — API + kiosk au quotidien
SERVER_URL=https://lespass.mondomaine.tld
# Adresse RACINE du serveur — uniquement pour (re)appairer (make claim)
CLAIM_SERVER_URL=https://mondomaine.tld
API_KEY=xxxxxxx.yyyyyyy
TIREUSE_UUID=abc123-def456-...
RFID_TYPE=RC522
GPIO_VANNE=18
GPIO_FLOW_SENSOR=23
FLOW_CALIBRATION_FACTOR=6.5
SYSTEMD_NOTIFY=True
GIT_REPO=https://github.com/TiBillet/Lespass.git
GIT_BRANCH=main-fedow-import
```

**Changer l'adresse du serveur ou du tenant** : editer ces deux lignes dans le
`.env` puis `sudo systemctl restart tibeer kiosk`. Le Makefile reprend aussi
ses valeurs par defaut (`CLAIM_SERVER_URL`, `GIT_REPO`, `GIT_BRANCH`,
`RFID_TYPE`) depuis ce fichier : un `make claim PIN=<code>` sans argument
`SERVER=` re-appaire sur la meme adresse.

### Commandes utiles sur le Pi

```bash
# Voir les logs en temps reel
sudo journalctl -u tibeer -f

# Redemarrer les services
sudo systemctl restart tibeer.service kiosk.service

# Arreter les services
sudo systemctl stop tibeer.service kiosk.service

# Editer la configuration
nano /home/sysop/tibeer/controlvanne/Pi/.env

# Re-appairer (nouveau PIN visible dans Admin → Tireuses → Taps)
# SERVER est optionnel : repris du .env (CLAIM_SERVER_URL) s'il existe
cd /home/sysop/tibeer/controlvanne/Pi
make claim PIN=<code> [SERVER=https://votre-domaine.tld]
```

### Demarrage automatique

Au demarrage du Pi, la sequence est :
1. `pigpiod` demarre (GPIO)
2. `tibeer.service` demarre :
   - Ping serveur (verif connectivite + calibration)
   - Auth kiosk (token usage unique → `?kiosk_token=` dans URL Chromium → cookie session pose par Django)
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
│  │  (orchestrateur)                   │  kiosk_detail.html        │   │
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
├── SI carte retiree (absente depuis > 3 secondes, CARD_GRACE_PERIOD_S) :
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
Admin Unfold                    make claim (Pi, via SSH)
  │                                  │
  │  1. Creer TireuseBec             │
  │     → PairingDevice auto-cree    │
  │     → PIN 6 chiffres genere      │
  │                                  │
  │                                  │  2. make claim PIN=<code> SERVER=<url>
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
  │                                  │  3. Genere .env
  │                                  │  4. Configure services systemd
  │                                  │  5. Redemarre tibeer
  │                                  │
  │  PIN consomme (usage unique)     │
```

### Principes techniques detailles

#### Lecture RFID — `hardware/rfid_reader.py`

Le lecteur NFC lit l'identifiant unique (UID, 4 octets) de la carte sans contact posee sur la tireuse. Trois types de lecteurs sont supportes, tous derriere la meme interface `read_uid() → str | None` :

- **RC522** (SPI) — le plus courant. Communique via le bus SPI du Pi (`/dev/spidev0.0`). La lecture est un cycle requete (`MFRC522_Request`) + anticollision (`MFRC522_Anticoll`). Le 5e octet (checksum XOR) est retire, on ne garde que les 4 octets de l'UID convertis en hex majuscule (ex: `"741ECC2A"`). Bibliotheque : `mfrc522-python`.

- **VMA405** (serie USB) — lecteur autonome connecte en USB. Envoie l'UID en texte sur le port serie (`/dev/ttyUSB0`, 9600 bauds). Lecture via `pyserial`, non bloquante.

- **ACR122U** (USB PC/SC) — lecteur de bureau. Utilise le protocole PC/SC via `pyscard`. Commande APDU standard `FF CA 00 00 00` (GET UID ISO 14443). Necessite le daemon `pcscd` actif.

La boucle principale appelle `read_uid()` toutes les 100ms. Si une carte est presente, la methode retourne son UID hex. Sinon, `None`. La detection de presence/absence se fait par comparaison avec l'UID precedent + un delai anti-rebond (`CARD_GRACE_PERIOD_S`, 3 secondes par defaut) pour eviter les fausses deconnexions dues aux micro-coupures de lecture. Note : ce timer est reinitialise apres les appels reseau `authorize()` + `pour_start` pour eviter que les ~3 secondes d'appels bloquants ne declenchent une fermeture prematuree de la vanne.

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
2. La carte est retiree (grace period de `CARD_GRACE_PERIOD_S` = 3s ecoulee)
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
# Tests pytest DB-only (36 tests, ~8s)
docker exec lespass_django poetry run pytest \
  tests/pytest/test_controlvanne_api.py \
  tests/pytest/test_controlvanne_billing.py \
  tests/pytest/test_controlvanne_models.py -v

# Tests d'appairage discovery (dont le flow tireuse TI)
docker exec lespass_django poetry run pytest \
  tests/pytest/test_discovery_claim_creates_termuser.py \
  tests/pytest/test_discovery_pin_pairing.py -v
```

Couverture :
- `test_controlvanne_api.py` (17 tests) : TireuseAPIKey, HasTireuseAccess, ping, authorize, event, auth-kiosk
- `test_controlvanne_billing.py` (7 tests) : calcul volume, facturation, Transaction, LigneArticle
- `test_controlvanne_models.py` (12 tests) : proprietes modeles, maintenance, events complementaires
- Tests E2E Playwright : non portes depuis lespass-main pour l'instant
  (`test_controlvanne_admin.py`, `test_controlvanne_kiosk.py`) — a porter dans un prochain lot
