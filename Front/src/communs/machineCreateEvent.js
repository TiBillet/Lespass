import { guard, immediate, state, transition } from 'robot3';


function validateEmail(email) {
  const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/;
  if (email.match(re) === null) {
    return false;
  } else {
    return true;
  }
};

function canSubmitEspace(ctx) {
  // console.log('-> canSubmitEspace, ctx =', ctx);
  let error = 0
  const input = document.querySelector('input[role="textbox"][aria-label="email pour le login"]').parentNode.querySelector('.invalid-feedback')
  const radioImg = document.querySelector('label[role="fake-input-radio"][aria-labelledby="Lieu / association"] .invalid-feedback')
  // DOM
  if (ctx.categorie === "") {
    error++
    radioImg.style.display = "flex"
  } else {
    radioImg.style.display = "none"
  }
  if (validateEmail(ctx.email) === false) {
    error++
    input.style.display = "flex"
  } else {
    input.style.display = "none"
  }
  if (error === 0) {
    return true
  }
  return false
}

function cantSubmitEspace(ctx) {
  return !canSubmitEspace(ctx)
}

function canSubmitInformations(ctx) {
  console.log('--------------------------------------------------');
  console.log('-> canSubmitInformations, ctx =', ctx);
  let error = 0
  console.log('-> canSubmitInformations.');

  const organisation = document.querySelector(`input[role="textbox"][aria-label="nom de l'organisation"]`).parentNode.querySelector('.invalid-feedback')
  const shortDescription = document.querySelector(`input[role="textbox"][aria-label="courte description"]`).parentNode.querySelector('.invalid-feedback')
  const img = document.querySelector(`input[role="textbox"][aria-label="Sélectionner une image"]`).parentNode.querySelector('.invalid-feedback')
  const logo = document.querySelector(`input[role="textbox"][aria-label="Sélectionner un logo"]`).parentNode.querySelector('.invalid-feedback')

  // DOM
  if (ctx.organisation === "") {
    error++
    organisation.style.display = "flex"
  } else {
    organisation.style.display = "none"
  }

  if (ctx.short_description === "") {
    error++
    shortDescription.style.display = "flex"
  } else {
    shortDescription.style.display = "none"
  }

  if (ctx.img === null) {
    error++
    img.style.display = "flex"
  } else {
    img.style.display = "none"
  }

  if (ctx.logo === null) {
    error++
    logo.style.display = "flex"
  } else {
    logo.style.display = "none"
  }

  // retour
  if (error === 0) {
    return true
  }
  return false
}

function cantSubmitInformations(ctx) {
  return !canSubmitInformations(ctx)
}

export const machineCreateEvent = {
  espace: state(
    transition('evtValidateEspace', 'espaceNoValidate',
      guard(cantSubmitEspace)
    ),
    transition('evtValidateEspace', 'informations',
      guard(canSubmitEspace)
    )
  ),
  espaceNoValidate: state(
    transition('evtValidateEspace', 'espaceNoValidate',
      guard(cantSubmitEspace)
    ),
    transition('evtValidateEspace', 'informations',
      guard(canSubmitEspace)
    )
  ),
  informations: state(
    transition('evtReturnEspace', 'espace'),
    transition('evtValidateInformations', 'summary',
      guard(canSubmitInformations)
    ),
    transition('evtValidateInformations', 'informationsNoValidate',
      guard(cantSubmitInformations)
    )
  ),
  informationsNoValidate: state(
    transition('evtReturnEspace', 'espace'),
    transition('evtValidateInformations', 'informationsNoValidate',
      guard(cantSubmitInformations)
    ),
    transition('evtValidateInformations', 'summary',
      guard(canSubmitInformations)
    ),
  ),
  summary: state(
    transition('evtReturnInformations', 'informations')
  )
}
