console.log('DEMO =',state.demo.active, '  --  type =', typeof state.demo.active)

import { generatePemKeys, signMessage } from './modules/cryptoRsa.js'
import { readConfFile, writeConfFile, isCordovaApp } from './modules/hardwareLayer.js'

// port serveur localpour pi et desktop
const PORT = 3000
const mobile = isCordovaApp()
const cordovaFileName = 'configLaboutik.json'

// get configuration save in localstorage
let confLocalStorage = JSON.parse(localStorage.getItem('laboutik'))

// delete local configuration and update configuration app
async function deleteConfs() {
	console.log('-> deleteConfs')
	try {
		// supprimer le fichier de configuration local
		localStorage.removeItem('laboutik')

		let configuration, basePath, pathToFile, updateFile
		if (mobile === true) {
			basePath = cordova.file.dataDirectory
			pathToFile = basePath + cordovaFileName
			configuration = await readConfFile.cordova(pathToFile)
		} else {
			configuration = await readConfFile.http(PORT)
		}

		// supprimer le serveur courant
		configuration.current_server = ''

		// supprimer le serveur courant sauvegardé dans configuration.servers
		const serversToKeep = configuration.servers.filter(item => item.server !== configuration.current_server)
		configuration['servers'] = serversToKeep
		// supprimer le clientformData.append('ip_lan', configuration.ip)
		configuration.client = null

		// sauvegarder le fichier de configuration app
		if (mobile === true) {
			updateFile = await writeConfFile.cordova(basePath, cordovaFileName, configuration)
		} else {
			updateFile = await writeConfFile.http(configuration, PORT)
		}
		if (updateFile === true) {
			return true
		} else {
			return false
		}
	} catch (error) {
		console.log('Erreur, deleteConfs :', error)
		return false
	}
}

window.laboutikNewPair = async function () {
	const result = await deleteConfs()
	let redirectionUrl = `http://localhost:${PORT}`
	if (mobile === true) {
		redirectionUrl = 'http://localhost/index.html'
	}
	console.log('result =', result)
	if (result === true) {
		// redirection
		window.location.href = redirectionUrl
	} else {
		console.log('newPair, erreur maj configuration')
	}
}

function showPairAgain() {
	localStorage.removeItem('laboutik')
	document.querySelector('#new-pair').classList.remove('hide')
}

// gère le formulaire #form-new-harware après un hx-post
window.handleLogin = function (event) {
	const responseStatus = event.detail.xhr.status
	if (responseStatus === 200) {
		let url = currentConfiguration.current_server + 'laboutik/ask_primary_card'
		window.location.href = url
	}

	// console.log('response =', response)
	if (responseStatus === 400 || responseStatus === 401) {
		const response = JSON.parse(event.detail.xhr.responseText)
		console.log('response =', response)
		document.querySelector('#response-error').style.display = 'flex'
		document.querySelector('#response-error').innerText = response.msg
	}
}

async function initLogin() {
	log({ tag: 'INFO', msg: '-> initLogin' })
	const configuration = JSON.parse(localStorage.getItem('laboutik'))
	console.log('-> configuration =', configuration)
	if (configuration !== null) {
		const csrf_token = document.querySelector('input[name="csrfmiddlewaretoken"]').value
		const signature = await signMessage(configuration.keysPemCashlessClient, configuration.password)

		// dev affiche le formulaire
		// document.querySelector('#form-login-hardware').style.display = 'block'

		// remplir les inputs
		document.querySelector('#form-login-hardware input[name="username"]').value = configuration.client.username
		document.querySelector('#form-login-hardware input[name="password"]').value = configuration.client.password
		document.querySelector('#form-login-hardware input[name="periph"]').value = configuration.front_type
		document.querySelector('#form-login-hardware input[name="signature"]').value = signature.b64encoded

		if (mobile === true) {
			document.querySelector('#form-login-hardware input[name="ip_lan"]').value = configuration.ip
		} else {
			document.querySelector('#form-login-hardware input[name="ip_lan"]').value = configuration.piDevice.ip
		}

		// valid form
		document.querySelector('#form-login-hardware button').click()

	} else {
		showPairAgain()
	}
}

// gère le formulaire #form-new-harware après un hx-post
window.handleActivation = function (event) {
	const responseStatus = event.detail.xhr.status
	// console.log('-> handleActivation, responseStatus =', responseStatus)
	if (responseStatus === 201) {
		// save config app in local storage
		// console.log('new_hardware ok, configuration =', currentConfiguration)
		localStorage.setItem('laboutik', JSON.stringify(currentConfiguration))
		initLogin()
	}

	if (responseStatus === 400) {
		showPairAgain()
	}

}

// remplir le formulaire #form-new-harware et le valider
async function activateDevice(configuration) {
	log({ tag: 'info', msg: '-> activateDevice' })
	const configServer = configuration.servers.find(item => item.server === configuration.current_server)

	try {
		// generate client rsa keys pem
		const keysPemCashlessClient = await generatePemKeys()
		// add to configuration
		configuration['keysPemCashlessClient'] = keysPemCashlessClient

		// dev affiche le formulaire
		// document.querySelector('#form-new-harware').style.display = 'block'

		// remplir les inputs
		document.querySelector('#form-new-harware input[name="version"]').value = configuration.version
		document.querySelector('#form-new-harware input[name="username"]').value = configuration.client.username
		document.querySelector('#form-new-harware input[name="password"]').value = configuration.client.password
		document.querySelector('#form-new-harware input[name="hostname"]').value = configuration.hostname
		document.querySelector('#form-new-harware input[name="periph"]').value = configuration.front_type
		document.querySelector('#form-new-harware input[name="public_pem"]').value = configuration.keysPemCashlessClient.publicKey
		document.querySelector('#form-new-harware input[name="pin_code"]').value = configuration.pin_code
		if (mobile === true) {
			document.querySelector('#form-new-harware input[name="ip_lan"]').value = configuration.ip
		} else {
			document.querySelector('#form-new-harware input[name="ip_lan"]').value = configuration.piDevice.ip
		}

		// valid form
		document.querySelector('#form-new-harware button').click()
	} catch (error) {
		log('-> ActivateDevice,', error)
	}
}

// main
function initMain(configuration) {
	log({ tag: 'INFO', msg: '-> initMain' })
	// lecture fichier de conf ok
	if (configuration !== null) {

		// reset confLocalStorage si "login retour" !== "login confLocalStorage"
		if (confLocalStorage !== null && (configuration.client.password !== confLocalStorage.client.password || configuration.client.username !== confLocalStorage.client.username)) {
			localStorage.removeItem('laboutik')
			confLocalStorage = null
		}

		// login error = client null ou pas de serveur courant désigné
		if (configuration.client === null || configuration.current_server === "") {
			// nouvel appairage
			showPairAgain()
			return
		}

		// la configuration local n'existe pas
		if (confLocalStorage === null) {
			// console.log('. confLocalStorage = null => activateDevice()')
			activateDevice(configuration)
			return
		}

		initLogin()
	} else {
		log({ msg: 'Aucune configuration' })
	}

}

// mobile
if (mobile === true) {
	document.addEventListener('deviceready', async () => {
		log({ tag: 'INGO', msg: '-> mobile, deviceready' })
		const basePath = cordova.file.dataDirectory
		const pathToFile = basePath + cordovaFileName

		// read configuration file
		currentConfiguration = await readConfFile.cordova(pathToFile)
		initMain(currentConfiguration)
	})
} else {
	// pi, desktop

	// read configuration file
	currentConfiguration = await readConfFile.http(PORT)
	initMain(currentConfiguration)
}
