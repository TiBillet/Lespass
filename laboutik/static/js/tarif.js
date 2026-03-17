/**
 * TARIF.JS - OVERLAY DE SÉLECTION DE TARIF (MULTI-TARIF + PRIX LIBRE)
 * / Rate selection overlay (multi-rate + free price)
 *
 * LOCALISATION : laboutik/static/js/tarif.js
 *
 * Affiche un overlay plein écran quand un article multi-tarif est cliqué.
 * Le caissier choisit le tarif voulu, et l'article est ajouté au panier
 * avec le bon prix et le bon price_uuid.
 *
 * COMMUNICATION :
 * Reçoit : 'tarifSelection' depuis articles.js (via tibilletUtils.js)
 * Émet : 'articlesAdd' (vers #addition via tibilletUtils.js) avec priceUuid
 *
 * FLUX :
 * 1. Clic article multi-tarif → articles.js:manageKey() → 'tarifSelection'
 * 2. tibilletUtils.js route vers CETTE FONCTION
 * 3. Génère l'overlay HTML avec les boutons tarif
 * 4. Clic tarif fixe → ajoute au panier directement
 * 5. Clic tarif prix libre → affiche input → validation → ajoute au panier
 */

/**
 * Affiche l'overlay de sélection de tarif
 * / Shows rate selection overlay
 *
 * Génère le HTML de l'overlay côté client (les données tarifs sont déjà
 * dans les data-attributes de l'article, transmises via l'événement).
 *
 * @param {Object} event - Événement avec event.detail contenant uuid, name, tarifs, currency
 */
function tarifSelection(event) {
	const { uuid, name, tarifs, currency } = event.detail

	// Construit les boutons de tarif
	// / Builds rate buttons
	let boutonsHtml = ''
	for (let i = 0; i < tarifs.length; i++) {
		const tarif = tarifs[i]
		const prixAffiche = (tarif.prix_centimes / 100).toFixed(2)

		if (tarif.free_price) {
			// Tarif prix libre : bouton qui ouvre l'input
			// / Free price rate: button that opens input
			boutonsHtml += `
				<div class="tarif-btn tarif-btn-free" data-testid="tarif-btn-free-${tarif.price_uuid}">
					<div class="tarif-btn-label">${tarif.name}</div>
					<div class="tarif-btn-sublabel">min ${prixAffiche} ${currency}</div>
					<div id="tarif-free-input-${tarif.price_uuid}" class="tarif-free-input-container">
						<input type="number"
							id="tarif-free-amount-${tarif.price_uuid}"
							class="tarif-free-input"
							min="${prixAffiche}"
							step="0.10"
							placeholder="${prixAffiche}"
							inputmode="decimal"
							aria-label="Montant libre"
							data-testid="tarif-free-input-${tarif.price_uuid}"
						/>
						<span class="tarif-free-currency" aria-hidden="true">${currency}</span>
						<button type="button"
							class="tarif-free-validate"
							onclick="tarifValidateFreePrix('${uuid}', '${tarif.price_uuid}', ${tarif.prix_centimes}, '${name} (${tarif.name})', '${currency}')"
							data-testid="tarif-free-validate-${tarif.price_uuid}"
						>OK</button>
					</div>
					<div id="tarif-free-error-${tarif.price_uuid}" class="tarif-free-error" role="alert"></div>
				</div>
			`
		} else {
			// Tarif fixe : clic direct → ajout au panier
			// / Fixed rate: direct click → add to cart
			boutonsHtml += `
				<button type="button"
					class="tarif-btn"
					onclick="tarifSelectFixed('${uuid}', '${tarif.price_uuid}', ${tarif.prix_centimes}, '${name} (${tarif.name})', '${currency}')"
					data-testid="tarif-btn-${tarif.price_uuid}"
				>
					<div class="tarif-btn-label">${tarif.name}</div>
					<div class="tarif-btn-price">${prixAffiche} ${currency}</div>
				</button>
			`
		}
	}

	// Injecte l'overlay dans #messages et le rend visible.
	// hideAndEmptyElement() met .hide sur #messages quand on ferme un overlay.
	// Il faut retirer .hide quand on injecte du nouveau contenu.
	// / Injects overlay into #messages and makes it visible.
	// hideAndEmptyElement() sets .hide on #messages when closing an overlay.
	// We must remove .hide when injecting new content.
	const messagesEl = document.querySelector('#messages')
	messagesEl.innerHTML = `
		<div id="tarif-overlay" class="tarif-overlay" data-testid="tarif-overlay">
			<div class="tarif-overlay-content">
				<h2 class="tarif-overlay-title">${name}</h2>
				<div class="tarif-overlay-subtitle">Choisir un tarif</div>
				<div class="tarif-list">
					${boutonsHtml}
				</div>
				<button type="button"
					class="tarif-btn-retour"
					onclick="tarifClose()"
					data-testid="tarif-btn-retour"
				>
					<i class="fas fa-arrow-left" aria-hidden="true"></i> RETOUR
				</button>
			</div>
		</div>
	`
	messagesEl.classList.remove('hide')
}

/**
 * Sélectionne un tarif fixe et ajoute au panier
 * / Selects a fixed rate and adds to cart
 *
 * @param {String} productUuid - UUID du produit
 * @param {String} priceUuid - UUID du prix sélectionné
 * @param {Number} prixCentimes - Prix en centimes
 * @param {String} displayName - Nom affiché (produit + tarif)
 * @param {String} currency - Symbole monétaire
 */
function tarifSelectFixed(productUuid, priceUuid, prixCentimes, displayName, currency) {
	tarifClose()
	addArticleWithPrice(productUuid, priceUuid, prixCentimes, displayName, currency)
}

/**
 * Valide le montant du prix libre et ajoute au panier
 * / Validates free price amount and adds to cart
 *
 * Vérifie que le montant saisi est >= au minimum (prix_centimes).
 * Si valide, ajoute au panier. Sinon, affiche une erreur.
 *
 * @param {String} productUuid - UUID du produit
 * @param {String} priceUuid - UUID du prix
 * @param {Number} minimumCentimes - Prix minimum en centimes
 * @param {String} displayName - Nom affiché
 * @param {String} currency - Symbole monétaire
 */
function tarifValidateFreePrix(productUuid, priceUuid, minimumCentimes, displayName, currency) {
	const inputEl = document.querySelector(`#tarif-free-amount-${priceUuid}`)
	const errorEl = document.querySelector(`#tarif-free-error-${priceUuid}`)
	const montantSaisi = parseFloat(inputEl.value)

	// Validation : le montant doit être un nombre >= minimum
	// / Validation: amount must be a number >= minimum
	if (isNaN(montantSaisi) || montantSaisi <= 0) {
		errorEl.textContent = 'Entrez un montant valide'
		inputEl.classList.add('tarif-input-error')
		return
	}

	const minimumEuros = minimumCentimes / 100
	if (montantSaisi < minimumEuros) {
		errorEl.textContent = `Minimum : ${minimumEuros.toFixed(2)} ${currency}`
		inputEl.classList.add('tarif-input-error')
		return
	}

	// Montant valide : convertir en centimes et ajouter au panier
	// / Valid amount: convert to cents and add to cart
	const montantCentimes = Math.round(montantSaisi * 100)
	tarifClose()
	addArticleWithPrice(productUuid, priceUuid, montantCentimes, displayName, currency, montantCentimes)
}

/**
 * Ajoute un article au panier avec un price_uuid spécifique
 * / Adds an article to cart with a specific price_uuid
 *
 * Émet l'événement 'articlesAdd' avec les données enrichies (priceUuid, customAmount).
 * Incrémente aussi la quantité sur la tuile article.
 *
 * @param {String} productUuid - UUID du produit
 * @param {String} priceUuid - UUID du prix sélectionné
 * @param {Number} prixCentimes - Prix en centimes
 * @param {String} displayName - Nom affiché dans le panier
 * @param {String} currency - Symbole monétaire
 * @param {Number|null} customAmount - Montant custom en centimes (prix libre) ou null
 */
function addArticleWithPrice(productUuid, priceUuid, prixCentimes, displayName, currency, customAmount) {
	// Cherche la quantité actuelle dans le panier pour ce tarif spécifique
	// / Gets current quantity in cart for this specific rate
	const lineId = `${productUuid}--${priceUuid}`
	const existingInput = document.querySelector(`#addition-form [name="repid-${lineId}"]`)
	let quantity = existingInput ? Number(existingInput.value) + 1 : 1

	// Incrémente la quantité sur la tuile article
	// / Increment quantity on article tile
	try {
		const eleQuantity = document.querySelector(`#article-quantity-number-${productUuid}`)
		let tileQty = Number(eleQuantity.innerText)
		tileQty++
		eleQuantity.innerText = tileQty
		eleQuantity.classList.add('badge-visible')
	} catch (error) {
		console.log('-> tarif.js - addArticleWithPrice, tile update error:', error)
	}

	// Émet l'événement pour ajouter au panier (avec priceUuid)
	// / Emits event to add to cart (with priceUuid)
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'tarif.js', method: 'addArticleWithPrice' },
		msg: 'articlesAdd',
		data: {
			uuid: productUuid,
			priceUuid: priceUuid,
			price: prixCentimes,
			quantity: quantity,
			name: displayName,
			currency: currency,
			customAmount: customAmount || null,
		}
	})
}

/**
 * Ferme l'overlay de sélection de tarif
 * / Closes rate selection overlay
 */
function tarifClose() {
	// Retire l'overlay et cache #messages (meme logique que hideAndEmptyElement)
	// / Removes overlay and hides #messages (same logic as hideAndEmptyElement)
	const messagesEl = document.querySelector('#messages')
	messagesEl.classList.add('hide')
	messagesEl.innerHTML = ''
}

/**
 * INITIALISATION - Attache le handler tarifSelection sur #messages
 * / Initialization - Attaches tarifSelection handler on #messages
 */
document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#messages').addEventListener('tarifSelection', tarifSelection)
})
