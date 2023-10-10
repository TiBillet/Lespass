import { createApp, markRaw } from "vue";
import { createPinia } from "pinia";
import piniaPluginPersistedstate from "pinia-plugin-persistedstate";
import router from "./router";
import App from "./App.vue";
import mitt from "mitt";


// bootstrap 5.3.2
import 'bootstrap/dist/css/bootstrap.min.css'
import * as Bootstrap from 'bootstrap/dist/js/bootstrap.bundle.js'
window.bootstrap = Bootstrap

// material-kit-2
import './assets/css/material-kit-2/material-kit.min.css'

// import the fontawesome core
// import { library } from '@fortawesome/fontawesome-svg-core'
// import font awesome icon component
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
// import specific icons
// import { faMagnifyingGlass } from '@fortawesome/free-solid-svg-icons'

// add icons to the library
// library.add(faMagnifyingGlass)

window.emitter = mitt();

const pinia = createPinia();
pinia.use(piniaPluginPersistedstate);

// permettre l'utilisation du router dans le store, exemple: this.router.push('/')
pinia.use(({ store }) => {
  store.router = markRaw(router);
});

const app = createApp(App);

// ajout "blobal" du composant "font-awesome-icon" 
app.component('font-awesome-icon', FontAwesomeIcon)

// --- directives ---
/**
 * Focus l'élément ayant l'id  = bunding.value
 */
app.directive("focuselement", (el, binding) => {
  el.addEventListener("click", () => {
    document.querySelector(`#${binding.value}`).focus();
  });
});

app.use(pinia).use(router).mount("#app");
