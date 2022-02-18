import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// const path = require('path')
import { resolve } from 'path'
let urlLieu = 'http://m.django-local.org:8002'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "/src"),
      "~@": resolve(__dirname, "/src")
    },
  },
  server: {
    // pour exposer le port d'un container docker
    host: true,
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': urlLieu,
      '/media': urlLieu
    }
  }
})
