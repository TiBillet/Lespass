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

export function initNfcReader(socket) {
  const nfc = new NFC()
  nfc.on('reader', reader => {
    const msg = { status: 'available' }
    socket.emit('nfcMessage', msg)

    reader.on('card', card => {
      const msg = { tagId: card.uid }
      socket.emit('nfcMessage', msg)
    })


    reader.on('error', err => {
      // console.log(`${reader.reader.name}  an error occurred`, err);
      const msg = { errorNfcReader: err }
      socket.emit('nfcMessage', msg)
    });

    reader.on('end', () => {
      // console.log(`${reader.reader.name}  device removed`)
      const msg = { status: 'disable' }
      socket.emit('nfcMessage', msg)
    });

  });

  nfc.on('error', err => {
    // console.log('an error occurred', err);
    const msg = { errorNfc: err }
    socket.emit('nfcMessage', msg)
  });
}

console.log('Module "acr122u-u9" loaded !');
