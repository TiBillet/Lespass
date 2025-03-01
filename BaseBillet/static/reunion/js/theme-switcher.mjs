/**
 * Application du thème à la page. Le thème en `localStorage` est priorisé si il
 * existe, sinon on se base sur le navigateur.
 * Si on est sur la page des préférences, on applique aussi le choix de thème à
 * la checkbox.
 * 
 * @param {HTMLElement} doc le document cible du thème
 * @param {HTMLInputElement} toggle la checkbox de thème
 * @return {Function({matches: boolean})}
 *   callback qui prend les préférences navigateur en entrée, prévu pour une
 *   application partielle de la fonction à un event listener
 */
const refresh = (doc, toggle) => ({ matches }) => {
    const theme = localStorage.getItem('theme') || (matches ? 'dark' : 'light')
    
    doc.dataset.bsTheme = theme
    
    if (toggle) toggle.checked = theme === 'dark'
}

/**
 * Mise à jour du choix de thème en fonction de l'état de la checkbox.
 * Si `checked` alors thème sombre, sinon thème clair.
 * 
 * @param {HTMLElement} doc le document cible du thème
 * @returns  {Function({target: HTMLInputElement})}
 *   callback qui prend l'évènement de clic sur la checkbox en entrée, prévu
 *   pour une application partielle de la fonction à un event listener
 */
const update = doc => ({ target: { checked }}) => {
    const theme = checked ? 'dark' : 'light'

    doc.dataset.bsTheme = theme

    localStorage.setItem('theme', theme)
}

/**
 * Initialisation du thème.
 */
export const init = () => {
    const doc = document.querySelector('html')
    const toggle = document.querySelector('#darkThemeCheck')
    const query = window.matchMedia('(prefers-color-scheme: dark)')

    // application initiale du thème
    refresh(doc, toggle)(query)

    // on écoute les changements de préférence navigateur 
    query.addEventListener('change', refresh(doc, toggle))

    // si page des préférences on écoute la checkbox
    if (toggle) toggle.addEventListener('click', update(doc))
}
