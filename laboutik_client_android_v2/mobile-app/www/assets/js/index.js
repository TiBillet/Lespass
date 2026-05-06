import {
  getDevicesStatusAndShow,
  awaitDevicesOk,
  getConfFile,
  showLogs,
  managedPinCode,
  updateCurrentServerAndGoServer
} from "./modules/utils.js"
import { showMainContent } from './modules/renderHtml.js'


/**
 * wait cordova (devices activation)
 */
document.addEventListener('deviceready', async () => {
  window.state = {}
  const confFile = await getConfFile()
  // étape 1/init - affectation des propriétées de state 
  for (const key in confFile) {
    state[key] = confFile[key]
  }
  state['step'] = 'init'

  // 2 required devices status
  const result = getDevicesStatusAndShow()
  if (result.nfcStatus !== 'enabled' || result.networkOK !== true) {
    await awaitDevicesOk()
  }

  // 3 - affiche la liste des serveurs et le "boutan add place"
  showMainContent(confFile)
})

document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('.logs-icon').addEventListener('click', showLogs)
  // validation du pincode
  document.querySelector('#pin-code').addEventListener('keydown', managedPinCode)
})