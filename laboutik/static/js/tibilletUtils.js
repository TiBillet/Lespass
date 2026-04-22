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
 * Affiche un message dans l'overlay de debug visible à l'écran (Android WebView).
 * Tombe en dégradé sur console.log si l'overlay n'existe pas (navigateur desktop).
 * Cliquer sur l'overlay pour le vider.
 * / Shows a message in the on-screen debug overlay (Android WebView).
 * Falls back to console.log if overlay doesn't exist (desktop browser).
 * Click overlay to clear it.
 *
 * SUPPRIMER une fois le bug de recharge NFC résolu.
 * / REMOVE once NFC recharge bug is resolved.
 */
function debugLog(msg) {
	console.log(msg)
}

// Capture les erreurs JS non gérées et les affiche dans le debug overlay.
// / Captures unhandled JS errors and shows them in the debug overlay.
window.onerror = function(message, source, lineno, colno, error) {
	debugLog('ERR: ' + message + ' (' + (source || '').split('/').pop() + ':' + lineno + ')')
	return false
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
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'hx_display_type_payement.html', method: 'additionUpdateForm' },
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
 * - additionTotalChange → updateBtValider sur #bt-valider (maj total)
 * - additionRemoveArticle → articlesRemove sur #products (maj quantité tuile)
 * - resetArticles → additionReset sur #addition + articlesReset sur #products (reset complet)
 * - additionDisplayPaymentTypes → additionDisplayPaymentTypes sur #addition (affiche paiements)
 * - additionManageForm → additionManageForm sur #addition (modifie formulaire)
 */
const switches = {
	articlesAdd: [{ name: 'additionInsertArticle', selector: '#addition' }],
	additionTotalChange: [{ name: 'updateBtValider', selector: '#bt-valider' }],
	additionRemoveArticle: [{ name: 'articlesRemove', selector: '#products' }],
	resetArticles: [{ name: 'additionReset', selector: '#addition' }, { name: 'articlesReset', selector: '#products' }],
	articlesDisplayCategory: [{ name: 'articlesDisplayCategory', selector: '#products' }],
	additionDisplayPaymentTypes: [{ name: 'additionDisplayPaymentTypes', selector: '#addition' }],
	additionManageForm: [{ name: 'additionManageForm', selector: '#addition' }],
	primaryCardManageForm: [{ name: 'primaryCardManageForm', selector: '#form-nfc' }],
	checkCardManageForm: [{ name: 'checkCardManageForm', selector: '#form-check-nfc' }],
	tarifSelection: [{ name: 'tarifSelection', selector: '#products' }]
}

/**
 * ORGANISATEUR D'ÉVÉNEMENTS - RÉCEPTEUR CENTRAL
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

		// Trace les messages critiques pour le debug Android.
		// / Traces critical messages for Android debug.
		if (msg === 'additionManageForm') {
			debugLog('EVT additionManageForm action=' + (data && data.actionType))
		}

		// Récupère les routes depuis la table switches
		const eventSwitch = switches[msg]

		// TODO : Si 'msg' n'existe pas dans 'switches', eventSwitch sera undefined
		// et le forEach plantera. Ne devrait-on pas vérifier si eventSwitch existe
		// ou logger un warning pour les événements non reconnus ?

		// Envoie l'événement vers chaque destination
		for (let i = 0; i < eventSwitch.length; i++) {
			const eventData = eventSwitch[i];
			sendEvent(eventData.name, eventData.selector, data)
		}
	} catch (error) {
		// Silencieux en production
		debugLog('EVT ERR: ' + error)
	}
}

/**
 * INITIALISATION - Attache l'écouteur sur #event-organizer
 * / Initialization - Attaches listener on #event-organizer
 */
document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#event-organizer').addEventListener('organizerMsg', eventsOrganizer)
})
