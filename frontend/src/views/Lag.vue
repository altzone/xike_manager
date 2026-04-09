<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">Link Aggregation</h1>
        <p class="text-sm text-gray-400 mt-1">Combine multiple ports into a single logical link for increased bandwidth and redundancy. Supports up to 16 LAG groups.</p>
      </div>
      <button @click="apply" :disabled="applying"
        class="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition shadow-sm disabled:opacity-50 flex items-center gap-1.5">
        <svg v-if="!applying" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
        <svg v-else class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
        {{ applying ? 'Applying...' : 'Apply' }}
      </button>
    </div>

    <!-- System Priority -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div class="flex items-center gap-4">
        <label class="text-sm font-medium text-gray-700">LACP System Priority</label>
        <input v-model.number="systemPriority" type="number" min="0" max="65535"
          class="w-32 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"/>
        <span class="text-xs text-gray-400">0 - 65535 (lower = higher priority)</span>
      </div>
    </div>

    <!-- Port table -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50/80">
          <tr>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Port</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Type</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">
              Mode
              <span class="ml-1 text-gray-400 font-normal normal-case" title="Static: manual grouping. LAG: static trunk. LACP: dynamic negotiation (802.3ad)">?</span>
            </th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">
              LACP Timeout
              <span class="ml-1 text-gray-400 font-normal normal-case" title="Short: 1s intervals. Long: 30s intervals.">?</span>
            </th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">
              Trunk Group
              <span class="ml-1 text-gray-400 font-normal normal-case" title="Assign ports to the same group number (1-16) to bond them together.">?</span>
            </th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Link</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50">
          <tr v-for="port in ports" :key="port.port" class="hover:bg-gray-50/50 transition"
            :class="port.group > 0 ? groupColor(port.group) : ''">
            <td class="px-5 py-3">
              <div class="flex items-center gap-2">
                <span class="font-semibold text-gray-900">{{ port.port }}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  :class="port.port >= 9 ? 'bg-violet-100 text-violet-700' : 'bg-sky-100 text-sky-700'">
                  {{ port.port >= 9 ? 'SFP+ 10G' : 'RJ45 2.5G' }}
                </span>
              </div>
            </td>
            <td class="px-5 py-3 text-gray-500">{{ port.port >= 9 ? '10G' : '2.5G' }}</td>
            <td class="px-5 py-3">
              <select v-model.number="port.type"
                class="px-2 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-xs focus:ring-2 focus:ring-indigo-500 outline-none transition">
                <option :value="0">Static (none)</option>
                <option :value="1">LAG (static trunk)</option>
                <option :value="2">LACP (802.3ad)</option>
              </select>
            </td>
            <td class="px-5 py-3">
              <select v-model.number="port.timeout" :disabled="port.type < 2"
                class="px-2 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-xs focus:ring-2 focus:ring-indigo-500 outline-none transition disabled:opacity-40">
                <option :value="0">Short (1s)</option>
                <option :value="1">Long (30s)</option>
              </select>
            </td>
            <td class="px-5 py-3">
              <input v-model.number="port.group" type="number" min="0" max="16" :disabled="port.type === 0"
                class="w-16 px-2 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-xs text-center focus:ring-2 focus:ring-indigo-500 outline-none transition disabled:opacity-40"
                placeholder="0"/>
            </td>
            <td class="px-5 py-3">
              <span class="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full"
                :class="port.state === 1 ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-400'">
                <span class="w-1.5 h-1.5 rounded-full" :class="port.state === 1 ? 'bg-emerald-500' : 'bg-gray-300'"></span>
                {{ port.state === 1 ? 'Up' : 'Down' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Active groups summary -->
    <div v-if="activeGroups.length" class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Active Groups</h2>
      <div class="flex flex-wrap gap-3">
        <div v-for="g in activeGroups" :key="g.id"
          class="rounded-lg border px-4 py-3" :class="groupColor(g.id)">
          <p class="text-sm font-bold">Group {{ g.id }}</p>
          <p class="text-xs text-gray-500 mt-1">
            Ports: {{ g.ports.join(', ') }} &mdash;
            {{ g.mode === 2 ? 'LACP' : 'Static LAG' }}
          </p>
        </div>
      </div>
    </div>

    <p v-if="msg" class="text-sm transition-all" :class="msgOk ? 'text-emerald-600' : 'text-red-500'">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../composables/useApi.js'

const props = defineProps({ switchId: Number })
const ports = ref([])
const systemPriority = ref(32768)
const applying = ref(false)
const msg = ref('')
const msgOk = ref(true)

const colors = [
  '', 'bg-blue-50 border-blue-200', 'bg-emerald-50 border-emerald-200', 'bg-amber-50 border-amber-200',
  'bg-purple-50 border-purple-200', 'bg-pink-50 border-pink-200', 'bg-cyan-50 border-cyan-200',
  'bg-orange-50 border-orange-200', 'bg-lime-50 border-lime-200'
]
function groupColor(g) { return colors[g % colors.length] || 'bg-gray-50 border-gray-200' }

const activeGroups = computed(() => {
  const groups = {}
  ports.value.filter(p => p.group > 0 && p.type > 0).forEach(p => {
    if (!groups[p.group]) groups[p.group] = { id: p.group, ports: [], mode: p.type }
    groups[p.group].ports.push(p.port)
  })
  return Object.values(groups).sort((a, b) => a.id - b.id)
})

async function load() {
  const data = await api(`/api/switches/${props.switchId}/lag`)
  systemPriority.value = data.system_priority
  ports.value = data.ports
}

async function apply() {
  applying.value = true; msg.value = ''
  try {
    await api(`/api/switches/${props.switchId}/lag`, {
      method: 'POST',
      body: JSON.stringify({ system_priority: systemPriority.value, ports: ports.value })
    })
    msg.value = 'LAG configuration applied'; msgOk.value = true
    await load()
  } catch (e) { msg.value = e.message; msgOk.value = false }
  finally { applying.value = false }
}

onMounted(load)
</script>
