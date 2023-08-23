import {createApp, markRaw} from 'vue'
import {createPinia} from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import router from './router'
import App from './App.vue'
import mitt from 'mitt'

window.emitter = mitt()

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

// permettre l'utilisation du router dans le store, exemple: this.router.push('/')
pinia.use(({ store }) => {
  store.router = markRaw(router);
})

const app = createApp(App)

// --- directives ---
/**
 * Focus l'élément ayant l'id  = bunding.value
 */
app.directive('focuselement', (el, binding) => {
  el.addEventListener('click', () =>{
    document.querySelector(`#${binding.value}`).focus()
  })
})

app.use(pinia).use(router).mount('#app')
