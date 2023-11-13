import { guard, state, transition } from 'robot3';

export const machineCreateEvent = {
    event: state(
    //   transition('evtValidateEvent', 'eventNoValidate'),
      transition('evtValidateEvent', 'informations')
    ),
    eventNoValidate: state(
    //   transition('evtValidateEvent', 'eventNoValidate'),
      transition('evtValidateEvent', 'informations')
    ) ,
    informations: state(
        transition('evtReturnEvent', 'event'),
        // transition('evtValidateInformations', 'informationsNoValidate'),
        transition('evtValidateInformations', 'prices'),
    ),
    informationsNoValidate: state(
        transition('evtReturnEvent', 'event'),
         // transition('evtValidateInformations', 'informationsNoValidate'),
          // transition('evtValidateInformations', 'prices'),
    ),
    prices: state(
        transition('evtReturnInformations', 'informations'),
    )
}
  