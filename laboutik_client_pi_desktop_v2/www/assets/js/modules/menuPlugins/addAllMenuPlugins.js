// liste de dossiers à prendre en compte
const listMenuToAdd = []

// pas de plugins pas de munu burger 
if (listMenuToAdd.length === 0){
  document.querySelector('.header-menu').style.display = "none"
}

function uuidv4() {
    // Tableau de 16 octets aléatoires
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);

    // Version 4
    bytes[6] = (bytes[6] & 0x0f) | 0x40;

    // Variant RFC 4122
    bytes[8] = (bytes[8] & 0x3f) | 0x80;

    // Conversion en hexadécimal
    const hex = Array.from(bytes, b =>
        b.toString(16).padStart(2, "0")
    );

    // Construction de l'UUID
    return (
        hex.slice(0, 4).join("") + "-" +
        hex.slice(4, 6).join("") + "-" +
        hex.slice(6, 8).join("") + "-" +
        hex.slice(8, 10).join("") + "-" +
        hex.slice(10, 16).join("")
    );
}

export function addAllMenuItems() {
  // console.log('-> addAllMenuItems')
  listMenuToAdd.forEach(async (plug) => {
    // plugin import
    const { menu } = await import("./" + plug + "/index.js")
    let activateMenu = true
    const uuid = uuidv4()

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