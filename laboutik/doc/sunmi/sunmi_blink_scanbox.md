# SUNMI Blink (ScanBox) — Documentation complète
## Pour développeurs seniors & agents IA
**Version :** 1.0 — Mars 2026
**Sources :** SUNMI Developer Portal (Hardware Products > Accessories > Blink), sunmi.com/en/blink/, Sunmi Scanner User Guide, Code Scanner Engine doc

---

## 1. Qu'est-ce que le Blink ?

Le **SUNMI Blink** (aussi appelé "ScanBox" dans certains contextes commerciaux) est un **scanner de codes-barres 2D posé sur comptoir**, plug-and-play, à connectivité USB HID.

Il est classé dans **Hardware Products > Accessories** sur le portail développeur SUNMI — et **non** dans "Scanning Development" — car il ne nécessite aucun SDK pour son usage de base. Il fonctionne nativement comme un clavier HID sur tout système d'exploitation.

**Positionnement produit :** Accessoire de caisse premium, conçu pour remplacer les QR codes papier (risque de fraude) et les scanners industriels (ergonomie/esthétique médiocres).

---

## 2. Fiche technique hardware

| Paramètre | Valeur |
|-----------|--------|
| Dimensions | 9,7 cm × 9 cm × 10 cm |
| Fenêtre de scan | 7,5 cm × 7,5 cm |
| Précision de lecture | 2D > 10 mil |
| Angle de scan ergonomique | 45° |
| Interface | USB male, câble 1,5 m |
| Tension d'entrée | 5V + 0,5A |
| Courant en veille | < 1 mA |
| Courant en fonctionnement | < 190 mA |
| Température de fonctionnement | -10°C à +55°C |
| Température de stockage | -40°C à +70°C |
| Humidité | 5% à 95% (sans condensation) |
| Matière du cadre | Alliage d'aluminium |
| Couleur cadre | Orange (2 variantes) |
| Compatibilité OS | Windows / iOS / Android / Linux |

**Symbologies supportées (selon fiche produit officielle) :**
- QR Code (2D)
- Code 128 (1D)

> ⚠️ La fiche produit sunmi.com ne liste que QR Code + Code 128. Les scanners infrarouge SUNMI sur terminaux mobiles (L2, V2, P2…) supportent 20+ types de codes. Le Blink est un produit distinct avec un moteur optique dédié — se référer au `Blink_document.pdf` (téléchargeable sur le portail dev) pour la liste exhaustive.

---

## 3. LED & Feedback — Ce qui s'allume et pourquoi

### Il n'y a PAS de LED d'éclairage pilotable

Le Blink utilise un **capteur d'image CMOS 2D** (pas un laser de type "pistolet"). L'illumination de la zone de scan est **automatique et interne** — le hardware gère l'exposition sans intervention logicielle.

### Ce qu'il y a : un "Sensor Light" (LED indicateur)

La page produit SUNMI décrit deux éléments de feedback :

| Feedback | Comportement |
|----------|-------------|
| **Sensor Light** (LED) | S'allume / clignote à chaque scan réussi — visible pour le client |
| **Beeping Sound** (buzzer) | Émet un bip à chaque scan réussi — audible pour le client |

Ces deux feedbacks sont **automatiques** et déclenchés par le firmware du Blink lui-même, pas par l'application hôte. Il n'existe **aucune API documentée** pour les contrôler programmatiquement (allumer/éteindre/changer la couleur).

### Configuration du feedback (via Scanner Settings)

Pour les appareils SUNMI avec moteur scanner intégré (L2, V2, P2…), le feedback peut être configuré dans l'app **Scanner Settings** :
- Prompt mode : activer/désactiver le bip et/ou la vibration
- Le Blink étant un périphérique USB HID autonome, ses paramètres de feedback sont dans son propre firmware (voir `Blink_document.pdf`)

---

## 4. Connexion à un appareil SUNMI

### Comportement plug-and-play

Le Blink se branche sur le port USB de l'appareil SUNMI hôte (ou via adaptateur si le SUNMI n'a qu'un port propriétaire). Dès la connexion :

1. Le Blink est reconnu comme **périphérique HID (clavier)** par Android
2. Chaque scan injecte le résultat dans le **champ de texte focusé**, comme une frappe clavier
3. **Zéro configuration, zéro développement** pour l'usage de base

### Modes de sortie — configurables dans Scanner Settings

| Mode | Comportement | Cas d'usage |
|------|-------------|-------------|
| **Simulated keystroke** *(défaut)* | Simule des frappes clavier, résultat dans l'EditText focusé | Formulaires, caisses simples |
| **Direct fill** | Copie dans clipboard + injection (plus rapide que keystroke) | Caisses haut débit |
| **Broadcast output** *(+ keystroke par défaut)* | Envoie un Intent Android avec le résultat | Apps Android qui ne gèrent pas le focus |

> ✅ **Recommandé pour une app Cordova :** activer le **Broadcast output** pour recevoir les scans sans dépendre du focus HTML.

### Écouter les scans par broadcast (Android / SUNMI)

```java
// Constantes
private static final String ACTION_SCAN = "com.sunmi.scanner.ACTION_DATA_CODE_RECEIVED";
private static final String FIELD_DATA = "data";           // String — résultat texte
private static final String FIELD_RAW  = "source_byte";   // byte[] — données brutes

// Enregistrement du receiver
private BroadcastReceiver scanReceiver = new BroadcastReceiver() {
    @Override
    public void onReceive(Context context, Intent intent) {
        String result = intent.getStringExtra(FIELD_DATA);
        byte[] raw    = intent.getByteArrayExtra(FIELD_RAW); // v2.3.1+
        // Traiter le résultat ici
    }
};

private void registerScanReceiver() {
    IntentFilter filter = new IntentFilter();
    filter.addAction(ACTION_SCAN);
    registerReceiver(scanReceiver, filter);
}

private void unregisterScanReceiver() {
    unregisterReceiver(scanReceiver);
}
```

### Soft-trigger (déclenchement logiciel du scan)

Via l'AIDL du service scanner SUNMI :

```java
// Bind au service
private IScanInterface scanInterface;

private ServiceConnection conn = new ServiceConnection() {
    @Override
    public void onServiceConnected(ComponentName name, IBinder service) {
        scanInterface = IScanInterface.Stub.asInterface(service);
    }
    @Override
    public void onServiceDisconnected(ComponentName name) {
        scanInterface = null;
    }
};

public void bindScannerService(Context ctx) {
    Intent intent = new Intent();
    intent.setPackage("com.sunmi.scanner");
    intent.setAction("com.sunmi.scanner.IScanInterface");
    ctx.bindService(intent, conn, Service.BIND_AUTO_CREATE);
}

// Déclencher un scan par code
scanInterface.scan();   // démarre la capture
scanInterface.stop();   // arrête la capture (utiliser en binôme avec scan())

// Trigger clavier personnalisé (ex: remplacer la touche physique)
scanInterface.sendKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_CAMERA));

// Identifier le type de moteur scanner connecté
int model = scanInterface.getScannerModel();
// 100 = NONE, 101-122 = modèles spécifiques (Newland, Zebra, Honeywell, SUNMI SS…)
```

**AndroidManifest.xml requis (Android 11+) :**
```xml
<manifest>
    <queries>
        <package android:name="com.sunmi.scanner" />
        <package android:name="com.sunmi.sunmiqrcodescanner" />
    </queries>
</manifest>
```

### Intégration Cordova

Le Blink sur un terminal SUNMI avec app Cordova — chemin recommandé :

**Option A — Broadcast via plugin natif**
```java
// Native plugin : ScanPlugin.java
public class ScanPlugin extends CordovaPlugin {

    private BroadcastReceiver receiver;

    @Override
    public boolean execute(String action, JSONArray args, CallbackContext cb) {
        if ("startListening".equals(action)) {
            receiver = new BroadcastReceiver() {
                @Override
                public void onReceive(Context ctx, Intent intent) {
                    String code = intent.getStringExtra("data");
                    cb.success(code); // remonte le résultat en JS
                }
            };
            IntentFilter f = new IntentFilter("com.sunmi.scanner.ACTION_DATA_CODE_RECEIVED");
            cordova.getActivity().registerReceiver(receiver, f);
            return true;
        }
        if ("stopListening".equals(action)) {
            cordova.getActivity().unregisterReceiver(receiver);
            cb.success();
            return true;
        }
        return false;
    }
}
```

```javascript
// www/js/scanner.js
var Scanner = {
    startListening: function(onScan, onError) {
        cordova.exec(onScan, onError, 'ScanPlugin', 'startListening', []);
    },
    stopListening: function(success, error) {
        cordova.exec(success, error, 'ScanPlugin', 'stopListening', []);
    }
};

// Usage :
Scanner.startListening(function(code) {
    console.log('Scan reçu :', code);
    // ex: mettre à jour panier, lookup produit, paiement…
}, function(err) {
    console.error('Erreur scan :', err);
});
```

**Option B — cordova-plugin-broadcaster** (si pas de plugin custom)
```javascript
// Écouter l'action broadcast directement
broadcaster.addEventListener('com.sunmi.scanner.ACTION_DATA_CODE_RECEIVED', function(e) {
    console.log('Code scanné :', e.data);
});
```

---

## 5. Connexion à un Raspberry Pi (ou tout OS non-Android)

Le Blink étant un **périphérique USB HID standard**, il fonctionne sur n'importe quel hôte USB sans driver.

> ⚠️ **Point critique :** Le câble du Blink se termine par un **USB male** (spécifié "USB male with 1.5 meter line"). Compatible USB-A standard. À vérifier physiquement si le port hôte est bien USB-A (le Raspberry Pi 4 a 2× USB-A 3.0 + 2× USB-A 2.0 — compatible).

### Sur Raspberry Pi / Linux

**Option 1 — Lecture HID via evdev (recommandée)**
```python
import evdev

def find_blink():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for dev in devices:
        # Le Blink apparaît comme un clavier HID
        caps = dev.capabilities(verbose=True)
        if evdev.ecodes.EV_KEY in dev.capabilities():
            return dev
    return None

blink = find_blink()
if blink:
    print(f"Blink trouvé : {blink.name} sur {blink.path}")
    for event in blink.read_loop():
        if event.type == evdev.ecodes.EV_KEY:
            key_event = evdev.categorize(event)
            if key_event.keystate == evdev.KeyEvent.key_down:
                print(f"Touche : {key_event.keycode}")
```

**Option 2 — Lecture via /dev/hidraw (binaire brut)**
```python
import struct

HIDRAW_DEVICE = '/dev/hidraw0'  # adapter selon votre système

with open(HIDRAW_DEVICE, 'rb') as f:
    while True:
        data = f.read(8)  # paquet HID standard = 8 bytes
        # Parsing des keycodes HID standard
        modifier, _, key1, key2, key3, key4, key5, key6 = struct.unpack('8B', data)
        if key1 != 0:
            print(f"Key HID: {key1:#04x}")
```

**Option 3 — Lecture dans un terminal (le plus simple)**

Comme le Blink simule un clavier, si le terminal a le focus :
```python
# Le scan + Enter est automatiquement envoyé — lire stdin suffit
import sys

print("En attente d'un scan...")
for line in sys.stdin:
    code = line.strip()
    if code:
        print(f"Code reçu : {code}")
        # traitement…
```

**Option 4 — Flask webhook (pour intégration web)**
```python
from flask import Flask, request, jsonify
import evdev
import threading

app = Flask(__name__)
last_scan = {"code": None}

def scan_loop():
    blink = find_blink()  # voir Option 1
    buffer = ""
    for event in blink.read_loop():
        if event.type == evdev.ecodes.EV_KEY:
            key = evdev.categorize(event)
            if key.keystate == evdev.KeyEvent.key_down:
                if key.keycode == 'KEY_ENTER':
                    last_scan["code"] = buffer
                    buffer = ""
                elif key.keycode.startswith('KEY_'):
                    char = key.keycode.replace('KEY_', '').lower()
                    buffer += char

@app.route('/scan', methods=['GET'])
def get_scan():
    return jsonify(last_scan)

threading.Thread(target=scan_loop, daemon=True).start()
app.run(host='0.0.0.0', port=5000)
```

---

## 6. Avantage commercial vs téléphone client (QR affiché)

SUNMI positionne explicitement le Blink contre l'usage du QR code papier et du téléphone commerçant comme scanner.

| Problème avec le téléphone / QR papier | Solution Blink |
|----------------------------------------|----------------|
| Le client cherche son appli, sort son téléphone → friction | Scan immédiat, le client approche simplement son écran |
| Mauvais angles, poses inconfortables | Angle fixe 45°, zone ouverte 7,5×7,5 cm |
| QR code papier = risque de fraude (substitution) | Hardware actif, non remplaçable physiquement |
| Scanner pistolaire industriel = image dégradée en caisse | Design premium aluminium, personnalisable aux couleurs marque |
| Qualité variable selon le téléphone du commerçant | Moteur optique dédié, précision constante (>10 mil) |
| Consommation élevée du téléphone scanner | Veille < 1mA, alimentation USB passive |

### Avantages techniques vs caméra téléphone

| Critère | Caméra téléphone | Blink |
|---------|-----------------|-------|
| Temps de scan | 200-800ms (autofocus) | Quasi-instantané (pas d'autofocus) |
| Lecture codes abîmés | Moyenne (dépend du moteur) | Bonne (moteur dédié >10 mil) |
| Fiabilité sous éclairage faible | Médiocre sans torche | Bonne (illumination interne auto) |
| Lecture sans contact | Non (le commerçant tient le tel) | Oui (posé sur comptoir) |
| Connexion à la caisse | Bluetooth / WiFi (latence) | USB filaire (zéro latence) |
| Gestion du focus logiciel | Nécessaire | Non requise (HID) |
| Personnalisation marque | Impossible | Cadre, base, fenêtre personnalisables |

### Argument commercial résumé

> Le Blink résout **3 problèmes simultanément** : l'expérience client (friction, ergonomie), la sécurité marchande (pas de fraude au QR), et l'image de marque en caisse (design premium personnalisable). C'est le seul accessoire SUNMI pensé comme un objet de comptoir et non comme un outil professionnel.

---

## 7. Limites et points de vigilance

- **Symbologies limitées** (QR + Code 128 selon fiche officielle) — vérifier `Blink_document.pdf` pour la liste complète du moteur
- **Pas d'API LED** documentée — le Sensor Light est géré par le firmware, non pilotable par l'app
- **Soft-trigger AIDL** (`scan()`/`stop()`) nécessite Android + service `com.sunmi.scanner` — non disponible sur Raspberry Pi / Windows
- **Sur Raspberry Pi** : utiliser evdev ou stdin pour lire le HID — le broadcast Android n'existe pas
- **Câble fixe 1,5m** — pas de mode sans fil Bluetooth ou WiFi
- **Compatible iOS** (HID natif) mais iOS bloque l'accès à `/dev/hidraw` — lecture uniquement via le champ focusé ou une app dédiée
- **Personnalisation** (cadre, couleur) : sur devis, via représentant SUNMI — pas de commande web directe
- **Page dev mise à jour en 2023** — vérifier si de nouvelles APIs ont été ajoutées au firmware depuis

---

## 8. Ressources

| Ressource | Lien / Chemin |
|-----------|--------------|
| Page Hardware Blink (portail dev) | https://developer.sunmi.com/docs/en-US/ceghjk502/crieghjk579 |
| Blink_document.pdf | Bouton Download sur la page ci-dessus |
| Page produit SUNMI | https://www.sunmi.com/en/blink/ |
| Sunmi Scanner User Guide | https://developer.sunmi.com/docs/read/en-US/frmeghjk546 |
| Code Scanner Engine (Infrared) | https://developer.sunmi.com/docs/en-US/cdixeghjk491/xfareghjk568 |
| Camera-Based Scanner SDK | https://developer.sunmi.com/docs/en-US/cdixeghjk491/xfafeghjk480 |
| ScanHeadDemo.zip | Lien dans la page Code Scanner Engine |

---

## 9. Checklist agent IA — Implémentation Blink

### Pré-requis
- [ ] Confirmer que le terminal cible a un port USB-A disponible (ou adaptateur)
- [ ] Confirmer l'OS hôte : Android SUNMI / Raspberry Pi Linux / Windows / iOS
- [ ] Télécharger et lire `Blink_document.pdf` pour la liste complète des symbologies

### Sur Android SUNMI (app Cordova)
- [ ] Activer "Broadcast output" dans Scanner Settings (sur le device)
- [ ] Implémenter `ScanPlugin.java` avec `BroadcastReceiver` sur `com.sunmi.scanner.ACTION_DATA_CODE_RECEIVED`
- [ ] Exposer `Scanner.startListening(callback)` / `Scanner.stopListening()` en JS
- [ ] Ajouter `<queries>` dans AndroidManifest.xml pour Android 11+
- [ ] Tester : app en foreground, en background, écran verrouillé
- [ ] Gérer le cas "service scanner non disponible" (device non-SUNMI)

### Sur Raspberry Pi / Linux
- [ ] Connecter le Blink en USB, vérifier la présence dans `/dev/input/` via `evdev.list_devices()`
- [ ] Identifier le device Blink par son nom HID
- [ ] Implémenter la boucle `read_loop()` avec buffer + détection KEY_ENTER
- [ ] Tester la lecture en terminal (stdin) avant evdev si prototypage rapide
- [ ] Gérer les permissions udev (`/dev/input/eventX` requiert sudo ou règle udev)

### Tests d'intégration
- [ ] QR Code (paiement mobile) lu correctement
- [ ] Code 128 (code-barre produit) lu correctement
- [ ] Résultat reçu en < 200ms après scan
- [ ] Pas de doublon scan (vérifier que le CMOS ne scanne pas en boucle)
- [ ] Feedback LED + bip visible/audible pour le client
- [ ] Comportement si Blink débranché à chaud (pas de crash app)

---

*Généré à partir du SUNMI Developer Portal et de sunmi.com — Mars 2026*
*Sources : Hardware Products > Accessories > Blink, Sunmi Scanner User Guide, Code Scanner Engine (Infrared scan code), fiche produit officielle*
