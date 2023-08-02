// store
import { useSessionStore } from "../stores/session"
import { getLocalStateKey } from "../communs/storeLocal.js"

// gère les routes(pages)
import { createRouter, createWebHistory } from 'vue-router'
import { routes } from './routes.js'

const domain = `${location.protocol}//${location.host}`

function loadEventData (to, from, next) {
  const { loadEvent } = useSessionStore()
  loadEvent(to.params.slug, next)
}

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

  // par défaut le header et la navbar son affiché
  let { setIdentitySite } = useSessionStore()
   setIdentitySite(true)

  // le header et la navbar son cachée
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
      const { emailActivation } = useSessionStore()
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
    const {postStripeReturn} = useSessionStore()

    const stripeStep = getLocalStateKey('stripeStep')

    // redirection en fonction de l'url provenant stripeEtape définie dans Event.vue
    nouvelleRoute = stripeStep.nextPath

    const uuidStripe = to.params.id
    // console.log('uuidStripe =', uuidStripe)
    if (uuidStripe !== undefined) {
      postStripeReturn(uuidStripe)
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
  }
  if (redirection === false) {
    next()
  }

  useSessionStore().routeName = to.name
})

export default router
