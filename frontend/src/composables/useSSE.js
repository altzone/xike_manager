import { ref, onUnmounted } from 'vue'
import { api } from './useApi.js'

/**
 * Live stats for one switch over Server-Sent Events, with polling as a fallback.
 *
 * The stream is opened with a short-lived token (EventSource cannot send headers, so the
 * token sits in the URL and in access logs; the real session token never does).
 * One reconnect timer at a time, and nothing runs after disconnect()/unmount.
 *
 * Returns { data, connected, switchError, connect, disconnect }:
 *   - connected: stats are flowing (stream or poll)
 *   - switchError: the last backend 'switch_error' message while the switch itself is
 *     unreachable (the stream is fine), null as soon as stats arrive again
 */
export function useSSE(switchId) {
  const data = ref(null)
  const connected = ref(false)
  const switchError = ref(null)
  let source = null
  let reconnectTimer = null
  let fallbackTimer = null
  let retryCount = 0
  let active = false
  let polling = false
  let prevCounters = null // internal_port -> [tx_good, rx_good] from the previous poll
  let prevTime = null

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
      switchError.value = null
      retryCount = 0
      stopFallback()
    })
    // the backend reports a switch problem on this event; the stream itself is still up
    source.addEventListener('switch_error', (e) => {
      connected.value = false
      let msg = null
      try { msg = JSON.parse(e.data)?.error } catch (err) {}
      switchError.value = msg || 'switch_error'
    })
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

  // same delta logic as the backend stream, so pages keep reading stats[port].tx_pps while polling
  function withRates(ports) {
    const now = performance.now()
    const elapsed = prevTime ? (now - prevTime) / 1000 : 0
    for (const p of ports) {
      const key = p.internal_port ?? p.port
      const last = prevCounters?.[key]
      if (last && elapsed > 0) {
        p.tx_pps = Math.round(Math.max(0, p.tx_good - last[0]) / elapsed)
        p.rx_pps = Math.round(Math.max(0, p.rx_good - last[1]) / elapsed)
      } else {
        p.tx_pps = 0
        p.rx_pps = 0
      }
    }
    prevCounters = Object.fromEntries(ports.map(p => [p.internal_port ?? p.port, [p.tx_good, p.rx_good]]))
    prevTime = now
    return ports
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
      // a poll that resolves after the stream came back must not wipe the stream's richer payload
      if (source && connected.value) return
      data.value = { temperature: status.temperature || '?', ports: withRates(stats) }
      connected.value = !!status.online
      switchError.value = status.online ? null : (status.error || 'offline')
    } catch (e) {
      connected.value = false
      // 5xx: the backend answered but the switch did not (a network error is not a switch problem)
      if (e?.status >= 500) switchError.value = e.message
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
  return { data, connected, switchError, connect, disconnect }
}
