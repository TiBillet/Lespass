<template>
    <fieldset class="col shadow-sm p-3 mb-5 bg-body rounded">
      <legend>
        <h3 class="font-weight-bolder text-info text-gradient align-self-start">Email</h3>
      </legend>
      <!-- email -->
      <div class="mb-2">
        <div class="input-group has-validation">
          <input id="profil-email" :value="profil.email" type="email"
                 @change="updateProfil('email', $event.target.value)"
                 pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$"
                 class="form-control card-email-input" placeholder="Email" required>
          <div class="invalid-feedback">
            Merci de renseigner une adresse email valide.
          </div>
        </div>
      </div>

      <!-- confirme email -->
      <div class="mb-2">
        <div class="input-group has-validation">
          <input id="profil-confirme-email" :value="profil.confirmeEmail" type="email"
                 @change="updateProfil('confirmeEmail', $event.target.value)"
                 pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" class="form-control card-email-input"
                 placeholder="Confirmer email" required>
          <div class="invalid-feedback">
            Merci de renseigner une adresse email valide et identique.
          </div>
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

// vue
import {ref, onMounted, onUpdated} from 'vue'

// store
import {useStore} from '@/store'

const props = defineProps({
  indexMemo: String,
  defaultEmail: String
})
const store = useStore()

// mémorise par défaut
let record = true

console.log('props =', JSON.stringify(props, null, 2))

let profil = ref({})
const dataInit = {
  email: props.defaultEmail,
  confirmeEmail: props.defaultEmail
}

console.log('dataInit =', JSON.stringify(dataInit, null, 2))

// mémorise le composant dans le store ou la variable globale window
try {
  if (props.indexMemo === '' || props.indexMemo === undefined) {
    throw new Error(`Erreur index memo vide !`)
  }
  if (props.indexMemo !== '') {
    // init de base pour la persistance de tous les composants "CardEmail" dans le store
    if (store.memoComposants['CardEmail'] === undefined) {
      store.memoComposants['CardEmail'] = {}
    }
    // console.log('3 -> store.memoComposants.CardEmail =', store.memoComposants.CardEmail)
    // init de l'instance de clef "props.indexMemo"
    if (store.memoComposants.CardEmail[props.indexMemo] === undefined) {
      // console.log('Mémorisation initiale')
      store.memoComposants.CardEmail[props.indexMemo] = dataInit
      store.memoComposants.CardEmail[props.indexMemo]['initDate'] = new Date().toLocaleString()
      profil.value = dataInit
    } else {
      // instance existante
      profil.value = store.memoComposants.CardEmail[props.indexMemo]
      // console.log('Mémorisation existante')
    }
  }
} catch (erreur) {
  record = false
  // console.log(erreur)
  console.log('Mémorisation du composant impossible')
  // instance sans mémorisation dans le store
  profil.value = dataInit
  // utilisation hors local storage
  if (window.store === undefined) {
    window.store = {}
  }
  if (window.store['CardEmail'] === undefined) {
    window.store['CardEmail'] = dataInit
    profil.value = dataInit
  } else {
    profil.value = window.store.CardEmail
  }
}

function updateProfil(key, value) {
  console.log(key + " = " + value)
  if (record === true) {
    profil.value[key] = value
  }
}

emitter.on('emailChange', (value) => {
  profil.value.email = value
  profil.value.confirmeEmail = value
})

</script>

<style scoped>

</style>