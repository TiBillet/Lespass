/**
 * ADDITION.JS - GESTION DU PANIER/ADDITION
 * / Shopping cart management
 * 
 * LOCALISATION : laboutik/static/js/addition.js
 * 
 * Gère la logique du panier :
 * - Ajout/suppression d'articles
 * - Calcul du total
 * - Préparation du formulaire de paiement
 * 
 * COMMUNICATION :
 * Reçoit : 'additionInsertArticle', 'additionReset', 'additionDisplayPaymentTypes', 'additionManageForm'
 * Émet : 'additionTotalChange' (vers #bt-valider), 'additionRemoveArticle' (vers #products)
 * 
 * Voir tibilletUtils.js pour le système d'événements.
 */

/**
 * Calcule le montant total du panier en centimes
 * / Calculates cart total in cents
 * 
 * Parcourt les inputs 'repid-*' du formulaire, récupère les quantités et prix,
 * puis calcule le total.
 * 
 * @returns {Number} Total en centimes
 */
function calculateTotal() {
	total = 0
	// TODO : La variable 'total' n'est pas déclarée avec 'let' ou 'const'.
	// Cela crée une variable globale implicite. Ne devrait-on pas utiliser 'let total = 0' ?
	document.querySelectorAll('#addition-form input').forEach(input => {
		if (input.name.includes('repid-')) {
			const uuid = input.name.substring(6)
			const number = parseInt(input.value)
			// TODO : Que se passe-t-il si l'article n'existe plus dans le DOM (supprimé) ?
			// document.querySelector retournera null et article.dataset.price plantera.
			// Ne devrait-on pas vérifier si 'article' existe avant d'accéder à dataset ?
			const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
			const price = parseInt(article.dataset.price)
			total = total + (number * price)
		}
	})
	return total
}

/**
 * Ajoute un article au panier
 * / Adds item to cart
 * 
 * Handler de 'additionInsertArticle'. Appelé via le flux :
 * clic article → articles.js:addArticle → 'articlesAdd' → tibilletUtils.js → CETTE FONCTION
 * 
 * Actions :
 * - Crée input caché 'repid-{uuid}' dans le formulaire
 * - Crée ligne d'affichage dans #addition-list
 * - Recalcule le total et émet 'additionTotalChange'
 * 
 * @param {Object} param0 - event.detail contenant uuid, price, quantity, name, currency
 */
function additionInsertArticle({ detail }) {
	const { uuid, price, quantity, name, currency } = detail

	const input = document.querySelector(`#addition-form [name="repid-${uuid}"]`)
	
	if (input === null) {
		// Nouvel article : création input + ligne d'affichage
		document.querySelector('#addition-form').insertAdjacentHTML('beforeend', `
			<input type="number" name="repid-${uuid}" value="1" />
		`)
		
		const additionLine = `
			<div id="addition-line-${uuid}" data-quantity="${quantity}" data-price="${uuid}" class="addition-line-grid">
				<div class="addition-col-bt BF-col">
					<i class="fas fa-minus-square" onclick="additionRemoveArticle('${uuid}');" title="Enlever un article !"></i>
				</div>
				<div id="addition-quantity-${uuid}" class="addition-col-quantity BF-col">${quantity}</div>
				<div class="addition-col-name BF-col">${name}</div>
				<div class="addition-col-price BF-col">${price / 100}${currency}</div>
			</div>
		`
		document.querySelector('#addition-list').insertAdjacentHTML('beforeend', additionLine)
	} else {
		// Article existant : mise à jour quantité
		input.value = Number(quantity)
		document.querySelector(`#addition-line-${uuid} .addition-col-quantity`).innerText = quantity
	}
	
	const totalAddition = calculateTotal()

	// Met à jour le bouton VALIDER
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionInsertArticle' },
		msg: 'additionTotalChange',
		data: { totalAddition }
	})

	document.querySelector('#addition-total').value = totalAddition
}

/**
 * Retire un article du panier (décrémente)
 * / Removes item from cart (decrements)
 * 
 * Appelée par onclick sur le bouton "-" dans la ligne du panier.
 * Supprime la ligne si quantité atteint 0.
 * Émet 'additionRemoveArticle' pour maj l'affichage sur la tuile.
 * 
 * @param {String} uuid - UUID de l'article
 */
function additionRemoveArticle(uuid) {
	const eleQuantity = document.querySelector(`#addition-quantity-${uuid}`)
	let quantity = Number(eleQuantity.innerText)
	quantity--
	
	eleQuantity.innerText = quantity
	document.querySelector(`#addition-form [name="repid-${uuid}"]`).value = Number(quantity)
	
	if (quantity === 0) {
		document.querySelector(`#addition-line-${uuid}`).remove()
		document.querySelector(`#addition-form [name="repid-${uuid}"]`).remove()
	}

	// Met à jour la tuile article
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionRemoveArticle' },
		msg: 'additionRemoveArticle',
		data: { uuid, quantity }
	})

	const totalAddition = calculateTotal()

	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionRemoveArticle' },
		msg: 'additionTotalChange',
		data: { totalAddition }
	})

	document.querySelector('#addition-total').value = totalAddition
}

/**
 * Réinitialise le panier
 * / Resets cart
 * 
 * Handler de 'additionReset'. Vide tout :
 * - Supprime les inputs 'repid-*'
 * - Vide #addition-list
 * - Réinitialise les champs du formulaire
 * 
 * Déclenché par clic sur RESET → 'resetArticles' → tibilletUtils.js → CETTE FONCTION
 */
function additionReset() {
	const allInputs = document.querySelectorAll('#addition-form input')
	allInputs.forEach((input) => {
		if (input.getAttribute('name').includes('repid-')) {
			input.remove()
		}
	})

	document.querySelector('#addition-list').innerHTML = ''
	document.querySelector('#addition-comportement').value = ''
	document.querySelector('#addition-total').value = ''
	document.querySelector('#addition-moyen-paiement').value = ''
	document.querySelector('#addition-uuid-transaction').value = ''
	document.querySelector('#addition-given-sum').value = ''

	// Réinitialise l'URL et le trigger HTMX du formulaire.
	// additionDisplayPaymentTypes() change hx-trigger vers 'click',
	// additionManageForm('postUrl') change hx-post vers /payer/.
	// Sans ce reset, le 2ème paiement envoie directement à /payer/ sans passer par /moyens_paiement/.
	// / Reset the form's HTMX URL and trigger.
	// Without this, the 2nd payment posts directly to /payer/ skipping /moyens_paiement/.
	const form = document.querySelector('#addition-form')
	const urlInitiale = form.getAttribute('data-url-reset')
	if (urlInitiale) {
		form.setAttribute('hx-post', urlInitiale)
	}
	form.setAttribute('hx-trigger', 'validerPaiement')
	htmx.process(form)

	const totalAddition = calculateTotal()

	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionReset' },
		msg: 'additionTotalChange',
		data: { totalAddition }
	})

	document.querySelector('#addition-total').value = totalAddition
}

/**
 * Affiche les types de paiement
 * / Displays payment types
 *
 * Handler de 'additionDisplayPaymentTypes'. Appelé par clic sur VALIDER.
 *
 * Logique :
 * - Si panier vide : affiche #message-no-article
 * - Si articles présents : déclenche le formulaire HTMX pour charger les options de paiement
 *
 * IMPORTANT - GESTION DE L'URL :
 * L'URL de l'endpoint est définie dans le template addition.html via hx-post.
 * NE PAS utiliser form.setAttribute('hx-post', ...) ici car cela écraserait l'URL
 * correcte par une chaîne littérale (cause du bug 404 précédent).
 *
 * Déclenché par clic VALIDER → 'additionDisplayPaymentTypes' → tibilletUtils.js → CETTE FONCTION
 */
function additionDisplayPaymentTypes() {
	let nbArticles = 0
	const form = document.querySelector('#addition-form')
	
	// Compte les articles (inputs repid-*)
	form.querySelectorAll('input').forEach(ele => {
		const name = ele.getAttribute('name')
		if (name.includes('repid-')) {
			nbArticles++
		}
	})

	if (nbArticles <= 0) {
		document.querySelector('#message-no-article').classList.remove('hide')
	} else {
		/**
		 * CORRECTION DU BUG 404 :
		 * ------------------------
		 * L'URL est déjà définie dans le template addition.html via :
		 * hx-post="{% url 'laboutik-paiement-moyens_paiement' %}"
		 * 
		 * Ancien code (supprimé) :
		 * form.setAttribute('hx-post', 'hx_display_type_payment')
		 * → Cette ligne écrasait l'URL correcte par une chaîne littérale,
		 *   causant une requête vers /hx_display_type_payment (404)
		 * 
		 * SOLUTION : On ne touche PAS à hx-post, l'URL est déjà bonne dans le HTML.
		 * On configure seulement hx-trigger='click' pour déclencher la requête.
		 */
		
		// Active le déclenchement au clic
		form.setAttribute('hx-trigger', 'click')
		
		// Processe HTMX pour prendre en compte le nouvel attribut hx-trigger
		htmx.process(form)
		
		// Déclenche le formulaire pour charger partial/hx_display_type_payment.html
		form.click()
	}
}

/**
 * Modifie dynamiquement le formulaire
 * / Dynamically modifies form
 * 
 * Handler de 'additionManageForm'. Permet aux partials HTMX de modifier le formulaire.
 * 
 * Actions supportées (actionType) :
 * - 'updateInput' : Met à jour valeur d'un input (selector, value)
 * - 'postUrl' : Change l'URL HTMX (value)
 * - 'submit' : Soumet le formulaire
 * 
 * Appelée depuis les partials via askAdditionManageForm() dans tibilletUtils.js
 * 
 * @param {Object} event - Événement avec event.detail contenant actionType, selector, value
 */
function additionManageForm(event) {
	try {
		const data = event.detail
		const form = document.querySelector('#addition-form')

		if (data.actionType === 'updateInput') {
			form.querySelector(data.selector).value = data.value
		}

		if (data.actionType === 'postUrl') {
			form.setAttribute('hx-post', data.value)
			htmx.process(form)
		}

		if (data.actionType === 'submit') {
			form.setAttribute('hx-trigger', 'click')
			htmx.process(form)
			form.click()
		}

	} catch (error) {
		console.log('-> addition.js - additionManageForm,', error)
	}
}

/**
 * INITIALISATION - Attache les handlers sur #addition
 * / Initialization - Attaches handlers on #addition
 */
document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#addition').addEventListener('additionInsertArticle', additionInsertArticle)
	document.querySelector('#addition').addEventListener('additionReset', additionReset)
	document.querySelector('#addition').addEventListener('additionDisplayPaymentTypes', additionDisplayPaymentTypes)
	document.querySelector('#addition').addEventListener('additionManageForm', additionManageForm)
})
