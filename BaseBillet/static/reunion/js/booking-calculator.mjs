/**
 * Turns a price string into a int 100 times the value
 * to avoid float approximation issues
 * @param {string} price
 * @returns {integer}
 */
const parsePrice100 = price => {
    if (typeof price === 'string') {
        return price
            .replace(' ', '')
            .split(',')
            .reduce((acc, x) => acc > 0 ? acc + Number(x) : Number(x) * 100, 0)
    }
    return Number(price) * 100
}

/**
 * 
 * @param {Array<{amount: HTMLInputElement, price: HTMLElement, customPrice: HTMLInputElement}>} orders 
 * @param {HTMLElement} totalAmount
 * @param {HTMLElement} totalPrice
 */
const updateTotal = (orders, totalAmount, totalPrice) => _ => {
    let ta = 0
    let tp = 0

    orders
        .forEach(({ amount, price, customPrice }) => {
            let a = Number(amount.value)
            
            // Gestion de l'affichage du container de prix libre
            const customContainer = customPrice?.closest('.custom-amount-container')
            if (customContainer) {
                if (a > 0) {
                    customContainer.style.display = 'block'
                    customPrice.required = true
                } else {
                    customContainer.style.display = 'none'
                    customPrice.required = false
                    customPrice.value = ''
                }
            }

            let p = 0
            if (customPrice && a > 0) {
                p = parsePrice100(customPrice.value || 0)
            } else if (price) {
                p = parsePrice100(price.textContent)
            }

            ta += a
            tp += a * p
        })

    totalAmount.textContent = ta

    if (totalPrice)
        totalPrice.textContent = (tp / 100).toLocaleString('fr-FR')
}

export const init = () => {
    const totalAmount = document.querySelector('.js-total-amount')
    const totalPrice = document.querySelector('.js-total-price')
    const orders = [...document.querySelectorAll('.js-order')]
        .map(el => ({
            price: el.querySelector('.js-order-price'),
            amount: el.querySelector('.js-order-amount'),
            customPrice: el.querySelector('.js-order-custom-price')
        }))
        .filter(({ amount }) => amount !== null )
    
    orders.forEach(({ amount, customPrice }) => {
        const update = updateTotal(orders, totalAmount, totalPrice)
        amount.addEventListener('bs-counter:update', update)
        if (customPrice) {
            customPrice.addEventListener('input', update)
        }
    })

    updateTotal(orders, totalAmount, totalPrice)()
}
