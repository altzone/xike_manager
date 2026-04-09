import { reactive } from 'vue'

const state = reactive({ toasts: [] })
let nextId = 0

export function useToast() {
  function success(msg) { add(msg, true) }
  function error(msg) { add(msg, false) }
  function add(msg, ok) {
    const id = nextId++
    state.toasts.push({ id, msg, ok })
    setTimeout(() => {
      const idx = state.toasts.findIndex(t => t.id === id)
      if (idx !== -1) state.toasts.splice(idx, 1)
    }, 3500)
  }
  return { toasts: state.toasts, success, error }
}
