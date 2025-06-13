/**
 * Turns a price string into a int 100 times the value
 * to avoid float approximation issues
 * @param {string} price
 * @returns {integer}
 */
const parsePrice100 = price =>
    price
        .replace(' ', '')
        .split(',')
        .reduce((acc, x) => acc > 0 ? acc + Number(x) : Number(x) * 100, 0)

/**
 * 
 * @param {Array<{amount: HTMLInputElement, price: HTMLElement}>} orders 
 * @param {HTMLElement} totalAmount
 * @param {HTMLElement} totalPrice
 */
const updateTotal = (orders, totalAmount, totalPrice) => _ => {
    let ta = 0
    let tp = 0
    const openOrders = orders.filter(({ amount }) =>
        amount.closest('details').open
    )

    if (openOrders.some(({ price }) => Number(price === null )))
        totalPrice.closest('.js-total-has-price').classList.add('d-none')
    else
        totalPrice.closest('.js-total-has-price').classList.remove('d-none')

    openOrders
        .forEach(({ amount, price }) => {
            let a = Number(amount.value)
            let p = price ? parsePrice100(price.textContent) : 0

            ta += a
            tp += a * p
        })

    totalAmount.textContent = ta

    if (totalPrice)
        totalPrice.textContent = (tp / 100).toLocaleString('fr-FR')
}

const clearGroup = group => {
    group.querySelectorAll('.js-order-amount').forEach(amount => {
        amount.value = ''
    })
} 

export const init = () => {
    const totalAmount = document.querySelector('.js-total-amount')
    const totalPrice = document.querySelector('.js-total-price')
    const priceGroups = document.querySelectorAll('.js-price-group')
    const orders = [...document.querySelectorAll('.js-order')]
        .map(el => ({
            price: el.querySelector('.js-order-price'),
            amount: el.querySelector('.js-order-amount')
        }))
        .filter(({ amount }) => amount !== null )
    
    orders.forEach(({ amount }) => {
        amount.addEventListener('bs-counter:update', updateTotal(orders, totalAmount, totalPrice))
    })
    
    priceGroups.forEach(group => group.addEventListener('toggle', _ => {
        if (! group.open)
            clearGroup(group)
        
        updateTotal(orders, totalAmount, totalPrice)()
    }))

    updateTotal(orders, totalAmount, totalPrice)()
}
