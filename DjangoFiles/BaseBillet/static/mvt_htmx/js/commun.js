// Le code commun à plusieurs éléments est mis si-dessous
const listInputsToFilled = ['number', 'email', 'text', 'tel']
const listNumber = ['number', 'tel']

function showModal(id) {
  bootstrap.Modal.getOrCreateInstance(document.querySelector(id)).show()
}

function hideModal(id) {
  bootstrap.Modal.getOrCreateInstance(document.querySelector(id)).hide()
}


// TODO: à modifier fonctionne partiellement
function updateTheme() {
  document.querySelectorAll('.maj-theme').forEach(ele => {
    ele.classList.toggle('dark-version')
  })
}

/**
 * Ajoute la class "is-filled" si le input n'est pas vide
 * @param {object} input - Elément DOM
 */
function setInputFilled(input) {
  const inputType = input.getAttribute('type')
  if (listInputsToFilled.includes(inputType) && input.value !== "") {
    input.parentNode.classList.add('is-filled')
  }
}

function setAllInputFilled() {
  document.querySelectorAll('input').forEach(input => {
    const inputType = input.getAttribute('type')
    if (listInputsToFilled.includes(inputType) && input.value !== "") {
      input.parentNode.classList.add('is-filled')
    }
  })
}

/**
 * Donne la valeur mini
 * @param {number} value1 - Valeur 1
 * @param {number} value2 - Valeur 2
 * @returns {number}
 */
function getMin(value1, value2) {
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
function inputNumberNomNominatif(id, action, value1, value2) {
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
function inputNumberGroup(action, inputId) {
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

function formatNumberParentNode2(event, limit) {
  const element = event.target
  // obligation de changer le type pour ce code, si non "replace" ne fait pas "correctement" son travail
  element.setAttribute('type', 'text')
  let initValue = element.value
  element.value = initValue.replace(/[^\d+]/g, '').substring(0, limit)
  if (element.value.length < limit) {
    element.parentNode.parentNode.querySelector('.invalid-feedback').style.display = 'block'
  } else {
    element.parentNode.parentNode.querySelector('.invalid-feedback').style.display = 'none'
  }
}

function validateEmail(evt) {
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
function formatNumber(event) {
  // console.log('-> formatNumber !')
  const element = event.target
  // limite le nombre de chiffre
  let limit = element.getAttribute('limit')
  let min = element.getAttribute('min')
  let max = element.getAttribute('max')

  if (limit !== null && (min !== null || max !== null)) {
    console.log("Attention: l'attribut limit ne peut être utilisé avec min ou max !")
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

function testInput(event) {
  console.log('-> testInput, event=', event)
  const input = event.target
  let inputType = input.getAttribute('type')

  // is-filled
  setInputFilled(input)

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

// manage validation form, Block le "Post" si non valide
function blockSubmitFormIsNoValidate(event, id) {
  const form = document.querySelector('#' + id)

  // console.log('-> blockSubmitFormIsNoValidate')
  if (form.checkValidity() === false) {
    event.preventDefault()
    event.stopPropagation()
    // élément invalid
    const invalidElement = form.querySelector('input:invalid')
    // éffacer les anciens/autres éléments invalident
    form.querySelectorAll('input').forEach(ele => {
      ele.parentNode.querySelector('label').classList.remove('track')
    })
    invalidElement.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
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
  } else {
    form.submit()
  }
}

// manage validation form, stop track after click for inputs
// Vérifie is-filled
document.body.addEventListener("click", (evt) => {
  const element = evt.target
  if (element.tagName === "INPUT") {
    setInputFilled(element)

    if (element.type === 'radio') {
      const multi = document.querySelectorAll(`input[name=${element.getAttribute('name')}]`)
      multi.forEach(mele => {
        mele.parentNode.querySelector('label').classList.remove('track')
      })
    } else {
      element.parentNode.querySelector('label').classList.remove('track')
    }
  }
})

// --- mise en place des écoutes(lancement de codes en fonctions d'un message du DOM ---
// codes ou méthodes lancées une fois un élément remplacé par le contenu d'une requête
document.body.addEventListener("htmx:afterSettle", (evt) => {
  // console.log('-> htmx:afterSwap evt.target.id =', evt.target.id);

  if (evt.target.id === "tibillet-membership-modal") {
    showModal("#tibillet-membership-modal");
  }

  if (evt.target.id === "tibillet-modal-message") {
    hideModal("#tibillet-login-modal");
    showModal('#tibillet-modal-message')
  }
});

// affiche le spinner
document.body.addEventListener('htmx:beforeRequest', function () {
  document.querySelector('#tibillet-spinner').style.display = "flex"
});

// efface  le spinner
document.body.addEventListener('htmx:afterRequest', function () {
  document.querySelector('#tibillet-spinner').style.display = "none"
});

// gestion des inputs
document.addEventListener("keyup", (event) => {
  testInput(event)
});

/**
 * Initialise, une fois le contenu du DOM Chargé :
 * L'affichage des "toasts" présent dans le document
 * Reset des inputs radio et checkbox
 * Corrige material kit 2 "is-filled"
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

  // corrige material kit 2 "is-filled"
  setAllInputFilled()
})
