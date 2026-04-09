<template>
  <div class="space-y-6">
    <div class="flex items-center gap-2"><h1 class="text-xl font-bold text-gray-900">Monitoring</h1><Tip title="MAC Address Table">The switch learns which devices are connected to which ports by inspecting source MAC addresses. This table shows all learned entries with their port, age timer, and VLAN group.</Tip></div>

    <!-- MAC Table -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 class="font-semibold text-gray-900">MAC Address Table</h2>
          <p class="text-xs text-gray-400 mt-0.5">{{ total }} entries learned</p>
        </div>
        <div class="flex items-center gap-3">
          <div class="relative">
            <svg class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
            <input v-model="search" @input="doSearch" placeholder="Search MAC..."
              class="pl-9 pr-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none w-56 transition"/>
          </div>
          <button @click="refresh" class="p-2 text-gray-400 hover:text-gray-600 transition">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          </button>
          <button @click="clearMacs" class="text-xs text-red-500 hover:text-red-700 transition">Clear All</button>
        </div>
      </div>
      <table v-if="macs.length" class="w-full text-sm">
        <thead class="bg-gray-50/80">
          <tr>
            <th class="px-5 py-2.5 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">#</th>
            <th class="px-5 py-2.5 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">MAC Address</th>
            <th class="px-5 py-2.5 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Port</th>
            <th class="px-5 py-2.5 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">FID</th>
            <th class="px-5 py-2.5 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Age (s)</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50">
          <tr v-for="m in macs" :key="m.idx" class="hover:bg-gray-50/50 transition">
            <td class="px-5 py-2.5 text-gray-400">{{ m.idx }}</td>
            <td class="px-5 py-2.5 font-mono text-gray-900 font-medium">{{ m.mac }}</td>
            <td class="px-5 py-2.5">
              <span class="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded text-xs font-medium">Port {{ m.port }}</span>
            </td>
            <td class="px-5 py-2.5 text-gray-500">{{ m.fid }}</td>
            <td class="px-5 py-2.5 text-gray-500">{{ m.age }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="px-5 py-8 text-center text-gray-400 text-sm">
        {{ search ? 'No matching entries' : 'MAC table is empty' }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../composables/useApi.js'
import Tip from '../components/Tip.vue'

const props = defineProps({ switchId: Number })
const macs = ref([])
const total = ref(0)
const search = ref('')
let searchTimeout = null

async function loadMacs(query = '') {
  const url = query
    ? `/api/switches/${props.switchId}/mac/dynamic?search=${encodeURIComponent(query)}`
    : `/api/switches/${props.switchId}/mac/dynamic`
  const res = await api(url)
  macs.value = res.entries || []
  total.value = res.total || macs.value.length
}

function doSearch() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => loadMacs(search.value), 300)
}

async function refresh() { await loadMacs(search.value) }

async function clearMacs() {
  if (!confirm('Clear all dynamic MAC entries?')) return
  await api(`/api/switches/${props.switchId}/mac/clear`, { method: 'POST' })
  await loadMacs()
}

onMounted(() => loadMacs())
</script>
