// paramètres

let lang = navigator.language.toLowerCase()

// Add your label translation according to the browser language.
const translation = {
  fr: {
    menuTitle: 'PARAMETRES',
    srvPinCode: 'Serveur pin code'
  }
}

if(translation[lang] === undefined) {
  lang = 'fr'
}

const iconSvg = `
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/>
  <path d="M12 2v2"/>
  <path d="M12 20v2"/>
  <path d="M4.93 4.93l1.41 1.41"/>
  <path d="M17.66 17.66l1.41 1.41"/>
  <path d="M2 12h2"/>
  <path d="M20 12h2"/>
  <path d="M4.93 19.07l1.41-1.41"/>
  <path d="M17.66 6.34l1.41-1.41"/>
  <circle cx="12" cy="12" r="8"/>
</svg>
`

function renderPlugin() {
  return  `
    <div class="params-container">
      <div>${translation[lang].menuTitle}</div>
      <div class="input-group-row">
        <div class="params-label">${translation[lang].srvPinCode}</div>
        <input id="manage-server-pin-code" class="params-input" type="text" id="update-server-pin-code" value="${state.server_pin_code}"/>
      </div>
    </div>
    <style>
    .params-container {
  width: 100%;
  height: 100%;
}

    .params-label {
  width: 30%;
}

.params-input {
  width: 60%;
}

.params-bt {
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  border-radius: 6px;
  cursor: pointer;
  user-select: none;
  padding: 0 6px;
}

.params-bt-valid {
  margin-left: 8px;
  color: var(--blanc01);
  background-color: var(--vert03);
}
    </style>
  `
}

function managedServerPinCode(event) {
  console.log('-> managedServerPinCode');
   if (event.key === 'Enter') {
    const url = event.target.value
    const urlRegex = /^https?:\/\/(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+(?:\/[^\s]*)?$/

    console.log('enter - url =', url);
   }
}

function showParams() {
  const content = document.querySelector('.divers-content')
  content.innerHTML = renderPlugin()
  content.style.display = 'block'
  document.querySelector('#manage-server-pin-code').addEventListener('keydown', managedServerPinCode)
}

export const menu = {
  func:showParams, // fonction à lancer
  iconSvg, // icon svg
  label: translation[lang].menuTitle,
}
