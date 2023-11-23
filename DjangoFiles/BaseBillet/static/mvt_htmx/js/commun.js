console.log('-> commun.js');
const domain = `${window.location.protocol}//${window.location.host}`;
console.log('domain =', domain);

function showModal(id) {
  const elementModal = document.querySelector(id);
  const modal = bootstrap.Modal.getOrCreateInstance(elementModal);
  modal.show();
}

function hideModal(id) {
  const elementModal = document.querySelector(id);
  const modal = bootstrap.Modal.getOrCreateInstance(elementModal);
  modal.hide();
}


 // une fois l'élément remplacé par le contenu de la requête
document.body.addEventListener("htmx:afterSettle", (evt) => {
  console.log('-> htmx:afterSwap evt.target.id =', evt.target.id);

  // show modal membership_form.html
  if (evt.target.id === "tibillet-membership-modal") {
    showModal("#tibillet-membership-modal");
  }

  if (evt.target.id === "tibillet-modal-message") {
    hideModal("#tibillet-login-modal");
    showModal('#tibillet-modal-message')
  }
});

// gestion du spinner
document.body.addEventListener('htmx:beforeRequest', function (evt) {
  console.log('-> lance le spinner');
  document.querySelector('#tibillet-spinner').style.display = "flex"
});
document.body.addEventListener('htmx:afterRequest', function (evt) {
  console.log('-> stop le spinner');
  document.querySelector('#tibillet-spinner').style.display = "none"
});

// TODO: à modifier fonctionne partiellement
function updateTheme() {
  document.querySelectorAll('.maj-theme').forEach(ele => {
    ele.classList.toggle('dark-version')
  })
}
