import { putLog } from './utils.js'
import { goServer, confirmDeleteServer } from "./utils.js"

function showInputPinCode() {
  // putLog('info', '-> showInputPinCode')
  // efface un ancien contenu de pin-code
  document.querySelector('#pin-code').value = ''
  // affiche l'interface "add palce"
  document.querySelector('.content-input').style.display = 'flex'
  // actualise le serveur discovery en cours
  document.querySelector('#label-server-pin-code').innerText = state.server_pin_code
  // insert dans le input permettant l'édition du serveur discovery le serveur en cours
  document.querySelector('#update-server-pin-code').value = state.server_pin_code
  // efface le input d'édition du serveur discovery
  document.querySelector('#update-server-pin-code').style.display = 'none'
  // supprime un ancien message de pin-code erroné
  document.querySelector('#pin-code-message').innerText = ''
  // supprime un ancien message de serveur discovery erroné
  document.querySelector('#retour-server-pin-code').innerText = ''
  // affiche l'ui serveur dicovery
  document.querySelector('.infos-server-pin-code').style.display = 'flex'
}

export function renderHtml(state) {
  // console.log('-> renderHtml - state =', state)
  let content = '', manage = ''
  if (state.networkStatus !== 'available' || state.nfcStatus !== 'available') {
    manage = 'devicesStatus'
    content += '<div class="status-body">'
    // network
    if (state.networkStatus !== 'available') {
      content += `
    <div class="status-item">
      <div class="status-messages">
        <div class="status-messages-icon">
          <img src="${location}assets/images/no-network.svg" />
        </div>
        <div class="status-messages-info">
          <div class="BF-ligne">- No connection.</div>
          <div class="BF-ligne">Activate wifi, xG network.</div>
        </div>
      </div>
    </div>`
    }

    // nfcStatus : disabled
    if (state.nfcStatus !== 'available') {
      content += `
    <div class="status-item">
      <div class="status-messages">
        <div class="status-messages-icon">
          <img src="${location}assets/images/no-nfc.svg" />
        </div>
    </div>`
    }
    content += '</div>'
  } else {
    manage = 'servers'
    content += `<div class="main-content">
    <div class="main-content-servers">`
    if (state.servers) {
      // show servers list
      for (const item of state.servers) {
        const hostname = (new URL(item.server_url)).hostname
        content += `<div class="servers-list-item">
      <div class="bt bt-go-server" data-server="${item.server_url}">${hostname}</div>
      <div class="bt bt-delete-server" data-server="${item.server_url}">Delete</div> 
    </div>`
      }
    }
    content += `</div>
    <div class="main-content-footer">
      <div class="bt no-select">Add place</div>
    </div>
  </div>`
  }
  document.querySelector('main').innerHTML = content

  if (manage === 'servers') {
    // listen bt 'add place'
    document.querySelector('.main-content-footer .bt').addEventListener('click', showInputPinCode)

    // listen all .bt-go-server elements
    document.querySelectorAll('.bt-go-server').forEach((element) => {
      element.addEventListener('click', goServer)
    })

    // listen all .bt-delete-server elements
    document.querySelectorAll('.bt-delete-server').forEach((element) => {
      element.addEventListener('click', confirmDeleteServer)
    })
  }
}
