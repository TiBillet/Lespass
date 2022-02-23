import {getCurrentInstance} from 'vue'
export function getVueGlobal() {
  return getCurrentInstance().appContext.config.globalProperties
}
