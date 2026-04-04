# Schéma de câblage TiBillet — Pi 3B+ + PoE HAT (C)

> Document destiné à un stagiaire en électronique.
> Vérifié le 04/04/2026.

---

## Architecture générale

```
Switch PoE 802.3af/at
       │ RJ45 (réseau + 48V)
       ▼
Waveshare PoE HAT (C)   ← posé sur le Pi via header GPIO 40 broches
  ├── 5V → alimente le Pi (automatique via GPIO)
  └── 12V / 2A → header 2P → module relais → électrovanne ASCO
       │
Raspberry Pi 3B+
  ├── SPI  → MFRC522 NFC
  ├── GPIO 17 → DIGMESA débitmètre
  ├── GPIO 26 → module relais Handsontec
  └── HDMI  → écran kiosque
```

---

## Budget de puissance

| Rail | Consommation | Limite HAT | Marge |
|---|---|---|---|
| 5V (Pi + périphériques) | ~640 mA ≈ 3,2W | 4,5A | large |
| 12V (électrovanne) | ~800 mA ≈ 9,6W | 2A | ok |
| **Total** | **≈ 12,8W** | **25W** | **~49%** |

---

## Tableau de câblage complet

### 1. MFRC522 — Lecteur NFC (SPI)

> ⚠️ Alimenter en **3,3V uniquement** — le 5V détruit la puce.

| Broche MFRC522 | GPIO BCM | Pin physique | Remarque |
|---|---|---|---|
| VCC | — | **Pin 1** | 3,3V — JAMAIS 5V |
| GND | — | **Pin 6** | Masse |
| MOSI | GPIO 10 | **Pin 19** | SPI0 MOSI |
| MISO | GPIO 9 | **Pin 21** | SPI0 MISO |
| SCK | GPIO 11 | **Pin 23** | SPI0 SCLK |
| SDA (CS) | GPIO 8 | **Pin 24** | SPI0 CE0 |
| RST | GPIO 25 | **Pin 22** | Reset logiciel |
| IRQ | — | Non connecté | Non utilisé |

> Activer SPI dans `raspi-config` → Interfacing Options → SPI → Yes

---

### 2. DIGMESA 934-6550 — Débitmètre (GPIO interrupt)

> Sortie open-collector NPN — nécessite une résistance pull-up.
> Le Pi possède des pull-up internes activables en Python (`GPIO.PUD_UP`).

| Broche DIGMESA | GPIO BCM | Pin physique | Remarque |
|---|---|---|---|
| VCC | — | **Pin 1** | 3,3V (ou Pin 17 = autre 3,3V) |
| GND | — | **Pin 9** | Masse (ou tout autre GND) |
| OUT (signal) | GPIO 17 | **Pin 11** | Entrée interrupt — pull-up interne |

> Configurer en Python : `GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)`
> Chaque impulsion = volume calibré (à mesurer empiriquement avec de l'eau)

---

### 3. Module relais Handsontec 1 canal — Commande électrovanne

> ⚠️ **Retirer le jumper VCC–JD-VCC avant tout branchement.**
> S'il reste en place, le 5V de la bobine remonte sur le 3,3V du Pi → destruction garantie.

| Broche relais | GPIO BCM | Pin physique | Remarque |
|---|---|---|---|
| VCC (signal opto) | — | **Pin 1** | 3,3V — côté signal optocoupleur |
| JD-VCC (bobine) | — | **Pin 2** | 5V — alimente la bobine relais |
| GND | — | **Pin 6** | Masse commune |
| IN | GPIO 26 | **Pin 37** | Commande relais — actif LOW |

> Le relais s'active quand GPIO 26 = LOW (0V).
> Il se désactive quand GPIO 26 = HIGH (3,3V).
> En Python : `GPIO.output(26, GPIO.LOW)` → ouvre l'électrovanne

---

### 4. Électrovanne ASCO SCG283A012V — Charge 12V DC

> Câblage sur les bornes à vis du module relais.
> Utiliser du fil min. **0,5 mm²** pour le 12V.

| Borne relais | Connexion | Remarque |
|---|---|---|
| COM | Fil + du header 12V PoE HAT | Alimentation 12V permanente |
| NO | Fil + de l'électrovanne ASCO | Circuit ouvert au repos |
| — | Fil − électrovanne → GND 12V | Retour masse alimentation 12V |

> **Normalement Ouvert (NO)** : l'électrovanne est fermée au repos (pas d'eau),
> elle s'ouvre uniquement quand le relais est activé. C'est le mode sécurisé.

---

### 5. Diode flyback 1N4007 — Protection électrovanne

> Le module relais protège déjà sa propre bobine (diode intégrée).
> La diode ci-dessous protège les **contacts du relais** contre le retour
> de tension de la bobine de l'électrovanne ASCO.

```
12V ──────┬──────── borne COM relais
          │
    cathode │ 1N4007  (bande = cathode = côté +12V)
    anode  │
          │
          └──────── borne − électrovanne (GND 12V)
```

**En pratique** : souder la diode directement sur les cosses de l'électrovanne,
cathode côté + (fil rouge), anode côté − (fil noir). Gainé thermorétractable.

---

### 6. Écran HDMI — Mode kiosque

> L'écran a sa **propre alimentation secteur**.
> Le Pi ne fournit que le signal vidéo numérique via le câble HDMI.
> Consommation supplémentaire côté Pi : ~30 mA (signal HDMI) + ~150 mA (Chromium kiosque).

| Connexion | Détail |
|---|---|
| Câble HDMI | Port HDMI du Pi → port HDMI de l'écran |
| Alim écran | Prise secteur séparée — indépendante du PoE |

---

## Récapitulatif des pins utilisés sur le Pi 3B+

| Pin physique | GPIO BCM | Fonction | Périphérique |
|---|---|---|---|
| Pin 1 | — | 3,3V | VCC NFC + VCC débitmètre + VCC signal relais |
| Pin 2 | — | 5V | JD-VCC bobine relais |
| Pin 6 | — | GND | NFC + débitmètre + relais |
| Pin 9 | — | GND | (alternative GND débitmètre) |
| Pin 11 | GPIO 17 | Entrée interrupt | Débitmètre DIGMESA — signal pulses |
| Pin 19 | GPIO 10 | SPI0 MOSI | MFRC522 — données vers NFC |
| Pin 21 | GPIO 9 | SPI0 MISO | MFRC522 — données depuis NFC |
| Pin 22 | GPIO 25 | Sortie | MFRC522 — RST reset |
| Pin 23 | GPIO 11 | SPI0 SCLK | MFRC522 — horloge SPI |
| Pin 24 | GPIO 8 | SPI0 CE0 | MFRC522 — chip select |
| Pin 37 | GPIO 26 | Sortie | Module relais — commande électrovanne |
| Port HDMI | — | Vidéo | Écran kiosque |

> ✅ Aucun doublon de pin.
> ✅ GPIO 26 (relais) ≠ GPIO 25 (RST NFC) ≠ GPIO 17 (débitmètre).

---

## Checklist câblage — dans l'ordre

- [ ] Retirer le jumper VCC–JD-VCC du module relais
- [ ] Câbler tous les GND en premier
- [ ] Câbler les alimentations 3,3V et 5V
- [ ] Câbler les signaux SPI du MFRC522
- [ ] Câbler le signal GPIO 17 du débitmètre
- [ ] Câbler le signal GPIO 26 du relais
- [ ] Souder la diode 1N4007 sur les cosses de l'électrovanne
- [ ] Câbler les bornes 12V du relais vers l'électrovanne
- [ ] Brancher le câble HDMI
- [ ] Vérifier au multimètre : pas de continuité Pin 1 (3,3V) ↔ Pin 2 (5V)
- [ ] Brancher le câble RJ45 PoE en dernier

---

## Matériel nécessaire

| Composant | Référence | Prix ~ |
|---|---|---|
| Raspberry Pi 3B+ | Kubii | ~45€ |
| Waveshare PoE HAT (C) | Waveshare | ~20€ |
| Module relais 1 canal | Handsontec MDU1150 | ~3€ |
| MFRC522 NFC | AliExpress / Amazon | ~3€ |
| Débitmètre | DIGMESA 934-6550 | (déjà disponible) |
| Électrovanne | ASCO SCG283A012V | (déjà disponible) |
| Diode flyback | 1N4007 | ~0,10€ |
| Switch PoE | TP-Link TL-SG1005LP ou similaire | ~25€ |
| Câble RJ45 Cat5e | — | ~5€ |
| Fils Dupont femelle-femelle 20cm | — | ~2€ |
| Fil 0,5 mm² pour 12V | — | ~2€ |
| Gaine thermorétractable | — | ~1€ |
| **Total** | | **~106€** |
