import { putLog } from './utils.js'
import { updateCurrentServerAndGoServer, deleteServer } from "./utils.js"


export function showDevicesStatus(ctx) {
  let alertContent = '<div class="status-body">'
  // network
  if (ctx.networkOK === false) {
    alertContent += `
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

  // not_available / enabled / disabled
  if (ctx.nfcStatus !== 'enabled') {
    alertContent += `
    <div class="status-item">
      <div class="status-messages">
        <div class="status-messages-icon">
          <img src="http://localhost/assets/images/no-nfc.svg" />
        </div>`

    if (ctx.nfcStatus === 'disabled') {
      alertContent += `
        <div class="status-messages-info">
          <div class="BF-ligne">NFC disabled</div>
          <div class="BF-ligne">Activate NFC</div>
        </div>
      </div>
      <div class="status-action">
        <div class="bt" onclick="ConnectivityPlugin.openNfcSettings()">Settings NFC</div>
      </div>`
    } else {
      alertContent += `
        <div class="status-messages-info">
          <div>No NFC on this device</div>
        </div>
      </div>
      <div class="status-action">
        <div class="bt" onclick="navigator.app.exitApp();">Exit app</div>
      </div>`
    }
    alertContent += '</div>'
  }

  alertContent += '</div>'
  document.querySelector('main').innerHTML = alertContent
}

function showInputPinCode() {
  // putLog('info', '-> showInputPinCode')
  document.querySelector('.content-input').style.display = 'flex'
}

export function showMainContent(confFile) {
  // putLog('info', '-> showMainContent', confFile)
  let content = `<div class="main-content">
    <div class="main-content-servers">`
  // show servers list
  for (const item of confFile.servers) {
    const hostname = (new URL(item.server_url)).hostname
    content += `<div class="servers-list-item">
      <div class="bt bt-go-server" data-server="${item.server_url}">${hostname}</div>
      <div class="bt bt-delete-server" data-server="${item.server_url}">Delete</div> 
    </div>`
  }

  content += `</div>
    <div class="main-content-footer">
      <div class="bt no-select">Add place</div>
    </div>
  </div>`
  document.querySelector('main').innerHTML = content

  // listen bt 'add place'
  document.querySelector('.main-content-footer .bt').addEventListener('click', showInputPinCode)

  // listen all .bt-go-server elements
  document.querySelectorAll('.bt-go-server').forEach((element) => {
    element.addEventListener('click', updateCurrentServerAndGoServer)
  })

  // listen all .bt-delete-server elements
  document.querySelectorAll('.bt-delete-server').forEach((element) => {
    element.addEventListener('click', deleteServer)
  })
}
