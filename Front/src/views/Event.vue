<template>
  <Loading v-if="loading"/>
  <p v-if="error !== null" class="text-dark">{{ error }}</p>

  <!-- info getEventHeader en tant qu'action () est contractuel, le getter donne des données antérieures -->
  <Header v-if="loading === false" :header-event="getEventHeader()"/>
  <div v-if="loading === false" class="container mt-7">

    <!-- artistes -->
    <div v-for="(artist, index) in event.artists" :key="index">
      <CardArtist :data-artist="artist" class="mb-6"/>
    </div>


    <form @submit.prevent="validerAchats($event)" class="needs-validation" novalidate>
      <!--
      Billet(s)
      Si attribut "image", une image est affiché à la place du nom
      Attribut 'style-image' gère les propriétées(css) de l'image (pas obligaoire, style par défaut)
       -->
      <CardBillet :image="true" :style-image="{height: '30px',width: 'auto'}"/>

      <CardOptions/>

      <CardEmail/>

      <CardAdhesion/>

      <!--
      Don(s):
      les dons ont désactivé par défaut
      l'attribut enable-names permet dactiver une liste de don par son nom (attention: nom unique !!)
      -->
      <CardGifts :enable-names="['Don']"/>

      <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
    </form>


  </div>

</template>

<script setup>
// console.clear()
console.log('-> Event.vue !')

// vue
import {useRoute} from 'vue-router'

// store
import {storeToRefs} from 'pinia'
import {useEventStore} from '@/stores/event'
import {useLocalStore} from '@/stores/local'

// composants
import Loading from '@/components/Loading.vue'
import Header from '@/components/Header.vue'
import CardArtist from '@/components/CardArtist.vue'
import CardBillet from '@/components/CardBillet.vue'
import CardOptions from '@/components/CardOptions.vue'
import CardEmail from '@/components/CardEmail.vue'
import CardAdhesion from '@/components/CardAdhesion.vue'
import CardGifts from '@/components/CardGifts.vue'

// state event
const {event, forms, loading, error} = storeToRefs(useEventStore())
// actions
const {getEventBySlug, getEventHeader} = useEventStore()
// state adhésion
let {adhesion, stripeEtape} = useLocalStore()

const route = useRoute()
const slug = route.params.slug

// load event
getEventBySlug(slug)

// formatage des données POST events
function formatBodyPost() {
  // console.log('-> fonc formatBodyPost !')

  const form = forms.value.find(obj => obj.event === event.value.uuid)

  // proxy to array
  const prices = JSON.parse(JSON.stringify(form.prices))

  // init body with prices ticket
  const body = {
    event: form.event,
    email: form.email,
    prices,
    options: []
  }

  // options radio
  for (const optionRadioKey in form.options_radio) {
    const option = form.options_radio[optionRadioKey]
    if (option.activation === true) {
      body.options.push(option.uuid)
    }
  }

  // options checkbox
  for (const optionCheckboxKey in form.options_checkbox) {
    const option = form.options_checkbox[optionCheckboxKey]
    if (option.activation === true) {
      body.options.push(option.uuid)
    }
  }

  // adhésion
  if (adhesion.activation === true) {
    console.log('adhesion =', adhesion)
    const obj = {
      uuid: adhesion.uuidPrix,
      qty: 1,
      customers: [{
        first_name: adhesion.first_name,
        last_name: adhesion.last_name,
        phone: adhesion.phone,
        postal_code: adhesion.postal_code,
        birth_date: "1984-04-18"
      }]
    }
    body.prices.push(obj)
  }

  // gifts
  for (const giftKey in form.gifts) {
    const gift = form.gifts[giftKey]
    if (gift.enable === true) {
      body.prices.push({
        uuid: gift.price,
        qty: 1
      })
    }
  }
  return body
}

function validerAchats(domEvent) {
  console.log('-> fonc validerAchats !')

  // efface tous les messages d'invalidité
  const msgInvalides = domEvent.target.querySelectorAll('.invalid-feedback')
  for (let i = 0; i < msgInvalides.length; i++) {
    msgInvalides[i].style.display = 'none'
  }

  if (domEvent.target.checkValidity() === false) {
    // formulaire non valide
    // console.log('formulaire pas vailde !')
    // scroll vers l'entrée non valide et affiche un message
    const elements = domEvent.target.querySelectorAll('input')
    for (let i = 0; i < elements.length; i++) {
      const element = elements[i]
      if (element.checkValidity() === false) {
        // console.log('element = ', element)
        element.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
        element.parentNode.querySelector('.invalid-feedback').style.display = 'block'
        break
      }
    }
  } else {
    // vérifier emails
    const email = document.querySelector(`#profil-email`)
    const confirmeEmail = document.querySelector(`#profil-confirme-email`)
    if (email.value !== confirmeEmail.value) {
      // console.log('formulaire non valide !')
      confirmeEmail.parentNode.querySelector('.invalid-feedback').style.display = 'block'
      confirmeEmail.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
    } else {
      // formulaire valide
      console.log('formulaire valide !')

      // vérifier qu'il y a au moins un achat pour valider un POST
      let buyEnable = false
      const form = forms.value.find(obj => obj.event === event.value.uuid)
      console.log('formulaire =', JSON.stringify(form, null, 2))
      if (form.prices.length > 0) {
        buyEnable = true
      }
      if (adhesion.activation === true) {
        buyEnable = true
      }
      // lancement achat
      if (buyEnable === true) {
        const body = JSON.stringify(formatBodyPost())

        // ---- requête "POST" achat billets ----
        const urlApi = `/api/reservations/`

        // options de la requête
        const options = {
          method: 'POST',
          body: body,
          headers: {
            'Content-Type': 'application/json'
          }
        }
        console.log('options =', options)

        // chargement
        loading.value = true

        fetch(urlApi, options).then(response => {
          if (response.status !== 201 && response.status !== 400) {
            throw new Error(`${response.status} - ${response.statusText}`)
          }
          return response.json()
        }).then(retour => {
          console.log('retour =', retour)
          if (retour.checkout_url !== undefined) {
            // redirection vers stripe
            stripeEtape = 'attente_stripe_reservation'
            window.location.assign(retour.checkout_url)
          } else {
            loading.value = false
            let contenuMessage = ''
            for (const key in retour) {
              for (let i = 0; i < retour[key].length; i++) {
                contenuMessage += `<h3>- ${retour[key][i]}</h3>`
              }
            }
            emitter.emit('modalMessage', {
              titre: 'Information',
              dynamique: true,
              contenu: contenuMessage
            })
          }
        }).catch(function (erreur) {
          loading.value = false
          error.value = `Event, réservation produits erreur: ${erreur}`
          /*
          emitter.emit('message', {
            tmp: 6,
            typeMsg: 'danger',
            contenu: `Event, réservation produits erreur: ${erreur}`
          })
           */
        })
      } else {
        // aucun produit sélectionné
        emitter.emit('modalMessage', {
          titre: '?',
          contenu: `Aucun produit sélectionné !`
        })
      }
    }
  }

}


/*

function goValiderAchats(event) {
  // console.log('-> fonc goValiderAchats !')

  // efface tous les messages d'invalidité
  const msgInvalides = event.target.querySelectorAll('.invalid-feedback')
  for (let i = 0; i < msgInvalides.length; i++) {
    msgInvalides[i].style.display = 'none'
  }

  // vérifier email
  const email = document.querySelector('#profil-email')
  if (email.checkValidity() === false) {
    email.parentNode.querySelector(`.invalid-feedback`).style.display = 'block'
    email.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
  } else {
    email.parentNode.querySelector(`.invalid-feedback`).style.display = 'none'
  }
  const confirmEmail = document.querySelector('#profil-confirme-email')
  if (email.value !== confirmEmail.value) {
    confirmEmail.parentNode.querySelector(`.invalid-feedback`).style.display = 'block'
    confirmEmail.setCustomValidity('erreur')
    confirmEmail.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
  } else {
    confirmEmail.parentNode.querySelector(`.invalid-feedback`).style.display = 'none'
    confirmEmail.setCustomValidity('')
  }

  // vérifier activation adhésion
  const adhesionActive = store.memoComposants.CardAdhesion[store.currentUuidEvent].activation
  console.log('adhesionActive =', adhesionActive)

  // vérifier la sélection d'un prix d'adhésion
  const adhesionPrix = store.memoComposants.CardAdhesion[store.currentUuidEvent].uuidPrix
  console.log('adhesionPrix =', adhesionPrix)

  // enlever ancien sigalement (si adhésion active et aucune sélection de prix)
  if (document.querySelector(`#card-adhesion-uuid-price-parent0`)) {
    document.querySelector(`#card-adhesion-uuid-price-parent0`).querySelector(`.invalid-feedback`).style.display = 'none'
  }

  // signaler si adhésion active et aucune sélection de prix
  if (adhesionActive === true && adhesionPrix === '') {
    document.querySelector(`#card-adhesion-uuid-price-parent0`).querySelector(`.invalid-feedback`).style.display = 'block'
    document.querySelector(`#card-adhesion-uuid-price-parent0`).scrollIntoView({
      behavior: 'smooth',
      inline: 'center',
      block: 'center'
    })
  }


  // continuer validation du formulaire
  if ((adhesionActive === true && adhesionPrix !== '') || adhesionActive === false) {
    console.log('valider les autres champs du formulaire !!')
    if (event.target.checkValidity() === true) {
      // formulaire valide, formatage data pour api
      console.log('validation formulaire ok, formatage des datas !')
      const data = formaterDatas(adhesionActive, adhesionPrix)
      const body = JSON.stringify(data)
      console.log('body =', body)

      if (data.prices.length === 0) {
        // pas d'achats
        emitter.emit('message', {
          tmp: 4,
          typeMsg: 'warning',
          contenu: `Rien à valider !`
        })
      } else {
        // ---- requête "POST" achat billets ----
        const urlApi = `/api/reservations/`
        // options de la requête
        const options = {
          method: 'POST',
          body: body,
          headers: {
            'Content-Type': 'application/json'
          }
        }
        fetch(urlApi, options).then(response => {
          if (response.status !== 201 && response.status !== 400) {
            throw new Error(`${response.status} - ${response.statusText}`)
          }
          return response.json()
        }).then(retour => {
          console.log('retour =', retour)
          if (retour.checkout_url !== undefined) {
            // icon de chargement
            emitter.emit('statusLoading', true)
            // redirection vers stripe en conservant l'historique de navigation
            window.location.assign(retour.checkout_url)
          } else {
            let contenuMessage = ''
            for (const key in retour) {
              for (let i = 0; i < retour[key].length; i++) {
                contenuMessage += `<h3>- ${retour[key][i]}</h3>`
              }
            }
            emitter.emit('modalMessage', {
              titre: 'Information',
              dynamique: true,
              contenu: contenuMessage
            })
          }
        }).catch(function (erreur) {
          emitter.emit('message', {
            tmp: 6,
            typeMsg: 'danger',
            contenu: `Store, réservation produits erreur: ${erreur}`
          })
        })

      }
    } else {
      // formulaire non valide
      console.log('formulaire pas vailde !')
      // scroll vers l'entrée non valide et affiche un message
      const elements = event.target.querySelectorAll('input')
      for (let i = 0; i < elements.length; i++) {
        const element = elements[i]
        if (element.checkValidity() === false) {
          // console.log('element = ', element)
          element.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
          element.parentNode.querySelector('.invalid-feedback').style.display = 'block'
          break
        }
      }
    }
  }
}

 */
</script>
<style>
.invalid-feedback {
  margin-top: -4px !important;
  margin-left: 4px !important;
}

#app {
  background-color: #FFFFFF;
}
</style>