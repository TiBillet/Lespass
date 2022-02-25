import { createApp } from 'vue'
import store from './store'
import router from './router'
import App from './App.vue'
import mitt from 'mitt'
window.emitter = mitt()
window.accessToken = ''


let app = createApp(App)
// ajout de variable au scope de vue3
app.config.globalProperties.access = ''
app.use(store).use(router).mount('#app')

