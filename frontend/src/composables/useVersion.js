import { ref, computed } from 'vue'
import { api, storageGet } from './useApi.js'

// The version this page was built from (vite.config.js) and the one the server runs. They differ
// when the browser still shows the page of an earlier SwitchPilot after an update.
const app = __APP_VERSION__
const server = ref('')
let lastCheck = 0
let later = null

// Asked at most once a minute, signed in only. A call within the minute is not dropped: one check
// is kept for when the minute is over.
async function check() {
  if (!storageGet('token')) return
  const wait = lastCheck + 60000 - Date.now()
  if (wait > 0) {
    if (!later) later = setTimeout(() => { later = null; check() }, wait)
    return
  }
  lastCheck = Date.now()
  try { server.value = (await api('/api/version')).version || '' } catch (e) { lastCheck = 0 }
}

// Checked again whenever the user comes back to the page (other tab, other window such as the
// terminal that ran the update, network back); the side menu also checks on each new section.
let watching = false
function watchReturns() {
  if (watching) return
  watching = true
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') check() })
  window.addEventListener('focus', check)
  window.addEventListener('online', check)
}

export function useVersion() {
  watchReturns()
  return {
    app,
    server,
    // what runs on the server; the page's own build until the server answered
    shown: computed(() => server.value || app),
    stale: computed(() => !!server.value && server.value !== app),
    check,
  }
}
