<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">Configuration History</h1>
        <p class="text-sm text-gray-400 mt-1">Save, compare, download and restore switch configurations</p>
      </div>
      <div class="flex gap-2">
        <label class="px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 transition cursor-pointer flex items-center gap-1.5">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
          Import
          <input type="file" accept=".json" @change="importFile" class="hidden"/>
        </label>
        <button @click="showSave = true"
          class="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition shadow-sm flex items-center gap-1.5">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/></svg>
          Save Snapshot
        </button>
      </div>
    </div>

    <!-- Snapshots list -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div v-if="snapshots.length" class="divide-y divide-gray-50">
        <div v-for="s in snapshots" :key="s.id" class="px-5 py-4 flex items-center justify-between hover:bg-gray-50/50 transition group">
          <div class="flex items-center gap-4">
            <div class="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center shrink-0">
              <svg class="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
              </svg>
            </div>
            <div>
              <p class="font-medium text-gray-900">{{ s.name }}</p>
              <p class="text-xs text-gray-400">{{ formatDate(s.created_at) }}</p>
            </div>
          </div>
          <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition">
            <button @click="viewSnapshot(s)" class="px-3 py-1.5 text-xs bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition">View</button>
            <button @click="downloadSnapshot(s)" class="px-3 py-1.5 text-xs bg-indigo-50 text-indigo-600 rounded-lg hover:bg-indigo-100 transition">Download</button>
            <button @click="deleteSnapshot(s.id)" class="px-3 py-1.5 text-xs bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition">Delete</button>
          </div>
        </div>
      </div>
      <div v-else class="px-5 py-12 text-center">
        <div class="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
          <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/></svg>
        </div>
        <p class="text-gray-400 text-sm">No snapshots yet</p>
        <p class="text-gray-300 text-xs mt-1">Save your first configuration snapshot</p>
      </div>
    </div>

    <!-- View modal -->
    <div v-if="viewing" class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" @click.self="viewing = null">
      <div class="bg-white rounded-2xl p-6 w-full max-w-2xl shadow-2xl max-h-[80vh] overflow-auto">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-bold text-gray-900">{{ viewing.name }}</h2>
          <button @click="viewing = null" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <pre class="text-xs bg-gray-50 rounded-lg p-4 overflow-auto max-h-[60vh] font-mono text-gray-700">{{ JSON.stringify(viewing.config, null, 2) }}</pre>
      </div>
    </div>

    <!-- Save modal -->
    <div v-if="showSave" class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" @click.self="showSave = false">
      <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <h2 class="text-lg font-bold text-gray-900 mb-4">Save Configuration Snapshot</h2>
        <form @submit.prevent="saveSnapshot" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input v-model="saveName" required placeholder="e.g. Before VLAN change" autofocus
              class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none transition"/>
          </div>
          <p class="text-xs text-gray-400">This will capture all current switch settings: ports, VLANs, STP, LAG, IGMP, etc.</p>
          <div class="flex gap-3">
            <button type="button" @click="showSave = false" class="flex-1 py-2.5 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition">Cancel</button>
            <button type="submit" :disabled="saving" class="flex-1 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition disabled:opacity-50">
              {{ saving ? 'Saving...' : 'Save' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <p v-if="msg" class="text-sm" :class="msgOk ? 'text-emerald-600' : 'text-red-500'">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../composables/useApi.js'

const props = defineProps({ switchId: Number })
const snapshots = ref([])
const showSave = ref(false)
const saveName = ref('')
const saving = ref(false)
const viewing = ref(null)
const msg = ref('')
const msgOk = ref(true)

function flash(m, ok = true) { msg.value = m; msgOk.value = ok; setTimeout(() => msg.value = '', 3000) }

function formatDate(d) {
  if (!d) return ''
  return new Date(d + 'Z').toLocaleString()
}

async function load() {
  snapshots.value = await api(`/api/switches/${props.switchId}/snapshots`)
}

async function saveSnapshot() {
  saving.value = true
  try {
    await api(`/api/switches/${props.switchId}/snapshots`, {
      method: 'POST', body: JSON.stringify({ name: saveName.value })
    })
    showSave.value = false; saveName.value = ''
    flash('Snapshot saved'); await load()
  } catch (e) { flash(e.message, false) }
  finally { saving.value = false }
}

async function viewSnapshot(s) {
  const full = await api(`/api/switches/${props.switchId}/snapshots/${s.id}`)
  viewing.value = full
}

async function downloadSnapshot(s) {
  const full = await api(`/api/switches/${props.switchId}/snapshots/${s.id}`)
  const blob = new Blob([JSON.stringify(full, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `${s.name.replace(/\s+/g, '_')}_${s.id}.json`; a.click()
  URL.revokeObjectURL(url)
}

async function deleteSnapshot(id) {
  if (!confirm('Delete this snapshot?')) return
  await api(`/api/switches/${props.switchId}/snapshots/${id}`, { method: 'DELETE' })
  flash('Snapshot deleted'); await load()
}

async function importFile(e) {
  const file = e.target.files[0]
  if (!file) return
  const text = await file.text()
  try {
    const data = JSON.parse(text)
    const config = data.config || data
    const name = data.name || file.name.replace('.json', '')
    await api(`/api/switches/${props.switchId}/snapshots/import`, {
      method: 'POST', body: JSON.stringify({ name: `Imported: ${name}`, config })
    })
    flash('Snapshot imported'); await load()
  } catch (err) { flash('Invalid JSON file', false) }
  e.target.value = ''
}

onMounted(load)
</script>
