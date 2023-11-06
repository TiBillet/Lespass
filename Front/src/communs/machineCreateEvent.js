const validateEmail = (ctx, value) => {
  const email = ctx[value];
  const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/;
  if (email.match(re) === null) {
    return false;
  } else {
    return true;
  }
};

export const machineCreateEvent = {
  selectEspace: {
    name: "selectEspace",
    actions: {
      onEnter(machine) {
        console.log('-> selectEspace, onEnter, machine =', machine);
        // --- entrée dans l'étape "selectEspace" ---
        const state = machine.state
        // active le premier inputRadioImg si un seul type d'espace
        if (state.espacesType.length === 1) {
          document.querySelector(`label[role="fake-input-radio"][aria-labelledby="${state.espacesType[0].name}"]`).click()
          state.categorie = state.espacesType[0].categorie
        }
        // stripe = true
        state.stripe = true

        // écoute sur email
        document.querySelector('#login-email').addEventListener('change', (evt) => {
          machine.state.email = evt.target.value
          machine.transition(machine.currentStepName)
          console.log('--> state =', machine.state);
        }, null, machine)
      }
    },
    destination: {
      target: "afficherBoutonSuivant0",
      action(machine, stepName) {
        const currentStep = machine.steps[stepName]
        const destination = currentStep?.destination?.target
        // conditions
        if (validateEmail(machine.state, "email") && machine.state.categorie !== "") {
          // lancer l'étape suivante
          machine.next(machine, destination, currentStep)
        } else {
          // ne rien faire
          console.log(`Je ne peux pas aller à l'étape "${destination}", les conditions ne sont pas bonnes !`);
        }
      }
    },
  },

  afficherBoutonSuivant0: {
    name: "afficherBoutonSuivant0",
    actions: {
      onEnter(machine) {
        // bouton suivant visible
        document.querySelector('button[role="button"][aria-label="suivant0"]').style.display = "flex"
        // activer le boutonn de navigation "INFORMATIONS"
        document.querySelector('li[data-cible="informations"]').classList.remove('tibillet-no-clickable')
      },
      onExit(machine) {
        
      },
    },
    destination: {
      target: "resume",
      action(machine, stepName) {
        console.log(
          'transition action for "destination" in "off" enterInformations'
        );
      },
    }
  },
};
