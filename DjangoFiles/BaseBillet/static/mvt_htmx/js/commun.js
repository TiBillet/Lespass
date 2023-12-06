// Le code commun à plusieurs éléments est mis si-dessous

function showModal(id) {
  bootstrap.Modal.getOrCreateInstance(document.querySelector(id)).show()
}

function hideModal(id) {
  bootstrap.Modal.getOrCreateInstance(document.querySelector(id)).hide()
}


// une fois l'élément remplacé par le contenu de la requête
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

// --- gestion du spinner ---
// affiche
document.body.addEventListener('htmx:beforeRequest', function () {
  document.querySelector('#tibillet-spinner').style.display = "flex"
});
// efface
document.body.addEventListener('htmx:afterRequest', function () {
  document.querySelector('#tibillet-spinner').style.display = "none"
});

// TODO: à modifier fonctionne partiellement
function updateTheme() {
  document.querySelectorAll('.maj-theme').forEach(ele => {
    ele.classList.toggle('dark-version')
  })
}


function initManageInputs() {
  document.querySelectorAll('input').forEach(input => {
    const inputType = input.getAttribute('type')
    // number et tel
    if ((inputType === 'number' || inputType === 'tel')) {
      input.addEventListener("change", formatNumber)
      input.addEventListener("blur", formatNumber)
    }
    // email
    if (inputType === 'email') {
      input.addEventListener("keyup", validateEmail)
      input.addEventListener("change", validateEmail)
      input.addEventListener("blur", validateEmail)
    }

    // correction "is-filled" de material kit
    if (['number', 'email', 'text', 'tel'].includes(inputType) && input.value !== "") {
      input.parentNode.classList.add('is-filled')
    }
  })
}

/**
 * Initialise
 * L'affichage des "toasts" présent dans le document
 * Reset des inputs radio et checkbox
 * Gère le formatage des entrées(input)
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

  // gère le formatage des entrées(input)
  initManageInputs()
})

// manage validation forms
const forms = document.querySelectorAll('.needs-validation')
// Loop over them and prevent submission
Array.from(forms).forEach(form => {
  form.addEventListener('submit', event => {
    console.log('validation =', form.checkValidity())
    if (!form.checkValidity()) {
      event.preventDefault()
      event.stopPropagation()
    }
    form.classList.add('was-validated')
  }, false)
})

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


/**
 * Gére un produit avec plusieurs clients
 * Ajoute dans le formulaire un nouveau client (interface = nom/prénom/suppression client)
 * @param element
 * @param {string} prefixName - Préfixe contenu dans l'attribut name
 * @param {string} priceUuid - Uuid du prix
 * @param {string} priceName - Nom du prix
 * @param {number} stock - Nombre maxi de produit
 * @param {number} maxPerUser - Nombre maxi de produit par utilisateur
 */
function addReservation(element, prefixName, priceUuid, priceName, stock, maxPerUser) {
  const index = parseInt(element.getAttribute('data-index'))
  const max = getMin(stock, maxPerUser)
  // console.log('index =', index, '  --  max =', max)
  if ("content" in document.createElement("template")) {
    // le navigateur gère <template>
    const templateCustomer = document.querySelector('#tibillet-customer-template')
    let clone = document.importNode(templateCustomer.content, true);
    let parent = clone.querySelector('div[role="group"]')
    // modifier le parent (aria-label/id)
    parent.setAttribute('aria-label', `Customer - ${priceName} - ${index + 1}`)
    parent.setAttribute('id', `tibillet-group-customer-${index + 1}-${priceUuid}`)
    // modifier input first name (name)
    parent.querySelectorAll('input')[0].setAttribute('name', `${prefixName}-first-name-${index + 1}-${priceUuid}`)
    // modifier input last name (name)
    parent.querySelectorAll('input')[1].setAttribute('name', `${prefixName}-last-name-${index + 1}-${priceUuid}`)
    // modifier bouton (aria-label/méthode)
    parent.querySelector('button').setAttribute('aria-label', `Supprimer ce client, ${priceName}`)
    parent.querySelector('button').setAttribute('onclick', `deleteCustomer('tibillet-group-customer-${index + 1}-${priceUuid}','${priceUuid}')`)
    // modifier l'index du bouton "ajouter réservation"
    element.setAttribute('data-index', index + 1)
    document.querySelector(`#tibillet-container-customers-${priceUuid}`).appendChild(clone)
  } else {
    // le navigateur ne gère pas <template>
    console.log('Le navigateur ne gère pas le tag "<template>" !')
  }
  const nbCustomers = document.querySelector(`#tibillet-container-customers-${priceUuid}`).querySelectorAll('.tibillet-group-customer').length
  if (nbCustomers === max) {
    element.style.display = 'none'
  }
}

/**
 * Supprime le couple nom/prénom et affiche le bouton "Ajouter réservation"
 * @param {string} id - id(Dom) du groupe(prénom/nom) client à supprimer
 * @param {string} priceUuid - Uuid du prix concerné lors de la suppression
 */
function deleteCustomer(id, priceUuid) {
  // supprime le couple customer first name, las name
  document.querySelector('#' + id).remove()
  // affiche le bouton "ajouter réservation
  document.querySelector(`#tibillet-add-reservation-${priceUuid}`).style.display = 'block'
}

function join(priceUuid, priceName, pricePrix, priceStock, priceMaxPerUser) {
  console.log('priceUuid =', priceUuid, '  --  priceName =', priceName, '  -- pricePrix =', pricePrix, '  --  priceStock =', priceStock, '  --  priceMaxPerUser =', priceMaxPerUser)
  if ("content" in document.createElement("template")) {
    // le navigateur gère <template>

    // 1- remplacer "block je m'abonne" par "block price, ajouter une réservation"
    const templatePrice = document.querySelector('#tibillet-nominative-price')
    let clone = document.importNode(templatePrice.content, true);
    // adapter le template
    let parent = clone.querySelector('div[role="group"]')
    let button = parent.querySelector('button')
    let h4 = parent.querySelector('h4')
    parent.setAttribute('id', `tibillet-price-with-adhesion-required-${priceUuid}`)
    parent.setAttribute('aria-label', `groupe interaction tarif ${priceName}`)
    h4.setAttribute('aria-label', priceName)
    h4.innerText = `${priceName.toLowerCase()} : ${pricePrix} €`
    button.setAttribute('id', `tibillet-add-reservation-${priceUuid}`)
    button.setAttribute('aria-label', `Ajouter une réservation - ${priceName}`)
    button.setAttribute('data-index', 0)
    button.setAttribute('onclick', `addReservation(this,'tibillet-customer','${priceUuid}','${priceName}',${priceStock},${priceMaxPerUser})`)

    const cible = document.querySelector('#tibillet-activation-price-' + priceUuid)
    // effacer le bloc "nom:prix + bouton je m'abonne"
    cible.style.setProperty('display', 'none', 'important')
    // ajouter un "block prix"
    cible.before(clone)
    // ajout du container customers
    cible.insertAdjacentHTML('afterend', `<div id="tibillet-container-customers-${priceUuid}" class="d-flex flex-column">`)

    // 2 - ajouter l'adhésion
    const templateAdhesion = document.querySelector(`#tibillet-template-adhesion-required-${priceUuid}`)
    let cloneAdhesion = document.importNode(templateAdhesion.content, true);
    const cibleAdhesion = document.querySelector(`#tibillet-adhesion-container-${priceUuid}`)

    cibleAdhesion.append(cloneAdhesion)
  } else {
    // le navigateur ne gère pas <template>
    console.log('Le navigateur ne gère pas le tag "<template>" !')
  }
}

function unsubscribeAdhesionRequired(priceUuid) {
  // enlever l'adhésion obligatoire
  document.querySelector(`#tibillet-adhesion-required-${priceUuid}`).remove()
  // enlever le "block price + ajouter une réservation"
  document.querySelector(`#tibillet-price-with-adhesion-required-${priceUuid}`).remove()
  // réafficher le "block price + je m'abonne"
  document.querySelector(`#tibillet-activation-price-${priceUuid}`).style.setProperty('display', 'flex', 'important')
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
  if (min !== null) {
    min = parseInt(min)
  } else {
    min = 1
  }
  let max = element.getAttribute('max')
  if (max !== null) {
    max = parseInt(max)
  } else {
    max = 100000
  }
  let initValue = element.value
  element.value = initValue.replace(/[^\d+]/g, '')
  // gère le nombre de chiffre max du input
  if (limit !== null) {
    limit = parseInt(limit)
    element.value = element.value.substring(0, limit)
  }

  if (element.value < min) {
    element.value = min
  }
  if (element.value > max) {
    element.value = max
  }

  element.parentNode.classList.remove('is-invalid')
  element.parentNode.classList.add('is-valid')

  if (element.value.length < limit) {
    element.parentNode.classList.remove('is-valid')
    element.parentNode.classList.add('is-invalid')
  }
}