const spinner = document.getElementById('tibillet-spinner')

/**
 * 
 * @param {HTMLDivElement} spinner 
 */
const showSpinner = () => {
    spinner.style.display = 'block'
}

/**
 * 
 * @param {HTMLDivElement} spinner 
 */
export const hideSpinner = () => {
    spinner.style.display = 'none'
}

export const init = form =>
    form.addEventListener('htmx:beforeRequest', showSpinner)
