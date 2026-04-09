<template>
  <div class="space-y-6">
    <h1 class="text-xl font-bold text-gray-900">Port Configuration</h1>

    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <p class="text-xs text-gray-400">Click a setting to change it. Changes apply immediately.</p>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-gray-50/80">
          <tr>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Port</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Description</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Status</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Speed Config</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Actual</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Flow Ctrl</th>
            <th class="px-5 py-3 text-right font-medium text-gray-500 text-xs uppercase tracking-wider">TX</th>
            <th class="px-5 py-3 text-right font-medium text-gray-500 text-xs uppercase tracking-wider">RX</th>
            <th class="px-5 py-3 text-right font-medium text-gray-500 text-xs uppercase tracking-wider">Errors</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50">
          <tr v-for="port in ports" :key="port.port" class="hover:bg-gray-50/50 transition">
            <td class="px-5 py-3">
              <div class="flex items-center gap-2">
                <span class="font-semibold text-gray-900">{{ port.port }}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  :class="port.type?.includes('SFP') ? 'bg-violet-100 text-violet-700' : 'bg-sky-100 text-sky-700'">
                  {{ port.type }}
                </span>
              </div>
            </td>
            <td class="px-5 py-3">
              <input v-model="port.description" @blur="saveDesc(port)"
                class="w-full px-2 py-1 text-sm bg-transparent border-0 border-b border-transparent hover:border-gray-300 focus:border-indigo-500 outline-none transition"
                placeholder="Add description..."/>
            </td>
            <td class="px-5 py-3">
              <button @click="togglePort(port)"
                class="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full transition cursor-pointer"
                :class="port.status === 'Enabled' ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100' : 'bg-red-50 text-red-600 hover:bg-red-100'">
                <span class="w-1.5 h-1.5 rounded-full" :class="port.status === 'Enabled' ? 'bg-emerald-500' : 'bg-red-400'"></span>
                {{ port.status === 'Enabled' ? 'Enabled' : 'Disabled' }}
              </button>
            </td>
            <td class="px-5 py-3">
              <select v-model="port.speed_config" @change="applyPort(port)"
                class="px-2 py-1 bg-gray-50 border border-gray-200 rounded-lg text-xs focus:ring-2 focus:ring-indigo-500 outline-none transition">
                <option value="Auto">Auto</option>
                <option value="10Mbps Full">10M Full</option>
                <option value="10Mbps Half">10M Half</option>
                <option value="100Mbps Full">100M Full</option>
                <option value="100Mbps Half">100M Half</option>
                <option value="1000Mbps Full">1G Full</option>
                <option value="2500Mbps Full">2.5G Full</option>
                <option v-if="port.type?.includes('SFP')" value="10Gbps Full">10G Full</option>
              </select>
            </td>
            <td class="px-5 py-3">
              <span class="text-xs font-medium" :class="port.speed_actual === 'Link Down' ? 'text-gray-400' : 'text-gray-700'">
                {{ port.speed_actual }}
              </span>
            </td>
            <td class="px-5 py-3">
              <button @click="toggleFlow(port)"
                class="text-xs px-2 py-1 rounded-lg border transition"
                :class="port.flow_ctrl_config === 'On' ? 'bg-indigo-50 border-indigo-200 text-indigo-700' : 'bg-gray-50 border-gray-200 text-gray-400'">
                {{ port.flow_ctrl_config }}
              </button>
            </td>
            <td class="px-5 py-3 text-right font-mono text-gray-600 tabular-nums text-xs">
              {{ stats[port.port]?.tx_good?.toLocaleString() || '0' }}
            </td>
            <td class="px-5 py-3 text-right font-mono text-gray-600 tabular-nums text-xs">
              {{ stats[port.port]?.rx_good?.toLocaleString() || '0' }}
            </td>
            <td class="px-5 py-3 text-right">
              <span v-if="(stats[port.port]?.tx_bad || 0) + (stats[port.port]?.rx_bad || 0) > 0"
                class="text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded-full">
                {{ ((stats[port.port]?.tx_bad || 0) + (stats[port.port]?.rx_bad || 0)).toLocaleString() }}
              </span>
              <span v-else class="text-xs text-gray-300">0</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="msg" class="text-sm" :class="msgOk ? 'text-emerald-600' : 'text-red-500'">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'

const props = defineProps({ switchId: Number })
const toast = useToast()
const ports = ref([])
const statsRaw = ref([])
const msg = ref('')
const msgOk = ref(true)
const stats = computed(() => {
  const m = {}; statsRaw.value.forEach(s => m[s.port] = s); return m
})

function flash(m, ok = true) { ok ? toast.success(m) : toast.error(m) }

async function saveDesc(port) {
  await api(`/api/switches/${props.switchId}/ports/description`, {
    method: 'POST', body: JSON.stringify({ port: port.port, description: port.description })
  })
  flash(`Port ${port.port} description saved`)
}

async function applyPort(port) {
  try {
    await api(`/api/switches/${props.switchId}/ports/config`, {
      method: 'POST', body: JSON.stringify([{
        port: port.port, enabled: port.status === 'Enabled',
        speed: port.speed_config, flow_ctrl: port.flow_ctrl_config
      }])
    })
    flash(`Port ${port.port} updated`)
    await reload()
  } catch (e) { flash(e.message, false) }
}

async function togglePort(port) {
  port.status = port.status === 'Enabled' ? 'Disabled' : 'Enabled'
  await applyPort(port)
}

async function toggleFlow(port) {
  port.flow_ctrl_config = port.flow_ctrl_config === 'On' ? 'Off' : 'On'
  await applyPort(port)
}

async function reload() {
  ports.value = await api(`/api/switches/${props.switchId}/ports`)
  statsRaw.value = await api(`/api/switches/${props.switchId}/ports/stats`)
}

onMounted(reload)
</script>
