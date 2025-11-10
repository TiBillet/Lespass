/**
 * update front, button article and addition list
 * @param {String} uuid - uuid article 
 * @param {Number} number - quantity article 
 */
function updateArticle(uuid, number) {
	// console.log('-> updateArticle, uuid =', uuid, '  --  number =', number)
	try {
		// article
		const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
		// maj number
		article.querySelector(`#article-quantity-number-${uuid}`).innerText = number
	} catch (error) {
		console.log('-> updateArticle,', error)
	}
}

/**
 * increment the quantity of the selected article
 * @param {String} uuid - uuid article 
 * @param {String} price - price article
 * @param {String} name - name article
 * @param {String} currency - currency article
 */
function addArticle(uuid, price, name, currency) {
	const eleQuantity = document.querySelector(`#article-quantity-number-${uuid}`)
	// get qunatity
	let quantity = Number(eleQuantity.innerText)
	quantity++
	// update qunatity
	eleQuantity.innerText = quantity

	// dispatch event
	sendEvent('articleIsIncremented', '#addition', { uuid, price, quantity, name, currency })
}

/**
 * decrement the quantity of article
 * @param {String} uuid - uuid article 
 */

function listenDecrementArticle(event) {
	const { uuid, quantity } = event.detail
	// console.log('-> decrementArticle, uuid =', uuid, '  --  quantity =', quantity)
	// article
	const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
	// update front
	updateArticle(uuid, quantity)
}

function resetArticles() {
	document.querySelectorAll('#products .article-container').forEach(article => {
		const uuid = article.dataset.uuid
		// number articles to 0
		document.querySelector(`#article-quantity-number-${uuid}`).innerText = 0
		// remove attribute
		article.removeAttribute('data-disable')
		// hide lock element
		article.querySelector('.article-lock-layer').style.display = "none"
	})
	// reset addition
	sendEvent('resetAddition', '#addition', {})
	// total to 0 of button valider 
	sendEvent('infoTotalAddition', 'body', { totalAddition: 0 })
}

/**
 * manages the selection of articles
 * @param {Object} event - to get article node 
 */
function manageKey(event) {
	const ele = event.target.parentNode
	if (ele.classList.contains('article-container') && ele.getAttribute('data-disable') === null) {
		const articleUuid = ele.dataset.uuid
		const articleGroup = ele.dataset.group
		const articlePrice = ele.dataset.price
		const articleName = ele.dataset.name
		const articleCurrency = ele.dataset.currency

		// manage article groups: display the "layer-lock"
		document.querySelectorAll('#products .article-container').forEach(item => {
			const itemGroup = item.dataset.group
			if (itemGroup !== articleGroup) {
				item.querySelector('.article-lock-layer').style.display = "block"
				item.setAttribute('data-disable', 'true')
			}
		})

		addArticle(articleUuid, articlePrice, articleName, articleCurrency)
	}
}

document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#products').addEventListener('click', manageKey)
	document.querySelector('#products').addEventListener('articleIsDecrement', listenDecrementArticle)
	document.querySelector('#products').addEventListener('resetArticles', resetArticles)
})
