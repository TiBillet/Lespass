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

	sendCommand(eventName, form, data) {
		// console.log('-> sendCommand form =', form, '  --  data =', data, '  --  eventName =', eventName)
		try {
			data['form'] = form
			const event = new CustomEvent(eventName, { detail: data })
			document.querySelector(form).dispatchEvent(event)
		} catch (error) {
			console.log('sendCommand,', error);
		}
	}

	parseAndSendCommands(tagId, conf) {
		try {
			let eventTrigger = ''
			const eventName = conf.eventName
			const form = conf.selectorForm
			const actions = conf.actions
			for (let i = 0; i < actions.length; i++) {
				const action = actions[i].split(',')
				const updateType = action[0]
				let obj
				// populate input tagId
				if (updateType === 'inputTagId') {
					obj = {
						updateType: 'input',
						selector: action[1],
						value: tagId
					}
				}
				// populate input
				if (updateType === 'input') {
					obj = {
						updateType: 'input',
						selector: action[1],
						value: action[2],
					}
				}
				// populate hx-post
				if (updateType === 'url') {
					obj = {
						updateType: 'url',
						value: action[1],
					}
				}
				// populate hx-trigger
				if (updateType === 'hx-trigger') {
					eventTrigger = action[1]
					obj = {
						updateType: 'hx-trigger',
						value: action[1],
					}
				}

				// submit
				if (updateType === 'submit') {
					obj = {
						updateType: 'submit',
						value: eventTrigger,
					}
				}

				// send event
				this.sendCommand(eventName,form, obj)
			}
		} catch (error) {
			console.log('nfc - parseAndSendCommands :', error)
		}
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
				this.parseAndSendCommands(tagId, conf)
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
        <div class="nfc-reader-simu-bt" tag-id="${item.tag_id}">${item.name}</div>
      `
			})
			document.querySelector('#nfc-simu-tag').innerHTML = uiSimu

			// bt simulation receipt tag id
			document.querySelector('#nfc-simu-tag').addEventListener('click', (ev) => {
				if (ev.target.className === 'nfc-reader-simu-bt') {
					try {
						const tagId = ev.target.getAttribute('tag-id')
						this.parseAndSendCommands(tagId, conf)
						this.stop()
					} catch (error) {
						console.log('-> simulaton tag id,', error)
					}
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