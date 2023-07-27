import { useSessionStore } from '@/stores/session'

function loadEventData (to, from, next) {
  const { loadEvent } = useSessionStore()
  loadEvent(to.params.slug, next)
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
    component: import(/* webpackChunkName: "Accueil" */ '../views/Accueil.vue')
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
    beforeEnter: [loadEventData],
    name: 'Event',
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
