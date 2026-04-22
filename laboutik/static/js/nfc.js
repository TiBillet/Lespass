// https://github.com/nerdy-harry/phonegap-nfc-api31?tab=readme-ov-file#nfcshowsettings

// Stub de sécurité : si tibilletUtils.js est en cache (ancienne version sans debugLog),
// on définit une version silencieuse pour que nfc.js ne crashe pas.
// / Safety stub: if tibilletUtils.js is cached (old version without debugLog),
// define a silent version so nfc.js doesn't crash.
if (typeof debugLog !== 'function') {
	// eslint-disable-next-line no-unused-vars
	var debugLog = function(msg) { try { console.log('[DBG-stub] ' + msg) } catch(e) {} }
}

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
		debugLog('NFC SendTagId tag=' + tagId + ' event=' + (conf && conf.eventManageForm))

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

		debugLog('NFC verif tag=' + tagId)

		// mettre tagId en majuscule
		if (tagId !== null) {
			tagId = tagId.toUpperCase()

			// vérifier taille tagId
			let tailleTagId = tagId.length
			if (tailleTagId < 8 || tailleTagId > 8) {
				msgErreurs++
				debugLog('NFC ERR taille=' + tailleTagId)
				console.log('Erreur, taille tagId = ' + tailleTagId + ' !!')
			}

			// vérifier uuidConnexion
			if (uuidConnexion !== this.uuidConnexion) {
				msgErreurs++
				debugLog('NFC ERR uuid mismatch recu=' + uuidConnexion + ' attendu=' + this.uuidConnexion)
				console.log('Erreur uuidConnexion différent !!')
			}

			// envoyer le résultat du lecteur
			if (msgErreurs === 0) {
				this.SendTagIdAndSubmit(tagId, conf)
				this.stop()
			} else {
				debugLog('NFC BLOQUE msgErreurs=' + msgErreurs)
			}
		} else {
			debugLog('NFC ERR tagId null')
		}
	}

	listenCordovaNfc() {
		console.log('-> listenCordovaNfc,', new Date())
		debugLog('NFC listenCordova cordovaLecture=' + this.cordovaLecture)
		try {
			// Sur les pages externes (ex : http://192.168.x.x:8002), enableForegroundDispatch
			// + onNewIntent ne fonctionne pas de manière fiable avec singleInstance.
			// On utilise donc readerMode (enableReaderMode) qui livre le tag directement
			// via ReaderCallback.onTagDiscovered, sans passer par onNewIntent.
			// / On external pages (e.g. http://192.168.x.x:8002), enableForegroundDispatch
			// + onNewIntent is unreliable with singleInstance launch mode.
			// We use readerMode (enableReaderMode) which delivers the tag directly
			// via ReaderCallback.onTagDiscovered, bypassing onNewIntent entirely.
			if (typeof nfc !== 'undefined') {
				// FLAG_READER_NO_PLATFORM_SOUNDS : supprime le son système Android (0x100).
				// On joue un bip unique via Web Audio API dans le callback pour garder le retour sonore.
				// Sans ce flag, Android rejoue le son à chaque poll NFC avant que disableReaderMode
				// prenne effet côté natif, causant un double bip.
				// / FLAG_READER_NO_PLATFORM_SOUNDS: suppress Android system sound (0x100).
				// We play one beep via Web Audio API in the callback to keep audio feedback.
				// Without this flag, Android replays the sound each NFC poll before disableReaderMode
				// takes effect natively, causing a double beep.
				const flags = nfc.FLAG_READER_NFC_A | nfc.FLAG_READER_NFC_B | nfc.FLAG_READER_NFC_V | nfc.FLAG_READER_NO_PLATFORM_SOUNDS
				nfc.readerMode(
					flags,
					(tagJson) => {
						// tagJson est l'objet tag brut (id, techTypes, …)
						// / tagJson is the raw tag object (id, techTypes, …)
						if (this.cordovaLecture === true) {
							this.cordovaLecture = false
							nfc.disableReaderMode()
							// Bip unique via Web Audio API en remplacement du son système supprimé.
							// / Single beep via Web Audio API replacing the suppressed system sound.
							try {
								const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
								const osc = audioCtx.createOscillator()
								const gain = audioCtx.createGain()
								osc.connect(gain)
								gain.connect(audioCtx.destination)
								osc.frequency.value = 1000
								gain.gain.setValueAtTime(0.4, audioCtx.currentTime)
								gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.15)
								osc.start(audioCtx.currentTime)
								osc.stop(audioCtx.currentTime + 0.15)
							} catch (audioErr) {
								console.log('-> nfc beep audio error:', audioErr)
							}
							this.verificationTagId(nfc.bytesToHexString(tagJson.id), this.uuidConnexion)
						}
					},
					(error) => {
						console.log('-> listenCordovaNfc readerMode error:', error)
					}
				)
				// clearInterval seulement si nfc est disponible et readerMode enregistré.
				// Si nfc n'est pas encore prêt, on réessaie au prochain tick.
				// / clearInterval only once nfc is available and readerMode is registered.
				// If nfc is not ready yet, retry on next tick.
				clearInterval(this.intervalIDVerifApiCordova)
			}
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
		// crypto.randomUUID() nécessite HTTPS et Chrome 92+ — indisponible dans le WebView Cordova sur HTTP.
		// On utilise un générateur UUID v4 simple basé sur Math.random().
		// / crypto.randomUUID() requires HTTPS and Chrome 92+ — unavailable in Cordova WebView over HTTP.
		// Using a simple Math.random()-based UUID v4 generator instead.
		this.uuidConnexion = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
			const r = Math.random() * 16 | 0
			return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
		})

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
			// Désactiver readerMode pour libérer le lecteur NFC natif
			// / Disable readerMode to release the native NFC reader
			if (typeof nfc !== 'undefined') {
				nfc.disableReaderMode()
			}
		}

		// simulation
		if (modeNfc === 'NFCSIMU') {
			document.querySelector('#nfc-simu-tag').removeEventListener('click', this.sendSimuNfcTagId)
		}
		this.uuidConnexion = null
	}
}