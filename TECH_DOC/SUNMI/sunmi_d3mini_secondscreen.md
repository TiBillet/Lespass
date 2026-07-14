# SUNMI D3 Mini — Secondary Screen (Full Display)
## Documentation for Senior Developers & AI Coding Agents
**Version:** 1.0 — March 2026
**App stack:** Apache Cordova
**Target hardware:** SUNMI D3 Mini (variant with 80mm printer + real secondary touchscreen)

---

## 1. Hardware Context

### Device Variants
The **D3 Mini** line has two secondary-display variants:

| Variant | Secondary display type | API family |
|---------|------------------------|------------|
| D3 Mini (basic) | 7-digit segment LED | `LcdApi.showDigital()` |
| **D3 Mini (Pro/Full)** | **Real LCD touchscreen** | **Presentation API + DSKernel SDK + ClientView** |

This document covers **only the second variant**: the one with a real LCD touchscreen acting (by default) as a mirror of the main screen.

### Physical layout
- **Main screen** — capacitive touchscreen, runs the primary Android app (your Cordova app)
- **Secondary screen** — real LCD touchscreen, physically facing the customer
- **Built-in 80mm thermal printer** — driven by the inner printer SDK (see `sunmi_inner_printer.md`)
- Both screens share the **same Android OS instance** — two logical displays, one device

### Default "Mirror" Behaviour
Out of the box, the secondary screen simply mirrors the main display (Android default for a secondary display without a `Presentation` assigned to it).  
**As soon as you attach a `Presentation` window to the secondary display, mirroring stops** and the secondary screen becomes fully independent.

---

## 2. Escaping Mirror Mode — Conceptual Overview

Android exposes multiple connected displays through `DisplayManager`. The secondary screen appears as a display flagged with `Display.FLAG_PRESENTATION`. When no `Presentation` window occupies it, Android mirrors the primary display.

**The escape mechanism:**
1. Enumerate displays via `DisplayManager`
2. Find the one with `Display.FLAG_PRESENTATION`
3. Attach your own `Presentation` subclass (or a `WebView` inside a `Dialog`) to that display
4. Mirror stops immediately; your content is shown independently

Three concrete approaches are documented below, ranked by compatibility with a **Cordova** app.

---

## 3. Approaches — Ranked by Cordova Compatibility

### ★★★ Approach A — ClientView (Recommended for Cordova)

#### What it is
**ClientView** is an official SUNMI open-source application designed specifically for the D3 Mini and D3 Pro. Its sole job is to **display any URL / web page on the customer (secondary) screen**.

- Source code: downloadable from the SUNMI developer portal as `ClientView code.zip`
- No modifications to your existing Cordova app required
- The secondary screen loads a WebView pointing to any URL you configure

#### How it works with Cordova

```
[Main screen]                        [Secondary screen]
Cordova App                          ClientView App
  └─ serves content at               └─ WebView
     local URL or remote URL   ──►       pointing to that URL
```

**Option A1 — Remote URL (simplest)**
Configure ClientView to point to a URL your backend serves (e.g., `https://yourserver.com/customer-display`).  
Your Cordova app updates the display by updating that URL's content server-side.

**Option A2 — Local Cordova server (recommended for offline)**
Cordova apps using `cordova-plugin-local-server` (or similar) expose a local HTTP server (e.g., `http://localhost:8080`).  
Configure ClientView to load `http://localhost:8080/customer-display.html`.  
Communication channel: shared `SharedPreferences` or an `Intent` broadcast from Cordova → ClientView to trigger page refreshes.

**Option A3 — Intent-based URL switching**
From your Cordova app (via a native plugin or `cordova-plugin-broadcaster`), send an `Intent` to ClientView with a new URL to display:

```java
// Native side of a Cordova plugin (Java)
Intent intent = new Intent("com.sunmi.clientview.ACTION_SHOW_URL");
intent.setPackage("com.sunmi.clientview"); // ClientView package name — verify in APK manifest
intent.putExtra("url", "http://localhost:8080/receipt-preview.html");
context.sendBroadcast(intent);
```

> ⚠️ **Verify the actual Intent action string** from the ClientView source (`ClientView code.zip`). The name above is illustrative. Always read the source.

#### Setup steps
1. Download `ClientView code.zip` from the SUNMI developer portal (Customer Display Development → ClientView section)
2. Build and deploy ClientView APK to the D3 Mini (or distribute via SUNMI App Market)
3. ClientView auto-starts on boot and auto-attaches to the secondary screen
4. Configure the initial URL inside ClientView settings or via Intent

#### Features included in ClientView
- URL display (any HTTP/HTTPS URL)
- Browsing history
- Auto-start on device boot
- Dual-screen independent control (main screen controls secondary screen content)
- No additional SDK dependency in your Cordova project

---

### ★★☆ Approach B — Android Presentation API (Native WebView)

Use this when you need **tight integration** between the Cordova app and the secondary display without deploying a separate APK.

#### Concept
Create a custom `Presentation` subclass that inflates a `WebView`. Attach it to the secondary display. Load any URL (including `file:///android_asset/www/...` for Cordova assets).

#### Core Android code

```java
import android.app.Presentation;
import android.content.Context;
import android.hardware.display.DisplayManager;
import android.os.Bundle;
import android.view.Display;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class CustomerDisplayPresentation extends Presentation {

    private WebView webView;

    public CustomerDisplayPresentation(Context context, Display display) {
        super(context, display);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(getContext());
        webView.setWebViewClient(new WebViewClient());
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        setContentView(webView);
        webView.loadUrl("file:///android_asset/www/customer-display.html");
        // Or: webView.loadUrl("http://localhost:8080/customer-display.html");
    }

    public void loadUrl(String url) {
        if (webView != null) {
            webView.post(() -> webView.loadUrl(url));
        }
    }

    public void evaluateJS(String script) {
        if (webView != null) {
            webView.post(() -> webView.evaluateJavascript(script, null));
        }
    }
}
```

#### Attaching the Presentation to the secondary display

```java
public class SecondScreenManager {

    private CustomerDisplayPresentation presentation;
    private final Context context;

    public SecondScreenManager(Context context) {
        this.context = context;
    }

    public void start() {
        DisplayManager dm = (DisplayManager) context.getSystemService(Context.DISPLAY_SERVICE);
        Display[] displays = dm.getDisplays(DisplayManager.DISPLAY_CATEGORY_PRESENTATION);

        if (displays.length == 0) {
            // No secondary display found — device may not be the right variant
            Log.w("SecondScreen", "No PRESENTATION display found.");
            return;
        }

        Display secondaryDisplay = displays[0]; // Take first presentation display
        presentation = new CustomerDisplayPresentation(context, secondaryDisplay);
        presentation.show();
    }

    public void stop() {
        if (presentation != null && presentation.isShowing()) {
            presentation.dismiss();
            presentation = null;
        }
    }

    public void navigate(String url) {
        if (presentation != null) {
            presentation.loadUrl(url);
        }
    }

    public void runScript(String js) {
        if (presentation != null) {
            presentation.evaluateJS(js);
        }
    }
}
```

#### Keeping the display alive when Activity goes to background

```java
// In the Presentation subclass onCreate(), after setContentView():
getWindow().setType(WindowManager.LayoutParams.TYPE_SYSTEM_OVERLAY);
// Requires permission in AndroidManifest.xml:
// <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />
```

> ⚠️ `TYPE_SYSTEM_OVERLAY` is restricted on Android 8+. On SUNMI devices (which use a customised Android), this may be permitted by default. Test on actual hardware.

#### Cordova plugin bridge

Create a Cordova plugin (`src/android/SecondScreenPlugin.java`) that:

```java
public class SecondScreenPlugin extends CordovaPlugin {

    private SecondScreenManager manager;

    @Override
    public boolean execute(String action, JSONArray args, CallbackContext callbackContext) {
        switch (action) {
            case "start":
                manager = new SecondScreenManager(cordova.getActivity());
                cordova.getActivity().runOnUiThread(() -> manager.start());
                callbackContext.success();
                return true;

            case "navigate":
                String url = args.optString(0, "");
                cordova.getActivity().runOnUiThread(() -> manager.navigate(url));
                callbackContext.success();
                return true;

            case "runScript":
                String js = args.optString(0, "");
                cordova.getActivity().runOnUiThread(() -> manager.runScript(js));
                callbackContext.success();
                return true;

            case "stop":
                cordova.getActivity().runOnUiThread(() -> manager.stop());
                callbackContext.success();
                return true;
        }
        return false;
    }
}
```

**JavaScript side (Cordova):**
```javascript
// www/js/second-screen.js
var SecondScreen = {
    start: function(success, error) {
        cordova.exec(success, error, 'SecondScreenPlugin', 'start', []);
    },
    navigate: function(url, success, error) {
        cordova.exec(success, error, 'SecondScreenPlugin', 'navigate', [url]);
    },
    runScript: function(js, success, error) {
        cordova.exec(success, error, 'SecondScreenPlugin', 'runScript', [js]);
    },
    stop: function(success, error) {
        cordova.exec(success, error, 'SecondScreenPlugin', 'stop', []);
    }
};

// Usage:
SecondScreen.start(function() {
    SecondScreen.navigate('https://yourserver.com/customer-display');
});
```

---

### ★☆☆ Approach C — DSKernel SDK (Programmatic Templates)

Use this when you need to send **structured data** (text, QR codes, images, video) to the secondary screen via SUNMI's own IPC layer, without managing a WebView yourself.

> This approach does **not** support raw HTML. It uses predefined display templates fed with JSON data.

#### Gradle dependency

```gradle
// app/build.gradle
dependencies {
    compile 'com.sunmi:DS_Lib:latest.release'
}
```

#### DSKernel SDK lifecycle

```java
// 1. Get instance
DSKernel mDSKernel = DSKernel.newInstance();

// 2. Initialise (call in Application.onCreate() or Activity.onCreate())
mDSKernel.init(context, new IDSKernel() {
    @Override
    public void onInitResult(boolean success) {
        // SDK ready — you can now send data
    }
});

// 3. Register connection callback
mDSKernel.addConnCallback(new IConnCallback() {
    @Override
    public void onConnected() { /* secondary screen app ready */ }
    @Override
    public void onDisconnected() { /* handle disconnect */ }
});

// 4. Register receive callback (if secondary screen sends back data)
mDSKernel.addReceiveCallback(new IReceiveCallback() {
    @Override
    public void onReceiveData(DSPacket packet) { /* handle incoming */ }
});

// 5. Cleanup
mDSKernel.unInit(context);
```

#### Sending content

```java
// Send structured text/JSON payload
String json = buildDataModelJson(DataModel.TEXT, yourPayload);
DSPacket packet = UPacketFactory.buildShowText(packageName, json, new ISendCallback() {
    @Override public void onSuccess() { }
    @Override public void onFail(int code) { }
});
mDSKernel.sendData(packet);

// Send a file (image, video)
mDSKernel.sendFile(packageName, "/sdcard/image.jpg", new ISendCallback() { ... });

// Send a command (e.g., switch template)
mDSKernel.sendCMD(packageName, json, fileId, new ISendCallback() { ... });
```

#### DataModel types — all supported templates

| DataModel constant | Display type | JSON key fields |
|--------------------|--------------|-----------------|
| `TEXT` | Text block | `title`, `subTitle`, `time` |
| `QRCODE` | QR code + label | `qrContent`, `label` |
| `SHOW_IMG_WELCOME` | Fullscreen welcome image | `imgPath` or `imgUrl` |
| `IMAGES` | Single image | `imgPath` or `imgUrl` |
| `VIDEO` | Single video | `videoPath` or `videoUrl` |
| `VIDEOS` | Video playlist | `videoList[]` (array of paths/URLs) |
| `SHOW_IMG_LIST` | Scrolling image list | `imgList[]` |
| `SHOW_IMGS_LIST` | Multi-image grid | `imgList[]` |
| `SHOW_VIDEO_LIST` | Video list with previews | `videoList[]` |
| `MENUVIDEOS` | Menu + video overlay | `menuItems[]`, `videoPath` |

#### Example JSON — TEXT template

```json
{
  "dataModel": "TEXT",
  "data": {
    "title": "Order #1042",
    "subTitle": "Thank you for your purchase!",
    "time": "2026-03-24 14:32"
  }
}
```

#### Example JSON — QRCODE template

```json
{
  "dataModel": "QRCODE",
  "data": {
    "qrContent": "https://yourapp.com/receipt/1042",
    "label": "Scan to get your receipt"
  }
}
```

#### File caching strategy
The DSKernel SDK caches transferred files on the secondary screen side. To force a refresh:
- Use a unique `fileId` on each `sendFile` call
- Or include a cache-busting suffix in the filename

---

## 4. SUNMI-Specific AndroidManifest.xml Additions

```xml
<!-- Required for Presentation API with background persistence -->
<uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />

<!-- Required if using DSKernel -->
<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
<uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />

<!-- Auto-install secondary screen app via SUNMI App Market: -->
<!-- Add to <application> tag: -->
<!-- android:sharedUserId="com.sunmi.ds" -->
<!-- (Only if your app IS the secondary screen app — not for the main Cordova app) -->
```

---

## 5. App Architecture on SUNMI Dual-Screen Devices

```
┌─────────────────────────────────────────┐
│             Android OS                  │
│                                         │
│  Display 0 (main)   Display 1 (customer)│
│  ┌──────────────┐   ┌──────────────┐   │
│  │  Cordova App │   │  ClientView  │   │
│  │  (your app)  │──►│  (WebView)   │   │
│  │              │   │  loads URL   │   │
│  └──────────────┘   └──────────────┘   │
│         │                  ▲           │
│         └──── Intent ───────┘           │
│              broadcast                  │
└─────────────────────────────────────────┘
```

For Approach B (native plugin):
```
┌─────────────────────────────────────────┐
│             Android OS                  │
│                                         │
│  Display 0 (main)   Display 1 (customer)│
│  ┌──────────────┐   ┌──────────────┐   │
│  │  Cordova App │   │ Presentation │   │
│  │  + Plugin ───┼──►│  (WebView)   │   │
│  │              │   │  loads URL   │   │
│  └──────────────┘   └──────────────┘   │
└─────────────────────────────────────────┘
```

---

## 6. Cordova-Specific Integration Guide

### Recommended path for your Cordova app

**Phase 1 — Validate with ClientView (zero code change)**
1. Install ClientView on a D3 Mini test device
2. Create a static `customer-display.html` in your Cordova `www/` folder
3. Serve it via `cordova-plugin-local-webserver` (port 8080) or a remote URL
4. Configure ClientView to load that URL
5. Verify rendering, fonts, and touch interactions on secondary screen

**Phase 2 — Dynamic content via Cordova → ClientView bridge**
1. Add `cordova-plugin-broadcaster` (or write a minimal native plugin) to send Intents
2. On payment completion, cart update, or custom events → broadcast new URL to ClientView
3. ClientView reloads the WebView to the new URL

**Phase 3 (optional) — Full native plugin (Approach B)**
If you need JS ↔ secondary screen bidirectional communication (e.g., touch events on secondary screen back to Cordova):
1. Implement `SecondScreenPlugin.java` as described in Approach B
2. Register in `plugin.xml`
3. Use `SecondScreen.runScript()` to push data into the secondary WebView from Cordova JS

### Useful Cordova plugins

| Plugin | Purpose |
|--------|---------|
| `cordova-plugin-broadcaster` | Send/receive Android Intents from JS |
| `cordova-plugin-local-webserver` | Serve local files over HTTP (for ClientView to load) |
| `cordova-plugin-file` | Access app storage paths for image/video transfer to DSKernel |

---

## 7. Decision Matrix

| Scenario | Recommended approach |
|----------|---------------------|
| Display HTML/CSS/JS pages | **A (ClientView)** or B |
| Offline HTML (bundled in Cordova assets) | B (native plugin with `file:///android_asset/`) |
| Display receipt QR code | C (DSKernel QRCODE template) or A |
| Display promotional video | C (DSKernel VIDEO/VIDEOS) or A |
| Bi-directional JS communication | B (native plugin) |
| Zero code change in Cordova app | **A (ClientView)** |
| Tight control from Cordova JS | B (native plugin) |
| SUNMI-native template UI (text/images) | C (DSKernel) |

---

## 8. Known Constraints & DO NOTs

- **DO NOT** assume `displays[0]` is the secondary screen — always filter by `Display.FLAG_PRESENTATION` or use `DisplayManager.DISPLAY_CATEGORY_PRESENTATION`
- **DO NOT** try to modify the mirror with CSS or JS from the main WebView — the mirror is at the OS level, not the web layer
- **DO NOT** use `TYPE_SYSTEM_OVERLAY` without testing on the exact SUNMI firmware version — behaviour varies
- **DO NOT** mix Approach A and Approach B simultaneously — only one app can own the secondary display's `Presentation` window at a time
- **DO NOT** hard-code ClientView's Intent action string without verifying in its source — use the zip source as truth
- **DO NOT** use DSKernel (Approach C) if you need raw HTML — it only supports its own template DataModel types
- **DSKernel is NOT available on all SUNMI models** — confirm device compatibility in the SUNMI SDK documentation
- **ClientView is D3 Mini / D3 Pro specific** — do not assume it works on T1, T2, or other models without verification

---

## 9. Resources & Downloads

| Resource | Location |
|----------|---------|
| `ClientView code.zip` | SUNMI Developer Portal → Customer Display Development → ClientView |
| `DS_Lib` (DSKernel SDK) | Maven: `com.sunmi:DS_Lib:latest.release` |
| Secondary Display API doc | https://developer.sunmi.com/docs/en-US/cdixeghjk491/xfcfeghjk535 |
| ClientView doc page | https://developer.sunmi.com/docs/en-US/cdixeghjk491/xmmqeghjk513 |
| T1 Custom Vice Screen doc | https://developer.sunmi.com/docs/en-US/cdixeghjk491/xfzaeghjk480 |
| T1 Built-in Vice Screen doc | https://developer.sunmi.com/docs/en-US/cdixeghjk491/xfmreghjk568 |
| SUNMI Developer Portal | https://developer.sunmi.com |

---

## 10. AI Agent Implementation Checklist

Use this checklist to implement secondary screen support in the Cordova app:

### Pre-requisites
- [ ] Confirm target device is D3 Mini with real LCD secondary screen (not segment LED variant)
- [ ] Confirm Android API level on device (check SUNMI specs — typically Android 11 or 13)
- [ ] Install ClientView APK on test device (build from source zip or use SUNMI App Market)

### Approach A — ClientView (start here)
- [ ] Add `cordova-plugin-local-webserver` or choose a remote URL strategy
- [ ] Create `www/customer-display.html` with your customer-facing UI
- [ ] Configure ClientView initial URL (via its settings UI or via Intent on first launch)
- [ ] Implement Intent broadcast from Cordova to ClientView for URL switching
  - [ ] Verify exact Intent action string from ClientView source code
  - [ ] Test broadcast from `cordova-plugin-broadcaster`
- [ ] Test on device: mirror must stop when ClientView is running
- [ ] Test: Cordova app background → secondary screen must stay active

### Approach B — Native Plugin (if needed beyond Approach A)
- [ ] Create `src/android/SecondScreenPlugin.java` with `CordovaPlugin` base
- [ ] Implement `SecondScreenManager.java` (DisplayManager + Presentation + WebView)
- [ ] Register plugin in `plugin.xml` and `config.xml`
- [ ] Expose JS API: `start`, `navigate`, `runScript`, `stop`
- [ ] Add `SYSTEM_ALERT_WINDOW` permission to `AndroidManifest.xml`
- [ ] Test URL loading: remote URL, local HTTP, `file:///android_asset/www/`
- [ ] Test JS injection via `evaluateJavascript()`
- [ ] Test lifecycle: Activity pause/resume — secondary screen must stay visible

### Approach C — DSKernel (if structured templates are acceptable)
- [ ] Add `compile 'com.sunmi:DS_Lib:latest.release'` to `build.gradle`
- [ ] Initialise DSKernel in `Application.onCreate()`
- [ ] Implement `IConnCallback` and `IReceiveCallback`
- [ ] Build JSON payloads for required DataModel types (TEXT, QRCODE, etc.)
- [ ] Test `sendData` and `sendFile` for each template type needed
- [ ] Handle file caching (unique fileIds or cache-bust strategy)

### Integration tests
- [ ] Mirror mode deactivates when secondary screen app is attached
- [ ] Secondary screen content updates within 500ms of Cordova event
- [ ] Device reboot → secondary screen app auto-starts correctly
- [ ] Secondary screen remains active during Cordova app background/foreground cycles
- [ ] No crash when secondary display is not available (non-D3-Mini devices)

---

*Generated from SUNMI Developer Portal exploration — March 2026*
*Sources: Secondary Display API, ClientView documentation, DSKernel SDK reference, T1 Vice Screen documentation*
