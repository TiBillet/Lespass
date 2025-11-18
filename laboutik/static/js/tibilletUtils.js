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
	// console.log(`-> sendEvent "${name}" on "${selector}"`)
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
	uuidTransaction = uuidTransaction === 'None' ? '' : uuidTransaction
	console.log('-> setAndSubmitForm, method =', method, '  --  uuidTransaction =', uuidTransaction);

	// modifie la valeur de l'input moyen de paiement
	document.querySelector('#addition-moyen-paiement').value = method

	// modifie la valeur de l'input uuid transaction
	if (uuidTransaction !== '') {
		document.querySelector('input[name="uuid_transaction"]').value = uuidTransaction
	}

	// Insert l'input given-sum (somme donnée) ou modifie sa valeur. 
	const givenSumElement = document.querySelector('#given-sum')
	if (method === 'espece' && givenSumElement !== null) {
		const givenSum = givenSumElement.value
		document.querySelector('#addition-given-sum').value = givenSum
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

window.manageFormHtmx = function (event) {
	const action = event.detail
	// console.log('-> updateFormHtmx, action =', action)
	const form = document.querySelector(action.form)

	if (action.updateType === 'url') {
		form.setAttribute('hx-post', action.value)
		// ask htmx to process new changes
		htmx.process(form)
	}

	if (action.updateType === 'trigger') {
		form.setAttribute('hx-trigger', action.value)
		// ask htmx to process new changes
		htmx.process(form)
	}

	if (action.updateType === 'input') {
		document.querySelector(action.selector).value = action.value
		// ask htmx to process new changes
		htmx.process(form)
	}

	if (action.updateType === 'submit') {
		sendEvent(action.value, action.form, {})
	}
}
