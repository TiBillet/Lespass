import { showDevicesStatus, showMainContent } from './renderHtml.js'
import { env } from '../../../env.js'

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

async function testNetWorkOk(url = "https://api.github.com", timeout = 3000, retries = 2) {
  let test = false
  async function tryFetch() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
      showSpinner()
      const response = await fetch(url, {
        method: "HEAD",
        signal: controller.signal,
        cache: "no-store"
      })
      return true
    } catch (error) {
      return false
    } finally {
      clearTimeout(timer)
      hideSpinner()
    }
  }

  for (let i = 0; i < retries; i++) {
    test = await tryFetch()
  }

  return test
}

export async function getDevicesStatusAndShow() {
  // console.log('-> getDevicesStatusAndShow')
  // NFC : not_available / enabled / disabled
  const nfcStatus = (await ConnectivityPlugin.getNfcStatus()).status
  // réseau : true / false
  const networkOK = await testNetWorkOk()
  showDevicesStatus({ networkOK, nfcStatus })
  return { nfcStatus, networkOK }
}

export async function awaitDevicesOk() {
  return new Promise((resolve) => {
    const testNetWorkOk = setInterval(async () => {
      const result = await getDevicesStatusAndShow()
      if (result.nfcStatus === 'enabled' && result.networkOK === true) {
        clearInterval(testNetWorkOk)
        resolve(result)
      }
    }, 3000)
  })
}

/**
 * 
 * @returns {object} - configuration
 */
async function readConfFile() {
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
        putLog('error', `- info, read "configLaboutik.json" failed !`)
        resolve(null)
      })
    }, () => {
      putLog('error', `- info, read "configLaboutik.json" failed !`)
      resolve(null)
    })
  })
}

/**
 * Write configuration file
 * @param {object} confFile
 * @returns {boolean}
 */
async function writeFile(confFile) {
  // console.log('-> writeToFile, saveFileName =', state.saveFileName, '  --  basePath =', state.basePath)
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
              putLog('error', `- info, write "configLaboutik.json" failed: ${e.toString()}`)
              resolve(false)
            }
            const blob = new Blob([data], { type: 'text/plain' })
            fileWriter.write(blob)
          }, () => { resolve(false) })
        }, () => { resolve(false) })
    }, () => { resolve(false) })
  })
}

export async function getConfigurationAndSave() {
  //confFile = fichier sauvegardé dans dossier app
  let confFile = await readConfFile()
  if (confFile === null) {
    // confFile = fichier env.js dans www
    confFile = env

    /*
    // dev mock
    env.servers = [
      { server_url: 'https://lespass.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini' },
      { server_url: 'https://lespass1.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-1' },
      { server_url: 'https://lespass2.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-2' },
      { server_url: 'https://lespass3.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-3' },
      { server_url: 'https://lespass4.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-4' },
      { server_url: 'https://lespass5.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-5' },
      { server_url: 'https://lespass6.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-6' },
      { server_url: 'https://lespass7.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-7' },
      { server_url: 'https://lespass8.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-8' },
      { server_url: 'https://lespass9.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-9' },
      { server_url: 'https://lespass10.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-10' },
      { server_url: 'https://lespass11.filaos.re', api_key: 'ZtYOljZ6.pOOzpDrZxBgNldQ6hljZnCC1gfnxXWcY', device_name: 'd3mini-11' },
    ]
    */

    // création confFile
    await writeFile(confFile)
  }

  return confFile
}

async function getServerInfos(pinCode) {
  putLog('info', '-> getServerInfos  -- type pinCode =', pinCode)
  const confFile = await readConfFile()
  putLog('info','confFile = ', confFile)
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


export async function updateCurrentServerAndGoServer(event) {
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
}

export async function deleteServer(event) {
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