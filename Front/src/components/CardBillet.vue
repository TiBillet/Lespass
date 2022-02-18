<template>
  <form @submit.prevent="goValiderAchats($event)" class="needs-validation" novalidate>
    <!-- email -->
    <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
      <legend>Email</legend>
      <div class="mb-2">
        <div class="input-group has-validation">
          <input v-model="store.state.formulaireBillet[uuidEvent].email" type="email"
                 pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$"
                 class="form-control" placeholder="Adresse" required @keyup="majFormulaireBillet($event, 'email')">
          <div class="invalid-feedback">
            Une adresse email valide svp !
          </div>
        </div>
      </div>

      <div class="mb-2">
        <div class="input-group has-validation">
          <input id="email-confirmation" v-model="store.state.formulaireBillet[uuidEvent].confirmeEmail"
                 type="email"
                 pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" class="form-control"
                 placeholder="Confirmer adresse" required @change="majFormulaireBillet($event, 'confirmeEmail')">
          <div class="invalid-feedback">
            Une adresse email valide et identique svp !
          </div>
        </div>
      </div>

      <!-- message pour l'adresse email -->
      <div class="text-warning mb-0">
        Cette adresse email vous permet de recevoir votre(vos) billet(s),
        si celle-ci comporte une erreur vous n'aurez pas votre(vos) billet(s).
      </div>
      <!-- attention adresse email -->
      <div class="col-md-12">
        <div class="form-check form-switch">
          <input v-model="attentionEmail" class="form-check-input"
                 type="checkbox" id="valid-email"
                 @change="majFormulaireBillet($event, 'attentionEmail')" required>
          <label class="form-check-label text-dark" for="valid-email">Prise en compte du message
            si-dessus. {{ store.state.formulaireBillet[uuidEvent].attentionEmail }}</label>
          <div class="invalid-feedback">La prise en compte doit être activée, svp !</div>
        </div>
      </div>
    </fieldset>

    <!-- Position -->
    <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
      <legend>Position</legend>
      <div class="d-flex flex-row">
        <div class="form-check">
          <input value="fosse" id="position1" class="form-check-input" type="radio"
                 v-model="store.state.formulaireBillet[uuidEvent].position"
                 @change="majFormulaireBillet($event, 'position')">
          <label class="form-check-label" for="position1">Fosse</label>
          <div class="invalid-feedback">Position, svp !</div>
        </div>
        <div class="form-check ms-4">
          <input value="gradin" id="position2" class="form-check-input" type="radio"
                 v-model="store.state.formulaireBillet[uuidEvent].position"
                 @change="majFormulaireBillet($event, 'position')">
          <label class="form-check-label" for="position2">Gradin</label>
          <div class="invalid-feedback">Position, svp !</div>
        </div>

      </div>
    </fieldset>

    <!-- adhésion -->
    <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
      <legend>Adhésion</legend>
      <div class="form-check form-switch">
        <input v-model="adhesion" class="form-check-input" type="checkbox" id="etat-adhesion"
               @change="majFormulaireBillet($event, 'adhesion')">
        <label class="form-check-label text-dark" for="etat-adhesion">Prendre une adhésion
          associative.</label>
      </div>
      <div v-if="adhesion">
        <!-- nom -->
        <div class="input-group mb-2 has-validation">
          <input :value="store.state.formulaireBillet[uuidEvent].adhesionInfos.nom" type="text"
                 class="form-control"
                 placeholder="Nom" aria-label="Nom pour l'adhésion" required
                 @keyup="majFormulaireBillet($event, 'adhesionInfos.nom')">
          <div class="invalid-feedback">Un nom svp !</div>
        </div>
        <!-- prénom -->
        <div class="input-group mb-2 has-validation">
          <input :value="store.state.formulaireBillet[uuidEvent].adhesionInfos.prenom" type="text"
                 id="adhesion-prenom" class="form-control"
                 placeholder="Prénom" aria-label="Prénom pour l'adhésion" required
                 @keyup="majFormulaireBillet($event, 'adhesionInfos.prenom')">
          <div class="invalid-feedback">Un prénom svp !</div>
        </div>
        <!-- adresse -->
        <div class="input-group mb-2 has-validation">
          <input :value="store.state.formulaireBillet[uuidEvent].adhesionInfos.adresse" id="adhesion-adresse"
                 type="text"
                 class="form-control" placeholder="Adresse" aria-label="Adresse pour l'adhésion" required
                 @keyup="majFormulaireBillet($event, 'adhesionInfos.adresse')">
          <div class="invalid-feedback">Une adresse svp !</div>
        </div>
        <!-- téléphone -->
        <div class="input-group mb-2 has-validation">
          <input :value="store.state.formulaireBillet[uuidEvent].adhesionInfos.tel" type="tel"
                 class="form-control"
                 placeholder="Fixe ou Mobile" pattern="^[0-9-+\s()]*$"
                 aria-label="Adresse pour l'adhésion" required
                 @keyup="majFormulaireBillet($event, 'adhesionInfos.tel')">
          <div class="invalid-feedback">Un numéro de téléphone svp !</div>
        </div>

      </div>

    </fieldset>

    <BilletInputs :data-product="dataProduct" :uuid-event="uuidEvent"/>
    <div class="col-md-12 col-lg-9">
      <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
    </div>

  </form>
</template>

<script setup>
console.log('-> CardBillet.vue')

// vue
import {useStore} from 'vuex'
import {ref} from 'vue'

// composant
import BilletInputs from './BilletInputs.vue'

const testc = false

const store = useStore()
// attributs/props
const props = defineProps({
  dataProduct: Object,
  uuidEvent: String
})

let adhesion = ref(store.state.formulaireBillet[props.uuidEvent].adhesion)
let attentionEmail = ref(store.state.formulaireBillet[props.uuidEvent].attentionEmail)
console.log('props.dataProduct =', props.dataProduct)


function majFormulaireBillet(event, sujet) {
  console.log('-> majFormulaireBillet')
  let valeur = event.target.value
  if (sujet === 'attentionEmail') {
    valeur = attentionEmail.value
  }
  if (sujet === 'adhesion') {
    valeur = adhesion.value
  }
  store.commit('majFormulaireBillet', {uuidEvent: props.uuidEvent, sujet: sujet, valeur: valeur})
}


function goValiderAchats(event) {
  emitter.emit("goValiderAchat", event.target)
}
</script>

<style scoped>

</style>