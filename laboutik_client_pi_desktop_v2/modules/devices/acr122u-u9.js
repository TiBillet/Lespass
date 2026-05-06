'use strict'

// pour "configurer" le lecteur nfc
// ouvrir le fichier:  sudo nano /usr/lib/pcsc/drivers/ifd-ccid.bundle/Contents/Info.plist (pour pi)
// localiser la ligne  <key>ifdDriverOptions</key>,
// la ligne suivante vaux <string>0x0000</string>,
// modifier la <string>0x0001</string>,
// sauvegarder le fichier et redémarer pcscd(sudo service pcscd restart)
// même action pour le fichier sudo nano /usr/lib/pcsc/drivers/ifd-acsccid.bundle/Contents/Info.plist (pour desktop)

// source : https://github.com/pokusew/nfc-pcsc#flow-of-handling-tags
import { NFC } from 'nfc-pcsc'

let nfcInstance = null
let currentReader = null
let nfcStatus = 'disable'  // 'available' | 'disable' | 'error'

// get status
export function getStatus(socket) {
  socket.emit('nfcMessage', { status: nfcStatus })
  // console.log("-> nfc status:", nfcStatus)
}

// stop listening
export function stopListening() {
  return new Promise((resolve) => {
    try {
      if (currentReader && typeof currentReader.close === 'function') {
        currentReader.close()
      }
    } catch (err) {
      console.error('Erreur fermeture lecteur:', err.message)
    } finally {
      currentReader = null
    }

    try {
      if (nfcInstance && typeof nfcInstance.close === 'function') {
        nfcInstance.close()
      }
    } catch (err) {
      console.error('Erreur fermeture NFC:', err.message)
    } finally {
      nfcInstance = null
    }

    nfcStatus = 'disable'
    // console.log("-> nfc stop listening")
    resolve()
  })
}

// start listening
export async function startListening(socket, data) {
  await stopListening()
  function emit(msg) {
    if (socket) socket.emit('nfcMessage', msg)
  }

  console.log("-> nfc start listening")
  nfcInstance = new NFC()

  nfcInstance.on('reader', reader => {
    currentReader = reader
    // status
    nfcStatus = 'available'

    // get status
    if (data === "nfcReaderStatus") {
      nfcStatus = 'available'
      emit({ status: nfcStatus })
      stopListening()
    }

    // get read card
    reader.on('card', card => {
      console.log('nfc - tagId =', card.uid, '  --  data =', data)
      emit({ tagId: card.uid, data })
      stopListening()
    })

    // status
    reader.on('error', err => {
      nfcStatus = 'error'
    })

    // status
    reader.on('end', () => {
      currentReader = null
      nfcStatus = 'disable'
    })

  });

  nfcInstance.on('error', err => {
    nfcStatus = 'error'
  })
}

console.log('Module "acr122u-u9" loaded !');
