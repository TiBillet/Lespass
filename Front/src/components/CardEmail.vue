<template>
  <fieldset class="col shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Email</h3>
    </legend>
    <!-- email -->
    <div class="input-group mb-2 has-validation">
      <span class="input-group-text" @click="inputFocus('profil-email')">Email</span>
      <input id="profil-email" :value="getEmail.email" type="email"
             @change.stop="updateEmail('email', $event.target.value)"
             pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$"
             class="form-control card-email-input" placeholder="Email" required>
      <div class="invalid-feedback">
        Merci de renseigner une adresse email valide.
      </div>
    </div>

    <!-- confirme email -->
    <div class="input-group mb-2 has-validation">
      <span class="input-group-text" @click="inputFocus('profil-confirme-email')">Confirmez l'email</span>
      <input id="profil-confirme-email" :value="getEmail.confirme" type="email"
             @change.stop="updateEmail('emailConfirme', $event.target.value)"
             pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$"
             class="form-control card-email-input" placeholder="Email" required>
      <div class="invalid-feedback">
        Merci de renseigner une adresse email valide et identique.
      </div>
    </div>

    <!-- message pour l'adresse email -->
    <div class="text-warning mb-0">
      Merci de bien vérifier votre adresse email afin de bien recevoir votre(vos) billet(s).
    </div>

  </fieldset>
</template>

<script setup>
console.log('-> CardEmail.vue !')

// store
import {useEventStore} from '@/stores/event'

const {getEmail, updateEmail} = useEventStore()

function inputFocus(id) {
  document.querySelector(`#${id}`).focus()
}
</script>

<style scoped>

</style>