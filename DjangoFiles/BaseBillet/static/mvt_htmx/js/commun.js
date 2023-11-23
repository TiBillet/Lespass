console.log('-> commun.js');
const domain = `${window.location.protocol}//${window.location.host}`;
console.log('domain =', domain);

function showModal(id) {
  const elementModal = document.querySelector(id);
  const modal = bootstrap.Modal.getOrCreateInstance(elementModal);
  modal.show();
}

 // une fois l'élément remplacé par le contenu de la requête
 htmx.on("htmx:afterSettle", (evt) => {
  // console.log('-> htmx:afterSwap evt =', evt);
  
  // show modal membership_form.html
  if (evt.target.id === "tibillet-membership-modal") {
    showModal("#tibillet-membership-modal");
  }

    // show modal login.html
    if (evt.target.id === "tibillet-login-modal") {
      showModal("#tibillet-login-modal");
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
