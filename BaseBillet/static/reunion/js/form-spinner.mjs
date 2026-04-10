/**
 * Affiche/cache le spinner de chargement (#tibillet-spinner)
 * Utilise la classe .active (coherent avec loading-states HTMX)
 * / Shows/hides the loading spinner using .active class
 *
 * LOCALISATION : reunion/js/form-spinner.mjs
 */
const spinner = document.getElementById('tibillet-spinner')

const showSpinner = () => {
    spinner.classList.add('active')
}

export const hideSpinner = () => {
    spinner.classList.remove('active')
}

export const init = form =>
    form.addEventListener('htmx:beforeRequest', showSpinner)
