import { ref } from 'vue'

export function useDirty() {
  const dirty = ref(false)
  function markDirty() { dirty.value = true }
  function markClean() { dirty.value = false }
  return { dirty, markDirty, markClean }
}
