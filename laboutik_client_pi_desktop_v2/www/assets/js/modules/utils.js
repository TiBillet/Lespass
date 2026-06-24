import { renderHtml } from './renderHtml.js'

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
 * read a configuration file from an http server
 * @returns {object|null} - configuration
 */
export async function readConfFile() {
  // console.log('-> readConfFile')
  try {
    showSpinner()
    // PORT est déclaré dans index.html
    const response = await fetch(`http://localhost:${PORT}/read_config_file`, {
      method: "GET",
      mode: 'cors'
    })
    if (response.status === 400) {
      throw new Error('update/create file - backup error.')
    }
    const result = await response.json()
    hideSpinner()
    return result
  } catch (error) {
    hideSpinner()
    putLog('error', 'readConfigFile,', error)
    return null
  }
}

/**
 * Write configuration file
 * @param {object} config file
 * @returns {boolean}
 */
export async function writeConfFile(content) {
  // console.log('-> writeConfFile - content =', content)
  try {
    // PORT est déclaré dans index.html
    const response = await fetch(`http://localhost:${PORT}/write_config_file`, {
      method: "POST",
      mode: 'cors',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(content)
    })
    // const result = await response.json()
    if (response.status !== 200) {
      throw new Error('Erreur lors de la création/mise a jour du fichier de configuration.')
    }
    return true
  } catch (error) {
    console.log('util.js - writeConfFile,', error)
    return false
  }

}

/**
 * Change background color of general status
 * @param {string} status - error|success|info|warning
 */
export function setGeneralStatus(status) {
  document.querySelector('.header-status').style.backgroundColor = `var(--${status})`
}


// écoute les messages du back
function listens(socket) {
  socket.on('networkStatus', (status) => {
    if (status === 'disable') {
      putLog('error', 'networkStatus =', status)
      setGeneralStatus('error')
    } else {
      setGeneralStatus('success')
    }
    state['networkStatus'] = status
    renderHtml(state)
  })

  socket.on('nfcMessage', (msg) => {
    // console.log('- nfcMessage =', msg)
    if (msg.status) {
      if (msg.status === 'disable') {
        putLog('error', 'nfcStatus =', msg.status)
        setGeneralStatus('error')
      } else {
        setGeneralStatus('success')
      }
      state['nfcStatus'] = msg.status
      renderHtml(state)
    }
  })

  socket.on('printersStatus', (printersStatus) => {
    // console.log('- printersStatus =', printersStatus)
    state['printersStatus'] = printersStatus
    renderHtml(state)
  })

}

export function initBridgeHardFront() {
  try {
    const socket = io(location.origin)
    listens(socket)
    socket.on("connect", () => {
      console.log('socket.io - client connecté - ', new Date())
    })
  } catch (error) {
    putLog('error', '-> initSocketIo -', error)
  }
}


/**
 * Post le pinCode au serveur discovery pour récupérer
 * @param {int} pinCode 
 * @returns {object} 
 */
async function getServerInfos(pinCode) {
  // putLog('info', '-> getServerInfos  -- type pinCode =', pinCode)
  try {
    // requête à l'app django discovery
    showSpinner()
    // '/api/discovery/claim/' = url pour proxy serveur
    const response = await fetch('/api/discovery/claim/', {
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
  // console.log('data =', data);

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
  const updateConfFile = await writeConfFile(state)

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

        // update conFile = state
        const updateConfFile = await writeConfFile(state)
        // retour à l'ancien state si fichier pas sauvegardé
        if (updateConfFile === false) {
          state = structuredClone(oldState)
          oldState = null
          typeMsg = "error"
        }

        putLog(typeMsg, 'Update config file, add server =', updateConfFile)
        // render
        renderHtml(state)
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
