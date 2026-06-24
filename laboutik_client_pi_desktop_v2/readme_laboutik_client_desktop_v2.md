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
└── package.json                        # Dépendances Node.js pour desktop
```


## Installation du driver
```bash
cd install_desktop
chmod +x install_conf_blacklist_and_nfc_usb
sudo ./install_conf_blacklist_and_nfc_usb
```
Redémarrer l'ordinateur pour la prise en compte par le système


## Vérification du lecteur
```bash
pcsc_scan
```
Doit détecter votre lecteur et lire des cartes nfc.

## Install nodejs
### Installer le gestionnaire de version de nodejs
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh | bash
# test
nvm --version
```

### Installer nodej
```bash
nvm install --lts
# test
node -v
npm -v
```


### modules nodejs de l'app
```bash
chmod +x install_conf_blacklist_and_nfc_usb
install-modules-nodejs desktop
```

## js
```bash
# nfcAvailable = nfc listening
socket.emit('nfcAvailable')
# start listening = after card reading send 'nfcMessage' with object {tagId, data}
socket.emit('nfcStartListening',{uuid: 'shhshjhjhshsh255'})
# stop current listening
socket.emit('nfcStopListening')
```
