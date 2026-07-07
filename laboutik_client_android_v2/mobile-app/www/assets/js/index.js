import { addAllMenuItems } from './modules/menuPlugins/addAllMenuPlugins.js'
import { getDevicesStatus, managedPinCode, readConfFile, setGeneralStatus, deleteServer, managedServerPinCode } from "./modules/utils.js"

// Ouvrir/fermer le menu burger / Toggle burger menu
function toggleClassMenuBurger(event) {
  // console.log('-> toggleClassMenuBurger')
  const menuContainer = document.querySelector('.menu-burger-container')
  menuContainer.classList.toggle('menu-burger-show')
}

function hideMenu(event) {
  const classEle = event.target.classList
  if (classEle.contains('menu-burger-container') || classEle.contains('menu-burger-item-touch')) {
    toggleClassMenuBurger()
  }
}

function hideContentInput() {
  document.querySelector('.content-input').style.display = 'none'
}

function hideConfirmDeleteServer() {
  document.querySelector('.confirm-container').style.display = 'none'
}

function showInputServeurPincode() {
  document.querySelector('.infos-server-pin-code').style.display = "none"
  document.querySelector('#update-server-pin-code').style.display = "flex"
}

document.addEventListener('DOMContentLoaded', () => {
  // add method on icon menu burger
  document.querySelector('.header-menu > svg').addEventListener('click', toggleClassMenuBurger)

  // hide menu burger
  document.querySelector('.menu-burger-container').addEventListener('click', hideMenu)

  // validation du pincode
  document.querySelector('#pin-code').addEventListener('keydown', managedPinCode)

  // gestion bouton return
  document.querySelector('.bt-input-return').addEventListener('click', hideContentInput)

  // hide window confirm delete server, bt cancel
  document.querySelector('.bt-delete-cancel').addEventListener('click', hideConfirmDeleteServer)

  // validate delete server
  document.querySelector('.bt-delete-validate').addEventListener('click', deleteServer)

  // affiche le input d'édition du serveur pin-code
  document.querySelector('#icon-update-server-pin-code').addEventListener('click', showInputServeurPincode)

  // permet l'édition du serveur pin-code
  document.querySelector('#update-server-pin-code').addEventListener('keydown', managedServerPinCode)
})

/**
 * wait cordova (devices activation)
 */
document.addEventListener('deviceready', async () => {
  // init menu plugins
  addAllMenuItems()

  window.state = {}
  const confFile = await readConfFile()
  // console.log('deviceready - confFile =', confFile);

  if (confFile === null) {
    setGeneralStatus('error')
    return
  }

  // étape 1/init - affectation des propriétées de state 
  for (const key in confFile) {
    state[key] = confFile[key]
  }
  state['step'] = 'init'

  // étape 2 - listen devices status 
  await getDevicesStatus()
})
