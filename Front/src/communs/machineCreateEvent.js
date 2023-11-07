import { guard, immediate, state, transition } from 'robot3';


function validateEmail(email) {
  const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/;
  if (email.match(re) === null) {
    return false;
  } else {
    return true;
  }
};

function canSubmitTabEspace(ctx, data) {
  if (ctx.categorie !== "" && validateEmail(ctx.email) === true) {
    return true
  }
  return false
}

export const machineCreateEvent = {
  espace: state(
    transition('evtInputsEspace', 'showBtNextForGoInformations',
      guard(canSubmitTabEspace)
    )
  ),
  showBtNextForGoInformations: state(
    transition('evtShowTabInformtions', 'showTabInformtions')
  ),
  showTabInformtions: state()
}
