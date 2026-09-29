// https://github.com/nerdy-harry/phonegap-nfc-api31?tab=readme-ov-file#nfcshowsettings

let NfcReader = class {
  constructor() {
    this.modeNfc = ''
    this.uuidConnexion = null
    this.socket = null
    this.socketPort = 3000
    this.intervalIDVerifApiCordova = null
    this.cordovaLecture = false
    // Cartes du simulateur (mode DEMO), posees par kiosk/templates/kiosk/base.html.
    // Ce sont les memes que la caisse et la tireuse.
    // / Simulator cards (DEMO), set by base.html. Same as the POS and the tap.
    this.simuData = window?.DEMO?.cartesDuSimulateur || []
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
    // Simulateur de cartes : un panneau discret, replie en bas de l'ecran.
    // On clique sur son en-tete pour deplier la liste des cartes.
    //
    // Il ne masque PAS le message « posez votre carte » : le lecteur physique
    // tourne en parallele (cf. startLecture). C'est le meme principe que le
    // bouton .nfc-toggle-simu de la caisse LaBoutik (laboutik/static/js/nfc.js).
    //
    // / Card simulator: a discreet panel, collapsed at the bottom of the screen.
    // It does NOT cover the "tap your card" message: the physical reader runs
    // in parallel.

    // Un seul panneau a la fois (startLecture peut etre rappele).
    // / Only one panel at a time (startLecture may be called again).
    const panneauExistant = document.querySelector('#nfc-reader-simu-panel')
    if (panneauExistant) {
      panneauExistant.remove()
    }

    let cartesHtml = ''
    this.simuData.forEach((item) => {
      cartesHtml += `
        <div class="nfc-reader-simu-bt" tag-id="${item.tagId}" data-testid="kiosk-nfc-simu-carte">${item.name}</div>`
    })

    const uiSimu = `<div id="nfc-reader-simu-panel" data-testid="kiosk-nfc-simulator">
      <button type="button"
              id="nfc-reader-simu-toggle"
              data-testid="kiosk-nfc-simu-toggle"
              aria-expanded="false"
              aria-controls="nfc-reader-simu-cartes">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
          <path d="M9 9l-2 3 2 3" stroke="currentColor" stroke-width="2"/>
          <path d="M15 9l2 3-2 3" stroke="currentColor" stroke-width="2"/>
        </svg>
        <span data-i8n="nfcCardSimulation,capitalize">Simulateur de cartes</span>
      </button>
      <div id="nfc-reader-simu-cartes" hidden>${cartesHtml}</div>
    </div>
    <style>
      #nfc-reader-simu-panel {
        position: fixed;
        left: 50%;
        bottom: 0;
        transform: translateX(-50%);
        /* au-dessus des modales de la borne (z-index 300)
           / above the kiosk modals */
        z-index: 2000;
        /* Jetons de la borne (kiosk/static/kiosk/css/tokens.css), avec repli.
           / Kiosk tokens, with fallback. */
        background: var(--color-surface, #ffffff);
        color: var(--color-text, #111111);
        border-radius: 12px 12px 0 0;
        box-shadow: 0 -2px 16px rgba(0, 0, 0, 0.35);
        max-width: 96vw;
      }

      #nfc-reader-simu-toggle {
        display: flex;
        align-items: center;
        gap: 8px;
        width: 100%;
        padding: 10px 18px;
        background: transparent;
        border: none;
        color: inherit;
        font-size: 1rem;
        font-weight: 600;
        cursor: pointer;
      }

      #nfc-reader-simu-cartes {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 12px;
        padding: 0 18px 18px 18px;
      }

      #nfc-reader-simu-cartes[hidden] {
        display: none;
      }

      .nfc-reader-simu-bt {
        min-width: 120px;
        padding: 18px 12px;
        background-color: var(--color-text, #17141a);
        color: var(--color-on-dark, #ffffff);
        display: flex;
        justify-content: center;
        align-items: center;
        font-size: 1.25rem;
        border-radius: 8px;
        font-weight: bold;
        cursor: pointer;
      }
    </style>`
    // Une modale ouverte avec showModal() rend INERTE tout ce qui est hors
    // d'elle : on pose donc le panneau A L'INTERIEUR de la modale ouverte
    // (modale admin), sinon ses cartes ne seraient pas cliquables.
    // / A showModal() dialog makes everything outside it inert: put the panel
    // INSIDE the open dialog, or its cards would not be clickable.
    const modaleOuverte = document.querySelector('dialog[open]')
    const conteneurDuPanneau = modaleOuverte || document.body
    conteneurDuPanneau.insertAdjacentHTML('beforeend', uiSimu)

    // Deplie / replie la liste des cartes.
    // / Expand / collapse the card list.
    const boutonToggle = document.querySelector('#nfc-reader-simu-toggle')
    const listeCartes = document.querySelector('#nfc-reader-simu-cartes')
    boutonToggle.addEventListener('click', () => {
      const etaitReplie = listeCartes.hasAttribute('hidden')
      if (etaitReplie) {
        listeCartes.removeAttribute('hidden')
      } else {
        listeCartes.setAttribute('hidden', '')
      }
      boutonToggle.setAttribute('aria-expanded', etaitReplie ? 'true' : 'false')
    })

    document.querySelectorAll('.nfc-reader-simu-bt').forEach((bt) => {
      bt.addEventListener('click', () => {
        const tagId = bt.getAttribute('tag-id')
        console.log('tagId =', tagId);

        // Retire le panneau, puis envoie le resultat comme le ferait le lecteur.
        // / Remove the panel, then emit the result as the reader would.
        document.querySelector('#nfc-reader-simu-panel').remove()

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

    // En mode DEMO, le simulateur s'affiche EN PLUS du lecteur physique, comme
    // sur l'app Android : on peut cliquer une carte simulee OU poser une vraie
    // carte sur le lecteur. Le premier des deux qui repond gagne.
    // C'est 'nfcResult' qui tranche : kiosk/static/kiosk/js/main.js recoit
    // l'evenement et appelle stopLecture() -> le panneau est retire et le
    // lecteur arrete. Le nettoyage est donc commun aux deux chemins.
    // / In DEMO mode the simulator is shown ALONGSIDE the physical reader, like
    // the Android app: click a simulated card OR tap a real one. First one wins;
    // main.js receives 'nfcResult' and calls stopLecture().
    const modeDemoActif = (window.DEMO !== undefined)
    const simulationSeuleDemandee = (options?.simulation === true)

    if (modeDemoActif || simulationSeuleDemandee) {
      this.simule()
    }

    // Demande explicite de simulation : on n'allume pas le lecteur.
    // / Explicit simulation request: do not start the reader.
    if (simulationSeuleDemandee) {
      return
    }

    // hardware : le mode se choisit depuis type_app (window.KIOSK, expose par
    // base.html), pas depuis un localStorage 'laboutik' absent sur l'origine
    // serveur du kiosque. / hardware: the mode is picked from type_app
    // (window.KIOSK, exposed by base.html), not a 'laboutik' localStorage
    // absent on the kiosk's server origin.
    //
    // - cordova         -> NFCMC : plugin NFC natif (borne Android / Sunmi)
    // - pi ou desktop   -> NFCLO : serveur socket.io local (nfcServer.js, port 3000)
    // - autre (unknown) -> aucun lecteur : simple navigateur, sans serveur local.
    //   Avant, ce cas partait en NFCLO et chaque page affichait l'erreur
    //   « xhr poll error / CORS » sur http://localhost:3000.
    // / cordova -> NFCMC, pi/desktop -> NFCLO, anything else -> no hardware
    // reader (plain browser: no local socket.io server to reach).
    const typeApp = window.KIOSK ? window.KIOSK.type_app : ''
    let mode = ''
    if (typeApp === 'cordova') {
      mode = 'NFCMC'
    } else if (typeApp === 'pi' || typeApp === 'desktop') {
      mode = 'NFCLO'
    }

    this.modeNfc = mode
    if (mode === '') {
      console.warn(`Aucun lecteur NFC materiel pour type_app = "${typeApp}"`)
      return
    }
    this.gestionModeLectureNfc(mode)
  }

  stopLecture() {
    console.log('1 -> stopLecture')
    let modeNfc = this.modeNfc

    // simulateur DEMO : retirer le panneau s'il est encore affiché (écran
    // changé, modale fermée, ou scan d'une vraie carte)
    // / DEMO simulator: remove the panel if still shown (screen changed,
    // modal closed, or a real card was tapped)
    const panneauSimu = document.querySelector('#nfc-reader-simu-panel')
    if (panneauSimu) {
      panneauSimu.remove()
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