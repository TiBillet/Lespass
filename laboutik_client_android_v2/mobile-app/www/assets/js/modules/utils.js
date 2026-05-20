import { renderHtml } from './renderHtml.js'
import { env } from '../../../env.js'
// dev
import './dev.js'

export function putLog(typeMsg, msg, options) {
  let msgFinal = ''
  if (options !== undefined) {
    if (typeof (options) === 'string') {
      msgFinal = msg + ' ' + options
    }
    if (typeof (options) === 'object') {
      msgFinal = msg + ' ' + JSON.stringify(options, null, 2)
    }
    console.log(msg, options)
  } else {
    msgFinal = msg
    console.log(msg)
  }

  document.querySelector('.logs-content').insertAdjacentHTML('beforeend', `<div style="color: var(--${typeMsg});">${msgFinal}</div>`)
}

export function showLogs() {
  const logs = document.querySelector('.logs-content')
  logs.classList.toggle('showasblock')
  const showasblockExist = logs.classList.contains('showasblock')
  if (showasblockExist) {
    logs.style.display = 'block'
  } else {
    logs.style.display = 'none'
  }
}

function showSpinner() {
  const spinner = document.querySelector('.spinner')
  spinner.style.display = "flex"
}

function hideSpinner() {
  const spinner = document.querySelector('.spinner')
  spinner.style.display = "none"
}

/**
 * Vérifie le parse
 * @param {string} content 
 * @returns 
 */
function ParseStringToObject(content) {
  try {
    return JSON.parse(content)
  } catch (error) {
    putLog('error', '-> ParseStringToObject,', error)
  }
}

/**
 * read file
 * @returns {string} string content file
 */
async function cordovaReadFile(pathFile) {
  // console.log('-> readFile')
  showSpinner()
  return await new Promise((resolve) => {
    window.resolveLocalFileSystemURL(pathFile, function (fileEntry) {
      fileEntry.file(function (file) {
        const reader = new FileReader()
        reader.onloadend = function () {
          hideSpinner()
          resolve(this.result)
        }
        reader.readAsText(file)
      }, () => {
        hideSpinner()
        resolve(null)
      })
    }, () => {
      hideSpinner()
      resolve(null)
    })
  })
}

/**
 * Retourne le fichier de configuration si il existe, sinon env
 * @returns {object|null} The configuration object | null
 */
export async function readConfFile() {
  // console.log('-> readConfFile')
  try {
    let configFile
    const pathFile = cordova.file.dataDirectory + 'configLaboutik.json'
    const confFile = await cordovaReadFile(pathFile)

    if (confFile !== null) {
      configFile = ParseStringToObject(confFile)
    } else {
      configFile = env
      configFile['version'] = env.version
      // création du fichier de configuration
      const result = await writeConfigFile(configFile)
      if (result === false) {
        throw new Error('update/create file - backup error.')
      }
    }
    return configFile
  } catch (error) {
    putLog('error', 'readConfigFile,', error)
    return null
  }
}

/**
 * Write configuration file
 * @param {object} config file
 * @returns {boolean}
 */
async function writeConfigFile(confFile) {
  // console.log('2 -> writeConfigFile, confFile =', confFile)
  const data = JSON.stringify(confFile)
  return await new Promise((resolve) => {
    window.resolveLocalFileSystemURL(cordova.file.dataDirectory, function (directoryEntry) {
      directoryEntry.getFile('configLaboutik.json', { create: true },
        function (fileEntry) {
          fileEntry.createWriter(function (fileWriter) {
            fileWriter.onwriteend = function () {
              // file write ok
              resolve(true)
            }
            fileWriter.onerror = function (e) {
              // you could hook this up with our global error handler, or pass in an error callback
              resolve(false)
            }
            const blob = new Blob([data], { type: 'text/plain' })
            fileWriter.write(blob)
          }, () => { resolve(false) })
        }, () => { resolve(false) })
    }, () => { resolve(false) })
  })
}


/**
 * Change background color of general status
 * @param {string} status - error|success|info|warning
 */
export function setGeneralStatus(status) {
  document.querySelector('.header-status').style.backgroundColor = `var(--${status})`
}

export async function testNetworkStatus(timeout = 5000) {
  const urls = [
    "https://httpbin.org/get",
    "https://www.google.com/generate_204",
    "https://postman-echo.com/get"
  ]
  const promises = urls.map(async (url) => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeout)
    try {
      const response = await fetch(url, {
        method: "HEAD",
        mode: "no-cors",
        signal: controller.signal,
        cache: "no-store"
      })
      clearTimeout(timer)
      return response
    } catch (error) {
      clearTimeout(timer)
      return null
    }
  })
  const responses = await Promise.all(promises);

  if (responses.filter(item => item !== null).length >= 1) {
    return 'available'
  }
  return 'disable'
}

/**
 * Listen required devices status
 */
export async function initListenDevicesStatus() {
  // console.log('-> initListenDevicesStatus')
  try {
    // NFC : available / disabled
    const nfcStatus = await nfcPlugin.available()
    if (nfcStatus !== 'available') {
      putLog('error', 'nfcStatus =', nfcStatus)
      setGeneralStatus('error')
    } else {
      setGeneralStatus('success')
    }
    state['nfcStatus'] = nfcStatus

    // network :available / disabled
    const networkStatus = await testNetworkStatus()
    if (networkStatus === 'disable') {
      putLog('error', 'networkStatus =', networkStatus)
      setGeneralStatus('error')
    } else {
      setGeneralStatus('success')
    }
    state['networkStatus'] = networkStatus
  } catch (error) {
    putLog('error', "-> initListenDevicesStatus,", error)
    setGeneralStatus('error')
  }

  renderHtml(state)
  // relance les écoutes dans 5 secondes
  const timeoutId = setTimeout(initListenDevicesStatus, 5000)
}


/**
 * Post le pinCode au serveur discovery pour récupérer
 * @param {int} pinCode 
 * @returns {object} 
 */
async function getServerInfos(pinCode) {
  // putLog('info', '-> getServerInfos  -- type pinCode =', pinCode, typeof (pinCode))
  try {
    // requête à l'app django discovery
    showSpinner()
    const response = await fetch(state.server_pin_code + '/api/discovery/claim/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        pin_code: pinCode
      })
    })
    const retour = await response.json()
    hideSpinner()
    if (response.status === 200) {
      return { error: false, server: retour }
    } else {
      return { error: true, msgs: retour.pin_code }
    }
  } catch (error) {
    hideSpinner()
    putLog('error', 'error:', error)
  }
}

/**
 * Go server - post api_key and follow back redirection
 * @param {object} event 
 */
export async function goServer(event) {
  // console.log('-> goServer')
  showSpinner()

  const url = event.target.getAttribute('data-server')
  const data = state.servers.find(item => item.server_url === url)
  // console.log('data =', data)

  // TODO: peut être ajouter le current server dans config file.

  // Soumission POST via formulaire natif pour éviter les restrictions CORS/fetch
  // et garantir la transmission du cookie session sur la redirection Django
  const form = document.createElement('form')
  form.method = 'POST'
  form.action = url + '/laboutik/auth/bridge/'

  const input = document.createElement('input')
  input.type = 'hidden'
  input.name = 'api_key'
  input.value = data.api_key

  const input2 = document.createElement('input')
  input2.type = 'hidden'
  input2.name = 'type_app'
  console.log('state.type_app =', state.type_app);

  input2.value = state.type_app

  form.appendChild(input)
  form.appendChild(input2)
  document.body.appendChild(form)
  form.submit()
}

/**
 * Delete server in list after click button "Delete"
 * @param {object} event 
 */
export async function confirmDeleteServer(event) {
  console.log('-> confirmDeleteServer')
  // show window confirmation
  document.querySelector('.confirm-container').style.display = "flex"
  // ajoute l'url du serveur cliqué dans le bouton valider
  const url = event.target.getAttribute('data-server')
  document.querySelector('.bt-delete-validate').setAttribute('data-server', url)
}


/**
 * Delete server in list after click button "Delete"
 * @param {object} event 
 */
export async function deleteServer(event) {
  // console.log('-> deleteServer')

  // hide window confirmation
  document.querySelector('.confirm-container').style.display = "none"

  const url = event.target.getAttribute('data-server')
  let typeMsg = "success"

  // copie l'ancien state
  const oldState = structuredClone(state)

  // trouver tous les servers sauf url
  const filterServers = state.servers.filter(item => item.server_url !== url)
  state.servers = filterServers

  // update conFile
  const updateConfFile = await writeConfigFile(state)

  // retour à l'ancien state si fichier pas sauvegardé
  if (updateConfFile === false) {
    state = structuredClone(oldState)
    oldState = null
    typeMsg = "error"
  }
  // putLog(typeMsg, 'update config file, after delete server =', updateConfFile)

  // render
  renderHtml(state)
}

/**
 * Vérifie la conformité du pinCode (entier de 6 chiffres)
 * le clavier android fourni au 'input type="number"' un nombre ou une valeur ''
 * @param {object} event 
 */
export async function managedPinCode(event) {
  // TODO: attention au clavier virtuel pour la version pi
  const label = document.querySelector('#pin-code-message')
  let pinCode
  if (event.key === 'Enter') {
    event.target.blur()
    try {
      pinCode = document.querySelector('#pin-code').value
      // pas vide
      if (pinCode === '') {
        throw new Error('no pin code !')
      } else {
        // ce n'est pas un entier
        if (pinCode.includes('.')) {
          throw new Error("It's not an integer !")
        }
        // il faut 6 chiffres
        if (pinCode.length > 6 || pinCode.length < 6) {
          throw new Error('You need 6 digits for the pin code !')
        }
      }

      // pinCode entré -> get server
      const result = await getServerInfos(parseInt(pinCode))
      let typeMsg = "success"

      if (result.error === false) {
        // cache la vue permettant d'entrer le pincode
        document.querySelector('.content-input').style.display = 'none'

        // copie l'ancien state
        const oldState = structuredClone(state)

        // add server in servers list
        state.servers.push(result.server)

        // update conFile
        const updateConfFile = await writeConfigFile(state)

        // retour à l'ancien state si fichier pas sauvegardé
        if (updateConfFile === false) {
          state = structuredClone(oldState)
          oldState = null
          typeMsg = "error"
        }

        putLog('typeMsg', 'update config file, add server =', updateConfFile)
        // render
        showMainContent(state)

      } else {
        result.msgs.forEach(msg => {
          throw new Error(msg)
        })
      }

    } catch (error) {
      // putLog('error','error =', error)
      label.textContent = error
    }
  } else {
    label.textContent = ''
  }
}
