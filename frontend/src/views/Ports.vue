<template>
  <div>
    <h1 class="text-xl font-bold text-gray-900 mb-6">Port Configuration</h1>
    <div class="bg-white rounded-xl border overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b">
          <tr>
            <th class="px-4 py-3 text-left font-medium text-gray-500">Port</th>
            <th class="px-4 py-3 text-left font-medium text-gray-500">Type</th>
            <th class="px-4 py-3 text-left font-medium text-gray-500">Status</th>
            <th class="px-4 py-3 text-left font-medium text-gray-500">Speed</th>
            <th class="px-4 py-3 text-left font-medium text-gray-500">Flow Control</th>
            <th class="px-4 py-3 text-right font-medium text-gray-500">TX Good</th>
            <th class="px-4 py-3 text-right font-medium text-gray-500">RX Good</th>
          </tr>
        </thead>
        <tbody class="divide-y">
          <tr v-for="port in ports" :key="port.port" class="hover:bg-gray-50">
            <td class="px-4 py-3 font-medium">{{ port.port }}</td>
            <td class="px-4 py-3 text-gray-500">{{ port.type }}</td>
            <td class="px-4 py-3">
              <span class="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full"
                :class="port.speed_actual !== 'Link Down' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'">
                <span class="w-1.5 h-1.5 rounded-full" :class="port.speed_actual !== 'Link Down' ? 'bg-emerald-500' : 'bg-gray-400'"></span>
                {{ port.speed_actual === 'Link Down' ? 'Down' : 'Up' }}
              </span>
            </td>
            <td class="px-4 py-3 text-gray-600">{{ port.speed_actual }}</td>
            <td class="px-4 py-3 text-gray-500">{{ port.flow_ctrl_actual }}</td>
            <td class="px-4 py-3 text-right font-mono text-gray-600">{{ stats[port.port]?.tx_good?.toLocaleString() || '-' }}</td>
            <td class="px-4 py-3 text-right font-mono text-gray-600">{{ stats[port.port]?.rx_good?.toLocaleString() || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../composables/useApi.js'

const props = defineProps({ switchId: Number })
const ports = ref([])
const statsRaw = ref([])
const stats = computed(() => {
  const map = {}
  statsRaw.value.forEach(s => map[s.port] = s)
  return map
})

onMounted(async () => {
  ports.value = await api(`/api/switches/${props.switchId}/ports`)
  statsRaw.value = await api(`/api/switches/${props.switchId}/ports/stats`)
})
</script>
