/**
 * Application du thème à la page. Le thème en `localStorage` est priorisé si il
 * existe, sinon on force 'light'.
 * 
 * @param {HTMLElement} doc le document cible du thème
 * @param {HTMLInputElement} toggle la checkbox de thème
 * @param {HTMLElement} navToggle le bouton de la navbar
 */
const refresh = (doc, toggle, navToggle) => {
    const theme = localStorage.getItem('theme') || 'light'
    
    doc.dataset.bsTheme = theme
    
    if (toggle) toggle.checked = theme === 'dark'
}

/**
 * Mise à jour du choix de thème.
 * 
 * @param {HTMLElement} doc le document cible du thème
 * @param {string} theme le thème à appliquer
 * @param {HTMLInputElement} toggle la checkbox de thème
 * @param {HTMLElement} navToggle le bouton de la navbar
 */
const setTheme = (doc, theme, toggle, navToggle) => {
    doc.dataset.bsTheme = theme
    localStorage.setItem('theme', theme)
    if (toggle) toggle.checked = theme === 'dark'
}

/**
 * Initialisation du thème.
 */
export const init = () => {
    const doc = document.querySelector('html')

    const attachEvents = () => {
        const toggle = document.querySelector('#darkThemeCheck')
        const navToggle = document.querySelector('#themeToggle')

        // application initiale du thème
        refresh(doc, toggle, navToggle)

        // si bouton navbar on écoute le clic
        if (navToggle && !navToggle.dataset.themeBound) {
            navToggle.addEventListener('click', () => {
                const currentTheme = doc.dataset.bsTheme
                const newTheme = currentTheme === 'dark' ? 'light' : 'dark'
                setTheme(doc, newTheme, toggle, navToggle)
            })
            navToggle.dataset.themeBound = 'true'
        }

        // si page des préférences on écoute la checkbox
        if (toggle && !toggle.dataset.themeBound) {
            toggle.addEventListener('change', (e) => {
                const newTheme = e.target.checked ? 'dark' : 'light'
                setTheme(doc, newTheme, toggle, navToggle)
            })
            toggle.dataset.themeBound = 'true'
        }
    }

    attachEvents()

    // Ré-attacher les événements après chaque swap HTMX
    document.body.addEventListener('htmx:afterSwap', () => {
        attachEvents()
    })
}
