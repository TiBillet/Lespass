// store
import { useAllStore } from '@/stores/all'
import { useLocalStore } from '@/stores/local'

// gère les routes(pages)
import { createRouter, createWebHistory } from 'vue-router'
import { routes } from './routes.js'

const domain = `${location.protocol}//${location.host}`

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior (to, from, savedPosition) {
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

  // par défaut le header et la navbar sons affichés
  const { setIdentitySite } = useAllStore()
  setIdentitySite(true)

  // le header et la navbar sont cachées
  if (to.path.includes('embed')) {
    setIdentitySite(false)
  }

  // intercepte la route "NotFound" et redirige sur le wiki tibillet
  if (to.name === 'NotFound') {
    // window.location = "https://wiki.tibillet.re/"
  }

  // intercepte la route "EmailConfirmation" et active l'email
  if (to.name === 'EmailConfirmation') {
    const id = to.params.id
    const token = to.params.token
    if (id !== undefined && token !== undefined) {
      const { emailActivation } = useLocalStore()
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
  if (to.name === 'StripeReturn') {
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

  useAllStore().routeName = to.name

})

export default router
