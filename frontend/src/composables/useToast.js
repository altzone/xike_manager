import { reactive } from 'vue'

const state = reactive({ toasts: [] })
let nextId = 0

export function useToast() {
  function success(msg) { add(msg, true) }
  function error(msg) { add(msg, false) }
  function dismiss(id) {
    const idx = state.toasts.findIndex(t => t.id === id)
    if (idx !== -1) state.toasts.splice(idx, 1)
  }
  function add(msg, ok) {
    const id = nextId++
    state.toasts.push({ id, msg: String(msg), ok })
    if (state.toasts.length > 4) state.toasts.shift()
    setTimeout(() => dismiss(id), ok ? 3500 : 7000)  // errors stay longer
  }
  return { toasts: state.toasts, success, error, dismiss }
}
