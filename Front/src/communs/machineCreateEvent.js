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
  // console.log('-> canSubmitTabEspace, ctx =', ctx);
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

  if (ctx.long_description === "") {
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

function informationsChange(ctx) {
  const retour = false
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
    // dev
    transition('evtShowTabSummary', 'showTabSummary')
  ),
  espaceFullData: state(
    transition('evtInputsEspace', 'showBtNextForGoInformations',
      guard(canSubmitTabEspace)
    ),
    transition('evtShowTabInformtions', 'showTabInformtions',
      guard(informationsNoChange)
    )
    ,
    transition('evtShowTabInformtions', 'showTabInformtionsFullData',
      guard(informationsChange)
    )
  ),
  showBtNextForGoInformations: state(
    transition('evtShowTabInformtions', 'showTabInformtions'),
    transition('evtInputsEspace', 'espace',
      guard(cantSubmitTabEspace)
    ),
  ),
  showTabInformtions: state(
    transition('evtReturnEspace', 'espaceFullData'),
    transition('evtInputsInformations', 'showBtNextForGoSummary',
      guard(canSubmitTabInformations)
    )
  ),
  showTabInformtionsFullData: state(
    transition('evtReturnEspace', 'espaceFullData'),
    transition('evtShowTabSummary', 'showTabSummary'),
    transition('evtInputsInformations', 'showBtNextForGoSummary',
      guard(canSubmitTabInformations)
    )
  ),
  showBtNextForGoSummary: state(
    // return
    transition('evtReturnEspace', 'espaceFullData'),
    // suivant
    transition('evtShowTabSummary', 'showTabSummary'),
    // tester les entrées
    transition('evtInputsInformations', 'showTabInformtionsFullData')
  ),
  showTabSummary: state(
    transition('evtReturnInformations', 'showTabInformtionsFullData'),
  )
}
