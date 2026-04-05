/**
 * TARIF.JS - OVERLAY DE SÉLECTION DE TARIF (MULTI-TARIF + PRIX LIBRE + POIDS/MESURE)
 * / Rate selection overlay (multi-rate + free price + weight/measure)
 *
 * LOCALISATION : laboutik/static/js/tarif.js
 *
 * Affiche un overlay dans #products quand un article multi-tarif est cliqué.
 * Le caissier choisit le tarif voulu, et l'article est ajouté au panier
 * avec le bon prix et le bon price_uuid. L'overlay reste ouvert pour le multi-clic.
 *
 * COMMUNICATION :
 * Reçoit : 'tarifSelection' depuis articles.js (via tibilletUtils.js)
 * Émet : 'articlesAdd' (vers #addition via tibilletUtils.js) avec priceUuid
 *
 * FLUX :
 * 1. Clic article multi-tarif → articles.js:manageKey() → 'tarifSelection'
 * 2. tibilletUtils.js route vers #products
 * 3. Génère l'overlay HTML avec les boutons tarif
 * 4. Clic tarif fixe → ajoute au panier (overlay reste ouvert)
 * 5. Clic tarif prix libre → validation → ajoute au panier (overlay reste ouvert)
 * 6. Clic tarif poids/mesure → pavé numérique → OK → ajoute au panier
 * 7. Bouton RETOUR → restaure la grille articles
 */

// escapeHtml() est défini dans tibilletUtils.js (chargé dans le <head>).
// / escapeHtml() is defined in tibilletUtils.js (loaded in <head>).

/**
 * Affiche l'overlay de sélection de tarif dans #products
 * / Shows rate selection overlay in #products
 *
 * L'overlay se superpose a la grille articles (position absolute).
 * Le panier (#addition) reste visible et accessible.
 * / Overlay covers article grid (position absolute).
 * Cart (#addition) stays visible and accessible.
 *
 * @param {Object} event - Événement avec event.detail contenant uuid, name, tarifs, currency
 */
function tarifSelection(event) {
	const { uuid, name, tarifs, currency } = event.detail

	// Construire les boutons : 3 types (fixe, prix libre, poids/mesure)
	// / Build buttons: 3 types (fixed, free price, weight/measure)
	let boutonsHtml = ''
	for (let i = 0; i < tarifs.length; i++) {
		const tarif = tarifs[i]
		const prixAffiche = (tarif.prix_centimes / 100).toFixed(2)

		// Echapper tous les textes dynamiques pour éviter les injections XSS.
		// Les UUID et nombres ne sont pas échappés (pas de risque HTML).
		// / Escape all dynamic text to prevent XSS injection.
		// UUIDs and numbers are not escaped (no HTML risk).
		const nomTarifSafe = escapeHtml(tarif.name)
		const currencySafe = escapeHtml(currency)
		const prixAfficheSafe = escapeHtml(prixAffiche)
		const nomCompletSafe = escapeHtml(name + ' (' + tarif.name + ')')

		if (tarif.poids_mesure) {
			// Tarif poids/mesure : pavé numérique
			// / Weight/measure rate: numpad
			const uniteSaisie = tarif.unite_saisie_label || 'g'
			const prixReference = tarif.prix_reference_label || '/kg'
			const diviseur = (uniteSaisie === 'cl') ? 100 : 1000

			boutonsHtml += `
				<div class="tarif-btn tarif-btn-poids" data-testid="tarif-btn-poids-${tarif.price_uuid}">
					<div class="tarif-btn-label">
						<i class="fas fa-balance-scale" aria-hidden="true"></i> ${nomTarifSafe}
					</div>
					<div class="tarif-btn-sublabel">${prixAfficheSafe} ${currencySafe}${escapeHtml(prixReference)}</div>
					<div class="tarif-numpad-zone" id="tarif-numpad-${tarif.price_uuid}">
						<div class="tarif-numpad-display">
							<span class="tarif-numpad-value" id="tarif-numpad-value-${tarif.price_uuid}">0</span>
							<span class="tarif-numpad-unit">${escapeHtml(uniteSaisie)}</span>
						</div>
						<div class="tarif-numpad-total" id="tarif-numpad-total-${tarif.price_uuid}">
							= 0,00 ${currencySafe}
						</div>
						<div class="tarif-numpad-grid">
							<button type="button" class="tarif-numpad-btn" data-digit="7">7</button>
							<button type="button" class="tarif-numpad-btn" data-digit="8">8</button>
							<button type="button" class="tarif-numpad-btn" data-digit="9">9</button>
							<button type="button" class="tarif-numpad-btn" data-digit="4">4</button>
							<button type="button" class="tarif-numpad-btn" data-digit="5">5</button>
							<button type="button" class="tarif-numpad-btn" data-digit="6">6</button>
							<button type="button" class="tarif-numpad-btn" data-digit="1">1</button>
							<button type="button" class="tarif-numpad-btn" data-digit="2">2</button>
							<button type="button" class="tarif-numpad-btn" data-digit="3">3</button>
							<button type="button" class="tarif-numpad-btn tarif-numpad-btn-clear" data-digit="C">C</button>
							<button type="button" class="tarif-numpad-btn" data-digit="0">0</button>
							<button type="button" class="tarif-numpad-btn tarif-numpad-btn-ok"
								data-product-uuid="${uuid}"
								data-price-uuid="${tarif.price_uuid}"
								data-prix-centimes="${tarif.prix_centimes}"
								data-display-name="${nomCompletSafe}"
								data-currency="${currencySafe}"
								data-unite-saisie="${escapeHtml(uniteSaisie)}"
								data-diviseur="${diviseur}"
								data-testid="tarif-numpad-ok-${tarif.price_uuid}"
							>OK</button>
						</div>
					</div>
				</div>
			`
		} else if (tarif.free_price) {
			// Tarif prix libre (pas de fermeture apres ajout)
			// / Free price rate (no close after add)
			boutonsHtml += `
				<div class="tarif-btn tarif-btn-free" data-testid="tarif-btn-free-${tarif.price_uuid}">
					<div class="tarif-btn-label">${nomTarifSafe}</div>
					<div class="tarif-btn-sublabel">min ${prixAfficheSafe} ${currencySafe}</div>
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
						<span class="tarif-free-currency" aria-hidden="true">${currencySafe}</span>
						<button type="button"
							class="tarif-free-validate"
							data-product-uuid="${uuid}"
							data-price-uuid="${tarif.price_uuid}"
							data-prix-centimes="${tarif.prix_centimes}"
							data-display-name="${nomCompletSafe}"
							data-currency="${currencySafe}"
							data-testid="tarif-free-validate-${tarif.price_uuid}"
						>OK</button>
					</div>
					<div id="tarif-free-error-${tarif.price_uuid}" class="tarif-free-error" role="alert"></div>
				</div>
			`
		} else {
			// Tarif fixe : clic = ajout au panier (pas de fermeture)
			// / Fixed rate: click = add to cart (no close)
			boutonsHtml += `
				<button type="button"
					class="tarif-btn tarif-btn-fixed"
					data-product-uuid="${uuid}"
					data-price-uuid="${tarif.price_uuid}"
					data-prix-centimes="${tarif.prix_centimes}"
					data-display-name="${nomCompletSafe}"
					data-currency="${currencySafe}"
					data-testid="tarif-btn-${tarif.price_uuid}"
				>
					<div class="tarif-btn-label">${nomTarifSafe}</div>
					<div class="tarif-btn-price">${prixAfficheSafe} ${currencySafe}</div>
				</button>
			`
		}
	}

	// CHANGEMENT CLE : injecter dans #products (pas #messages)
	// L'overlay se superpose a la grille articles, le panier reste visible.
	// / KEY CHANGE: inject into #products (not #messages)
	// Overlay covers article grid, cart stays visible.
	const articlesZone = document.querySelector('#products')

	// Sauvegarder le contenu actuel pour pouvoir le restaurer a la fermeture
	// / Save current content to restore on close
	if (!window._tarifOverlayOriginalContent) {
		window._tarifOverlayOriginalContent = articlesZone.innerHTML
	}

	articlesZone.innerHTML = `
		<div id="tarif-overlay" class="tarif-overlay" data-testid="tarif-overlay">
			<div class="tarif-overlay-content">
				<h2 class="tarif-overlay-title">${escapeHtml(name)}</h2>
				<div class="tarif-overlay-subtitle">Choisir un tarif</div>
				<div class="tarif-list">
					${boutonsHtml}
				</div>
				<button type="button"
					class="tarif-btn-retour"
					data-testid="tarif-btn-retour"
				>
					<i class="fas fa-arrow-left" aria-hidden="true"></i> RETOUR
				</button>
			</div>
		</div>
	`

	// --- Attacher les handlers ---

	// Bouton RETOUR
	// / BACK button
	articlesZone.querySelector('.tarif-btn-retour').addEventListener('click', tarifClose)

	// Tarifs fixes : clic = ajout au panier, PAS de fermeture
	// / Fixed rates: click = add to cart, NO close
	articlesZone.querySelectorAll('.tarif-btn-fixed').forEach(btn => {
		btn.addEventListener('click', () => {
			addArticleWithPrice(
				btn.dataset.productUuid,
				btn.dataset.priceUuid,
				Number(btn.dataset.prixCentimes),
				btn.dataset.displayName,
				btn.dataset.currency
			)
		})
	})

	// Tarifs prix libre
	// / Free price rates
	articlesZone.querySelectorAll('.tarif-free-validate').forEach(btn => {
		btn.addEventListener('click', () => {
			tarifValidateFreePrix(
				btn.dataset.productUuid,
				btn.dataset.priceUuid,
				Number(btn.dataset.prixCentimes),
				btn.dataset.displayName,
				btn.dataset.currency
			)
		})
	})

	// --- Pavé numérique : handlers sur les boutons ---
	// / Numpad: handlers on buttons
	articlesZone.querySelectorAll('.tarif-numpad-grid').forEach(grid => {
		grid.querySelectorAll('.tarif-numpad-btn').forEach(btn => {
			btn.addEventListener('click', () => {
				const digit = btn.dataset.digit
				// Trouver la zone parent pour lire les data
				// / Find parent zone to read data
				const zone = btn.closest('.tarif-numpad-zone')
				const valueEl = zone.querySelector('.tarif-numpad-value')
				const totalEl = zone.querySelector('.tarif-numpad-total')

				if (digit === 'C') {
					// Effacer la saisie / Clear input
					valueEl.textContent = '0'
					totalEl.textContent = '= 0,00 ' + btn.closest('.tarif-btn-poids').querySelector('.tarif-btn-sublabel').textContent.split(' ').pop()
					return
				}

				// OK : valider et ajouter au panier
				// / OK: validate and add to cart
				if (btn.classList.contains('tarif-numpad-btn-ok')) {
					const quantiteSaisie = parseInt(valueEl.textContent, 10) || 0
					if (quantiteSaisie <= 0) {
						return
					}
					const prixUnitaireCentimes = Number(btn.dataset.prixCentimes)
					const diviseur = Number(btn.dataset.diviseur)
					const prixCalculeCentimes = Math.round(quantiteSaisie / diviseur * prixUnitaireCentimes)
					const uniteSaisie = btn.dataset.uniteSaisie
					const displayName = btn.dataset.displayName

					// Nom avec quantite : "Comte 350g"
					// / Name with quantity: "Comte 350g"
					const nomAvecQuantite = displayName.replace(/\)$/, '') + ' ' + quantiteSaisie + uniteSaisie + ')'
					// Si le nom ne contient pas de parenthese, simplifier
					// / If name has no parenthesis, simplify
					const nomFinal = displayName.includes('(') ? nomAvecQuantite : displayName + ' ' + quantiteSaisie + uniteSaisie

					addArticleWithPrice(
						btn.dataset.productUuid,
						btn.dataset.priceUuid,
						prixCalculeCentimes,
						nomFinal,
						btn.dataset.currency,
						prixCalculeCentimes,  // customAmount
						quantiteSaisie,       // weightAmount
						uniteSaisie           // weightUnit
					)

					// Reinitialiser le pave pour la prochaine saisie
					// / Reset numpad for next entry
					valueEl.textContent = '0'
					totalEl.textContent = '= 0,00 ' + btn.dataset.currency
					return
				}

				// Chiffre : ajouter au nombre
				// / Digit: append to number
				let currentValue = valueEl.textContent
				if (currentValue === '0') {
					currentValue = digit
				} else {
					currentValue += digit
				}
				// Limiter a 5 chiffres (99999g = 99.999kg max)
				// / Limit to 5 digits (99999g = 99.999kg max)
				if (currentValue.length > 5) {
					return
				}
				valueEl.textContent = currentValue

				// Calculer le prix en temps reel
				// / Calculate price in real time
				const okBtn = zone.querySelector('.tarif-numpad-btn-ok')
				const prixUnit = Number(okBtn.dataset.prixCentimes)
				const div = Number(okBtn.dataset.diviseur)
				const currencyLabel = okBtn.dataset.currency
				const quantite = parseInt(currentValue, 10) || 0
				const prixCalc = (quantite / div * prixUnit / 100).toFixed(2).replace('.', ',')
				totalEl.textContent = '= ' + prixCalc + ' ' + currencyLabel
			})
		})
	})
}

/**
 * Valide le montant du prix libre et ajoute au panier
 * / Validates free price amount and adds to cart
 *
 * Vérifie que le montant saisi est >= au minimum (prix_centimes).
 * Si valide, ajoute au panier et reinitialise l'input (pas de fermeture).
 * / Checks amount >= minimum. If valid, adds to cart and resets input (no close).
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
	addArticleWithPrice(productUuid, priceUuid, montantCentimes, displayName, currency, montantCentimes)

	// Reinitialiser l'input pour la prochaine saisie (pas de fermeture)
	// / Reset input for next entry (no close)
	inputEl.value = ''
	errorEl.textContent = ''
	inputEl.classList.remove('tarif-input-error')
}

/**
 * Compteur global pour generer des suffixes uniques sur les lignes a montant variable.
 * Les tarifs fixes partagent la meme ligne (qty++). Les prix libres et poids/mesure
 * creent une nouvelle ligne a chaque saisie (montant different a chaque fois).
 * / Global counter for unique suffixes on variable-amount lines.
 * Fixed prices share a line (qty++). Free and weight-based create a new line per entry.
 */
let _tarifVariableCounter = 0

/**
 * Ajoute un article au panier avec un price_uuid spécifique
 * / Adds an article to cart with a specific price_uuid
 *
 * Pour les tarifs a montant variable (prix libre, poids/mesure), chaque saisie cree
 * une ligne panier separee avec un suffixe unique (--1, --2, ...).
 * Pour les tarifs fixes, le clic incremente la quantite sur la ligne existante.
 * / For variable-amount prices (free, weight), each entry creates a separate cart line
 * with a unique suffix (--1, --2, ...). For fixed prices, click increments quantity.
 *
 * @param {String} productUuid - UUID du produit
 * @param {String} priceUuid - UUID du prix sélectionné
 * @param {Number} prixCentimes - Prix en centimes
 * @param {String} displayName - Nom affiché dans le panier
 * @param {String} currency - Symbole monétaire
 * @param {Number|null} customAmount - Montant custom en centimes (prix libre/poids) ou null
 * @param {Number|null} weightAmount - Quantité saisie (grammes, cl...) ou null
 * @param {String|null} weightUnit - Unité de saisie ('g', 'cl'...) ou null
 */
function addArticleWithPrice(productUuid, priceUuid, prixCentimes, displayName, currency, customAmount, weightAmount, weightUnit) {
	// Montant variable (prix libre ou poids/mesure) : chaque saisie = nouvelle ligne.
	// Montant fixe : meme ligne, on incremente la quantite.
	// / Variable amount (free or weight): each entry = new line.
	// Fixed amount: same line, increment quantity.
	const estMontantVariable = !!(customAmount || weightAmount)

	let lineId
	let quantity

	if (estMontantVariable) {
		// Nouvelle ligne avec suffixe unique. Le backend ignore le 3e segment '--'.
		// / New line with unique suffix. Backend ignores the 3rd '--' segment.
		_tarifVariableCounter++
		lineId = `${productUuid}--${priceUuid}--${_tarifVariableCounter}`
		quantity = 1
	} else {
		// Tarif fixe : meme ligne, on incremente
		// / Fixed price: same line, increment
		lineId = `${productUuid}--${priceUuid}`
		const existingInput = document.querySelector(`#addition-form [name="repid-${lineId}"]`)
		quantity = existingInput ? Number(existingInput.value) + 1 : 1
	}

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

	// Émet l'événement pour ajouter au panier (avec lineId unique)
	// / Emits event to add to cart (with unique lineId)
	sendEvent('organizerMsg', '#event-organizer', {
		src: { file: 'tarif.js', method: 'addArticleWithPrice' },
		msg: 'articlesAdd',
		data: {
			uuid: productUuid,
			priceUuid: priceUuid,
			lineId: lineId,
			price: prixCentimes,
			quantity: quantity,
			name: displayName,
			currency: currency,
			customAmount: customAmount || null,
			weightAmount: weightAmount || null,
			weightUnit: weightUnit || null,
		}
	})
}

/**
 * Ferme l'overlay de sélection de tarif et restaure la grille articles
 * / Closes rate selection overlay and restores article grid
 */
function tarifClose() {
	const articlesZone = document.querySelector('#products')
	if (window._tarifOverlayOriginalContent) {
		articlesZone.innerHTML = window._tarifOverlayOriginalContent
		window._tarifOverlayOriginalContent = null
	}
}

/**
 * INITIALISATION - Attache le handler tarifSelection sur #products
 * / Initialization - Attaches tarifSelection handler on #products
 */
document.addEventListener('DOMContentLoaded', () => {
	// Ecouter tarifSelection sur #products
	// L'ancien listener etait sur #messages — desormais sur #products
	// / Listen for tarifSelection on #products (was #messages)
	const articlesZone = document.querySelector('#products')
	if (articlesZone) {
		articlesZone.addEventListener('tarifSelection', tarifSelection)
	}
})
