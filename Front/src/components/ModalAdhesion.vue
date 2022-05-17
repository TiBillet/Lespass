<template>
  <!-- modal adhésion -->
  <div v-if="Object.entries(place).length > 0" class="modal fade" id="modal-form-adhesion" tabindex="-1" role="dialog"
       aria-labelledby="modal-form-adhesion"
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 d-flex align-items-center">
              <h3 class="font-weight-bolder text-info text-gradient align-self-start w-85">Adhésion</h3>
              <div v-if="modal.status === 'input'" class="d-flex align-items-center modal-click-info" @click="goStatus()">
                <span>status</span>
                <i class="fas fa-question mb-1"></i>
              </div>
            </div>
            <div class="card-body">
              <!-- error -->
              <div v-if="modal.status === 'error'" class="bg-light"
                   :style="`width: ${modal.size.width}px; height: ${modal.size.height}px;`">
                <h1>Erreur !</h1>
                <div class="text-warning">
                  {{ modal.message }}
                </div>
              </div>
              <!-- loadding -->
              <div v-if="modal.status === 'loading'"
                   class="position-relative d-flex justify-content-center align-items-center bg-light"
                   :style="`width: ${modal.size.width}px; height: ${modal.size.height}px;`">
                <h1>En attente !</h1>
                <div class="position-absolute d-flex justify-content-center align-items-center"
                     :style="`width: ${modal.size.width}px; height: ${modal.size.height}px;`">
                  <div class="spinner-border text-success" role="status" style="width: 10rem; height: 10rem;"></div>
                </div>
              </div>
              <!-- formulaire -->
              <form v-if="modal.status === 'input'" @submit.prevent="validerAdhesion($event)" novalidate>

                <!-- prix -->
                <div class="input-group mb-2 has-validation">
                  <div :id="`adesion-modal-price-parent${index}`" class="col form-check mb-3"
                       v-for="(price, index) in getPricesAdhesion()" :key="index">
                    <input v-if="index === 0" :value="price.uuid" v-model="adhesion.uuidPrix"
                           class="form-check-input input-adesion-modal-price" type="radio"
                           name="prixAdhesionModal" :id="`uuidadhesionmodalpriceradio${index}`"
                           required>
                    <input v-else :value="price.uuid" v-model="adhesion.uuidPrix"
                           class="form-check-input input-adesion-modal-price" type="radio"
                           name="prixAdhesionModal" :id="`uuidadhesionmodalpriceradio${index}`">
                    <label class="form-check-label" :for="`uuidadhesionmodalpriceradio${index}`">{{ price.name }} - {{
                        price.prix
                      }}€</label>
                    <div v-if="index === 0" class="invalid-feedback">
                      Un tarif ?
                    </div>
                  </div>
                </div>

                <!-- nom -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" @click="inputFocus('adhesion-nom')">Nom</span>
                  <input id="adhesion-nom" v-model="adhesion.lastName" type="text"
                         class="form-control" aria-label="Nom pour l'adhésion" required>
                  <div class=" invalid-feedback">Un nom svp !
                  </div>
                </div>

                <!-- prénom -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" @click="inputFocus('adhesion-prenom')">Prénom</span>
                  <input id="adhesion-prenom" v-model="adhesion.firstName" type="text"
                         class="form-control" aria-label="Prénom pour l'adhésion" required>
                  <div class="invalid-feedback">Un prénom svp !</div>
                </div>

                <!-- email -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" @click="inputFocus('adhesion-email')">Email</span>
                  <input id="adhesion-email" v-model="adhesion.email" type="email"
                         pattern="[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}$" class="form-control" required>
                  <div class="invalid-feedback">
                    Une adresse email valide svp !
                  </div>
                </div>

                <!-- code postal -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" @click="inputFocus('adhesion-code-postal')">Code postal</span>
                  <input id="adhesion-code-postal" v-model="adhesion.postalCode"
                         type="number" class="form-control" aria-label="Code postal" required>
                  <div class="invalid-feedback">Code postal svp !</div>
                </div>

                <!-- téléphone -->
                <div class="input-group has-validation">
                  <span class="input-group-text" @click="inputFocus('adhesion-tel')">Fixe ou Mobile</span>
                  <input id="adhesion-tel" v-model="adhesion.phone" type="tel"
                         class="form-control" pattern="^[0-9-+\s()]*$"
                         aria-label="Fixe ou Mobile" required>
                  <div class="invalid-feedback">Un numéro de téléphone svp !</div>
                </div>
                <p class="mb-2">Non obligatoire, uniquement utile pour vous envoyer les confirmations d'achats."</p>

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
console.log('-> ModalAdhesion.vue !')

// vue
import {ref} from 'vue'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'
import {useLocalStore} from '@/stores/local'

// routes
import {useRouter} from 'vue-router'

// obtenir prix adhesion
const {place} = storeToRefs(useAllStore())
// stockage adhesion en ocal
const {adhesion} = storeToRefs(useLocalStore())

const router = useRouter()

const modal = ref({
  status: 'input',
  size: {},
  message: ''
})

function getPricesAdhesion() {
  const prices = place.value.membership_products.find(product => product.categorie_article === 'A').prices

  console.log('prices =', prices)
  return prices
}

function inputFocus(id) {
  document.querySelector(`#${id}`).focus()
}

function goStatus() {
  // ferme le modal
  const elementModal = document.querySelector('#modal-form-adhesion')
  const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
  modal.hide()
  // aller au status
  router.push('/status')
}


function postAdhesionModal(data) {
  console.log(`-> fonc postAdhesionModal !`)
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

  fetch(domain + apiMemberShip, options).then(response => {
    console.log('response =', response)
    if (response.status !== 201) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    // init étape adhésion stripe
    adhesion.value.status = 'attente_stripe'
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

function validerAdhesion(event) {
  console.log('-> fonc validerAdhesion !!')

  // efface tous les messages d'invalidité
  const msgInvalides = event.target.querySelectorAll('.invalid-feedback')
  for (let i = 0; i < msgInvalides.length; i++) {
    msgInvalides[i].style.display = 'none'
  }

  if (event.target.checkValidity() === true) {
    // formulaire valide
    // console.log('-> valide !')
    const modalForm = document.querySelector(`#modal-form-adhesion form`).getBoundingClientRect()

    modal.value = {
      status: 'loading',
      size: {
        width: modalForm.width,
        height: modalForm.height
      }
    }

    console.log('test adhesion =', adhesion.value)
    postAdhesionModal({
      email: adhesion.value.email,
      first_name: adhesion.value.firstName,
      last_name: adhesion.value.lastName,
      phone: adhesion.value.phone,
      postal_code: adhesion.value.postalCode,
      adhesion: adhesion.value.uuidPrix
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


/*
// vue
import {ref} from 'vue'
import {useRouter} from 'vue-router'

// store
import {useStore} from '@/store'

// myStore
import {storeLocalGet, storeLocalSet} from '@/storelocal'

// api
import {postAdhesionModal} from '@/api'

const store = useStore()

// init store local
// const storeLocal = new StoreLocal()

const router = useRouter()

let prices = ref([])

// get prices
try {
  emitter.emit('statusLoading', true)
  const apiLieu = `/api/here/`
  const domain = `${location.protocol}//${location.host}`
  fetch(domain + apiLieu).then((response) => {
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then((retour) => {
    store.place = retour
    prices.value = store.place.membership_products.filter(article => article.categorie_article === 'A')[0].prices
    console.log('prices.value =', prices.value)
  })
  emitter.emit('statusLoading', false)
} catch (erreur) {
  // console.log('Store, place, erreur:', erreur)
  emitter.emit('message', {
    tmp: 4,
    typeMsg: 'danger',
    contenu: `Chargement lieu, erreur: ${erreur}`
  })
}


// console.log('props.prices = ', props.prices)

let adhesionFormModal = ref({
  email: storeLocalGet('email'),
  firstName: '',
  lastName: '',
  phone: '',
  postalCode: '',
  uuidPrix: ''
})




emitter.on('emailChange', (value) => {
  try {
    adhesionFormModal.value.email = value
  } catch (erreur) {
    console.log('-> ModalAdhesion.vue, erreur:', erreur)
  }
})
*/
</script>

<style scoped>
.modal-click-info {
  cursor: pointer;
}
</style>