# Installation Desktop - LaBoutik Client v2

## Prérequis matériels

- Ordinateur sous Linux (Ubuntu/Debian recommandé)
- Lecteur NFC USB ACR122U-U9 (PC/SC)
- Imprimante thermique réseau (optionnel)

## Fichiers d'installation

Tous les scripts et fichiers de configuration pour le desktop se trouvent dans le dossier `install_desktop/` :

```
install_desktop/
├── install_conf_blacklist_and_nfc_usb  # Script d'installation système (étape 1)
├── package.json                        # Dépendances Node.js pour desktop
└── src/
    └── (fichiers de configuration)
```

---

## Étape 1 : Installation du système et des dépendances système

Cette étape installe Node.js, configure le système et prépare le hardware NFC USB.

### Installation des dépendances système

```bash
cd install_desktop
chmod +x install_conf_blacklist_and_nfc_usb
sudo ./install_conf_blacklist_and_nfc_usb
```

### Ce que fait le script

1. **Installation de Node.js et npm**
   - Ajoute le repository NodeSource
   - Installe Node.js 24.x (inclut npm)
   - Installe les outils de compilation (gcc, g++, make, node-gyp)

2. **Configuration du lecteur NFC USB**
   - Installe `libpcsclite1`, `libpcsclite-dev`, `pcscd`, `pcsc-tools`
   - Blacklist les modules noyau `nfc` et `pn533` (évitent les conflits avec pcscd)
   - Redémarre le service `pcscd`

3. **Vérification du lecteur**
   ```bash
   pcsc_scan
   ```
   Doit détecter votre lecteur ACR122U.

### Vérification après installation

```bash
node --version   # Doit afficher v24.x.x
npm --version    # Doit afficher 10.x.x
pcsc_scan        # Doit détecter le lecteur NFC
```

---

## Étape 2 : Configuration du hardware NFC

### Brochage ACR122U-U9

Le lecteur ACR122U se connecte directement en USB. Aucun câblage supplémentaire n'est nécessaire.

| Connexion | Description |
|-----------|-------------|
| USB | Connecteur USB-A ou USB-C (avec adaptateur) |
| LED | Indicateur d'état (rouge/vert) |
| Buzzer | Bip à la détection d'une carte |

### Vérification du service PC/SC

```bash
# Vérifier que pcscd tourne
sudo systemctl status pcscd

# Redémarrer si nécessaire
sudo systemctl restart pcscd

# Lister les lecteurs détectés
pcsc_scan
```

### Test du lecteur

```bash
# Scanner les cartes présentes
pcsc_scan
# Passez une carte NFC devant le lecteur
# L'UID doit s'afficher dans le terminal
```

---

## Étape 3 : Installation des modules Node.js de l'application

Cette étape installe les dépendances npm spécifiques au desktop.

### Préparation

Le script `install-modules-nodejs` se trouve à la racine du projet :

```bash
cd /chemin/vers/laboutik_client_pi_desktop_v2
chmod +x install-modules-nodejs
```

### Installation pour Desktop

```bash
./install-modules-nodejs desktop
```

**Ce que fait le script :**
1. Supprime `node_modules/` et `package-lock.json`
2. Copie `install_desktop/package.json` à la racine
3. Configure `env.js` avec `type_app: 'desktop'`
4. Lance `npm install`

### Modules installés pour le Desktop

| Module | Utilisation |
|--------|-------------|
| `socket.io` | Communication temps réel avec le front-end |
| `nfc-pcsc` | Communication avec le lecteur ACR122U via PC/SC |

### Vérification

```bash
ls node_modules/   # Vérifier que nfc-pcsc et socket.io sont présents
```

---

## Étape 4 : Configuration de l'application

### Créer le fichier de configuration

```bash
cp ./env-example.js ./env.js
```

### Modifier env.js

```javascript
export const env = {
  type_app: 'desktop',           // Ne pas modifier
  server_pin_code: "https://votre-serveur.tld",  // URL de votre serveur
  servers: [],
  currentServer: '',
  PORT: 3000,
  HOST: 'localhost',
  logLevel: 10,
  ipPrinters: []                 // IPs des imprimantes thermiques
}
```

**Paramètres importants :**

| Paramètre | Description | Exemple |
|-----------|-------------|---------|
| `server_pin_code` | URL du serveur de codes PIN | `"https://discovery.tibillet.coop"` |
| `ipPrinters` | Tableau des IPs des imprimantes | `['192.168.1.25', '192.168.1.26']` |
| `PORT` | Port du serveur local | `3000` |
| `HOST` | Adresse d'écoute | `'localhost'` ou `'0.0.0.0'` |

---

## Étape 5 : Lancement de l'application

### Lancement manuel

```bash
node nfcServer.js
```

### Lancement avec un gestionnaire de processus (recommandé)

**Avec PM2 :**
```bash
# Installer PM2
sudo npm install -g pm2

# Lancer l'application
pm2 start nfcServer.js --name laboutik

# Sauvegarder la configuration
pm2 save
pm2 startup
```

**Avec systemd :**
Créer le fichier `/etc/systemd/system/laboutik.service` :
```ini
[Unit]
Description=LaBoutik Client Desktop
After=network.target

[Service]
Type=simple
User=%I
WorkingDirectory=/chemin/vers/laboutik_client_pi_desktop_v2
ExecStart=/usr/bin/node nfcServer.js
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable laboutik
sudo systemctl start laboutik
```

---

## Débogage

### Logs de l'application

```bash
# Logs en temps réel
tail -f /var/log/syslog | grep node

# Si utilisé avec PM2
pm2 logs laboutik
```

### Test du lecteur NFC

```bash
# Utiliser pcsc_scan pour vérifier que le lecteur fonctionne
pcsc_scan
```

### Test de l'impression

```javascript
// Dans le code ou la console Node.js
import { testPrinter, print } from './modules/devices/thermalPrinterTcp.js'
import { env } from './env.js'

if (testPrinter()) {
  const text =
    "TEST IMPRESSION\n" +
    "----------------\n" +
    "Bonjour monde !\n"
  print(env.ipPrinters[0], text)
}
```

---

## Récapitulatif des étapes

| Étape | Action | Commande |
|-------|--------|----------|
| 1 | Installation système | `sudo ./install_desktop/install_conf_blacklist_and_nfc_usb` |
| 2 | Vérifier hardware | `pcsc_scan` |
| 3 | Installer modules Node.js | `./install-modules-nodejs desktop` |
| 4 | Configurer env.js | `cp env-example.js env.js` + édition |
| 5 | Lancer l'application | `node nfcServer.js` ou `pm2 start nfcServer.js` |

---

## Dépannage

### Le lecteur n'est pas détecté

```bash
# Vérifier que pcscd tourne
sudo systemctl status pcscd

# Vérifier les logs
sudo journalctl -u pcscd -f

# Recharger les règles udev
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Erreur de compilation nfc-pcsc

```bash
# Réinstaller les dépendances de compilation
sudo apt-get install --reinstall libpcsclite-dev build-essential

# Nettoyer et réinstaller
rm -rf node_modules package-lock.json
./install-modules-nodejs desktop
```

### Permission denied sur le lecteur

```bash
# Ajouter l'utilisateur au groupe pcscd
sudo usermod -a -G pcscd $USER
# Déconnexion/reconnexion nécessaire
```

### Conflit avec le module noyau

Si vous voyez des erreurs liées à `nfc` ou `pn533` :
```bash
# Vérifier que les modules sont blacklistés
cat /etc/modprobe.d/blacklist-nfc-usb.conf

# Si absent, recréer le fichier
sudo ./install_desktop/install_conf_blacklist_and_nfc_usb
```
