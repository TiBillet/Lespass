// gère les routes(pages)
import {createRouter, createWebHistory} from 'vue-router'
import Accueil from '../views/Accueil.vue'

// common
import {emailActivation, getStripeReturn} from '@/common'

const routes = [
  {
    path: '/',
    name: 'Accueil',
    component: Accueil
  },
  {
    path: '/event/:slug',
    name: 'Event',
    // route level code-splitting
    // this generates a separate chunk (about.[hash].js) for this route
    // which is lazy-loaded when the route is visited.
    component: () => import(/* webpackChunkName: "Event" */ '../views/Event.vue')
  },
  {
    path: '/artist/:slug',
    name: 'Artist',
    component: () => import(/* webpackChunkName: "Artist" */ '../views/ArtistPage.vue')
  },
  {
    // route interceptée
    path: '/emailconfirmation/:id/:token',
    name: 'EmailConfirmation',
    component: {}
  },
  {
    // route interceptée
    path: '/stripe/return/:id',
    name: 'StripeReturn',
    component: {}
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  console.log('from =', from)
  console.log('to =', to)

  // traitement de la redirection si interception
  let redirection = false
  let nouvelleRoute = '/'
  if (from.name !== undefined) {
    nouvelleRoute === from.name
  }

  // intercepte la route "EmailConfirmation" et active l'email
  // https://m.django-local.org:8002/emailconfirmation/M2M2YjcxYzAtZGRlNy00MWNiLTk1ZjUtNTViZmUyYTVmZjgy/b1k88g-d7fca49b197cc5f471c1f255819c5f58
  if (to.name === "EmailConfirmation") {
    const id = to.params.id
    const token = to.params.token
    // console.log('id =', id, '  --  token =', token)
    if (id !== undefined && token !== undefined) {
      emailActivation(id, token)
    } else {
      emitter.emit('message', {
        tmp: 6,
        typeMsg: 'danger',
        contenu: `Confirmation email, erreur: id et/ou token indéfinis !`
      })
    }
    redirection = true
  }

  // intercepte retour de stripe
  // http://m.django-local.org:3000/stripe/return/a8f3439f-d7f3-474a-9980-8873950c98f8
  // POST /webhook_stripe/a8f3439f-d7f3-474a-9980-8873950c98f8
  if (to.name === "StripeReturn") {
    console.log('Interception "StripeReturn" !')
    console.log('to =', to)
    const uuidStripe = to.params.id
    console.log('uuidStripe =', uuidStripe)
    if (uuidStripe !== undefined) {
      getStripeReturn(uuidStripe)
    } else {
      emitter.emit('message', {
        tmp: 6,
        typeMsg: 'danger',
        contenu: `Retour stipe, erreur: id indéfini !`
      })
    }
    redirection = true
  }

  if (redirection === true) {
    next({
      path: nouvelleRoute,
      replace: true
    })
  } else {
    next()
  }

})


export default router
