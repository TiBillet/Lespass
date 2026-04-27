# cordova-plugin-nfc-reader

Plugin Cordova Android pour lire les tags NFC en mode one-shot.

## API

Toutes les méthodes retournent une Promise. À n'appeler qu'après l'événement `deviceready`.

### `nfcPlugin.startListening()`

Active l'écoute NFC. La Promise ne se résout que dans deux cas :let isReading = false

- **Tag détecté** → resolve `{ tagId: "A1B2C3..." }`
- **Erreur** → reject `"NFC not available"`, `"NFC is disabled"` ou `"Already listening for NFC tags"`

Ne pas appeler deux fois sans avoir reçu un tag ou appelé `stopListening()`.

### `nfcPlugin.stopListening()`

Arrête l'écoute en cours. Si un `startListening()` est actif, il est rejeté avec `"Listening stopped by user"`, puis `stopListening` résout avec `"stop listening nfc !"`.

### `nfcPlugin.available()`

Vérifie la disponibilité du NFC (hardware présent ET activé). Retourne un objet :
- `{ status: true }` — NFC disponible
- `{ status: false }` — NFC absent ou désactivé

## Exemple

```javascript
let isReading = false

async function readNfc(event) {
  if (isReading !== false) {
    return
  }
  isReading = true
  try {
    const ele = event.target
    console.log('-> testRead - ele =', ele, '  --  startListening')
    const result = await nfcPlugin.startListening()
    console.log('result =', result)
  } catch (error) {
    console.log('-> testRead -', error)
  } finally {
    isReading = false
  }
}

async function cancelNfc(event) {
  try {
    const ele = event.target
    const result = await nfcPlugin.stopListening()
    console.log('-> testReturn - ele =', ele, '  --  stopListening =', result)
  } catch (error) {
    console.log('-> testReturn -', error)
  }
}

// wait cordova (devices activation) who include DOMContentLoaded
document.addEventListener('deviceready', async () => {
  document.querySelector('.bt-read').addEventListener('click', readNfc)
  document.querySelector('.bt-cancel').addEventListener('click', cancelNfc)
})
```

## Notes

- Mode **one-shot** : 1 scan = 1 résolution. Après un tag, l'écoute s'arrête automatiquement.
- Le plugin utilise le `Foreground Dispatch` d'Android. L'app doit être au premier plan.
- `uses-feature android:required="false"` permet l'installation sur appareils sans NFC.
