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
	let total = 0
	document.querySelectorAll('#addition-form input').forEach(input => {
		if (input.name.startsWith('repid-')) {
			const lineId = input.name.substring(6) // uuid ou uuid--priceUuid
			const number = parseInt(input.value)

			// Cherche le prix unitaire dans la ligne d'affichage du panier
			// (data-unit-price est set par additionInsertArticle, gère le prix libre)
			// / Gets unit price from cart display line
			// (data-unit-price is set by additionInsertArticle, handles free price)
			const additionLine = document.querySelector(`#addition-line-${lineId}`)
			if (additionLine) {
				const unitPrice = parseInt(additionLine.dataset.unitPrice)
				total = total + (number * unitPrice)
			} else {
				// Fallback : lire depuis la tuile article (ancien format, uuid seul)
				// / Fallback: read from article tile (old format, uuid only)
				const productUuid = lineId.split('--')[0]
				const article = document.querySelector(`#products div[data-uuid="${productUuid}"]`)
				if (article) {
					const price = parseInt(article.dataset.price)
					total = total + (number * price)
				}
			}
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
	// priceUuid et customAmount sont optionnels (absents pour les articles mono-tarif)
	// / priceUuid and customAmount are optional (absent for single-rate articles)
	const priceUuid = detail.priceUuid || null
	const customAmount = detail.customAmount || null
	const weightAmount = detail.weightAmount || null
	const weightUnit = detail.weightUnit || null

	// lineId : identifiant unique de la ligne panier.
	// Pour les tarifs fixes : uuid--priceUuid (partage entre clics, qty incremente).
	// Pour les montants variables (prix libre, poids/mesure) : uuid--priceUuid--N (unique par saisie).
	// Si lineId est fourni par tarif.js, on l'utilise. Sinon on le construit (mono-tarif classique).
	// / lineId: unique cart line identifier.
	// Fixed prices: uuid--priceUuid (shared, qty increments).
	// Variable amounts (free, weight): uuid--priceUuid--N (unique per entry).
	const lineId = detail.lineId || (priceUuid ? `${uuid}--${priceUuid}` : uuid)
	const inputKey = `repid-${lineId}`

	// Supprime le placeholder "Panier vide" si le panier etait vide
	// / Removes "Empty cart" placeholder if cart was empty
	const emptyPlaceholder = document.querySelector('#addition-empty')
	if (emptyPlaceholder) { emptyPlaceholder.remove() }

	const input = document.querySelector(`#addition-form [name="${inputKey}"]`)

	// Prix affiché : le customAmount (prix libre) ou le prix standard
	// / Displayed price: customAmount (free price) or standard price
	const prixAffiche = customAmount || price

	if (input === null) {
		// Nouvel article : création input + ligne d'affichage
		const formEl = document.querySelector('#addition-form')
		formEl.insertAdjacentHTML('beforeend', `
			<input type="number" name="${inputKey}" value="1" />
		`)

		// Si prix libre ou poids/mesure, ajouter un input cache pour le montant custom.
		// La cle utilise le meme lineId que le repid (avec suffixe --N si variable).
		// / If free price or weight-based, add hidden input for custom amount.
		// Key uses the same lineId as repid (with --N suffix if variable).
		if (customAmount) {
			formEl.insertAdjacentHTML('beforeend', `
				<input type="hidden" name="custom-${lineId}" value="${customAmount}" />
			`)
		}

		// Si vente au poids/mesure, ajouter un input cache pour la quantite saisie
		// / If weight-based sale, add hidden input for entered quantity
		if (weightAmount) {
			formEl.insertAdjacentHTML('beforeend', `
				<input type="hidden" name="weight-${lineId}" value="${weightAmount}" />
			`)
		}

		const additionLine = `
			<div id="addition-line-${lineId}" data-quantity="${quantity}" data-price="${lineId}" data-unit-price="${prixAffiche}" class="addition-line-grid">
				<div class="addition-col-bt">
					<button type="button" class="addition-remove-btn" onclick="additionRemoveArticle('${lineId}');" title="Enlever un article" aria-label="Enlever ${escapeHtml(name)}">
						<i class="fas fa-minus" aria-hidden="true"></i>
					</button>
				</div>
				<div class="addition-col-info">
					<div class="addition-col-name">${escapeHtml(name)}</div>
					<div id="addition-quantity-${lineId}" class="addition-col-quantity-label">&times; ${quantity}</div>
				</div>
				<div class="addition-col-price">${(prixAffiche / 100).toFixed(2)}${currency}</div>
			</div>
		`
		document.querySelector('#addition-list').insertAdjacentHTML('beforeend', additionLine)
	} else {
		// Article existant : mise à jour quantité
		input.value = Number(quantity)
		document.querySelector(`#addition-quantity-${lineId}`).innerHTML = `&times; ${quantity}`
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
function additionRemoveArticle(lineId) {
	// lineId peut être "uuid" (mono-tarif) ou "uuid--priceUuid" (multi-tarif)
	// / lineId can be "uuid" (single-rate) or "uuid--priceUuid" (multi-rate)
	const productUuid = lineId.split('--')[0]

	const eleQuantity = document.querySelector(`#addition-quantity-${lineId}`)
	let quantity = Number(eleQuantity.textContent.replace('×', '').trim())
	quantity--

	eleQuantity.innerHTML = `&times; ${quantity}`
	document.querySelector(`#addition-form [name="repid-${lineId}"]`).value = Number(quantity)

	if (quantity === 0) {
		document.querySelector(`#addition-line-${lineId}`).remove()
		document.querySelector(`#addition-form [name="repid-${lineId}"]`).remove()
		// Supprimer aussi l'input custom si présent (prix libre)
		// / Also remove custom input if present (free price)
		const customInput = document.querySelector(`#addition-form [name="custom-${lineId}"]`)
		if (customInput) { customInput.remove() }
	}

	// Met à jour la tuile article (utilise le productUuid pour trouver la tuile)
	// / Updates article tile (uses productUuid to find the tile)
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionRemoveArticle' },
		msg: 'additionRemoveArticle',
		data: { uuid: productUuid, quantity }
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
		const inputName = input.getAttribute('name')
		// Supprime les inputs repid-* et custom-* (prix libre)
		// / Removes repid-* and custom-* (free price) inputs
		if (inputName.startsWith('repid-') || inputName.startsWith('custom-')) {
			input.remove()
		}
	})

	// Remet le placeholder "Panier vide" (le texte traduit est dans data-empty-text)
	// / Restores "Empty cart" placeholder (translated text is in data-empty-text)
	const additionList = document.querySelector('#addition-list')
	const emptyText = additionList.dataset.emptyText || 'Panier vide'
	additionList.innerHTML = `
		<div id="addition-empty" class="BF-col addition-placeholder" data-testid="addition-empty-placeholder">
			<i class="fas fa-shopping-basket" aria-hidden="true"></i>
			<span>${emptyText}</span>
		</div>
	`
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
