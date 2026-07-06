// logs
const iconSvg = `
<svg class="logs-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
 stroke-width="2">
  <rect x="6" y="4" width="12" height="16" />
  <line x1="8" y1="9" x2="16" y2="9" />
  <line x1="8" y1="13" x2="16" y2="13" />
  <line x1="8" y1="17" x2="13" y2="17" />
</svg>
`
let lang = navigator.language.toLowerCase()

// Add your label translation according to the browser language.
const translatedLabel = {
  fr: 'LOGS'
}
if(translatedLabel[lang] === undefined) {
  lang = 'fr'
}

function showLogs() {
  const logs = document.querySelector('.logs-content')
  logs.classList.toggle('showasblock')
  const showasblockExist = logs.classList.contains('showasblock')
  if (showasblockExist) {
    logs.style.display = 'block'
  } else {
    logs.style.display = 'none'
  }
}

export const menu = {
  func:showLogs, // fonction à lancer
  iconSvg, // icon svg
  label: translatedLabel[lang],
}
