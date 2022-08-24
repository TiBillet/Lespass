<template>
    <!-- info getEventHeader en tant qu'action () est contractuel, le getter donne des données antérieures -->
    <!-- <Header :data-header="getEventHeader()"/> -->

    <div v-if="Object.entries(event).length > 0" class="container mt-5">

      <!-- artistes -->
      <div v-for="(artist, index) in event.artists" :key="index">
        <CardArtist :data-artist="artist" class="mb-6"/>
      </div>

       <div class="container">
        <p>
        </p>
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

        <!--
        Don(s):
        les dons sont désactivés par défaut
        l'attribut enable-names permet d'activer une liste de don par son nom (attention: nom unique !!)
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
import {useAllStore} from '@/stores/all'

// composants
import CardArtist from '@/components/CardArtist.vue'
import CardBillet from '@/components/CardBillet.vue'
import CardOptions from '@/components/CardOptions.vue'
import CardEmail from '@/components/CardEmail.vue'
import CardGifts from '@/components/CardGifts.vue'

// state event
const {event, forms} = storeToRefs(useEventStore())
// actions
const {getEventBySlug} = useEventStore()
// state adhésion
let {setEtapeStripe} = useLocalStore()
// state "all" for loading components
const {adhesion, loading, error} = storeToRefs(useAllStore())

const route = useRoute()
const slug = route.params.slug

// const emit = defineEmits(['update:layout'])

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

        // enregistre "l'étape stripe"
        setEtapeStripe('attente_stripe_reservation')

        // lance la/les réservation(s)
        fetch(urlApi, options).then(response => {
          if (response.status !== 201 && response.status !== 400) {
            throw new Error(`${response.status} - ${response.statusText}`)
          }
          return response.json()
        }).then(retour => {
          console.log('-> /api/reservations/, retour =', retour)
          if (retour.checkout_url !== undefined) {
            // redirection vers stripe
            window.location.assign(retour.checkout_url)
          } else {

            loading.value = false
            // let contenuMessage = JSON.stringify(retour, null, 2)
            emitter.emit('modalMessage', {
              titre: 'Succès',
              dynamic: true,
              contenu: `<h5>Réservation de l'évènement ok !<h5>`
            })
          }
        }).catch(function (erreur) {
          loading.value = false
          error.value = `Event, réservation produits erreur: ${erreur}`
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
</script>
<style>
.invalid-feedback {
  margin-top: -4px !important;
  margin-left: 4px !important;
}
</style>