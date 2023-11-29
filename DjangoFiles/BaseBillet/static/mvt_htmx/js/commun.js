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

// --- gestion du spinner ---
// affiche
document.body.addEventListener('htmx:beforeRequest', function (evt) {
    console.log('-> lance le spinner');
    document.querySelector('#tibillet-spinner').style.display = "flex"
});
// efface
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

// dev test
function testJs() {
    console.log('-> fonc testJs ' + new Date() + ' !')
}

// show toasts
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.toast').forEach(toast => {
        toast.classList.add('show')
    })
})

// for components
function inputNumberNomNominatif(id,action, value1, value2) {
    const element = document.querySelector('#' + id)
    let number = parseInt(element.value)
    if (action === 'plus') {
        let max = value2
        if (value1 < value2) {
            max = value1
        }
        if ((number +1) <= max ) {
            element.value = number + 1
        }
    } else{
        // value1 = min
        if ((number -1) >= value1) {
            element.value = number - 1
        }
    }
}