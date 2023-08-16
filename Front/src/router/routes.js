import Accueil from '../views/Accueil.vue'

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
    meta: {
      // nom de la fonction de préchargement: "events", dans le module "preload.js"
      // avec retour de donnée dans les params ($route.params.events)
       preload: {name: 'events', data: 'events'}
    },
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
    meta: {
      // nom de la fonction de préchargement: "event", dans le module "preload.js"
      // sans retour de donnée dans les params
      preload: {name: 'event', data: null},
    },
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
