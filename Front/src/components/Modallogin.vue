<template>
  <div id="modal-form-login" aria-hidden="true" aria-labelledby="modal-form-login"
       class="modal fade" role="dialog"
       tabindex="-1">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-gradient">Connectez vous</h3>
              <!-- <p class="mb-0">Entrez votre email</p> -->
            </div>
            <div class="card-body">
              <form role="form text-left" @submit.prevent="validerLogin($event)">
                <div class="input-group mb-3">
                  <input id="login-email" :value="adhesion.email" laria-describedby="email-addon" aria-label="Email"
                         class="form-control" placeholder="Email" type="email"
                         pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" required>
                </div>
                <div class="text-center">
                  <button class="btn btn-round bg-gradient-info btn-lg w-100 mt-4 mb-0 btn-sm" type="submit">Valider</button>
                </div>
                <div class="text-center mt-2">
                  <a class="text-info" type="submit">Se connecter avec communecter</a>
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
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'

// const {adhesion} = useLocalStore()
const domain = `${location.protocol}//${location.host}`
const {adhesion, loading, error} = storeToRefs(useAllStore())

async function validerLogin(event) {
  if (event.target.checkValidity() === true) {
    // enregistre l'email dans le storeUser
    const email = document.querySelector('#login-email').value
    console.log('-> validerLogin, email =', email)
    adhesion.email = email


    const api = `/api/user/create/`
    try {
      loading.value = true
      const response = await fetch(domain + api, {
        method: 'POST',
        cache: 'no-cache',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({email: email})
      })
      const retour = await response.json()
      console.log('retour =', retour)
      // if (response.status === 201 || response.status === 401 || response.status === 202) {

      if (response.status === 200) {
        // ferme le modal
        const elementModal = document.querySelector('#modal-form-login')
        const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
        modal.hide()
        // message de succès
        emitter.emit('modalMessage', {
          titre: 'Validation',
          contenu: retour
        })
      } else {
        throw new Error(`Erreur création utilisateur !`)
      }
    } catch (erreur) {
      console.log('-> validerLogin, erreur :', erreur)
      error.value = erreur
    }
  }
  loading.value = false
}
</script>

<style>
</style>