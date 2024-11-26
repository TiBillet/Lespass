/** Search bar tag filtering based on query string */

const params = new URLSearchParams(window.location.search)
const tagTypes = ['type', 'genre', 'price-cap', 'location', 'audience', 'accessibility']
const target = document.querySelector('#filterTags')
const tags = tagTypes.reduce((acc, type) =>
    params.has(type) ? [...acc, ...params.get(type).split(',')] : acc,
    []
)

const renderTag = label =>
    `<button class="btn btn-info d-none d-md-block js-filter-tag" type="button" style="border-radius: 0;">
        ${label} <i class="bi bi-x"></i>
    </button>`

target.innerHTML = tags.map(renderTag).join('\n')

Array.from(target.querySelectorAll('.js-filter-tag')).forEach(child =>
    child.addEventListener('click', _ => child.remove())
)

//

if (tags.length === 0)
    target.querySelector('js-filter-indicator').classList.add('d-none')
