# Communiquer en Python avec la SUNMI 80mm Cloud Printer

> Documentation de référence : [developer.sunmi.com](https://developer.sunmi.com/docs/en-US/cdixeghjk491/xffaeghjk480)  
> Synthèse réalisée le 2026-03-24

---

## 🖨️ Modèle concerné

**SUNMI 80mm Kitchen Cloud Printer – Modèle NT31x**

| Paramètre | Valeur |
|-----------|--------|
| Modèle | NT31x (NT310, NT311, NT312, NT313…) |
| Firmware minimum | 2.7.0 |
| SUNMI APP minimum | 2.19.0 |
| Résolution | **576 dots par ligne** |
| Connectivité | WiFi, LAN (Ethernet), Bluetooth |

---

## 🔀 Deux modes de communication

### Mode 1 — Via le Cloud SUNMI (internet)

```
Votre serveur Python ──POST──▶ API SUNMI Cloud ──▶ Imprimante (WiFi/LAN)
https://openapi.sunmi.com
```

- Nécessite un compte partenaire SUNMI et des clés API (APPID / APPKEY)
- L'imprimante doit être connectée à Internet
- Recommandé pour la production (suivi des impressions, gestion multi-sites)

### Mode 2 — Via LAN HTTP (direct, sans internet)

```
Votre script Python ──POST──▶ http://<IP_imprimante>/cgi-bin/print.cgi
```

- Aucune authentification requise
- Machine et imprimante doivent être sur le **même sous-réseau**
- Idéal pour usage local (restaurant, boutique)
- Pour obtenir l'IP : double-clic sur le bouton de couplage → l'imprimante imprime sa page réseau

---

## 🌐 Mode Cloud SUNMI — Détails

### 1. Prérequis

1. Créer un compte partenaire sur <https://partner.sunmi.com>
2. Souscrire au service **Cloud Printer** → obtenir **APPID** et **APPKEY**
3. Configurer l'imprimante en WiFi via le SDK réseau Sunmi (ou l'app SUNMI)
4. Lier le **SN** (numéro de série) de l'imprimante à votre shop via l'API

### 2. Signature des requêtes (HMAC-SHA256)

Chaque requête POST vers l'API doit inclure ces headers :

| Header | Valeur |
|--------|--------|
| `Sunmi-Appid` | Votre APPID |
| `Sunmi-Timestamp` | Timestamp Unix 10 chiffres |
| `Sunmi-Nonce` | 6 chiffres aléatoires |
| `Sunmi-Sign` | `HMAC-SHA256(json_body + appid + timestamp + nonce, appkey)` |
| `Source` | `openapi` (valeur fixe) |
| `Content-Type` | `application/json` |

**Algorithme de signature :**
```
sign = HMAC-SHA256(
    message = json_body + APPID + timestamp + nonce,
    key     = APPKEY
)
```

### 3. Base URL

```
https://openapi.sunmi.com
```

> ⚠️ Utiliser **HTTPS uniquement** (TLS 1.2 ou 1.3, HTTP/1 uniquement — HTTP/2 non supporté).

### 4. Endpoints principaux

| Action | Méthode | Chemin |
|--------|---------|--------|
| Lier l'imprimante à un shop | POST | `/v2/printer/open/open/device/bindShop` |
| Délier l'imprimante | POST | `/v2/printer/open/open/device/unbindShop` |
| Vérifier statut en ligne | POST | `/v2/printer/open/open/device/onlineStatus` |
| **Envoyer une impression (Cloud to Cloud)** | POST | `/v2/printer/open/open/device/pushContent` |
| Notifier nouvelle commande (Device to Cloud) | POST | `/v2/printer/open/open/ticket/newTicketNotify` |
| Vider la file d'impression | POST | `/v2/printer/open/open/device/clearPrintJob` |
| Vérifier statut d'impression | POST | `/v2/printer/open/open/ticket/printStatus` |
| Diffuser un message vocal | POST | `/v2/printer/open/open/device/pushVoice` |

### 5. Corps de la requête d'impression — `pushContent`

```json
{
  "sn"        : "N31XXXXXXXXXX",
  "trade_no"  : "commande_unique_32chars",
  "content"   : "<ESC/POS bytes encodés en hexadécimal>",
  "count"     : 1,
  "order_type": 1,
  "media_text": "Nouvelle commande !"
}
```

- `content` = commandes ESC/POS converties en **bytes** puis en **string hexadécimale** (`bytes.hex()`)
- `trade_no` doit être **unique** par impression (un doublon est ignoré)
- `order_type` : 1=nouvelle commande, 2=annulation, 3=relance, 4=remboursement, 5=autre
- `media_text` : texte TTS (synthèse vocale) diffusé par le haut-parleur

### 6. Codes d'erreur API

| Code | Description |
|------|-------------|
| 10000 | Succès |
| 20000 | Paramètre manquant |
| 20001 | Requête expirée |
| 30000 | Authentification échouée (APPID invalide ou IP non autorisée) |
| 40000 | Signature invalide |
| 10071701 | Appareil inconnu (SN erroné) |
| 10071704 | SN n'appartient pas à ce canal |
| 10071705 | Order déjà envoyé (trade_no dupliqué) |

---

## 🐍 Code Python complet

### Dépendances

```bash
pip install requests pillow numpy
```

### Classe SunmiCloudPrinter

```python
# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import random
import requests
import time
from typing import Any, Dict, List, Tuple

# ── Constantes d'alignement ──────────────────────────────────────────────
ALIGN_LEFT   = 0
ALIGN_CENTER = 1
ALIGN_RIGHT  = 2

# ── Constantes de rendu d'image ──────────────────────────────────────────
DIFFUSE_DITHER   = 0
THRESHOLD_DITHER = 2


class SunmiCloudPrinter:
    """
    Classe principale pour générer des commandes ESC/POS et les envoyer
    à une imprimante SUNMI 80mm Cloud Printer (NT31x) via l'API Cloud.
    """

    APP_ID  = 'VOTRE_APPID'   # ← Remplacer
    APP_KEY = 'VOTRE_APPKEY'  # ← Remplacer

    def __init__(self, dots_per_line: int = 576) -> None:
        """
        :param dots_per_line: 576 pour 80mm, 384 pour 58mm
        """
        self._DOTS_PER_LINE = dots_per_line
        self._charHSize     = 1
        self._asciiCharWidth = 12
        self._cjkCharWidth   = 24
        self._orderData: bytes = b''

        random.seed()

    @property
    def orderData(self) -> bytes:
        return self._orderData

    def clear(self) -> None:
        """Vide le buffer de données ESC/POS."""
        self._orderData = b''

    # ── Signature & HTTP ──────────────────────────────────────────────────

    def generateSign(self, body: str, timestamp: str, nonce: str) -> str:
        msg = body + self.APP_ID + timestamp + nonce
        return hmac.new(
            key=self.APP_KEY.encode('utf-8'),
            msg=msg.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

    def httpPost(self, path: str, body: Dict[str, Any]) -> dict:
        url       = 'https://openapi.sunmi.com' + path
        timestamp = str(int(time.time()))
        nonce     = '{:06d}'.format(random.randint(0, 999999))
        body_str  = json.dumps(body, ensure_ascii=False)
        headers   = {
            'Sunmi-Appid'     : self.APP_ID,
            'Sunmi-Timestamp' : timestamp,
            'Sunmi-Nonce'     : nonce,
            'Sunmi-Sign'      : self.generateSign(body_str, timestamp, nonce),
            'Source'          : 'openapi',
            'Content-Type'    : 'application/json',
        }
        response = requests.post(
            url=url,
            data=body_str.encode('utf-8'),
            headers=headers
        )
        result = response.json()
        print(result)
        return result

    # ── Appels API ────────────────────────────────────────────────────────

    def bindShop(self, sn: str, shop_id: int) -> dict:
        return self.httpPost('/v2/printer/open/open/device/bindShop',
                             {'sn': sn, 'shop_id': shop_id})

    def unbindShop(self, sn: str, shop_id: int) -> dict:
        return self.httpPost('/v2/printer/open/open/device/unbindShop',
                             {'sn': sn, 'shop_id': shop_id})

    def onlineStatus(self, sn: str) -> dict:
        return self.httpPost('/v2/printer/open/open/device/onlineStatus',
                             {'sn': sn})

    def clearPrintJob(self, sn: str) -> dict:
        return self.httpPost('/v2/printer/open/open/device/clearPrintJob',
                             {'sn': sn})

    def printStatus(self, trade_no: str) -> dict:
        return self.httpPost('/v2/printer/open/open/ticket/printStatus',
                             {'trade_no': trade_no})

    def pushVoice(self, sn: str, content: str,
                  cycle: int = 1, interval: int = 2, expire_in: int = 300) -> dict:
        return self.httpPost('/v2/printer/open/open/device/pushVoice', {
            'sn'       : sn,
            'content'  : content,
            'cycle'    : cycle,
            'interval' : interval,
            'expire_in': expire_in,
        })

    def pushContent(self, trade_no: str, sn: str, count: int = 1,
                    order_type: int = 1, media_text: str = '', cycle: int = 1) -> dict:
        """Envoie le buffer ESC/POS à l'imprimante via le Cloud SUNMI."""
        return self.httpPost('/v2/printer/open/open/device/pushContent', {
            'trade_no'  : trade_no,
            'sn'        : sn,
            'order_type': order_type,
            'content'   : self._orderData.hex(),
            'count'     : count,
            'media_text': media_text,
            'cycle'     : cycle,
        })

    def newTicketNotify(self, sn: str) -> dict:
        """Mode Device to Cloud : notifie l'imprimante qu'une commande est disponible."""
        return self.httpPost('/v2/printer/open/open/ticket/newTicketNotify',
                             {'sn': sn})

    # ── ESC/POS — Texte & Formatage ───────────────────────────────────────

    def appendRawData(self, data: bytes) -> None:
        self._orderData += data

    def appendText(self, text: str) -> None:
        """Ajoute du texte UTF-8 au buffer."""
        self._orderData += text.encode('utf-8', errors='ignore')

    def lineFeed(self, n: int = 1) -> None:
        """[LF] Saut(s) de ligne."""
        if n > 0:
            self._orderData += b'\x0a' * n

    def restoreDefaultSettings(self) -> None:
        """[ESC @] Réinitialise l'imprimante."""
        self._charHSize = 1
        self._orderData += b'\x1b\x40'

    def restoreDefaultLineSpacing(self) -> None:
        """[ESC 2] Interligne par défaut."""
        self._orderData += b'\x1b\x32'

    def setLineSpacing(self, n: int) -> None:
        """[ESC 3 n] Interligne en dots (0–255)."""
        if 0 <= n <= 255:
            self._orderData += b'\x1b\x33' + n.to_bytes(1, 'little')

    def setAlignment(self, n: int) -> None:
        """[ESC a n] Alignement : 0=gauche, 1=centre, 2=droite."""
        if 0 <= n <= 2:
            self._orderData += b'\x1b\x61' + n.to_bytes(1, 'little')

    def setPrintModes(self, bold: bool = False,
                      double_h: bool = False, double_w: bool = False) -> None:
        """[ESC ! n] Modes : gras, double hauteur, double largeur."""
        n = (8 if bold else 0) | (16 if double_h else 0) | (32 if double_w else 0)
        self._charHSize = 2 if double_w else 1
        self._orderData += b'\x1b\x21' + n.to_bytes(1, 'little')

    def setCharacterSize(self, h: int = 1, w: int = 1) -> None:
        """[GS ! n] Taille du caractère : h et w de 1 à 8."""
        n = 0
        if 1 <= h <= 8: n |= (h - 1)
        if 1 <= w <= 8: n |= (w - 1) << 4
        self._charHSize = w
        self._orderData += b'\x1d\x21' + n.to_bytes(1, 'little')

    def setUnderlineMode(self, n: int) -> None:
        """[ESC - n] Souligné : 0=off, 1=1pt, 2=2pt."""
        if 0 <= n <= 2:
            self._orderData += b'\x1b\x2d' + n.to_bytes(1, 'little')

    def setBlackWhiteReverseMode(self, enabled: bool) -> None:
        """[GS B n] Inversion noir/blanc."""
        self._orderData += b'\x1d\x42\x01' if enabled else b'\x1d\x42\x00'

    def setAbsolutePrintPosition(self, n: int) -> None:
        """[ESC $ n] Position absolue (dots depuis le bord gauche)."""
        if 0 <= n <= 65535:
            self._orderData += b'\x1b\x24' + n.to_bytes(2, 'little')

    def cutPaper(self, full_cut: bool = False) -> None:
        """[GS V] Coupe papier : full_cut=True → coupe totale, False → partielle."""
        self._orderData += b'\x1d\x56\x30' if full_cut else b'\x1d\x56\x31'

    # ── ESC/POS — Modes spéciaux SUNMI ───────────────────────────────────

    def setUtf8Mode(self, enabled: bool = True) -> None:
        """Active/désactive l'encodage UTF-8 (nécessaire pour accents, etc.)."""
        n = 1 if enabled else 0
        self._orderData += b'\x1d\x28\x45\x03\x00\x06\x03' + n.to_bytes(1, 'little')

    def setCjkEncoding(self, n: int) -> None:
        """Encodage CJK : 0=GB18030, 1=BIG5, 11=Shift_JIS, 12=JIS0208, 128=désactivé."""
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x03\x00\x06\x01' + n.to_bytes(1, 'little')

    def setPrintDensity(self, n: int) -> None:
        """Densité d'impression en % (70–130, défaut=100)."""
        if 70 <= n <= 130:
            self._orderData += b'\x1d\x28\x45\x02\x00\x07' + n.to_bytes(1, 'little')

    def setPrintSpeed(self, n: int) -> None:
        """Vitesse d'impression (0–250, 255=défaut)."""
        if 0 <= n <= 255:
            self._orderData += b'\x1d\x28\x45\x02\x00\x08' + n.to_bytes(1, 'little')

    def cutPaperPostponed(self, full_cut: bool = False, n: int = 0) -> None:
        """Coupe différée après (76+n) dots supplémentaires. Utile pour coupes multiples."""
        if 0 <= n <= 255:
            cmd = b'\x1d\x56\x61' if full_cut else b'\x1d\x56\x62'
            self._orderData += cmd + n.to_bytes(1, 'little')

    # ── ESC/POS — Code-barres ─────────────────────────────────────────────

    def appendBarcode(self, hri_pos: int, height: int, module_size: int,
                      barcode_type: int, text: str) -> None:
        """
        Imprime un code-barres.
        hri_pos : 0=aucun, 1=au-dessus, 2=en-dessous, 3=les deux
        barcode_type : 65=UPC-A, 67=EAN-13, 68=EAN-8, 69=CODE39, 72=CODE93, 73=CODE128
        """
        if not text: return
        data = text.encode('utf-8', errors='ignore')[:255]
        height = max(1, min(255, height))
        module_size = max(1, min(6, module_size))
        self._orderData += b'\x1d\x48' + (hri_pos & 3).to_bytes(1, 'little')
        self._orderData += b'\x1d\x66\x00'
        self._orderData += b'\x1d\x68' + height.to_bytes(1, 'little')
        self._orderData += b'\x1d\x77' + module_size.to_bytes(1, 'little')
        self._orderData += b'\x1d\x6b' + barcode_type.to_bytes(1, 'little')
        self._orderData += len(data).to_bytes(1, 'little') + data

    # ── ESC/POS — QR Code ─────────────────────────────────────────────────

    def appendQRcode(self, module_size: int, ec_level: int, text: str) -> None:
        """
        Imprime un QR code.
        module_size : 1–16 (taille d'un module en dots, défaut conseillé : 4–6)
        ec_level    : 0=L(7%), 1=M(15%), 2=Q(25%), 3=H(30%)
        """
        content = text.encode('utf-8', errors='ignore')
        if not content: return
        tlen = min(len(content), 65535)
        module_size = max(1, min(16, module_size))
        ec = max(0, min(3, ec_level)) + 48
        self._orderData += b'\x1d\x28\x6b\x04\x00\x31\x41\x00\x00'
        self._orderData += b'\x1d\x28\x6b\x03\x00\x31\x43' + module_size.to_bytes(1, 'little')
        self._orderData += b'\x1d\x28\x6b\x03\x00\x31\x45' + ec.to_bytes(1, 'little')
        self._orderData += b'\x1d\x28\x6b' + (tlen + 3).to_bytes(2, 'little') + b'\x31\x50\x30'
        self._orderData += content
        self._orderData += b'\x1d\x28\x6b\x03\x00\x31\x51\x30'


# ── Impression via LAN HTTP (sans cloud) ──────────────────────────────────

def print_via_lan(printer_ip: str, escpos_bytes: bytes) -> int:
    """
    Envoie des commandes ESC/POS directement à l'imprimante en LAN.
    :param printer_ip: Adresse IP de l'imprimante (ex: '192.168.1.100')
    :param escpos_bytes: Commandes ESC/POS en bytes
    :return: Code HTTP (200 = succès)
    """
    url = f'http://{printer_ip}/cgi-bin/print.cgi'
    response = requests.post(url, data=escpos_bytes.hex())
    print(f'Status: {response.status_code}')
    return response.status_code
```

---

## 📋 Exemples d'utilisation

### Exemple 1 — Ticket de caisse (mode Cloud)

```python
import time

sn = 'N31XXXXXXXXXX'   # ← SN imprimé sur la page réseau de votre imprimante
p  = SunmiCloudPrinter(dots_per_line=576)

# Activer UTF-8 (pour accents, symboles €, etc.)
p.setUtf8Mode(True)

# En-tête centré, grand
p.setAlignment(ALIGN_CENTER)
p.setPrintModes(bold=True, double_h=True)
p.appendText('MA BOUTIQUE\n')
p.setPrintModes()
p.appendText('123 Rue de la Paix, Paris\n')
p.appendText('--------------------------------\n')

# Lignes de produit à gauche
p.setAlignment(ALIGN_LEFT)
p.appendText('Café expresso         x2    4.00€\n')
p.appendText('Croissant beurre      x1    1.50€\n')
p.appendText('Jus d\'orange         x1    3.00€\n')
p.appendText('--------------------------------\n')

# Total en gras
p.setPrintModes(bold=True)
p.appendText('TOTAL                       8.50€\n')
p.setPrintModes()

# QR code de fidélité
p.setAlignment(ALIGN_CENTER)
p.appendQRcode(module_size=5, ec_level=1, text='https://maboutique.fr/fidelite')
p.lineFeed(3)

# Coupe partielle
p.cutPaper(full_cut=False)

# Envoi via Cloud SUNMI
p.pushContent(
    trade_no=f'{sn}_{int(time.time())}',  # ID unique de commande
    sn=sn,
    count=1,
    media_text='Nouvelle commande !'       # Message vocal facultatif
)
```

### Exemple 2 — Impression LAN directe (sans compte SUNMI)

```python
PRINTER_IP = '192.168.1.100'  # ← IP de votre imprimante

p = SunmiCloudPrinter(dots_per_line=576)
p.setUtf8Mode(True)
p.restoreDefaultSettings()
p.setAlignment(ALIGN_CENTER)
p.setPrintModes(bold=True, double_h=True)
p.appendText('TEST IMPRESSION LAN\n')
p.setPrintModes()
p.setAlignment(ALIGN_LEFT)
p.appendText('Connexion directe OK\n')
p.lineFeed(2)
p.cutPaper()

# Envoi direct sans cloud
print_via_lan(PRINTER_IP, p.orderData)
```

### Exemple 3 — Code-barres + QR code

```python
p = SunmiCloudPrinter(576)
p.setUtf8Mode(True)
p.setAlignment(ALIGN_CENTER)

# Code-barres CODE128
p.appendBarcode(
    hri_pos     = 2,          # texte en-dessous
    height      = 80,         # hauteur en dots
    module_size = 3,          # largeur d'un module
    barcode_type= 73,         # 73 = CODE128
    text        = 'ABC-12345'
)
p.lineFeed(2)

# QR code
p.appendQRcode(
    module_size = 6,
    ec_level    = 1,          # M = 15%
    text        = 'https://example.com'
)
p.lineFeed(3)
p.cutPaper()
```

### Exemple 4 — Vérifier le statut en ligne

```python
p = SunmiCloudPrinter()
result = p.onlineStatus('N31XXXXXXXXXX')
# result = {'code': 1, 'msg': 'success', 'data': {'list': [{'sn': '...', 'is_online': 1}], ...}}
if result['code'] == 1:
    status = result['data']['list'][0]['is_online']
    print('En ligne' if status == 1 else 'Hors ligne')
```

---

## 📐 Référence rapide — Commandes ESC/POS

| Commande | Bytes (hex) | Description |
|----------|-------------|-------------|
| Reset | `1B 40` | Réinitialise l'imprimante |
| LF | `0A` | Saut de ligne |
| Alignement gauche | `1B 61 00` | |
| Alignement centre | `1B 61 01` | |
| Alignement droite | `1B 61 02` | |
| Gras ON | `1B 45 01` | |
| Gras OFF | `1B 45 00` | |
| Double hauteur+largeur | `1B 21 30` | |
| Mode normal | `1B 21 00` | |
| Souligné 1pt | `1B 2D 01` | |
| Souligné OFF | `1B 2D 00` | |
| Inversion NB ON | `1D 42 01` | |
| Coupe partielle | `1D 56 31` | |
| Coupe totale | `1D 56 30` | |
| UTF-8 ON | `1D 28 45 03 00 06 03 01` | |
| Image raster | `1D 76 30 00 ...` | GS v 0 |
| QR code | `1D 28 6B ...` | GS ( k |

---

## 🗂️ Structure des deux modes d'intégration

### Cloud to Cloud (direct push)
```
1. S'inscrire sur partner.sunmi.com → obtenir APPID/APPKEY
2. Lier le SN de l'imprimante à votre shop_id : POST /device/bindShop
3. Construire les commandes ESC/POS → bytes → hex string
4. Appeler POST /device/pushContent avec le content en hex
5. (Optionnel) Vérifier via POST /ticket/printStatus
```

### Device to Cloud (callback)
```
1. Même inscription + liaison
2. Appeler POST /ticket/newTicketNotify → notifie l'imprimante
3. L'imprimante rappelle VOTRE API pour récupérer les données
4. Vous répondez avec les bytes ESC/POS (votre serveur doit être accessible)
```

---

## ⚙️ Notes importantes

- Le champ `trade_no` est l'identifiant unique de l'impression. Si vous renvoyez le même `trade_no`, l'impression est ignorée (déduplication). Utilisez un timestamp ou UUID pour garantir l'unicité.
- Le `content` envoyé à l'API doit être en **hexadécimal minuscule** (résultat de `bytes.hex()`).
- Pour afficher correctement les accents et symboles (€, ÉÀÜ…), **activer UTF-8** avec `setUtf8Mode(True)` au début du buffer.
- En mode LAN, l'imprimante doit être sur le **même sous-réseau IP** que votre machine. En cas d'échec, vérifiez les règles de pare-feu et le VLAN.
- La coupe papier différée (`cutPaperPostponed`) est utile pour imprimer plusieurs sections avec des coupes intermédiaires sans ajouter de lignes blanches.
- Après envoi d'une commande de statut, attendre **au moins 600 ms** avant d'envoyer la suivante.

---

*Sources : developer.sunmi.com — Cloud Printer V2 Documentation (2026)*
