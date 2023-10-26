<template>
  <!-- modal formulaire adhésion -->
  <div id="modal-form-adhesion" class="modal fade" tabindex="-1" role="dialog" aria-labelledby="modal-form-adhesion"
    data-mdb-backdrop="true" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 d-flex flex-column align-items-star">
              <h3 class="font-weight-bolder text-info text-gradient align-self-start w-85">
                {{
                  getMembershipData(props.productUuid)
                    .name
                }}</h3>
              <h5 style="white-space: pre-line">{{
                getMembershipData(props.productUuid)
                  .short_description
              }}</h5>
            </div>
            <div class="card-body">
              <!-- formulaire -->
              <form id="form-valid-membership" class="needs-validation"
                @submit.prevent="validerAdhesion($event, props.productUuid)" novalidate role="form"
                aria-label="Formulaire d'adhésion">
                <!-- conditions -->
                <div class="input-group mb-2 has-validation">
                  <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox"
                      v-model="getFormMembership(props.productUuid).readConditions" true-value="true" false-value="false"
                      required role="checkbox" aria-labelledby="statuts et règlement intérieur de l'association"
                      :class="getFormMembership(props.productUuid).readConditions === 'true' ? 'bg-success' : ''" />
                    <label class="form-check-label text-dark" for="read-conditions">
                      <span>j'ai pris connaissance des </span>
                      <span v-if="getMembershipData(props.productUuid).categorie_article === 'A'">
                        <a v-if="getMembershipData(props.productUuid).legal_link !== null" class="text-info"
                          @click="goStatus()">statuts et du règlement intérieur de l'association.</a>
                        <span v-else>statuts et du règlement intérieur de l'association</span>
                      </span>
                      <span v-else>
                        <a v-if="getMembershipData(props.productUuid).legal_link !== null" class="text-info"
                          @click="goStatus()">CGU/CGV.</a>
                        <span v-else>CGU/CGV.</span>
                      </span>
                    </label>
                    <div class="invalid-feedback" role="heading" aria-label="Conditions non acceptées.">Conditions non
                      acceptées.</div>
                  </div>
                </div>

                <!-- prix -->
                <InputRadio :data-radio="convertForInputRadio()" v-model="getFormMembership(props.productUuid).uuidPrice"
                  msg-error="Tarif SVP" validation="true" />

                <!-- nom -->
                <InputMd id="adhesion-nom" label="Nom ou Structure" msg-role="Nom pour l'adhésion."
                  msg-error="Merci de remplir votre nom." v-model="getFormMembership(props.productUuid).last_name"
                  class="mt-3" validation="true"/>

                <!--prénom -->
                <InputMd id="adhesion-prenom" label="Prénom" msg-role="Prénom pour l'adhésion."
                  msg-error="Merci de remplir votre prénom." v-model="getFormMembership(props.productUuid).first_name"
                  class="mt-3" validation="true"/>

                <!-- email -->
                <InputMd type="email" id="adhesion-email" label="Email" msg-role="Email pour l'adhésion."
                  msg-error="Merci de remplir votre email." v-model="getFormMembership(props.productUuid).email"
                  class="mt-3" validation="true" @keyup="validateEmail($event)"/>

                <!-- code postal -->
                <InputMd type="number" id="adhesion-code-postal" label="Code postal" msg-role="Code postal pour l'adhésion."
                  msg-error="Merci de remplir votre code postal." v-model="getFormMembership(props.productUuid).postal_code"
                  class="mt-3" validation="true" @keyup="formatNumber($event, 5)"/>

                <!-- téléphone -->
                <InputMd type="tel" id="adhesion-tel" label="Fixe ou Mobile" msg-role="Fixe ou Mobile pour l'adhésion."
                  msg-error="Merci de remplir votre numéro de téléphone." v-model="getFormMembership(props.productUuid).phone"
                  class="mt-3" validation="true" @keyup="formatNumber($event, 10)"/>

                <!-- options radio -->
                <InputRadio v-if="getMembershipOptionsRadio(props.productUuid).length > 0" :data-radio="convertMembershipOptionsRadio()" v-model="getFormMembership(props.productUuid).option_radio"
                  msg-error="Tarif SVP" msg-role="Choisir index radio " validation="true" />

                <!-- options checkbox -->
                <div v-if="getFormMembership(props.productUuid).option_checkbox.length > 0" class="mt-3">
                  <div v-for="(option, index) in getFormMembership(props.productUuid).option_checkbox" :key="index"
                    class="input-group mb-1">
                    <div class="form-check form-switch">
                      <input class="form-check-input me-2 options-adhesion-to-unchecked" type="checkbox"
                        :id="`option-checkbox-adhesion${option.uuid}`" v-model="option.checked" true-value="true"
                        false-value="false" role="checkbox" :aria-labelledby="`Choisir index checkbox ${index}.`"
                        :class="option.checked === 'true' ? 'bg-success' : ''">

                      <label class="form-check-label text-dark mb-0" :for="`option-checkbox-adhesion${option.uuid}`">
                        {{ option.name }}
                      </label>
                    </div>

                  </div>
                </div>

                <div class="text-center">
                  <p class="mb-2 mt-2">
                    Aucune de ces informations ne sont et ne seront utilisées pour du démarchage
                    commercial.
                    TiBillet est une solution libre et open-source qui prend soin de votre vie
                    privée.
                  </p>

                  <button type="submit" class="btn btn-round bg-gradient-info btn-lg w-100 mt-4 mb-0" role="button"
                    aria-label="valider formulaire adhésion">
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
import { log } from '../communs/LogError'
import { setLocalStateKey } from '../communs/storeLocal.js'

// component
import InputRadio from './InputRadio.vue'
import InputMd from './InputMd.vue'

// store
import { useSessionStore } from '../stores/session'

const sessionStore = useSessionStore()
const {
  getMembershipData,
  getMembershipPrices,
  getMembershipOptionsRadio,
  getFormMembership,
  setLoadingValue,
} = sessionStore

const props = defineProps({
  productUuid: String
})

const domain = `${window.location.protocol}//${window.location.host}`

function convertForInputRadio() {
  let options = []
  getMembershipPrices(props.productUuid).forEach(data => {
    options.push({
      label: data.name + " - " + data.prix + "€",
      value: data.uuid
    })
  })
  return { options, name: 'membership-prices' }
}

function convertMembershipOptionsRadio() {
  let options = []
  getMembershipOptionsRadio(props.productUuid).forEach(data => {
    options.push({
      label: data.name,
      value: data.uuid
    })
  })
  return { options, name: 'membership-options-radio'}
}

function validateEmail(event) {
  let value = event.target.value
  // event.target.setAttribute('type', 'text')
  const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/
  if (value.match(re) === null) {
    event.target.parentNode.querySelector('.invalid-feedback').style.display = 'block'
  } else {
    event.target.parentNode.querySelector('.invalid-feedback').style.display = 'none'
  }
}

function formatNumber(event, limit) {
  const element = event.target
  // obligation de changer le type pour ce code, si non "replace" ne fait pas "correctement" son travail
  element.setAttribute('type', 'text')
  let initValue = element.value
  element.value = initValue.replace(/[^\d+]/g, '').substring(0, limit)
  if (element.value.length < limit) {
    element.parentNode.querySelector('.invalid-feedback').style.display = 'block'
  } else {
    element.parentNode.querySelector('.invalid-feedback').style.display = 'none'
  }
}

function goStatus() {
  const lien = getMembershipData(props.productUuid).legal_link
  // console.log('-> goStatus, lien =', lien)
  if (lien !== null) {
    window.open(lien, '_blank')
  }
}

function inputFocus(id) {
  document.querySelector(`#${id}`).focus()
}

function postAdhesionModal(data, uuidForm) {
  // console.log(`-> fonc postAdhesionModal !`)
  const domain = `${location.protocol}//${location.host}`
  const apiMemberShip = `/api/membership/`
  const options = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  }

  // init étape adhésion stripe enregistrement en local(long durée)
  setLocalStateKey('stripeStep', { action: 'expect_payment_stripe_membership', uuidForm, nextPath: '/' })

  setLoadingValue(true)

  fetch(domain + apiMemberShip, options).then(response => {
    console.log('response =', response)
    if (response.status !== 201) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    setLoadingValue(false)
    // redirection stripe formulaire paiement
    window.location = retour.checkout_url
  }).catch(function (error) {
    setLoadingValue(false)
    log({ message: 'postAdhesionModal, /api/membership/, error:', error })
    emitter.emit('modalMessage', {
      titre: 'Erreur',
      typeMsg: 'danger',
      contenu: `Post /api/membership/ : ${error.message}`
    })
  })
}

async function validerAdhesion(event, uuidForm) {
  if (!event.target.checkValidity()) {
    event.preventDefault()
    event.stopPropagation()
  }
  event.target.classList.add('was-validated')
  if (event.target.checkValidity() === true) {
    console.log('validation ok!')

    // ferme le modal
    const elementModal = document.querySelector('#modal-form-adhesion')
    const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
    modal.hide()

    const form = JSON.parse(JSON.stringify(getFormMembership(uuidForm)))
    let options = []

    // récupération des options chekbox validés
    form.option_checkbox.forEach((opt) => {
      if (opt.checked === 'true') {
        options.push(opt.uuid)
      }
    })

    // récupération de l'option radio validée
    if (form.option_radio !== '') {
      options.push(form.option_radio)
    }

    // POST adhésion
    postAdhesionModal({
      email: form.email,
      first_name: form.first_name,
      last_name: form.last_name,
      phone: form.phone,
      postal_code: form.postal_code,
      adhesion: form.uuidPrice,
      options
    }, uuidForm)
  }
}
</script>

<style scoped>
.modal-click-info {
  cursor: pointer;
}
</style>