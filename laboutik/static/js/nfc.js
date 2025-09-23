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
				// entrer la valeur dans le formulaire
				document.querySelector('#tag-id-cm').value = tagId
				const event = new CustomEvent("nfcResult", { detail: tagId })
				document.querySelector('#form-nfc').dispatchEvent(event)

				// réinitialisation de l'état du lecteur nfc
				this.uuidConnexion = null
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

	sendSimuNfcTagId(event) {
		if (event.target.className === 'nfc-reader-simu-bt') {
			const tagId = event.target.getAttribute('tag-id')
			// entrer la valeur dans le formulaire
			document.querySelector('#tag-id-cm').value = tagId
			// envoyer le résultat au formulaire
			const newEvent = new CustomEvent("nfcResult", { detail: null })
			document.querySelector('#form-nfc').dispatchEvent(newEvent)
			this.stop()
		}
	}

	/**
	* Gestion de la réception du tagIDS et de l'uuidConnexion
	* @param mode
	*/
	gestionModeLectureNfc(mode) {
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
				this.listenCordovaNfc()
			}, 500)
		}

		// simulation
		if (mode === 'NFCSIMU') {
			// compose le message à afficher
			let uiSimu = ''
			this.simuData.forEach((item, i) => {
				uiSimu += `
        <div class="nfc-reader-simu-bt" tag-id="${item.tag_id}">${item.name}</div>
      `
			})
			document.querySelector('#nfc-container').insertAdjacentHTML('beforeend', uiSimu)
			document.querySelector('#nfc-container').addEventListener('click', this.sendSimuNfcTagId.bind(this))
		}
	}

	start() {
		console.log('0 -> startLecture  --  DEMO =', state.demo.active)
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
			document.querySelector('#nfc-container').removeEventListener('click', this.sendSimuNfcTagId)
		}
		this.uuidConnexion = null
	}
}