import { guard, immediate, state, transition } from 'robot3';


function validateEmail(email) {
  const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/;
  if (email.match(re) === null) {
    return false;
  } else {
    return true;
  }
};

function canSubmitTabEspace(ctx) {
  console.log('-> canSubmitTabEspace, ctx.categorie  =', ctx.categorie, '  --  validateEmail(ctx.email)  =', validateEmail(ctx.email));
  if (ctx.categorie !== "" && validateEmail(ctx.email) === true) {
    return true
  }
  return false
}

function cantSubmitTabEspace(ctx) {
  // console.log('-> cantSubmitTabEspace, ctx =', ctx);
  if (ctx.categorie === "" || validateEmail(ctx.email) === false) {
    return true
  }
  return false
}


function canSubmitTabInformations(ctx) {
  let error = 0
  if (ctx.organistaion === "") {
    error++
    // TODO: afficher le message d'erreur "invalid-feedback" 
  }
  if (ctx.short_description === "") {
    error++
    // TODO: afficher le message d'erreur "invalid-feedback" 
  }

  // console.log('-> test textarea =', ctx.long_description.replace('\n', ''));
  let longDescription = ctx.long_description
  if (longDescription.replace('\n', '').replace(' ', '') === "") {
    error++
    // TODO: afficher le message d'erreur "invalid-feedback" 
  }

  if (ctx.img === null) {
    error++
    // TODO: afficher le message d'erreur "invalid-feedback" 
  }

  if (ctx.logo === null) {
    error++
    // TODO: afficher le message d'erreur "invalid-feedback" 
  }

  // retour
  if (error === 0) {
    return true
  }
  return false
}

function cantSubmitTabInformations(ctx) {
  let retour = true
  if (canSubmitTabInformations(ctx) === true) {
    retour = false
  }
  return retour
}

function informationsChange(ctx) {
  let retour = false
  const testChange = {
    organisation: "",
    short_description: "",
    long_description: "",
    img: null,
    logo: null
  }
  for (const key in testChange) {
    console.log('key =', key);
    if (ctx[key] !== testChange[key]) {
      retour = true
      break
    }
  }
  return retour
}

function informationsNoChange(ctx) {
  // if (informationsChange(ctx) === true) {
  //   return false
  // }
  return !informationsChange(ctx)
}


export const machineCreateEvent = {
  espace: state(
    transition('evtInputsEspace', 'showBtNextForGoInformations',
      guard(canSubmitTabEspace)
    ),
  ),
  // TODO: remplacer showBtNextForGoInformations par "espaceValide"
  showBtNextForGoInformations: state(
    transition('evtShowTabInformtions', 'showTabInformtions',
      guard(cantSubmitTabInformations)
    ),
    transition('evtShowTabInformtions', 'showBtNextForGoSummary',
      guard(canSubmitTabInformations)
    ),
    transition('evtInputsEspace', 'espace',
      guard(cantSubmitTabEspace)
    ),
  ),
  showTabInformtions: state(
    transition('evtReturnEspace', 'showBtNextForGoInformations'),
    transition('evtInputsInformations', 'showBtNextForGoSummary',
      guard(canSubmitTabInformations)
    )
  ),
  showBtNextForGoSummary: state(
    // retour
    transition('evtReturnEspace', 'showBtNextForGoInformations'),
    // tester les entrées
    transition('evtInputsInformations', 'showTabInformtions',
      guard(cantSubmitTabInformations)
    ),
    // aller au résumé / validation
    transition('evtShowTabSummary', 'showTabSummary',
      guard(canSubmitTabInformations)
    )
  ),
  showTabSummary: state(
    transition('evtReturnInformations', 'showBtNextForGoSummary'),
  )
}
