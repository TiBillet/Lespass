/**
* total in unit cents
* @returns {Number} total articles
*/
function calculateTotal() {
	total = 0
	document.querySelectorAll('#addition-form input').forEach(input => {
		if (input.name.includes('repid-')) {
			const uuid = input.name.substring(6)
			const number = parseInt(input.value)
			const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
			const price = parseInt(article.dataset.price)
			total = total + (number * price)
		}
	})
	return total
}

/**
 * 
 * @param {*} param0 
 */
function additionInsertArticle({ detail }) {
	// console.log('-> additionInsertArticle, detail =', detail)

	const { uuid, price, quantity, name, currency } = detail
	// console.log('-> updateAddition, uuid =', uuid, '  --  price =', price, '  --  quantity =', quantity)
	// input in form
	const input = document.querySelector(`#addition-form [name="repid-${uuid}"]`)
	if (input === null) {
		// create input if not exist
		document.querySelector('#addition-form').insertAdjacentHTML('beforeend', `<input type="number" name="repid-${uuid}" value="1" />`)
		// create the addition list line - css are in components/addition.html
		const additionLine = `<div id="addition-line-${uuid}" data-quantity="${quantity}" data-price="${uuid}" class="addition-line-grid">
				<div class="addition-col-bt BF-col">
					<i class="fas fa-minus-square" onclick="additionRemoveArticle('${uuid}');" title="Enlever un article !"></i>
				</div>
				<div id="addition-quantity-${uuid}" class="addition-col-quantity BF-col">${quantity}</div>
				<div class="addition-col-name BF-col">${name}</div>
				<div class="addition-col-price BF-col">${price / 100}${currency}</div>
			`
		document.querySelector('#addition-list').insertAdjacentHTML('beforeend', additionLine)
	} else {
		// update input only
		input.value = Number(quantity)
		// addition line column quantity
		document.querySelector(`#addition-line-${uuid} .addition-col-quantity`).innerText = quantity
	}
	const totalAddition = calculateTotal()

	// dispatch event "additionTotalChange"
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionInsertArticle' },
		msg: 'additionTotalChange',
		data: { totalAddition }
	})
}

/**
* Remove an article in the addition 
* decrement the quantity of article in the addition list and input in #addition-form
* @param {String} uuid - uuid article
*/
function additionRemoveArticle(uuid) {
	const eleQuantity = document.querySelector(`#addition-quantity-${uuid}`)
	let quantity = Number(eleQuantity.innerText)
	quantity--
	// addition list
	eleQuantity.innerText = quantity
	// #addition-form
	document.querySelector(`#addition-form [name="repid-${uuid}"]`).value = Number(quantity)
	if (quantity === 0) {
		// addition list
		document.querySelector(`#addition-line-${uuid}`).remove()
		// #addition-form
		document.querySelector(`#addition-form [name="repid-${uuid}"]`).remove()
	}

	// dispatch event "articlesRemove"
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionRemoveArticle' },
		msg: 'additionRemoveArticle',
		data: { uuid, quantity }
	})

	const totalAddition = calculateTotal()

	// dispatch event "additionTotalChange"
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionInsertArticle' },
		msg: 'additionTotalChange',
		data: { totalAddition }
	})
}

function additionReset() {
	// clear inputs contain name='repid-xxxxxxx'
	const allInputs = document.querySelectorAll('#addition-form input')
	allInputs.forEach((input) => {
		if (input.getAttribute('name').includes('repid-')) {
			input.remove()
		}
	})

	// clear addition list lines
	document.querySelector('#addition-list').innerHTML = ''
	// inputs = ''
	document.querySelector('#addition-comportement').value = ''
	document.querySelector('#addition-total').value = '0'
	document.querySelector('#addition-moyen-paiement').value = ''
	document.querySelector('input[name="uuid_transaction"]').value = ''
	document.querySelector('#addition-given-sum').value = '0'

	const totalAddition = calculateTotal()

	// dispatch event "additionTotalChange"
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionInsertArticle' },
		msg: 'additionTotalChange',
		data: { totalAddition }
	})
}


document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#addition').addEventListener('additionInsertArticle', additionInsertArticle)
	document.querySelector('#addition').addEventListener('additionReset', additionReset)
})