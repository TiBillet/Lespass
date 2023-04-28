<template>
  <!-- modal formulaire adhésion -->
  <div class="modal fade" id="modal-form-adhesion" tabindex="-1" role="dialog"
       aria-labelledby="modal-form-adhesion" data-mdb-backdrop="true" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 d-flex flex-column align-items-star">
              <h3 class="font-weight-bolder text-info text-gradient align-self-start w-85">
                {{ getPartialDataAdhesion(productUuid).name }}</h3>
              <h5 style="white-space: pre-line">{{
                  getPartialDataAdhesion(productUuid).short_description
                }}</h5>
            </div>
            <div class="card-body">
              <!-- formulaire -->
              <form @submit.prevent="validerAdhesion($event)" novalidate>

                <!-- conditions -->
                <div class="input-group mb-2 has-validation">
                  <div class="form-check form-switch position-relative">
                    <div>
                      <input id="read-conditions" class="form-check-input" type="checkbox" required
                             @click="checkConditions()" :checked="adhesion.readConditions">
                      <label v-if="getPartialDataAdhesion(productUuid).categorie_article === 'A'"
                             class="form-check-label text-dark" for="read-conditions">
                        j'ai pris connaissance des <a class="text-info" @click="goStatus()">status et du réglement
                        intérieur de l'association.</a>
                      </label>
                      <label v-else class="form-check-label text-dark" for="read-conditions">
                        j'ai pris connaissance des <a class="text-info" @click="goStatus()">CGU/CGV.</a>
                      </label>
                    </div>
                    <div class="invalid-feedback position-absolute">
                      Conditions non acceptées.
                    </div>
                  </div>
                </div>

                <!-- prix -->
                <div class="input-group mb-2 has-validation">
                  <div :id="`adesion-modal-price-parent${index}`" class="col form-check mb-2"
                       v-for="(price, index) in getPricesAdhesion(productUuid)" :key="index">
                    <input v-if="index === 0" :value="price.uuid" v-model="adhesion.adhesion"
                           class="form-check-input input-adesion-modal-price" type="radio"
                           name="prixAdhesionModal" :id="`uuidadhesionmodalpriceradio${index}`"
                           required>
                    <input v-else :value="price.uuid" v-model="adhesion.adhesion"
                           class="form-check-input input-adesion-modal-price" type="radio"
                           name="prixAdhesionModal" :id="`uuidadhesionmodalpriceradio${index}`">
                    <label class="form-check-label" :for="`uuidadhesionmodalpriceradio${index}`">
                      {{ price.name }} - {{ price.prix }}€
                    </label>
                    <div v-if="index === 0" class="invalid-feedback">
                      Merci de choisir un tarif.
                    </div>
                  </div>
                </div>

                <!-- nom -->
                <div class="input-group mb-2 has-validation">
                                    <span class="input-group-text"
                                          @click="inputFocus('adhesion-nom')">Nom ou Structure</span>
                  <input id="adhesion-nom" v-model="adhesion.last_name" type="text"
                         class="form-control" aria-label="Nom pour l'adhésion" required>
                  <div class=" invalid-feedback">Merci de remplir votre nom.</div>
                </div>

                <!-- prénom -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" @click="inputFocus('adhesion-prenom')">Prénom</span>
                  <input id="adhesion-prenom" v-model="adhesion.first_name" type="text"
                         class="form-control" aria-label="Prénom pour l'adhésion" required>
                  <div class="invalid-feedback">Merci de remplir votre prénom.</div>
                </div>


                <!-- email -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" @click="inputFocus('adhesion-email')">Email</span>
                  <input id="adhesion-email" v-model="adhesion.email" type="email"
                         pattern="[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}$"
                         class="form-control" required>
                  <div class="invalid-feedback">
                    Merci de remplir votre email.
                  </div>
                </div>

                <!-- code postal -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" @click="inputFocus('adhesion-code-postal')">Code postal</span>
                  <input id="adhesion-code-postal" v-model="adhesion.postal_code"
                         type="number" class="form-control" aria-label="Code postal" required>
                  <div class="invalid-feedback">Merci de remplir votre code postal.</div>
                </div>

                <!-- téléphone -->
                <!--                <p class="mb-2">Téléphone non obligatoire, mais utile pour vous envoyer les confirmations et la double authentification."</p>-->
                <div class="input-group has-validation">
                                    <span class="input-group-text"
                                          @click="inputFocus('adhesion-tel')">Fixe ou Mobile</span>
                  <input id="adhesion-tel" v-model="adhesion.phone" type="tel"
                         class="form-control" pattern="^[0-9-+\s()]*$"
                         aria-label="Fixe ou Mobile" required>
                  <div class="invalid-feedback">Merci de remplir votre numéro de téléphone.</div>
                </div>

                <!-- options checkbox -->
                <div v-if="getPartialDataAdhesion(productUuid).option_generale_checkbox.length > 0" class="mt-3">
                  <div v-for="(option, index) in getPartialDataAdhesion(productUuid).option_generale_checkbox"
                       :key="index" class="mb-1">
                    <div class="form-switch input-group has-validation">
                      <input class="form-check-input me-2 options-adhesion-to-unchecked" type="checkbox"
                             :id="`option-checkbox-adhesion${option.uuid}`">
                      <label class="form-check-label text-dark mb-0" :for="`option-checkbox-adhesion${option.uuid}`">
                        {{ option.name }}
                      </label>
                    </div>
                    <div class="ms-5">{{ option.description }}</div>
                    <!-- <div class="invalid-feedback">Choisisser une options !</div> -->
                  </div>
                </div>

                <!-- options radio -->
                <div v-if="getPartialDataAdhesion(productUuid).option_generale_radio.length > 0" class="mt-3">
                  <div v-for="(option, index) in getPartialDataAdhesion(productUuid).option_generale_radio"
                       :key="index" class="mb-2">
                    <div class="form-switch input-group has-validation ps-0">
                      <input class="form-check-input me-2 options-adhesion-to-unchecked" type="radio"
                             name="option-radio-name-adhesion"
                             :id="`option-radio-adhesion${index}`"
                             :data-uuid="option.uuid"
                             style="margin-left: 0;">
                      <label class="form-check-label text-dark mb-0" :for="`option-radio-adhesion${index}`">
                        {{ option.name }}
                      </label>
                    </div>
                    <div class="ms-5">{{ option.description }}</div>
                  </div>
                  <!-- <div class="invalid-feedback">Choisisser une options !</div> -->
                </div>


                <div class="text-center">
                  <p class="mb-2 mt-2">
                    Aucune de ces informations ne sont et ne seront utilisées pour du démarchage
                    commercial.
                    TiBillet est une solution libre et open-source qui prends soin de votre vie
                    privée.
                  </p>

                  <button type="submit" class="btn btn-round bg-gradient-info btn-lg w-100 mt-4 mb-0">
                    Valider
                  </button>
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
console.log('-> ModalMembershipForm.vue !')
import { onMounted } from 'vue'

// store
import { storeToRefs } from 'pinia'
import { useAllStore } from '@/stores/all'
import { useLocalStore } from '@/stores/local'

// routes
import { useRouter } from 'vue-router'

// obtenir data adhesion
const { place, adhesion, loading, error } = storeToRefs(useAllStore())
const { getPricesAdhesion, getPartialDataAdhesion } = useAllStore()

// stockage adhesion en local
let { setEtapeStripe } = useLocalStore()
const router = useRouter()

const props = defineProps({
  productUuid: String
})

function inputFocus (id) {
  document.querySelector(`#${id}`).focus()
}

function checkConditions () {
  adhesion.value.readConditions = document.querySelector(`#read-conditions`).checked
}

function goStatus () {
  const lien = getPartialDataAdhesion(props.productUuid).legal_link
  // console.log('-> goStatus, lien =', lien)
  if (lien !== null) {
    window.open(place.value.site_web, '_blank')
  }
}

function postAdhesionModal (data) {
  // console.log(`-> fonc postAdhesionModal !`)
  const domain = `${location.protocol}//${location.host}`
  const apiMemberShip = `/api/membership/`
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
  setEtapeStripe('attente_stripe_adhesion')

  loading.value = true
  fetch(domain + apiMemberShip, options).then(response => {
    console.log('response =', response)
    if (response.status !== 201) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    // redirection stripe formulaire paiement
    window.location = retour.checkout_url
  }).catch(function (error) {
    console.log('error =', error)
    const modalForm = document.querySelector(`#modal-form-adhesion form`).getBoundingClientRect()
    modal.value = {
      status: 'error',
      size: {
        width: modalForm.width,
        height: modalForm.height
      },
      message: error
    }
  })
}

function searchInvalidFeedbackElement (ele) {
  for (let i = 0; i < 3; i++) {
    const parent = ele.parentNode
    const eleInvF = parent.querySelector('.invalid-feedback')
    if (eleInvF !== null) {
      return eleInvF
    }
    ele = parent
  }
  return null
}

function validerAdhesion (event) {
  console.log('-> fonc validerAdhesion !!')

  // efface tous les messages d'invalidité
  //document.querySelector(`#read-conditions`).parentNode.querySelector(`.invalid-feedback`).style.display = 'none'
  const msgInvalides = event.target.querySelectorAll('.invalid-feedback')
  for (let i = 0; i < msgInvalides.length; i++) {
    msgInvalides[i].style.display = 'none'
  }

  // vérification status
  const satusElement = document.querySelector(`#read-conditions`)
  if (satusElement.checked === false) {
    const warningElement = satusElement.parentNode.parentNode.querySelector(`.invalid-feedback`)
    warningElement.style.display = 'block'
    warningElement.style.top = '20px'
    warningElement.style.left = '-6px'
  }
  if (satusElement.checked === true) {
    // console.log('event.target.checkValidity() =', event.target.checkValidity())
    if (event.target.checkValidity() === true) {
      // formulaire valide
      // console.log('-> valide !')

      // ferme le modal
      const elementModal = document.querySelector('#modal-form-adhesion')
      const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
      modal.hide()

      // récupération des options chekbox validés
      let optionsAdhesion = []
      for (const option of getPartialDataAdhesion(props.productUuid).option_generale_checkbox) {
        const inputCheckbox = document.querySelector(`#option-checkbox-adhesion${option.uuid}`)
        if (inputCheckbox.checked === true) {
          optionsAdhesion.push(option.uuid)
        }
      }

      // récupération de l'option radio validée
      const optionsRadio = document.querySelectorAll('input[name="option-radio-name-adhesion"]')
      for (const ele of optionsRadio) {
        const uuid = ele.getAttribute('data-uuid')
        if (ele.checked === true) {
          optionsAdhesion.push(uuid)
          break
        }
      }

      // POST adhésion
      postAdhesionModal({
        email: adhesion.value.email,
        first_name: adhesion.value.first_name,
        last_name: adhesion.value.last_name,
        phone: adhesion.value.phone,
        postal_code: adhesion.value.postal_code,
        adhesion: adhesion.value.adhesion,
        options: optionsAdhesion
      })
    } else {
      // formulaire non valide
      console.log('-> pas valide !')
      // scroll vers l'entrée non valide et affiche un message
      const elements = event.target.querySelectorAll('input')
      for (let i = 0; i < elements.length; i++) {
        const element = elements[i]
        if (element.checkValidity() === false) {
          element.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'center' })
          try {
            const invalidFeedbackElement = searchInvalidFeedbackElement(element)
            console.log('element = ', element)
            invalidFeedbackElement.style.display = 'block'
          } catch (e) {
            console.log(`Pas d'élément avec la class "invalid-feedback" !`)
          }
          break
        }
      }
    }
  }
}

</script>

<style scoped>
.modal-click-info {
  cursor: pointer;
}
</style>