<template>
  <div id="modal-form-login" aria-hidden="true" aria-labelledby="modal-form-login"
       class="modal fade" role="dialog"
       tabindex="-1">
    <div class="modal-dialog modal-dialog-centered modal-sm" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-gradient">Connectez vous</h3>
              <p class="mb-0">Entrez votre email</p>
            </div>
            <div class="card-body">
              <form role="form text-left" @submit.prevent="validerLogin($event)">
                <div class="input-group mb-3">
                  <input id="test-email" v-model="email" laria-describedby="email-addon" aria-label="Email"
                         class="form-control" placeholder="Email" type="email"
                         pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" required>
                </div>
                <div class="text-center">
                  <button class="btn btn-round bg-gradient-info btn-lg w-100 mt-4 mb-0" type="submit">Valider</button>
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
// store
import {useStore} from '@/store'
// vue
import {ref} from 'vue'

const store = useStore()
const email = ref(store.user.email)
const domain = `${location.protocol}//${location.host}`

async function validerLogin(event) {
  if (event.target.checkValidity() === true) {
    console.log('refreshToken =', store.user.refreshToken)
    // enregistre l'email dans le storeUser
    store.user.email = email.value
    // -- créer utilisateur = refreshToken = '' --
    if (store.user.refreshToken === '') {
      const api = `/api/user/create/`
      try {
        const response = await fetch(domain + api, {
          method: 'POST',
          cache: 'no-cache',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({email: email.value})
        })
        const retour = await response.json()
        if (response.status === 201 || response.status === 401 || response.status === 202) {
          // ferme le modal
          const elementModal = document.querySelector('#modal-form-login')
          const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
          modal.hide()
          // message de succès
          emitter.emit('modalMessage', {
            titre: 'Création utilisateur OK !',
            contenu: retour
          })
        } else {
          throw new Error(`Erreur création utilisateur !`)
        }
      } catch (erreur) {
        emitter.emit('message', {
          tmp: 8,
          typeMsg: 'warning',
          contenu: `${domain + api} : ${erreur}`
        })
      }
    }
  }
}
</script>
<style>

</style>