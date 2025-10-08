function calculateTotal() {
	total = 0
	document.querySelectorAll('#addition-form input').forEach(input => {
		const uuid = input.name
		const number = parseInt(input.value)
		const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
		const price = parseInt(article.dataset.price)
		total = total + (number * price)
	})
	// maj total
	document.querySelector('#bt-valider-total').innerText = (total / 100)
}

function updateArticlesAndAddition(uuid, number) {
	try {
		// article
		const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
		const articleName = article.querySelector('.article-name-layer').innerText
		const articlePrix = article.querySelector('.article-footer-layer .article-prix').innerText

		// maj number
		article.querySelector(`#article-quantity-number-${uuid}`).innerText = number

		if (number === 0) {
			// enlever l'input
			document.querySelector(`#addition-form input[name="${uuid}"]`).remove()
			// enlever la ligne d'addition
			document.querySelector(`#addition-line-${uuid}`).remove()
		} else {
			// addition
			const input = document.querySelector(`#addition-form [name="${uuid}"]`)
			if (input === null) {
				// création du input si inexistant
				document.querySelector('#addition-form').insertAdjacentHTML('beforeend', `<input type="number" name="${uuid}" value="1" />`)
				// création de la "ligne  d'addition" - css dans components/addition.html
				const additionLine = `<div id="addition-line-${uuid}" class="addition-line-grid">
				<div class="addition-col-bt BF-col">
          <i class="fas fa-minus-square" onclick="deleteProduct('${uuid}');" title="Enlever un article !"></i>
        </div>
				<div class="addition-col-number BF-col">${number}</div>
				<div class="addition-col-name BF-col">${articleName}</div>
				<div class="addition-col-prix BF-col">${articlePrix}</div>
			`
				document.querySelector('#addition-list').insertAdjacentHTML('beforeend', additionLine)
			} else {
				// maj input uniquement
				input.value = number
				document.querySelector(`#addition-line-${uuid} .addition-col-number`).innerText = number
			}
		}
		calculateTotal()
	} catch (error) {
		console.log('-> updateArticlesAndAddition,', error)

	}
}

function addArticle(uuid, prix) {
	let number
	const ele = document.querySelector(`#addition-form [name="${uuid}"]`)

	if (ele === null) {
		number = 1
	} else {
		number = parseInt(ele.value) + 1
	}

	// maj visuels
	updateArticlesAndAddition(uuid, number)
}

window.deleteProduct = function (uuid) {
	// article
	const article = document.querySelector(`#products div[data-uuid="${uuid}"]`)
	let number = parseInt(article.querySelector('.article-footer-layer .article-quantity').innerText)
	number = number - 1
	// maj visuels
	updateArticlesAndAddition(uuid, number)
}

function manageKey(event) {
	const ele = event.target.parentNode
	if (ele.classList.contains('article-container') && ele.getAttribute('data-disable') === null) {
		const articleUuid = ele.dataset.uuid
		const articlePrice = new Big(ele.dataset.price.replace(',', '.'))
		const articleGroup = ele.dataset.group

		// gérer les groupes d'articles : afficher le layer-lock
		document.querySelectorAll('#products .article-container').forEach(item => {
			itemGroup = item.dataset.group
			if (itemGroup !== articleGroup) {
				item.querySelector('.article-lock-layer').style.display = "block"
				item.setAttribute('data-disable', 'true')
			}
		})

		// ajouter un article
		addArticle(articleUuid, articlePrice)
	}
}

function manageReset() {
	document.querySelectorAll('#products .article-container').forEach(article => {
		const uuid = article.dataset.uuid
		// number articles à 0
		document.querySelector(`#article-quantity-number-${uuid}`).innerText = 0
		// enlever l'attribut et le visuel de désactivation
		article.removeAttribute('data-disable')
		article.querySelector('.article-lock-layer').style.display = "none"
	})
	// vider les inputs du formulaire
	document.querySelector('#addition-form').innerHTML = ''
	// vider les lignes d'addition
	document.querySelector('#addition-list').innerHTML = ''
	// total à 0
	document.querySelector('#bt-valider-total').innerText = 0
}

document.addEventListener('DOMContentLoaded', () => {
	document.querySelector('#products').addEventListener('click', manageKey)
	document.querySelector('#bt-reset').addEventListener('click', manageReset)
})
