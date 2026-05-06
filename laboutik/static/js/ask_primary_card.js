// point d'entré de l'app laboutik
globalThis.state = {
  confFile: null, // fichier de configuration pour la persistance des données
  nfc: null  // instance global du lecteur nfc
}

/**
 * Read the configuration file
 * @returns {object} - configuration
 */
async function cordovaReadConfFile() {
  const pathFile = cordova.file.dataDirectory + 'configLaboutik.json'
  return await new Promise((resolve) => {
    window.resolveLocalFileSystemURL(pathFile, function (fileEntry) {
      fileEntry.file(function (file) {
        const reader = new FileReader()
        reader.onloadend = function () {
          resolve(JSON.parse(this.result))
        }
        reader.readAsText(file)
      }, () => {
        console.warn('- info, read "configLaboutik.json" failed !')
        resolve(null)
      })
    }, () => {
      console.warn('- info, read "configLaboutik.json" failed !')
      resolve(null)
    })
  })
}


/**
 * read a configuration file from an http server
 * @returns {object} - configuration
 */
async function fetchConfFile() {
  try {
    const response = await fetch('http://localhost:3000/config_file', {
      method: "GET",
      mode: 'cors'
    })
    //TODO: vérifier que le retour de la fonction est un objet
    return await response.json()
  } catch (error) {
    console.log('httpReadFromFile,', error)
    return null
  }
}

// gestionnaire du formulaire
function primaryCardManageForm(event) {
  try {
    const data = event.detail
    const form = document.querySelector('#form-nfc')

    // update input
    if (data.actionType === 'updateInput') {
      form.querySelector(data.selector).value = data.value
    }

    // change post url
    if (data.actionType === 'postUrl') {
      form.setAttribute('hx-post', data.value)
      htmx.process(form)
    }

    // submit form
    if (data.actionType === 'submit') {
      form.setAttribute('hx-trigger', 'click')
      htmx.process(form)
      // submit
      form.click()
    }

  } catch (error) {
    console.log('-> addition.js - additionManageForm,', error)
  }
}

async function initStateForPiDesktop() {
  console.log('pi/desktop')
  // TODO: ajouter la route http://localhost:3000/config_file au nfcServer.js
  // state.confFile = await fetchConfFile() 
  state.nfc = new NfcReader()
  initNfc()
}

/**
 * cordova :
 * attente de la prise en compte des périphériques
 * affectation des propriétées de state
 */
document.addEventListener('deviceready', async () => {
  console.log('cordova - deviceready')
  state.confFile = await cordovaReadConfFile()
  state.nfc = new NfcReader()
  initNfc()
})


/**
 * TODO
 * pi et desktop :
 * affectation des propriétées de state
 */
document.addEventListener("DOMContentLoaded", () => {
  // écoute des commandes sur le formulaire "#form-nfc"
  document.querySelector('#form-nfc').addEventListener('primaryCardManageForm', primaryCardManageForm)

  if (isCordovaApp() === false) {
    initStateForPiDesktop()
  }
})