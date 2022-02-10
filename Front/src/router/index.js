// gère les routes(pages)
import {createRouter, createWebHistory} from 'vue-router'

import ChargementDatas from '../views/ChargementDatas.vue'
import Accueil from '../views/Accueil.vue'
// import Buy from '../views/Buy.vue'

const routes = [
  {
    path: '/Accueil',
    name: 'Accueil',
    component: Accueil
  },
  {
    path: '/',
    name: 'ChargementDatas',
    component: ChargementDatas
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
    path: '/buy/:uuidEvent/:productUuid',
    name: 'Buy',
    component: () => import(/* webpackChunkName: "Buy" */ '../views/Buy.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
