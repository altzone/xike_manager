import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../composables/useApi.js'

export const useSwitchesStore = defineStore('switches', () => {
  const list = ref([])
  const loaded = ref(false)
  const currentId = ref(null)
  // live status of the current switch, maintained by SwitchView
  const status = ref({ online: null, temperature: '', checked: false })

  const current = computed(() => list.value.find(s => s.id === currentId.value) || null)
  // settings SwitchPilot cannot change yet on this switch's firmware line (2.0.0.x), from the backend
  function readOnly(feature) { return (current.value?.read_only || []).includes(feature) }

  async function load() {
    list.value = await api('/api/switches')
    loaded.value = true
    return list.value
  }

  function setCurrent(id) {
    if (currentId.value !== id) status.value = { online: null, temperature: '', checked: false }
    currentId.value = id
  }

  function patch(id, data) {
    const i = list.value.findIndex(s => s.id === id)
    if (i >= 0) list.value[i] = { ...list.value[i], ...data }
  }

  return { list, loaded, currentId, current, status, load, setCurrent, patch, readOnly }
})
