/** ask_primary_card.html et le point d'entrée front de l'application laboutik.
 * récupération du type d'application cordova/pi/desktop par l'url de la page 
 * pour toute l'aplication
 */

// port socketIo pour application pi et desktop
state.socketIoPort = 3000 

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
    const response = await fetch(`http://localhost:${state.socketIoPort}/read_config_file`, {
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

/**
 * Load config file in state.configFile
 * @param {string} typeApp - cordova/pi/desktop 
 */
async function loadConfigFile(typeApp) {
  // console.log('-> loadConfigFile - typeApp =', typeApp)
  let configFile = null
  if (typeApp !== 'cordova') {
    configFile = await readConfFile()
  } else  {
    configFile = await cordovaReadConfFile()
  }
  state['configFile'] = configFile
  // stockage configFile
  localStorage.setItem("configFile", JSON.stringify(configFile));
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


/**
 * Attend le chargement de la page
 */
document.addEventListener("DOMContentLoaded", () => {
  // écoute des commandes/évènements sur le formulaire "#form-nfc"
  document.querySelector('#form-nfc').addEventListener('primaryCardManageForm', primaryCardManageForm)

  // ajout du type_app dans le formulaire
  document.querySelector('input[name="type_app"]').value = state.typeApp

  // entrée front de l'application, chargement du fichier de configuration
  if (state.typeApp !== 'cordova') {
    // application non cordova, page chargée
    loadConfigFile(state.typeApp)
  } else {
    // application cordova, attent que les périphériques soient pris en compte :
    document.addEventListener('deviceready', async () => {
      loadConfigFile(state.typeApp)
    })
  }
})