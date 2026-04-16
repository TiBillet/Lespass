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


	/**
	* Gestion de la réception du tagIDS et de l'uuidConnexion
	* @param mode
	*/
	async gestionModeLectureNfc(mode) {
		const conf = this.conf
		console.log('1 -> gestionModeLectureNfc, mode =', mode)
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
			const tagId = await nfcPlugin.startListening()
      this.verificationTagId(tagId, this.uuidConnexion)
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
		}
	}

	async start(conf) {
		// console.log('0 -> startLecture  --  DEMO =', state.demo.active)
		this.conf = conf
		try {
			if (state.demo.active) {
				// simule
				this.modeNfc = 'NFCSIMU'
			} else {
				// hardware: récupère le nfcMode
        const cordovaNfcPlugin = await nfcPlugin.available()
        if(cordovaNfcPlugin === 1) {
          this.modeNfc="NFCMC"
        }
				// TODO: ajouter le  pi(mfc...) et desktop(usb)
			}
			this.gestionModeLectureNfc(this.modeNfc)
		} catch (err) {
			console.log(`Nfc initLecture, storage: ${err}  !`)
		}
	}

	async stop() {
		// console.log('1 -> stopLecture')
		let modeNfc = this.modeNfc

		// tagId pour "un serveur nfc + front" en local
		if (modeNfc === "NFCLO") {
			// console.log('-> émettre: "AnnuleDemandeTagId"')
			this.socket.emit('AnnuleDemandeTagId', { uuidConnexion: this.uuidConnexion })
		}

		// cordova
		if (modeNfc === 'NFCMC') {
			await nfcPlugin.stopListening()
		}

		// simulation
		if (modeNfc === 'NFCSIMU') {
			document.querySelector('#nfc-simu-tag').removeEventListener('click', this.sendSimuNfcTagId)
		}
		this.uuidConnexion = null
	}
}