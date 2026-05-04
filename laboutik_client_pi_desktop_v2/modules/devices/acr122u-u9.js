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
let currentSocket = null

export function initNfcReader(socket) {
  currentSocket = socket

  if (nfcInstance !== null) {
    console.log('NFC déjà initialisé, socket mis à jour')
    return
  }

  function emit(msg) {
    if (currentSocket) currentSocket.emit('nfcMessage', msg)
  }

  nfcInstance = new NFC()

  nfcInstance.on('reader', reader => {

    emit({ status: 'available' })

    reader.on('card', card => {
      emit({ tagId: card.uid })
    })


    reader.on('error', err => {
      // console.log(`${reader.reader.name}  an error occurred`, err);
      emit({ errorNfcReader: err })
    })

    reader.on('end', () => {
      // console.log(`${reader.reader.name}  device removed`)
      emit({ status: 'disable' })
    })

  });

  nfcInstance.on('error', err => {
    // console.log('an error occurred', err);
    emit({ errorNfc: err })
  })
}

console.log('Module "acr122u-u9" loaded !');
