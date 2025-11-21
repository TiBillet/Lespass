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

	// demande au composant addition de modifier la valeur de l'input moyen de paiement
	sendEvent('manageAdditionFormHtmx', '#addition-form', { updateType: 'input', selector: '#addition-moyen-paiement', value: method })

	// demande au composant addition de modifier la valeur de l'input uuid transaction
	if (uuidTransaction !== '') {
		sendEvent('manageAdditionFormHtmx', '#addition-form', { updateType: 'input', selector: 'input[name="uuid_transaction"]', value: uuidTransaction })
	}

	// demande au composant addition de modifier la valeur de l'input given-sum (somme donnée)
	const givenSumElement = document.querySelector('#given-sum')
	if (method === 'espece' && givenSumElement !== null) {
		// somme donnée en centimes
		const givenSum = Number(givenSumElement.value) * 100
		// demande au composant addition de modifier la valeur de l'input givenSum
		sendEvent('manageAdditionFormHtmx', '#addition-form', { updateType: 'input', selector: '#addition-given-sum', value: givenSum })
	}

	// demande au composant addition de modifier la valeur du hx-post (changer l'url du POST)
	sendEvent('manageAdditionFormHtmx', '#addition-form', { updateType: 'url', selector: '#addition-form', value: 'hx_payment' })
	// demande au composant addition de modifier la valeur de hx-trigger
	sendEvent('manageAdditionFormHtmx', '#addition-form', { updateType: 'trigger', value: 'validerPaiement' })

	hideAndEmptyElement('#confirm')
	hideAndEmptyElement('#messages')

	// submit le formulaire
	sendEvent('manageAdditionFormHtmx', '#addition-form', { updateType: 'submit', value: 'validerPaiement' })

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

// aiguillage d'eventsOrganizer :
// - Est un objet contenant l'aiguillage de chaque évènement reçu
// - un évènement reçu dispatch d'autres évèvement - exemple: { name: 'additionInsertArticle', selector: '#addition' }
// - exemple: je reçois le message 'addArticle' alors j'envoie le message "additionInsertArticle"
const switches = {
	articlesAdd: [{ name: 'additionInsertArticle', selector: '#addition' }],
	additionTotalChange: [{ name: 'updateBtValider', selector: '#bt-valider' }],
	additionRemoveArticle: [{ name: 'articlesRemove', selector: '#products' }],
	resetArticles: [{ name: 'additionReset', selector: '#addition' }, { name: 'articlesReset', selector: '#products' }],
	articlesDisplayCategory: [{ name: 'articlesDisplayCategory', selector: '#products' }],
}

function eventsOrganizer(event) {
	try {
		const data = event.detail.data
		const src = event.detail.src
		const msg = event.detail.msg
		console.log(`--- eventsOrganizer - ${src.file}/${src.method} ---`)
		console.log('- msg =', msg)
		console.log('- data =', data)
		console.log('--------------------------------------------------------------------')
		console.log('   ')

		// récupère les "routes" d'un évènement
		const eventSwitch = switches[msg]

		// envoi les évènements
		for (let i = 0; i < eventSwitch.length; i++) {
			const eventData = eventSwitch[i];
			sendEvent(eventData.name, eventData.selector, data)
		}
	} catch (error) {

	}
}

document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#event-organizer').addEventListener('organizerMsg', eventsOrganizer)
})