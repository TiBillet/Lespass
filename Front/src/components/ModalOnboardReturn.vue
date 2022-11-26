<template>
  <div id="modal-onboard-return" aria-hidden="true" aria-labelledby="modal-onboard-return"
       class="modal fade" role="dialog"
       tabindex="-1" data-backdrop="static">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="container card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-center">Dernière étape !</h3>
              <div class="d-flex flex-row justify-content-center">
                <hr class="text-dark w-50">
              </div>
            </div>

            <div class="card-body">
              <form @submit.prevent="ValidateTenant($event)" novalidate>
                <!-- prénom -->
                <label for="organisation">Nom de l'organisation</label>
                <div class="input-group mb-2 has-validation">
                  <input id="organisation" v-model="tenant.organisation" type="text"
                         class="form-control" aria-label="Prénom pour l'adhésion" required>
                  <div class="invalid-feedback">Merci de remplir le nom de votre organisation.</div>
                </div>

                <label for="short_description">Une courte description.</label>
                <div class="input-group mb-2 has-validation">
                  <input id="short_description" v-model="tenant.short_description" type="text"
                         class="form-control" aria-label="Prénom pour l'adhésion" required>
                  <div class="invalid-feedback">Une description courte.</div>
                </div>

                <label for="img_url">L'url de l'image de la bannière.</label>
                <div class="input-group mb-2 has-validation">
                  <input id="img_url" type="text"
                         class="form-control" v-model="tenant.img_url" aria-label="Prénom pour l'adhésion" required>
                  <div class="invalid-feedback">Bannière.</div>
                </div>

                <label for="logo_url">L'url de l'image du logo.</label>
                <div class="input-group mb-2 has-validation">
                  <input id="logo_url" type="text"
                         class="form-control" v-model="tenant.logo_url" aria-label="Prénom pour l'adhésion" required>
                  <div class="invalid-feedback">Logo.</div>
                </div>

                <!-- conditions -->
                <div class="input-group mb-2 has-validation">
                  <div class="form-check form-switch position-relative mt-2">
                    <input id="read-conditions" class="form-check-input" type="checkbox" required
                           @click="checkConditions()" :checked="tenant.readConditions">
                    <label class="form-check-label text-dark" for="read-conditions">
                      j'ai pris connaissance des <a class="text-info" @click="goStatus()">conditions générales</a>
                    </label>
                    <div class="invalid-feedback position-absolute">
                      Conditions non acceptées.
                    </div>
                  </div>
                </div>

                <p class="text-justify">Un mail de validation sera envoyé dés la procédure de création terminée. Pensez
                  à regarder
                  dans vos spams si non reçu !</p>

                <div class="text-center">
                  <button type="submit" class="btn btn-round bg-gradient-info btn-lg w-100 mt-4 mb-0">Valider</button>
                </div>

              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'
import {useRoute} from 'vue-router'

const route = useRoute()
const accStripe = route.params.accstripe

// asset
import communecterLogo from '@/assets/img/communecterLogo_31x28.png'

// const {adhesion} = useLocalStore()
const domain = `${location.protocol}//${location.host}`
const {tenant, loading, error} = storeToRefs(useAllStore())

function goStatus() {
  window.open("https://tibillet.org", "_blank")
}

function inputFocus(id) {
  document.querySelector(`#${id}`).focus()
}

function checkConditions() {
  tenant.value.readConditions = document.querySelector(`#read-conditions`).checked
}

// function getDomainName(hostName)
// {
//     return hostName.substring(hostName.lastIndexOf(".", hostName.lastIndexOf(".") - 1) + 1);
// }

function SubmitTenant(data) {
  // console.log(`-> fonc postAdhesionModal !`)
  const domain = `${location.protocol}//${location.host}`
  const apiMemberShip = `/api/place/`
  const options = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'/*,
      'Token': window.accessToken*/
    },
    body: JSON.stringify(data)
  }

  console.log('options =', JSON.stringify(data, null, 2))
  // init étape adhésion stripe
  // setEtapeStripe('attente_stripe_adhesion')

  loading.value = true
  fetch(domain + apiMemberShip, options).then(response => {
    console.log('response =', response)
    if (response.status !== 201) {
      loading.value = false
      emitter.emit('modalMessage', {
        titre: 'Erreur',
        contenu: response.json()
      })
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    // console.log(retour)
    console.log("domain : ", retour.domain)
    // const domain = `${location.protocol}//${location.host}`
    window.location = (`https://${retour.domain}`);
  }).catch(function (error) {
    console.log(error)
  })
}

function ValidateTenant(event) {
  console.log('-> fonc ValidateTenant !!')

  // efface tous les messages d'invalidité
  document.querySelector(`#read-conditions`).parentNode.querySelector(`.invalid-feedback`).style.display = 'none'
  const msgInvalides = event.target.querySelectorAll('.invalid-feedback')
  for (let i = 0; i < msgInvalides.length; i++) {
    msgInvalides[i].style.display = 'none'
  }


  // vérification status
  const satusElement = document.querySelector(`#read-conditions`)
  if (satusElement.checked === false) {
    const warningElement = satusElement.parentNode.querySelector(`.invalid-feedback`)
    warningElement.style.display = 'block'
    warningElement.style.top = '20px'
    warningElement.style.left = '-6px'
  }
  if (satusElement.checked === true) {
    if (event.target.checkValidity() === true) {
      // formulaire valide
      // console.log('-> valide !')

      // ferme le modal
      // const elementModal = document.querySelector('#modal-onboard-return')
      // const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
      // modal.hide()

      // POST adhésion
      SubmitTenant({
        organisation: tenant.value.organisation,
        short_description: tenant.value.short_description,
        img_url: tenant.value.img_url,
        logo_url: tenant.value.logo_url,
        categorie: "S",
        stripe_connect_account: accStripe,
      })
    } else {
      // formulaire non valide
      console.log('-> pas valide !')
      // scroll vers l'entrée non valide et affiche un message
      const elements = event.target.querySelectorAll('input')
      for (let i = 0; i < elements.length; i++) {
        const element = elements[i]
        if (element.checkValidity() === false) {
          // console.log('element = ', element)
          element.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
          element.parentNode.querySelector('.invalid-feedback').style.display = 'block'
          break
        }
      }
    }
  }
}

</script>

<style scoped>

/*.no-click {*/
/*    opacity: 0.2;*/
/*    pointer-events: none;*/
/*}*/

.h-44px {
  height: 44px;
}

.communecter-logo {
  height: 26px;
  width: auto;
}
</style>