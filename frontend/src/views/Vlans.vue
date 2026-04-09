<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-bold text-gray-900">VLAN Configuration</h1>
      <div class="flex items-center gap-2 text-xs text-gray-400">
        <span class="bg-gray-100 px-2 py-1 rounded">Tag entries: {{ limits.used }}/{{ limits.max }}</span>
        <span class="bg-amber-50 text-amber-700 px-2 py-1 rounded">Native VLAN max: 63</span>
      </div>
    </div>

    <!-- Step 1: VLANs -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 class="font-semibold text-gray-900">Networks</h2>
          <p class="text-xs text-gray-400 mt-0.5">Define your VLANs, then assign them to ports below</p>
        </div>
        <div class="flex gap-2">
          <button @click="syncVlans" :disabled="syncing"
            class="px-3.5 py-2 bg-amber-50 text-amber-700 text-sm rounded-lg hover:bg-amber-100 border border-amber-200 transition-all flex items-center gap-1.5"
            title="Copy these VLAN definitions to all other switches">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            {{ syncing ? 'Syncing...' : 'Sync to all switches' }}
          </button>
          <button @click="showAddVlan = true"
            class="px-3.5 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-all shadow-sm flex items-center gap-1.5">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
            Add VLAN
          </button>
        </div>
      </div>
      <div v-if="vlans.length" class="divide-y divide-gray-50">
        <div v-for="v in vlans" :key="v.vlan_id" class="px-5 py-3 flex items-center justify-between hover:bg-gray-50/50 transition">
          <div class="flex items-center gap-3">
            <span class="w-10 h-10 rounded-lg bg-indigo-50 flex items-center justify-center text-sm font-bold text-indigo-600">{{ v.vlan_id }}</span>
            <div>
              <p class="font-medium text-gray-900">{{ v.name }}</p>
              <p class="text-xs text-gray-400">VLAN {{ v.vlan_id }}</p>
            </div>
          </div>
          <button @click="deleteVlan(v.vlan_id)" class="text-gray-300 hover:text-red-500 transition p-1">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>
        </div>
      </div>
      <div v-else class="px-5 py-8 text-center text-gray-400 text-sm">No VLANs defined. Add one to get started.</div>
    </div>

    <!-- Step 2: Port Assignment -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 class="font-semibold text-gray-900">Port Assignment</h2>
          <p class="text-xs text-gray-400 mt-0.5">Configure each port mode and VLAN membership</p>
        </div>
        <button @click="applyAll" :disabled="applying"
          class="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 transition-all shadow-sm disabled:opacity-50 flex items-center gap-1.5">
          <svg v-if="!applying" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
          <svg v-else class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
          {{ applying ? 'Applying...' : 'Apply & Save' }}
        </button>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-gray-50/80">
          <tr>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Port</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Mode</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Access / Native VLAN</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">Allowed VLANs (trunk)</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50">
          <tr v-for="pa in portAssignments" :key="pa.port" class="hover:bg-gray-50/50 transition"
            :class="pa.port === 1 ? 'bg-amber-50/30' : ''">
            <td class="px-5 py-3">
              <div class="flex items-center gap-2">
                <span class="font-semibold text-gray-900">{{ pa.port }}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  :class="pa.port >= 9 ? 'bg-violet-100 text-violet-700' : 'bg-sky-100 text-sky-700'">
                  {{ pa.port >= 9 ? 'SFP+ 10G' : 'RJ45 2.5G' }}
                </span>
                <span v-if="pa.port === 1" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">MGMT</span>
              </div>
            </td>
            <td class="px-5 py-3">
              <select v-model="pa.mode" :disabled="pa.port === 1"
                class="px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none disabled:opacity-50 transition">
                <option value="flat">Flat</option>
                <option value="access">Access</option>
                <option value="trunk">Trunk</option>
              </select>
            </td>
            <td class="px-5 py-3">
              <select v-if="pa.mode === 'access'" v-model.number="pa.access_vlan"
                class="px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none transition">
                <option v-for="v in vlans" :key="v.vlan_id" :value="v.vlan_id"
                  :disabled="v.vlan_id > 63">
                  {{ v.name }} ({{ v.vlan_id }}){{ v.vlan_id > 63 ? ' - exceeds PVID limit!' : '' }}
                </option>
              </select>
              <select v-else-if="pa.mode === 'trunk'" v-model.number="pa.native_vlan"
                class="px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none transition">
                <option v-for="v in vlans.filter(x => x.vlan_id <= 63)" :key="v.vlan_id" :value="v.vlan_id">
                  {{ v.name }} ({{ v.vlan_id }})
                </option>
              </select>
              <span v-else class="text-gray-300 text-xs">-</span>
            </td>
            <td class="px-5 py-3">
              <div v-if="pa.mode === 'trunk'" class="flex flex-wrap gap-1.5">
                <label v-for="v in vlans" :key="v.vlan_id"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium cursor-pointer transition-all select-none"
                  :class="pa.trunk_vlans.includes(v.vlan_id) ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200' : 'bg-gray-100 text-gray-400 hover:bg-gray-200'">
                  <input type="checkbox" :value="v.vlan_id" v-model="pa.trunk_vlans" class="hidden">
                  {{ v.name }} <span class="opacity-60">{{ v.vlan_id }}</span>
                </label>
              </div>
              <span v-else class="text-gray-300 text-xs">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Status message -->
    <div v-if="msg" class="rounded-lg px-4 py-3 text-sm flex items-center gap-2 transition-all"
      :class="msgOk ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'">
      <svg v-if="msgOk" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
      <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01"/></svg>
      {{ msg }}
    </div>

    <!-- Add VLAN modal -->
    <div v-if="showAddVlan" class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" @click.self="showAddVlan = false">
      <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <h2 class="text-lg font-bold text-gray-900 mb-4">Create VLAN</h2>
        <form @submit.prevent="addVlan" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">VLAN ID</label>
            <input v-model.number="newVlan.id" type="number" min="1" max="4095" required placeholder="10"
              class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none transition"/>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input v-model="newVlan.name" required placeholder="e.g. LAN, VoIP, Guest..."
              class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none transition"/>
          </div>
          <p v-if="newVlan.id > 63" class="text-xs text-amber-600 bg-amber-50 px-3 py-2 rounded-lg">
            VLAN {{ newVlan.id }} can only be used as tagged (trunk). It cannot be set as native/access VLAN (hardware limit: max 63).
          </p>
          <div class="flex gap-3 pt-1">
            <button type="button" @click="showAddVlan = false" class="flex-1 py-2.5 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition">Cancel</button>
            <button type="submit" class="flex-1 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition shadow-sm">Create</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../composables/useApi.js'

const props = defineProps({ switchId: Number })
const vlans = ref([])
const portAssignments = ref([])
const limits = reactive({ used: 0, max: 111 })
const showAddVlan = ref(false)
const newVlan = ref({ id: '', name: '' })
const applying = ref(false)
const syncing = ref(false)
const msg = ref('')
const msgOk = ref(true)

async function load() {
  vlans.value = await api(`/api/switches/${props.switchId}/vlans`)
  const assignments = await api(`/api/switches/${props.switchId}/vlans/assignments`)
  portAssignments.value = assignments.map(a => ({
    ...a,
    access_vlan: a.mode === 'access' ? a.pvid : (vlans.value[0]?.vlan_id || 1),
    native_vlan: a.mode === 'trunk' ? a.pvid : (vlans.value.find(v => v.vlan_id <= 63)?.vlan_id || 1),
    trunk_vlans: a.trunk_vlans || [],
  }))
  const lim = await api(`/api/switches/${props.switchId}/vlans/limits`)
  limits.used = lim.used_tag_entries
  limits.max = lim.max_tag_entries
}

async function addVlan() {
  try {
    await api(`/api/switches/${props.switchId}/vlans`, {
      method: 'POST', body: JSON.stringify({ vlan_id: newVlan.value.id, name: newVlan.value.name })
    })
    showAddVlan.value = false
    newVlan.value = { id: '', name: '' }
    await load()
  } catch (e) { msg.value = e.message; msgOk.value = false }
}

async function deleteVlan(vid) {
  if (!confirm(`Delete VLAN ${vid}?`)) return
  await api(`/api/switches/${props.switchId}/vlans/${vid}`, { method: 'DELETE' })
  await load()
}

async function applyAll() {
  applying.value = true; msg.value = ''
  try {
    const assignments = portAssignments.value.filter(p => p.port !== 1).map(p => ({
      port: p.port,
      mode: p.mode,
      access_vlan: p.mode === 'access' ? p.access_vlan : null,
      native_vlan: p.mode === 'trunk' ? p.native_vlan : null,
      trunk_vlans: p.mode === 'trunk' ? p.trunk_vlans : null,
    }))
    const res = await api(`/api/switches/${props.switchId}/vlans/apply`, {
      method: 'POST', body: JSON.stringify(assignments)
    })
    msg.value = `Applied: ${res.port_vlans} port configs, ${res.tag_entries} tag entries`
    msgOk.value = true
    await load()
  } catch (e) { msg.value = e.message; msgOk.value = false }
  finally { applying.value = false }
}

async function syncVlans() {
  if (!confirm('Copy all VLAN definitions from this switch to every other switch?')) return
  syncing.value = true
  try {
    const res = await api(`/api/switches/${props.switchId}/vlans/sync`, { method: 'POST' })
    msg.value = `Synced to ${res.targets} switch(es)`; msgOk.value = true
  } catch (e) { msg.value = e.message; msgOk.value = false }
  finally { syncing.value = false }
}

onMounted(load)
</script>
