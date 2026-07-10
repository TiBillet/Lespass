/**
 * TIBILLET UTILS - SYSTÈME D'ÉVÉNEMENTS CENTRAL (EVENT BUS)
 * / Central Event System for LaBoutik
 * 
 * LOCALISATION : laboutik/static/js/tibilletUtils.js
 * 
 * Ce fichier implémente un "Event Bus" qui permet aux composants de communiquer
 * sans se connaître directement via un système d'événements personnalisés.
 * 
 * ARCHITECTURE :
 * - sendEvent() : Émet un événement sur un élément DOM
 * - switches : Table de routage des événements
 * - eventsOrganizer() : Récepteur central qui route les événements
 * 
 * FLUX D'UN ÉVÉNEMENT :
 * 1. Composant émet : sendEvent('organizerMsg', '#event-organizer', { msg: 'articlesAdd', data })
 * 2. eventsOrganizer() reçoit et consulte switches[msg]
 * 3. switches['articlesAdd'] = [{ name: 'additionInsertArticle', selector: '#addition' }]
 * 4. sendEvent() déclenche l'événement sur l'élément cible
 * 5. Le handler dans l'autre fichier est exécuté
 */

let currentConfiguration = null
const logTypes = ['DANGER', 'WARNING', 'INFO']

/**
 * Is cordova application ?
 * @public
 * @returns {boolean}
 */
function isCordovaApp() {
	try {
		if (window.cordova) {
			return true
		}
	} catch (error) {
		return false
	}
}

/**
 * Echappe les caractères spéciaux HTML pour éviter les injections XSS.
 * Utilisé pour tout texte dynamique injecté via innerHTML ou insertAdjacentHTML
 * (noms de produits, noms de tarifs, symboles monétaires).
 * / Escapes HTML special characters to prevent XSS injection.
 *
 * LOCALISATION : laboutik/static/js/tibilletUtils.js
 *
 * Défini ici (chargé dans le <head>) pour être disponible dans tous les scripts :
 * tarif.js, addition.js, nfc.js, articles.js.
 *
 * @param {String} texte - Texte brut à échapper
 * @returns {String} Texte avec caractères HTML échappés
 */
function escapeHtml(texte) {
	return String(texte)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;')
}

/**
 * Convertit les valeurs Django ('True', 'False', 'None') en valeurs JS
 * / Converts Django values to JS values
 */
function tibilletConvDjangoToJs(value) {
	const convList = {
		'True': true,
		'False': false,
		'None': null
	}
	if (convList[value]) {
		return convList[value]
	} else {
		console.log(`Variable "${value}" inconnue dans la liste.`);
		// TODO : Cette fonction ne retourne rien explicitement si la valeur n'est pas dans convList.
		// Ne devrait-elle pas retourner 'value' tel quel ou throw une erreur ?
		// Actuellement elle retourne 'undefined' ce qui peut causer des bugs silencieux.
	}
}

/**
 * Fonction de logging utilitaire
 * / Utility logging function
 */
function log({ tag, msg }) {
	const arg0 = arguments[0]
	const arg1 = arguments[1]
	const typeArgument0 = typeof (arg0)
	const typeArgument1 = typeof (arg1)
	if (typeArgument0 === 'object' && logTypes.includes(tag)) {
		console.log(msg)
	} else {
		let formatMsg = ''
		if (typeArgument0 === 'string') formatMsg += arg0
		if (typeArgument1 === 'object') formatMsg += JSON.stringify(arg1)
		if (typeArgument1 === 'string') formatMsg += ' ' + arg1
		console.log(formatMsg)
	}
}

/**
 * Convertit une valeur Big en nombre flottant
 * / Converts Big value to float
 */
function bigToFloat(value) {
	try {
		return parseFloat(new Big(value).valueOf())
	} catch (error) {
		console.log('-> bigToFloat, ', error)
	}
}

/**
 * Émet un événement personnalisé sur un élément du DOM
 * / Dispatches a custom event on a DOM element
 * 
 * C'est la fonction fondamentale du système d'événements.
 * Elle crée un CustomEvent et le déclenche sur l'élément ciblé.
 * 
 * Exemple d'utilisation dans articles.js :
 * sendEvent('organizerMsg', '#event-organizer', {
 *     src: { file: 'articles.js', method: 'addArticle' },
 *     msg: 'articlesAdd',
 *     data: { uuid, price, quantity, name, currency }
 * })
 * 
 * @param {string} name - Nom de l'événement
 * @param {string} selector - Sélecteur CSS de l'élément cible
 * @param {object} data - Données à passer (disponibles dans event.detail)
 */
function sendEvent(name, selector, data) {
	// console.log('-> sendEvent - selector =', selector, '  --  data =', data);
	data = data === undefined ? {} : data
	try {
		const event = new CustomEvent(name, { detail: data })
		document.querySelector(selector).dispatchEvent(event)
	} catch (error) {
		console.log('sendEvent,', error);
	}
}

/**
 * Cache et vide un élément du DOM
 * / Hides and empties a DOM element
 */
function hideAndEmptyElement(selector) {
	const element = document.querySelector(selector)
	element.classList.add('hide')
	element.innerHTML = ''
}

/**
 * Change bill url to laboutik/paiement/moyens_paiement
 * for init POST url from form wiht id="addition-form".
 */
function initUrlAddition() {
	sendEventOrganizer({
		src: { file: 'hx_messages.html', method: 'changeUrlAddition' },
		msg: 'additionManageForm',
		data: { actionType: 'postUrl', selector: null, value: '/laboutik/paiement/moyens_paiement/' }
	})
}


/**
 * Envoyer des datas à un élément html par 'event'
 * @param {object} data  - Données(disponibles dans event.detail) à passer au routeur d 'évènements
 */
function sendEventOrganizer(data) {
	// console.log('-> sendEvent - selector =', selector, '  --  data =', data);
	data = data === undefined ? {} : data
	try {
		const event = new CustomEvent('organizerMsg', { detail: data })
		document.querySelector('#event-organizer').dispatchEvent(event)
	} catch (error) {
		console.log('sendEventOrganizer,', error);
	}
}


/**
 * Demande la mise à jour d'un champ du formulaire d'addition
 * / Requests update to addition form field
 * 
 * Appelée depuis les partials HTMX (ex: hx_display_type_payment.html)
 * pour modifier dynamiquement les inputs cachés du formulaire de paiement.
 * 
 * Exemple : onclick="askAdditionManageForm('updateInput', '#addition-moyen-paiement', 'espece')"
 * 
 * @param {string} actionType - Type d'action ('updateInput', 'postUrl', 'submit')
 * @param {string} selector - Sélecteur du champ à modifier
 * @param {*} value - Valeur à assigner
 */
function askAdditionManageForm(actionType, selector, value) {
	sendEventOrganizer({
		src: { file: 'tibiletUtils.js', method: 'askAdditionManageForm' },
		msg: 'additionManageForm',
		data: { actionType, selector, value }
	})
}

/**
 * TABLE DE ROUTAGE DES ÉVÉNEMENTS
 * / Event routing table
 * 
 * Définit pour chaque message entrant vers quel événement et quel sélecteur l'envoyer.
 * Structure : { 'messageEntrant': [{ name: 'eventAEmettre', selector: '#cible' }] }
 * 
 * ROUTES DÉFINIES :
 * - articlesAdd → additionInsertArticle sur #addition (ajoute au panier)
 * - additionTotalChange → updateSumOfValidateButton sur #bt-valider (maj total)
 * - additionRemoveArticle → articlesRemove sur #products (maj quantité tuile)
 * - resetArticles → additionReset sur #addition + articlesReset sur #products (reset complet)
 * - additionDisplayPaymentTypes → additionDisplayPaymentTypes sur #addition (affiche paiements)
 * - additionManageForm → additionManageForm sur #addition (modifie formulaire)
 */
const switches = {
	articlesAdd: [{ name: 'additionInsertArticle', selector: '#addition' }],
	additionTotalChange: [{ name: 'updateSumOfValidateButton', selector: '#bt-valider' }],
	additionRemoveArticle: [{ name: 'articlesRemove', selector: '#products' }],
	resetArticles: [{ name: 'additionReset', selector: '#addition' }, { name: 'articlesReset', selector: '#products' }],
	articlesDisplayCategory: [{ name: 'articlesDisplayCategory', selector: '#products' }],
	footerAskAdditionDisplayPaymentTypes: [{ name: 'additionDisplayPaymentTypes', selector: '#addition' }],
	additionManageForm: [{ name: 'additionManageForm', selector: '#addition' }],
	nfcAskManageForm: [{ auto: true }],
	tarifSelection: [{ name: 'tarifSelection', selector: '#products' }],

	nfcSendEmptyCardManageForm: [{ name: 'emptyCardManageForm', selector: '#vider-carte-form' }],
	nfcRechargeClientForm: [{ name: 'rechargeClientForm', selector: '#recharge-client-form' }]
}

/**
 * ROUTEUE D'ÉVÉNEMENTS - RÉCEPTEUR CENTRAL
 * / Central event receiver and router
 * 
 * Reçoit tous les événements 'organizerMsg' sur #event-organizer et les route
 * selon la table switches. C'est le cœur du système d'événements.
 * 
 * Exemple de flux complet :
 * 1. articles.js:addArticle() envoie { msg: 'articlesAdd', data: { uuid, price... } }
 * 2. CETTE FONCTION reçoit l'événement et lit event.detail.msg = 'articlesAdd'
 * 3. Consulte switches['articlesAdd'] = [{ name: 'additionInsertArticle', selector: '#addition' }]
 * 4. Appelle sendEvent('additionInsertArticle', '#addition', data)
 * 5. addition.js:additionInsertArticle() est exécuté
 * 
 * @param {Event} event - Événement 'organizerMsg' avec event.detail contenant src, msg, data
 */
function eventsOrganizer(event) {
	try {
		const data = event.detail.data
		const src = event.detail.src
		const msg = event.detail.msg

		// console.log('--- eventsOrganizer ----------------------------');
		// console.log('-> eventsOrganizer - msg =', msg);
		// console.log('-> eventsOrganizer - src =', src);

		// keys of switches in array
		const keys = Object.keys(switches)
		if (!keys.includes(msg)) {
			throw new Error(`eventsOrganizer - message "${msg}" unknown !`);
		}

		// Récupère les routes depuis la table switches
		const eventSwitch = switches[msg]

		// Envoie l'événement vers chaque destination
		for (let i = 0; i < eventSwitch.length; i++) {
			const eventData = eventSwitch[i];
			if (eventData?.auto) {
				sendEvent(data.formSelector, data.formSelector, data)
			} else {
				sendEvent(eventData.name, eventData.selector, data)
			}

		}
	} catch (error) {
		console.warn(error.message)
	}
}

/**
 * gestionnaire de formulaire :
 * - peut modifier l'url
 * - peut mettre à jour une valeur d'un input
 * - submit le formulaire
 * @param {Event} event 
 */
function globalManageForm(event) {
	// console.log('-> globalManageForm')
	try {
		const data = event.detail
		// console.log('data =', data);

		const form = document.querySelector(data.formSelector)

		// create,populate or update an input value from is attribute name
		// data {actionType: 'createAndPopInput', name: 'panier_type', value: 'xxx'}
		if (data.actionType === 'createAndPopInput') {
			let input = form.querySelector(`input[name="${data.name}"]`)
			if (!input) {
				input = document.createElement('input')
				input.name = data.name
				form.appendChild(input)
			}
			input.value = data.value
		}

		// update input
		// data {actionType: 'updateInput', selector: 'input[name="xxxx"]', value: 'xxx'}
		if (data.actionType === 'updateInput') {
			form.querySelector(data.selector).value = data.value
		}

		// change post url
		// data {actionType: 'postUrl', value: 'xxx'}
		if (data.actionType === 'postUrl') {
			form.setAttribute('hx-post', data.value)
			htmx.process(form)
		}

		// submit form
		// data {actionType: 'submit'}
		if (data.actionType === 'submit') {
			form.setAttribute('hx-trigger', 'click')
			htmx.process(form)
			// submit
			form.click()
		}

	} catch (error) {
		console.log('-> globalManageForm,', error)
	}
}


/**
 * INITIALISATION - Attache l'écouteur sur #event-organizer
 * / Initialization - Attaches listener on #event-organizer
 */
document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#event-organizer').addEventListener('organizerMsg', eventsOrganizer)
})
