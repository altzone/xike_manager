<template>
  <div>
    <h1 class="text-xl font-bold text-gray-900 mb-6">VLAN Configuration</h1>

    <!-- Limits warning -->
    <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-6 text-sm text-amber-800 flex items-start gap-2">
      <svg class="w-5 h-5 text-amber-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
      </svg>
      <div>
        <strong>Hardware limits:</strong> Native VLAN (PVID) max <strong>63</strong> &mdash;
        Tag VLAN entries: <strong>{{ tagEntries.length }}/111</strong> used &mdash;
        Port 1 is management (flat mode)
      </div>
    </div>

    <!-- Port VLAN assignment -->
    <div class="bg-white rounded-xl border overflow-hidden mb-6">
      <div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <h2 class="font-semibold text-gray-700">Port Assignment</h2>
        <button @click="savePortVlans" :disabled="saving"
          class="px-3 py-1.5 bg-indigo-600 text-white text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-50">
          {{ saving ? 'Saving...' : 'Apply & Save' }}
        </button>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b">
          <tr>
            <th class="px-4 py-2 text-left font-medium text-gray-500">Port</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">Type</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">Mode</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">PVID / Native</th>
          </tr>
        </thead>
        <tbody class="divide-y">
          <tr v-for="pv in portVlans" :key="pv.port" class="hover:bg-gray-50"
            :class="pv.port === 1 ? 'bg-yellow-50' : ''">
            <td class="px-4 py-2 font-medium">
              {{ pv.port }}
              <span v-if="pv.port === 1" class="text-[10px] bg-yellow-200 text-yellow-800 px-1.5 py-0.5 rounded ml-1">MGMT</span>
            </td>
            <td class="px-4 py-2 text-gray-500">{{ pv.port >= 9 ? 'SFP+ 10G' : 'RJ45 2.5G' }}</td>
            <td class="px-4 py-2">
              <select v-model="pv.mode" :disabled="pv.port === 1"
                class="px-2 py-1 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none disabled:bg-gray-100">
                <option value="flat">Flat (no VLAN)</option>
                <option value="access">Access</option>
                <option value="trunk">Trunk</option>
              </select>
            </td>
            <td class="px-4 py-2">
              <div class="flex items-center gap-2">
                <input v-if="pv.mode !== 'flat'" v-model.number="pv.pvid" type="number" min="0" :max="63"
                  class="w-20 px-2 py-1 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  :class="pv.pvid > 63 ? 'border-red-500 bg-red-50' : ''"/>
                <span v-if="pv.pvid > 63 && pv.mode !== 'flat'" class="text-red-500 text-xs">Max 63!</span>
                <span v-if="pv.mode === 'flat'" class="text-gray-400 text-xs">N/A</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Tag VLANs -->
    <div class="bg-white rounded-xl border overflow-hidden">
      <div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <h2 class="font-semibold text-gray-700">Tagged VLANs (802.1Q)</h2>
        <div class="flex gap-2">
          <button @click="showAddTag = true"
            class="px-3 py-1.5 bg-emerald-600 text-white text-xs rounded-lg hover:bg-emerald-700">Add Entry</button>
          <button @click="saveTagVlans" :disabled="saving"
            class="px-3 py-1.5 bg-indigo-600 text-white text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-50">Apply & Save</button>
        </div>
      </div>
      <table v-if="tagEntries.length" class="w-full text-sm">
        <thead class="bg-gray-50 border-b">
          <tr>
            <th class="px-4 py-2 text-left font-medium text-gray-500">#</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">Port</th>
            <th class="px-4 py-2 text-left font-medium text-gray-500">VLAN ID</th>
          </tr>
        </thead>
        <tbody class="divide-y">
          <tr v-for="te in tagEntries" :key="te.entry" class="hover:bg-gray-50">
            <td class="px-4 py-2 text-gray-400">{{ te.entry }}</td>
            <td class="px-4 py-2 font-medium">Port {{ te.port }}</td>
            <td class="px-4 py-2">
              <span class="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded text-xs font-medium">VLAN {{ te.vlan_id }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-center text-gray-400 py-6">No tagged VLAN entries</p>
    </div>

    <!-- Add tag modal -->
    <div v-if="showAddTag" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="showAddTag = false">
      <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <h2 class="text-lg font-bold mb-4">Add Tagged VLAN</h2>
        <form @submit.prevent="addTag" class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Port</label>
            <select v-model.number="newTag.port" class="w-full px-3 py-2 border rounded-lg">
              <option v-for="p in 10" :key="p" :value="p">Port {{ p }}{{ p >= 9 ? ' (SFP+)' : '' }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">VLAN ID (1-4095)</label>
            <input v-model.number="newTag.vlan_id" type="number" min="1" max="4095" required
              class="w-full px-3 py-2 border rounded-lg"/>
          </div>
          <div class="flex gap-3 pt-2">
            <button type="button" @click="showAddTag = false" class="flex-1 py-2 border rounded-lg">Cancel</button>
            <button type="submit" class="flex-1 py-2 bg-emerald-600 text-white rounded-lg">Add</button>
          </div>
        </form>
      </div>
    </div>

    <p v-if="msg" class="mt-4 text-sm" :class="msgOk ? 'text-emerald-600' : 'text-red-500'">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../composables/useApi.js'

const props = defineProps({ switchId: Number })
const portVlans = ref([])
const tagEntries = ref([])
const saving = ref(false)
const msg = ref('')
const msgOk = ref(true)
const showAddTag = ref(false)
const newTag = ref({ port: 7, vlan_id: 10 })

async function load() {
  portVlans.value = await api(`/api/switches/${props.switchId}/vlans/port`)
  tagEntries.value = await api(`/api/switches/${props.switchId}/vlans/tag`)
}

async function savePortVlans() {
  saving.value = true; msg.value = ''
  try {
    const configs = portVlans.value.filter(p => p.port !== 1)
    await api(`/api/switches/${props.switchId}/vlans/port`, { method: 'POST', body: JSON.stringify(configs) })
    msg.value = 'Port VLANs saved'; msgOk.value = true
    await load()
  } catch (e) { msg.value = e.message; msgOk.value = false }
  finally { saving.value = false }
}

async function saveTagVlans() {
  saving.value = true; msg.value = ''
  try {
    await api(`/api/switches/${props.switchId}/vlans/tag`, { method: 'POST', body: JSON.stringify(tagEntries.value) })
    msg.value = 'Tag VLANs saved'; msgOk.value = true
    await load()
  } catch (e) { msg.value = e.message; msgOk.value = false }
  finally { saving.value = false }
}

function addTag() {
  const nextEntry = tagEntries.value.length ? Math.max(...tagEntries.value.map(e => e.entry)) + 1 : 0
  tagEntries.value.push({ entry: nextEntry, port: newTag.value.port, vlan_id: newTag.value.vlan_id })
  showAddTag.value = false
  newTag.value = { port: 7, vlan_id: 10 }
}

onMounted(load)
</script>
