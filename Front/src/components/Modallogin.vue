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
              <form role="form text-left" @submit.prevent="validerLogin()">
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
// vue
import {useStore} from 'vuex'
import {ref} from 'vue'

// common
import {refreshAccessToken} from '@/common'

const store = useStore()
const email = ref(store.state.profil.email)
const domain = `${location.protocol}//${location.host}`


async function validerLogin() {
  console.log('fonc validerLogin, email =', email.value)

  // 1 - utilisateur exsite ?
  const emailB64 = btoa(email.value)
  let api = `/api/membership/${emailB64}/`
  let userExist = false
  let accessTokenValide = false

  // enregistrer email dans le store
  store.commit('updateProfilEmail', email.value)

  console.log('url =', domain + api)
  try {
    const response = await fetch(domain + api, {
      method: 'GET',
      cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
      headers: {
        'Content-Type': 'application/json'
      }
    })
    // génère une erreur si response différent de 200(ok)
    if (response.status !== 200 && response.status !== 402) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    const retour = await response.json()
    // console.log('retour =', JSON.stringify(retour, null, 2))
    // console.log('retour.a_jour_cotisation =', retour.a_jour_cotisation)
    if (retour.a_jour_cotisation !== undefined) {
      userExist = true
    }
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Erreur, ${domain + api} : ${erreur}`
    })
  }

  // vérifier la validité du access token
  if (userExist === true) {
    let apiTest = `/api/user/token/verify/`
    // 200=ok / 401=pas authorisé ou expiré / 400= refresh token = ''
    console.log(`verification du refresh token ${domain + apiTest}, refresh =${store.state.refreshToken}`)
    try {
      const response = await fetch(domain + apiTest, {
        method: 'POST',
        cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({token: accessToken})
      })

      console.log('response =', response)
      if (response.status !== 200 && response.status !== 401 && response.status !== 400) {
        throw new Error(`${response.status} - ${response.statusText}`)
      }
      if (response.status === 400 || response.status === 401) {
        // reset refresh token
        window.accessToken = ''
        accessTokenValide = false
      }

      if (response.status === 200) {
        accessTokenValide = true
      }

    } catch (erreur) {
      emitter.emit('message', {
        tmp: 4,
        typeMsg: 'danger',
        contenu: `Verification de la validité du access token: ${erreur}`
      })
    }

  }

  // TODO: si userExist === true && accessTokenValide === false && store.state.refreshToken === 'vide' => demander nouveau acces et refresh token (sans création d'utilisateur)/ email
  // informe refresh vide
  if (userExist === true && accessTokenValide === false && store.state.refreshToken === '') {
    emitter.emit('message', {
      tmp: 4,
      typeMsg: 'warning',
      contenu: `Utilisateur ok, access token non valide, refresh token vide; informer l'administrateur !`
    })
  }


  // demander nouveau access / refresh token (api= /api/user/token/refresh/)
  if (userExist === true && accessTokenValide === false && store.state.refreshToken !== '') {
    accessTokenValide = refreshAccessToken(store.state.refreshToken)
  }

  console.log('userExist =', userExist)
  console.log('accessTokenValide =', accessTokenValide)

  // créer l'utilisateur
  if (userExist === false) {
    api = `/api/user/create/`
    try {
      const response = await fetch(domain + api, {
        method: 'POST',
        cache: 'no-cache',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({email: email.value})
      })
      if (response.status !== 201) {
        throw new Error(`Erreur création utilisateur !`)
      }
      const retour = await response.json()
      if (response.status === 201) {
        // ferme le modal
        const elementModal = document.querySelector('#modal-form-login')
        const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
        modal.hide()
        // message de succès
        emitter.emit('modalMessage', {
          titre: 'Création utilisateur OK !',
          contenu: retour
        })
      }
    } catch (erreur) {
      emitter.emit('message', {
        tmp: 8,
        typeMsg: 'warning',
        contenu: `Erreur, ${domain + api} : ${erreur}`
      })
    }
  }

}
</script>
<style>

</style>