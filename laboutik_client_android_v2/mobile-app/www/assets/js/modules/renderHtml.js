import { putLog } from './utils.js'
import { goServer, confirmDeleteServer } from "./utils.js"

function showInputPinCode() {
  // putLog('info', '-> showInputPinCode')
  document.querySelector('.content-input').style.display = 'flex'
}

export function renderHtml(state) {
  let content = '', manage = ''
  if (state.networkStatus !== 'available' || state.nfcStatus !== 'available') {
    manage = 'devicesStatus'
    content += '<div class="status-body">'
    // network disable
    if (state.networkStatus !== 'available') {
      content += `
    <div class="status-item">
      <div class="status-messages">
        <div class="status-messages-icon">
          <img src="http://localhost/assets/images/no-network.svg" />
        </div>
        <div class="status-messages-info">
          <div class="BF-ligne">- No connection.</div>
          <div class="BF-ligne">Activate wifi, xG network.</div>
        </div>
      </div>
      <div class="status-action">
        <div class="bt" onclick="ConnectivityPlugin.openWifiSettings()">Settings network</div>
      </div>
    </div>`
    }

    // no nfc
    if (state.nfcStatus !== 'available') {
      content += `
    <div class="status-item">
      <div class="status-messages">
        <div class="status-messages-icon">
          <img src="http://localhost/assets/images/no-nfc.svg" />
        </div>`
    }
    // désactivé
    if (state.nfcStatus === 'disabled') {
      content += `
        <div class="status-messages-info">
          <div class="BF-ligne">NFC disabled</div>
          <div class="BF-ligne">Activate NFC</div>
        </div>
      </div>
      <div class="status-action">
        <div class="bt" onclick="ConnectivityPlugin.openNfcSettings()">Settings NFC</div>
      </div>`
    } else {
      // no nfc on devices
      content += `
        <div class="status-messages-info">
          <div>No NFC on this device</div>
        </div>
      </div>
      <div class="status-action">
        <div class="bt" onclick="navigator.app.exitApp();">Exit app</div>
      </div>`
    }
    content += '</div>'
  } else {
    manage = 'servers'
    content += `
    <div class="main-content">
      <div class="main-content-servers">`
    if (state.servers) {
      // show servers list
      for (const item of state.servers) {
        const hostname = (new URL(item.server_url)).hostname
        content += `
        <div class="servers-list-item">
          <div class="bt bt-go-server" data-server="${item.server_url}">${hostname}</div>
          <div class="bt bt-delete-server" data-server="${item.server_url}">Delete</div> 
        </div>`
      }
    }
    content += `
      </div>
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
