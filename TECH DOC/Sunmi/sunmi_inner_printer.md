# SUNMI Built-in Printer (Imprimante Intégrée) — Guide Développeur

> Documentation de référence : [developer.sunmi.com](https://developer.sunmi.com/docs/en-US/cdixeghjk491/xdzaeghjk480)
> Synthèse réalisée le 2026-03-24

---

## 🖨️ Présentation

Les appareils SUNMI (terminaux POS, handhelds, kiosques) embarquent une imprimante thermique **directement intégrée au device** — appelée **inner printer** ou **inbuilt non-detachable printer**.

**Exemples de devices concernés :** SUNMI V1, V2, V2 PRO, V2s, V2s Plus, T2, T2s, P2, M2, D2, S2…

**Caractéristiques matérielles :**

| Paramètre | Valeur |
|-----------|--------|
| Technologie | Thermique |
| Formats papier | 58mm ou 80mm (selon le modèle) |
| Coupe-papier (cutter) | Certains modèles uniquement |
| Modes d'impression | Reçu thermique / Étiquette / Black mark (selon le modèle) |
| Tiroir-caisse | Certains modèles desktop |
| Afficheur client LCD | Certains modèles |

---

## 🔌 Modes de connexion disponibles

| Mode | Description | Cas d'usage |
|------|-------------|-------------|
| **PrinterX SDK (New)** | Lib Gradle Android, API haut niveau | App Android native — recommandé |
| **AIDL (Old SDK)** | Accès direct au service système via AIDL | Legacy, encore très répandu |
| **Virtual Bluetooth `InnerPrinter`** | L'imprimante intégrée expose un BT virtuel | Apps tierces, systèmes POS legacy |
| **ESC/POS Raw** | Envoi de bytes directement | Via commandApi() ou BT |
| **JavaScript Printer** | SDK pour webviews/apps hybrides | Apps web embarquées |
| **Flutter Printer** | Plugin Flutter officiel SUNMI | Apps Flutter cross-platform |
| **Uniapp Printer** | Plugin Uniapp officiel SUNMI | Apps Uniapp |

---

## I. Service d'impression SUNMI (SunmiPrinter)

Le service d'impression est **préinstallé dans le système** des appareils SUNMI. Il est accessible depuis les paramètres système sous le nom **`[SunmiPrinter]`**.

### Paramètres configurables

**a. Type d'imprimante**
Certains modèles supportent plusieurs modes :
- Reçu thermique standard (défaut)
- Mode étiquette (label) — avec calibration auto ou manuelle
- Mode black mark — avec réglage de position de coupe

**b. Densité d'impression**
Réglable de 70% à 130%.

**c. Style d'impression**
Permet de surcharger temporairement le layout du développeur. Active l'impression multi-codes sur une ligne (barcodes/QR via commandes EPSON).

**d. Polices disponibles**
- SunmiMonoSpaced 1.0 — plage limitée, épaisse, pour l'anglais
- SunmiMonoSpaced 2.0 — quasi tous les blocs, fine
- SunmiMonoSpaced 3.0 — version améliorée de la 2.0 (recommandée)
- Police personnalisée — possible en désactivant la compatibilité système

**e. Format papier**
L'imprimante intégrée 80mm peut être configurée en mode 58mm (avec un guide physique).

**f. Alertes système**
Broadcast vocal automatique si le papier manque ou si le capot est ouvert. Désactivable.

**g. DND au démarrage**
Désactive le broadcast vocal au boot tout en conservant les alertes normales.

**h. Bluetooth virtuel InnerPrinter**
Bluetooth fictif intégré au système permettant de contrôler l'imprimante comme un périphérique BT classique. Données parsées en ESC/POS par défaut (ou TSPL si configuré).

**i. Coupe automatique**
Si activé, coupe automatiquement après chaque impression, même sans commande GS V dans le contenu.

---

## II. SDK New — PrinterX (recommandé)

### 1. Intégration

```gradle
// build.gradle (module)
dependencies {
    implementation 'com.sunmi:printerx:1.0.17'
}
```

**Ressources :**
- GitHub Demo : https://github.com/shangmisunmi/SunmiPrinterDemo
- Gitee Demo : disponible sur gitee.com

### 2. Initialisation et obtention du printer

```java
// Obtenir le printer (asynchrone)
PrinterSdk.getInstance().getPrinter(context, new PrinterListen() {

    @Override
    public void onDefPrinter(Printer printer) {
        // Imprimante par défaut (built-in en général)
        mPrinter = printer;
    }

    @Override
    public void onPrinters(List<Printer> printers) {
        // Toutes les imprimantes disponibles sur le device
        for (Printer p : printers) {
            Log.d("Printer", p.toString()); // ID unique du printer
        }
    }
});
```

> Le `PrinterListen` peut être conservé en permanence : SUNMI met à jour dynamiquement la liste des imprimantes en temps réel.

### 3. Activer les logs de debug

```java
PrinterSdk.getInstance().log(true, "MyApp");
// Tag par défaut : [PrinterX]
// Désactiver en production !
```

### 4. Libérer les ressources

```java
PrinterSdk.getInstance().destroy();
```

### 5. Sauter vers les paramètres système

```java
// Ouvrir la page de réglage de densité
printer.startSettings(activity, SettingItem.DENSITY);

// Autres valeurs de SettingItem :
// SettingItem.TYPE    → type d'imprimante (thermique/étiquette)
// SettingItem.PAPER   → format du papier
// SettingItem.FONT    → police
// SettingItem.ALL     → tous les paramètres
```

---

## III. LineApi — Impression de tickets (haut niveau)

La **LineApi** est l'API recommandée pour imprimer des tickets thermiques. Elle travaille ligne par ligne et imprime immédiatement chaque élément.

```java
LineApi line = printer.lineApi();
```

### 3.1 Initialiser le style de base

```java
// Style par défaut
line.initLine(BaseStyle.getStyle());

// Centré
line.initLine(BaseStyle.getStyle().setAlign(Align.CENTER));

// Avec marge gauche de 20px et hauteur de ligne de 40px
line.initLine(BaseStyle.getStyle()
    .setPosX(20)
    .setHeight(40)
    .setAlign(Align.LEFT));
```

**Options de BaseStyle :**

| Méthode | Description | Défaut |
|---------|-------------|--------|
| `setAlign(Align)` | Alignement inline | LEFT |
| `setWidth(n)` | Largeur de la zone imprimable | Largeur papier |
| `setHeight(n)` | Hauteur de ligne (0–255 px) | 30 px |
| `setPosX(n)` | Marge gauche | 0 px |

### 3.2 Imprimer du texte

```java
// Impression directe
line.printText("Bonjour client !", TextStyle.getStyle());

// Accumulation puis impression (addText + saut de ligne)
line.addText("Article 1 : ", TextStyle.getStyle().enableBold(true));
line.addText("Café expresso\n", TextStyle.getStyle());

// Colonnes (rapport de largeur 2:1:1)
TextStyle centered = TextStyle.getStyle().setAlign(Align.CENTER);
line.printTexts(
    new String[]{"Produit", "Qté", "Prix"},
    new int[]{2, 1, 1},
    new TextStyle[]{centered, centered, centered}
);
```

**Options de TextStyle :**

| Méthode | Description | Plage | Défaut |
|---------|-------------|-------|--------|
| `setTextSize(n)` | Taille caractère (px) | 6–96 | 24 |
| `setTextWidthRatio(n)` | Magnification horizontale | 0–7 | 0 |
| `setTextHeightRatio(n)` | Magnification verticale | 0–7 | 0 |
| `setTextSpace(n)` | Espacement (px) | 0–100 | 0 |
| `enableBold(bool)` | Gras | — | false |
| `enableUnderline(bool)` | Souligné | — | false |
| `enableStrikethrough(bool)` | Barré | — | false |
| `enableItalics(bool)` | Italique | — | false |
| `enableInvert(bool)` | Inversion | — | false |
| `enableAntiColor(bool)` | Texte blanc sur fond noir | — | false |
| `setFont(name)` | Police custom (depuis assets/) | — | Police système |

### 3.3 Imprimer un code-barres

```java
line.printBarCode("1234567890",
    BarcodeStyle.getStyle()
        .setSymbology(Symbology.CODE128)
        .setBarHeight(80)
        .setDotWidth(2)
        .setReadable(HumanReadable.POS_TWO)   // texte en-dessous
        .setAlign(Align.CENTER)
);
```

**Types de codes-barres (Symbology) :**
UPCA, UPCE, EAN13, EAN8, CODE39, ITF, CODABAR, CODE93, CODE128

**Position HRI (HumanReadable) :**
HIDE, POS_ONE (dessus), POS_TWO (dessous), POS_THREE (dessus et dessous)

### 3.4 Imprimer un QR code

```java
line.printQrCode("https://example.com",
    QrStyle.getStyle()
        .setDot(6)                      // taille module (1–16)
        .setErrorLevel(ErrorLevel.M)    // L/M/Q/H
        .setAlign(Align.CENTER)
);
```

**Niveaux de correction d'erreur (ErrorLevel) :**

| Valeur | Taux de correction |
|--------|--------------------|
| L | 7% |
| M | 15% |
| Q | 25% |
| H | 30% |

### 3.5 Imprimer une image (Bitmap)

```java
BitmapFactory.Options opts = new BitmapFactory.Options();
opts.inScaled = false;
Bitmap bmp = BitmapFactory.decodeResource(getResources(), R.drawable.logo, opts);

line.printBitmap(bmp,
    BitmapStyle.getStyle()
        .setAlgorithm(ImageAlgorithm.DITHERING)
        .setAlign(Align.CENTER)
);
```

**Algorithmes image (ImageAlgorithm) :**

| Algorithme | Description | Paramètre float |
|------------|-------------|-----------------|
| BINARIZATION | Binarisation (seuil) | ~200 selon couleurs |
| DITHERING | Dithering niveaux de gris | Non requis |

> ⚠️ Le fond doit être opaque. Les pixels transparents sont convertis en noir.

### 3.6 Ligne de séparation

```java
line.printDividingLine(DividingLine.EMPTY, 20);   // 20px blanc
line.printDividingLine(DividingLine.DOTTED, 2);   // ligne pointillée 2px
line.printDividingLine(DividingLine.SOLID, 2);    // ligne pleine 2px
line.printDividingLine(DividingLine.EMPTY, 20);   // 20px blanc
```

### 3.7 Sortie papier et coupe

```java
// Sortie papier automatique + coupe si cutter présent
line.autoOut();
```

### 3.8 Mode transaction (impression atomique)

```java
line.enableTransMode(true);   // Activer le cache

// Toutes les commandes suivantes sont mises en attente
line.printText("Ligne 1", TextStyle.getStyle());
line.printText("Ligne 2", TextStyle.getStyle());
line.autoOut();

// Soumettre en une seule opération atomique
line.printTrans(result -> {
    if (result.resultCode == 0) {
        Log.d("Print", "Succès");
    } else {
        Log.e("Print", "Échec : " + result.message);
    }
});
```

---

## IV. CommandApi — ESC/POS et TSPL bruts

Pour les développeurs qui construisent leur contenu directement en commandes binaires.

```java
CommandApi cmd = printer.commandApi();
```

### 4.1 Envoi ESC/POS

```java
// Reset imprimante
cmd.sendEscCommand(new byte[]{0x1B, 0x40});

// Centrer
cmd.sendEscCommand(new byte[]{0x1B, 0x61, 0x01});

// Activer UTF-8 (commande SUNMI propriétaire)
cmd.sendEscCommand(new byte[]{0x1D, 0x28, 0x45, 0x03, 0x00, 0x06, 0x03, 0x01});

// Texte en GB18030 (encodage par défaut)
byte[] text = "Reçu n°001\n".getBytes("gb18030");
cmd.sendEscCommand(text);

// Gras ON
cmd.sendEscCommand(new byte[]{0x1B, 0x45, 0x01});

// Gras OFF
cmd.sendEscCommand(new byte[]{0x1B, 0x45, 0x00});

// Coupe partielle
cmd.sendEscCommand(new byte[]{0x1D, 0x56, 0x31});
```

> **Encodage par défaut : GB18030.** Pour les caractères UTF-8 (accents, €, etc.), envoyer d'abord la commande propriétaire SUNMI : `\x1D\x28\x45\x03\x00\x06\x03\x01`

### 4.2 Envoi TSPL (étiquettes)

```java
// Exemple d'étiquette 40x30mm
String tspl =
    "SIZE 40 mm,30 mm\n" +
    "GAP 2 mm,0 mm\n" +
    "CLS\n" +
    "TEXT 10,10,\"3\",0,1,1,\"Produit ABC\"\n" +
    "BARCODE 10,50,\"CODE128\",60,1,0,2,2,\"12345678\"\n" +
    "PRINT 1\n";

cmd.sendTsplCommand(tspl.getBytes(StandardCharsets.US_ASCII));
```

> ⚠️ TSPL ne fonctionne qu'en **mode étiquette** (vérifier `PrinterInfo.TYPE == 2`). Sur les modèles V2 PRO, V2s, basculer le mode dans les paramètres.

---

## V. QueryApi — Statut et informations

```java
QueryApi query = printer.queryApi();
```

### 5.1 Statut en temps réel (thread secondaire !)

```java
new Thread(() -> {
    Status s = query.getStatus();

    // États d'erreur (bloquants)
    if (s == Status.READY)                 Log.d("P", "Prête");
    else if (s == Status.ERR_PAPER_OUT)    Log.e("P", "Plus de papier");
    else if (s == Status.ERR_COVER)        Log.e("P", "Capot ouvert");
    else if (s == Status.ERR_PRINTER_HOT)  Log.e("P", "Surchauffe tête");
    else if (s == Status.ERR_MOTOR_HOT)    Log.e("P", "Surchauffe moteur");
    else if (s == Status.ERR_PAPER_JAM)    Log.e("P", "Bourrage papier");
    else if (s == Status.ERR_CUTTER)       Log.e("P", "Erreur coupe-papier");
    else if (s == Status.OFFLINE)          Log.e("P", "Hors ligne");

    // Avertissements (non bloquants)
    else if (s == Status.WARN_THERMAL_PAPER) Log.w("P", "Papier presque épuisé");
    else if (s == Status.WARN_PICK_PAPER)    Log.w("P", "Papier non retiré");
}).start();
```

### 5.2 Informations matérielles

```java
String firmware = query.getInfo(PrinterInfo.VERSION);  // ex: "2.7.0"
String paper    = query.getInfo(PrinterInfo.PAPER);    // ex: "80mm"
String type     = query.getInfo(PrinterInfo.TYPE);     // "0"=thermique
String density  = query.getInfo(PrinterInfo.DENSITY);  // ex: "100"
String distance = query.getInfo(PrinterInfo.DISTANCE); // longueur totale imprimée (mm)
String cuts     = query.getInfo(PrinterInfo.CUTTER);   // nb de coupes
```

**Types d'imprimante (PrinterInfo.TYPE) :**

| Valeur | Type |
|--------|------|
| 0 | Thermique standard (défaut) |
| 1 | Thermique black mark |
| 2 | Thermique étiquettes |
| 3 | Stylus |
| 4 | Laser |

### 5.3 Broadcasts système Android

```java
// Déclarer un BroadcastReceiver dans l'app
IntentFilter filter = new IntentFilter();
filter.addAction("woyou.aidlservice.jiuv5.NORMAL_ACTION");
filter.addAction("woyou.aidlservice.jiuv5.OUT_OF_PAPER_ACTION");
filter.addAction("woyou.aidlservice.jiuv5.COVER_OPEN_ACTION");
filter.addAction("woyou.aidlservice.jiuv5.OVER_HEATING_ACITON");
filter.addAction("woyou.aidlservice.jiuv5.LESS_OF_PAPER_ACTION");
filter.addAction("woyou.aidlservice.jiuv5.KNIFE_ERROR_ACTION_1");
filter.addAction("woyou.aidlservice.jiuv5.KNIFE_ERROR_ACTION_2");
filter.addAction("woyou.aidlservice.jiuv5.PAPER_ERROR_ACITON");
filter.addAction("woyou.aidlservice.jiuv5.ERROR_ACTION");

registerReceiver(printerReceiver, filter);
```

| Broadcast | Description |
|-----------|-------------|
| NORMAL_ACTION | Prête |
| OUT_OF_PAPER_ACTION | Plus de papier |
| PAPER_ERROR_ACITON | Bourrage papier |
| OVER_HEATING_ACITON | Surchauffe tête |
| MOTOR_HEATING_ACITON | Surchauffe moteur |
| COVER_OPEN_ACTION | Capot ouvert |
| COVER_ERROR_ACTION | Capot mal fermé |
| KNIFE_ERROR_ACTION_1 | Erreur coupe-papier |
| KNIFE_ERROR_ACTION_2 | Coupe-papier rétabli |
| LESS_OF_PAPER_ACTION | Papier presque épuisé |
| LABEL_NON_EXISTENT_ACITON | Étiquette non détectée |
| BLACKLABEL_NON_EXISTENT_ACITON | Black mark non détecté |
| ERROR_ACTION | Erreur inconnue |

---

## VI. Bluetooth Virtuel InnerPrinter

Chaque device SUNMI expose l'imprimante intégrée comme un **périphérique Bluetooth fictif** nommé `InnerPrinter`.

**Avantages :**
- Compatible avec n'importe quel système POS tiers (sans SDK SUNMI)
- Connexion BT standard, envoi de bytes ESC/POS bruts
- Mode TSPL configurable depuis les paramètres système SunmiPrinter

**Fonctionnement :**
1. Chercher le device BT nommé `InnerPrinter` dans la liste Bluetooth
2. S'y connecter comme à un périphérique SPP (Serial Port Profile)
3. Envoyer des bytes ESC/POS directement via le socket BT

---

## VII. Exemple complet — Ticket de caisse

```java
public void printReceipt(Printer printer) {
    LineApi line = printer.lineApi();

    // Transaction atomique
    line.enableTransMode(true);

    // --- En-tête ---
    line.initLine(BaseStyle.getStyle().setAlign(Align.CENTER));

    // Logo (optionnel)
    // line.printBitmap(logoBitmap, BitmapStyle.getStyle().setAlgorithm(ImageAlgorithm.DITHERING));

    line.printText("MA BOUTIQUE",
        TextStyle.getStyle().setTextSize(36).enableBold(true));
    line.printText("123 Rue de la Paix, Paris",
        TextStyle.getStyle().setTextSize(20));
    line.printText("Tel: 01 23 45 67 89",
        TextStyle.getStyle().setTextSize(20));

    line.printDividingLine(DividingLine.EMPTY, 10);
    line.printDividingLine(DividingLine.SOLID, 2);
    line.printDividingLine(DividingLine.EMPTY, 10);

    // --- Corps ---
    line.initLine(BaseStyle.getStyle().setAlign(Align.LEFT));

    TextStyle normal   = TextStyle.getStyle().setTextSize(22);
    TextStyle bold     = TextStyle.getStyle().setTextSize(22).enableBold(true);
    TextStyle centered = TextStyle.getStyle().setAlign(Align.CENTER);
    TextStyle right    = TextStyle.getStyle().setAlign(Align.RIGHT);

    // En-tête colonnes
    line.printTexts(
        new String[]{"Produit", "Qté", "Prix"},
        new int[]{3, 1, 1},
        new TextStyle[]{bold, bold, bold}
    );

    line.printDividingLine(DividingLine.DOTTED, 2);

    // Lignes produit
    line.printTexts(
        new String[]{"Café expresso", "x2", "4.00€"},
        new int[]{3, 1, 1},
        new TextStyle[]{normal, centered, right}
    );
    line.printTexts(
        new String[]{"Croissant beurre", "x1", "1.50€"},
        new int[]{3, 1, 1},
        new TextStyle[]{normal, centered, right}
    );

    line.printDividingLine(DividingLine.SOLID, 2);

    // Total
    line.printTexts(
        new String[]{"TOTAL", "", "5.50€"},
        new int[]{3, 1, 1},
        new TextStyle[]{bold, bold, bold}
    );

    line.printDividingLine(DividingLine.EMPTY, 20);

    // QR code de fidélité
    line.initLine(BaseStyle.getStyle().setAlign(Align.CENTER));
    line.printQrCode("https://maboutique.fr/fidelite",
        QrStyle.getStyle().setDot(5).setErrorLevel(ErrorLevel.M));

    line.printText("Merci de votre visite !",
        TextStyle.getStyle().setTextSize(20));

    line.printDividingLine(DividingLine.EMPTY, 20);

    // Sortie + coupe
    line.autoOut();

    // Soumettre la transaction
    line.printTrans(result -> {
        if (result.resultCode == 0)
            Log.d("Print", "Impression réussie");
        else
            Log.e("Print", "Erreur : " + result.message);
    });
}
```

---

## VIII. Architecture globale

```
Application Android
        │
        ▼
┌──────────────────────────────────┐
│     SUNMI PrinterX SDK           │
│  com.sunmi:printerx:1.0.17       │
│                                  │
│  PrinterSdk.getInstance()        │
│    .getPrinter(ctx, listener)    │
└──────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│          SUNMI Print Service (service système)         │
│          (préinstallé sur tous les devices SUNMI)      │
└───────────────────────────────────────────────────────┘
        │              │              │
        ▼              ▼              ▼
  Inner Printer   Custom Printer   Laser Printer
  (intégrée)     (BT/LAN/USB)     (kiosque K1/K2)
        │
        ▼
   Virtual BT
  "InnerPrinter"
  (apps tierces)
```

---

## IX. Référence rapide — Commandes ESC/POS brutes

| Commande | Bytes (hex) | Description |
|----------|-------------|-------------|
| Reset | `1B 40` | Réinitialise l'imprimante |
| LF | `0A` | Saut de ligne |
| Align gauche | `1B 61 00` | |
| Align centre | `1B 61 01` | |
| Align droite | `1B 61 02` | |
| Gras ON | `1B 45 01` | |
| Gras OFF | `1B 45 00` | |
| Double H+L | `1B 21 30` | |
| Mode normal | `1B 21 00` | |
| Souligné 1pt | `1B 2D 01` | |
| Coupe partielle | `1D 56 31` | |
| Coupe totale | `1D 56 30` | |
| UTF-8 ON (SUNMI) | `1D 28 45 03 00 06 03 01` | |
| Densité 100% | `1D 28 45 02 00 07 64` | |
| QR code | `1D 28 6B ...` | GS ( k |
| Barcode | `1D 6B ...` | GS k |
| Image raster | `1D 76 30 00 ...` | GS v 0 |

---

## X. Ressources

| Ressource | Lien |
|-----------|------|
| GitHub Demo officiel | https://github.com/shangmisunmi/SunmiPrinterDemo |
| Documentation PDF built-in printer | Disponible sur developer.sunmi.com |
| Commandes ESC/POS SUNMI | https://ota.cdn.sunmi.com/DOC/resource/re_en/ESC-POS%20Command%20set.docx |
| App Store outil impression screenshot | SUIYIN (App Store SUNMI) |
| Plugin impression web | Sunmiprinterplugin (App Store SUNMI) |

---

*Sources : developer.sunmi.com — Built-in Printer Service Documentation (2026)*
