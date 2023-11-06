export class CreateMachine {
  constructor(state, machineDefinition) {
    this.state = state;
    this.steps = machineDefinition;
    this.currentStepName = 'no init'
    this.logLevel = 1
  }

  transition(step) {
    if(this.logLevel > 3) {
      console.log("-> transition, step =", step);
    }
    const currentStep = this.steps[step];

    if (currentStep) {
      // actions.onEnter
      if (currentStep?.actions?.onEnter) {
        currentStep.actions.onEnter(this)
      }
      // go destination
      if (currentStep?.destination?.action) {
        currentStep.destination.action(this, step)
      }
    } else {
      console.log(`Etape "${step}" inexistant !`);
    }
  }

  next(machine, destination, currentStep) {
    // sortir de l'étape
    const exitFunction = currentStep?.actions?.onExit
    if (exitFunction) {
      currentStep.actions.onExit(this)
    }
    // lancer l'étape suivante
    if (destination) {
      // console.log(`Je peux aller à l'étape "${destination}" !`);
      machine.transition(destination)
    } else {
      console.log("Destination inconnue !")
    }
  }

  init(step) {
    if (this.logLevel > 3) {
      console.log('-> init, step =', step);
    }
    this.currentStepName = step
    const currentStep = this.steps[step];
    // actions.onEnter
    if (currentStep?.actions?.onEnter) {
      currentStep.actions.onEnter(this)
    }
  }
}