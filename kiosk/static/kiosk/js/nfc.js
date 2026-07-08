// https://github.com/nerdy-harry/phonegap-nfc-api31?tab=readme-ov-file#nfcshowsettings

let NfcReader = class {
  constructor() {
    this.modeNfc = ''
    this.uuidConnexion = null
    this.socket = null
    this.socketPort = 3000
    this.intervalIDVerifApiCordova = null
    this.cordovaLecture = false
    this.simuData = [
      { name: 'primary', tagId: window?.DEMO?.demoTagIdCm },
      { name: 'client1', tagId: window?.DEMO?.demoTagIdClient1 },
      { name: 'client2', tagId: window?.DEMO?.demoTagIdClient2 },
      { name: 'client3', tagId: window?.DEMO?.demoTagIdClient3 },
      { name: 'unknown', tagId: 'XXXXXXXX' }
    ]
  }

  verificationTagId(tagId, uuidConnexion) {
    let msgErreurs = 0, data

    // mettre tagId en majuscule
    if (tagId !== null) {
      tagId = tagId.toUpperCase()

      // vérifier taille tagId
      let tailleTagId = tagId.length
      if (tailleTagId < 8 || tailleTagId > 8) {
        msgErreurs++
        console.log('Erreur, taille tagId = ' + tailleTagId + ' !!')
      }

      // vérifier uuidConnexion
      if (uuidConnexion !== this.uuidConnexion) {
        msgErreurs++
        console.log('Erreur uuidConnexion différent !!')
      }

      // envoyer le résultat du lecteur
      if (msgErreurs === 0) {
        const event = new CustomEvent("nfcResult", { detail: tagId })
        document.body.dispatchEvent(event)

        // réinitialisation de l'état du lecteur nfc
        this.uuidConnexion = null
      }
    }
  }

  listenCordovaNfc() {
    console.log('-> listenCordovaNfc,', new Date())
    try {
      nfc.addTagDiscoveredListener((nfcEvent) => {
        let tag = nfcEvent.tag
        if (this.cordovaLecture === true) {
          this.verificationTagId(nfc.bytesToHexString(tag.id), this.uuidConnexion)
        }
      })
      clearInterval(this.intervalIDVerifApiCordova)
    } catch (error) {
      console.log('-> listenCordovaNfc :', error)
    }
  }

  simule() {
    // compose le message à afficher
    let uiSimu = `<div id="nfc-reader-simu-overlay">
      <fieldset id="nfc-reader-simu-container">
        <legend data-i8n="nfcCardSimulation,capitalize">Nfc - Simulation</legend>`

    this.simuData.forEach((item, i) => {
      uiSimu += `
        <div class="nfc-reader-simu-bt" tag-id="${item.tagId}">${item.name}</div>
      `
    })

    uiSimu += `
      </fieldset>
    </div>
    <style>
      #nfc-reader-simu-overlay {
        width: 100vw;
        height: 100vh;
        position: absolute;
        left: 0;
        top: 0;
        /* au-dessus du modal SweetAlert2 (.swal2-container : z-index 1060),
           sinon les clics sont captés par le backdrop et les cartes sont
           inatteignables / above the SweetAlert2 modal (.swal2-container:
           z-index 1060), otherwise clicks are caught by the backdrop and
           the cards are unreachable */
        z-index: 2000;
        opacity: 0.9;
        display: flex;
		    flex-direction: column;
		    justify-content: center;
		    align-items: center;
        background-color:#000000;
      }

      #nfc-reader-simu-container {
        min-height: 200px;
        padding: 20px;
        background-color:rgba(255, 255, 255,1);
        color: #000000;
        opacity: 1;
        display: flex;
		    flex-direction: column;
		    justify-content: center;
		    align-items: center;
      }

      .nfc-reader-simu-bt {
        width: 150px;
        height: 80px;
        background-color: #0000ff;
        color: #ffffff;
		    display: flex;
		    flex-direction: row;
		    justify-content: center;
		    align-items: center;
        font-size: 1.5rem;
        margin-bottom: 2rem;
        border-radius: 8px;
        font-weight: bold;
	    }

      .nfc-reader-simu-ligne label {
        margin-left: 10px;
      }
    </style>`
    document.body.insertAdjacentHTML('beforeend', uiSimu)

    // clic sur le fond noir (hors cartes) : fermer l'overlay pour rendre la
    // main au modal SweetAlert (bouton Annuler), sans envoyer de tagId
    // / click on the black background (outside the cards): close the overlay
    // to give back control to the SweetAlert modal (Cancel button), no tagId sent
    const overlaySimu = document.querySelector('#nfc-reader-simu-overlay')
    overlaySimu.addEventListener('click', (clickEvent) => {
      if (clickEvent.target === overlaySimu) {
        overlaySimu.remove()
      }
    })

    document.querySelectorAll('.nfc-reader-simu-bt').forEach((bt) => {
      bt.addEventListener('click', () => {
        const tagId = bt.getAttribute('tag-id')
        console.log('tagId =', tagId);

        // hide ui simu
        document.querySelector('#nfc-reader-simu-overlay').remove()

        // envoyer le résultat du lecteur
        const event = new CustomEvent("nfcResult", { detail: tagId })
        document.body.dispatchEvent(event)
      })
    })
  }

  /**
  * Gestion de la réception du tagIDS et de l'uuidConnexion
  * @param mode
  */
  gestionModeLectureNfc(mode) {
    // console.log('1 -> gestionModeLectureNfc, mode =', mode)
    this.uuidConnexion = crypto.randomUUID()

    // nfc serveur socket_io + front sur le même appareil (pi ou desktop)
    // protocole de laboutik_client_pi_desktop_v2/nfcServer.js :
    // émettre 'nfcStartListening' / 'nfcStopListening', recevoir 'nfcMessage'.
    // / protocol of laboutik_client_pi_desktop_v2/nfcServer.js:
    // emit 'nfcStartListening' / 'nfcStopListening', receive 'nfcMessage'.
    if (mode === 'NFCLO') {
      // garde : socket.io non chargé -> pas de crash, juste un log
      // / guard: socket.io not loaded -> no crash, just a log
      if (typeof io === 'undefined') {
        console.error('Socket.io absent : mode NFCLO indisponible')
        return
      }

      // déconnecte une ancienne connexion, évite plusieurs écoutes
      // / disconnect a previous connection, avoids stacked listeners
      if (this.socket) {
        this.socket.disconnect()
      }

      // initialise la connexion
      this.socket = io('http://localhost:' + this.socketPort, {})

      // réception d'un tagId, message = 'nfcMessage' ({ tagId, data })
      // / tagId reception, message = 'nfcMessage' ({ tagId, data })
      this.socket.on('nfcMessage', (retour) => {
        if (retour.tagId) {
          this.verificationTagId(retour.tagId, retour.data?.uuidConnexion)
        }
      })

      // initialise la getion des erreurs socket.io
      this.socket.on('connect_error', (error) => {
        // TODO: émettre un log
        console.error(`Socket.io - http://localhost:${this.socketPort} :`, error)
      })

      // demande la lecture
      this.socket.emit('nfcStartListening', { uuidConnexion: this.uuidConnexion })
    }

    // cordova
    if (mode === 'NFCMC') {
      this.cordovaLecture = true
      this.intervalIDVerifApiCordova = setInterval(() => {
        this.listenCordovaNfc()
      }, 500)
    }
  }

  startLecture(options) {
    console.log('0 -> startLecture  --  DEMO =', window?.DEMO)
    // simule (mode DEMO du kiosque ou demande explicite) / simulate (kiosk
    // DEMO mode or explicit request)
    if (window.DEMO !== undefined || options?.simulation === true) {
      this.simule()
      return
    }

    // hardware : le mode se choisit depuis type_app (window.KIOSK, expose par
    // base.html), pas depuis un localStorage 'laboutik' absent sur l'origine
    // serveur du kiosque. / hardware: the mode is picked from type_app
    // (window.KIOSK, exposed by base.html), not a 'laboutik' localStorage
    // absent on the kiosk's server origin.
    const mode = (window.KIOSK && window.KIOSK.type_app === "cordova") ? "NFCMC" : "NFCLO"
    this.modeNfc = mode
    this.gestionModeLectureNfc(mode)
  }

  stopLecture() {
    console.log('1 -> stopLecture')
    let modeNfc = this.modeNfc

    // simulateur DEMO : retirer l'overlay s'il est encore affiché (fermeture
    // de la popup par timer/annulation sans clic sur une carte)
    // / DEMO simulator: remove the overlay if still shown (popup closed by
    // timer/cancel without a card click)
    const overlaySimu = document.querySelector('#nfc-reader-simu-overlay')
    if (overlaySimu) {
      overlaySimu.remove()
    }

    // tagId pour "un serveur nfc + front" en local
    if (modeNfc === "NFCLO" && this.socket) {
      // arrête la lecture côté nfcServer.js puis déconnecte
      // / stop the read on nfcServer.js side then disconnect
      this.socket.emit('nfcStopListening')
      this.socket.disconnect()
      this.socket = null
    }

    // cordova
    if (modeNfc === 'NFCMC') {
      this.cordovaLecture = false
      clearInterval(this.intervalIDVerifApiCordova)
    }

    this.uuidConnexion = null
  }
}