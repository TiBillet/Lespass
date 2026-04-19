/**
 * Affiche/cache le spinner de chargement (#tibillet-spinner)
 * Utilise la classe .active (coherent avec loading-states HTMX)
 * / Shows/hides the loading spinner using .active class
 *
 * LOCALISATION : reunion/js/form-spinner.mjs
 */
const spinner = document.getElementById('tibillet-spinner')

const showSpinner = () => {
    if (spinner) {
        spinner.classList.add('active')
    }
}

export const hideSpinner = () => {
    if (spinner) {
        spinner.classList.remove('active')
    }
}

/**
 * Initialise le spinner sur un formulaire HTMX
 * / Initializes spinner on an HTMX form
 *
 * Actions :
 * - Affiche le spinner au debut de la requete (htmx:beforeRequest)
 * - Cache le spinner a la fin de la requete (htmx:afterRequest), succes ou erreur
 *
 * @param {HTMLElement} form - Le formulaire HTMX a surveiller
 */
export const init = form => {
    if (!form) return

    form.addEventListener('htmx:beforeRequest', showSpinner)
    form.addEventListener('htmx:afterRequest', hideSpinner)
}
