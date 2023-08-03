import Accueil from "../views/Accueil.vue"
import { log } from "../communs/LogError"
import { useSessionStore } from "../stores/session"

const domain = `${window.location.protocol}//${window.location.host}`

async function loadEvent(to, from, next) {
  const { setLoadingValue, initFormEvent } = useSessionStore()
  setLoadingValue(true)
   const urlApi = `/api/eventslug/${to.params.slug}`
    try {
      const response = await fetch(domain + urlApi)
      if (response.status !== 200) {
        throw new Error(`${response.status} - ${response.statusText}`)
      }
      const retour = await response.json()
      setLoadingValue(false)
      initFormEvent(retour)
      // Une fois le chargement de l'évènement fait, aller à la page event.
      next()
    } catch (error) {
      setLoadingValue(false)
      log({ message: `loadEvent, /api/eventslug/${to.params.slug}, error: `, error })
      emitter.emit('modalMessage', {
        titre: 'Erreur',
        contenu: `Chargement de l'évènement '${to.params.slug}' -- erreur: ${error.message}`
      })
       next()
    }


}

export const routes = [
  {
    // 404, route interceptée
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: {}
  },
  {
    path: '/',
    name: 'Accueil',
    // route level code-splitting
    // this generates a separate chunk (about.[hash].js) for this route
    // which is lazy-loaded when the route is visited.
    component: Accueil
  },
  {
    // route interceptée
    path: '/emailconfirmation/:id/:token',
    name: 'EmailConfirmation',
    component: {}
  },
  {
    path: '/event/:slug',
    // si iframe
    alias: '/event/embed/:slug',
    name: 'Event',
    beforeEnter: [loadEvent],
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
    component: () => import(/* webpackChunkName: "Adhesions" */ '../views/Adhesions.vue')
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
