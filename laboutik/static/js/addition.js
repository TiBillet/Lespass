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
 * Émet : 'additionTotalChange' (vers #addition), 'additionRemoveArticle' (vers #products)
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
 * Met a jour l'en-tete et le bas du ticket
 * / Updates the ticket header and footer
 *
 * En-tete : pastille de comptage + bouton VIDER.
 * Bas : total affiche + bouton VALIDER actif ou non.
 * / Header: count pill + EMPTY button. Footer: displayed total + VALIDATE
 * button enabled or not.
 *
 * Le nombre affiche est la somme des quantites des lignes du panier, lue sur
 * les inputs repid-* du formulaire (meme source que calculateTotal).
 * Panier vide : la pastille retombe sur "—" et le bouton VIDER est desactive.
 *
 * Gardes null partout : l'en-tete n'existe que sur l'interface de vente, pas
 * sur les vues ou #addition est absent (ventes, tables...).
 *
 * / The displayed number is the sum of the cart line quantities, read from the
 * form's repid-* inputs (same source as calculateTotal).
 * Empty cart: the pill falls back to "—" and the EMPTY button is disabled.
 * Null-guarded: the header only exists on the sales interface.
 */
function additionMajEntete() {
	let nombreArticles = 0
	document.querySelectorAll('#addition-form input').forEach(input => {
		if (input.name.startsWith('repid-')) {
			nombreArticles += Number(input.value) || 0
		}
	})

	const eleCompteur = document.querySelector('#addition-count')
	if (eleCompteur) {
		// Libelles traduits poses par le template (cotton/addition.html)
		// / Translated labels set by the template
		const libelleUn = eleCompteur.dataset.labelUn || 'article'
		const libellePlusieurs = eleCompteur.dataset.labelPlusieurs || 'articles'
		const libelle = nombreArticles > 1 ? libellePlusieurs : libelleUn
		eleCompteur.textContent = nombreArticles > 0 ? `${nombreArticles} ${libelle}` : '\u2014'
	}

	const eleVider = document.querySelector('#addition-vider')
	if (eleVider) {
		eleVider.disabled = nombreArticles === 0
		// Panier vide = plus rien a confirmer, on desarme
		// / Empty cart = nothing left to confirm, disarm
		if (nombreArticles === 0) { additionDesarmerVider() }
	}

	// Le total affiche, lui, est ecrit par additionMajTotal() (handler de
	// l'evenement additionTotalChange) : un seul ecrivain par element.
	// / The displayed total is written by additionMajTotal(), the
	// additionTotalChange handler: one writer per element.
	const eleValider = document.querySelector('#addition-bt-valider')
	if (eleValider) {
		eleValider.disabled = nombreArticles === 0
	}
}

/**
 * Met a jour une ligne du ticket : quantite affichee et total de la ligne
 * / Updates a ticket row: displayed quantity and row total
 *
 * Le total de la ligne est recalcule depuis data-unit-price, qui porte deja le
 * prix unitaire reel (prix libre et vente au poids compris).
 * / The row total is recomputed from data-unit-price, which already carries the
 * real unit price (free price and weight-based sales included).
 *
 * @param {String} lineId - Identifiant de la ligne panier
 * @param {Number} quantity - Nouvelle quantite
 */
function additionMajLigne(lineId, quantity) {
	const ligne = document.querySelector(`#addition-line-${lineId}`)
	if (!ligne) { return }

	ligne.dataset.quantity = quantity

	const eleQuantite = document.querySelector(`#addition-quantity-${lineId}`)
	if (eleQuantite) { eleQuantite.innerHTML = `&times; ${quantity}` }

	const eleTotalLigne = document.querySelector(`#addition-price-${lineId}`)
	if (eleTotalLigne) {
		const prixUnitaire = Number(ligne.dataset.unitPrice) || 0
		const monnaie = eleTotalLigne.dataset.currency || ''
		eleTotalLigne.textContent = `${(prixUnitaire * quantity / 100).toFixed(2)}${monnaie}`
	}
}

/**
 * Ecrit le total dans le bas du ticket
 * / Writes the total at the bottom of the ticket
 *
 * Handler de 'additionTotalChange' (table switches de tibilletUtils.js), emis
 * par additionInsertArticle(), additionRemoveArticle() et additionReset().
 * Reprend mot pour mot ce que faisait footer.js:updateSumOfValidateButton()
 * sur #bt-valider-total, quand le footer pleine largeur existait encore.
 * / Handler of 'additionTotalChange', emitted by the three cart functions.
 * Does exactly what footer.js:updateSumOfValidateButton() used to do.
 *
 * @param {Event} event - event.detail.totalAddition, total en centimes
 */
function additionMajTotal(event) {
	const eleTotal = document.querySelector('#addition-total-affiche')
	if (!eleTotal) { return }

	const totalCentimes = Number(event.detail.totalAddition) || 0
	const monnaie = eleTotal.dataset.currency || ''
	eleTotal.textContent = `${(totalCentimes / 100).toFixed(2)} ${monnaie}`.trim()
}

/**
 * Rejoue une classe d'animation sur un element
 * / Replays an animation class on an element
 *
 * Le retrait + reflow force est indispensable : sans lui, une classe deja
 * posee ne relancerait pas son animation. La classe est retiree a la fin.
 * / The remove + forced reflow is required: an already-present class would not
 * restart its animation. The class is removed once the animation ends.
 *
 * @param {HTMLElement} element - Element a animer
 * @param {String} classe - Classe d'animation (is-new, is-removed...)
 */
function additionRejouerAnimation(element, classe) {
	element.classList.remove(classe)
	void element.offsetWidth  // reflow force / forced reflow
	element.classList.add(classe)
	element.addEventListener('animationend', () => element.classList.remove(classe), { once: true })
}

/**
 * Flash vert sur la ligne qui vient d'etre ajoutee ou incrementee
 * / Green flash on the line that was just added or incremented
 *
 * @param {String} lineId - Identifiant de la ligne panier
 */
function additionFlashAjout(lineId) {
	const ligne = document.querySelector(`#addition-line-${lineId}`)
	if (ligne) { additionRejouerAnimation(ligne, 'is-new') }
}

/**
 * Flash rouge sur la ligne qui vient d'etre decrementee
 * / Red flash on the line that was just decremented
 *
 * @param {String} lineId - Identifiant de la ligne panier
 */
function additionFlashRetrait(lineId) {
	const ligne = document.querySelector(`#addition-line-${lineId}`)
	if (ligne) { additionRejouerAnimation(ligne, 'is-removed') }
}

/**
 * Fait disparaitre une ligne dont la quantite est tombee a zero
 * / Fades out a line whose quantity dropped to zero
 *
 * La ligne reste a l'ecran le temps de l'animation rouge, mais ses id sont
 * retires immediatement : si le meme article est re-ajoute dans la foulee, les
 * selecteurs ne doivent plus tomber sur la ligne en train de disparaitre.
 * Le pointer-events:none du CSS empeche un second clic sur son bouton moins.
 * Le setTimeout est un filet de securite si animationend ne part pas
 * (animations desactivees par le systeme).
 *
 * / The row stays on screen for the length of the red animation, but its ids
 * are stripped at once: if the same article is re-added right away, selectors
 * must not find the vanishing row. The CSS pointer-events:none blocks a second
 * click on its minus button. The setTimeout is a safety net in case
 * animationend never fires (system-disabled animations).
 *
 * @param {String} lineId - Identifiant de la ligne panier
 */
function additionRetirerLigneAnimee(lineId) {
	const ligne = document.querySelector(`#addition-line-${lineId}`)
	if (!ligne) { return }

	const eleQuantite = ligne.querySelector(`#addition-quantity-${lineId}`)
	if (eleQuantite) { eleQuantite.removeAttribute('id') }
	const eleTotalLigne = ligne.querySelector(`#addition-price-${lineId}`)
	if (eleTotalLigne) { eleTotalLigne.removeAttribute('id') }
	ligne.removeAttribute('id')

	ligne.classList.add('is-removing')
	ligne.addEventListener('animationend', () => ligne.remove(), { once: true })
	setTimeout(() => ligne.remove(), 600)
}

/**
 * Bouton VIDER du ticket — confirmation en deux temps
 * / Ticket EMPTY button — two-step confirmation
 *
 * Premier appui : le bouton s'arme (rouge, libelle "Confirmer") et se desarme
 * tout seul apres 2,6 s. Deuxieme appui : emet 'resetArticles', le meme
 * evenement que le bouton RESET du footer (footer.js:manageReset), qui vide a
 * la fois l'addition et les quantites des tuiles.
 * / First tap arms the button (red, "Confirm" label), auto-disarming after
 * 2.6s. Second tap emits 'resetArticles' — the same event as the footer RESET
 * button — which clears both the cart and the tile quantities.
 *
 * Appele par l'attribut onclick du bouton (cotton/addition.html).
 */
let additionViderTimer = null

function additionArmerVider() {
	const bouton = document.querySelector('#addition-vider')
	if (!bouton || bouton.disabled) { return }

	if (!bouton.classList.contains('is-armed')) {
		bouton.classList.add('is-armed')
		bouton.querySelector('.addition-vider-label').textContent = bouton.dataset.labelConfirmer
		additionViderTimer = setTimeout(additionDesarmerVider, 2600)
		return
	}

	additionDesarmerVider()
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'addition.js', method: 'additionArmerVider' },
		msg: 'resetArticles',
		data: {}
	})
}

/**
 * Remet le bouton VIDER dans son etat de repos
 * / Puts the EMPTY button back to its resting state
 */
function additionDesarmerVider() {
	clearTimeout(additionViderTimer)
	const bouton = document.querySelector('#addition-vider')
	if (!bouton) { return }
	bouton.classList.remove('is-armed')
	bouton.querySelector('.addition-vider-label').textContent = bouton.dataset.labelVider
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

		// Ligne du ticket, composition de la maquette (.tk-line) :
		// bouton moins | nom + prix unitaire | quantite + total de la ligne.
		// / Ticket row, mockup composition (.tk-line):
		// minus button | name + unit price | quantity + row total.
		const additionLine = `
			<div id="addition-line-${lineId}" data-quantity="${quantity}" data-price="${lineId}" data-unit-price="${prixAffiche}" class="addition-line-grid">
				<div class="addition-col-bt">
					<button type="button" class="addition-remove-btn" onclick="additionRemoveArticle('${lineId}');" title="Enlever un article" aria-label="Enlever ${escapeHtml(name)}">
						<i class="fas fa-minus" aria-hidden="true"></i>
					</button>
				</div>
				<div class="addition-col-info">
					<div class="addition-col-name">${escapeHtml(name)}</div>
					<div class="addition-col-unit">${(prixAffiche / 100).toFixed(2)}${currency}</div>
				</div>
				<div class="addition-col-right">
					<span id="addition-quantity-${lineId}" class="addition-col-quantity">&times; ${quantity}</span>
					<span id="addition-price-${lineId}" class="addition-col-price" data-currency="${currency}">${(prixAffiche * quantity / 100).toFixed(2)}${currency}</span>
				</div>
			</div>
		`
		document.querySelector('#addition-list').insertAdjacentHTML('beforeend', additionLine)
	} else {
		// Article existant : mise à jour quantité (et total de la ligne)
		// / Existing item: quantity update (and row total)
		input.value = Number(quantity)
		additionMajLigne(lineId, quantity)
	}

	// Flash vert sur la ligne touchée — nouvelle comme mise à jour
	// / Green flash on the touched line — new or updated
	additionFlashAjout(lineId)

	const totalAddition = calculateTotal()

	// Met à jour le bouton VALIDER
	sendEventOrganizer({
		src: { file: 'addition.js', method: 'additionInsertArticle' },
		msg: 'additionTotalChange',
		data: { totalAddition }
	})

	document.querySelector('#addition-total').value = totalAddition
	additionMajEntete()
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

	// Ligne deja en train de disparaitre (ses id ont ete retires) : on ignore.
	// Le pointer-events:none de .is-removing bloque deja le clic, ceci couvre
	// le cas ou le CSS n'aurait pas ete applique.
	// / Row already vanishing (its ids were stripped): ignore. The CSS
	// pointer-events:none already blocks the click; this covers the case where
	// the stylesheet did not apply.
	const eleQuantity = document.querySelector(`#addition-quantity-${lineId}`)
	if (!eleQuantity) { return }

	let quantity = Number(eleQuantity.textContent.replace('×', '').trim())
	quantity--

	additionMajLigne(lineId, quantity)
	document.querySelector(`#addition-form [name="repid-${lineId}"]`).value = Number(quantity)

	if (quantity === 0) {
		// La ligne part en fondu rouge ; les inputs, eux, disparaissent tout de
		// suite pour que le total et le compteur soient justes immediatement.
		// / The row fades out in red; the inputs are removed at once so the
		// total and the counter are correct straight away.
		additionRetirerLigneAnimee(lineId)
		document.querySelector(`#addition-form [name="repid-${lineId}"]`).remove()
		// Supprimer aussi l'input custom si présent (prix libre)
		// / Also remove custom input if present (free price)
		const customInput = document.querySelector(`#addition-form [name="custom-${lineId}"]`)
		if (customInput) { customInput.remove() }
	} else {
		// Flash rouge sur la ligne décrémentée
		// / Red flash on the decremented line
		additionFlashRetrait(lineId)
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
	additionMajEntete()
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
	additionMajEntete()
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

	// Fermer l'overlay tarif s'il est encore ouvert (vrac/multi-tarif).
	// Sans ca, #products contient toujours l'overlay numpad au moment du paiement
	// et le broadcast WebSocket post-vente ne trouve pas les badges stock cibles
	// (htmx:oobErrorNoTarget). Cf. Session 35 §10.2.
	// / Close the rate overlay if still open. Without this, #products holds the
	// numpad overlay during payment and the post-sale WS broadcast can't find
	// the stock badge targets (htmx:oobErrorNoTarget).
	if (typeof tarifClose === 'function') {
		tarifClose()
	}

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
	console.log('-> additionManageForm - event.detail =', event.detail)
	try {
		const data = event.detail
		const form = document.querySelector('#addition-form')

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
	document.querySelector('#addition').addEventListener('additionMajTotal', additionMajTotal)
	document.querySelector('#addition').addEventListener('additionReset', additionReset)
	document.querySelector('#addition').addEventListener('additionDisplayPaymentTypes', additionDisplayPaymentTypes)
	document.querySelector('#addition').addEventListener('additionManageForm', additionManageForm)
})
