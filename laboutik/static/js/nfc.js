// https://github.com/nerdy-harry/phonegap-nfc-api31?tab=readme-ov-file#nfcshowsettings

const NfcReader = class {
  constructor(socketIoPort, typeApp) {
    this.typeApp = typeApp
    this.uuidConnexion = null
    this.socketIo = null
    this.socketIoPort = socketIoPort
    this.simuData = state.demo.tags_id
    this.simuActivate = false
    this.conf = null
  }


  SendTagIdAndSubmit(tagId, conf) {
    // console.log('-> SendTagIdAndSubmit, conf =', conf)
    // console.log('-> SendTagIdAndSubmit, tagId =', tagId)

    // stop listening nfc
    this.stop()

    // dispatch event - peuple le tagId dans un formulaire
    sendEventOrganizer({
      src: { file: 'nfc.js', method: 'SendTagIdAndSubmit' },
      msg: 'nfcAskManageForm',
      data: { formSelector: conf.formSelector, actionType: 'updateInput', selector: conf.inputSelector, value: tagId }
    })

    // modifie l'url du post du formulaire
    sendEventOrganizer({
      src: { file: 'nfc.js', method: 'SendTagIdAndSubmit' },
      msg: 'nfcAskManageForm',
      data: { formSelector: conf.formSelector, actionType: 'postUrl', selector: '', value: conf.submitUrl }
    })

    // submit le formulaire
    sendEventOrganizer({
      src: { file: 'nfc.js', method: 'SendTagIdAndSubmit' },
      msg: 'nfcAskManageForm',
      data: { formSelector: conf.formSelector, actionType: 'submit' }
    })

  }

  verificationTagId(tagId, uuidConnexion) {
    let msgErreurs = []

    // mettre tagId en majuscule
    if (tagId !== null) {
      tagId = tagId.toUpperCase()

      // vérifier taille tagId
      let tailleTagId = tagId.length
      if (tailleTagId < 8 || tailleTagId > 8) {
        msgErreurs.push('Erreur, taille tagId = ' + tailleTagId + ' !!')
      }

      // vérifier uuidConnexion
      if (uuidConnexion !== this.uuidConnexion) {
        msgErreurs.push('Erreur uuidConnexion différent !!')
      }

      // envoyer le résultat du lecteur
      if (msgErreurs.length === 0) {
        this.SendTagIdAndSubmit(tagId, this.conf)
        this.stop()
      }
    } else {
      msgErreurs.push('tagId null')
    }

    if (msgErreurs.length > 0) {
      console.log('-> verificationTagId :')
      msgErreurs.forEach(msg => console.log(msg))
      this.stop()
    }
  }

  showUiSimu() {
    // compose l'interface de simulation à afficher
    let uiSimu = ''
    // console.log('-> nfc.toggleSimu')
    this.simuData.forEach((item, i) => {
      uiSimu += `
        <div class="nfc-reader-simu-bt" tag-id="${item.tag_id}">${escapeHtml(item.name)}</div>
      `
    })

    // Zone de saisie manuelle : permet de tester un tag_id qui n'est
    // pas dans la liste. Persistance du dernier tag saisi via localStorage.
    // Manual input zone: allows testing a tag_id not in the list.
    // Persists last entered tag via localStorage.
    // Le parent .nfc-container-slot est flex-column avec text blanc :
    // on force color/background et une largeur fixe sur l'input.
    // Parent .nfc-container-slot is flex-column with white text:
    // force color/background and a fixed width on the input.
    const dernierTagSaisi = localStorage.getItem('nfcSimuManualTag') || ''
    uiSimu += `
        <div class="nfc-reader-simu-manual" style="margin-top:1rem;display:flex;gap:8px;align-items:center;justify-content:center;">
          <input type="text"
                 id="nfc-simu-manual-input"
                 placeholder="Tag ID (ex : A49E8E2A)"
                 maxlength="8"
                 value="${escapeHtml(dernierTagSaisi)}"
                 style="width:200px;padding:10px 12px;border:1px solid #d1d5db;border-radius:6px;font-family:monospace;font-size:1rem;text-transform:uppercase;color:#111;background:#fff;" />
          <button type="button"
                  id="nfc-simu-manual-submit"
                  style="padding:10px 18px;background:#2563eb;color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;white-space:nowrap;">
            Valider
          </button>
        </div>
      `

    document.querySelector('#nfc-simu-tag').innerHTML = uiSimu

    // bt simulation receipt tag id
    document.querySelector('#nfc-simu-tag').addEventListener('click', (ev) => {
      if (ev.target.className === 'nfc-reader-simu-bt') {
        try {
          const tagId = ev.target.getAttribute('tag-id')
          this.SendTagIdAndSubmit(tagId, this.conf)
          this.stop()
        } catch (error) {
          console.log('-> simulaton tag id,', error)
        }
      }
    })

    // Submit du tag saisi manuellement (clic bouton OU touche Entree).
    // Submit manually entered tag (button click OR Enter key).
    const soumettreTagManuel = () => {
      const input = document.querySelector('#nfc-simu-manual-input')
      const tagSaisi = input.value.trim().toUpperCase()
      if (tagSaisi === '') return
      localStorage.setItem('nfcSimuManualTag', tagSaisi)
      this.SendTagIdAndSubmit(tagSaisi, this.conf)
      this.stop()
    }

    document.querySelector('#nfc-simu-manual-submit').addEventListener('click', soumettreTagManuel)
    document.querySelector('#nfc-simu-manual-input').addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault()
        soumettreTagManuel()
      }
    })
  }

  hideUiSimu() {
    document.querySelector('#nfc-simu-tag').innerHTML = ''
  }

  piDesktopStopRead() {
    if (this.socketIo) {
      this.socketIo.emit('nfcStopListening')
      this.socketIo.disconnect()
      this.socketIo = null
    }
  }

  piDesktopStarRead() {
    // console.log('-> piDesktopStarRead')

    // déconnecte anciennes connexion sur le back, évite plusieurs écoutes
    // un appel front donne une seule réponse back
    if (this.socketIo) {
      this.socketIo.disconnect();
    }

    // initialise la connexion
    this.socketIo = io('http://localhost:' + this.socketIoPort, {})

    // initialise la réception d'un tagId, méssage = 'nfcMessage'
    this.socketIo.on('nfcMessage', (retour) => {
      // console.log('réception du message "nfcMessage" - retour =', retour)
      if (retour.tagId) {
        this.piDesktopStopRead()
        this.verificationTagId(retour.tagId, retour.data.uuidConnexion)
      }
    })

    // initialise la getion des erreurs socket.io
    this.socketIo.on('connect_error', (error) => {
      // TODO: émettre un log
      console.error(`Socket.io - 'http://localhost:${this.socketPort} :`, error)
    })

    // Demande de lecture, le back stope les anciennes lectures 
    // et en démarre une nouvelle.
    this.socketIo.emit('nfcStartListening', { uuidConnexion: this.uuidConnexion })
  }

  async cordovaStopRead() {
    const result = await nfcPlugin.stopListening()
    console.log('-> nfc.cordovaStopRead -', result, '  --  ', new Date())
  }

  async start(conf) {
    console.log('-> nfc.start')

    try {
      this.conf = conf
      this.uuidConnexion = crypto.randomUUID()

      // ajoute le bouton .nfc-toggle-simu si démo activée
      if (state.demo.active) {
        // bt toggle simu
        const btToggleSimu = `
      <div class="nfc-toggle-simu">
        <div class="touch"></div>
		    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
			  <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2" />
			  <path d="M9 9l-2 3 2 3" stroke="currentColor" stroke-width="2" />
			  <path d="M15 9l2 3-2 3" stroke="currentColor" stroke-width="2" />
		    </svg>
	    </div>`

        const eleIsInDom = document.querySelector('.nfc-container div[class="nfc-toggle-simu"]')
        // insertion in dom
        if (eleIsInDom === null) {
          document.querySelector('.nfc-container').insertAdjacentHTML('beforeend', btToggleSimu)
          // action
          document.querySelector('.nfc-toggle-simu .touch').addEventListener('click', (event) => {
            event.stopPropagation()
            event.preventDefault()
            document.querySelector('.nfc-toggle-simu .touch').classList.toggle('activate')
            if (document.querySelector('.nfc-toggle-simu .touch').classList.contains('activate')) {
              this.simuActivate = true
            } else {
              this.simuActivate = false
            }
            this.start(this.conf)
          })
        }
      }

      // simu
      if (this.simuActivate) {
        this.showUiSimu()
      } else {
        this.hideUiSimu()

        // pi ou desktop
        if (this.typeApp === 'desktop' || this.typeApp === 'pi') {
          this.piDesktopStarRead()
        }
        // cordova
        if (this.typeApp === 'cordova') {
          // console.log('mode : cordova')
          // lance la lecture, seul nfcPlugin.stopListening peut l'arréter
          try {
            const result = await nfcPlugin.startListening()
            this.verificationTagId(result.tagId, this.uuidConnexion)
          } catch (error) {
            console.log('Processus nfc.start :', error);
          }

        }
      }
    } catch (error) {
      console.log('nfc.start, error:', error)
      this.stop()
    }

  }

  async stop() {
    try {
      // simu
      if (this.simuActivate) {
        this.hideUiSimu()
      }

      // pi ou desktop
      if (this.typeApp === 'desktop' || this.typeApp === 'pi') {
        this.piDesktopStopRead()
      }
      // cordova
      if (this.typeApp === 'cordova') {
        await this.cordovaStopRead()
      }
    } catch (error) {
      console.log('nfc.stop, error:', error)
    }
  }
}