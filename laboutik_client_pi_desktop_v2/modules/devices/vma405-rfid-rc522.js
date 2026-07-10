// si problême de droit
// sudo chown root:gpio /dev/gpiomem
// sudo chmod g+rw /dev/gpiomem
// sudo chmod g+rw /dev/gpiomem
// sudo usermod -a -G gpio $USER
// sudo usermod -a -G spi $USER
// sudo usermod -a -G netdev $USER
//
// CONTRAT ATTENDU PAR nfcServer.js
// / API contract expected by nfcServer.js
//
// nfcServer.js:37 déstructure { startListening, stopListening, getStatus } du
// module de device. Le driver desktop (acr122u-u9.js) expose ces trois
// fonctions ; ce driver ne les exposait pas, ce qui cassait le mode
// `type_app: 'pi'` (TypeError: nfc.startListening is not a function).
//
// Le `data` reçu dans startListening(socket, data) DOIT être renvoyé avec le
// tagId : le front lit `retour.data?.uuidConnexion` et rejette toute lecture
// dont l'uuidConnexion ne correspond pas à celui qu'il a envoyé.
//
// / nfcServer.js destructures { startListening, stopListening, getStatus }.
// The `data` passed to startListening must be echoed back with the tagId:
// the front-end checks `retour.data?.uuidConnexion` and drops mismatches.

import * as pkgRpiSoftspi from "rpi-softspi"
import { MFRC522 } from "./rc522/index.js"
// import { logs, memoryStat } from '../commun.js'

const SoftSPI = pkgRpiSoftspi.default

let mfrc522 = null
let currentSocket = null

// `data` de la demande de lecture en cours, à renvoyer avec le tagId.
// / Payload of the current read request, echoed back with the tagId.
let currentData = undefined

// Identifiant du setInterval de polling, indispensable pour pouvoir l'arrêter.
// / Polling interval id, required to be able to stop it.
let pollingTimer = null

// 'available' | 'disable' | 'error' — même vocabulaire que acr122u-u9.js
// / same status vocabulary as acr122u-u9.js
let nfcStatus = 'disable'

const softSPI = new SoftSPI({
  clock: 23, // pin number of SCLK
  mosi: 19, // pin number of MOSI
  miso: 21, // pin number of MISO
  client: 24 // pin number of CS
})

// Émet vers le socket courant, s'il y en a un.
// / Emit to the current socket, if any.
function emit(msg) {
  if (currentSocket) currentSocket.emit('nfcMessage', msg)
}

// Initialise le lecteur une seule fois. Retourne false si le matériel répond pas.
// / Initialise the reader once. Returns false when the hardware is unreachable.
function initReader() {
  if (mfrc522 !== null) {
    return true
  }

  try {
    // GPIO 24 can be used for buzzer bin (PIN 18), Reset pin is (PIN 22).
    mfrc522 = new MFRC522(softSPI).setResetPin(22)
    nfcStatus = 'available'
    console.log('Module "vma405-rfid-rc522" initialisé !')
    return true
  } catch (error) {
    console.log('-> initReader,', error)
    nfcStatus = 'error'
    emit({ errorNfc: error.message })
    return false
  }
}

// get status
export function getStatus(socket) {
  if (socket) socket.emit('nfcMessage', { status: nfcStatus })
}

// stop listening
export function stopListening() {
  if (pollingTimer !== null) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

// start listening
// Appelé au démarrage de nfcServer.js avec socket = null (aucun client connecté),
// puis à chaque évènement 'nfcStartListening' avec le socket et le data du front.
// / Called at nfcServer.js startup with socket = null, then on each
// 'nfcStartListening' event with the client socket and the front-end payload.
export function startListening(socket, data) {
  // Une demande de lecture annule la précédente.
  // / A new read request cancels the previous one.
  stopListening()

  currentSocket = socket
  currentData = data

  if (!initReader()) {
    return
  }

  emit({ status: nfcStatus })

  // Demande de statut seule : pas de lecture de carte.
  // / Status probe only: no card read.
  if (data === "nfcReaderStatus") {
    return
  }

  // Sans socket, personne n'écoute : inutile de scanner.
  // / No socket, nobody is listening: skip the scan.
  if (!currentSocket) {
    return
  }

  startPolling()
}

// Compatibilité : ancien point d'entrée, utilisé avant le refactor de nfcServer.js.
// / Backward compatibility with the pre-refactor entry point.
export function initNfcReader(socket) {
  startListening(socket)
}

function startPolling() {
  pollingTimer = setInterval(function () {
    try {
      //# reset card
      mfrc522.reset()
      emit({ status: nfcStatus })

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

      // Le data de la demande accompagne le tagId (vérif uuidConnexion côté front).
      // / The request payload travels with the tagId (front checks uuidConnexion).
      emit({ tagId: resultat, data: currentData })

      // Stop
      mfrc522.stopCrypto()
      mfrc522.setResetPin(22)

      // Lecture unique, comme acr122u-u9.js : on arrête le polling après un tag.
      // / Single read, like acr122u-u9.js: stop polling once a tag is read.
      stopListening()
    } catch (error) {
      console.log('-> mfrc522, setInterval,', error)
      emit({ errorNfcReader: error.message })
    }
  }, 500)
}

console.log('Module "vma405-rfid-rc522" loaded !')
