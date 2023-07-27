import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import router from './router'
import App from './App.vue'
import mitt from 'mitt'
import { useSessionStore } from '@/stores/session'

//dev hot reload
if (import.meta.hot) {
  import.meta.hot.on('vite:beforeFullReload', () => {
    throw '(skipping full reload)'
  })
}

window.emitter = mitt()
window.accessToken = ''

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

const app = createApp(App)
app.use(pinia).use(router)

async function initApp () {
  const { loadPlace } = useSessionStore()
  // chargement des données initiales
  await loadPlace()
  app.mount('#app')
}

initApp()
