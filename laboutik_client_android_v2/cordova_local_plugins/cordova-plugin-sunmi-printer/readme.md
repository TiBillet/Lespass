# cordova-plugin-sunmi-printer

Plugin Cordova pour imprimer sur les terminaux **Sunmi** (V2, D3mini, etc.) via le SDK `com.sunmi:printerlibrary:1.0.23`.

## Prérequis

Terminal Sunmi avec le service `woyou.aidlservice.jiuiv5` préinstallé. Ce plugin ne fonctionne pas sur les appareils non-Sunmi.

## Installation

```bash
cordova plugin add /cordova_local_plugins/cordova-plugin-sunmi-printer
```

## Utilisation

Toutes les méthodes retournent une **Promise**.

### Exemple : imprimer un ticket

```javascript
async function printTicket() {
  try {
    // 1. Initialiser le service (obligatoire avant toute impression)
    await SunmiPrinterPlugin.initSunmiPrinterService();

    // 2. Vérifier la disponibilité
    const ok = await SunmiPrinterPlugin.isPrinterAvailable();
    if (!ok) {
      console.error("Imprimante non disponible");
      return;
    }

    // 3. Imprimer
    await SunmiPrinterPlugin.setAlign(1);                    // 0=gauche, 1=centre, 2=droite
    await SunmiPrinterPlugin.printText("TIBILLET", 32, true, false);
    await SunmiPrinterPlugin.lineWrap(1);
    await SunmiPrinterPlugin.printText("Ticket #12345", 24, false, false);
    await SunmiPrinterPlugin.printText("15.00 EUR", 28, true, false);
    await SunmiPrinterPlugin.lineWrap(2);
    await SunmiPrinterPlugin.printQr("https://tibillet.coop", 8, 0);
    await SunmiPrinterPlugin.lineWrap(3);
    await SunmiPrinterPlugin.cutPaper();

    console.log("Ticket imprimé");
  } catch (err) {
    console.error("Erreur d'impression:", err);
  }
}
```

### API disponible

| Méthode | Arguments | Description |
|---------|-----------|-------------|
| `initSunmiPrinterService()` | — | Connecte le service AIDL Sunmi (appeler en premier) |
| `isPrinterAvailable()` | — | `true` si le service est connecté |
| `printText(text, size, bold, underline)` | String, Float, Bool, Bool | Texte simple |
| `setAlign(align)` | Int (0/1/2) | Alignement |
| `printQr(data, moduleSize, errorLevel)` | String, Int, Int | QR code |
| `printBarCode(data, symbology, height, width, textPos)` | String + 4 Ints | Code-barres |
| `printTable(texts[], widths[], aligns[])` | 3 arrays | Colonnes alignées |
| `lineWrap(n)` | Int | Saut de lignes |
| `cutPaper()` | — | Coupe du papier |
| `openDrawer()` | — | Ouvre le tiroir-caisse |
| `autoOutPaper()` | — | Éjection auto du papier |
| `updatePrinterState()` | — | État matériel (int) |
| `printBitmap(base64)` | String Base64 | Image Base64 → Bitmap → impression (voir ci-dessous) |

### Impression d'image

**Formats supportés** : PNG, JPEG, BMP (décodage via `BitmapFactory` Android).

**Préparation côté JS** :
```javascript
// Depuis un canvas
const canvas = document.getElementById('monCanvas');
const base64 = canvas.toDataURL('image/png').split(',')[1]; // retire le prefixe data:image/...

// Depuis un fichier (FileReader)
const file = input.files[0];
const reader = new FileReader();
reader.onloadend = () => {
  const base64 = reader.result.split(',')[1];
  SunmiPrinterPlugin.printBitmap(base64);
};
reader.readAsDataURL(file);
```

**Conseils** :
- Largeur max : **384 px** (imprimantes thermiques Sunmi 58mm : V2, V2s, D3mini, etc. à 203 DPI).
- Le préfixe `data:image/...;base64,` doit être retiré avant d'envoyer.

## Debug

```bash
adb logcat | grep SunmiPrintHelper
```
