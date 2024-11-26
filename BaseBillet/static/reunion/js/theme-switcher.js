/** Theme switcher based on local store first, user preferences last */

const query = window.matchMedia('(prefers-color-scheme: dark)')
const target = document.querySelector('html')
const toggle = document.querySelector('#darkThemeCheck')

const refresh = ({ matches }) => {
    let theme = localStorage.getItem('theme') || (matches ? 'dark' : 'light')
    
    target.dataset.bsTheme = theme
    
    if (toggle) toggle.checked = theme === 'dark'
}

const update = ({ target: { checked }}) => {
    let theme = checked ? 'dark' : 'light'

    target.dataset.bsTheme = theme

    localStorage.setItem('theme', theme)
}

refresh(query)
query.addEventListener('change', refresh)
toggle.addEventListener('click', update)
