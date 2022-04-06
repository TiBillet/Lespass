<template>
  <!-- modal adhésion -->
  <div class="modal fade" id="modal-form-adhesion" tabindex="-1" role="dialog"
       aria-labelledby="modal-form-adhesion"
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-gradient">Adhésion</h3>
            </div>
            <div class="card-body">
              <form @submit.prevent="validerAdhesion($event)" novalidate>

                <!-- prix -->
                <div class="input-group mb-2 has-validation">
                  <div :id="`adesion-modal-price-parent${index}`" class="col form-check mb-3"
                       v-for="(price, index) in prices" :key="index">
                    <input v-if="index === 0" :value="price.uuid" v-model="adhesionFormModal.uuidPrix"
                           class="form-check-input input-adesion-modal-price" type="radio"
                           name="prixAdhesionModal" :id="`uuidadhesionmodalpriceradio${index}`"
                           required>
                    <input v-else :value="price.uuid" v-model="adhesionFormModal.uuidPrix"
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
                  <span class="input-group-text">Nom</span>
                  <input v-model="adhesionFormModal.lastName" type="text"
                         class="form-control" aria-label="Nom pour l'adhésion">
                  <div class=" invalid-feedback">Un nom svp !
                  </div>
                </div>

                <!-- prénom -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text">Prénom</span>
                  <input v-model="adhesionFormModal.firstName" type="text"
                         class="form-control" aria-label="Prénom pour l'adhésion">
                  <div class="invalid-feedback">Un prénom svp !</div>
                </div>

                <!-- email -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text">Email</span>
                  <!-- <input v-model="adhesionFormModal.email" type="email"
                         pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" class="form-control" required> -->
                   <input v-model="adhesionFormModal.email" type="email"
                         pattern="[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}$" class="form-control" required>
                  <div class="invalid-feedback">
                    Une adresse email valide svp !
                  </div>
                </div>

                <!-- code postal -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text">Code postal</span>
                  <input v-model="adhesionFormModal.postalCode" id="adhesion-adresse"
                         type="number" class="form-control" aria-label="Code postal" required>
                  <div class="invalid-feedback">Code postal svp !</div>
                </div>

                <!-- téléphone -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text">Fixe ou Mobile</span>
                  <input v-model="adhesionFormModal.phone" type="tel"
                         class="form-control" pattern="^[0-9-+\s()]*$"
                         aria-label="Fixe ou Mobile" required>
                  <div class="invalid-feedback">Un numéro de téléphone svp !</div>
                </div>

                <!-- date de naissance -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text">Date de naissance</span>
                  <input type="date" v-model="adhesionFormModal.birthDate" pattern="^[0-9-+\s()]*$"
                         aria-label="Date de naissance" required>
                  <div class="invalid-feedback">Date de naissance svp !</div>
                </div>

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
// myStore
import {StoreLocal} from '@/divers'

// api
import {postAdhesionModal} from '@/api'

const storeLocal = StoreLocal.use('localStorage', 'Tibilet-identite')

// attributs/props
const props = defineProps({
  prices: Object
})

// console.log('props.prices = ', props.prices)

let adhesionFormModal = {
  email: storeLocal.email,
  firstName: '',
  lastName: '',
  phone: '',
  postalCode: '',
  birthDate: '',
  uuidPrix: ''
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
    console.log('-> valide !')
    postAdhesionModal({
      email: adhesionFormModal.email,
      first_name: adhesionFormModal.firstName,
      last_name: adhesionFormModal.lastName,
      phone: adhesionFormModal.phone,
      postal_code: adhesionFormModal.postalCode,
      birth_date: adhesionFormModal.birthDate,
      adhesion: adhesionFormModal.uuidPrix
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
</script>

<style scoped>

</style>