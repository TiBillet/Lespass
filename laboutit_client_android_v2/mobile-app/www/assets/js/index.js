import {
  getDevicesStatusAndShow,
  awaitDevicesOk,
  getConfigurationAndSave,
  showLogs,
  managedPinCode,
  updateCurrentServerAndGoServer
} from "./modules/utils.js"
import { showMainContent } from './modules/renderHtml.js'

/**
 * wait cordova (devices activation)
 */
document.addEventListener('deviceready', async () => {
  // 1  devices status
  const result = getDevicesStatusAndShow()
  if (result.nfcStatus !== 'enabled' || result.networkOK !== true) {
    await awaitDevicesOk()
  }

  // 2 read configuration
  const confFile = await getConfigurationAndSave()

  // 3 - affiche la liste des serveurs et le "boutan add place"
  showMainContent(confFile)
})

document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('.logs-icon').addEventListener('click', showLogs)
  // validation du pincode
  document.querySelector('#pin-code').addEventListener('keydown', managedPinCode)
})