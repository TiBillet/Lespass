const listMenuToAdd = ['logs']
export function addAllMenuItems() {
  // console.log('-> addAllMenuItems')
  listMenuToAdd.forEach(async (plug) => {
    // plugin import
    const { menu } = await import("./" + plug + "/index.js")
    let activateMenu = true
    const uuid = crypto.randomUUID()

    // ajoute l'item menu si les conditions sont à "true"
    if (menu.conditions !== undefined) {
      // lance la liste de conditions
      for (let i = 0; i < menu.conditions.length; i++) {
        const condition = menu.conditions[i]
        try {
          activateMenu = await window[condition]()
        } catch (error) {
          console.log(`addAllMenuPlugin.js, la fonction condition = "${condition}" n'existe pas !`)
        }
      }
    }

    if (activateMenu === true) {
      let addClass = ''
      if (menu.testClass !== undefined) {
        addClass = ' ' + menu.testClass
      }
      let visual = ''
      if (menu.iconSvg) {
        visual = menu.iconSvg
      }

      // menu item
      const menuAddHtmlFragment = `<div class="menu-burger-item">
        ${visual}
        <div class="menu-burger-item-label">${menu.label}</div>
        <div id="menu-item-${uuid}" data-testid="laboutik-menu-logs" class="menu-burger-item-touch"></div>
      </div>`

      // add menu item in dom
      document.querySelector('.menu-burger-content').insertAdjacentHTML('beforeend', menuAddHtmlFragment)
      document.querySelector('#menu-item-' + uuid).addEventListener('click', menu.func)
    }
  })
}