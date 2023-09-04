<template>
  <div class="container mt-5 test-view-event">
    <!-- artistes -->
    <div v-for="(artist, index) in getEventForm.artists" :key="index">
      <CardArtist :artist="artist.configuration" class="mb-6"/>
    </div>

    <form id="reservation" @submit.prevent="validerAchats($event)" class="needs-validation" novalidate>

      <CardEmail v-model:email.checkemail="getEventForm.email"/>

      <!--
       Billet(s)
       Si attribut "image = booléen", une image est affiché à la place du nom
       Attribut 'style-image' gère les propriétées(css) de l'image (pas obligaoire, style par défaut)
      -->
      <CardBillet v-model:products="getEventForm.products"/>

      <CardCreditCashless v-model:products="getEventForm.products"/>

      <CardOptions/>

      <CardGifts/>

      <button type="submit" class="btn bg-gradient-dark w-100" role="button" aria-label="Valider la réservation">
        Valider la réservation
      </button>
    </form>
  </div>
</template>

<script setup>
console.log('-> Event.vue !')
// le près chargement de l'évènement est géré par .../router/routes.js fonction "preload"
import { useRoute } from 'vue-router'

// store
import { useSessionStore } from '../stores/session'
import { setLocalStateKey } from '../communs/storeLocal.js'

// composants
import CardArtist from '../components/CardArtist.vue'
import CardEmail from '../components/CardEmail.vue'
import CardBillet from '../components/CardBillet.vue'
import CardOptions from '../components/CardOptions.vue'
import CardGifts from '../components/CardGifts.vue'
import CardCreditCashless from '../components/CardCreditCashless.vue'

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
    prices: [],
    options: []
  }

  // infos:

  // récupération des prix des billets ("B" et "F")
  let products = form.products.filter(product => ['B', 'F'].includes(product.categorie_article))
  products.forEach((product) => {
    product.prices.forEach((price) => {
      // produit nom nominatif et quantité supérieure à 0
      console.log('product.nominative =', product.nominative )
      if (product.nominative === false && price.qty > 0) {
        let activatedLinkProduct = false
        if (price.adhesion_obligatoire !== null) {
          activatedLinkProduct = form.products.find(prod => prod.uuid === price.adhesion_obligatoire).activated
        }
        // si adésion obligatoire = null ou produit lié activé
        console.log('-> adésion obligatoire =', price.adhesion_obligatoire, '  --  activatedLinkProduct =', activatedLinkProduct)
        if (price.adhesion_obligatoire === null || (price.adhesion_obligatoire !== null && activatedLinkProduct === true)) {
          console.log('price name =', price.name)
          body.prices.push({
            uuid: price.uuid,
            qty: price.qty
          })
        }
      }
      if (product.nominative === true) {
        // price sans uuid (besoin uniquement pour le formulaire html)
        let filterCustomers = []
        if (price.customers.length > 0) {
          price.customers.forEach((customer) => {
            filterCustomers.push({ first_name: customer.first_name, last_name: customer.last_name })
          })
          body.prices.push({
            uuid: price.uuid,
            qty: price.customers.length,
            customers: filterCustomers
          })
        }
      }
    })
  })

  // récupération des adhésions ("A")
  products = form.products.filter(product => product.categorie_article === 'A')
  products.forEach((product) => {
    if (product.activated === true && product.conditionsRead === 'true') {
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

      /*
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
       */
    }
  })

  // récupération du cashless ("S")
  products = form.products.filter(product => product.categorie_article === 'S')
  products.forEach((product) => {
    if (product.activated === true && product.qty > 0) {
      body.prices.push({
        uuid: product.uuid,
        qty: product.qty
      })
    }
  })

  // récupération du don ("D")
  products = form.products.filter(product => product.categorie_article === 'D')
  products.forEach((product) => {
    if (product.activatedGift === true) {
      body.prices.push({
        uuid: product.uuid,
        qty: 1
      })
    }
  })

  // option radio de l'évènement
  if (form.optionRadioSelected !== '') {
    body.options.push(form.optionRadioSelected)
  }

  // option checkbox de l'évènement
  form.options_checkbox.forEach(option => {
    if (option.checked === 'true') {
      body.options.push(option.uuid)
    }
  })

  return body
}

// lance la réservation
async function validerAchats (event) {
  if (!event.target.checkValidity()) {
    event.preventDefault()
    event.stopPropagation()
  }
  event.target.classList.add('was-validated')

  // scroll first invalide field
  const firstElement = event.target.querySelector('#reservation .form-control:invalid')
  if (firstElement !== null) {
    firstElement.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'center' })
  }

  if (event.target.checkValidity() === true) {
    console.log('validation ok!')
    try {
      const rawData = formatBodyPost()

      if (rawData.prices.length === 0) {
        throw new Error('Pas de billet dans la reservation.')
      }

      const body = JSON.stringify(rawData)

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
      console.log('body =', body)

      // active l'icon de chargement
      setLoadingValue(true)

      const response = await fetch(urlApi, options)
      if (response.status >= 400 && response.status <= 599) {
        let typeErreur = 'Client'
        if (response.status >= 500) {
          typeErreur = 'Serveur'
        }
        throw new Error(`${typeErreur}, ${response.status} - ${response.statusText}`)
      }

      const retour = await response.json()
      if (retour.checkout_url !== undefined) {
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
        console.log('--> aller chez stripe !')
        window.location.assign(retour.checkout_url)

      } else {
        setLoadingValue(false)
        // paiement sans stripe, exemple: réservation gratuite
        emitter.emit('modalMessage', {
          typeMsg: 'success',
          titre: 'Demande envoyée.',
          dynamic: true,
          contenu: '<h4>Merci de vérifier votre réservation dans votre boite email.</h4>'
        })
      }

    } catch (error) {
      setLoadingValue(false)
      // action stripe = aucune
      setLocalStateKey('stripeStep', { action: null })
      console.log('error.message =', error.message)
      emitter.emit('modalMessage', {
        titre: 'Erreur(s)',
        // contenu = html => dynamic = true
        dynamic: true,
        contenu: '<h3>' + error.message + '</h3>',
        typeMsg: 'warning',
      })
    }
  }
}

</script>

<style></style>