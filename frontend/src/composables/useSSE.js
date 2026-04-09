import { ref, onUnmounted } from 'vue'

export function useSSE(switchId) {
  const data = ref(null)
  const connected = ref(false)
  let source = null

  function connect() {
    const token = localStorage.getItem('token')
    source = new EventSource(`/api/switches/${switchId}/sse?token=${token}`)
    source.addEventListener('stats', (e) => {
      data.value = JSON.parse(e.data)
      connected.value = true
    })
    source.addEventListener('error', () => {
      connected.value = false
    })
    source.onerror = () => {
      connected.value = false
      setTimeout(() => { if (source) connect() }, 5000)
    }
  }

  function disconnect() {
    if (source) { source.close(); source = null }
    connected.value = false
  }

  onUnmounted(disconnect)
  return { data, connected, connect, disconnect }
}
