<template>
  <fieldset class="col shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Email</h3>
    </legend>
    <!-- email -->
    <h4 v-if="getIsLogin" role="heading" aria-label="Email de l'utilisateur connecté.">{{ email === '' ? getEmail :
      email }}</h4>
    <div v-else>
      <!--
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" v-focuselement="'card-email-email'">Email</span>
        <input id="card-email-email" type="text" :value="email === '' ? getEmail : email" @input="emitValue($event)"
          @change="emitValue($event)" class="form-control card-email-input" placeholder="Email" role="textbox"
          aria-label="Entrer un email." required />
        <div class="invalid-feedback" role="heading" aria-label="Merci de renseigner une adresse email valide.">
          Merci de renseigner une adresse email valide.
        </div>
       
      -->
      <div class="input-group input-group-dynamic mb-4 has-validation">
        <label class="form-label" for="card-email-email">Email</label>
        <input type="email" class="form-control" id="card-email-email" aria-describedby="basic-addon3"
          :value="email === '' ? getEmail : email" @input="emitValue($event)" @change="emitValue($event)"
          @focusin="focused($event)" @focusout="defocused($event)" role="textbox" aria-label="Entrer un email." required>
        <div class="invalid-feedback" role="heading" aria-label="Merci de renseigner une adresse email valide.">
          Merci de renseigner une adresse email valide.
        </div>
      </div>



      <!-- confirme email -->
      <div class="input-group input-group-dynamic mb-4 has-validation">
        <label class="form-label" for="card-email-confirm-email">Confirmez l'email</label>
        <input id="card-email-confirm-email" type="text" :value="confirmEmail" @keyup="validateEmail($event)"
          @change="validateEmail($event)" class="form-control card-email-input" required @focusin="focused($event)"
          @focusout="defocused($event)" role="textbox" aria-label="Confirmer email entré." />
        <div class="invalid-feedback" role="heading"
          aria-label="Merci de renseigner une adresse email valide et identique.">
          Merci de renseigner une adresse email valide et identique.
        </div>
      </div>

      <!-- message pour l'adresse email -->
      <div class="text-warning mb-0">
        Merci de bien vérifier votre adresse email afin de bien recevoir votre(vos) billet(s).
      </div>
    </div>
  </fieldset>
</template>

<script setup>
console.log('-> CardEmail.vue !')
// store
import { useSessionStore } from '@/stores/session'
import '../assets/js/material-kit-2/material-kit.js'



const emit = defineEmits(['update:email'])
const props = defineProps({
  email: String,
  emailModifiers: { default: () => ({}) }
})

// state
const { getIsLogin, getEmail } = useSessionStore()

let confirmEmail = ''

function validateEmail(event) {
  const ele = event.target
  let value = ele.value
  event.target.setAttribute('type', 'text')
  const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/
  if (value.match(re) === null) {
    event.target.parentNode.querySelector('.invalid-feedback').style.display = 'block'
  } else {
    event.target.parentNode.querySelector('.invalid-feedback').style.display = 'none'
  }
}

function emitValue(e) {
  if (props.emailModifiers.checkemail) {
    validateEmail(e)
  }
  emit('update:email', e.target.value)
}


function focused(evt) {
  evt.target.parentNode.classList.add('is-focused')

}

function defocused(evt) {
  const input = evt.target
  const parent = input.parentNode
  parent.classList.remove('is-focused')
  if (input.value != "") {
    parent.classList.add('is-filled');
  }
}


/*
// on key up
if (this.value != "") {
        this.parentElement.classList.add('is-filled');
      } else {
        this.parentElement.classList.remove('is-filled');
      }

*/
</script>

<style></style>