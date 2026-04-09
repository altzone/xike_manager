<template>
  <div>
    <h1 class="text-xl font-bold text-gray-900 mb-6">Monitoring</h1>

    <!-- MAC Table -->
    <div class="bg-white rounded-xl border overflow-hidden mb-6">
      <div class="px-4 py-3 bg-gray-50 border-b">
        <h2 class="font-semibold text-gray-700">Dynamic MAC Table</h2>
      </div>
      <table v-if="macs.length" class="w-full text-sm">
        <thead class="bg-gray-50 border-b">
          <tr>
            <th class="px-4 py-2 text-left font-medium text-gray-500">#</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">MAC Address</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">Port</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">FID</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">Age</th>
          </tr>
        </thead>
        <tbody class="divide-y">
          <tr v-for="(m, i) in macs" :key="i" class="hover:bg-gray-50">
            <td class="px-4 py-2 text-gray-400">{{ m.idx }}</td>
            <td class="px-4 py-2 font-mono">{{ m.mac }}</td>
            <td class="px-4 py-2">{{ m.port }}</td>
            <td class="px-4 py-2 text-gray-500">{{ m.fid }}</td>
            <td class="px-4 py-2 text-gray-500">{{ m.age }}s</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-center text-gray-400 py-6">No entries</p>
    </div>

    <!-- Loop / IGMP / Storm -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="bg-white rounded-xl border p-4">
        <h3 class="font-semibold text-gray-700 mb-2">Loop Detection</h3>
        <div v-for="(v, k) in loop" :key="k" class="text-sm text-gray-500">{{ k }}: {{ v }}</div>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <h3 class="font-semibold text-gray-700 mb-2">IGMP Snooping</h3>
        <div v-for="(v, k) in igmp" :key="k" class="text-sm text-gray-500">{{ k }}: {{ v }}</div>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <h3 class="font-semibold text-gray-700 mb-2">Storm Control</h3>
        <div v-for="(v, k) in storm" :key="k" class="text-sm text-gray-500">{{ k }}: {{ v }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../composables/useApi.js'

const props = defineProps({ switchId: Number })
const macs = ref([])
const loop = ref({})
const igmp = ref({})
const storm = ref({})

onMounted(async () => {
  const raw = await api(`/api/switches/${props.switchId}/mac/dynamic`)
  macs.value = Object.keys(raw).filter(k => k.startsWith('Idx_')).map(k => {
    const e = raw[k]
    return { idx: e.Dynamic_idx, mac: e.Dynamic_mac_addr, port: e.Dynamic_portid, fid: e.Dynamic_fid, age: e.Dynamic_age_timer }
  })
  const l = await api(`/api/switches/${props.switchId}/loop`)
  loop.value = l.status || {}
  const ig = await api(`/api/switches/${props.switchId}/igmp`)
  igmp.value = ig.config || {}
  storm.value = await api(`/api/switches/${props.switchId}/storm`)
})
</script>
