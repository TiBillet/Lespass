function showModal(id) {
  bootstrap.Modal.getOrCreateInstance(document.querySelector(id)).show()
}

function hideModal(id) {
  /*
  const elementModal = document.querySelector(id);
  const modal = bootstrap.Modal.getOrCreateInstance(elementModal);
  modal.hide();
   */
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
  console.log('-> lance le spinner');
  document.querySelector('#tibillet-spinner').style.display = "flex"
});
// efface
document.body.addEventListener('htmx:afterRequest', function () {
  console.log('-> stop le spinner');
  document.querySelector('#tibillet-spinner').style.display = "none"
});

// TODO: à modifier fonctionne partiellement
function updateTheme() {
  document.querySelectorAll('.maj-theme').forEach(ele => {
    ele.classList.toggle('dark-version')
  })
}

/**
 * Affiche les "toasts" présent dans le document
 */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.toast').forEach(toast => {
    toast.classList.add('show')
  })
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
  if (action === 'plus') {
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