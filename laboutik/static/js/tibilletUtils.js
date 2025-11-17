let currentConfiguration = null
const logTypes = ['DANGER', 'WARNING', 'INFO']

function tibilletConvDjangoToJs(value) {
	const convList = {
		'True': true,
		'False': false,
		'None': null
	}
	let retour
	if (convList[value]) {
		return convList[value]
	} else {
		console.log(`tibilletConvDjandoToJs.js, variable "${value}" inconnue dans la list "convlist".`);
	}
}


function log({ tag, msg }) {
	const arg0 = arguments[0]
	const arg1 = arguments[1]
	const typeArgument0 = typeof (arg0)
	const typeArgument1 = typeof (arg1)
	// tag + msg
	if (typeArgument0 === 'object' && logTypes.includes(tag)) {
		console.log(msg)
	} else {
		let formatMsg = ''
		// string
		if (typeArgument0 === 'string') {
			formatMsg += arg0
		}
		// string + object
		if (typeArgument1 === 'object') {
			formatMsg += JSON.stringify(arg1)
		}
		// string + string
		if (typeArgument1 === 'string') {
			formatMsg += ' ' + arg1
		}
		console.log(formatMsg)
	}
}


function bigToFloat(value) {
	try {
		return parseFloat(new Big(value).valueOf())
	} catch (error) {
		console.log('-> bigToFloat, ', error)
	}
}
/**
 * Send custum ecent
 * @param {string} name event name 
 * @param {string} selector css selector
 * @param {object} data 
 */
function sendEvent(name, selector, data) {
	data = data === undefined ? {} : data
	// console.log(`-> sendEvent "${name}"  --   selector = ${selector}  -- data = ${JSON.stringify(data, null, 2)}`)
	try {
		const event = new CustomEvent(name, { detail: data })
		document.querySelector(selector).dispatchEvent(event)
	} catch (error) {
		console.log('sendEvent,', error);
	}
}

function hideAndEmptyElement(selector) {
	const element = document.querySelector(selector)
	// cache
	element.classList.add('hide')
	// vide
	element.innerHTML = ''
}

// update form
function setAndSubmitForm(method, uuidTransaction) {
	console.log('-> setAndSubmitForm, method =', method, '  --  uuidTransaction =', uuidTransaction);
	// modifie la valeur de l'input moyen de paiement
	document.querySelector('#addition-moyen-paiement').value = method

	// modifie la valeur de l'input uuid transaction
	if (uuidTransaction !== '') {
		// test input uuid transaction exist
		const inputExist = document.querySelector('input[name="uuid_transaction"]')
		if (inputExist === null) {
			// premier insertion dans le dom
			document.querySelector('#addition-form').insertAdjacentHTML('afterend', `<input type="text" class="addition-include-data" name="uuid_transaction" value="${uuidTransaction}" />`)
		} else {
			// maj value uniquement
			inputExist.value = uuidTransaction
		}
	}

	// Insert l'input given-sum (somme donnée) ou modifie sa valeur. 
	const givenSumElement = document.querySelector('#given-sum')
	if (method === 'espece' && givenSumElement !== null) {
		const givenSum = givenSumElement.value
		// test input exist
		const inputExist = document.querySelector('#addition-given-sum')
		if (inputExist === null) {
			// premier insertion dans le dom
			document.querySelector('#addition-form').insertAdjacentHTML('afterend', `<input type="number" class="addition-include-data" id="addition-given-sum" name="given_sum" value="${givenSum}" />`)
		} else {
			// maj value uniquement
			inputExist.value = givenSum
		}
	}

	const form = document.querySelector('#addition-form')
	// changer l'url du POST
	form.setAttribute('hx-post', 'hx_payment')
	// update event to submit
	form.setAttribute('hx-trigger', 'validerPaiement')
	// prend en compte les changement sur le formulaire
	htmx.process(form)

	hideAndEmptyElement('#confirm')
	hideAndEmptyElement('#messages')

	// submit le formulaire
	sendEvent('validerPaiement', '#addition-form')
}
