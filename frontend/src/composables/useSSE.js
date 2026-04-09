import { ref, onUnmounted } from 'vue'
import { api } from './useApi.js'

export function useSSE(switchId) {
  const data = ref(null)
  const connected = ref(false)
  let source = null
  let reconnectTimer = null
  let fallbackTimer = null
  let retryCount = 0

  function connect() {
    cleanup()
    const token = localStorage.getItem('token')
    if (!token) return

    try {
      source = new EventSource(`/api/switches/${switchId}/sse?token=${token}`)

      source.addEventListener('stats', (e) => {
        data.value = JSON.parse(e.data)
        connected.value = true
        retryCount = 0
      })

      source.addEventListener('error', () => {
        connected.value = false
        scheduleReconnect()
      })

      source.onerror = () => {
        connected.value = false
        scheduleReconnect()
      }
    } catch (e) {
      connected.value = false
      startFallback()
    }
  }

  function scheduleReconnect() {
    if (source) { source.close(); source = null }
    retryCount++
    const delay = Math.min(retryCount * 3000, 30000) // backoff: 3s, 6s, 9s... max 30s
    reconnectTimer = setTimeout(() => {
      // Try SSE first, fallback to polling if it fails
      connect()
      // Also do a poll as backup
      pollOnce()
    }, delay)
  }

  async function pollOnce() {
    try {
      const stats = await api(`/api/switches/${switchId}/ports/stats`)
      const status = await api(`/api/switches/${switchId}/ping`)
      if (stats && status) {
        data.value = {
          temperature: status.temperature || '?',
          ports: stats,
        }
        connected.value = status.online
      }
    } catch (e) {
      connected.value = false
    }
  }

  function startFallback() {
    // Poll every 5s when SSE is completely broken
    if (fallbackTimer) return
    fallbackTimer = setInterval(pollOnce, 5000)
  }

  function cleanup() {
    if (source) { source.close(); source = null }
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (fallbackTimer) { clearInterval(fallbackTimer); fallbackTimer = null }
  }

  function disconnect() {
    cleanup()
    connected.value = false
  }

  onUnmounted(disconnect)
  return { data, connected, connect, disconnect }
}
