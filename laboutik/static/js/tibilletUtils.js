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

// demande de mise à jour du moyen de paiement dans le formulaire de l'addition
function askAdditionManageForm(actionType, selector, value) {
	// dispatch event "askAdditionManageForm"
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'hx_display_type_payement.html', method: 'additionUpdateForm' },
		msg: 'additionManageForm',
		data: { actionType, selector, value }
	})
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
	additionDisplayPaymentTypes: [{ name: 'additionDisplayPaymentTypes', selector: '#addition' }],
	additionManageForm: [{ name: 'additionManageForm', selector: '#addition' }],
	primaryCardManageForm: [{ name: 'primaryCardManageForm', selector: '#form-nfc' }],
  checkCardManageForm: [{ name: 'checkCardManageForm', selector: '#form-check-nfc' }]
}

function eventsOrganizer(event) {
	try {
		const data = event.detail.data
		const src = event.detail.src
		const msg = event.detail.msg
		// console.log(`--- eventsOrganizer - ${src.file}/${src.method} ---`)
		// console.log('- msg =', msg)
		// console.log('- data =', data)
		// console.log('--------------------------------------------------------------------')
		// console.log('   ')

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