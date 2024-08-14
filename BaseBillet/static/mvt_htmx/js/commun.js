// window.xxxx (scope global) est utilisé pour rendre acessible les variables et fonctions à htmx en rendu partiel.

// Le code commun à plusieurs éléments est mis si-dessous
const listInputsToFilled = ['number', 'email', 'text', 'tel']
const listNumber = ['number', 'tel']

// pour la création d'un évènement
let stepEvalRange, currentRangeStart

// create tenant
let etape

window.showModal = function (id) {
	bootstrap.Modal.getOrCreateInstance(document.querySelector(id)).show()
}

window.hideModal = function (id) {
	bootstrap.Modal.getOrCreateInstance(document.querySelector(id)).hide()
	window.setTimeout(() => {
		document.querySelector('.modal-backdrop').remove()
	}, 700)
}

window['htmlEntities'] = function (str) {
	return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// TODO: à modifier fonctionne partiellement
window.updateTheme = function () {
	document.querySelectorAll('.maj-theme').forEach(ele => {
		ele.classList.toggle('dark-version')
	})
}


/**
 * Donne la valeur mini
 * @param {number} value1 - Valeur 1
 * @param {number} value2 - Valeur 2
 * @returns {number}
 */
window.getMin = function (value1, value2) {
	let min = 0
	if (value1 === value2) {
		min = value1
	}
	if (value1 < value2) {
		min = value1
	}
	if (value2 < value1) {
		min = value2
	}
	return min
}

// for components
/**
 * Gére un produit avec un seul client
 * @param {string} id - Id du input à gérer
 * @param {string} action - Action(plus ou moins) à gérer
 * @param {number} value1 - Pour action=plus: Nombre maxi de produit, Pour action=moins: nombre minimum
 * @param {number} value2 - Nombre maxi de produit par utilisateur
 */
window.inputNumberNomNominatif = function (id, action, value1, value2) {
	const element = document.querySelector('#' + id)
	let number = parseInt(element.value)
	if (action === 'over') {
		let max = getMin(value1, value2)
		if ((number + 1) <= max) {
			element.value = number + 1
		}
	} else {
		// value1 = min
		if ((number - 1) >= value1) {
			element.value = number - 1
		}
	}
}

/**
 * Gère le groupe bouton "-" + input + bouton "+"
 * min = valeur minimale fixée si pas attribué (attribut min du input)
 * max = valeur maximale fixée si pas attribué (attribut max du input)
 * @param {string} action - under=moins ou over=plus
 * @param {string} inputId - Dom, id (sans le #) de l'input contenant le nombre
 */
window.inputNumberGroup = function (action, inputId) {
	const input = document.querySelector('#' + inputId)
	let min = input.getAttribute('min')
	if (min !== null) {
		min = parseInt(min)
	} else {
		min = 1
	}
	let max = input.getAttribute('max')
	if (max !== null) {
		max = parseInt(max)
	} else {
		max = 100000
	}

	let valueInput = input.value

	// moins
	if (action === 'under') {
		if (valueInput === '') {
			valueInput = 6
		}
		if (valueInput > min) {
			--valueInput
		}
	}
	// plus
	if (action === 'over') {
		if (valueInput === '') {
			valueInput = 4
		}
		if (valueInput < max) {
			++valueInput
		}
	}
	input.value = valueInput
}

window.formatNumberParentNode2 = function (event, limit) {
	const element = event.target
	// obligation de changer le type pour ce code, si non "replace" ne fait pas "correctement" son travail
	element.setAttribute('type', 'text')
	let initValue = element.value
	element.value = initValue.replace(/[^\d+]/g, '').substring(0, limit)
	if (element.value.length < limit) {
		element.parentNode.classList.remove('is-valid')
		element.parentNode.classList.add('is-invalid')
	} else {
		element.parentNode.classList.remove('is-invalid')
		element.parentNode.classList.add('is-valid')
	}
}

window.validateEmail = function (evt) {
	let value = evt.target.value
	const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/
	if (value.match(re) === null) {
		evt.target.parentNode.classList.remove('is-valid')
		evt.target.parentNode.classList.add('is-invalid')
	} else {
		evt.target.parentNode.classList.remove('is-invalid')
		evt.target.parentNode.classList.add('is-valid')
	}
}

/**
 * Format la valeur entrée dans input
 * Attribut DOM/variable js - limit = gère le nombre de chiffre max
 * Attribut DOM/variable js - min = gère la valeur mini
 * Attribut DOM/variable js - max = gère la valeur maxi
 * @param {object} event - èvènement du input
 */
window.formatNumber = function (event) {
	// console.log('-> formatNumber !')
	const element = event.target
	// limite le nombre de chiffre
	let limit = element.getAttribute('limit')
	let min = element.getAttribute('min')
	let max = element.getAttribute('max')

	if (limit !== null && (min !== null || max !== null)) {
		console.log('Attention: l\'attribut limit ne peut être utilisé avec min ou max !')
		return
	}

	let initValue = element.value
	element.value = initValue.replace(/[^\d+]/g, '')
	// gère le nombre de chiffre max du input
	if (limit !== null) {
		limit = parseInt(limit)
		element.value = element.value.substring(0, limit)
	}

	if (limit === null) {
		if (min !== null) {
			min = parseInt(min)
		} else {
			min = 1
		}
		if (max !== null) {
			max = parseInt(max)
		} else {
			max = 100000
		}
		if (element.value < min) {
			element.value = min
		}
		if (element.value > max) {
			element.value = max
		}
	}

	element.parentNode.classList.remove('is-invalid')
	element.parentNode.classList.add('is-valid')

	if (element.value.length < limit) {
		element.parentNode.classList.remove('is-valid')
		element.parentNode.classList.add('is-invalid')
	}
}

// check input type number, tel and email
function testInput(event) {
	const input = event.target
	let inputType = input.getAttribute('type')

	if (inputType !== null) {
		// gestion number
		const listNumber = ['number', 'tel']
		if (listNumber.includes(inputType)) {
			formatNumber(event)
		}

		// email
		if (inputType === 'email') {
			validateEmail(event)
		}
	}
}


// bypass submit / check form / scroll to error
window.validateForm = function (evt, elementForm) {
	let form
	if (elementForm !== undefined) {
		form = elementForm
	} else {
		form = evt.target
	}

	// console.log("-> evt.target.checkValidity() =", form.checkValidity())
	if (form.checkValidity() === false) {
		// efface le spinner
		document.querySelector('#tibillet-spinner').style.display = 'none'
		if (evt !== undefined && evt !== null) {
			evt.preventDefault()
			evt.stopPropagation()
		}
		// élément invalid
		const invalidElement = form.querySelector('input:invalid')
		// éffacer les anciens/autres éléments invalident
		form.querySelectorAll('input').forEach(ele => {
			ele.parentNode.querySelector('label').classList.remove('track')
		})
		invalidElement.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'center' })
		invalidElement.focus()

		if (invalidElement.type === 'radio') {
			const multi = document.querySelectorAll(`input[name=${invalidElement.getAttribute('name')}]`)
			multi.forEach(mele => {
				mele.parentNode.querySelector('label').classList.add('track')
			})
		} else {
			const label = invalidElement.parentNode.querySelector('label')
			label.classList.add('track')
		}
	}
}

// manage validation form, stop track after click for inputs
document.body.addEventListener('click', (evt) => {
	const element = evt.target
	if (element.tagName === 'INPUT' && element.style.display !== 'none') {

		if (element.type === 'radio') {
			const multi = document.querySelectorAll(`input[name=${element.getAttribute('name')}]`)
			multi.forEach(mele => {
				mele.parentNode.querySelector('label').classList.remove('track')
			})
		} else {
			if (element.parentNode.querySelector('label') !== null) {
				element.parentNode.querySelector('label').classList.remove('track')
			}
		}
	}
})


// gestion des inputs (number, email)
document.addEventListener('keyup', (event) => {
	testInput(event)
})

/**
 * Initialise, une fois le contenu du DOM Chargé :
 * L'affichage des "toasts" présent dans le document
 * Reset des inputs radio et checkbox
 */
document.addEventListener('DOMContentLoaded', () => {
	// toasts
	document.querySelectorAll('.toast').forEach(toast => {
		toast.classList.add('show')
	})

	// reset input checkbox
	document.querySelectorAll('input[type="checkbox"]').forEach(input => {
		input.checked = false
	})

	// reset input radio
	document.querySelectorAll('input[type="radio"]').forEach(input => {
		input.checked = false
	})
})

// material kit 2: restart the initialization of part of code on dynamics elements (htmx partial render)
// onLoad = when dom content loaded and htmx element add(swap)
htmx.onLoad(function (content) {
	// Material Design Input function
	var inputs = content.querySelectorAll('input');

	for (var i = 0; i < inputs.length; i++) {
		inputs[i].addEventListener('focus', function (e) {
			this.parentElement.classList.add('is-focused');
		}, false);

		inputs[i].onkeyup = function (e) {
			if (this.value != "") {
				this.parentElement.classList.add('is-filled');
			} else {
				this.parentElement.classList.remove('is-filled');
			}
		};

		inputs[i].addEventListener('focusout', function (e) {
			if (this.value != "") {
				this.parentElement.classList.add('is-filled');
			}
			this.parentElement.classList.remove('is-focused');
		}, false);
	}
})
