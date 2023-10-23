import {defineConfig} from 'vite'
import vue from '@vitejs/plugin-vue'
// const path = require('path')
import {resolve} from 'path'

let urlLieu = 'https://demo.tibillet.localhost/'

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
    // host: 'demo.tibillet.localhost',
    port: 3000,
    https: true,
    strictPort: true,
    proxy: {
      "/api": {
        target: urlLieu,
        changeOrigin: true,
        secure: false
      },
      '/medias':{
        target: urlLieu,
        changeOrigin: true,
        secure: false
      },
      '/media':{
        target: urlLieu,
        changeOrigin: true,
        secure: false
      }
    },
    hmr: false
  }
})
