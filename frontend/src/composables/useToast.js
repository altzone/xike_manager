import { ref } from 'vue'

const toasts = ref([])
let nextId = 0

export function useToast() {
  function show(msg, ok = true) {
    const id = nextId++
    toasts.value.push({ id, msg, ok })
    setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, 3500)
  }
  function success(msg) { show(msg, true) }
  function error(msg) { show(msg, false) }
  return { toasts, show, success, error }
}
