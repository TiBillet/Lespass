// si problême de droit
// sudo chown root:gpio /dev/gpiomem
// sudo chmod g+rw /dev/gpiomem
// sudo chmod g+rw /dev/gpiomem
// sudo usermod -a -G gpio $USER
// sudo usermod -a -G spi $USER
// sudo usermod -a -G netdev $USER
import { EventEmitter } from 'node:events'
import * as pkgRpiSoftspi from "rpi-softspi"
import { MFRC522 } from "./rc522/index.js"
// import { logs, memoryStat } from '../commun.js'

const SoftSPI = pkgRpiSoftspi.default
export const deviceEmitter = new EventEmitter()
const softSPI = new SoftSPI({
  clock: 23, // pin number of SCLK
  mosi: 19, // pin number of MOSI
  miso: 21, // pin number of MISO
  client: 24 // pin number of CS
})

// GPIO 24 can be used for buzzer bin (PIN 18), Reset pin is (PIN 22).
// const mfrc522 = new Mfrc522(softSPI).setResetPin(22).setBuzzerPin(18);
// const mfrc522 = new Mfrc522(softSPI)
const mfrc522 = new MFRC522(softSPI).setResetPin(22)

setInterval(function () {
  try {
    // console.log('---------------------------------------------')
    // console.log('mfrc522 - setInterval :')
    // memoryStat()

    //# reset card
    mfrc522.reset()
    deviceEmitter.emit('nfcReaderOn')

    // Scan for cards
    let response = mfrc522.findCard()
    if (!response.status) {
      // console.log("No Card");
      mfrc522.setResetPin(22)
      return
    }

    // Get the UID of the card
    response = mfrc522.getUid()
    if (!response.status) {
      // logs('--- attention ---> uidScanError')
      deviceEmitter.emit('nfcReader', 'uidScanError')
      mfrc522.setResetPin(22)
      return
    }

    // If we have the UID, continue
    const uid = response.data
    let resultat = ''
    for (let i = 0; i < 4; i++) {
      let lettre = uid[i].toString(16).toUpperCase()
      if (uid[i].toString(16).length === 1) {
        resultat += '0' + lettre
      } else {
        resultat += lettre
      }
    }

    // resultat
    // logs('nfcReaderTagId = ' + resultat)
    deviceEmitter.emit('nfcReaderTagId', resultat)

    // Stop
    mfrc522.stopCrypto()
    mfrc522.setResetPin(22)
  } catch (error) {
    console.log('-> mfrc522, setInterval,', error)
  }
}, 500)

