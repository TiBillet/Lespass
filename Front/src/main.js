import { createApp, markRaw } from "vue";
import { createPinia } from "pinia";
import piniaPluginPersistedstate from "pinia-plugin-persistedstate";
import router from "./router";
import App from "./App.vue";
import mitt from "mitt";


// bootstrap 5.3.2
import 'bootstrap/dist/css/bootstrap.min.css'

// material-kit-2
import './assets/css/material-kit-2/material-kit.min.css'

// import the fontawesome core 6.4.2
import { library } from '@fortawesome/fontawesome-svg-core'
// import font awesome icon component
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
// import specific icons
import { faTrashCan } from '@fortawesome/free-solid-svg-icons'
import { faSquareMinus } from '@fortawesome/free-solid-svg-icons'
import { faSquarePlus } from '@fortawesome/free-solid-svg-icons'
//
import { faPaintBrush } from '@fortawesome/free-solid-svg-icons'
import { faMusic } from '@fortawesome/free-solid-svg-icons'
import { faWheatAwn } from '@fortawesome/free-solid-svg-icons'
import { faCamera } from '@fortawesome/free-solid-svg-icons'
import { faImage } from '@fortawesome/free-solid-svg-icons'
import { faFilm } from '@fortawesome/free-solid-svg-icons'
import { faHouseFlag } from '@fortawesome/free-solid-svg-icons'
import { faPeopleGroup } from '@fortawesome/free-solid-svg-icons'
import { faBuilding } from '@fortawesome/free-solid-svg-icons'


// add icons to the library
library.add(faSquareMinus, faSquarePlus, faTrashCan, faPaintBrush,faMusic,faWheatAwn,faCamera,faImage,faFilm, faHouseFlag, faPeopleGroup, faBuilding)

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

import * as Bootstrap from "bootstrap/dist/js/bootstrap.bundle.js"
window.bootstrap = Bootstrap
