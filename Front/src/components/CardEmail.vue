<template>
  <fieldset class="col shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Email</h3>
    </legend>
    <!-- email -->
    <div class="input-group mb-2 has-validation">
      <span class="input-group-text" v-focuselement="'card-email-email'">Email</span>
      <input id="card-email-email" type="text" :value="email" @input="emitValue" class="form-control card-email-input"
             placeholder="Email"
             required/>
      <div class="invalid-feedback">
        Merci de renseigner une adresse email valide.
      </div>
    </div>
    <!-- confirme email -->
    <div class="input-group mb-2 has-validation">
      <span class="input-group-text" v-focuselement="'card-email-confirm-email'">Confirmez l'email</span>
      <input id="card-email-confirm-email" type="text" :value="confirmEmail" @input="validateEmail($event)"
             class="form-control card-email-input" placeholder="Email"
             required/>
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

const emit = defineEmits(['update:email'])
const props = defineProps({
  email: String,
  emailModifiers: { default: () => ({}) }
})

let confirmEmail = ''

function validateEmail (event) {
  let value = event.target.value
  const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/
  if (value.match(re) === null) {
    event.target.setCustomValidity("Invalid field.")
  } else {
    event.target.setCustomValidity("")
  }
}

function emitValue (e) {
  if (props.emailModifiers.checkemail) {
    validateEmail(e)
  }
  emit('update:email', e.target.value)
}
</script>

<style scoped>

</style>