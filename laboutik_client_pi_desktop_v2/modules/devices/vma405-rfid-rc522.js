// si problême de droit
// sudo chown root:gpio /dev/gpiomem
// sudo chmod g+rw /dev/gpiomem
// sudo chmod g+rw /dev/gpiomem
// sudo usermod -a -G gpio $USER
// sudo usermod -a -G spi $USER
// sudo usermod -a -G netdev $USER
import * as pkgRpiSoftspi from "rpi-softspi"
import { MFRC522 } from "./rc522/index.js"
// import { logs, memoryStat } from '../commun.js'

const SoftSPI = pkgRpiSoftspi.default

let mfrc522 = null
let currentSocket = null

const softSPI = new SoftSPI({
  clock: 23, // pin number of SCLK
  mosi: 19, // pin number of MOSI
  miso: 21, // pin number of MISO
  client: 24 // pin number of CS
})

export function initNfcReader(socket) {
  currentSocket = socket

  if (mfrc522 !== null) {
    console.log('NFC déjà initialisé, socket mis à jour')
    return
  }

  function emit(msg) {
    if (currentSocket) currentSocket.emit('nfcMessage', msg)
  }

  try {
    // GPIO 24 can be used for buzzer bin (PIN 18), Reset pin is (PIN 22).
    // const mfrc522 = new Mfrc522(softSPI).setResetPin(22).setBuzzerPin(18);
    // const mfrc522 = new Mfrc522(softSPI)
    mfrc522 = new MFRC522(softSPI).setResetPin(22)
    emit({ status: 'available' })
    console.log('Module "vma405-rfid-rc522" initialisé !')

    // Démarrer le polling
    startPolling(emit)
  } catch (error) {
    console.log('-> initNfcReader,', error)
    emit({ errorNfc: error.message })
  }
}

function startPolling(emit) {
  setInterval(function () {
    try {
      // console.log('---------------------------------------------')
      // console.log('mfrc522 - setInterval :')
      // memoryStat()

      //# reset card
      mfrc522.reset()
      emit({ status: 'available' })

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
        emit({ errorNfcReader: 'uidScanError' })
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
      emit({ tagId: resultat })

      // Stop
      mfrc522.stopCrypto()
      mfrc522.setResetPin(22)
    } catch (error) {
      console.log('-> mfrc522, setInterval,', error)
      emit({ errorNfcReader: error.message })
    }
  }, 500)
}

console.log('Module "vma405-rfid-rc522" loaded !')
