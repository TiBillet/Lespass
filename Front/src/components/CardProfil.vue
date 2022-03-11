<template>
  <!-- email -->
  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
    <legend>Email</legend>
    <div class="mb-2">
      <div class="input-group has-validation">
        <input :value="infos.email" type="email"
               @change="emitUpdateProfil('email', $event.target.value)"
               pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$"
               class="form-control" placeholder="Adresse" required>
        <div class="invalid-feedback">
          Une adresse email valide svp !
        </div>
      </div>
    </div>

    <div class="mb-2">
      <div class="input-group has-validation">
        <input id="email-confirmation" :value="infos.confirmeEmail" type="email"
               @change="emitUpdateProfil('confirmeEmail', $event.target.value)"
               pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" class="form-control"
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
               type="checkbox" id="valid-email"
               :checked="isUnderstood"
               @change="emitUpdateProfil('attentionEmail', $event.target.checked)"
               required>
        <label class="form-check-label text-dark" for="valid-email">Prise en compte du message
          si-dessus.</label>
        <div class="invalid-feedback">La prise en compte doit être activée, svp !</div>
      </div>
    </div>
  </fieldset>
</template>

<script setup>
console.log('-> CardProfil.vue !')
// vue
import {computed} from 'vue'

// store
import {useStore} from '@/store'

const props = defineProps({
  infos: Object
})

console.log('props.infos =', props.infos)

const store = useStore()

const isUnderstood = computed(() => {
  if (store.user.refreshToken !== '') {
    return true
  }
  return false
})


function emitUpdateProfil(key, value) {
  emitter.emit('emitUpdateProfil', {key: key, value: value})
}


/*
import {computed, ref} from 'vue'


const emit = defineEmits(['update:profil'])
let attentionEmail = ref(props.profil.attentionEmail)

console.log('props =', props)

const data = computed({
  get: () => props.profil,
  set: (value) => emit('update:profil', value),
})

function setAttentionEmail(etat) {
  props.profil.attentionEmail = etat
  emit('update:profil', props.profil)
}

 */
</script>

<style scoped>

</style>