<template>
  <div id="modal-form-login" aria-hidden="true" aria-labelledby="modal-form-login"
       class="modal fade" role="dialog"
       tabindex="-1">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="container card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-center">Connectez vous</h3>

              <div class="d-flex flex-row justify-content-center">
                <hr class="text-dark w-50">
              </div>

              <h4 class="font-weight-bolder text-info text-center">Avec votre e-mail</h4>
            </div>

            <div class="card-body">
              <form class="text-left needs-validation" @submit.prevent="validerLogin($event)" novalidate>
                <div class="input-group has-validation">
                  <input id="login-email" :value="getEmail" laria-describedby="email-addon" aria-label="Email"
                         class="form-control" placeholder="Email" type="email"
                          @keyup="validateEmail($event)" required>
                  <div class="invalid-feedback">
                    Merci de renseigner une adresse email valide.
                  </div>
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
                <h4 class="font-weight-bolder text-info text-center">Avec communecter</h4>
              </div>

              <div class="text-center mt-2">
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
// log
import { log } from '../communs/LogError.js'

// store
import { useSessionStore } from '@/stores/session'
import { setLocalStateKey } from '../communs/storeLocal'

// asset
import communecterLogo from '@/assets/img/communecterLogo_31x28.png'

const domain = `${location.protocol}//${location.host}`
let { getEmail, updateEmail, loading } = useSessionStore()

function validateEmail (event) {
  let value = event.target.value
  event.target.setAttribute('type', 'text')
  const re = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$/
  if (value.match(re) === null) {
    event.target.parentNode.querySelector('.invalid-feedback').style.display = "block"
  } else {
    event.target.parentNode.querySelector('.invalid-feedback').style.display = "none"
  }
}

async function validerLogin (event) {
  if (!event.target.checkValidity()) {
    event.preventDefault()
    event.stopPropagation()
  }
  event.target.classList.add('was-validated')
  if (event.target.checkValidity() === true) {
    const email = document.querySelector('#login-email').value
    // enregistre l'email dans le storeUser
    updateEmail(email)
    console.log('-> validerLogin, email =', email)

    const api = `/api/user/create/`
    try {
      loading = true
      const response = await fetch(domain + api, {
        method: 'POST',
        cache: 'no-cache',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: email })
      })
      const retour = await response.json()
      console.log('retour =', retour)
      // if (response.status === 201 || response.status === 401 || response.status === 202) {

      if (response.status === 200) {
        // enregistrement en local(long durée) de l'email
        setLocalStateKey('email', email)
        // ferme le modal
        const elementModal = document.querySelector('#modal-form-login')
        const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
        modal.hide()
        // message de succès
        emitter.emit('modalMessage', {
          titre: 'Validation',
          typeMsg: 'success',
          contenu: retour
        })
      } else {
        throw new Error(`Erreur création utilisateur !`)
      }
    } catch (error) {
      log({ message: 'login', error })
      emitter.emit('modalMessage', {
        titre: 'Erreur',
        typeMsg: 'danger',
        contenu: `Post, /api/user/create/ -- erreur: ${error.message}`
      })
    }
  }
  loading = false
}

function goCommunecter () {
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