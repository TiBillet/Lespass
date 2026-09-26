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
 * 5. Tuile prix libre → pavé numérique (clone de cotton/numpad.html, modele
 *    <template id="tarif-modele-pave-montant">) → « Ajouter · x € »
 *    → ajoute au panier (overlay reste ouvert, le pave se replie)
 * 6. Tarif poids/mesure → pavé numérique (clone de cotton/numpad.html,
 *    modele <template id="tarif-modele-pave"> dans cotton/articles.html)
 *    → bouton « Ajouter » → ajoute au panier
 * 7. Croix, toucher la grille voilee ou Echap → retire la popup (tarifClose)
 *
 * STYLE : laboutik/static/css/tarif.css (popup de la maquette).
 */

// escapeHtml() est défini dans tibilletUtils.js (chargé dans le <head>).
// / escapeHtml() is defined in tibilletUtils.js (loaded in <head>).

// Etat de la popup ouverte, rendu a la fermeture par tarifClose().
// / Open popup state, given back on close by tarifClose().
let tarifPositionDeDefilement = 0
let tarifElementARefocaliser = null

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
		// Prix affiche avec une virgule (« 4,00 ») / Price shown with a comma
		const prixAffiche = (tarif.prix_centimes / 100).toFixed(2).replace('.', ',')

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

			// Donnees stock pour la garde JS (bug 8) : permet de bloquer le submit
			// cote front quand vente hors stock interdite et quantite > stock dispo.
			// / Stock data for the JS guard (bug 8): blocks submit client-side when
			// out-of-stock sale is forbidden and quantity > available stock.
			const stockDisponible = (tarif.stock_disponible !== undefined && tarif.stock_disponible !== null)
				? tarif.stock_disponible
				: ''
			const autoriserHorsStock = tarif.autoriser_hors_stock === false ? 'false' : 'true'

			boutonsHtml += `
				<div class="tarif-btn tarif-btn-poids" data-testid="tarif-btn-poids-${tarif.price_uuid}">
					<div class="tarif-btn-label">
						<span>${nomTarifSafe}</span>
						<span class="tarif-btn-sublabel">${prixAfficheSafe} ${currencySafe}${escapeHtml(prixReference)}</span>
					</div>
					<div class="tarif-numpad-zone" id="tarif-numpad-${tarif.price_uuid}">
						<div class="tarif-numpad-display">
							<span class="tarif-numpad-value" id="tarif-numpad-value-${tarif.price_uuid}">0</span>
							<span class="tarif-numpad-unit">${escapeHtml(uniteSaisie)}</span>
						</div>
						<div class="tarif-numpad-total" id="tarif-numpad-total-${tarif.price_uuid}">
							= 0,00 ${currencySafe}
						</div>
						<!-- Le pave (cotton/numpad.html) est clone ici apres l'injection -->
						<!-- / The keypad (cotton/numpad.html) is cloned here after injection -->
						<div class="tarif-numpad-pave"></div>
						<button type="button" class="tarif-numpad-btn-ok"
							data-product-uuid="${uuid}"
							data-price-uuid="${tarif.price_uuid}"
							data-prix-centimes="${tarif.prix_centimes}"
							data-display-name="${nomCompletSafe}"
							data-currency="${currencySafe}"
							data-unite-saisie="${escapeHtml(uniteSaisie)}"
							data-diviseur="${diviseur}"
							data-stock-disponible="${stockDisponible}"
							data-autoriser-hors-stock="${autoriserHorsStock}"
							data-testid="tarif-numpad-ok-${tarif.price_uuid}"
							disabled
						>Ajouter</button>
						<div class="tarif-numpad-alerte-stock" id="tarif-numpad-alerte-${tarif.price_uuid}"
							role="alert" aria-live="polite" style="display: none;"></div>
					</div>
				</div>
			`
		} else if (tarif.free_price) {
			// Tarif prix libre : une tuile. Au toucher, elle laisse place au pave
			// numerique (meme bloc que le montant libre de la recharge cashless :
			// .card-clavier, hx_card_recharge.html). Le pave est clone apres l'injection.
			// / Free price rate: a tile. Tapping it shows the keypad (same block as
			// the cashless top-up free amount). The keypad is cloned after injection.
			boutonsHtml += `
				<div class="tarif-libre" data-testid="tarif-btn-free-${tarif.price_uuid}">
					<button type="button"
						class="tarif-btn tarif-btn-free tarif-libre-ouvrir"
						aria-expanded="false"
						aria-controls="tarif-libre-${tarif.price_uuid}"
						data-testid="tarif-libre-ouvrir-${tarif.price_uuid}"
					>
						<span class="tarif-btn-label">
							<span>${nomTarifSafe}</span>
							<span class="tarif-btn-sublabel">Prix libre · min ${prixAfficheSafe} ${currencySafe}</span>
						</span>
					</button>
					<div class="card-clavier tarif-libre-clavier" id="tarif-libre-${tarif.price_uuid}" hidden>
						<div class="card-clavier-head">
							<span id="tarif-libre-titre-${tarif.price_uuid}">${nomTarifSafe} · min ${prixAfficheSafe} ${currencySafe}</span>
							<button type="button" class="card-clavier-close tarif-libre-fermer" aria-label="Fermer le pavé">
								<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5.6 4.2 12 10.6l6.4-6.4L20.2 6 13.8 12.4l6.4 6.4-1.8 1.8-6.4-6.4-6.4 6.4-1.8-1.8 6.4-6.4-6.4-6.4z"/></svg>
							</button>
						</div>
						<output class="card-keypad-val" aria-live="polite" aria-labelledby="tarif-libre-titre-${tarif.price_uuid}">
							<span class="card-keypad-saisie">0</span> ${currencySafe}
						</output>
						<small id="tarif-free-error-${tarif.price_uuid}" class="card-montant-erreur" role="alert"></small>
						<div class="tarif-numpad-pave"></div>
						<button type="button"
							class="card-valider tarif-free-validate"
							data-product-uuid="${uuid}"
							data-price-uuid="${tarif.price_uuid}"
							data-prix-centimes="${tarif.prix_centimes}"
							data-display-name="${nomCompletSafe}"
							data-currency="${currencySafe}"
							data-testid="tarif-free-validate-${tarif.price_uuid}"
							disabled
						>Ajouter<span class="card-valider-montant"></span></button>
					</div>
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
					<span class="tarif-btn-label">${nomTarifSafe}</span>
					<span class="tarif-btn-price">${prixAfficheSafe} ${currencySafe}</span>
				</button>
			`
		}
	}

	// La popup se pose PAR-DESSUS la grille articles (#products), pas dans #messages :
	// - #messages couvre tout l'ecran, panier compris. Ici le panier reste visible :
	//   le caissier voit chaque tarif fixe s'ajouter (la popup ne se ferme pas).
	// - #messages recoit les reponses HTMX (paiement, alertes) : un swap y
	//   detruirait la popup.
	// On AJOUTE la popup a la fin de #products, sans toucher aux tuiles :
	// elles restent a jour (badge de quantite, stock pousse par WebSocket).
	// / The popup sits OVER the article grid, not in #messages (which covers the
	// cart and receives HTMX responses). It is APPENDED: tiles stay live.
	const articlesZone = document.querySelector('#products')

	// Une seule popup a la fois / One popup at a time
	const popupDejaOuverte = articlesZone.querySelector('#tarif-overlay')
	if (popupDejaOuverte) {
		popupDejaOuverte.remove()
	}

	// Retenir l'element a refocaliser a la fermeture (la tuile touchee)
	// / Remember the element to refocus on close (the tapped tile)
	tarifElementARefocaliser = document.activeElement

	// #products defile (overflow-y: auto). Une popup en position absolute y
	// serait posee en haut du CONTENU, pas de la zone visible. On remonte donc
	// en haut, on bloque le defilement pendant la popup, et on rendra la
	// position a la fermeture.
	// / #products scrolls: go to the top, lock scrolling, restore on close.
	tarifPositionDeDefilement = articlesZone.scrollTop
	articlesZone.scrollTop = 0
	articlesZone.classList.add('tarif-popup-ouverte')

	// Les tuiles sous le voile ne sont plus cliquables ni joignables au
	// clavier (inert) : aria-modal dit vrai.
	// / Tiles under the veil become inert, so aria-modal is truthful.
	for (const tuileSousLeVoile of articlesZone.children) {
		tuileSousLeVoile.inert = true
	}

	articlesZone.insertAdjacentHTML('beforeend', `
		<div id="tarif-overlay" class="tarif-overlay" data-testid="tarif-overlay">
			<div class="tarif-overlay-content"
				role="dialog"
				aria-modal="true"
				aria-labelledby="tarif-overlay-titre">
				<button type="button"
					class="card-modal-close tarif-btn-retour"
					aria-label="Fermer"
					data-testid="tarif-btn-retour"
				>
					<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5.6 4.2 12 10.6l6.4-6.4L20.2 6 13.8 12.4l6.4 6.4-1.8 1.8-6.4-6.4-6.4 6.4-1.8-1.8 6.4-6.4-6.4-6.4z"/></svg>
				</button>
				<h2 class="tarif-overlay-title" id="tarif-overlay-titre">${escapeHtml(name)}</h2>
				<div class="tarif-overlay-subtitle">Choisir un tarif</div>
				<div class="tarif-list">
					${boutonsHtml}
				</div>
			</div>
		</div>
	`)

	// --- Attacher les handlers ---

	// Croix : ferme la popup et restaure la grille
	// / Cross: closes the popup and restores the grid
	articlesZone.querySelector('.tarif-btn-retour').addEventListener('click', tarifClose)

	// Toucher la grille voilee ferme aussi (seulement le voile, pas la boite)
	// / Tapping the veiled grid closes too (only the veil, not the box)
	articlesZone.querySelector('.tarif-overlay').addEventListener('click', (event) => {
		if (event.target.classList.contains('tarif-overlay')) {
			tarifClose()
		}
	})

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

	// Tarifs prix libre : tuile → pave numerique → « Ajouter · x € »
	// / Free price rates: tile → keypad → "Add · x €"
	articlesZone.querySelectorAll('.tarif-libre').forEach(blocLibre => {
		const tuile = blocLibre.querySelector('.tarif-libre-ouvrir')
		const clavier = blocLibre.querySelector('.tarif-libre-clavier')
		tarifInsererPave(clavier, '#tarif-modele-pave-montant')

		tuile.addEventListener('click', () => tarifOuvrirPrixLibre(blocLibre))
		blocLibre.querySelector('.tarif-libre-fermer').addEventListener('click', () => tarifFermerPrixLibre(blocLibre))
		clavier.addEventListener('keypadSendValue', (event) => {
			tarifSaisiePrixLibre(clavier, event.detail.key)
		})
		const boutonAjouter = clavier.querySelector('.tarif-free-validate')
		boutonAjouter.addEventListener('click', () => {
			tarifAjouterPrixLibre(blocLibre, boutonAjouter)
		})
	})

	// --- Pavé numérique des tarifs au poids ---
	// Chaque zone recoit un clone du pave serveur (cotton/numpad.html).
	// Le pave envoie 'keypadSendValue' a la zone ; la zone met a jour la saisie.
	// Le bouton « Ajouter » valide et ajoute au panier.
	// / Each zone gets a clone of the server keypad. The keypad sends
	// 'keypadSendValue' to the zone; the « Ajouter » button adds to cart.
	articlesZone.querySelectorAll('.tarif-numpad-zone').forEach(zone => {
		tarifInsererPave(zone, '#tarif-modele-pave')
		zone.addEventListener('keypadSendValue', (event) => {
			tarifSaisiePoids(zone, event.detail.key)
		})
		const boutonAjouter = zone.querySelector('.tarif-numpad-btn-ok')
		boutonAjouter.addEventListener('click', () => {
			tarifAjouterPoids(zone, boutonAjouter)
		})
	})

	// Echap ferme la popup (comme la croix) / Escape closes the popup
	articlesZone.querySelector('#tarif-overlay').addEventListener('keydown', (event) => {
		if (event.key === 'Escape') {
			tarifClose()
		}
	})

	// Pas sur de l'utilité de ça, a voir
	// Focus sur le premier tarif : le clavier et le lecteur d'ecran entrent
	// directement dans la popup. / Focus the first rate.
	// const premierTarif = articlesZone.querySelector('#tarif-overlay .tarif-list button')
	// if (premierTarif) {
	// 	premierTarif.focus()
	// }
}

/**
 * Clone le pave numerique serveur dans une zone de la popup de tarif
 * / Clones the server keypad into a zone of the rate popup
 *
 * LOCALISATION : laboutik/static/js/tarif.js
 *
 * Les modeles sont rendus une seule fois par le serveur, dans cotton/articles.html
 * (composant c-numpad) :
 * - #tarif-modele-pave         : poids / mesure, nombre entier, sans virgule ;
 * - #tarif-modele-pave-montant : prix libre, avec virgule.
 * On retire son <script> et son <link> (le CSS est deja dans base.html),
 * on lui donne un id unique, et on le fait viser la zone (data-cible).
 * L'ecouteur de clic fait la meme chose que le script du composant :
 * il envoie 'keypadSendValue' { key } a la cible.
 * / Removes the component's script and link, gives a unique id, targets the zone.
 *
 * @param {HTMLElement} zone - element avec un id, qui contient .tarif-numpad-pave
 *                             et qui recevra 'keypadSendValue'
 * @param {String} selecteurModele - '#tarif-modele-pave' ou '#tarif-modele-pave-montant'
 */
function tarifInsererPave(zone, selecteurModele) {
	const modele = document.querySelector(selecteurModele)
	const emplacement = zone.querySelector('.tarif-numpad-pave')
	if (!modele || !emplacement) {
		console.log('-> tarif.js - tarifInsererPave : modele de pave introuvable')
		return
	}

	const copie = modele.content.cloneNode(true)
	copie.querySelectorAll('script, link').forEach(element => element.remove())

	const pave = copie.querySelector('.numpad-content')
	pave.id = 'pave-' + zone.id
	pave.dataset.cible = '#' + zone.id
	pave.addEventListener('click', (event) => {
		const touchePressee = event.target.closest('.numpad-touch')
		if (!touchePressee) {
			return
		}
		sendEvent('keypadSendValue', pave.dataset.cible, { key: touchePressee.dataset.key })
	})

	emplacement.appendChild(copie)
}

/**
 * Met a jour la saisie d'un tarif au poids apres une touche du pave
 * / Updates a weight price entry after a keypad key
 *
 * LOCALISATION : laboutik/static/js/tarif.js
 * Recoit : 'keypadSendValue' { key } depuis le pave clone (tarifInsererPave)
 *
 * Touches : "0" a "9" ajoutent un chiffre (5 chiffres max, 99999 g),
 * "Backspace" efface le dernier, "C" efface tout.
 * La quantite est un nombre entier (grammes, centilitres).
 *
 * @param {HTMLElement} zone - .tarif-numpad-zone
 * @param {String} touche - valeur de la touche (event.detail.key)
 */
function tarifSaisiePoids(zone, touche) {
	const valueEl = zone.querySelector('.tarif-numpad-value')
	const boutonAjouter = zone.querySelector('.tarif-numpad-btn-ok')

	// Masquer l'alerte stock quand l'utilisateur change la saisie
	// / Hide stock alert when user changes the input
	const alerteStockEl = zone.querySelector('.tarif-numpad-alerte-stock')
	if (alerteStockEl) {
		alerteStockEl.style.display = 'none'
	}

	let saisie = valueEl.textContent
	if (touche === 'C') {
		saisie = '0'
	} else if (touche === 'Backspace') {
		saisie = saisie.length > 1 ? saisie.slice(0, -1) : '0'
	} else if (/^[0-9]$/.test(touche)) {
		saisie = (saisie === '0') ? touche : saisie + touche
		// Limiter a 5 chiffres (99999g = 99.999kg max)
		// / Limit to 5 digits (99999g = 99.999kg max)
		if (saisie.length > 5) {
			return
		}
	} else {
		// Autre touche (virgule absente de ce pave) : rien a faire
		// / Any other key: nothing to do
		return
	}
	valueEl.textContent = saisie
	tarifAfficherTotalPoids(zone, boutonAjouter)
}

/**
 * Affiche le prix calcule et met a jour le bouton « Ajouter »
 * / Shows the computed price and updates the « Ajouter » button
 *
 * @param {HTMLElement} zone - .tarif-numpad-zone
 * @param {HTMLElement} boutonAjouter - .tarif-numpad-btn-ok (porte les data-*)
 */
function tarifAfficherTotalPoids(zone, boutonAjouter) {
	const valueEl = zone.querySelector('.tarif-numpad-value')
	const totalEl = zone.querySelector('.tarif-numpad-total')
	const quantite = parseInt(valueEl.textContent, 10) || 0
	const prixUnitaireCentimes = Number(boutonAjouter.dataset.prixCentimes)
	const diviseur = Number(boutonAjouter.dataset.diviseur)
	const monnaie = boutonAjouter.dataset.currency
	const prixAffiche = (quantite / diviseur * prixUnitaireCentimes / 100).toFixed(2).replace('.', ',')

	totalEl.textContent = '= ' + prixAffiche + ' ' + monnaie
	boutonAjouter.textContent = quantite > 0 ? 'Ajouter · ' + prixAffiche + ' ' + monnaie : 'Ajouter'
	boutonAjouter.disabled = quantite <= 0
}

/**
 * Valide la saisie d'un tarif au poids et ajoute l'article au panier
 * / Validates a weight price entry and adds the article to the cart
 *
 * @param {HTMLElement} zone - .tarif-numpad-zone
 * @param {HTMLElement} btn - bouton « Ajouter » (.tarif-numpad-btn-ok, porte les data-*)
 */
function tarifAjouterPoids(zone, btn) {
	const valueEl = zone.querySelector('.tarif-numpad-value')
	const quantiteSaisie = parseInt(valueEl.textContent, 10) || 0
	if (quantiteSaisie <= 0) {
		return
	}

	// Garde stock cote front (bug 8).
	// Si vente hors stock interdite ET quantite saisie > stock disponible,
	// on bloque cote front pour eviter un round-trip serveur.
	// Le serveur reste autoritaire (validation amont via _valider_stock_panier).
	// / Front-side stock guard (bug 8). Server remains authoritative.
	const autoriserHorsStock = btn.dataset.autoriserHorsStock !== 'false'
	const stockDisponibleStr = btn.dataset.stockDisponible
	const stockDisponible = (stockDisponibleStr === '' || stockDisponibleStr === undefined)
		? null
		: Number(stockDisponibleStr)
	if (!autoriserHorsStock && stockDisponible !== null && quantiteSaisie > stockDisponible) {
		const priceUuid = btn.dataset.priceUuid
		const alerteEl = document.querySelector(`#tarif-numpad-alerte-${priceUuid}`)
		if (alerteEl) {
			const uniteSaisieAlerte = btn.dataset.uniteSaisie || ''
			alerteEl.innerHTML = `
				<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill-rule="evenodd" d="M12 2.6 22.8 21.2H1.2zM10.9 9h2.2v6.2h-2.2zm0 7.6h2.2v2.2h-2.2z"/></svg>
				Stock insuffisant : ${quantiteSaisie}${uniteSaisieAlerte} demandes,
				${stockDisponible}${uniteSaisieAlerte} disponibles.
			`
			alerteEl.style.display = 'block'
		}
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

	// Reinitialiser la saisie pour la prochaine pesee
	// / Reset the entry for the next weighing
	valueEl.textContent = '0'
	tarifAfficherTotalPoids(zone, btn)
}

/**
 * Deplie le pave numerique d'un tarif prix libre (la tuile se cache)
 * / Unfolds a free price keypad (the tile hides)
 *
 * @param {HTMLElement} blocLibre - .tarif-libre
 */
function tarifOuvrirPrixLibre(blocLibre) {
	const tuile = blocLibre.querySelector('.tarif-libre-ouvrir')
	const clavier = blocLibre.querySelector('.tarif-libre-clavier')
	tuile.hidden = true
	tuile.setAttribute('aria-expanded', 'true')
	clavier.hidden = false
	// Le focus va sur la premiere touche : on peut taper tout de suite
	// / Focus the first key so typing can start right away
	const premiereTouche = clavier.querySelector('.numpad-touch')
	if (premiereTouche) {
		premiereTouche.focus()
	}
}

/**
 * Replie le pave d'un tarif prix libre, efface la saisie, remontre la tuile
 * / Folds the free price keypad back, clears the entry, shows the tile
 *
 * @param {HTMLElement} blocLibre - .tarif-libre
 */
function tarifFermerPrixLibre(blocLibre) {
	const tuile = blocLibre.querySelector('.tarif-libre-ouvrir')
	const clavier = blocLibre.querySelector('.tarif-libre-clavier')
	clavier.dataset.saisie = ''
	tarifAfficherPrixLibre(clavier)
	clavier.hidden = true
	tuile.hidden = false
	tuile.setAttribute('aria-expanded', 'false')
	tuile.focus()
}

/**
 * Applique une touche du pave au prix libre en cours de saisie
 * / Applies a keypad key to the free price being typed
 *
 * LOCALISATION : laboutik/static/js/tarif.js
 * Recoit : 'keypadSendValue' { key } depuis le pave clone (tarifInsererPave)
 * Regle de saisie : montantAppliquerTouche() (tibilletUtils.js), la meme que
 * pour la recharge en montant libre, le fond de caisse et les especes.
 *
 * @param {HTMLElement} clavier - .tarif-libre-clavier (la saisie est dans data-saisie)
 * @param {String} touche - valeur de la touche
 */
function tarifSaisiePrixLibre(clavier, touche) {
	const saisie = clavier.dataset.saisie || ''
	const nouvelleSaisie = montantAppliquerTouche(saisie, touche)
	if (nouvelleSaisie === null) {
		return
	}
	clavier.dataset.saisie = nouvelleSaisie
	tarifAfficherPrixLibre(clavier)
}

/**
 * Affiche le prix libre en grand et met a jour « Ajouter · x € »
 * / Shows the free price large and updates "Add · x €"
 *
 * @param {HTMLElement} clavier - .tarif-libre-clavier
 */
function tarifAfficherPrixLibre(clavier) {
	const saisie = clavier.dataset.saisie || ''
	const boutonAjouter = clavier.querySelector('.tarif-free-validate')
	const montantEnEuros = parseFloat(saisie.replace(',', '.')) || 0

	clavier.querySelector('.card-keypad-saisie').textContent = saisie === '' ? '0' : saisie
	clavier.querySelector('.card-keypad-val').classList.remove('is-invalide')
	clavier.querySelector('.card-montant-erreur').textContent = ''

	boutonAjouter.disabled = montantEnEuros <= 0
	boutonAjouter.querySelector('.card-valider-montant').textContent =
		montantEnEuros > 0 ? ' · ' + saisie + ' ' + boutonAjouter.dataset.currency : ''
}

/**
 * Verifie le prix libre (minimum du tarif) et ajoute l'article au panier
 * / Checks the free price (rate minimum) and adds the article to the cart
 *
 * Si le montant est sous le minimum : message sous le montant, rien n'est ajoute.
 * Sinon : ajout au panier, puis le pave se replie (la popup reste ouverte).
 * Le serveur revalide le montant a la vente.
 * / Below minimum: message, nothing added. Otherwise: add, then fold the keypad.
 *
 * @param {HTMLElement} blocLibre - .tarif-libre
 * @param {HTMLElement} btn - bouton « Ajouter » (.tarif-free-validate, porte les data-*)
 */
function tarifAjouterPrixLibre(blocLibre, btn) {
	const clavier = blocLibre.querySelector('.tarif-libre-clavier')
	const saisie = clavier.dataset.saisie || ''
	const montantCentimes = Math.round((parseFloat(saisie.replace(',', '.')) || 0) * 100)
	const minimumCentimes = Number(btn.dataset.prixCentimes)

	if (montantCentimes <= 0) {
		return
	}
	if (montantCentimes < minimumCentimes) {
		const minimumAffiche = (minimumCentimes / 100).toFixed(2).replace('.', ',')
		clavier.querySelector('.card-montant-erreur').textContent =
			`Minimum : ${minimumAffiche} ${btn.dataset.currency}`
		clavier.querySelector('.card-keypad-val').classList.add('is-invalide')
		return
	}

	addArticleWithPrice(
		btn.dataset.productUuid,
		btn.dataset.priceUuid,
		montantCentimes,
		btn.dataset.displayName,
		btn.dataset.currency,
		montantCentimes  // customAmount
	)
	tarifFermerPrixLibre(blocLibre)
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

	// Incrémente la quantité sur la tuile article.
	// Pendant l'overlay tarif (vrac/multi-tarif), #products est remplacé : la tuile
	// n'existe pas dans le DOM. On guard null pour eviter un TypeError noye dans
	// le try/catch (faux negatif en debug).
	// / Increment quantity on article tile.
	// During the rate overlay, #products is replaced: the tile is not in the DOM.
	// Guard null to avoid a TypeError swallowed by try/catch.
	try {
		const eleQuantity = document.querySelector(`#article-quantity-number-${productUuid}`)
		if (eleQuantity) {
			let tileQty = Number(eleQuantity.innerText)
			tileQty++
			eleQuantity.innerText = tileQty
			// afficherBadgeQuantite() vit dans articles.js, charge sur la meme page
			// / afficherBadgeQuantite() lives in articles.js, loaded on the same page
			afficherBadgeQuantite(eleQuantity)
		}
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
 * Ferme l'overlay de sélection de tarif et rend la main à la grille articles
 * / Closes rate selection overlay and gives the article grid back
 *
 * LOCALISATION : laboutik/static/js/tarif.js
 *
 * Les tuiles n'ont jamais quitte le DOM : on retire seulement la popup,
 * on rend les tuiles actives (inert), on remet le defilement et le focus.
 * / Tiles never left the DOM: remove the popup, un-inert the tiles,
 * restore scrolling and focus.
 *
 * Appelee par : la croix, un toucher sur le voile, Echap,
 * l'ajout d'un prix libre / poids, et addition.js.
 */
function tarifClose() {
	const articlesZone = document.querySelector('#products')
	if (!articlesZone) {
		return
	}
	const popupOuverte = articlesZone.querySelector('#tarif-overlay')
	if (!popupOuverte) {
		return
	}
	popupOuverte.remove()

	for (const tuile of articlesZone.children) {
		tuile.inert = false
	}
	articlesZone.classList.remove('tarif-popup-ouverte')
	articlesZone.scrollTop = tarifPositionDeDefilement

	// Rendre le focus a la tuile touchee, si elle est encore la
	// / Give focus back to the tapped tile, if still there
	const elementEncoreDansLaPage = tarifElementARefocaliser && document.contains(tarifElementARefocaliser)
	if (elementEncoreDansLaPage) {
		tarifElementARefocaliser.focus()
	}
	tarifElementARefocaliser = null
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
