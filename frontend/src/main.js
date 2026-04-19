import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import { routes, installGuards } from './router'
import './assets/main.css'

const app = createApp(App)
const pinia = createPinia()
const router = createRouter({ history: createWebHistory(), routes })

installGuards(router)

app.use(pinia)
app.use(router)
app.mount('#app')
