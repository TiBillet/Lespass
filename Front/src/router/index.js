// gère les routes(pages)
import {createRouter, createWebHistory} from 'vue-router'
import Accueil from '../views/Accueil.vue'

// common
import {emailActivation} from '@/common'

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
    // route intercepté
    path: '/emailconfirmation/:id/:token',
    name: 'EmailConfirmation',
    component: {}
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  // console.log('from =', from)
  // console.log('to =', to)
  // intercepte la route "EmailConfirmation" et active l'email
  if (to.name === "EmailConfirmation") {
    const id = to.params.id
    const token = to.params.token
    // console.log('id =', id, '  --  token =', token)
    if (id !== undefined && token !== undefined) {
      emailActivation(id, token)
    }
    let nouvelleRoute = '/'
    if (from.name !== undefined) {
      nouvelleRoute === from.name
    }
    next({
      path: nouvelleRoute,
      replace: true
    })
  } else {
    next()
  }
})


export default router
