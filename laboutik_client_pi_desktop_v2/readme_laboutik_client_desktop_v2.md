# installer les dépendences desktop
```bash
sudo ./install_desktop/install_conf_blacklist_and_nfc_usb
npm install socket.io
npm install nfc-pcsc
```

# Créer votre fichier de conf
- A la racine du projet, créer env.js et modifier le :   
  . type_app: 'desktop',
  . server_pin_code: "http://tibillet.localhost", // votre serveur de pin_code
  . ipPrinters: [] // ['192.168.1.25', '192.168.1.26']

```bash
cp ./env-example.js ./env.js
```

# exemples de codes

## impression
```js
if (testPrinter()) {
  const text =
    "TEST IMPRESSION\n" +
    "----------------\n" +
    "Bonjour monde !\n"
  print(env.ipPrinters[0], text)
}
```