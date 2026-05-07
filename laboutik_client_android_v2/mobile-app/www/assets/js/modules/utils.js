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
  console.log('-> initListenDevicesStatus');
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
 * Write configuration file
 * @param {object} confFile
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
 * read a  file
 * @returns {string} string content file
 */
async function cordovaReadFile(pathFile) {
  console.log('-> readFile')
  return await new Promise((resolve) => {
    window.resolveLocalFileSystemURL(pathFile, function (fileEntry) {
      fileEntry.file(function (file) {
        const reader = new FileReader()
        reader.onloadend = function () {
          resolve(this.result)
        }
        reader.readAsText(file)
      }, () => {
        resolve(null)
      })
    }, () => {
      resolve(null)
    })
  })
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
 * Retour le fichier de configuration si il existe, sinon env
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
      const result = writeConfigFile(configFile)
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

async function getServerInfos(pinCode) {
  putLog('info', '-> getServerInfos  -- type pinCode =', pinCode)
  const confFile = await readConfFile()
  putLog('info', 'confFile = ', confFile)
  try {
    // requête à l'app django discovery
    showSpinner()
    const response = await fetch(confFile.server_pin_code + '/api/discovery/claim/', {
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


export async function goServer(event) {
  /*
  const url = event.target.getAttribute('data-server')
  const confFile = await readConfFile()
  confFile.currentServer = url
  // update conFile
  const updateConfFile = await writeFile(confFile)
  putLog('info', 'update config file, current server =', updateConfFile)

  const data = confFile.servers.find(item => item.server_url === url)

  // Soumission POST via formulaire natif pour éviter les restrictions CORS/fetch
  // et garantir la transmission du cookie session sur la redirection Django
  const form = document.createElement('form')
  form.method = 'POST'
  form.action = url + '/laboutik/auth/bridge/'

  const input = document.createElement('input')
  input.type = 'hidden'
  input.name = 'api_key'
  input.value = data.api_key

  form.appendChild(input)
  document.body.appendChild(form)
  form.submit()
  */
}

export async function deleteServer(event) {
  /*
  const url = event.target.getAttribute('data-server')
  let confFile = await readConfFile()
  // trouver tous les servers sauf url
  const filterServers = confFile.servers.filter(item => item.server_url !== url)
  confFile.servers = filterServers
  // update conFile
  const updateConfFile = await writeFile(confFile)
  putLog('info', 'update config file, after delete server =', updateConfFile)
  // render
  showMainContent(confFile)
*/
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

      if (result.error === false) {
        const confFile = await readConfFile()
        // cache la vue permettant d'entrer le pincode
        document.querySelector('.content-input').style.display = 'none'
        // add server in servers list
        confFile.servers.push(result.server)
        // update conFile
        const updateConfFile = await writeFile(confFile)
        putLog('info', 'update config file, add server =', updateConfFile)
        // render
        showMainContent(confFile)

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
