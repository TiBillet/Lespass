<template>
  <div id="modal-form-login" aria-hidden="true" aria-labelledby="modal-form-login"
       class="modal fade" role="dialog"
       tabindex="-1">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="container card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-gradient text-center">Connectez vous</h3>

              <div class="d-flex flex-row justify-content-center">
                <hr class="text-dark w-50">
              </div>

              <h3 class="font-weight-bolder text-info text-gradient text-center">avec votre e-mail</h3>
            </div>

            <div class="card-body">
              <form role="form" class="text-left" @submit.prevent="validerLogin($event)">
                <div class="input-group">
                  <input id="login-email" :value="adhesion.email" laria-describedby="email-addon" aria-label="Email"
                         class="form-control" placeholder="Email" type="email"
                         pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" required>
                </div>
                <p class="mt-2">Nul besoin de mot de passe : un email vous sera envoyé pour validation.</p>
                <div class="text-center">
                  <button class="btn btn-round bg-gradient-info btn-lg mt-4 mb-0 h-44px" type="submit">Valider
                  </button>
                </div>
              </form>

              <div class="d-flex flex-row justify-content-center mt-4">
                <hr class="text-dark w-50">
              </div>

              <div class="d-flex flex-row justify-content-center mt-2">
                <h3 class="font-weight-bolder text-info text-gradient text-center">Avec communecter</h3>
              </div>

              <div class="text-center">
                <button class="btn btn-round bg-gradient-info btn-lg" type="button"
                        @click="goCommunecter()">
                  <div class="d-flex flex-row justify-content-center align-items-center w-100">
                    <img :src="communecterLogo" class="communecter-logo" alt="logo communecter">
                  </div>
                </button>
              </div>
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

// asset
import communecterLogo from '@/assets/img/communecterLogo_31x28.png'

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

function goCommunecter() {
  location.href = '/api/user/requestoauth/'
}
</script>

<style scoped>
.h-44px {
  height: 44px;
}

.communecter-logo {
  height: 26px;
  width: auto;
}
</style>