import {defineConfig} from 'vite'
import vue from '@vitejs/plugin-vue'
// const path = require('path')
import {resolve} from 'path'

let urlLieu = 'https://billetistan.django-local.org'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "/src"),
      "~@": resolve(__dirname, "/src")
    },
  },
  build: {
    minify: false
  },
  server: {
    // pour exposer le port d'un conteneur docker
    host: true,
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': urlLieu,
      '/media': urlLieu
    },
    hmr: {
      protocol: 'wss',
      port: 3000,
      clientPort: 443
    },
    watch: {
      usePolling: true
    }

  }
})
