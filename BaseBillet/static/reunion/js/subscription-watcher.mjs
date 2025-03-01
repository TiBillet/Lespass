/**
 * 
 * @param {HTMLDivElement} spinner 
 * @returns {Function}
 */
const showSpinner = spinner => () => {
    spinner.style.display = 'block'
}


export const init = () => {
    document.querySelectorAll('.js-membership-form-btn').forEach(btn => {
        btn.addEventListener('htmx:afterRequest', _ => {

            const form = document.getElementById('membership-form')
            const spinner = document.getElementById('tibillet-spinner')
        
            form.addEventListener('htmx:beforeRequest', showSpinner(spinner))
        })
    })
}
