// store
import {useSessionStore} from '@/stores/session'
import {useLocalStore} from '@/stores/local'

// gère les routes(pages)
import {createRouter, createWebHistory} from 'vue-router'
import Accueil from '../views/Accueil.vue'

const domain = `${location.protocol}//${location.host}`

const routes = [
  {
    // 404, route interceptée
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: {}
  },
  {
    path: '/',
    name: 'Accueil',
    component: Accueil
  },
  {
    // route interceptée
    path: '/emailconfirmation/:id/:token',
    name: 'EmailConfirmation',
    component: {}
  },
  {
    // /search/screens -> /search?q=screens
    path: '/event/embed/:slug',
    name: 'EventEmbed',
    component: () => import(/* webpackChunkName: "Event" */ '../views/Event.vue'),
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
    path: '/adhesions/',
    name: 'Adhesions',
    component: () => import(/* webpackChunkName: "Adhesions" */ '@/views/Adhesions.vue')
  },
  {
    // route interceptée
    path: '/stripe/return/:id',
    name: 'StripeReturn',
    component: {}
  },
  {
    // route interceptée
    path: '/emailconfirmation/:id/:token',
    name: 'EmailConfirmation',
    component: {}
  },
  {
    path: '/status',
    name: 'StatusPlace',
    component: () => import(/* webpackChunkName: "StatusPlace" */ '../views/StatusPlace.vue')
  },
  {
    path: '/onboardreturn/:accstripe/',
    name: 'OnboardReturn',
    component: () => import(/* webpackChunkName: "OnboardReturn" */ '../views/OnboardReturn.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // always scroll to top
    return {
      top: 0,
      behavior: 'smooth'
    }
  }
})


router.beforeEach((to, from, next) => {
  // traitement de la redirection si interception
  let redirection = false
  let nouvelleRoute = '/'
  if (from.name !== undefined) {
    nouvelleRoute = from.path
  }

  // par défaut le header et la navbar son affiché
  const {setIdentitySite} = useSessionStore()
  setIdentitySite(true)
  if (to.name === "EventEmbed") {
    setIdentitySite(false)
  }

  // intercepte la route "NotFound" et redirige sur le wiki tibillet
  if (to.name === "NotFound") {
    // window.location = "https://wiki.tibillet.re/"
  }

  // intercepte la route "EmailConfirmation" et active l'email
  if (to.name === "EmailConfirmation") {
    const id = to.params.id
    const token = to.params.token
    if (id !== undefined && token !== undefined) {
      const {emailActivation} = useLocalStore()
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
  if (to.name === "StripeReturn") {
    const localstore = useLocalStore()
    // redirection en fonction de l'url provenant stripeEtape définie dans Event.vue
    nouvelleRoute = localstore.stripeEtape.nextPath

    const uuidStripe = to.params.id
    // console.log('uuidStripe =', uuidStripe)
    if (uuidStripe !== undefined) {
      localstore.postStripeReturn(uuidStripe)
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

  useSessionStore().routeName = to.name

})


export default router
