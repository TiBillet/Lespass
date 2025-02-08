const refresh = (doc, toggle) => ({ matches }) => {
    let theme = localStorage.getItem('theme') || (matches ? 'dark' : 'light')
    
    doc.dataset.bsTheme = theme
    
    if (toggle) toggle.checked = theme === 'dark'
}

const update = doc => ({ target: { checked }}) => {
    let theme = checked ? 'dark' : 'light'

    doc.dataset.bsTheme = theme

    localStorage.setItem('theme', theme)
}

const init = () => {
    const doc = document.querySelector('html')
    const toggle = document.querySelector('#darkThemeCheck')
    const query = window.matchMedia('(prefers-color-scheme: dark)')

    refresh(doc, toggle)(query)

    query.addEventListener('change', refresh(doc, toggle))

    if (toggle) toggle.addEventListener('click', update(doc))
}

window.addEventListener('DOMContentLoaded', init)
