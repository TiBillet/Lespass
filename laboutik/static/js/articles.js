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
		const eleQuantity = document.querySelector(`#article-quantity-number-${uuid}`)
		let quantity = Number(eleQuantity.innerText)
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
		const articleUuid = ele.dataset.uuid
		const articlePrice = ele.dataset.price
		const articleName = ele.dataset.name
		const articleCurrency = ele.dataset.currency
		const multiTarif = ele.dataset.multiTarif === 'true'

		// Si l'article a plusieurs tarifs ou un prix libre → ouvrir la selection de tarif
		// au lieu d'ajouter directement au panier.
		// / If the article has multiple rates or free price → open rate selection
		// instead of adding directly to cart.
		if (multiTarif) {
			sendEvent('organizerMsg', '#event-organizer', {
				src: { file: 'articles.js', method: 'manageKey' },
				msg: 'tarifSelection',
				data: {
					uuid: articleUuid,
					name: articleName,
					tarifs: JSON.parse(ele.dataset.tarifs),
					currency: articleCurrency,
				}
			})
			return
		}

		addArticle(articleUuid, articlePrice, articleName, articleCurrency)
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
document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#products').addEventListener('click', manageKey)
	document.querySelector('#products').addEventListener('articlesRemove', articlesRemove)
	document.querySelector('#products').addEventListener('articlesReset', articlesReset)
	document.querySelector('#products').addEventListener('articlesDisplayCategory', articlesDisplayCategory)
})
