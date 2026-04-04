/**
 * LONGPRESS.JS — Détection d'appui long réutilisable
 * / Reusable long press detection component
 *
 * LOCALISATION : laboutik/static/js/longpress.js
 *
 * Utilise l'API Pointer Events (fonctionne tactile ET souris).
 * Écoute sur un conteneur parent via event delegation.
 * Émet un CustomEvent("longpress") avec bubbles:true sur l'élément cible.
 *
 * USAGE :
 *   initLongPress({
 *     container: document.getElementById('products'),
 *     selector: '.article-container',
 *     delay: 600,
 *     moveThreshold: 10
 *   })
 *
 * COMMUNICATION :
 * Émet : CustomEvent("longpress") sur l'élément cible
 *   detail: { productUuid: string, element: HTMLElement }
 */

function initLongPress(options) {
    const container = options.container
    const selector = options.selector
    const delay = options.delay || 600
    const moveThreshold = options.moveThreshold || 10

    let timer = null
    let startX = 0
    let startY = 0
    let activeElement = null
    let longPressTriggered = false

    container.addEventListener('pointerdown', function(e) {
        const target = e.target.closest(selector)
        if (!target) return

        activeElement = target
        startX = e.clientX
        startY = e.clientY
        longPressTriggered = false

        activeElement.classList.add('pressing')

        timer = setTimeout(function() {
            activeElement.classList.remove('pressing')
            longPressTriggered = true

            activeElement.dispatchEvent(new CustomEvent('longpress', {
                bubbles: true,
                detail: {
                    productUuid: activeElement.dataset.uuid,
                    element: activeElement
                }
            }))

            activeElement = null
        }, delay)
    })

    container.addEventListener('pointermove', function(e) {
        if (!timer) return

        const dx = e.clientX - startX
        const dy = e.clientY - startY
        const distance = Math.sqrt(dx * dx + dy * dy)

        if (distance > moveThreshold) {
            clearTimeout(timer)
            timer = null
            if (activeElement) {
                activeElement.classList.remove('pressing')
                activeElement = null
            }
        }
    })

    container.addEventListener('pointerup', function() {
        if (timer) {
            clearTimeout(timer)
            timer = null
        }
        if (activeElement) {
            activeElement.classList.remove('pressing')
            activeElement = null
        }
    })

    container.addEventListener('pointercancel', function() {
        if (timer) {
            clearTimeout(timer)
            timer = null
        }
        if (activeElement) {
            activeElement.classList.remove('pressing')
            activeElement = null
        }
    })

    container.addEventListener('click', function(e) {
        if (longPressTriggered) {
            e.stopPropagation()
            e.preventDefault()
            longPressTriggered = false
        }
    }, true)
}
