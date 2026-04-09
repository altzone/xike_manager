<template>
  <div class="space-y-6">
    <div class="flex items-center gap-2">
      <h1 class="text-xl font-bold text-gray-900">Port Configuration</h1>
      <Tip title="Port Settings">Configure physical port parameters. Changes apply immediately when you modify a setting. Descriptions are stored locally (not on the switch).</Tip>
    </div>

    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50/80">
          <tr>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-2"><span class="w-2.5"></span>Port</span></th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-1">Description <Tip>Custom label stored in SwitchPilot (not on switch hardware). Helps identify what is connected to each port.</Tip></span></th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-1">Status <Tip>Click to enable or disable a port. Disabled ports will not forward any traffic.</Tip></span></th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-1">Speed <Tip title="Speed / Duplex">Auto: negotiates best speed with the connected device. You can force a specific speed if auto-negotiation fails. RJ45 ports support up to 2.5G, SFP+ up to 10G.</Tip></span></th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-1">Link <Tip>Current link state and negotiated speed. Updates live every 3 seconds.</Tip></span></th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-1">Flow <Tip title="Flow Control (802.3x)">When enabled, the port sends PAUSE frames to slow down the sender when buffers are full. Helps prevent packet loss but can cause latency. Usually best left On.</Tip></span></th>
            <th class="px-5 py-3 text-right font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-1">TX <Tip>Total packets transmitted from this port since last reset.</Tip></span></th>
            <th class="px-5 py-3 text-right font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-1">RX <Tip>Total packets received on this port since last reset.</Tip></span></th>
            <th class="px-5 py-3 text-right font-medium text-gray-500 text-xs uppercase tracking-wider"><span class="flex items-center gap-1">Errors <Tip>Sum of TX and RX bad packets. Non-zero values may indicate cable issues, duplex mismatch, or CRC errors.</Tip></span></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50">
          <tr v-for="port in ports" :key="port.port" class="hover:bg-gray-50/50 transition">
            <td class="px-5 py-3">
              <div class="flex items-center gap-2">
                <span class="w-2.5 h-2.5 rounded-full shrink-0 transition-colors" :class="(stats[port.port]?.link && stats[port.port]?.link !== 'Link Down') ? 'bg-emerald-500 animate-pulse' : 'bg-gray-300'"></span>
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
            <td class="px-5 py-3">
              <span class="text-xs font-medium" :class="portLink(port.port) !== 'Down' ? 'text-emerald-600' : 'text-gray-400'">
                {{ portLink(port.port) }}
              </span>
            </td>
            <td class="px-5 py-3 text-right font-mono tabular-nums text-xs">
              <span class="text-gray-600">{{ stats[port.port]?.tx_good?.toLocaleString() || '0' }}</span>
              <span v-if="pps[port.port]?.tx > 0" class="text-emerald-600 ml-1">+{{ pps[port.port].tx }}/s</span>
            </td>
            <td class="px-5 py-3 text-right font-mono tabular-nums text-xs">
              <span class="text-gray-600">{{ stats[port.port]?.rx_good?.toLocaleString() || '0' }}</span>
              <span v-if="pps[port.port]?.rx > 0" class="text-emerald-600 ml-1">+{{ pps[port.port].rx }}/s</span>
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'
import Tip from '../components/Tip.vue'

const props = defineProps({ switchId: Number })
const toast = useToast()
const ports = ref([])
const statsRaw = ref([])
const prevStats = ref({})
const pps = ref({})
const msg = ref('')
const msgOk = ref(true)
let pollTimer = null
const stats = computed(() => {
  const m = {}; statsRaw.value.forEach(s => m[s.port] = s); return m
})

function portLink(port) {
  const link = stats.value[port]?.link || ''
  if (!link || link === 'Link Down') return 'Down'
  return link
}

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
  await pollStats()
}

async function pollStats() {
  try {
    const newStats = await api(`/api/switches/${props.switchId}/ports/stats`)
    // Calculate pps delta
    const newPps = {}
    for (const s of newStats) {
      const prev = prevStats.value[s.port]
      if (prev) {
        newPps[s.port] = {
          tx: Math.max(0, s.tx_good - prev.tx_good),
          rx: Math.max(0, s.rx_good - prev.rx_good),
        }
      } else {
        newPps[s.port] = { tx: 0, rx: 0 }
      }
    }
    prevStats.value = {}
    for (const s of newStats) prevStats.value[s.port] = { tx_good: s.tx_good, rx_good: s.rx_good }
    pps.value = newPps
    statsRaw.value = newStats
  } catch(e) {}
}

onMounted(() => {
  reload()
  pollTimer = setInterval(pollStats, 3000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>
