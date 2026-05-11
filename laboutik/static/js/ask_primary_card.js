// point d'entré de l'app laboutik
globalThis.state = {
  confFile: null, // fichier de configuration pour la persistance des données
  nfc: null  // instance global du lecteur nfc
}

const PORT = 3000

/**
 * Is cordova application ?
 * @public
 * @returns {boolean}
 */
function isCordovaApp() {
  try {
    if (cordova) {
      return true
    }
  } catch (error) {
    return false
  }
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
async function readConfFile() {
  try {
    const response = await fetch(`http://localhost:${PORT}/read_config_file`, {
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

async function initApp(typeApp) {
  if (typeApp === 'pi/desktop') {
    console.log('app pi/desktop !')
    state.confFile = await readConfFile()
  }

  if (typeApp === 'cordova') {
    console.log('app cordova !')
    state.confFile = await cordovaReadConfFile()
  }
  state.nfc = new NfcReader()
  initNfc()
}


/**
 * TODO
 * pi et desktop :
 * affectation des propriétées de state
 */
document.addEventListener("DOMContentLoaded", () => {
  // écoute des commandes sur le formulaire "#form-nfc"
  document.querySelector('#form-nfc').addEventListener('primaryCardManageForm', primaryCardManageForm)

  if (isCordovaApp() === false) {
    initApp('pi/desktop')
  } else {
    document.addEventListener('deviceready', async () => {
      initApp('cordova')
    })
  }
})