/// <reference types="vite/client" />

import type { Ref } from '@histoire/vendors/vue'

declare module '*.vue' {
  import { ComponentOptions } from 'vue'
  const comp: ComponentOptions
  export default comp
}

global {
  interface Window {
    __hst_controls_dark: Ref<boolean>[]
    __hst_controls_dark_ready: () => void
  }
}
