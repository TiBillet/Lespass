// https://github.com/nerdy-harry/phonegap-nfc-api31?tab=readme-ov-file#nfcshowsettings

let NfcReader = class {
	constructor() {
		this.modeNfc = ''
		this.uuidConnexion = null
		this.socket = null
		this.socketPort = 3000
		this.intervalIDVerifApiCordova = null
		this.cordovaLecture = false
		this.simuData = state.demo.tags_id
		this.conf = null
	}

	SendTagIdAndSubmit(tagId, conf) {
		console.log('-> SendTagIdAndSubmit, conf =', conf)
    console.log('-> SendTagIdAndSubmit, tagId =', tagId)

		// dispatch event - peuple le tagId dans un formulaire
		sendEvent('organizerMsg', '#event-organizer', {
			src: { file: 'nfc.js', method: 'SendTagIdAndSubmit' },
			msg: conf.eventManageForm,
			data: { actionType: 'updateInput', selector: '#nfc-tag-id', value: tagId }
		})

		// modifie l'url du post du formulaire
		sendEvent('organizerMsg', '#event-organizer', {
			src: { file: 'nfc.js', method: 'SendTagIdAndSubmit' },
			msg: conf.eventManageForm,
			data: { actionType: 'postUrl', selector: '', value: conf.submitUrl }
		})

		// submit le formulaire
		sendEvent('organizerMsg', '#event-organizer', {
			src: { file: 'nfc.js', method: 'SendTagIdAndSubmit' },
			msg: conf.eventManageForm,
			data: { actionType: 'submit' }
		})

	}

	verificationTagId(tagId, uuidConnexion) {
		const conf = this.conf
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
				this.SendTagIdAndSubmit(tagId, conf)
				this.stop()
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

	/**
	* Gestion de la réception du tagIDS et de l'uuidConnexion
	* @param mode
	*/
	gestionModeLectureNfc(mode) {
		const conf = this.conf
		// console.log('1 -> gestionModeLectureNfc, mode =', mode)
		this.uuidConnexion = crypto.randomUUID()

		// nfc serveur socket_io + front sur le même appareil (pi ou desktop)
		if (mode === 'NFCLO') {
			// initialise la connexion
			this.socket = io('http://localhost:' + this.socketPort, {})

			// initialise la réception d'un tagId, méssage = 'envoieTagId'
			this.socket.on('envoieTagId', (retour) => {
				this.verificationTagId(retour.tagId, retour.uuidConnexion)
			})

			// initialise la getion des erreurs socket.io
			this.socket.on('connect_error', (error) => {
				// TODO: émettre un log
				console.error(`Socket.io - ${this.socketUrl}:${this.socketPort} :`, error)
			})

			// demande la lecture
			this.socket.emit('demandeTagId', { uuidConnexion: this.uuidConnexion })
		}

		// cordova
		if (mode === 'NFCMC') {
			this.cordovaLecture = true
			this.intervalIDVerifApiCordova = setInterval(() => {
				this.listenCordovaNfc(conf)
			}, 500)
		}

		// simulation
		if (mode === 'NFCSIMU') {
			// compose le message à afficher
			let uiSimu = ''
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
						this.SendTagIdAndSubmit(tagId, conf)
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
				this.SendTagIdAndSubmit(tagSaisi, conf)
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
	}

	start(conf) {
		// console.log('0 -> startLecture  --  DEMO =', state.demo.active)
		this.conf = conf
		try {
			if (state.demo.active) {
				// simule
				this.modeNfc = 'NFCSIMU'
			} else {
				// hardware: récupère le nfcMode
				const storage = JSON.parse(localStorage.getItem('laboutik'))
				this.modeNfc = storage.mode_nfc
			}
			this.gestionModeLectureNfc(this.modeNfc)
		} catch (err) {
			console.log(`Nfc initLecture, storage: ${err}  !`)
		}
	}

	stop() {
		// console.log('1 -> stopLecture')
		let modeNfc = this.modeNfc

		// tagId pour "un serveur nfc + front" en local
		if (modeNfc === "NFCLO") {
			// console.log('-> émettre: "AnnuleDemandeTagId"')
			this.socket.emit('AnnuleDemandeTagId', { uuidConnexion: this.uuidConnexion })
		}

		// cordova
		if (modeNfc === 'NFCMC') {
			this.cordovaLecture = false
			clearInterval(this.intervalIDVerifApiCordova)
		}

		// simulation
		if (modeNfc === 'NFCSIMU') {
			document.querySelector('#nfc-simu-tag').removeEventListener('click', this.sendSimuNfcTagId)
		}
		this.uuidConnexion = null
	}
}