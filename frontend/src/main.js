import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router.js'
import './main.css'

// A page left open across an update asks for script files the new build no longer has: load the
// page the user was opening from the server, once (at most once a minute, so a real outage cannot
// loop). The router guard below remembers which page that is.
let opening = null
router.beforeEach((to) => { opening = to.fullPath })
window.addEventListener('vite:preloadError', (e) => {
  try {
    if (Date.now() - (Number(sessionStorage.getItem('sp-reloaded')) || 0) < 60000) return
    sessionStorage.setItem('sp-reloaded', String(Date.now()))
  } catch { return } // without storage a second failure cannot be told apart: leave the error as it is
  e.preventDefault()
  window.location.assign(opening || window.location.href)
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
