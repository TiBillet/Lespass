/**
 * ARTICLES.JS - GESTION DE LA GRILLE D'ARTICLES
 * / Article grid management
 *
 * LOCALISATION : laboutik/static/js/articles.js
 *
 * Gere l'affichage et la selection des articles :
 * - Detection des clics sur les articles
 * - Incrementation des quantites
 * - Filtrage par categorie
 *
 * COMMUNICATION :
 * Emet : 'articlesAdd' (vers #addition via tibilletUtils.js)
 * Recoit : 'articlesRemove', 'articlesReset', 'articlesDisplayCategory'
 *
 * NOTE : le verrouillage par groupe (data-group) a ete supprime.
 * Les paniers mixtes (VT + RE + AD) sont desormais autorises
 * grace au flow d'identification client unifie (session 05).
 * / NOTE: group-based locking (data-group) has been removed.
 * Mixed carts (VT + RE + AD) are now allowed
 * thanks to the unified client identification flow (session 05).
 */

/**
 * Incrémente la quantité et émet l'événement d'ajout
 * / Increments quantity and emits add event
 * 
 * Appelée par manageKey() après un clic sur un article.
 * Met à jour l'affichage de la quantité sur la tuile et émet 'articlesAdd'
 * qui sera routé vers addition.js:additionInsertArticle().
 * 
 * @param {String} uuid - UUID de l'article
 * @param {String} price - Prix en centimes
 * @param {String} name - Nom de l'article
 * @param {String} currency - Symbole monétaire
 */
function addArticle(uuid, price, name, currency) {
	try {
		let quantity = 0

		const eleQuantity = document.querySelector(`#article-quantity-number-${uuid}`)

		if (!eleQuantity && !eleQuantity.innerText) {
			throw new Error("Quantity not found")
		}

		quantity = Number(eleQuantity.innerText)

		quantity++
		eleQuantity.innerText = quantity

		// Rend le badge visible (transition CSS opacity 200ms)
		// / Makes badge visible (CSS opacity transition 200ms)
		eleQuantity.classList.add('badge-visible')

		// Envoie l'événement pour ajouter au panier
		sendEvent('organizerMsg', '#event-organizer', {
			src: { file: 'articles.js', method: 'addArticle' },
			msg: 'articlesAdd',
			data: { uuid, price, quantity, name, currency }
		})
	} catch (error) {
		console.log('-> article.js - addArticle,', error)
	}
}

function manageBtTarif(event) {
	if (event.target.classList.contains('article-touch')) {
		const touch = event.target
		console.log('-> manageBtTarif - touch =', touch)
		addArticleWithPrice(
			touch.dataset.productUuid,
			touch.dataset.priceUuid,
			Number(touch.dataset.prixCentimes),
			touch.dataset.displayName,
			touch.dataset.currency
		)
	}
}

/**
 * Affiche plusieurs tarifs
 * @param {object} dataArticle 
 */
function tarifSelection2(dataArticle) {
	const { uuid, name, tarifs, currency } = dataArticle
	console.log('-> tarifSelection - dataArticle =', dataArticle)
	let template = `
		<div class="tarifs-overlay">
			<div class="tarifs-container">`
	for (let i = 0; i < tarifs.length; i++) {
		const tarif = tarifs[i]
		const prixAffiche = (tarif.prix_centimes / 100).toFixed(2)

		// Echapper tous les textes dynamiques pour éviter les injections XSS.
		// Les UUID et nombres ne sont pas échappés (pas de risque HTML).
		// / Escape all dynamic text to prevent XSS injection.
		// UUIDs and numbers are not escaped (no HTML risk).
		console.log('-------------------------------------');
		const nomTarifSafe = escapeHtml(tarif.name)
		const currencySafe = escapeHtml(currency)
		const prixAfficheSafe = escapeHtml(prixAffiche)
		const nomCompletSafe = escapeHtml(name + ' (' + tarif.name + ')')
		console.log('nomTarifSafe =', nomTarifSafe, '  --  currencySafe =', currencySafe);
		console.log('prixAfficheSafe =', prixAfficheSafe, '  --  prixAfficheSafe =', prixAfficheSafe);

		let btClass = ''
		if (!tarif.free_price) {
			btClass = 'class="tarif-article bt-tarif" '
		} else {
			btClass = 'class="tarif-article-libre" '
		}

		template += `<div ${btClass}>`

		if (tarif.poids_mesure) {
			// TODO:
			console.log('poids')

		}
		if (tarif.free_price) {
			console.log('libre')
			template += `
				<div class="tal-title">${nomTarifSafe}</div>
				<div class="tal-value">
				<input type="number" placeHolder="0.00"/>
				</div>
				<div class="tal-price">0.00€</div>
				<div class="tal-validate">
				<div>
					<div>OK</div>
					<div class="article-touch" 
					data-product-uuid="${uuid}" 
					data-price-uuid="${tarif.price_uuid}" 
					data-prix-centimes="${tarif.prix_centimes}" 
					data-display-name="${nomCompletSafe}" 
					data-currency="${currencySafe}" 
					data-testid="tarif-btn-${tarif.price_uuid}"></div>
				</div>
				</div>`
		}

		if (!tarif.poids_mesure && !tarif.free_price) {
			console.log('fixe')
			template += `
					<div class="article-visual-layer">${nomTarifSafe}</div>
					<div class="article-footer-layer">${prixAfficheSafe} ${currencySafe}</div>
					<div class="article-touch" 
					data-product-uuid="${uuid}" 
					data-price-uuid="${tarif.price_uuid}" 
					data-prix-centimes="${tarif.prix_centimes}" 
					data-display-name="${nomCompletSafe}" 
					data-currency="${currencySafe}" 
					data-testid="tarif-btn-${tarif.price_uuid}"></div>`
		}
		template += `</div>`
	}

	template += `
			</div>
			<!-- Bt retour -->
			<div id="bt-retour-layer1" class="bt-basic-container bt-basic-bg-return" onclick="hideAndEmptyElement('#messages');">
				<div class="bt-basic-icon">
					<i class="fas fa-undo-alt"></i>
				</div>
				<div class="bt-basic-text">
					<div>RETOUR</div>
				</div>
			</div>
		</div>`
	const messages = document.querySelector('#messages')
	// ajout du template dans #messages
	messages.innerHTML = template
	// afffichage de #messages
	messages.classList.remove('hide')

	// gère les boutons tarif
	document.querySelector('#messages').addEventListener('click', manageBtTarif)

}

/**
 * Gere la selection d'un article (clic)
 * / Manages article selection (click)
 *
 * Ecouteur principal attache a #products (delegation d'evenements).
 * Declenche a chaque clic sur une tuile article.
 *
 * Actions :
 * 1. Recupere les donnees de l'article (uuid, price, name, currency)
 * 2. Si multi-tarif → ouvre la selection de tarif
 * 3. Sinon → appelle addArticle() pour incrementer et emettre l'evenement
 *
 * @param {Object} event - Evenement clic
 */
function manageKey(event) {
	const ele = event.target.parentNode

	if (ele.classList.contains('article-container')) {
		const methodeCaisse = ele?.dataset?.methodeCaisse
		// RE = recharge monnaie / RC = recharge cadeau / TM = recharge temps / VT = vente (service direct)
		// console.log('-> manageKey - methodeCaisse =', methodeCaisse)

		// articles "ordinaires"
		if (methodeCaisse === 'VT' || methodeCaisse === 'RE' || methodeCaisse === 'TM') {
			// Si le stock est bloquant (rupture + vente hors stock interdite),
			// on ignore le clic — l'article est grisé visuellement.
			// / If stock is blocking (out of stock + sales not allowed),
			// ignore the click — the article is visually greyed out.
			if (ele.dataset.stockBloquant === 'true') {
				return
			}

			const articleUuid = ele.dataset.uuid
			const articlePrice = ele.dataset.price
			const articleName = ele.dataset.name
			const articleCurrency = ele.dataset.currency
			// transforme le mot 'true' en bouléen
			const multiTarif = ele.dataset.multiTarif === 'true'

			// Si l'article a plusieurs tarifs ou un prix libre → ouvrir la selection de tarif
			// au lieu d'ajouter directement au panier.
			// / If the article has multiple rates or free price → open rate selection
			// instead of adding directly to cart.
			if (multiTarif) {
				tarifSelection2({
					uuid: articleUuid,
					name: articleName,
					tarifs: JSON.parse(ele.dataset.tarifs),
					currency: articleCurrency,
				})
			} else {
				addArticle(articleUuid, articlePrice, articleName, articleCurrency)
			}
		}

		// remboursement carte
		if (methodeCaisse === 'VC') {
			// Recupere uuid_pv et tag_id_cm depuis #addition-form.
			// Retrieves uuid_pv and tag_id_cm from #addition-form.
			const form = document.querySelector('#addition-form')
			const uuidPv = form.querySelector('input[name="uuid_pv"]').value
			const tagIdCm = form.querySelector('input[name="tag_id_cm"]').value
			const params = new URLSearchParams({ uuid_pv: uuidPv, tag_id_cm: tagIdCm })
			console.clear()
			console.log('uuidPv =', uuidPv)
			console.log('tagIdCm =', tagIdCm)
			console.log('params =', params.toString())
			htmx.ajax('GET', '/laboutik/paiement/vider_carte/overlay/?' + params.toString(), {
				target: '#messages',
				swap: 'innerHTML'
			})
		}

		// rechargement cadeau
		if (methodeCaisse === 'RC') {
			console.log('rechargement cadeau !');
			
		}
	}
}

/**
 * Met à jour la quantité sur la tuile (Handler)
 * / Updates quantity display on tile
 * 
 * Reçoit 'articlesRemove' depuis addition.js quand on retire un article du panier.
 * Synchronise l'affichage de la quantité sur la tuile avec le panier.
 * 
 * Flux : addition.js:additionRemoveArticle() → 'additionRemoveArticle' → 
 *        tibilletUtils.js → 'articlesRemove' → CETTE FONCTION
 * 
 * @param {Object} event - Événement avec event.detail.uuid et event.detail.quantity
 */
function articlesRemove(event) {
	const { uuid, quantity } = event.detail

	try {
		const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
		const eleQuantity = article.querySelector(`#article-quantity-number-${uuid}`)
		eleQuantity.innerText = quantity

		// Cache le badge quand la quantite revient a zero
		// / Hides badge when quantity returns to zero
		if (quantity <= 0) {
			eleQuantity.classList.remove('badge-visible')
		}
	} catch (error) {
		console.log('-> article.js - articlesRemove,', error)
	}
}

/**
 * Reinitialise l'affichage de tous les articles (Handler)
 * / Resets all articles display
 *
 * Recoit 'articlesReset' depuis common_user_interface.html (bouton RESET).
 * Reinitialise completement l'affichage des articles :
 * - Remet toutes les quantites a 0
 * - Cache les badges de quantite
 *
 * Flux : clic RESET → 'resetArticles' → tibilletUtils.js → 'articlesReset' → CETTE FONCTION
 */
function articlesReset() {
	try {
		document.querySelectorAll('#products .article-container').forEach(article => {
			const uuid = article.dataset.uuid
			const eleQuantity = document.querySelector(`#article-quantity-number-${uuid}`)
			eleQuantity.innerText = 0

			// Cache le badge (quantite remise a zero)
			// / Hides badge (quantity reset to zero)
			eleQuantity.classList.remove('badge-visible')
		})

	} catch (error) {
		console.log('-> article.js - articlesReset,', error)
	}
}

/**
 * Filtre l'affichage des articles par catégorie
 * / Filters article display by category
 *
 * LOCALISATION : laboutik/static/js/articles.js
 *
 * Reçoit l'événement 'articlesDisplayCategory' depuis categories.html.
 * Montre ou cache les articles selon leur classe CSS 'cat-<uuid>'.
 *
 * FLUX :
 * 1. Clic catégorie dans categories.html:manageCategories()
 * 2. Routage via tibilletUtils.js:eventsOrganizer()
 * 3. CETTE FONCTION filtre les articles visibles
 *
 * Si 'cat-all' : tous les articles sont visibles.
 * Sinon : seuls les articles qui ont la classe 'cat-<uuid>' sont visibles.
 *
 * @param {Object} event - Événement avec event.detail.category ('cat-all' ou 'cat-<uuid>')
 */
function articlesDisplayCategory(event) {
	const category = event.detail.category
	try {
		// Sélectionne tous les articles de la grille
		// / Selects all articles in the grid
		const tousLesArticles = document.querySelectorAll('#products .article-container')

		if (category === 'cat-all') {
			// Afficher tous les articles
			// / Show all articles
			for (const article of tousLesArticles) {
				article.style.display = ''
			}
		} else {
			// Afficher uniquement les articles de cette catégorie
			// / Show only articles of this category
			for (const article of tousLesArticles) {
				if (article.classList.contains(category)) {
					article.style.display = ''
				} else {
					article.style.display = 'none'
				}
			}
		}
	} catch (error) {
		console.log('-> article.js - articlesDisplayCategory,', error)
	}
}

/**
 * INITIALISATION - Attache les écouteurs sur #products
 * / Initialization - Attaches listeners on #products
 * 
 * Attache 4 écouteurs via délégation sur #products :
 * - 'click' → manageKey() : Détecte les clics sur les articles
 * - 'articlesRemove' → articlesRemove() : Maj quantité depuis panier
 * - 'articlesReset' → articlesReset() : Réinitialise tout (bouton RESET)
 * - 'articlesDisplayCategory' → articlesDisplayCategory() : Filtre par catégorie
 */
/**
 * Synchronise l'état bloquant de tous les badges stock vers les containers articles.
 * / Syncs blocking state from all stock badges to their article containers.
 *
 * LOCALISATION : laboutik/static/js/articles.js
 *
 * Appelée après chaque message WebSocket (htmx:wsAfterMessage).
 * Parcourt tous les badges stock et propage data-stock-bloquant
 * vers le container parent (.article-container).
 *
 * Les <script> dans du HTML WebSocket ne sont PAS exécutés par HTMX.
 * Cette fonction remplace les scripts inline du template OOB.
 *
 * COMMUNICATION :
 * Reçoit : 'htmx:wsAfterMessage' (HTMX ws extension — après réception message WebSocket)
 */
function syncStockBloquantApresWebSocket() {
	try {
		// Parcourir tous les badges stock présents dans le DOM
		// / Loop through all stock badges in the DOM
		const tousLesBadges = document.querySelectorAll('[id^="stock-badge-"]')

		for (const badgeDiv of tousLesBadges) {
			const productUuid = badgeDiv.id.replace('stock-badge-', '')
			const articleContainer = document.querySelector(`[data-uuid="${productUuid}"]`)
			if (!articleContainer) {
				continue
			}

			// Propager l'état bloquant du badge vers le container
			// / Propagate blocking state from badge to container
			if (badgeDiv.dataset.stockBloquant === 'true') {
				articleContainer.classList.add('article-bloquant')
				articleContainer.dataset.stockBloquant = 'true'
			} else {
				articleContainer.classList.remove('article-bloquant')
				delete articleContainer.dataset.stockBloquant
			}
		}
	} catch (error) {
		console.log('-> articles.js - syncStockBloquantApresWebSocket,', error)
	}
}

/**
 * Ferme le panel contextuel article (vide son contenu).
 * Appelé par les boutons [✕] dans les partials du panel.
 * / Closes the article context panel (empties its content).
 * Called by [✕] buttons in panel partials.
 *
 * LOCALISATION : laboutik/static/js/articles.js
 */
function closeArticlePanel() {
	document.getElementById('article-panel').innerHTML = ''
}

document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#products').addEventListener('click', manageKey)
	document.querySelector('#products').addEventListener('articlesRemove', articlesRemove)
	document.querySelector('#products').addEventListener('articlesReset', articlesReset)
	document.querySelector('#products').addEventListener('articlesDisplayCategory', articlesDisplayCategory)

	// Après chaque message WebSocket, synchroniser l'état bloquant
	// des badges stock vers les containers articles.
	// / After each WebSocket message, sync blocking state
	// from stock badges to article containers.
	document.body.addEventListener('htmx:wsAfterMessage', syncStockBloquantApresWebSocket)

	// Long press sur un article → charger le panel contextuel via HTMX
	// / Long press on article → load contextual panel via HTMX
	document.querySelector('#products').addEventListener('longpress', function (e) {
		const uuid = e.detail.productUuid
		if (!uuid) return
		htmx.ajax('GET', '/laboutik/article-panel/' + uuid + '/panel/', {
			target: '#article-panel',
			swap: 'innerHTML'
		})
	})
})
