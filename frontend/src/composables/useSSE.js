import { ref, onUnmounted } from 'vue'
import { api } from './useApi.js'

/**
 * Live stats for one switch over Server-Sent Events, with polling as a fallback.
 *
 * The stream is opened with a short-lived token (EventSource cannot send headers, so the
 * token sits in the URL and in access logs; the real session token never does).
 * One reconnect timer at a time, and nothing runs after disconnect()/unmount.
 */
export function useSSE(switchId) {
  const data = ref(null)
  const connected = ref(false)
  let source = null
  let reconnectTimer = null
  let fallbackTimer = null
  let retryCount = 0
  let active = false
  let polling = false

  async function connect() {
    active = true
    cleanup()
    let token
    try {
      token = (await api('/api/auth/stream-token', { method: 'POST' })).token
    } catch (e) {
      // poll meanwhile, and keep trying to get back on the stream (backend restart, proxy hiccup)
      if (active) { startFallback(); scheduleReconnect() }
      return
    }
    if (!active) return

    source = new EventSource(`/api/switches/${switchId}/sse?token=${encodeURIComponent(token)}`)
    source.addEventListener('stats', (e) => {
      data.value = JSON.parse(e.data)
      connected.value = true
      retryCount = 0
      stopFallback()
    })
    // the backend reports a switch problem on this event; the stream itself is still up
    source.addEventListener('switch_error', () => { connected.value = false })
    // connection-level failure (proxy, expired stream token, restart): reconnect with backoff
    source.onerror = () => {
      connected.value = false
      scheduleReconnect()
    }
  }

  function scheduleReconnect() {
    if (!active) return
    if (source) { source.close(); source = null }
    if (reconnectTimer) return
    retryCount++
    const delay = Math.min(retryCount * 3000, 30000) // 3s, 6s, 9s... max 30s
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (!active) return
      pollOnce()
      connect()
    }, delay)
  }

  async function pollOnce() {
    if (polling || !active) return
    polling = true
    try {
      const [stats, status] = await Promise.all([
        api(`/api/switches/${switchId}/ports/stats`),
        api(`/api/switches/${switchId}/ping`),
      ])
      if (!active) return
      data.value = { temperature: status.temperature || '?', ports: stats }
      connected.value = !!status.online
    } catch (e) {
      connected.value = false
    } finally {
      polling = false
    }
  }

  function startFallback() {
    if (fallbackTimer || !active) return
    pollOnce()
    fallbackTimer = setInterval(pollOnce, 5000)
  }

  function stopFallback() {
    if (fallbackTimer) { clearInterval(fallbackTimer); fallbackTimer = null }
  }

  function cleanup() {
    if (source) { source.close(); source = null }
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    stopFallback()
  }

  function disconnect() {
    active = false
    cleanup()
    connected.value = false
  }

  onUnmounted(disconnect)
  return { data, connected, connect, disconnect }
}
