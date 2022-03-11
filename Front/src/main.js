import {createApp, watch} from 'vue'
import {createPinia} from 'pinia'
import PersistedState from 'pinia-plugin-persistedstate'
import router from './router'
import App from './App.vue'
import mitt from 'mitt'

window.emitter = mitt()
window.accessToken = ''

const pinia = createPinia().use(PersistedState)
const app = createApp(App)
app.use(pinia).use(router).mount('#app')
