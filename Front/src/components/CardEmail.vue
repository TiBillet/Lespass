<template>
  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
    <legend>Email</legend>
    <!-- email -->
    <div class="mb-2">
      <div class="input-group has-validation">
        <input id="profil-email" :value="profil.email" type="email"
               @change="updateProfil('email', $event.target.value)"
               pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$"
               class="form-control card-email-input" placeholder="Adresse">
        <div class="invalid-feedback">
          Une adresse email valide svp !
        </div>
      </div>
    </div>

    <!-- confirme email -->
    <div class="mb-2">
      <div class="input-group has-validation">
        <input id="profil-confirme-email" :value="profil.confirmeEmail" type="email"
               @change="updateProfil('confirmeEmail', $event.target.value)"
               pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" class="form-control card-email-input"
               placeholder="Confirmer adresse" required>
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

        <input class="form-check-input"
               type="checkbox" id="card-email-valid"
               :checked="profil.activation"
               @change="updateProfil('activation', $event.target.checked)"
               required>
        <label class="form-check-label text-dark" for="card-email-valid">Prise en compte du message
          si-dessus.</label>
        <div class="invalid-feedback">La prise en compte doit être activée, svp !</div>
      </div>
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
  indexMemo: String
})
const store = useStore()

// mémorise par défaut
const record = true

// console.log('props =', JSON.stringify(props, null, 2))

let profil = ref({})
const dataInit = {
  email: "",
  confirmeEmail: "",
  activation: false
}

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

function updateComponent() {
  // emails différent, désactive le message "de prise d'attention sur la validité de l'émail"
  if (profil.value.confirmeEmail !== profil.value.email) {
    document.querySelector(`#card-email-valid`).removeAttribute('checked')
    profil.value.activation = false
  }

  // efface tous les erreurs de champ input non valide puisque connforme
  if (profil.value.confirmeEmail === profil.value.email) {
    const eles = document.querySelectorAll(`.card-email-input`)
    for (let i = 0; i < eles.length; i++) {
      const ele = eles[i]
      ele.parentNode.querySelector(`.invalid-feedback`).style.display = 'none'
    }
  }

  // efface le message d'erreur pour "la prise d'attention sur la validité de l'émail"
  if (profil.value.activation === true) {
    document.querySelector(`#card-email-valid`).parentNode.querySelector(`.invalid-feedback`).style.display = 'none'
  }
}

onMounted(() => {
  updateComponent()
})

onUpdated(() => {
  updateComponent()
})
</script>

<style scoped>

</style>