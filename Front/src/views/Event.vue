<template>
  <div class="container mt-5 test-view-event">
    <!-- artistes -->
    <div v-for="(artist, index) in getEventForm.artists" :key="index">
      <CardArtist :artist="artist.configuration" class="mb-6"/>
    </div>

    <form @submit.prevent="validerAchats($event)" class="needs-validation" novalidate>
      <CardEmail v-model:email.checkemail="getEventForm.email"/>

      <!--
     Billet(s)
     Si attribut "image", une image est affiché à la place du nom
     Attribut 'style-image' gère les propriétées(css) de l'image (pas obligaoire, style par défaut)
      -->
      <CardBillet v-model:products="getEventForm.products"/>

      <CardOptions/>

      <CardGifts/>

      <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
    </form>
  </div>
</template>

<script setup>
console.log('-> Event.vue !')
// le près chargement de l'évènement est géré par .../router/routes.js fonction "loadEvent"
import {useRoute} from 'vue-router'

// store
import { useSessionStore } from '../stores/session'
import { setLocalStateKey } from '../communs/storeLocal.js'

// composants
import CardArtist from '../components/CardArtist.vue'
import CardEmail from '../components/CardEmail.vue'
import CardBillet from '../components/CardBillet.vue'
import CardOptions from '../components/CardOptions.vue'
import CardGifts from '../components/CardGifts.vue'

const { getEventForm, setLoadingValue } = useSessionStore()
const route = useRoute()

// formatage des données POST event
function formatBodyPost () {
  // console.log('-> fonc formatBodyPost !')
  const form = JSON.parse(JSON.stringify(getEventForm))
  // init body with prices ticket
  const body = {
    event: form.uuid,
    email: form.email,
    // chargeCashless: form.chargeCashless, // TODO: à faire
    prices: [],
    options: []
  }

  // infos:
  // produits 'D' et 'A' n'ont pas la propriété customers dans leurs prix

  form.products.forEach((product) => {
    product.prices.forEach((price) => {
      if (price.customers !== undefined && price.customers.length >= 1) {
        // price sans uuid (besoin pour le formulaire)
        let filterCustomers = []
        price.customers.forEach((customer) => {
          filterCustomers.push({ first_name: customer.first_name, last_name: customer.last_name })
        })
        body.prices.push({
          uuid: price.uuid,
          qty: price.customers.length,
          customers: filterCustomers
        })
      }
    })
  })

  form.products.forEach((product) => {
    //adhésions
    if (product.categorie_article === 'A' && product.activated === true) {
      const data = product.customers[0]
      // ajout prix adhésion
      body.prices.push({
        uuid: data.uuid,
        qty: 1,
        customers: [{
          first_name: data.first_name,
          last_name: data.last_name,
          phone: data.phone,
          postal_code: data.postal_code
        }]
      })

      // ajout des options à choix unique(radio) de l'adhésions
      if (product.optionRadio !== '') {
        body.options.push(product.optionRadio)
      }

      // ajout des options à choix multiples(checkbox) de l'adhésions
      product.option_generale_checkbox.forEach((option) => {
        if (option.checked === 'true') {
          body.options.push(option.uuid)
        }
      })
    }

    // ajout don
    if (product.categorie_article === 'D') {
      console.log('product.activatedGift =', product.activatedGift, '  --  type =', typeof (product.activatedGift))
      console.log('product.selectedPrice =', product.selectedPrice)
      if (product.activatedGift === true && product.selectedPrice !== '') {
        body.prices.push({
          uuid: product.selectedPrice,
          qty: 1
        })
      }
    }
  })

  // ajout de l'option à choix unique(radio) de l'évènement
  if (form.optionRadioSelected !== '') {
    body.options.push(form.optionRadioSelected)
  }

  // ajout de l'option à choix multiples(checkbox) de l'évènement
  form.options_checkbox.forEach((option) => {
    if (option.checked === 'true') {
      body.options.push(option.uuid)
    }
  })

  return body
}

async function validerAchats (event) {
  if (!event.target.checkValidity()) {
    event.preventDefault()
    event.stopPropagation()
  }
  event.target.classList.add('was-validated')
  if (event.target.checkValidity() === true) {
    console.log('validation ok!')
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
    console.log('options =', JSON.stringify(options, null, 2))

    // active l'icon de chargement
    setLoadingValue(true)

    // lance la/les réservation(s)
    fetch(urlApi, options).then(response => {
      // erreurs
      if (response.status >= 400 && response.status <= 599) {
        let typeErreur = 'Client'
        if (response.status >= 500) {
          typeErreur = 'Serveur'
        }
        throw new Error(`${typeErreur}, ${response.status} - ${response.statusText}`)
      }
      return response.json()
    }).then((response) => {
      setLoadingValue(false)
      if (response.checkout_url !== undefined) {
        // mémorise l'étape ayant lancé l'opération stripe
        if (route.path.indexOf('embed') !== -1) {
          // reste sur l'event
          setLocalStateKey('stripeStep', {
            action: 'expect_payment_stripe_reservation',
            eventFormUuid: getEventForm.uuid,
            nextPath: route.path
          })
        } else {
          // va à l'accueil
          setLocalStateKey('stripeStep', {
            action: 'expect_payment_stripe_reservation',
            eventFormUuid: getEventForm.uuid,
            nextPath: '/'
          })
        }
        // paiement, redirection vers stripe
        window.location.assign(response.checkout_url)
      } else {
        // paiement sans stripe, exemple: réservation gratuite
        emitter.emit('modalMessage', {
          typeMsg: 'success',
          titre: 'Demande envoyée.',
          dynamic: true,
          contenu: '<h4>Merci de vérifier votre réservation dans votre boite email.</h4>'
        })
      }
    }).catch((erreur) => {
      setLoadingValue(false)
       // action stripe = aucune
      setLocalStateKey('stripeStep', { action: null })
      emitter.emit('modalMessage', {
        titre: 'Erreur(s)',
        // contenu = html => dynamic = true
        dynamic: true,
        contenu: '<h3>' + erreur + '</h3>',
        typeMsg: 'warning',
      })
    })
  }
}

</script>

<style></style>