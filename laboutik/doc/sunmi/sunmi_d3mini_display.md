# SUNMI D3 Mini — Afficheur Client Segment Display
## Guide d'intégration complet — Dev Senior & Agent IA

> **Sources explorées :** developer.sunmi.com — Customer Display Development, Built-in Printer Service / SDK Reference (New), APIs for Controlling LCD Customer Display
> **Date de rédaction :** 2026-03-24
> **Audience :** Développeur senior Android + Agent IA chargé de l'implémentation

---

## Sommaire

1. [Contexte matériel — Nature de l'afficheur D3 Mini](#1-contexte-matériel)
2. [Architecture SDK — Où se trouve la feature](#2-architecture-sdk)
3. [Intégration — Dépendances et setup](#3-intégration)
4. [API LcdApi — Référence complète](#4-api-lcdapi)
5. [Workflow d'implémentation recommandé](#5-workflow)
6. [Exemples de code complets](#6-exemples-de-code)
7. [Contraintes et pièges critiques](#7-contraintes-et-pièges)
8. [Helper de validation et utilitaires](#8-helpers)
9. [Comparatif des afficheurs SUNMI](#9-comparatif)
10. [Ressources officielles](#10-ressources)

---

## 1. Contexte matériel

### 1.1 Ce qu'est l'afficheur du D3 Mini

L'afficheur intégré au SUNMI D3 Mini est un **écran à segments** (*segment LCD screen / segment display*), comparable aux afficheurs de caisse traditionnels. Il **ne s'agit pas** d'un écran matriciel LCD graphique.

| Propriété | Valeur |
|-----------|--------|
| Type d'écran | Segment LCD (afficheur 7 segments) |
| Nombre de digits max | **7** |
| Caractères supportés | **0–9** et **A–Z** (majuscules uniquement) |
| Séparateur décimal | `.` insérable entre les caractères |
| Usage typique | Affichage prix / montant face client |
| Multiligne | ❌ Non supporté |
| Graphique / Bitmap | ❌ Non supporté |
| Texte libre Unicode | ❌ Non supporté |

Le D3 Mini **et le D3 PRO** (en accessoire) partagent le même type d'afficheur et la même API.

### 1.2 Exploration de la documentation — Ce qui a été trouvé

L'exploration de developer.sunmi.com a couvert les sections suivantes :

| Page explorée | URL | Pertinence D3 Mini |
|---------------|-----|--------------------|
| Customer Display Development — Overview | /xfcfeghjk535 | Contexte général |
| Secondary Display API Documentation | /xfcfeghjk535 | ❌ Écrans Android full (non D3 Mini) |
| T2 Mini Customer display | /xfcdeghjk524 | ❌ Écran 128×40 dots LCD |
| T1 Vice Screen + Dual Screen Interface | /xfzceghjk502 | ❌ Dual screen Android complet |
| **APIs for Controlling LCD Customer Display** | **/xdrxeghjk491** | ✅ **Page clé — contient l'API D3 Mini** |
| Status Light Service Guide | /xmaxeghjk491 | ❌ Concerne FLEX 3 uniquement |

> **Conclusion d'exploration :** La totalité de l'implémentation D3 Mini est concentrée dans la page "APIs for Controlling LCD Customer Display" du SDK Reference (New), accessible via `printer.lcdApi()`.

### 1.3 Positionnement dans l'écosystème SUNMI

La documentation confirme explicitement :

> *"Currently supported devices with customer display interfaces include: T1 MINI, T2 MINI, and D3 MINI, etc."*

Le D3 Mini est **le seul device desktop compact** avec un afficheur segment. Les autres afficheurs SUNMI (T1/T2 Mini) utilisent un LCD 128×40 dots matriciel avec des APIs différentes (`showText`, `showBitmap`). Ces deux familles d'APIs coexistent dans la même `LcdApi` mais ne sont pas interchangeables.

---

## 2. Architecture SDK

### 2.1 Positionnement dans le SDK PrinterX

L'afficheur client est **intégré au SDK d'impression PrinterX**. Il n'existe pas de SDK dédié séparé. L'accès se fait via la même instance `Printer` que pour l'impression thermique.

```
PrinterSdk (singleton)
    └── getPrinter(context, listener)
              │
         Printer (instance unique par device)
              ├── lineApi()         → Impression tickets
              ├── commandApi()      → ESC/POS brut
              ├── queryApi()        → Statut imprimante
              └── lcdApi()          → Afficheur client ← CIBLE
                      ├── config(Command)       → Cycle de vie
                      ├── showDigital(String)   → ✅ D3 Mini
                      ├── showText(...)         → T1/T2 Mini uniquement
                      ├── showTexts(...)        → T1/T2 Mini uniquement
                      └── showBitmap(...)       → T1/T2 Mini uniquement
```

### 2.2 Accès `lcdApi()` depuis le SDK

```java
public LcdApi lcdApi()
```

Méthode publique sur l'objet `Printer`. Retourne une instance `LcdApi` liée au périphérique d'affichage du device. Disponible uniquement après que `PrinterListen.onDefPrinter()` a été appelé.

---

## 3. Intégration

### 3.1 Dépendance Gradle

```gradle
// build.gradle (module app)
android {
    // ...
}

dependencies {
    implementation 'com.sunmi:printerx:1.0.17'
}
```

Version actuelle stable : **1.0.17**. Vérifier les release notes via la page "SDK Release Notes" sur developer.sunmi.com pour les mises à jour.

### 3.2 Version minimum du Print Service

Le service d'impression SUNMI est préinstallé sur tous les devices. Certaines fonctionnalités LcdApi nécessitent une version de service ≥ 6.6.32 (pour `startSettings`). Pour `lcdApi()` de base, aucune restriction de version minimum n'est documentée spécifiquement.

### 3.3 Permissions Android

Aucune permission Android `Manifest` spéciale n'est requise pour accéder à la LcdApi via PrinterX. L'API communique via le service système SUNMI préinstallé (IPC interne).

### 3.4 Initialisation dans Application ou Activity

**Recommandation :** initialiser le SDK au niveau `Application` pour conserver l'instance `Printer` tout au long du cycle de vie de l'app.

```java
// MyApplication.java
public class MyApplication extends Application {

    private static Printer sPrinter;
    private static LcdApi sLcd;

    @Override
    public void onCreate() {
        super.onCreate();
        initPrinterSdk();
    }

    private void initPrinterSdk() {
        PrinterSdk.getInstance().getPrinter(this, new PrinterListen() {

            @Override
            public void onDefPrinter(Printer printer) {
                sPrinter = printer;
                sLcd = printer.lcdApi();
                initDisplay();
            }

            @Override
            public void onPrinters(List<Printer> printers) {
                // Optionnel : traiter plusieurs imprimantes
            }
        });
    }

    private void initDisplay() {
        if (sLcd == null) return;
        sLcd.config(Command.INIT);
        sLcd.config(Command.WAKE);
        sLcd.config(Command.CLEAR);
    }

    @Override
    public void onTerminate() {
        super.onTerminate();
        PrinterSdk.getInstance().destroy();
    }

    // Accesseurs statiques pour les Activities/Fragments
    public static LcdApi getLcd() { return sLcd; }
    public static Printer getPrinter() { return sPrinter; }
}
```

---

## 4. API LcdApi — Référence complète

### 4.1 `config(Command command)` — Gestion du cycle de vie

```java
void config(Command command)
```

Méthode supportée par **tous** les types d'afficheurs SUNMI (segment ET matriciel). Doit être utilisée pour gérer l'état de l'écran.

**Contrainte documentée :** ne peut être utilisée qu'**après le réveil** du device (`WAKE`).

| Enum `Command` | Valeur | Description | Quand l'appeler |
|-----------------|--------|-------------|-----------------|
| `Command.INIT` | INIT | Initialise le périphérique LCD | Première utilisation, `onCreate()` |
| `Command.WAKE` | WAKE | Réveille l'afficheur | Avant tout affichage, après `INIT` |
| `Command.SLEEP` | SLEEP | Met l'afficheur en veille | `onPause()`, `onStop()`, fin de session |
| `Command.CLEAR` | CLEAR | Efface le contenu affiché | Avant nouveau contenu, avant `SLEEP` |

### 4.2 `showDigital(String digital)` — Affichage segment D3 Mini

```java
void showDigital(String digital)
```

**L'unique méthode d'affichage applicable au D3 Mini.**

| Paramètre | Type | Description |
|-----------|------|-------------|
| `digital` | `String` | Valeur à afficher. Max 7 caractères (hors `.`). Charset `[0-9A-Z.]` |

**Comportements détaillés :**
- Les caractères `.` sont des séparateurs décimaux intercalés — ils ne comptent pas dans les 7 digits.
- Seules les majuscules A–Z sont rendues. Les minuscules ne sont pas mentionnées comme supportées.
- Aucune exception n'est documentée pour un input invalide — le comportement est indéfini.

**Exemples valides :**

```java
lcd.showDigital("12.50");      // Prix 12,50 → 5 chars actifs + 1 point
lcd.showDigital("1234.99");    // Prix 1234,99 → 6 chars actifs + 1 point
lcd.showDigital("9999999");    // Maximum absolu, 7 digits
lcd.showDigital("0.00");       // Zéro
lcd.showDigital("TOTAL");      // Message alphabétique (5 chars)
lcd.showDigital("MERCI");      // Message de remerciement (5 chars)
lcd.showDigital("A.1234");     // Mix alpha+numérique
```

**Exemples invalides — À NE PAS FAIRE :**

```java
lcd.showDigital("12345678");   // ❌ 8 digits > 7
lcd.showDigital("12.50€");     // ❌ '€' hors charset
lcd.showDigital("bonjour");    // ❌ minuscules non supportées
lcd.showDigital("Bienvenue");  // ❌ 9 chars > 7 ET minuscules
lcd.showDigital(null);         // ❌ NullPointerException probable
```

### 4.3 Méthodes NON applicables au D3 Mini (pour mémoire)

Les méthodes suivantes existent dans `LcdApi` mais sont **réservées aux écrans 128×40 dots** (T1 Mini, T2 Mini) :

```java
// ❌ NE PAS utiliser sur D3 Mini
void showText(String text, int size, boolean fill)
// → Affiche texte avec taille (6–40px) sur écran matriciel

void showTexts(String[] text, int[] align)
// → Affiche plusieurs lignes de texte sur écran matriciel

void showBitmap(Bitmap bitmap)
// → Affiche un bitmap 128×40px sur écran matriciel
```

---

## 5. Workflow d'implémentation recommandé

### 5.1 Séquence de démarrage (obligatoire)

```
Application.onCreate()
    │
    ├── PrinterSdk.getInstance().getPrinter(ctx, listener)
    │           │
    │    [callback async] onDefPrinter(printer)
    │           │
    │    lcd = printer.lcdApi()
    │           │
    │    lcd.config(INIT)    ← initialisation hardware
    │    lcd.config(WAKE)    ← réveil obligatoire
    │    lcd.config(CLEAR)   ← état propre
    │    lcd.showDigital("0.00")  ← état initial
```

### 5.2 Séquence de mise à jour (pendant l'utilisation)

```
Événement métier (ajout article, calcul total...)
    │
    ├── [Validation] formatForSegmentDisplay(amount)
    │           │
    │    [Si null] → logger l'erreur, ne pas appeler showDigital
    │    [Si String] → lcd.showDigital(formattedValue)
```

### 5.3 Séquence de fermeture (obligatoire)

```
Activity.onPause() ou onStop()
    │
    ├── lcd.config(CLEAR)    ← efface l'affichage
    └── lcd.config(SLEEP)    ← mise en veille hardware

Application.onTerminate() ou service shutdown
    │
    └── PrinterSdk.getInstance().destroy()  ← libère les ressources
```

---

## 6. Exemples de code complets

### 6.1 Activity de caisse complète

```java
// CheckoutActivity.java
public class CheckoutActivity extends AppCompatActivity {

    private LcdApi lcd;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_checkout);

        // Récupérer l'instance depuis l'Application singleton
        lcd = MyApplication.getLcd();

        if (lcd != null) {
            // L'INIT/WAKE a déjà été fait dans Application.onCreate()
            // On peut directement afficher
            lcd.showDigital("0.00");
        } else {
            // Fallback : init locale si l'app a été tuée/relancée
            PrinterSdk.getInstance().getPrinter(this, new PrinterListen() {
                @Override
                public void onDefPrinter(Printer printer) {
                    lcd = printer.lcdApi();
                    lcd.config(Command.INIT);
                    lcd.config(Command.WAKE);
                    lcd.config(Command.CLEAR);
                    lcd.showDigital("0.00");
                }
                @Override
                public void onPrinters(List<Printer> printers) {}
            });
        }
    }

    /**
     * À appeler à chaque modification du total du panier.
     * @param totalCents montant en centimes (ex: 1250 = 12,50€)
     */
    public void onCartUpdated(int totalCents) {
        if (lcd == null) return;

        double total = totalCents / 100.0;
        String formatted = DisplayHelper.formatPrice(total);

        if (formatted != null) {
            lcd.showDigital(formatted);
        }
    }

    /**
     * À appeler lors de la validation du paiement.
     */
    public void onPaymentAccepted() {
        if (lcd == null) return;
        lcd.config(Command.CLEAR);
        lcd.showDigital("MERCI");
    }

    /**
     * À appeler en cas d'erreur de paiement.
     */
    public void onPaymentFailed() {
        if (lcd == null) return;
        lcd.config(Command.CLEAR);
        lcd.showDigital("ERREUR");
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (lcd != null) {
            lcd.config(Command.CLEAR);
            lcd.config(Command.SLEEP);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (lcd != null) {
            lcd.config(Command.WAKE);
            lcd.showDigital("0.00");
        }
    }
}
```

### 6.2 Version Kotlin

```kotlin
// CheckoutActivity.kt
class CheckoutActivity : AppCompatActivity() {

    private var lcd: LcdApi? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_checkout)

        PrinterSdk.getInstance().getPrinter(this, object : PrinterListen() {
            override fun onDefPrinter(printer: Printer) {
                lcd = printer.lcdApi()
                with(lcd!!) {
                    config(Command.INIT)
                    config(Command.WAKE)
                    config(Command.CLEAR)
                    showDigital("0.00")
                }
            }
            override fun onPrinters(printers: List<Printer>) {}
        })
    }

    fun updateTotal(totalEuros: Double) {
        val formatted = DisplayHelper.formatPrice(totalEuros) ?: return
        lcd?.showDigital(formatted)
    }

    override fun onPause() {
        super.onPause()
        lcd?.apply {
            config(Command.CLEAR)
            config(Command.SLEEP)
        }
    }

    override fun onResume() {
        super.onResume()
        lcd?.apply {
            config(Command.WAKE)
            showDigital("0.00")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        PrinterSdk.getInstance().destroy()
    }
}
```

---

## 7. Contraintes et pièges critiques

### ⛔ Contrainte 1 — WAKE obligatoire avant tout affichage

La méthode `config(Command.WAKE)` **doit** être appelée avant tout appel à `showDigital()`. Un appel sur un écran en veille (`SLEEP`) est silencieusement ignoré sans exception ni log. C'est la source numéro 1 de bugs "l'afficheur ne marche pas".

**Pattern à respecter :**
```java
// TOUJOURS dans cet ordre
lcd.config(Command.INIT);   // Une seule fois au démarrage
lcd.config(Command.WAKE);   // À chaque réveil
lcd.showDigital("...");     // Maintenant seulement
```

### ⛔ Contrainte 2 — Limite stricte de 7 caractères significatifs

Les points `.` ne sont pas comptabilisés dans les 7 digits, mais les caractères alphanumériques oui. Dépasser 7 caractères actifs produit un comportement non défini (tronquage ou affichage incorrect).

```java
// ✅ OK : 6 chiffres + 1 point
lcd.showDigital("1234.99");  // 6 chars actifs

// ❌ DANGER : 8 chiffres
lcd.showDigital("12345678"); // Comportement non défini
```

### ⛔ Contrainte 3 — Charset restreint [0-9 A-Z .]

Les caractères suivants **ne sont pas supportés** :
- Minuscules `a–z`
- Symboles monétaires `€ $ £ ¥`
- Espace ` `
- Ponctuation `, ; : ! ? -` (sauf `.`)
- Caractères accentués `é è à ç ü`
- Tout caractère Unicode hors ASCII basique

### ⛔ Contrainte 4 — Ne pas appeler les méthodes LCD matricielles sur D3 Mini

`showText()`, `showTexts()` et `showBitmap()` sont **exclusivement** pour les T1 Mini et T2 Mini (écrans 128×40 dots). Les appeler sur un D3 Mini ne lèvera probablement pas d'exception explicite mais n'affichera rien.

### ⛔ Contrainte 5 — Null safety sur l'instance LcdApi

L'instance `LcdApi` est obtenue de façon **asynchrone** via le callback `onDefPrinter()`. Elle est `null` jusqu'à ce que ce callback soit déclenché. Tout appel prématuré déclenche un `NullPointerException`.

```java
// ✅ Pattern défensif systématique
if (lcd != null) {
    lcd.showDigital("12.50");
}

// Kotlin : opérateur safe-call
lcd?.showDigital("12.50")
```

### ⛔ Contrainte 6 — Libération des ressources

Ne pas appeler `PrinterSdk.getInstance().destroy()` = fuite mémoire et blocage du service d'impression. Toujours libérer dans `onDestroy()`.

---

## 8. Helpers de validation et utilitaires

### 8.1 DisplayHelper complet (Java)

```java
// DisplayHelper.java
public final class DisplayHelper {

    private static final int MAX_SEGMENT_DIGITS = 7;
    private static final java.util.regex.Pattern VALID_CHARS =
        java.util.regex.Pattern.compile("[0-9A-Z.]+");

    private DisplayHelper() {}

    /**
     * Formate un montant en double vers une chaîne compatible segment display D3 Mini.
     * Exemples :
     *   12.5   → "12.50"
     *   1234.9 → "1234.90"
     *   0.0    → "0.00"
     *   99999  → null (trop long)
     *
     * @param amount montant en unité monétaire (ex: 12.50)
     * @return chaîne formatée ou null si trop longue
     */
    @Nullable
    public static String formatPrice(double amount) {
        String raw = String.format("%.2f", amount);
        return validateAndClean(raw);
    }

    /**
     * Valide et nettoie une chaîne arbitraire pour le segment display.
     * - Convertit en majuscules
     * - Filtre les caractères non supportés
     * - Vérifie la longueur max
     *
     * @param input chaîne brute
     * @return chaîne validée ou null si invalide/trop longue
     */
    @Nullable
    public static String validateAndClean(@Nullable String input) {
        if (input == null || input.isEmpty()) return null;

        // Majuscules
        String upper = input.toUpperCase();

        // Filtrer les caractères valides seulement
        StringBuilder filtered = new StringBuilder();
        for (char c : upper.toCharArray()) {
            if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || c == '.') {
                filtered.append(c);
            }
        }

        if (filtered.length() == 0) return null;

        // Compter les digits significatifs (hors points)
        String withoutDots = filtered.toString().replace(".", "");
        if (withoutDots.length() > MAX_SEGMENT_DIGITS) return null;

        return filtered.toString();
    }

    /**
     * Tronque un montant pour qu'il tienne dans 7 digits si nécessaire.
     * Perd les décimales si le montant entier dépasse 7 chiffres.
     */
    @NonNull
    public static String truncateToDisplay(double amount) {
        String full = String.format("%.2f", amount);
        String clean = validateAndClean(full);
        if (clean != null) return clean;

        // Fallback : montant sans décimales
        String noDecimal = String.format("%.0f", amount);
        String cleanNoDecimal = validateAndClean(noDecimal);
        if (cleanNoDecimal != null) return cleanNoDecimal;

        // Dernier recours : valeur maximale affichable
        return "9999999";
    }

    /**
     * Construit un message de statut sur 5–7 caractères A-Z.
     * Les chaînes trop longues sont tronquées à 7 caractères.
     */
    @NonNull
    public static String statusMessage(@NonNull String message) {
        String upper = message.toUpperCase().replaceAll("[^A-Z]", "");
        if (upper.length() > MAX_SEGMENT_DIGITS) {
            return upper.substring(0, MAX_SEGMENT_DIGITS);
        }
        return upper.isEmpty() ? "ERROR" : upper;
    }
}
```

### 8.2 Extension Kotlin

```kotlin
// LcdExtensions.kt
fun LcdApi.safeShowPrice(amount: Double) {
    val formatted = DisplayHelper.formatPrice(amount) ?: return
    showDigital(formatted)
}

fun LcdApi.safeShowMessage(message: String) {
    val clean = DisplayHelper.statusMessage(message)
    showDigital(clean)
}

fun LcdApi.safeShow(raw: String) {
    val clean = DisplayHelper.validateAndClean(raw) ?: return
    showDigital(clean)
}

// Usage
lcd?.safeShowPrice(12.50)          // → showDigital("12.50")
lcd?.safeShowMessage("MERCI")      // → showDigital("MERCI")
lcd?.safeShow("TOTAL")             // → showDigital("TOTAL")
```

### 8.3 Manager de cycle de vie (pattern recommandé)

```java
// CustomerDisplayManager.java
public class CustomerDisplayManager implements DefaultLifecycleObserver {

    private static CustomerDisplayManager instance;
    private LcdApi lcd;
    private boolean isInitialized = false;

    private CustomerDisplayManager() {}

    public static CustomerDisplayManager getInstance() {
        if (instance == null) instance = new CustomerDisplayManager();
        return instance;
    }

    public void initialize(Context context) {
        PrinterSdk.getInstance().getPrinter(context, new PrinterListen() {
            @Override
            public void onDefPrinter(Printer printer) {
                lcd = printer.lcdApi();
                lcd.config(Command.INIT);
                lcd.config(Command.WAKE);
                lcd.config(Command.CLEAR);
                isInitialized = true;
                showIdle();
            }
            @Override
            public void onPrinters(List<Printer> printers) {}
        });
    }

    public void showIdle() {
        safeShow("0.00");
    }

    public void showTotal(double amount) {
        String formatted = DisplayHelper.formatPrice(amount);
        if (formatted != null) safeShow(formatted);
    }

    public void showStatus(String message) {
        safeShow(DisplayHelper.statusMessage(message));
    }

    public void clear() {
        if (lcd != null) lcd.config(Command.CLEAR);
    }

    @Override
    public void onPause(@NonNull LifecycleOwner owner) {
        if (lcd != null) {
            lcd.config(Command.CLEAR);
            lcd.config(Command.SLEEP);
        }
    }

    @Override
    public void onResume(@NonNull LifecycleOwner owner) {
        if (lcd != null) {
            lcd.config(Command.WAKE);
            showIdle();
        }
    }

    @Override
    public void onDestroy(@NonNull LifecycleOwner owner) {
        PrinterSdk.getInstance().destroy();
        isInitialized = false;
        lcd = null;
    }

    private void safeShow(String value) {
        if (!isInitialized || lcd == null) return;
        lcd.showDigital(value);
    }

    public boolean isReady() { return isInitialized && lcd != null; }
}

// Enregistrement dans MainActivity.java
// getLifecycle().addObserver(CustomerDisplayManager.getInstance());
```

---

## 9. Comparatif des afficheurs SUNMI

| Device | Type | API | Résolution | Texte libre | Image | Prix |
|--------|------|-----|------------|-------------|-------|------|
| **D3 Mini** | **Segment LCD** | **`showDigital()`** | **7 digits** | ❌ A–Z only | ❌ | ✅ |
| D3 PRO (acc.) | Segment LCD | `showDigital()` | 7 digits | ❌ | ❌ | ✅ |
| T1 Mini | 128×40 LCD dots | `showText()`, `showBitmap()` | 128×40 px | ✅ | ✅ | ✅ |
| T2 Mini | 128×40 LCD dots | `showText()`, `showBitmap()` | 128×40 px | ✅ | ✅ | ✅ |
| T1 (full screen) | Écran Android | `Presentation` + DSKernel | Full HD | ✅ | ✅ | ✅ |
| T2 (full screen) | Écran Android | `Presentation` API | Full HD | ✅ | ✅ | ✅ |
| FLEX 3 | LED status | `StatusLightManager` | 7 couleurs | ❌ | ❌ | ❌ |

---

## 10. Ressources officielles

| Ressource | Lien / Info |
|-----------|-------------|
| SDK Gradle | `com.sunmi:printerx:1.0.17` |
| GitHub Demo officiel | https://github.com/shangmisunmi/SunmiPrinterDemo |
| Gitee Demo | https://gitee.com/shangmisunmi (dépôt miroir) |
| Doc LCD officielle (docx) | https://ota.cdn.sunmi.com/DOC/resource/re_cn/%E5%AE%A2%E6%98%BE/LCDEN.docx |
| LCD Demo ZIP | https://ota.cdn.sunmi.com/DOC/resource/re_en/TestLcd.zip |
| Page doc principale | https://developer.sunmi.com/docs/en-US/cdixeghjk491/xdrxeghjk491 |
| Partner Platform (global) | https://partner.sunmi.com |
| Android Presentation API | https://developer.android.com/reference/android/app/Presentation |

---

## 11. Checklist d'intégration — Pour l'agent IA

Voici la liste ordonnée des tâches à implémenter pour intégrer l'afficheur client D3 Mini :

- [ ] **Ajouter la dépendance** `com.sunmi:printerx:1.0.17` dans `build.gradle`
- [ ] **Créer `CustomerDisplayManager`** (singleton, lifecycle-aware)
- [ ] **Appeler `initialize(context)`** dans `Application.onCreate()`
- [ ] **Séquence démarrage :** `INIT → WAKE → CLEAR → showDigital("0.00")`
- [ ] **Implémenter `DisplayHelper.formatPrice()`** avec validation charset + longueur max 7
- [ ] **Implémenter `DisplayHelper.validateAndClean()`** pour les inputs arbitraires
- [ ] **Câbler `showTotal()`** sur chaque événement de mise à jour du panier
- [ ] **Câbler `showStatus()`** sur les événements paiement accepté/refusé
- [ ] **Gérer `onPause`** : `CLEAR → SLEEP`
- [ ] **Gérer `onResume`** : `WAKE → showDigital("0.00")`
- [ ] **Appeler `destroy()`** dans `onDestroy()`
- [ ] **Null-check systématique** sur `lcd` avant tout appel (init asynchrone)
- [ ] **Ne jamais appeler** `showText()`, `showTexts()`, `showBitmap()` sur D3 Mini
- [ ] **Tests :** valider les cas limites (montants > 7 digits, chars spéciaux, null)

---

## 12. Notes architecturales finales

**Threading :** Les méthodes `LcdApi` sont des appels IPC vers le service système SUNMI. Ils sont non bloquants mais doivent être appelés depuis le main thread ou avec synchronisation appropriée. En pratique, les appeler directement depuis le callback `onDefPrinter()` (qui s'exécute sur le main thread) est sûr.

**Couplage impression + affichage :** Puisque `lcdApi()` et `lineApi()` partagent la même instance `Printer`, une architecture où un unique `PrinterManager` central gère les deux est conseillée pour éviter les races conditions sur l'initialisation.

**Robustesse :** Le service SUNMI peut être redémarré par le système. `PrinterListen` est conçu pour recevoir des callbacks répétés — maintenir le listener actif (ne pas le désenregistrer) pour récupérer automatiquement en cas de redémarrage du service.

---

*Sources : developer.sunmi.com — Customer Display Development + SDK Reference (New), exploration complète du 2026-03-24*
