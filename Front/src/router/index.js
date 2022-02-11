// gère les routes(pages)
import {createRouter, createWebHistory} from 'vue-router'

import Accueil from '../views/Accueil.vue'
// import Buy from '../views/Buy.vue'

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
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
