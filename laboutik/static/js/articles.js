/**
 * ARTICLES.JS - GESTION DE LA GRILLE D'ARTICLES
 * / Article grid management
 * 
 * LOCALISATION : laboutik/static/js/articles.js
 * 
 * Gère l'affichage et la sélection des articles :
 * - Détection des clics sur les articles
 * - Incrémentation des quantités
 * - Gestion des groupes (verrouillage/déverrouillage)
 * 
 * COMMUNICATION :
 * Émet : 'articlesAdd' (vers #addition via tibilletUtils.js)
 * Reçoit : 'articlesRemove', 'articlesReset', 'articlesDisplayCategory'
 * 
 * GESTION DES GROUPES :
 * Les articles ont un data-group. Quand on sélectionne un article,
 * tous les articles des AUTRES groupes sont verrouillés (article-lock-layer).
 * Cela empêche de mélanger certains types d'articles dans une commande.
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
 * Gère la sélection d'un article (clic)
 * / Manages article selection (click)
 * 
 * Écouteur principal attaché à #products (délégation d'événements).
 * Déclenché à chaque clic sur une tuile article.
 * 
 * Actions :
 * 1. Récupère les données de l'article (uuid, group, price, name, currency)
 * 2. Si l'article a un groupe : verrouille les articles des autres groupes
 *    - Ajoute data-disable="true"
 *    - Affiche article-lock-layer (overlay gris)
 * 3. Appelle addArticle() pour incrémenter et émettre l'événement
 * 
 * @param {Object} event - Événement clic
 */
function manageKey(event) {
	const ele = event.target.parentNode
	// TODO : Que se passe-t-il si on clique sur un élément très profond (ex: icône dans l'icône) ?
	// event.target.parentNode pourrait ne pas être l'article-container mais un élément intermédiaire.
	// Ne devrait-on pas remonter récursivement jusqu'à trouver .article-container ou null ?
	
	if (ele.classList.contains('article-container') && ele.getAttribute('data-disable') === null) {
		const articleUuid = ele.dataset.uuid
		const articleGroup = ele.dataset.group
		const articlePrice = ele.dataset.price
		const articleName = ele.dataset.name
		const articleCurrency = ele.dataset.currency

		// Verrouille les articles des autres groupes
		document.querySelectorAll('#products .article-container').forEach(item => {
			const itemGroup = item.dataset.group
			if (itemGroup !== articleGroup) {
				item.querySelector('.article-lock-layer').style.display = "block"
				item.setAttribute('data-disable', 'true')
			}
		})
		// TODO : Une fois les articles d'autres groupes verrouillés, ils le restent même si
		// on retire tous les articles du groupe actif. Ne devrait-on pas déverrouiller automatiquement
		// quand le panier devient vide ? Actuellement seul le bouton RESET permet de déverrouiller.

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
		article.querySelector(`#article-quantity-number-${uuid}`).innerText = quantity
	} catch (error) {
		console.log('-> article.js - articlesRemove,', error)
	}
}

/**
 * Réinitialise l'affichage de tous les articles (Handler)
 * / Resets all articles display
 * 
 * Reçoit 'articlesReset' depuis common_user_interface.html (bouton RESET).
 * Réinitialise complètement l'affichage des articles :
 * - Remet toutes les quantités à 0
 * - Supprime data-disable sur tous les articles
 * - Cache article-lock-layer (déverrouille)
 * 
 * Flux : clic RESET → 'resetArticles' → tibilletUtils.js → 'articlesReset' → CETTE FONCTION
 */
function articlesReset() {
	try {
		document.querySelectorAll('#products .article-container').forEach(article => {
			const uuid = article.dataset.uuid
			document.querySelector(`#article-quantity-number-${uuid}`).innerText = 0
			article.removeAttribute('data-disable')
			article.querySelector('.article-lock-layer').style.display = "none"
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
