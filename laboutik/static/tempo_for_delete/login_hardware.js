console.log('DEMO =', state.demo.active)

import { generatePemKeys, signMessage } from './modules/cryptoRsa.js'
import { readConfFile, writeConfFile, isCordovaApp } from './modules/hardwareLayer.js'

// port serveur localpour pi et desktop
const PORT = 3000
const mobile = isCordovaApp()
const cordovaFileName = 'configLaboutik.json'

// get configuration save in localstorage
let confLocalStorage = JSON.parse(localStorage.getItem('laboutik'))

async function updateConfigurationFile(configuration) {
	if (mobile === true) {
		result = await writeConfFile.cordova(basePath, cordovaFileName, configuration)
	} else {
		result = await writeConfFile.http(configuration, PORT)
	}
	return result
}

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


function showPairAgain() {
  console.log('-> showPairAgain')
	localStorage.removeItem('laboutik')
	document.querySelector('#new-pair').classList.remove('hide')
}

window.laboutikNewPair = async function () {
	const result = await deleteConfs()
	let redirectionUrl = `http://localhost:${PORT}`
	if (mobile === true) {
		redirectionUrl = 'http://localhost/index.html'
	}
	// console.log('result =', result)
	if (result === true) {
		// redirection
		window.location.href = redirectionUrl
	} else {
		console.log('newPair, erreur maj configuration')
	}
}

async function initLogin() {
	console.log('-> initLogin')
	const configuration = JSON.parse(localStorage.getItem('laboutik'))
	// console.log('-> configuration =', configuration)

	if (configuration !== null) {
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

// remplir le formulaire #form-new-hardware et le valider
async function activateDevice(configuration) {
	console.log('-> activateDevice')
	try {
		// generate client rsa keys pem
		const keysPemCashlessClient = await generatePemKeys()
		// to add in local configuration
		localStorage.setItem('keysPemCashlessClient', JSON.stringify(keysPemCashlessClient))

		// dev affiche le formulaire
		//document.querySelector('#form-new-hardware').style.display = 'block'

		// remplir les inputs
		document.querySelector('#form-new-hardware input[name="version"]').value = configuration.version
		document.querySelector('#form-new-hardware input[name="username"]').value = configuration.client.username
		document.querySelector('#form-new-hardware input[name="password"]').value = configuration.client.password
		document.querySelector('#form-new-hardware input[name="hostname"]').value = configuration.hostname
		document.querySelector('#form-new-hardware input[name="periph"]').value = configuration.front_type
		document.querySelector('#form-new-hardware input[name="public_pem"]').value = keysPemCashlessClient.publicKey
		document.querySelector('#form-new-hardware input[name="pin_code"]').value = configuration.pin_code
		if (mobile === true) {
			document.querySelector('#form-new-hardware input[name="ip_lan"]').value = configuration.ip
		} else {
			document.querySelector('#form-new-hardware input[name="ip_lan"]').value = configuration.piDevice.ip
		}

		// valid form
		document.querySelector('#form-new-hardware button').click()
	} catch (error) {
		console.log('-> ActivateDevice,', error)
	}
}


// main
function initMain(configuration) {
  console.log('-> initMain, configuration =', configuration);
  
	try {
		//configuration fichier existe
		if (configuration !== null) {
       console.log('- configuration différente null');

			// configuration locale n'existe pas
			if (confLocalStorage === null) {
         console.log('- confLocalStorage = null');
				// le périphérique n'est pas activé
				if (activation === false) {
					activateDevice(configuration)
				}
				// le périphérique est activé
				if (activation) {
					const keysPemCashlessClient = JSON.parse(localStorage.getItem('keysPemCashlessClient'))
					configuration['keysPemCashlessClient'] = keysPemCashlessClient
					// enregidtrement local de la configuration et login
					localStorage.setItem('laboutik', JSON.stringify(configuration))
					// supprime donnée temporaire
					localStorage.removeItem('keysPemCashlessClient')
					initLogin()
				}
			}

			// configuration locale existe
			if (confLocalStorage !== null) {
				// configuration = configuration locale
				if (configuration.client.password === confLocalStorage.client.password && configuration.client.username === confLocalStorage.client.username) {
					initLogin()
				} else {
					// configuration !== configuration locale
					deleteConfs()
					showPairAgain()
				}
			}

			console.log('confLocalStorage =', confLocalStorage);

		} else {
			console.log('Aucune configuration')
			showPairAgain()
		}
	} catch (error) {
		console.log('initMain - error :', error.message);
	}
}

// mobile
if (mobile === true) {
	document.addEventListener('deviceready', async () => {
		console.log('-> mobile, deviceready')
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
