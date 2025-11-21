/**
 * increment the quantity of the selected article
 * @param {String} uuid - uuid article 
 * @param {String} price - price article
 * @param {String} name - name article
 * @param {String} currency - currency article
 */
function addArticle(uuid, price, name, currency) {
	try {
		const eleQuantity = document.querySelector(`#article-quantity-number-${uuid}`)
		// get qunatity
		let quantity = Number(eleQuantity.innerText)
		quantity++
		// update qunatity
		eleQuantity.innerText = quantity

		// dispatch event "articlesAdd"
		sendEvent('organizerMsg', '#event-organizer', {
			src: { file: 'articles.js', method: 'addArticle' },
			msg: 'articlesAdd',
			data: { uuid, price, quantity, name, currency }
		})
	} catch (error) {
		console.log('-> article.js - addArticle,', error)
	}
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

/**
 * update front, button article
 * @param {Object} event - { uuid, quantity }
 */
function articlesRemove(event) {
	const { uuid, quantity } = event.detail
	// console.log('-> updateArticle, uuid =', uuid, '  --  number =', number)
	try {
		// article
		const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
		// maj number
		article.querySelector(`#article-quantity-number-${uuid}`).innerText = quantity
	} catch (error) {
		console.log('-> article.js - articlesRemove,', error)
	}
}

function articlesReset() {
	try {
		document.querySelectorAll('#products .article-container').forEach(article => {
			const uuid = article.dataset.uuid
			// number articles to 0
			document.querySelector(`#article-quantity-number-${uuid}`).innerText = 0
			// remove attribute
			article.removeAttribute('data-disable')
			// hide lock element
			article.querySelector('.article-lock-layer').style.display = "none"
		})

	} catch (error) {
		console.log('-> article.js - articlesReset,', error)
	}
}

function articlesDisplayCategory(event) {
	const category = event.detail.category
	try {
		console.log('-> articlesDisplayCategory, category =', category)
		if (category === 'cat-all') {

		} else {
			
		}
	} catch (error) {
		console.log('-> article.js - articlesDisplayCategory,', error)
	}
}

document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#products').addEventListener('click', manageKey)
	document.querySelector('#products').addEventListener('articlesRemove', articlesRemove)
	document.querySelector('#products').addEventListener('articlesReset', articlesReset)
	document.querySelector('#products').addEventListener('articlesDisplayCategory', articlesDisplayCategory)
})