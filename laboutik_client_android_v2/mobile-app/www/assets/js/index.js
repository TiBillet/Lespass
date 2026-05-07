import { addAllMenuItems } from './modules/menuPlugins/addAllMenuPlugins.js'
import { readConfFile, initListenDevicesStatus, setGeneralStatus, managedPinCode } from "./modules/utils.js"

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

/**
 * wait cordova (devices activation)
 */
document.addEventListener('deviceready', async () => {
  // init menu plugins
  addAllMenuItems()

  window.state = {}
  const confFile = await readConfFile()
  if (confFile === null) {
    setGeneralStatus('error')
    return
  }

  // étape 1/init - affectation des propriétées de state 
  for (const key in confFile) {
    state[key] = confFile[key]
  }
  state['step'] = 'init'

  // listen devices status
  initListenDevicesStatus()
})


document.addEventListener('DOMContentLoaded', () => {
// add method on icon menu burger
  document.querySelector('.header-menu > svg').addEventListener('click', toggleClassMenuBurger)

  // hide menu burger
  document.querySelector('.menu-burger-container').addEventListener('click', hideMenu)

  // validation du pincode
  document.querySelector('#pin-code').addEventListener('keydown', managedPinCode)
})
